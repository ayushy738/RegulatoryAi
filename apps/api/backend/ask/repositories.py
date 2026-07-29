from __future__ import annotations

import json
from collections.abc import Callable
from datetime import datetime
from typing import Any, TypeVar
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import RowMapping
from sqlalchemy.orm import Session

from backend.ask.models import (
    AskCitation,
    AskClaim,
    AskFeedback,
    AskFeedbackValue,
    AskFollowup,
    AskResponseLineage,
    AskResponseVersion,
    AskRun,
    AskSavedItem,
    AskSavedItemType,
    AskSection,
    AskSource,
    ChatMessage,
    ChatMessageRole,
    ChatSession,
    ChatSessionPage,
    ChatTurn,
    ChatTurnPage,
)

ArtifactT = TypeVar("ArtifactT")

SESSION_COLUMNS = """
id,
user_id,
event_id,
title,
status,
primary_entity,
primary_topic,
scope_snapshot,
knowledge_mode_summary,
freshness_state,
is_pinned,
archived_at,
deleted_at,
created_at,
updated_at,
last_message_at
"""

QUALIFIED_SESSION_COLUMNS = """
cs.id,
cs.user_id,
cs.event_id,
cs.title,
cs.status,
cs.primary_entity,
cs.primary_topic,
cs.scope_snapshot,
cs.knowledge_mode_summary,
cs.freshness_state,
cs.is_pinned,
cs.archived_at,
cs.deleted_at,
cs.created_at,
cs.updated_at,
cs.last_message_at
"""

MESSAGE_COLUMNS = """
id,
public_id,
session_id,
user_id,
event_id,
role,
content,
created_at,
status,
response_version,
reply_to_message_id,
parent_message_id
"""

QUALIFIED_MESSAGE_COLUMNS = """
m.id,
m.public_id,
m.session_id,
m.user_id,
m.event_id,
m.role,
m.content,
m.created_at,
m.status,
m.response_version,
m.reply_to_message_id,
m.parent_message_id
"""


def _chat_session(row: RowMapping) -> ChatSession:
    return ChatSession(
        id=row["id"],
        user_id=row["user_id"],
        event_id=row["event_id"],
        title=row["title"],
        status=row["status"],
        primary_entity=row["primary_entity"],
        primary_topic=row["primary_topic"],
        scope_snapshot=dict(row["scope_snapshot"]),
        knowledge_mode_summary=dict(row["knowledge_mode_summary"]),
        freshness_state=row["freshness_state"],
        is_pinned=bool(row["is_pinned"]),
        archived_at=row["archived_at"],
        deleted_at=row["deleted_at"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        last_message_at=row["last_message_at"],
    )


def _chat_message(row: RowMapping) -> ChatMessage:
    return ChatMessage(
        id=row["id"],
        public_id=row["public_id"],
        session_id=row["session_id"],
        user_id=row["user_id"],
        event_id=row["event_id"],
        role=row["role"],
        content=row["content"],
        created_at=row["created_at"],
        status=row["status"],
        response_version=row["response_version"],
        reply_to_message_id=row["reply_to_message_id"],
        parent_message_id=row["parent_message_id"],
    )


def _optional_float(value: Any) -> float | None:
    return float(value) if value is not None else None


def _ask_section(row: RowMapping) -> AskSection:
    return AskSection(
        id=row["id"],
        response_version=row["response_version"],
        ordinal=row["ordinal"],
        section_type=row["section_type"],
        status=row["status"],
        knowledge_mode=row["knowledge_mode"],
        provenance_label=row["provenance_label"],
        title=row["title"],
        plain_text=row["plain_text"],
        content=dict(row["content"]),
        card_schema_version=row["card_schema_version"],
        model=row["model"],
        policy_version=row["policy_version"],
        prompt_version=row["prompt_version"],
        required_disclosure=row["required_disclosure"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _ask_source(row: RowMapping) -> AskSource:
    graph_reference = row["graph_reference"]
    return AskSource(
        id=row["id"],
        ordinal=row["ordinal"],
        source_key=row["source_key"],
        source_class=row["source_class"],
        source_type=row["source_type"],
        document_id=row["document_id"],
        document_version_id=row["document_version_id"],
        chunk_id=row["chunk_id"],
        graph_reference=dict(graph_reference) if graph_reference is not None else None,
        title_snapshot=row["title_snapshot"],
        url_snapshot=row["url_snapshot"],
        issuer_snapshot=row["issuer_snapshot"],
        publisher_snapshot=row["publisher_snapshot"],
        jurisdiction_snapshot=row["jurisdiction_snapshot"],
        published_at=row["published_at"],
        retrieved_at=row["retrieved_at"],
        evidence_snapshot=row["evidence_snapshot"],
        locator_snapshot=row["locator_snapshot"],
        content_hash=row["content_hash"],
        metadata=dict(row["metadata"]),
        created_at=row["created_at"],
    )


def _ask_claim(row: RowMapping) -> AskClaim:
    return AskClaim(
        id=row["id"],
        section_id=row["section_id"],
        ordinal=row["ordinal"],
        knowledge_mode=row["knowledge_mode"],
        claim_text=row["claim_text"],
        is_material=bool(row["is_material"]),
        support_status=row["support_status"],
        support_score=_optional_float(row["support_score"]),
        model=row["model"],
        policy_version=row["policy_version"],
        prompt_version=row["prompt_version"],
        required_disclosure=row["required_disclosure"],
        verifier_model=row["verifier_model"],
        verifier_policy_version=row["verifier_policy_version"],
        created_at=row["created_at"],
    )


def _ask_citation(row: RowMapping) -> AskCitation:
    return AskCitation(
        id=row["id"],
        claim_id=row["claim_id"],
        source_id=row["source_id"],
        ordinal=row["ordinal"],
        claim_knowledge_mode=row["claim_knowledge_mode"],
        source_class=row["source_class"],
        citation_kind=row["citation_kind"],
        marker=row["marker"],
        evidence_snapshot=row["evidence_snapshot"],
        locator_snapshot=row["locator_snapshot"],
        support_score=_optional_float(row["support_score"]),
        verification_status=row["verification_status"],
        verifier_model=row["verifier_model"],
        verifier_policy_version=row["verifier_policy_version"],
        created_at=row["created_at"],
    )


def _ask_followup(row: RowMapping) -> AskFollowup:
    return AskFollowup(
        id=row["id"],
        ordinal=row["ordinal"],
        label=row["label"],
        question=row["question"],
        action_type=row["action_type"],
        payload=dict(row["payload"]),
        created_at=row["created_at"],
    )


def _ask_feedback(row: RowMapping) -> AskFeedback:
    return AskFeedback(
        id=row["id"],
        run_id=row["run_id"],
        session_id=row["session_id"],
        user_id=row["user_id"],
        response_version=row["response_version"],
        value=row["value"],
        reason_code=row["reason_code"],
        comment=row["comment"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _ask_saved_item(row: RowMapping) -> AskSavedItem:
    return AskSavedItem(
        id=row["id"],
        session_id=row["session_id"],
        user_id=row["user_id"],
        item_type=row["item_type"],
        target_key=row["target_key"],
        run_id=row["run_id"],
        response_version=row["response_version"],
        source_id=row["source_id"],
        citation_id=row["citation_id"],
        section_id=row["section_id"],
        entity_id=row["entity_id"],
        document_id=row["document_id"],
        label_snapshot=row["label_snapshot"],
        metadata=dict(row["metadata"]),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


class ChatSessionsRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def create(
        self,
        *,
        session_id: UUID,
        user_id: UUID,
        event_id: int | None = None,
        title: str | None = None,
        primary_entity: str | None = None,
        primary_topic: str | None = None,
        scope_snapshot: dict[str, Any] | None = None,
        knowledge_mode_summary: dict[str, Any] | None = None,
        freshness_state: str | None = None,
    ) -> ChatSession:
        row = self._session.execute(
            text(
                f"""
                insert into public.chat_sessions (
                  id,
                  user_id,
                  event_id,
                  title,
                  primary_entity,
                  primary_topic,
                  scope_snapshot,
                  knowledge_mode_summary,
                  freshness_state
                )
                values (
                  :session_id,
                  :user_id,
                  :event_id,
                  :title,
                  :primary_entity,
                  :primary_topic,
                  cast(:scope_snapshot as jsonb),
                  cast(:knowledge_mode_summary as jsonb),
                  :freshness_state
                )
                returning {SESSION_COLUMNS}
                """
            ),
            {
                "session_id": session_id,
                "user_id": user_id,
                "event_id": event_id,
                "title": title,
                "primary_entity": primary_entity,
                "primary_topic": primary_topic,
                "scope_snapshot": json.dumps(scope_snapshot or {}),
                "knowledge_mode_summary": json.dumps(knowledge_mode_summary or {}),
                "freshness_state": freshness_state,
            },
        ).mappings().one()
        return _chat_session(row)

    def get_owned_for_update(
        self,
        *,
        session_id: UUID,
        user_id: UUID,
    ) -> ChatSession | None:
        row = self._session.execute(
            text(
                f"""
                select {SESSION_COLUMNS}
                from public.chat_sessions
                where id = :session_id
                  and user_id = :user_id
                  and deleted_at is null
                for update
                """
            ),
            {"session_id": session_id, "user_id": user_id},
        ).mappings().one_or_none()
        return _chat_session(row) if row is not None else None

    def get_owned(
        self,
        *,
        session_id: UUID,
        user_id: UUID,
    ) -> ChatSession | None:
        row = self._session.execute(
            text(
                f"""
                select {SESSION_COLUMNS}
                from public.chat_sessions
                where id = :session_id
                  and user_id = :user_id
                  and deleted_at is null
                """
            ),
            {"session_id": session_id, "user_id": user_id},
        ).mappings().one_or_none()
        return _chat_session(row) if row is not None else None

    def list_owned(
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
        parameters = {
            "user_id": user_id,
            "knowledge_mode": knowledge_mode,
            "entity": entity,
            "archived": archived,
            "pinned": pinned,
            "cursor_relevance": cursor_relevance,
            "cursor_updated_at": cursor_updated_at,
            "cursor_id": cursor_id,
            "query_limit": limit + 1,
        }
        filters = """
          and (
            (:archived and cs.archived_at is not null)
            or (not :archived and cs.archived_at is null)
          )
          and (
            cast(:pinned as boolean) is null
            or cs.is_pinned = :pinned
          )
          and (
            cast(:entity as text) is null
            or lower(
              regexp_replace(
                btrim(cs.primary_entity),
                '[[:space:]]+',
                ' ',
                'g'
              )
            ) = :entity
          )
          and (
            cast(:knowledge_mode as text) is null
            or exists (
              select 1
              from public.ask_sections search_section
              where search_section.user_id = cs.user_id
                and search_section.session_id = cs.id
                and search_section.knowledge_mode = :knowledge_mode
                and search_section.status = 'completed'
            )
          )
        """
        if query is not None:
            parameters["query"] = query
            rows = list(
                self._session.execute(
                    text(
                        f"""
                        with search_query as (
                          select plainto_tsquery('simple', :query) as value
                        ),
                        matches as (
                          select search_session.id as session_id, 500 as relevance
                          from public.chat_sessions search_session
                          cross join search_query
                          where search_session.user_id = :user_id
                            and (
                              setweight(
                                to_tsvector(
                                  'simple',
                                  coalesce(search_session.title, '')
                                ),
                                'A'
                              )
                              || setweight(
                                to_tsvector(
                                  'simple',
                                  coalesce(search_session.primary_entity, '')
                                ),
                                'B'
                              )
                              || setweight(
                                to_tsvector(
                                  'simple',
                                  coalesce(search_session.primary_topic, '')
                                ),
                                'C'
                              )
                            ) @@ search_query.value

                          union all

                          select search_message.session_id, 400 as relevance
                          from public.chat_messages search_message
                          cross join search_query
                          where search_message.user_id = :user_id
                            and search_message.session_id is not null
                            and to_tsvector(
                              'simple',
                              coalesce(search_message.content, '')
                            ) @@ search_query.value

                          union all

                          select search_source.session_id, 300 as relevance
                          from public.ask_sources search_source
                          cross join search_query
                          where search_source.user_id = :user_id
                            and (
                              setweight(
                                to_tsvector(
                                  'simple',
                                  coalesce(search_source.title_snapshot, '')
                                ),
                                'A'
                              )
                              || setweight(
                                to_tsvector(
                                  'simple',
                                  coalesce(search_source.issuer_snapshot, '')
                                ),
                                'B'
                              )
                              || setweight(
                                to_tsvector(
                                  'simple',
                                  coalesce(search_source.publisher_snapshot, '')
                                ),
                                'B'
                              )
                              || setweight(
                                to_tsvector(
                                  'simple',
                                  coalesce(search_source.evidence_snapshot, '')
                                ),
                                'C'
                              )
                              || setweight(
                                to_tsvector(
                                  'simple',
                                  coalesce(search_source.locator_snapshot, '')
                                ),
                                'D'
                              )
                            ) @@ search_query.value
                        ),
                        ranked as (
                          select session_id, max(relevance)::integer as relevance
                          from matches
                          group by session_id
                        )
                        select {QUALIFIED_SESSION_COLUMNS}, ranked.relevance
                        from ranked
                        join public.chat_sessions cs on cs.id = ranked.session_id
                        where cs.user_id = :user_id
                          and cs.deleted_at is null
                          {filters}
                          and (
                            cast(:cursor_relevance as integer) is null
                            or ranked.relevance < :cursor_relevance
                            or (
                              ranked.relevance = :cursor_relevance
                              and (
                                cs.updated_at < :cursor_updated_at
                                or (
                                  cs.updated_at = :cursor_updated_at
                                  and cs.id < :cursor_id
                                )
                              )
                            )
                          )
                        order by ranked.relevance desc, cs.updated_at desc, cs.id desc
                        limit :query_limit
                        """
                    ),
                    parameters,
                ).mappings()
            )
            retained = rows[:limit]
            return ChatSessionPage(
                items=tuple(_chat_session(row) for row in retained),
                has_more=len(rows) > limit,
                relevances=tuple(int(row["relevance"]) for row in retained),
            )

        cursor_clause = ""
        if cursor_updated_at is not None and cursor_id is not None:
            cursor_clause = """
              and (
                cs.updated_at < :cursor_updated_at
                or (
                  cs.updated_at = :cursor_updated_at
                  and cs.id < :cursor_id
                )
              )
            """
        rows = list(
            self._session.execute(
                text(
                    f"""
                    select {QUALIFIED_SESSION_COLUMNS}
                    from public.chat_sessions cs
                    where cs.user_id = :user_id
                      and cs.deleted_at is null
                      {filters}
                      {cursor_clause}
                    order by cs.updated_at desc, cs.id desc
                    limit :query_limit
                    """
                ),
                parameters,
            ).mappings()
        )
        retained = rows[:limit]
        return ChatSessionPage(
            items=tuple(_chat_session(row) for row in retained),
            has_more=len(rows) > limit,
            relevances=tuple(0 for _ in retained),
        )

    def record_message_activity(
        self,
        *,
        session_id: UUID,
        user_id: UUID,
        message_created_at: datetime,
    ) -> ChatSession:
        row = self._session.execute(
            text(
                f"""
                update public.chat_sessions
                set
                  updated_at = greatest(updated_at, :message_created_at),
                  last_message_at = greatest(
                    coalesce(last_message_at, :message_created_at),
                    :message_created_at
                  )
                where id = :session_id
                  and user_id = :user_id
                  and deleted_at is null
                returning {SESSION_COLUMNS}
                """
            ),
            {
                "session_id": session_id,
                "user_id": user_id,
                "message_created_at": message_created_at,
            },
        ).mappings().one()
        return _chat_session(row)

    def patch_owned(
        self,
        *,
        session_id: UUID,
        user_id: UUID,
        title: str | None,
        is_pinned: bool | None,
        now: datetime,
    ) -> ChatSession | None:
        row = self._session.execute(
            text(
                f"""
                update public.chat_sessions
                set
                  title = case when :change_title then :title else title end,
                  is_pinned = case
                    when :change_pin then :is_pinned
                    else is_pinned
                  end,
                  updated_at = case
                    when (
                      :change_title
                      and title is distinct from :title
                    ) or (
                      :change_pin
                      and is_pinned is distinct from :is_pinned
                    ) then :now
                    else updated_at
                  end
                where id = :session_id
                  and user_id = :user_id
                  and deleted_at is null
                returning {SESSION_COLUMNS}
                """
            ),
            {
                "session_id": session_id,
                "user_id": user_id,
                "change_title": title is not None,
                "title": title,
                "change_pin": is_pinned is not None,
                "is_pinned": is_pinned,
                "now": now,
            },
        ).mappings().one_or_none()
        return _chat_session(row) if row is not None else None

    def archive_owned(
        self,
        *,
        session_id: UUID,
        user_id: UUID,
        now: datetime,
    ) -> ChatSession | None:
        row = self._session.execute(
            text(
                f"""
                update public.chat_sessions
                set
                  archived_at = coalesce(archived_at, :now),
                  is_pinned = false,
                  updated_at = case
                    when archived_at is null or is_pinned then :now
                    else updated_at
                  end
                where id = :session_id
                  and user_id = :user_id
                  and deleted_at is null
                returning {SESSION_COLUMNS}
                """
            ),
            {"session_id": session_id, "user_id": user_id, "now": now},
        ).mappings().one_or_none()
        return _chat_session(row) if row is not None else None

    def restore_owned(
        self,
        *,
        session_id: UUID,
        user_id: UUID,
        now: datetime,
    ) -> ChatSession | None:
        row = self._session.execute(
            text(
                f"""
                update public.chat_sessions
                set
                  archived_at = null,
                  updated_at = case
                    when archived_at is not null then :now
                    else updated_at
                  end
                where id = :session_id
                  and user_id = :user_id
                  and deleted_at is null
                returning {SESSION_COLUMNS}
                """
            ),
            {"session_id": session_id, "user_id": user_id, "now": now},
        ).mappings().one_or_none()
        return _chat_session(row) if row is not None else None

    def soft_delete_owned(
        self,
        *,
        session_id: UUID,
        user_id: UUID,
        now: datetime,
    ) -> bool | None:
        row = self._session.execute(
            text(
                """
                select deleted_at
                from public.chat_sessions
                where id = :session_id
                  and user_id = :user_id
                for update
                """
            ),
            {"session_id": session_id, "user_id": user_id},
        ).mappings().one_or_none()
        if row is None:
            return None
        if row["deleted_at"] is not None:
            return True
        self._session.execute(
            text(
                """
                update public.chat_sessions
                set
                  deleted_at = :now,
                  is_pinned = false,
                  updated_at = :now
                where id = :session_id
                  and user_id = :user_id
                """
            ),
            {"session_id": session_id, "user_id": user_id, "now": now},
        )
        return True

    def duplicate_context_owned(
        self,
        *,
        source_session_id: UUID,
        duplicate_session_id: UUID,
        user_id: UUID,
    ) -> ChatSession | None:
        source = self.get_owned_for_update(
            session_id=source_session_id,
            user_id=user_id,
        )
        if source is None:
            return None
        base_title = source.title or "New research"
        duplicate_title = f"{base_title[:193]} (Copy)"
        return self.create(
            session_id=duplicate_session_id,
            user_id=user_id,
            event_id=source.event_id,
            title=duplicate_title,
            primary_entity=source.primary_entity,
            primary_topic=source.primary_topic,
            scope_snapshot=source.scope_snapshot,
            knowledge_mode_summary={},
            freshness_state=None,
        )


class ChatMessagesRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

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
        row = self._session.execute(
            text(
                f"""
                insert into public.chat_messages (
                  public_id,
                  session_id,
                  user_id,
                  event_id,
                  role,
                  content,
                  status,
                  response_version,
                  reply_to_message_id,
                  parent_message_id
                )
                values (
                  :public_id,
                  :session_id,
                  :user_id,
                  :event_id,
                  :role,
                  :content,
                  :status,
                  :response_version,
                  :reply_to_message_id,
                  :parent_message_id
                )
                returning {MESSAGE_COLUMNS}
                """
            ),
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
            },
        ).mappings().one()
        return _chat_message(row)

    def get_owned_by_public_id(
        self,
        *,
        public_id: UUID,
        user_id: UUID,
    ) -> ChatMessage | None:
        row = self._session.execute(
            text(
                f"""
                select {MESSAGE_COLUMNS}
                from public.chat_messages
                where public_id = :public_id
                  and user_id = :user_id
                  and session_id is not null
                """
            ),
            {"public_id": public_id, "user_id": user_id},
        ).mappings().one_or_none()
        return _chat_message(row) if row is not None else None


class ChatTurnsRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def list_owned(
        self,
        *,
        session_id: UUID,
        user_id: UUID,
        limit: int,
        cursor_created_at: datetime | None = None,
        cursor_id: int | None = None,
    ) -> ChatTurnPage:
        cursor_clause = ""
        if cursor_created_at is not None and cursor_id is not None:
            cursor_clause = """
              and (
                m.created_at > :cursor_created_at
                or (m.created_at = :cursor_created_at and m.id > :cursor_id)
              )
            """
        anchor_rows = list(
            self._session.execute(
                text(
                    f"""
                    select
                      {QUALIFIED_MESSAGE_COLUMNS},
                      owned_run.id as run_id
                    from public.chat_messages m
                    left join lateral (
                      select candidate.id
                      from public.ask_runs candidate
                      where candidate.user_message_id = m.id
                        and candidate.session_id = m.session_id
                        and candidate.user_id = m.user_id
                      order by candidate.response_version desc
                      limit 1
                    ) owned_run on true
                    left join public.ask_runs assistant_run
                      on assistant_run.assistant_message_id = m.id
                     and assistant_run.session_id = m.session_id
                     and assistant_run.user_id = m.user_id
                    where m.session_id = :session_id
                      and m.user_id = :user_id
                      and assistant_run.id is null
                      {cursor_clause}
                    order by m.created_at, m.id
                    limit :query_limit
                    """
                ),
                {
                    "session_id": session_id,
                    "user_id": user_id,
                    "cursor_created_at": cursor_created_at,
                    "cursor_id": cursor_id,
                    "query_limit": limit + 1,
                },
            ).mappings()
        )
        selected_rows = anchor_rows[:limit]
        run_ids = [row["run_id"] for row in selected_rows if row["run_id"] is not None]
        runs = self._load_runs(
            run_ids=run_ids,
            session_id=session_id,
            user_id=user_id,
        )
        assistant_messages = self._load_assistant_messages(
            run_ids=run_ids,
            session_id=session_id,
            user_id=user_id,
        )

        turns: list[ChatTurn] = []
        for row in selected_rows:
            anchor_message = _chat_message(row)
            run_id = row["run_id"]
            if run_id is not None:
                run, assistant_message = runs[run_id], assistant_messages[run_id]
                turns.append(
                    ChatTurn(
                        anchor_id=anchor_message.id,
                        anchor_created_at=anchor_message.created_at,
                        user_message=anchor_message,
                        assistant_message=assistant_message,
                        run=run,
                    )
                )
            else:
                turns.append(
                    ChatTurn(
                        anchor_id=anchor_message.id,
                        anchor_created_at=anchor_message.created_at,
                        user_message=(
                            anchor_message if anchor_message.role == "user" else None
                        ),
                        assistant_message=(
                            anchor_message
                            if anchor_message.role == "assistant"
                            else None
                        ),
                        run=None,
                    )
                )
        return ChatTurnPage(
            items=tuple(turns),
            has_more=len(anchor_rows) > limit,
        )

    def _load_assistant_messages(
        self,
        *,
        run_ids: list[UUID],
        session_id: UUID,
        user_id: UUID,
    ) -> dict[UUID, ChatMessage]:
        if not run_ids:
            return {}
        rows = self._session.execute(
            text(
                f"""
                select
                  {QUALIFIED_MESSAGE_COLUMNS},
                  r.id as run_id
                from public.ask_runs r
                join public.chat_messages m
                  on m.id = r.assistant_message_id
                 and m.session_id = r.session_id
                 and m.user_id = r.user_id
                where r.id = any(cast(:run_ids as uuid[]))
                  and r.session_id = :session_id
                  and r.user_id = :user_id
                """
            ),
            {
                "run_ids": run_ids,
                "session_id": session_id,
                "user_id": user_id,
            },
        ).mappings()
        return {row["run_id"]: _chat_message(row) for row in rows}

    def _load_runs(
        self,
        *,
        run_ids: list[UUID],
        session_id: UUID,
        user_id: UUID,
    ) -> dict[UUID, AskRun]:
        if not run_ids:
            return {}
        parameters = {
            "run_ids": run_ids,
            "session_id": session_id,
            "user_id": user_id,
        }
        run_rows = list(
            self._session.execute(
                text(
                    """
                    select
                      id,
                      response_version,
                      status,
                      decision_record,
                      knowledge_mode_summary,
                      model,
                      policy_version,
                      prompt_version,
                      general_ai_disclosure,
                      safe_error_code,
                      safe_error_message,
                      started_at,
                      completed_at,
                      created_at,
                      updated_at
                    from public.ask_runs
                    where id = any(cast(:run_ids as uuid[]))
                      and session_id = :session_id
                      and user_id = :user_id
                    """
                ),
                parameters,
            ).mappings()
        )
        sections = self._load_grouped(
            """
            select
              run_id,
              id,
              response_version,
              ordinal,
              section_type,
              status,
              knowledge_mode,
              provenance_label,
              title,
              plain_text,
              content,
              card_schema_version,
              model,
              policy_version,
              prompt_version,
              required_disclosure,
              created_at,
              updated_at
            from public.ask_sections
            where run_id = any(cast(:run_ids as uuid[]))
              and session_id = :session_id
              and user_id = :user_id
            order by run_id, response_version, ordinal
            """,
            parameters,
            _ask_section,
        )
        sources = self._load_grouped(
            """
            select
              run_id,
              id,
              ordinal,
              source_key,
              source_class,
              source_type,
              document_id,
              document_version_id,
              chunk_id,
              graph_reference,
              title_snapshot,
              url_snapshot,
              issuer_snapshot,
              publisher_snapshot,
              jurisdiction_snapshot,
              published_at,
              retrieved_at,
              evidence_snapshot,
              locator_snapshot,
              content_hash,
              metadata,
              created_at
            from public.ask_sources
            where run_id = any(cast(:run_ids as uuid[]))
              and session_id = :session_id
              and user_id = :user_id
            order by run_id, ordinal
            """,
            parameters,
            _ask_source,
        )
        claims = self._load_grouped(
            """
            select
              run_id,
              id,
              section_id,
              ordinal,
              knowledge_mode,
              claim_text,
              is_material,
              support_status,
              support_score,
              model,
              policy_version,
              prompt_version,
              required_disclosure,
              verifier_model,
              verifier_policy_version,
              created_at
            from public.ask_claims
            where run_id = any(cast(:run_ids as uuid[]))
              and session_id = :session_id
              and user_id = :user_id
            order by run_id, section_id, ordinal
            """,
            parameters,
            _ask_claim,
        )
        citations = self._load_grouped(
            """
            select
              run_id,
              id,
              claim_id,
              source_id,
              ordinal,
              claim_knowledge_mode,
              source_class,
              citation_kind,
              marker,
              evidence_snapshot,
              locator_snapshot,
              support_score,
              verification_status,
              verifier_model,
              verifier_policy_version,
              created_at
            from public.ask_citations
            where run_id = any(cast(:run_ids as uuid[]))
              and session_id = :session_id
              and user_id = :user_id
            order by run_id, claim_id, ordinal
            """,
            parameters,
            _ask_citation,
        )
        followups = self._load_grouped(
            """
            select
              run_id,
              id,
              ordinal,
              label,
              question,
              action_type,
              payload,
              created_at
            from public.ask_followups
            where run_id = any(cast(:run_ids as uuid[]))
              and session_id = :session_id
              and user_id = :user_id
            order by run_id, ordinal
            """,
            parameters,
            _ask_followup,
        )
        return {
            row["id"]: AskRun(
                id=row["id"],
                response_version=row["response_version"],
                status=row["status"],
                decision_record=dict(row["decision_record"]),
                knowledge_mode_summary=dict(row["knowledge_mode_summary"]),
                model=row["model"],
                policy_version=row["policy_version"],
                prompt_version=row["prompt_version"],
                general_ai_disclosure=row["general_ai_disclosure"],
                safe_error_code=row["safe_error_code"],
                safe_error_message=row["safe_error_message"],
                started_at=row["started_at"],
                completed_at=row["completed_at"],
                created_at=row["created_at"],
                updated_at=row["updated_at"],
                sections=tuple(sections.get(row["id"], [])),
                sources=tuple(sources.get(row["id"], [])),
                claims=tuple(claims.get(row["id"], [])),
                citations=tuple(citations.get(row["id"], [])),
                followups=tuple(followups.get(row["id"], [])),
            )
            for row in run_rows
        }

    def _load_grouped(
        self,
        sql: str,
        parameters: dict[str, Any],
        converter: Callable[[RowMapping], ArtifactT],
    ) -> dict[UUID, list[ArtifactT]]:
        grouped: dict[UUID, list[ArtifactT]] = {}
        rows = self._session.execute(text(sql), parameters).mappings()
        for row in rows:
            grouped.setdefault(row["run_id"], []).append(converter(row))
        return grouped


class ResponseVersionsRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get_owned(
        self,
        *,
        session_id: UUID,
        user_id: UUID,
        user_message_public_id: UUID,
    ) -> AskResponseLineage | None:
        user_row = self._session.execute(
            text(
                f"""
                select {MESSAGE_COLUMNS}
                from public.chat_messages
                where public_id = :user_message_public_id
                  and session_id = :session_id
                  and user_id = :user_id
                  and role = 'user'
                """
            ),
            {
                "user_message_public_id": user_message_public_id,
                "session_id": session_id,
                "user_id": user_id,
            },
        ).mappings().one_or_none()
        if user_row is None:
            return None

        user_message = _chat_message(user_row)
        version_rows = list(
            self._session.execute(
                text(
                    f"""
                    select
                      {QUALIFIED_MESSAGE_COLUMNS},
                      run.id as run_id
                    from public.ask_runs run
                    join public.chat_messages m
                      on m.id = run.assistant_message_id
                     and m.reply_to_message_id = run.user_message_id
                     and m.session_id = run.session_id
                     and m.user_id = run.user_id
                     and m.response_version = run.response_version
                    where run.user_message_id = :user_message_id
                      and run.session_id = :session_id
                      and run.user_id = :user_id
                    order by run.response_version
                    """
                ),
                {
                    "user_message_id": user_message.id,
                    "session_id": session_id,
                    "user_id": user_id,
                },
            ).mappings()
        )
        run_ids = [row["run_id"] for row in version_rows]
        runs = ChatTurnsRepository(self._session)._load_runs(
            run_ids=run_ids,
            session_id=session_id,
            user_id=user_id,
        )
        feedback = self._load_feedback(
            run_ids=run_ids,
            session_id=session_id,
            user_id=user_id,
        )
        return AskResponseLineage(
            user_message=user_message,
            versions=tuple(
                AskResponseVersion(
                    response_version=runs[row["run_id"]].response_version,
                    assistant_message=_chat_message(row),
                    run=runs[row["run_id"]],
                    feedback=feedback.get(row["run_id"]),
                )
                for row in version_rows
            ),
        )

    def _load_feedback(
        self,
        *,
        run_ids: list[UUID],
        session_id: UUID,
        user_id: UUID,
    ) -> dict[UUID, AskFeedback]:
        if not run_ids:
            return {}
        rows = self._session.execute(
            text(
                """
                select
                  id,
                  run_id,
                  session_id,
                  user_id,
                  response_version,
                  value,
                  reason_code,
                  comment,
                  created_at,
                  updated_at
                from public.ask_feedback
                where run_id = any(cast(:run_ids as uuid[]))
                  and session_id = :session_id
                  and user_id = :user_id
                """
            ),
            {
                "run_ids": run_ids,
                "session_id": session_id,
                "user_id": user_id,
            },
        ).mappings()
        return {row["run_id"]: _ask_feedback(row) for row in rows}

    def get_owned_by_assistant_public_id(
        self,
        *,
        assistant_message_public_id: UUID,
        user_id: UUID,
    ) -> AskResponseVersion | None:
        row = self._session.execute(
            text(
                f"""
                select
                  {QUALIFIED_MESSAGE_COLUMNS},
                  run.id as run_id
                from public.chat_messages m
                join public.ask_runs run
                  on run.assistant_message_id = m.id
                 and run.session_id = m.session_id
                 and run.user_id = m.user_id
                 and run.response_version = m.response_version
                where m.public_id = :assistant_message_public_id
                  and m.user_id = :user_id
                  and m.role = 'assistant'
                """
            ),
            {
                "assistant_message_public_id": assistant_message_public_id,
                "user_id": user_id,
            },
        ).mappings().one_or_none()
        if row is None:
            return None
        run_id = row["run_id"]
        run = ChatTurnsRepository(self._session)._load_runs(
            run_ids=[run_id],
            session_id=row["session_id"],
            user_id=user_id,
        )[run_id]
        feedback = self._load_feedback(
            run_ids=[run_id],
            session_id=row["session_id"],
            user_id=user_id,
        ).get(run_id)
        return AskResponseVersion(
            response_version=run.response_version,
            assistant_message=_chat_message(row),
            run=run,
            feedback=feedback,
        )


class FeedbackRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def upsert_owned(
        self,
        *,
        feedback_id: UUID,
        run_id: UUID,
        session_id: UUID,
        user_id: UUID,
        response_version: int,
        value: AskFeedbackValue,
        reason_code: str | None = None,
        comment: str | None = None,
    ) -> AskFeedback | None:
        row = self._session.execute(
            text(
                """
                insert into public.ask_feedback (
                  id,
                  run_id,
                  session_id,
                  user_id,
                  response_version,
                  value,
                  reason_code,
                  comment
                )
                select
                  :feedback_id,
                  run.id,
                  run.session_id,
                  run.user_id,
                  run.response_version,
                  :value,
                  :reason_code,
                  :comment
                from public.ask_runs run
                where run.id = :run_id
                  and run.session_id = :session_id
                  and run.user_id = :user_id
                  and run.response_version = :response_version
                on conflict (run_id, response_version)
                do update set
                  value = excluded.value,
                  reason_code = excluded.reason_code,
                  comment = excluded.comment,
                  updated_at = now()
                returning
                  id,
                  run_id,
                  session_id,
                  user_id,
                  response_version,
                  value,
                  reason_code,
                  comment,
                  created_at,
                  updated_at
                """
            ),
            {
                "feedback_id": feedback_id,
                "run_id": run_id,
                "session_id": session_id,
                "user_id": user_id,
                "response_version": response_version,
                "value": value,
                "reason_code": reason_code,
                "comment": comment,
            },
        ).mappings().one_or_none()
        return _ask_feedback(row) if row is not None else None


SAVED_ITEM_COLUMNS = """
id,
session_id,
user_id,
item_type,
target_key,
run_id,
response_version,
source_id,
citation_id,
section_id,
entity_id,
document_id,
label_snapshot,
metadata,
created_at,
updated_at
"""


class SavedItemsRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def list_owned(
        self,
        *,
        session_id: UUID,
        user_id: UUID,
    ) -> tuple[AskSavedItem, ...] | None:
        session_exists = self._session.execute(
            text(
                """
                select 1
                from public.chat_sessions
                where id = :session_id
                  and user_id = :user_id
                  and deleted_at is null
                """
            ),
            {"session_id": session_id, "user_id": user_id},
        ).scalar_one_or_none()
        if session_exists is None:
            return None
        rows = self._session.execute(
            text(
                f"""
                select {SAVED_ITEM_COLUMNS}
                from public.ask_saved_items
                where session_id = :session_id
                  and user_id = :user_id
                order by created_at, id
                """
            ),
            {"session_id": session_id, "user_id": user_id},
        ).mappings()
        return tuple(_ask_saved_item(row) for row in rows)

    def create_owned(
        self,
        *,
        saved_item_id: UUID,
        session_id: UUID,
        user_id: UUID,
        item_type: AskSavedItemType,
        target_key: str,
    ) -> AskSavedItem | None:
        statement = self._insert_statement(item_type)
        row = self._session.execute(
            text(statement),
            {
                "saved_item_id": saved_item_id,
                "session_id": session_id,
                "user_id": user_id,
                "target_key": target_key,
            },
        ).mappings().one_or_none()
        if row is not None:
            return _ask_saved_item(row)
        existing = self._session.execute(
            text(
                f"""
                select {SAVED_ITEM_COLUMNS}
                from public.ask_saved_items
                where session_id = :session_id
                  and user_id = :user_id
                  and item_type = :item_type
                  and target_key = :target_key
                """
            ),
            {
                "session_id": session_id,
                "user_id": user_id,
                "item_type": item_type,
                "target_key": target_key,
            },
        ).mappings().one_or_none()
        return _ask_saved_item(existing) if existing is not None else None

    def delete_owned(
        self,
        *,
        saved_item_id: UUID,
        session_id: UUID,
        user_id: UUID,
    ) -> bool:
        deleted_id = self._session.execute(
            text(
                """
                delete from public.ask_saved_items
                where id = :saved_item_id
                  and session_id = :session_id
                  and user_id = :user_id
                returning id
                """
            ),
            {
                "saved_item_id": saved_item_id,
                "session_id": session_id,
                "user_id": user_id,
            },
        ).scalar_one_or_none()
        return deleted_id is not None

    @staticmethod
    def _insert_statement(item_type: AskSavedItemType) -> str:
        statements = {
            "source": """
                insert into public.ask_saved_items (
                  id, session_id, user_id, item_type, target_key,
                  run_id, response_version, source_id, label_snapshot, metadata
                )
                select
                  :saved_item_id, source.session_id, source.user_id, 'source',
                  source.id::text, source.run_id, run.response_version, source.id,
                  source.title_snapshot,
                  jsonb_build_object(
                    'source_class', source.source_class,
                    'source_type', source.source_type,
                    'url', source.url_snapshot
                  )
                from public.ask_sources source
                join public.ask_runs run
                  on run.id = source.run_id
                 and run.session_id = source.session_id
                 and run.user_id = source.user_id
                where source.id::text = :target_key
                  and source.session_id = :session_id
                  and source.user_id = :user_id
                on conflict do nothing
                returning
            """,
            "citation": """
                insert into public.ask_saved_items (
                  id, session_id, user_id, item_type, target_key,
                  run_id, response_version, citation_id, label_snapshot, metadata
                )
                select
                  :saved_item_id, citation.session_id, citation.user_id, 'citation',
                  citation.id::text, citation.run_id, run.response_version, citation.id,
                  coalesce(citation.marker, 'Citation ' || (citation.ordinal + 1)::text),
                  jsonb_build_object(
                    'citation_kind', citation.citation_kind,
                    'evidence_snapshot', citation.evidence_snapshot,
                    'source_id', citation.source_id
                  )
                from public.ask_citations citation
                join public.ask_runs run
                  on run.id = citation.run_id
                 and run.session_id = citation.session_id
                 and run.user_id = citation.user_id
                where citation.id::text = :target_key
                  and citation.session_id = :session_id
                  and citation.user_id = :user_id
                on conflict do nothing
                returning
            """,
            "card": """
                insert into public.ask_saved_items (
                  id, session_id, user_id, item_type, target_key,
                  run_id, response_version, section_id, label_snapshot, metadata
                )
                select
                  :saved_item_id, section.session_id, section.user_id, 'card',
                  section.id::text, section.run_id, section.response_version, section.id,
                  coalesce(nullif(btrim(section.title), ''), section.section_type),
                  jsonb_build_object(
                    'section_type', section.section_type,
                    'knowledge_mode', section.knowledge_mode,
                    'card_schema_version', section.card_schema_version
                  )
                from public.ask_sections section
                where section.id::text = :target_key
                  and section.session_id = :session_id
                  and section.user_id = :user_id
                on conflict do nothing
                returning
            """,
            "entity": """
                insert into public.ask_saved_items (
                  id, session_id, user_id, item_type, target_key,
                  entity_id, label_snapshot, metadata
                )
                select
                  :saved_item_id, session.id, session.user_id, 'entity',
                  entity.canonical_id, entity.canonical_id, entity.canonical_name,
                  jsonb_build_object(
                    'entity_class', entity.entity_class,
                    'jurisdiction', entity.jurisdiction
                  )
                from public.chat_sessions session
                join public.regulatory_entity_catalog entity
                  on entity.canonical_id = :target_key
                where session.id = :session_id
                  and session.user_id = :user_id
                  and session.deleted_at is null
                on conflict do nothing
                returning
            """,
            "document": """
                insert into public.ask_saved_items (
                  id, session_id, user_id, item_type, target_key,
                  document_id, label_snapshot, metadata
                )
                select
                  :saved_item_id, session.id, session.user_id, 'document',
                  document.id::text, document.id, document.title,
                  jsonb_build_object(
                    'source_url', document.source_url,
                    'issuing_body', document.issuing_body,
                    'jurisdiction', document.jurisdiction
                  )
                from public.chat_sessions session
                join public.documents document
                  on document.id::text = :target_key
                where session.id = :session_id
                  and session.user_id = :user_id
                  and session.deleted_at is null
                on conflict do nothing
                returning
            """,
        }
        return statements[item_type] + f" {SAVED_ITEM_COLUMNS}"
