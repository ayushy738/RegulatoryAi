from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractContextManager
from datetime import UTC, datetime
from typing import Any, Protocol
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.ask.citation_persistence import (
    CitationPersistenceRepository,
    PersistedCitationDetail,
    PersistedVerifiedClaim,
    VerifiedClaimPersistenceRequest,
)
from backend.ask.models import (
    AskFeedback,
    AskFeedbackValue,
    AskResponseLineage,
    AskResponseVersion,
    AskSavedItem,
    AskSavedItemType,
    ChatMessage,
    ChatMessageRole,
    ChatSession,
    ChatSessionExport,
    ChatSessionPage,
    ChatTurnPage,
    TurnPlaceholder,
)
from backend.ask.repositories import (
    ChatMessagesRepository,
    ChatSessionsRepository,
    ChatTurnsRepository,
    FeedbackRepository,
    ResponseVersionsRepository,
    SavedItemsRepository,
)
from backend.core.db import session_scope


class ChatSessionNotFoundError(LookupError):
    """The requested active session is missing or not owned by the caller."""


class ChatSessionStateConflictError(RuntimeError):
    """The requested session action conflicts with its lifecycle state."""


class SessionRepository(Protocol):
    def get_owned_for_update(
        self,
        *,
        session_id: UUID,
        user_id: UUID,
    ) -> ChatSession | None: ...

    def record_message_activity(
        self,
        *,
        session_id: UUID,
        user_id: UUID,
        message_created_at: datetime,
    ) -> ChatSession: ...


class MessageRepository(Protocol):
    def create(
        self,
        *,
        public_id: UUID,
        session_id: UUID,
        user_id: UUID,
        event_id: int | None,
        role: ChatMessageRole,
        content: str,
        status: str = "completed",
        response_version: int | None = None,
        reply_to_message_id: int | None = None,
        parent_message_id: int | None = None,
    ) -> ChatMessage: ...


def persist_turn_placeholder(
    *,
    sessions: SessionRepository,
    messages: MessageRepository,
    session_id: UUID,
    user_id: UUID,
    user_message_id: UUID,
    assistant_message_id: UUID,
    content: str,
) -> TurnPlaceholder:
    owned_session = sessions.get_owned_for_update(
        session_id=session_id,
        user_id=user_id,
    )
    if owned_session is None:
        raise ChatSessionNotFoundError("Chat session not found")

    user_message = messages.create(
        public_id=user_message_id,
        session_id=owned_session.id,
        user_id=owned_session.user_id,
        event_id=owned_session.event_id,
        role="user",
        content=content,
        status="completed",
    )
    assistant_message = messages.create(
        public_id=assistant_message_id,
        session_id=owned_session.id,
        user_id=owned_session.user_id,
        event_id=owned_session.event_id,
        role="assistant",
        content="",
        status="pending",
        response_version=1,
        reply_to_message_id=user_message.id,
    )
    updated_session = sessions.record_message_activity(
        session_id=owned_session.id,
        user_id=owned_session.user_id,
        message_created_at=assistant_message.created_at,
    )
    return TurnPlaceholder(
        session=updated_session,
        user_message=user_message,
        assistant_message=assistant_message,
    )


SessionScopeFactory = Callable[[], AbstractContextManager[Session]]


class AskPersistenceService:
    def __init__(
        self,
        session_scope_factory: SessionScopeFactory = session_scope,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._session_scope_factory = session_scope_factory
        self._clock = clock

    def create_session(
        self,
        *,
        user_id: UUID,
        session_id: UUID | None = None,
        event_id: int | None = None,
        title: str | None = None,
        primary_entity: str | None = None,
        primary_topic: str | None = None,
        scope_snapshot: dict[str, Any] | None = None,
        knowledge_mode_summary: dict[str, Any] | None = None,
        freshness_state: str | None = None,
    ) -> ChatSession:
        with self._session_scope_factory() as database_session:
            return ChatSessionsRepository(database_session).create(
                session_id=session_id or uuid4(),
                user_id=user_id,
                event_id=event_id,
                title=title,
                primary_entity=primary_entity,
                primary_topic=primary_topic,
                scope_snapshot=scope_snapshot,
                knowledge_mode_summary=knowledge_mode_summary,
                freshness_state=freshness_state,
            )

    def create_turn_placeholder(
        self,
        *,
        session_id: UUID,
        user_id: UUID,
        user_message_id: UUID,
        assistant_message_id: UUID,
        content: str,
    ) -> TurnPlaceholder:
        with self._session_scope_factory() as database_session:
            return persist_turn_placeholder(
                sessions=ChatSessionsRepository(database_session),
                messages=ChatMessagesRepository(database_session),
                session_id=session_id,
                user_id=user_id,
                user_message_id=user_message_id,
                assistant_message_id=assistant_message_id,
                content=content,
            )

    def get_session(
        self,
        *,
        session_id: UUID,
        user_id: UUID,
    ) -> ChatSession | None:
        with self._session_scope_factory() as database_session:
            return ChatSessionsRepository(database_session).get_owned(
                session_id=session_id,
                user_id=user_id,
            )

    def list_sessions(
        self,
        *,
        user_id: UUID,
        limit: int,
        query: str | None = None,
        knowledge_mode: str | None = None,
        entity: str | None = None,
        archived: bool = False,
        pinned: bool | None = None,
        cursor_relevance: int | None = None,
        cursor_updated_at: datetime | None = None,
        cursor_id: UUID | None = None,
    ) -> ChatSessionPage:
        with self._session_scope_factory() as database_session:
            return ChatSessionsRepository(database_session).list_owned(
                user_id=user_id,
                limit=limit,
                query=query,
                knowledge_mode=knowledge_mode,
                entity=entity,
                archived=archived,
                pinned=pinned,
                cursor_relevance=cursor_relevance,
                cursor_updated_at=cursor_updated_at,
                cursor_id=cursor_id,
            )

    def patch_session(
        self,
        *,
        session_id: UUID,
        user_id: UUID,
        title: str | None,
        is_pinned: bool | None,
    ) -> ChatSession | None:
        with self._session_scope_factory() as database_session:
            repository = ChatSessionsRepository(database_session)
            current = repository.get_owned_for_update(
                session_id=session_id,
                user_id=user_id,
            )
            if current is None:
                return None
            if is_pinned is True and current.archived_at is not None:
                raise ChatSessionStateConflictError(
                    "Archived sessions cannot be pinned"
                )
            return repository.patch_owned(
                session_id=session_id,
                user_id=user_id,
                title=title,
                is_pinned=is_pinned,
                now=self._now(),
            )

    def archive_session(
        self,
        *,
        session_id: UUID,
        user_id: UUID,
    ) -> ChatSession | None:
        with self._session_scope_factory() as database_session:
            return ChatSessionsRepository(database_session).archive_owned(
                session_id=session_id,
                user_id=user_id,
                now=self._now(),
            )

    def restore_session(
        self,
        *,
        session_id: UUID,
        user_id: UUID,
    ) -> ChatSession | None:
        with self._session_scope_factory() as database_session:
            return ChatSessionsRepository(database_session).restore_owned(
                session_id=session_id,
                user_id=user_id,
                now=self._now(),
            )

    def duplicate_session(
        self,
        *,
        session_id: UUID,
        user_id: UUID,
        duplicate_session_id: UUID | None = None,
    ) -> ChatSession | None:
        with self._session_scope_factory() as database_session:
            return ChatSessionsRepository(
                database_session
            ).duplicate_context_owned(
                source_session_id=session_id,
                duplicate_session_id=duplicate_session_id or uuid4(),
                user_id=user_id,
            )

    def soft_delete_session(
        self,
        *,
        session_id: UUID,
        user_id: UUID,
    ) -> bool | None:
        with self._session_scope_factory() as database_session:
            return ChatSessionsRepository(database_session).soft_delete_owned(
                session_id=session_id,
                user_id=user_id,
                now=self._now(),
            )

    def export_session(
        self,
        *,
        session_id: UUID,
        user_id: UUID,
    ) -> ChatSessionExport | None:
        with self._session_scope_factory() as database_session:
            database_session.execute(
                text("set transaction isolation level repeatable read")
            )
            sessions = ChatSessionsRepository(database_session)
            owned = sessions.get_owned(
                session_id=session_id,
                user_id=user_id,
            )
            if owned is None:
                return None
            turns_repository = ChatTurnsRepository(database_session)
            turns = []
            cursor_created_at = None
            cursor_id = None
            while True:
                page = turns_repository.list_owned(
                    session_id=session_id,
                    user_id=user_id,
                    limit=100,
                    cursor_created_at=cursor_created_at,
                    cursor_id=cursor_id,
                )
                turns.extend(page.items)
                if not page.has_more or not page.items:
                    break
                cursor_created_at = page.items[-1].anchor_created_at
                cursor_id = page.items[-1].anchor_id
            saved_items = SavedItemsRepository(database_session).list_owned(
                session_id=session_id,
                user_id=user_id,
            )
            if saved_items is None:
                return None
            return ChatSessionExport(
                session=owned,
                turns=tuple(turns),
                saved_items=saved_items,
            )

    def list_turns(
        self,
        *,
        session_id: UUID,
        user_id: UUID,
        limit: int,
        cursor_created_at: datetime | None = None,
        cursor_id: int | None = None,
    ) -> ChatTurnPage | None:
        with self._session_scope_factory() as database_session:
            sessions = ChatSessionsRepository(database_session)
            if sessions.get_owned(session_id=session_id, user_id=user_id) is None:
                return None
            return ChatTurnsRepository(database_session).list_owned(
                session_id=session_id,
                user_id=user_id,
                limit=limit,
                cursor_created_at=cursor_created_at,
                cursor_id=cursor_id,
            )

    def get_response_lineage(
        self,
        *,
        session_id: UUID,
        user_id: UUID,
        user_message_public_id: UUID,
    ) -> AskResponseLineage | None:
        with self._session_scope_factory() as database_session:
            return ResponseVersionsRepository(database_session).get_owned(
                session_id=session_id,
                user_id=user_id,
                user_message_public_id=user_message_public_id,
            )

    def _now(self) -> datetime:
        now = self._clock()
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("Session lifecycle clock must be timezone-aware")
        return now

    def record_feedback(
        self,
        *,
        run_id: UUID,
        session_id: UUID,
        user_id: UUID,
        response_version: int,
        value: AskFeedbackValue,
        reason_code: str | None = None,
        comment: str | None = None,
        feedback_id: UUID | None = None,
    ) -> AskFeedback | None:
        with self._session_scope_factory() as database_session:
            return FeedbackRepository(database_session).upsert_owned(
                feedback_id=feedback_id or uuid4(),
                run_id=run_id,
                session_id=session_id,
                user_id=user_id,
                response_version=response_version,
                value=value,
                reason_code=reason_code,
                comment=comment,
            )

    def get_response_version(
        self,
        *,
        assistant_message_public_id: UUID,
        user_id: UUID,
    ) -> AskResponseVersion | None:
        with self._session_scope_factory() as database_session:
            return ResponseVersionsRepository(
                database_session
            ).get_owned_by_assistant_public_id(
                assistant_message_public_id=assistant_message_public_id,
                user_id=user_id,
            )

    def persist_verified_claim(
        self,
        request: VerifiedClaimPersistenceRequest,
    ) -> PersistedVerifiedClaim:
        with self._session_scope_factory() as database_session:
            return CitationPersistenceRepository(
                database_session
            ).persist_verified_claim(request)

    def get_citation_detail(
        self,
        *,
        assistant_message_public_id: UUID,
        citation_id: UUID,
        user_id: UUID,
    ) -> PersistedCitationDetail | None:
        with self._session_scope_factory() as database_session:
            return CitationPersistenceRepository(
                database_session
            ).get_owned_citation_detail(
                assistant_message_public_id=assistant_message_public_id,
                citation_id=citation_id,
                user_id=user_id,
            )

    def record_message_feedback(
        self,
        *,
        assistant_message_public_id: UUID,
        user_id: UUID,
        value: AskFeedbackValue,
        reason_code: str | None = None,
        comment: str | None = None,
        feedback_id: UUID | None = None,
    ) -> AskFeedback | None:
        with self._session_scope_factory() as database_session:
            version = ResponseVersionsRepository(
                database_session
            ).get_owned_by_assistant_public_id(
                assistant_message_public_id=assistant_message_public_id,
                user_id=user_id,
            )
            if version is None:
                return None
            return FeedbackRepository(database_session).upsert_owned(
                feedback_id=feedback_id or uuid4(),
                run_id=version.run.id,
                session_id=version.assistant_message.session_id,
                user_id=user_id,
                response_version=version.response_version,
                value=value,
                reason_code=reason_code,
                comment=comment,
            )

    def list_saved_items(
        self,
        *,
        session_id: UUID,
        user_id: UUID,
    ) -> tuple[AskSavedItem, ...] | None:
        with self._session_scope_factory() as database_session:
            return SavedItemsRepository(database_session).list_owned(
                session_id=session_id,
                user_id=user_id,
            )

    def save_item(
        self,
        *,
        session_id: UUID,
        user_id: UUID,
        item_type: AskSavedItemType,
        target_key: str,
        saved_item_id: UUID | None = None,
    ) -> AskSavedItem | None:
        with self._session_scope_factory() as database_session:
            return SavedItemsRepository(database_session).create_owned(
                saved_item_id=saved_item_id or uuid4(),
                session_id=session_id,
                user_id=user_id,
                item_type=item_type,
                target_key=target_key,
            )

    def delete_saved_item(
        self,
        *,
        saved_item_id: UUID,
        session_id: UUID,
        user_id: UUID,
    ) -> bool:
        with self._session_scope_factory() as database_session:
            return SavedItemsRepository(database_session).delete_owned(
                saved_item_id=saved_item_id,
                session_id=session_id,
                user_id=user_id,
            )
