from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from backend.ask.backfill import (
    preflight_backfill_validation,
    run_backfill,
)
from backend.core.migrations import apply_pending_migrations, discover_migrations
from backend.tests.ask_ai_postgres import (
    POSTGRES_MARK,
    insert_auth_user,
)

MIGRATIONS_DIR = Path(__file__).parents[1] / "migrations"
VALIDATION_MIGRATION = MIGRATIONS_DIR / "0025_ask_ai_backfill_validation.sql"
MIGRATION_README = MIGRATIONS_DIR / "README.md"


def _normalized_sql(path: Path) -> str:
    return " ".join(path.read_text(encoding="utf-8").lower().split())


def _insert_legacy_message(
    connection: Connection,
    *,
    user_id: UUID,
    role: str,
    content: str,
) -> int:
    return connection.execute(
        text(
            """
            insert into public.chat_messages (
              user_id,
              role,
              content,
              created_at
            )
            values (:user_id, :role, :content, :created_at)
            returning id
            """
        ),
        {
            "user_id": user_id,
            "role": role,
            "content": content,
            "created_at": datetime(2026, 7, 5, tzinfo=UTC),
        },
    ).scalar_one()


def test_0025_is_validation_only_and_preserves_null_null_compatibility() -> None:
    migrations = discover_migrations(MIGRATIONS_DIR)
    validation_migration = next(
        migration for migration in migrations if migration.version == "0025"
    )
    sql = _normalized_sql(VALIDATION_MIGRATION)
    readme = " ".join(
        MIGRATION_README.read_text(encoding="utf-8").lower().split()
    )

    assert validation_migration.filename == "0025_ask_ai_backfill_validation.sql"
    assert "ask_ai_backfill_incomplete" in sql
    assert "validate constraint chat_messages_public_session_pair_chk" in sql
    assert "chat_sessions_legacy_owner_event_key" in sql
    assert "chat_messages_owner_session_created_cursor_idx" in sql
    assert "set not null" not in sql
    assert "drop column" not in sql
    assert "delete from public.chat_messages" not in sql
    assert "paired identity check permits null/null" in readme


@POSTGRES_MARK
def test_0025_applies_from_empty_schema_and_records_ledger(
    postgres_engine: Engine,
) -> None:
    applied = apply_pending_migrations(
        postgres_engine,
        MIGRATIONS_DIR,
        through="0025",
    )

    assert len(applied) == 25
    assert applied[-1].version == "0025"
    with postgres_engine.connect() as connection:
        assert connection.execute(
            text(
                """
                select count(*)
                from public.schema_migrations
                where version = '0025'
                  and filename = '0025_ask_ai_backfill_validation.sql'
                """
            )
        ).scalar_one() == 1
        assert connection.execute(
            text(
                """
                select convalidated
                from pg_constraint
                where conrelid = 'public.chat_messages'::regclass
                  and conname = 'chat_messages_public_session_pair_chk'
                """
            )
        ).scalar_one() is True


@POSTGRES_MARK
def test_0025_refuses_pending_backfill_without_ledger_or_schema_change(
    postgres_engine: Engine,
) -> None:
    apply_pending_migrations(postgres_engine, MIGRATIONS_DIR, through="0024")
    owner_id = uuid4()
    with postgres_engine.begin() as connection:
        insert_auth_user(connection, owner_id)
        _insert_legacy_message(
            connection,
            user_id=owner_id,
            role="user",
            content="pending legacy row",
        )

    preflight = preflight_backfill_validation(postgres_engine)
    assert preflight.is_ready is False
    assert preflight.verification.pending_message_count == 1

    with pytest.raises(SQLAlchemyError):
        apply_pending_migrations(
            postgres_engine,
            MIGRATIONS_DIR,
            through="0025",
        )

    with postgres_engine.connect() as connection:
        assert connection.execute(
            text(
                """
                select count(*)
                from public.schema_migrations
                where version = '0025'
                """
            )
        ).scalar_one() == 0
        assert connection.execute(
            text(
                """
                select count(*)
                from pg_constraint
                where conrelid = 'public.chat_messages'::regclass
                  and conname = 'chat_messages_public_session_pair_chk'
                """
            )
        ).scalar_one() == 0
        assert connection.execute(
            text("select to_regclass('public.chat_sessions_legacy_owner_event_key')")
        ).scalar_one() is None


@POSTGRES_MARK
def test_0025_applies_after_preflight_and_keeps_flag_off_writes_safe(
    postgres_engine: Engine,
) -> None:
    apply_pending_migrations(postgres_engine, MIGRATIONS_DIR, through="0024")
    owner_id = uuid4()
    with postgres_engine.begin() as connection:
        insert_auth_user(connection, owner_id)
        message_ids = [
            _insert_legacy_message(
                connection,
                user_id=owner_id,
                role="user",
                content="question",
            ),
            _insert_legacy_message(
                connection,
                user_id=owner_id,
                role="assistant",
                content="answer",
            ),
        ]
        before = connection.execute(
            text(
                """
                select id, user_id, event_id, role, content, created_at
                from public.chat_messages
                order by id
                """
            )
        ).all()

    assert run_backfill(postgres_engine, batch_size=1).status == "complete"
    preflight = preflight_backfill_validation(postgres_engine)
    assert preflight.is_ready is True
    assert preflight.required_migration == "0025_ask_ai_backfill_validation.sql"

    assert [
        migration.version
        for migration in apply_pending_migrations(
            postgres_engine,
            MIGRATIONS_DIR,
            through="0025",
        )
    ] == ["0025"]
    with postgres_engine.begin() as connection:
        after = connection.execute(
            text(
                """
                select id, user_id, event_id, role, content, created_at
                from public.chat_messages
                where id = any(:message_ids)
                order by id
                """
            ),
            {"message_ids": message_ids},
        ).all()
        legacy_id = _insert_legacy_message(
            connection,
            user_id=owner_id,
            role="user",
            content="flag-off compatible write",
        )

    assert after == before
    with postgres_engine.connect() as connection:
        identity = connection.execute(
            text(
                """
                select public_id, session_id
                from public.chat_messages
                where id = :message_id
                """
            ),
            {"message_id": legacy_id},
        ).one()
    assert identity == (None, None)

    with pytest.raises(IntegrityError), postgres_engine.begin() as connection:
        connection.execute(
            text(
                """
                insert into public.chat_messages (
                  public_id,
                  user_id,
                  role,
                  content
                )
                values (:public_id, :user_id, 'user', 'partial identity')
                """
            ),
            {"public_id": uuid4(), "user_id": owner_id},
        )

    with postgres_engine.connect() as connection:
        legacy_session = connection.execute(
            text(
                """
                select user_id, event_id
                from public.chat_sessions
                where scope_snapshot @> '{"legacy_backfill": true}'::jsonb
                """
            )
        ).one()

    with pytest.raises(IntegrityError), postgres_engine.begin() as connection:
        connection.execute(
            text(
                """
                insert into public.chat_sessions (
                  id,
                  user_id,
                  event_id,
                  title,
                  status,
                  scope_snapshot
                )
                values (
                  :session_id,
                  :user_id,
                  :event_id,
                  'Duplicate legacy scope',
                  'complete',
                  '{"legacy_backfill": true, "legacy_backfill_version": 1,
                    "event_id": null}'::jsonb
                )
                """
            ),
            {
                "session_id": uuid4(),
                "user_id": legacy_session.user_id,
                "event_id": legacy_session.event_id,
            },
        )
