from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.exc import SQLAlchemyError

from backend.ask.backfill import (
    LEGACY_BACKFILL_ADVISORY_LOCK_KEY,
    LEGACY_BACKFILL_VERSION,
    LegacyBackfillConcurrentRunError,
    legacy_message_public_id,
    legacy_session_id,
    legacy_session_title,
    preview_backfill,
    run_backfill,
    verify_backfill,
)
from backend.core.migrations import apply_pending_migrations
from backend.tests.ask_ai_postgres import (
    POSTGRES_MARK,
    insert_auth_user,
)

MIGRATIONS_DIR = Path(__file__).parents[1] / "migrations"


def test_legacy_identity_is_deterministic_and_scope_specific() -> None:
    user_id = UUID("11111111-1111-1111-1111-111111111111")

    assert legacy_session_id(user_id, None) == legacy_session_id(user_id, None)
    assert legacy_session_id(user_id, None) != legacy_session_id(user_id, 41)
    assert legacy_session_id(user_id, 41) != legacy_session_id(uuid4(), 41)
    assert legacy_message_public_id(1) == legacy_message_public_id(1)
    assert legacy_message_public_id(1) != legacy_message_public_id(2)
    assert legacy_session_title(None) == "Legacy Ask history"
    assert legacy_session_title(41).endswith("Event 41")


@POSTGRES_MARK
def test_backfill_refuses_concurrent_runner(migrated_engine: Engine) -> None:
    with migrated_engine.connect() as lock_connection:
        assert lock_connection.execute(
            text("select pg_try_advisory_lock(:lock_key)"),
            {"lock_key": LEGACY_BACKFILL_ADVISORY_LOCK_KEY},
        ).scalar_one()
        try:
            with pytest.raises(
                LegacyBackfillConcurrentRunError,
                match="another Ask AI legacy backfill runner",
            ):
                run_backfill(migrated_engine)
        finally:
            lock_connection.execute(
                text("select pg_advisory_unlock(:lock_key)"),
                {"lock_key": LEGACY_BACKFILL_ADVISORY_LOCK_KEY},
            )


@pytest.fixture
def migrated_engine(postgres_engine: Engine) -> Engine:
    apply_pending_migrations(postgres_engine, MIGRATIONS_DIR, through="0024")
    return postgres_engine


def _insert_event(connection: Connection) -> int:
    identity = uuid4()
    source_id = connection.execute(
        text(
            """
            insert into public.sources (code, name, jurisdiction, url)
            values (:code, 'Backfill source', 'central', :url)
            returning id
            """
        ),
        {"code": f"backfill-{identity}", "url": f"https://example.invalid/{identity}"},
    ).scalar_one()
    document_id = connection.execute(
        text(
            """
            insert into public.documents (
              source_id,
              url_hash,
              source_url,
              title
            )
            values (:source_id, :url_hash, :url, 'Backfill event')
            returning id
            """
        ),
        {
            "source_id": source_id,
            "url_hash": str(uuid4()),
            "url": f"https://example.invalid/document/{uuid4()}",
        },
    ).scalar_one()
    return connection.execute(
        text(
            """
            insert into public.events (document_id, event_type)
            values (:document_id, 'NEW')
            returning id
            """
        ),
        {"document_id": document_id},
    ).scalar_one()


def _insert_legacy_message(
    connection: Connection,
    *,
    user_id: UUID,
    event_id: int | None,
    role: str,
    content: str,
    created_at: datetime,
) -> int:
    return connection.execute(
        text(
            """
            insert into public.chat_messages (
              user_id,
              event_id,
              role,
              content,
              created_at
            )
            values (:user_id, :event_id, :role, :content, :created_at)
            returning id
            """
        ),
        {
            "user_id": user_id,
            "event_id": event_id,
            "role": role,
            "content": content,
            "created_at": created_at,
        },
    ).scalar_one()


def _message_snapshot(connection: Connection) -> list[tuple[object, ...]]:
    return [
        tuple(row)
        for row in connection.execute(
            text(
                """
                select id, user_id, event_id, role, content, created_at
                from public.chat_messages
                order by id
                """
            )
        ).all()
    ]


@POSTGRES_MARK
def test_backfill_dry_run_groups_global_event_odd_and_multi_owner_history(
    migrated_engine: Engine,
) -> None:
    first_user = uuid4()
    second_user = uuid4()
    started_at = datetime(2026, 7, 1, tzinfo=UTC)
    with migrated_engine.begin() as connection:
        insert_auth_user(connection, first_user)
        insert_auth_user(connection, second_user)
        event_id = _insert_event(connection)
        message_ids = [
            _insert_legacy_message(
                connection,
                user_id=first_user,
                event_id=None,
                role="assistant",
                content="orphan assistant",
                created_at=started_at,
            ),
            _insert_legacy_message(
                connection,
                user_id=first_user,
                event_id=None,
                role="user",
                content="first question",
                created_at=started_at + timedelta(minutes=1),
            ),
            _insert_legacy_message(
                connection,
                user_id=first_user,
                event_id=None,
                role="user",
                content="odd trailing question",
                created_at=started_at + timedelta(minutes=2),
            ),
            _insert_legacy_message(
                connection,
                user_id=first_user,
                event_id=event_id,
                role="assistant",
                content="event orphan",
                created_at=started_at + timedelta(minutes=3),
            ),
            _insert_legacy_message(
                connection,
                user_id=second_user,
                event_id=None,
                role="user",
                content="second owner",
                created_at=started_at + timedelta(minutes=4),
            ),
        ]
        before = _message_snapshot(connection)

    preview = preview_backfill(migrated_engine)
    assert preview.legacy_message_count == 5
    assert preview.pending_message_count == 5
    assert preview.expected_session_count == 3
    assert preview.sessions_to_create == 3
    with migrated_engine.connect() as connection:
        assert connection.execute(
            text("select count(*) from public.chat_sessions")
        ).scalar_one() == 0

    result = run_backfill(migrated_engine, batch_size=2)
    assert result.status == "complete"
    assert result.batches_completed == 3
    assert result.messages_updated == 5
    assert result.sessions_created == 3
    assert result.verification.is_valid is True
    assert result.verification.backfilled_message_count == 5

    with migrated_engine.connect() as connection:
        after = _message_snapshot(connection)
        identities = connection.execute(
            text(
                """
                select id, user_id, event_id, public_id, session_id
                from public.chat_messages
                order by id
                """
            )
        ).all()
        sessions = connection.execute(
            text(
                """
                select user_id, event_id, scope_snapshot
                from public.chat_sessions
                order by user_id, event_id nulls first
                """
            )
        ).all()

    assert after == before
    assert [row.id for row in identities] == message_ids
    for row in identities:
        assert row.public_id == legacy_message_public_id(row.id)
        assert row.session_id == legacy_session_id(row.user_id, row.event_id)
    assert len(sessions) == 3
    assert all(
        row.scope_snapshot["legacy_backfill"] is True
        and row.scope_snapshot["legacy_backfill_version"] == LEGACY_BACKFILL_VERSION
        for row in sessions
    )

    rerun = run_backfill(migrated_engine, batch_size=2)
    assert rerun.status == "complete"
    assert rerun.batches_completed == 0
    assert rerun.messages_updated == 0
    assert rerun.sessions_created == 0
    assert rerun.verification.is_valid is True


@POSTGRES_MARK
def test_bounded_backfill_resumes_remaining_rows(
    migrated_engine: Engine,
) -> None:
    user_id = uuid4()
    started_at = datetime(2026, 7, 2, tzinfo=UTC)
    with migrated_engine.begin() as connection:
        insert_auth_user(connection, user_id)
        for index in range(5):
            _insert_legacy_message(
                connection,
                user_id=user_id,
                event_id=None,
                role="user" if index % 2 == 0 else "assistant",
                content=f"message {index}",
                created_at=started_at + timedelta(minutes=index),
            )

    partial = run_backfill(migrated_engine, batch_size=2, max_batches=1)
    assert partial.status == "partial"
    assert partial.batches_completed == 1
    assert partial.messages_updated == 2
    assert partial.verification.pending_message_count == 3

    resumed = run_backfill(migrated_engine, batch_size=2)
    assert resumed.status == "complete"
    assert resumed.messages_updated == 3
    assert resumed.verification.pending_message_count == 0
    assert resumed.verification.is_valid is True


@POSTGRES_MARK
def test_failed_batch_rolls_back_and_clean_rerun_resumes(
    migrated_engine: Engine,
) -> None:
    user_id = uuid4()
    started_at = datetime(2026, 7, 3, tzinfo=UTC)
    with migrated_engine.begin() as connection:
        insert_auth_user(connection, user_id)
        message_ids = [
            _insert_legacy_message(
                connection,
                user_id=user_id,
                event_id=None,
                role="user",
                content=f"message {index}",
                created_at=started_at + timedelta(minutes=index),
            )
            for index in range(3)
        ]
        failure_id = message_ids[1]
        connection.exec_driver_sql(
            f"""
            create function public.fail_ask_backfill_test()
            returns trigger
            language plpgsql
            as $$
            begin
              if old.id = {failure_id}
                 and old.session_id is null
                 and new.session_id is not null then
                raise exception 'injected backfill failure';
              end if;
              return new;
            end
            $$;

            create trigger fail_ask_backfill_test
            before update on public.chat_messages
            for each row execute function public.fail_ask_backfill_test();
            """
        )

    with pytest.raises(SQLAlchemyError):
        run_backfill(migrated_engine, batch_size=3)

    failed_verification = verify_backfill(migrated_engine)
    assert failed_verification.pending_message_count == 3
    with migrated_engine.begin() as connection:
        assert connection.execute(
            text("select count(*) from public.chat_sessions")
        ).scalar_one() == 0
        connection.exec_driver_sql(
            """
            drop trigger fail_ask_backfill_test on public.chat_messages;
            drop function public.fail_ask_backfill_test();
            """
        )

    resumed = run_backfill(migrated_engine, batch_size=3)
    assert resumed.status == "complete"
    assert resumed.messages_updated == 3
    assert resumed.verification.is_valid is True


@POSTGRES_MARK
def test_verification_reports_divergent_non_null_identity(
    migrated_engine: Engine,
) -> None:
    user_id = uuid4()
    with migrated_engine.begin() as connection:
        insert_auth_user(connection, user_id)
        message_id = _insert_legacy_message(
            connection,
            user_id=user_id,
            event_id=None,
            role="user",
            content="drift target",
            created_at=datetime(2026, 7, 4, tzinfo=UTC),
        )

    assert run_backfill(migrated_engine).status == "complete"
    with migrated_engine.begin() as connection:
        connection.execute(
            text(
                """
                update public.chat_messages
                set public_id = :wrong_public_id
                where id = :message_id
                """
            ),
            {"wrong_public_id": uuid4(), "message_id": message_id},
        )

    verification = verify_backfill(migrated_engine)
    assert verification.is_valid is False
    assert verification.public_id_mismatch_count == 1
    assert verification.drift_count == 1
