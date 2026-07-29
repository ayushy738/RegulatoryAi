from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from backend.core.migrations import apply_pending_migrations, discover_migrations
from backend.tests.ask_ai_postgres import POSTGRES_MARK, insert_auth_user
from backend.tests.test_ask_ai_artifact_migration import _seed_artifact_graph

pytestmark = POSTGRES_MARK

MIGRATIONS_DIR = Path(__file__).parents[1] / "migrations"
DURABILITY_MIGRATION = MIGRATIONS_DIR / "0029_ask_ai_run_durability.sql"
MIGRATION_README = MIGRATIONS_DIR / "README.md"


def test_0029_is_ordered_additive_and_documents_non_destructive_rollback() -> None:
    migrations = discover_migrations(MIGRATIONS_DIR)
    migration = next(item for item in migrations if item.version == "0029")
    sql = " ".join(
        DURABILITY_MIGRATION.read_text(encoding="utf-8").lower().split()
    )
    readme = " ".join(
        MIGRATION_README.read_text(encoding="utf-8").lower().split()
    )

    assert migration.filename == "0029_ask_ai_run_durability.sql"
    assert migrations[migrations.index(migration) + 1].version == "0030"
    for column in (
        "execution_version",
        "next_event_sequence",
        "lease_id",
        "lease_expires_at",
        "lease_heartbeat_at",
        "cancellation_request_id",
        "cancellation_requested_at",
        "cancellation_reason_code",
    ):
        assert f"add column {column}" in sql
    assert "alter table public.ask_run_events add column execution_version" in sql
    assert "rollback is flag-off and lease release" in readme
    assert "do not delete events or reset versions/sequences" in readme


def test_0029_applies_from_empty_schema_with_constraints_and_indexes(
    postgres_engine,
) -> None:
    applied = apply_pending_migrations(
        postgres_engine,
        MIGRATIONS_DIR,
        through="0029",
    )

    assert applied[-1].version == "0029"
    with postgres_engine.connect() as connection:
        columns = {
            row["column_name"]: row["is_nullable"]
            for row in connection.execute(
                text(
                    """
                    select column_name, is_nullable
                    from information_schema.columns
                    where table_schema = 'public'
                      and table_name = 'ask_runs'
                    """
                )
            ).mappings()
        }
        event_columns = {
            row["column_name"]: row["is_nullable"]
            for row in connection.execute(
                text(
                    """
                    select column_name, is_nullable
                    from information_schema.columns
                    where table_schema = 'public'
                      and table_name = 'ask_run_events'
                    """
                )
            ).mappings()
        }
        constraints = {
            row["conname"]
            for row in connection.execute(
                text(
                    """
                    select conname
                    from pg_constraint
                    where conrelid in (
                      'public.ask_runs'::regclass,
                      'public.ask_run_events'::regclass
                    )
                    """
                )
            ).mappings()
        }
        indexes = {
            row["indexname"]
            for row in connection.execute(
                text(
                    """
                    select indexname
                    from pg_indexes
                    where schemaname = 'public'
                      and tablename = 'ask_runs'
                    """
                )
            ).mappings()
        }

    assert columns["execution_version"] == "NO"
    assert columns["next_event_sequence"] == "NO"
    assert columns["lease_id"] == "YES"
    assert columns["cancellation_request_id"] == "YES"
    assert event_columns["execution_version"] == "NO"
    assert "ask_run_events_run_execution_version_key" in constraints
    assert "ask_runs_lease_pair_chk" in constraints
    assert "ask_runs_cancellation_pair_chk" in constraints
    assert "ask_runs_active_lease_expiry_idx" in indexes
    assert "ask_runs_pending_cancellation_idx" in indexes


def test_0029_populated_upgrade_preserves_events_and_initializes_allocators(
    postgres_engine,
) -> None:
    apply_pending_migrations(postgres_engine, MIGRATIONS_DIR, through="0026")
    user_id = uuid4()
    second_event_id = uuid4()
    with postgres_engine.begin() as connection:
        insert_auth_user(connection, user_id)
        graph = _seed_artifact_graph(connection, user_id=user_id)
    apply_pending_migrations(postgres_engine, MIGRATIONS_DIR, through="0028")
    with postgres_engine.begin() as connection:
        connection.execute(
            text(
                """
                insert into public.ask_run_events (
                  public_id,
                  run_id,
                  session_id,
                  user_id,
                  sequence,
                  event_type,
                  payload
                )
                values (
                  :public_id,
                  :run_id,
                  :session_id,
                  :user_id,
                  5,
                  'section.ready',
                  '{"retained": true}'::jsonb
                )
                """
            ),
            {
                "public_id": second_event_id,
                "run_id": graph["run_id"],
                "session_id": graph["session_id"],
                "user_id": user_id,
            },
        )

    apply_pending_migrations(postgres_engine, MIGRATIONS_DIR, through="0029")

    with postgres_engine.connect() as connection:
        run = connection.execute(
            text(
                """
                select
                  execution_version,
                  next_event_sequence,
                  lease_id,
                  cancellation_request_id
                from public.ask_runs
                where id = :run_id
                """
            ),
            {"run_id": graph["run_id"]},
        ).mappings().one()
        events = list(
            connection.execute(
                text(
                    """
                    select
                      public_id,
                      sequence,
                      execution_version,
                      event_type,
                      payload
                    from public.ask_run_events
                    where run_id = :run_id
                    order by sequence
                    """
                ),
                {"run_id": graph["run_id"]},
            ).mappings()
        )

    assert run["execution_version"] == 2
    assert run["next_event_sequence"] == 6
    assert run["lease_id"] is None
    assert run["cancellation_request_id"] is None
    assert [row["sequence"] for row in events] == [0, 5]
    assert [row["execution_version"] for row in events] == [1, 2]
    assert events[1]["public_id"] == second_event_id
    assert events[1]["payload"] == {"retained": True}


def test_0029_rejects_partial_lease_cancel_and_duplicate_event_versions(
    postgres_engine,
) -> None:
    apply_pending_migrations(postgres_engine, MIGRATIONS_DIR, through="0026")
    user_id = uuid4()
    with postgres_engine.begin() as connection:
        insert_auth_user(connection, user_id)
        graph = _seed_artifact_graph(connection, user_id=user_id)
    apply_pending_migrations(postgres_engine, MIGRATIONS_DIR, through="0028")
    apply_pending_migrations(postgres_engine, MIGRATIONS_DIR, through="0029")

    base = {
        "run_id": graph["run_id"],
        "session_id": graph["session_id"],
        "user_id": user_id,
    }
    with pytest.raises(IntegrityError), postgres_engine.begin() as connection:
        connection.execute(
            text(
                """
                update public.ask_runs
                set lease_id = :lease_id
                where id = :run_id
                """
            ),
            {**base, "lease_id": uuid4()},
        )

    with pytest.raises(IntegrityError), postgres_engine.begin() as connection:
        connection.execute(
            text(
                """
                update public.ask_runs
                set
                  cancellation_request_id = :request_id,
                  cancellation_reason_code = 'unsafe-detail'
                where id = :run_id
                """
            ),
            {**base, "request_id": uuid4()},
        )

    with pytest.raises(IntegrityError), postgres_engine.begin() as connection:
        connection.execute(
            text(
                """
                insert into public.ask_run_events (
                  run_id,
                  session_id,
                  user_id,
                  sequence,
                  execution_version,
                  event_type
                )
                values (
                  :run_id,
                  :session_id,
                  :user_id,
                  2,
                  1,
                  'duplicate.version'
                )
                """
            ),
            base,
        )
