from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.ask.models import ChatMessage, ChatMessageRole, ChatSession
from backend.ask.persistence import (
    AskPersistenceService,
    ChatSessionNotFoundError,
    persist_turn_placeholder,
)
from backend.ask.repositories import ChatMessagesRepository
from backend.core.migrations import apply_pending_migrations
from backend.tests.ask_ai_postgres import (
    POSTGRES_MARK,
    insert_auth_user,
)

MIGRATIONS_DIR = Path(__file__).parents[1] / "migrations"


def _session(user_id: UUID, session_id: UUID | None = None) -> ChatSession:
    now = datetime(2026, 7, 27, tzinfo=UTC)
    return ChatSession(
        id=session_id or uuid4(),
        user_id=user_id,
        event_id=41,
        title="Workspace",
        status="draft",
        primary_entity=None,
        primary_topic=None,
        scope_snapshot={},
        knowledge_mode_summary={},
        freshness_state=None,
        is_pinned=False,
        archived_at=None,
        deleted_at=None,
        created_at=now,
        updated_at=now,
        last_message_at=None,
    )


class FakeSessionsRepository:
    def __init__(self, owned_session: ChatSession | None) -> None:
        self.owned_session = owned_session
        self.activity_at: datetime | None = None

    def get_owned_for_update(
        self,
        *,
        session_id: UUID,
        user_id: UUID,
    ) -> ChatSession | None:
        if (
            self.owned_session is not None
            and self.owned_session.id == session_id
            and self.owned_session.user_id == user_id
        ):
            return self.owned_session
        return None

    def record_message_activity(
        self,
        *,
        session_id: UUID,
        user_id: UUID,
        message_created_at: datetime,
    ) -> ChatSession:
        assert self.owned_session is not None
        assert session_id == self.owned_session.id
        assert user_id == self.owned_session.user_id
        self.activity_at = message_created_at
        return self.owned_session


class FakeMessagesRepository:
    def __init__(self) -> None:
        self.created: list[dict[str, object]] = []

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
    ) -> ChatMessage:
        created_at = datetime(2026, 7, 27, 1, len(self.created), tzinfo=UTC)
        self.created.append(
            {
                "public_id": public_id,
                "session_id": session_id,
                "user_id": user_id,
                "event_id": event_id,
                "role": role,
                "content": content,
                "status": status,
                "response_version": response_version,
                "reply_to_message_id": reply_to_message_id,
                "parent_message_id": parent_message_id,
            }
        )
        return ChatMessage(
            id=len(self.created),
            public_id=public_id,
            session_id=session_id,
            user_id=user_id,
            event_id=event_id,
            role=role,
            content=content,
            created_at=created_at,
            status=status,
            response_version=response_version,
            reply_to_message_id=reply_to_message_id,
            parent_message_id=parent_message_id,
        )


def test_turn_coordinator_creates_ordered_owned_placeholders() -> None:
    owner_id = uuid4()
    owned_session = _session(owner_id)
    sessions = FakeSessionsRepository(owned_session)
    messages = FakeMessagesRepository()
    user_message_id = uuid4()
    assistant_message_id = uuid4()

    result = persist_turn_placeholder(
        sessions=sessions,
        messages=messages,
        session_id=owned_session.id,
        user_id=owner_id,
        user_message_id=user_message_id,
        assistant_message_id=assistant_message_id,
        content="What changed?",
    )

    assert [message["role"] for message in messages.created] == ["user", "assistant"]
    assert [message["content"] for message in messages.created] == [
        "What changed?",
        "",
    ]
    assert all(message["event_id"] == 41 for message in messages.created)
    assert [message["status"] for message in messages.created] == [
        "completed",
        "pending",
    ]
    assert messages.created[1]["response_version"] == 1
    assert messages.created[1]["reply_to_message_id"] == 1
    assert result.user_message.public_id == user_message_id
    assert result.assistant_message.public_id == assistant_message_id
    assert sessions.activity_at == result.assistant_message.created_at


def test_turn_coordinator_uses_one_non_leaking_missing_session_error() -> None:
    messages = FakeMessagesRepository()

    with pytest.raises(ChatSessionNotFoundError, match="Chat session not found"):
        persist_turn_placeholder(
            sessions=FakeSessionsRepository(None),
            messages=messages,
            session_id=uuid4(),
            user_id=uuid4(),
            user_message_id=uuid4(),
            assistant_message_id=uuid4(),
            content="Private question",
        )

    assert messages.created == []


@contextmanager
def _session_scope(engine: Engine) -> Iterator[Session]:
    database_session = Session(bind=engine)
    try:
        yield database_session
        database_session.commit()
    except Exception:
        database_session.rollback()
        raise
    finally:
        database_session.close()


@pytest.fixture
def migrated_engine(postgres_engine: Engine) -> Engine:
    apply_pending_migrations(postgres_engine, MIGRATIONS_DIR, through="0027")
    return postgres_engine


def _service(engine: Engine) -> AskPersistenceService:
    return AskPersistenceService(lambda: _session_scope(engine))


@POSTGRES_MARK
def test_owned_session_and_turn_persist_with_stable_public_ids(
    migrated_engine: Engine,
) -> None:
    owner_id = uuid4()
    session_id = uuid4()
    user_message_id = uuid4()
    assistant_message_id = uuid4()
    with migrated_engine.begin() as connection:
        insert_auth_user(connection, owner_id)

    service = _service(migrated_engine)
    created_session = service.create_session(
        session_id=session_id,
        user_id=owner_id,
        title="CERC workspace",
        primary_entity="CERC",
        primary_topic="tariff",
        scope_snapshot={"jurisdiction": "central"},
        knowledge_mode_summary={"official": True},
        freshness_state="current",
    )
    turn = service.create_turn_placeholder(
        session_id=session_id,
        user_id=owner_id,
        user_message_id=user_message_id,
        assistant_message_id=assistant_message_id,
        content="What changed?",
    )

    assert created_session.id == session_id
    assert created_session.scope_snapshot == {"jurisdiction": "central"}
    assert turn.user_message.public_id == user_message_id
    assert turn.user_message.content == "What changed?"
    assert turn.assistant_message.public_id == assistant_message_id
    assert turn.assistant_message.content == ""
    assert turn.assistant_message.status == "pending"
    assert turn.assistant_message.response_version == 1
    assert turn.assistant_message.reply_to_message_id == turn.user_message.id
    assert turn.session.last_message_at == turn.assistant_message.created_at

    with Session(migrated_engine) as database_session:
        messages = ChatMessagesRepository(database_session)
        assert messages.get_owned_by_public_id(
            public_id=user_message_id,
            user_id=owner_id,
        ) == turn.user_message
        assert messages.get_owned_by_public_id(
            public_id=user_message_id,
            user_id=uuid4(),
        ) is None


@POSTGRES_MARK
def test_cross_owner_turn_is_rejected_without_leaking_session_existence(
    migrated_engine: Engine,
) -> None:
    owner_id = uuid4()
    other_id = uuid4()
    with migrated_engine.begin() as connection:
        insert_auth_user(connection, owner_id)
        insert_auth_user(connection, other_id)

    service = _service(migrated_engine)
    owned_session = service.create_session(user_id=owner_id, title="Private")

    with pytest.raises(ChatSessionNotFoundError, match="Chat session not found"):
        service.create_turn_placeholder(
            session_id=owned_session.id,
            user_id=other_id,
            user_message_id=uuid4(),
            assistant_message_id=uuid4(),
            content="Cross-owner attempt",
        )

    with migrated_engine.connect() as connection:
        assert connection.execute(
            text(
                """
                select count(*)
                from public.chat_messages
                where session_id = :session_id
                """
            ),
            {"session_id": owned_session.id},
        ).scalar_one() == 0


@POSTGRES_MARK
def test_placeholder_failure_rolls_back_user_message_and_session_activity(
    migrated_engine: Engine,
) -> None:
    owner_id = uuid4()
    duplicate_public_id = uuid4()
    with migrated_engine.begin() as connection:
        insert_auth_user(connection, owner_id)

    service = _service(migrated_engine)
    owned_session = service.create_session(user_id=owner_id)

    with pytest.raises(IntegrityError):
        service.create_turn_placeholder(
            session_id=owned_session.id,
            user_id=owner_id,
            user_message_id=duplicate_public_id,
            assistant_message_id=duplicate_public_id,
            content="Must roll back",
        )

    with migrated_engine.connect() as connection:
        persisted_messages = connection.execute(
            text(
                """
                select count(*)
                from public.chat_messages
                where public_id = :public_id
                """
            ),
            {"public_id": duplicate_public_id},
        ).scalar_one()
        last_message_at = connection.execute(
            text(
                """
                select last_message_at
                from public.chat_sessions
                where id = :session_id
                """
            ),
            {"session_id": owned_session.id},
        ).scalar_one()

    assert persisted_messages == 0
    assert last_message_at is None
