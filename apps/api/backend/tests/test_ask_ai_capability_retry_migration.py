from __future__ import annotations

import asyncio
from contextlib import contextmanager
from datetime import timedelta
from pathlib import Path
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.ask.orchestration.retry import (
    CAPABILITY_RETRY_STALE_CODE,
    CapabilityRetryService,
    CapabilityRetryStatus,
    PostgresCapabilityRetryStore,
)
from backend.core.migrations import apply_pending_migrations, discover_migrations
from backend.tests.ask_ai_postgres import POSTGRES_MARK, insert_auth_user
from backend.tests.test_ask_ai_capability_retry import (
    NODE_ID,
    NOW,
    RecordingExecutor,
    _snapshot,
)
from backend.tests.test_ask_ai_orchestration_durability import _seed_run

pytestmark = POSTGRES_MARK

MIGRATIONS_DIR = Path(__file__).parents[1] / "migrations"
RETRY_MIGRATION = MIGRATIONS_DIR / "0031_ask_ai_capability_retries.sql"
MIGRATION_README = MIGRATIONS_DIR / "README.md"


def test_0031_is_ordered_additive_and_documents_retained_rollback() -> None:
    migrations = discover_migrations(MIGRATIONS_DIR)
    migration = next(item for item in migrations if item.version == "0031")
    sql = " ".join(
        RETRY_MIGRATION.read_text(encoding="utf-8").lower().split()
    )
    readme = " ".join(
        MIGRATION_README.read_text(encoding="utf-8").lower().split()
    )

    assert migration.filename == "0031_ask_ai_capability_retries.sql"
    assert migrations[migrations.index(migration) + 1].version == "0032"
    assert "create table public.ask_capability_retries" in sql
    assert "unique (run_id, node_id, original_request_id)" in sql
    assert "enable row level security" in sql
    assert "rollback is flag-off and worker stop" in readme
    assert "do not drop retry records" in readme


def test_0031_applies_from_empty_with_constraints_indexes_and_rls(
    postgres_engine,
) -> None:
    applied = apply_pending_migrations(
        postgres_engine,
        MIGRATIONS_DIR,
        through="0031",
    )

    assert applied[-1].version == "0031"
    with postgres_engine.connect() as connection:
        constraints = {
            row["conname"]
            for row in connection.execute(
                text(
                    """
                    select constraint_record.conname
                    from pg_constraint constraint_record
                    where constraint_record.conrelid =
                      'public.ask_capability_retries'::regclass
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
                      and tablename = 'ask_capability_retries'
                    """
                )
            ).mappings()
        }
        security = connection.execute(
            text(
                """
                select relrowsecurity
                from pg_class
                where oid = 'public.ask_capability_retries'::regclass
                """
            )
        ).scalar_one()

    assert {
        "ask_capability_retries_run_owner_fkey",
        "ask_capability_retries_original_request_key",
        "ask_capability_retries_state_chk",
        "ask_capability_retries_lease_pair_chk",
    } <= constraints
    assert {
        "ask_capability_retries_owner_created_idx",
        "ask_capability_retries_recovery_idx",
    } <= indexes
    assert security is True


def test_0031_populated_upgrade_preserves_existing_run(postgres_engine) -> None:
    apply_pending_migrations(postgres_engine, MIGRATIONS_DIR, through="0030")
    snapshot = _snapshot()
    with postgres_engine.begin() as connection:
        insert_auth_user(connection, snapshot.user_id)
        run_id, session_id = _seed_run(
            connection,
            user_id=snapshot.user_id,
            state=snapshot.orchestration_state,
        )
        connection.execute(
            text(
                """
                update public.ask_runs
                set
                  status = :status,
                  execution_version = :execution_version,
                  next_event_sequence = :next_event_sequence
                where id = :run_id
                """
            ),
            {
                "run_id": run_id,
                "status": snapshot.status.value,
                "execution_version": snapshot.execution_version,
                "next_event_sequence": snapshot.next_event_sequence,
            },
        )

    apply_pending_migrations(postgres_engine, MIGRATIONS_DIR, through="0031")

    with postgres_engine.connect() as connection:
        retained = connection.execute(
            text(
                """
                select session_id, user_id, status, execution_version
                from public.ask_runs
                where id = :run_id
                """
            ),
            {"run_id": run_id},
        ).mappings().one()
    assert retained == {
        "session_id": session_id,
        "user_id": snapshot.user_id,
        "status": snapshot.status.value,
        "execution_version": snapshot.execution_version,
    }


def test_postgres_retry_is_owner_scoped_idempotent_and_executes_once(
    postgres_engine,
) -> None:
    apply_pending_migrations(postgres_engine, MIGRATIONS_DIR, through="0031")
    snapshot = _snapshot()
    with postgres_engine.begin() as connection:
        insert_auth_user(connection, snapshot.user_id)
        run_id, session_id = _seed_run(
            connection,
            user_id=snapshot.user_id,
            state=snapshot.orchestration_state,
        )
        connection.execute(
            text(
                """
                update public.ask_runs
                set
                  status = :status,
                  execution_version = :execution_version,
                  next_event_sequence = :next_event_sequence
                where id = :run_id
                """
            ),
            {
                "run_id": run_id,
                "status": snapshot.status.value,
                "execution_version": snapshot.execution_version,
                "next_event_sequence": snapshot.next_event_sequence,
            },
        )

    @contextmanager
    def test_session_scope():
        with Session(postgres_engine) as database_session:
            yield database_session
            database_session.commit()

    retry_id = uuid4()
    store = PostgresCapabilityRetryStore(test_session_scope)
    service = CapabilityRetryService(store, clock=lambda: NOW)
    created = asyncio.run(
        service.request(
            run_id=run_id,
            user_id=snapshot.user_id,
            node_id=NODE_ID,
            idempotency_key=retry_id,
        )
    )
    repeated = asyncio.run(
        service.request(
            run_id=run_id,
            user_id=snapshot.user_id,
            node_id=NODE_ID,
            idempotency_key=retry_id,
        )
    )
    executor = RecordingExecutor()
    with postgres_engine.begin() as connection:
        connection.execute(
            text(
                "select set_config('request.jwt.claim.sub', :user_id, true)"
            ),
            {"user_id": str(snapshot.user_id)},
        )
        connection.execute(text("set local role authenticated"))
        assert connection.execute(
            text("select count(*) from public.ask_capability_retries")
        ).scalar_one() == 1
        connection.execute(text("reset role"))
        connection.execute(
            text(
                "select set_config('request.jwt.claim.sub', :user_id, true)"
            ),
            {"user_id": str(uuid4())},
        )
        connection.execute(text("set local role authenticated"))
        assert connection.execute(
            text("select count(*) from public.ask_capability_retries")
        ).scalar_one() == 0

    completed = asyncio.run(
        service.execute(
            retry_id=retry_id,
            user_id=snapshot.user_id,
            executor=executor,
            lease_ttl=timedelta(seconds=5),
        )
    )
    completed_again = asyncio.run(
        service.execute(
            retry_id=retry_id,
            user_id=snapshot.user_id,
            executor=executor,
            lease_ttl=timedelta(seconds=5),
        )
    )

    assert created == repeated
    assert completed.status is CapabilityRetryStatus.SUCCEEDED
    assert completed_again == completed
    assert executor.calls == [(NODE_ID, retry_id)]
    assert asyncio.run(
        store.load_owned_snapshot(
            run_id=run_id,
            user_id=uuid4(),
        )
    ) is None
    with postgres_engine.connect() as connection:
        run = connection.execute(
            text(
                """
                select orchestration_state, execution_version
                from public.ask_runs
                where id = :run_id and session_id = :session_id
                """
            ),
            {"run_id": run_id, "session_id": session_id},
        ).mappings().one()
    assert run["orchestration_state"] == (
        snapshot.orchestration_state.model_dump(mode="json")
    )
    assert run["execution_version"] == snapshot.execution_version


def test_postgres_retry_fails_stale_before_invoking_executor(
    postgres_engine,
) -> None:
    apply_pending_migrations(postgres_engine, MIGRATIONS_DIR, through="0031")
    snapshot = _snapshot()
    with postgres_engine.begin() as connection:
        insert_auth_user(connection, snapshot.user_id)
        run_id, _session_id = _seed_run(
            connection,
            user_id=snapshot.user_id,
            state=snapshot.orchestration_state,
        )
        connection.execute(
            text(
                """
                update public.ask_runs
                set
                  status = :status,
                  execution_version = :execution_version,
                  next_event_sequence = :next_event_sequence
                where id = :run_id
                """
            ),
            {
                "run_id": run_id,
                "status": snapshot.status.value,
                "execution_version": snapshot.execution_version,
                "next_event_sequence": snapshot.next_event_sequence,
            },
        )

    @contextmanager
    def test_session_scope():
        with Session(postgres_engine) as database_session:
            yield database_session
            database_session.commit()

    retry_id = uuid4()
    store = PostgresCapabilityRetryStore(test_session_scope)
    service = CapabilityRetryService(store, clock=lambda: NOW)
    asyncio.run(
        service.request(
            run_id=run_id,
            user_id=snapshot.user_id,
            node_id=NODE_ID,
            idempotency_key=retry_id,
        )
    )
    with postgres_engine.begin() as connection:
        connection.execute(
            text(
                """
                update public.ask_runs
                set
                  execution_version = execution_version + 1,
                  next_event_sequence = next_event_sequence + 1
                where id = :run_id
                """
            ),
            {"run_id": run_id},
        )
    executor = RecordingExecutor()

    failed = asyncio.run(
        service.execute(
            retry_id=retry_id,
            user_id=snapshot.user_id,
            executor=executor,
            lease_ttl=timedelta(seconds=5),
        )
    )

    assert failed.status is CapabilityRetryStatus.FAILED
    assert failed.safe_error_code == CAPABILITY_RETRY_STALE_CODE
    assert executor.calls == []
