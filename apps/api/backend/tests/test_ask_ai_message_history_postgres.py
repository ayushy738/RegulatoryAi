from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.orm import Session

from backend.ask.models import ChatTurn
from backend.ask.persistence import AskPersistenceService
from backend.core.migrations import apply_pending_migrations
from backend.tests.ask_ai_postgres import POSTGRES_MARK, insert_auth_user

MIGRATIONS_DIR = Path(__file__).parents[1] / "migrations"


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


def _create_run_turn(
    engine: Engine,
    *,
    owner_id: UUID,
    session_id: UUID,
    at: datetime,
    label: str,
    with_artifacts: bool = False,
) -> UUID:
    service = _service(engine)
    placeholder = service.create_turn_placeholder(
        session_id=session_id,
        user_id=owner_id,
        user_message_id=uuid4(),
        assistant_message_id=uuid4(),
        content=f"Question {label}",
    )
    run_id = uuid4()
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                update public.chat_messages
                set
                  content = case
                    when id = :assistant_id then :assistant_content
                    else content
                  end,
                  created_at = case
                    when id = :assistant_id then :assistant_at
                    else :user_at
                  end
                where id in (:user_id, :assistant_id)
                """
            ),
            {
                "user_id": placeholder.user_message.id,
                "assistant_id": placeholder.assistant_message.id,
                "assistant_content": f"Answer {label}",
                "user_at": at,
                "assistant_at": at + timedelta(seconds=1),
            },
        )
        connection.execute(
            text(
                """
                insert into public.ask_runs (
                  id,
                  session_id,
                  user_id,
                  user_message_id,
                  assistant_message_id,
                  status,
                  knowledge_mode_summary,
                  model,
                  policy_version,
                  prompt_version,
                  started_at,
                  completed_at,
                  created_at,
                  updated_at
                )
                values (
                  :run_id,
                  :session_id,
                  :owner_id,
                  :user_message_id,
                  :assistant_message_id,
                  'completed',
                  cast(:knowledge_mode_summary as jsonb),
                  'postgres-model',
                  'policy-1',
                  'prompt-1',
                  :started_at,
                  :completed_at,
                  :started_at,
                  :completed_at
                )
                """
            ),
            {
                "run_id": run_id,
                "session_id": session_id,
                "owner_id": owner_id,
                "user_message_id": placeholder.user_message.id,
                "assistant_message_id": placeholder.assistant_message.id,
                "knowledge_mode_summary": json.dumps({"live": True}),
                "started_at": at,
                "completed_at": at + timedelta(seconds=2),
            },
        )
        if with_artifacts:
            _insert_artifacts(
                connection,
                run_id=run_id,
                session_id=session_id,
                owner_id=owner_id,
                at=at,
            )
    return placeholder.user_message.public_id


def _insert_artifacts(
    connection: Connection,
    *,
    run_id: UUID,
    session_id: UUID,
    owner_id: UUID,
    at: datetime,
) -> None:
    section_id = uuid4()
    source_id = uuid4()
    claim_id = uuid4()
    connection.execute(
        text(
            """
            insert into public.ask_sections (
              id, run_id, session_id, user_id, response_version, ordinal,
              section_type, status, knowledge_mode, provenance_label, title,
              plain_text, content, card_schema_version, model, policy_version,
              prompt_version, created_at, updated_at
            )
            values (
              :id, :run_id, :session_id, :owner_id, 1, 0,
              'latest_update', 'completed', 'live', 'Live Web Sources',
              'Latest update', 'Deadline changed.',
              cast(:content as jsonb), '1', 'postgres-model', 'policy-1',
              'prompt-1', :created_at, :updated_at
            )
            """
        ),
        {
            "id": section_id,
            "run_id": run_id,
            "session_id": session_id,
            "owner_id": owner_id,
            "content": json.dumps({"deadline": "2026-08-31"}),
            "created_at": at + timedelta(seconds=1),
            "updated_at": at + timedelta(seconds=2),
        },
    )
    connection.execute(
        text(
            """
            insert into public.ask_sources (
              id, run_id, session_id, user_id, ordinal, source_key,
              source_class, source_type, title_snapshot, url_snapshot,
              publisher_snapshot, jurisdiction_snapshot, published_at,
              retrieved_at, evidence_snapshot, locator_snapshot, content_hash,
              metadata, created_at
            )
            values (
              :id, :run_id, :session_id, :owner_id, 0, 'live:postgres',
              'live', 'news', 'Consultation update',
              'https://example.test/consultation', 'Regulatory Bulletin',
              'central', :published_at, :retrieved_at,
              'Responses are due by 31 August.', 'paragraph 4',
              'sha256:postgres', cast(:metadata as jsonb), :created_at
            )
            """
        ),
        {
            "id": source_id,
            "run_id": run_id,
            "session_id": session_id,
            "owner_id": owner_id,
            "published_at": at - timedelta(minutes=30),
            "retrieved_at": at,
            "metadata": json.dumps({"language": "en"}),
            "created_at": at + timedelta(seconds=1),
        },
    )
    connection.execute(
        text(
            """
            insert into public.ask_claims (
              id, run_id, section_id, session_id, user_id, ordinal,
              knowledge_mode, claim_text, support_status, support_score,
              model, policy_version, prompt_version, verifier_model,
              verifier_policy_version, created_at
            )
            values (
              :id, :run_id, :section_id, :session_id, :owner_id, 0,
              'live', 'The deadline moved.', 'supported', 0.98,
              'postgres-model', 'policy-1', 'prompt-1', 'verifier-model',
              'verify-1', :created_at
            )
            """
        ),
        {
            "id": claim_id,
            "run_id": run_id,
            "section_id": section_id,
            "session_id": session_id,
            "owner_id": owner_id,
            "created_at": at + timedelta(seconds=1),
        },
    )
    connection.execute(
        text(
            """
            insert into public.ask_citations (
              run_id, claim_id, source_id, session_id, user_id, ordinal,
              claim_knowledge_mode, source_class, citation_kind, marker,
              evidence_snapshot, locator_snapshot, support_score,
              verification_status, verifier_model, verifier_policy_version,
              created_at
            )
            values (
              :run_id, :claim_id, :source_id, :session_id, :owner_id, 0,
              'live', 'live', 'live_source_link', '[Live 1]',
              'Responses are due by 31 August.', 'paragraph 4', 0.98,
              'verified', 'verifier-model', 'verify-1', :created_at
            )
            """
        ),
        {
            "run_id": run_id,
            "claim_id": claim_id,
            "source_id": source_id,
            "session_id": session_id,
            "owner_id": owner_id,
            "created_at": at + timedelta(seconds=1),
        },
    )
    connection.execute(
        text(
            """
            insert into public.ask_followups (
              run_id, session_id, user_id, ordinal, label, question,
              action_type, payload, created_at
            )
            values (
              :run_id, :session_id, :owner_id, 0, 'Check applicability',
              'Who must respond?', 'ask', cast(:payload as jsonb), :created_at
            )
            """
        ),
        {
            "run_id": run_id,
            "session_id": session_id,
            "owner_id": owner_id,
            "payload": json.dumps({"entity": "CERC"}),
            "created_at": at + timedelta(seconds=2),
        },
    )


def _cursor(turn: ChatTurn) -> tuple[datetime, int]:
    return turn.anchor_created_at, turn.anchor_id


@POSTGRES_MARK
def test_full_turn_restoration_and_unpaired_message_recovery(
    migrated_engine: Engine,
) -> None:
    owner_id = uuid4()
    other_id = uuid4()
    with migrated_engine.begin() as connection:
        insert_auth_user(connection, owner_id)
        insert_auth_user(connection, other_id)

    service = _service(migrated_engine)
    session = service.create_session(user_id=owner_id, title="Restoration")
    base = datetime(2026, 7, 27, 9, tzinfo=UTC)
    anchor_public_id = _create_run_turn(
        migrated_engine,
        owner_id=owner_id,
        session_id=session.id,
        at=base,
        label="full",
        with_artifacts=True,
    )
    singleton = service.create_turn_placeholder(
        session_id=session.id,
        user_id=owner_id,
        user_message_id=uuid4(),
        assistant_message_id=uuid4(),
        content="Unpaired persistence",
    )
    with migrated_engine.begin() as connection:
        connection.execute(
            text(
                """
                update public.chat_messages
                set created_at = case
                  when id = :user_id then :user_at
                  else :assistant_at
                end
                where id in (:user_id, :assistant_id)
                """
            ),
            {
                "user_id": singleton.user_message.id,
                "assistant_id": singleton.assistant_message.id,
                "user_at": base + timedelta(minutes=1),
                "assistant_at": base + timedelta(minutes=1, seconds=1),
            },
        )

    page = service.list_turns(session_id=session.id, user_id=owner_id, limit=10)

    assert page is not None
    assert page.has_more is False
    assert len(page.items) == 3
    full_turn = page.items[0]
    assert full_turn.user_message is not None
    assert full_turn.user_message.public_id == anchor_public_id
    assert full_turn.assistant_message is not None
    assert full_turn.assistant_message.content == "Answer full"
    assert full_turn.run is not None
    assert [section.plain_text for section in full_turn.run.sections] == [
        "Deadline changed."
    ]
    assert [source.evidence_snapshot for source in full_turn.run.sources] == [
        "Responses are due by 31 August."
    ]
    assert [claim.support_score for claim in full_turn.run.claims] == [0.98]
    assert [citation.marker for citation in full_turn.run.citations] == ["[Live 1]"]
    assert [followup.question for followup in full_turn.run.followups] == [
        "Who must respond?"
    ]
    assert page.items[1].user_message is not None
    assert page.items[1].assistant_message is None
    assert page.items[2].user_message is None
    assert page.items[2].assistant_message is not None
    assert service.list_turns(
        session_id=session.id,
        user_id=other_id,
        limit=10,
    ) is None


@POSTGRES_MARK
def test_complete_turn_cursor_is_chronological_and_stable_under_insert(
    migrated_engine: Engine,
) -> None:
    owner_id = uuid4()
    with migrated_engine.begin() as connection:
        insert_auth_user(connection, owner_id)

    service = _service(migrated_engine)
    session = service.create_session(user_id=owner_id, title="Cursor")
    base = datetime(2026, 7, 27, 10, tzinfo=UTC)
    expected = [
        _create_run_turn(
            migrated_engine,
            owner_id=owner_id,
            session_id=session.id,
            at=base + timedelta(minutes=index),
            label=str(index),
        )
        for index in range(3)
    ]

    first = service.list_turns(session_id=session.id, user_id=owner_id, limit=1)
    assert first is not None
    assert first.has_more is True
    assert first.items[0].user_message is not None
    assert first.items[0].user_message.public_id == expected[0]

    concurrent = _create_run_turn(
        migrated_engine,
        owner_id=owner_id,
        session_id=session.id,
        at=base + timedelta(minutes=3),
        label="concurrent",
    )
    seen = [expected[0]]
    current = first.items[-1]
    while True:
        cursor_created_at, cursor_id = _cursor(current)
        page = service.list_turns(
            session_id=session.id,
            user_id=owner_id,
            limit=1,
            cursor_created_at=cursor_created_at,
            cursor_id=cursor_id,
        )
        assert page is not None
        assert len(page.items) == 1
        current = page.items[0]
        assert current.user_message is not None
        assert current.assistant_message is not None
        assert current.run is not None
        seen.append(current.user_message.public_id)
        if not page.has_more:
            break

    assert seen == [*expected, concurrent]
    assert len(seen) == len(set(seen))
