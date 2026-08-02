from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from backend.ask.decision.shadow import DeterministicShadowDecisionEvaluator
from backend.ask.decision.shadow_persistence import (
    ShadowDecisionPersistenceService,
    ShadowDecisionWriteOutcome,
)
from backend.core.migrations import apply_pending_migrations
from backend.tests.ask_ai_postgres import POSTGRES_MARK, insert_auth_user
from backend.tests.test_ask_ai_saved_items import _seed_targets

pytestmark = POSTGRES_MARK

MIGRATIONS_DIR = Path(__file__).parents[1] / "migrations"
NOW = datetime(2026, 7, 27, 12, tzinfo=UTC)


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


def test_owned_run_shadow_decision_is_exact_idempotent_and_non_overwriting(
    postgres_engine: Engine,
) -> None:
    apply_pending_migrations(postgres_engine, MIGRATIONS_DIR, through="0030")
    owner_id = uuid4()
    other_id = uuid4()
    with postgres_engine.begin() as connection:
        insert_auth_user(connection, owner_id)
        insert_auth_user(connection, other_id)
        graph = _seed_targets(connection, user_id=owner_id)

    service = ShadowDecisionPersistenceService(
        lambda: _session_scope(postgres_engine)
    )
    evaluator = DeterministicShadowDecisionEvaluator()
    record = evaluator.evaluate(
        query="Latest DSM amendment",
        now=NOW,
        user_timezone="UTC",
    )

    stored = service.persist_owned_run(
        run_id=graph["run_id"],
        user_id=owner_id,
        decision_record=record,
    )
    repeated = service.persist_owned_run(
        run_id=graph["run_id"],
        user_id=owner_id,
        decision_record=record,
    )
    hidden = service.persist_owned_run(
        run_id=graph["run_id"],
        user_id=other_id,
        decision_record=record,
    )
    conflicting_record = evaluator.evaluate(
        query="What is DSM",
        now=NOW,
        user_timezone="UTC",
    )
    conflict = service.persist_owned_run(
        run_id=graph["run_id"],
        user_id=owner_id,
        decision_record=conflicting_record,
    )

    assert stored.outcome is ShadowDecisionWriteOutcome.STORED
    assert repeated.outcome is ShadowDecisionWriteOutcome.IDEMPOTENT
    assert hidden.outcome is ShadowDecisionWriteOutcome.NOT_FOUND
    assert hidden.run_id is None
    assert conflict.outcome is ShadowDecisionWriteOutcome.CONFLICT
    with postgres_engine.connect() as connection:
        persisted = connection.execute(
            text(
                """
                select decision_record, policy_version
                from public.ask_runs
                where id = :run_id
                """
            ),
            {"run_id": graph["run_id"]},
        ).mappings().one()

    assert persisted["decision_record"] == record.model_dump(mode="json")
    assert persisted["policy_version"] == record.policy_version
