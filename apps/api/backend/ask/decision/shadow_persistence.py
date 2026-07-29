from __future__ import annotations

import json
from collections.abc import Callable
from contextlib import AbstractContextManager
from enum import StrEnum
from uuid import UUID

from pydantic import Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.ask.decision.models import DecisionModel, DecisionRecord
from backend.core.db import session_scope


class ShadowDecisionWriteOutcome(StrEnum):
    STORED = "stored"
    IDEMPOTENT = "idempotent"
    NOT_FOUND = "not_found"
    CONFLICT = "conflict"


class ShadowDecisionWriteResult(DecisionModel):
    outcome: ShadowDecisionWriteOutcome
    run_id: UUID | None = None
    policy_version: str | None = Field(default=None, min_length=1)


class ShadowDecisionRunRepository:
    def __init__(self, database_session: Session) -> None:
        self._session = database_session

    def persist_owned(
        self,
        *,
        run_id: UUID,
        user_id: UUID,
        decision_record: DecisionRecord,
    ) -> ShadowDecisionWriteResult:
        record = DecisionRecord.model_validate(
            decision_record.model_dump(mode="python")
        )
        row = self._session.execute(
            text(
                """
                select decision_record, policy_version
                from public.ask_runs
                where id = :run_id and user_id = :user_id
                for update
                """
            ),
            {"run_id": run_id, "user_id": user_id},
        ).mappings().one_or_none()
        if row is None:
            return ShadowDecisionWriteResult(
                outcome=ShadowDecisionWriteOutcome.NOT_FOUND
            )

        canonical = record.model_dump(mode="json")
        existing = dict(row["decision_record"])
        existing_policy = row["policy_version"]
        if existing:
            if (
                existing == canonical
                and existing_policy in {None, record.policy_version}
            ):
                if existing_policy is None:
                    self._session.execute(
                        text(
                            """
                            update public.ask_runs
                            set policy_version = :policy_version, updated_at = now()
                            where id = :run_id and user_id = :user_id
                            """
                        ),
                        {
                            "run_id": run_id,
                            "user_id": user_id,
                            "policy_version": record.policy_version,
                        },
                    )
                return ShadowDecisionWriteResult(
                    outcome=ShadowDecisionWriteOutcome.IDEMPOTENT,
                    run_id=run_id,
                    policy_version=record.policy_version,
                )
            return ShadowDecisionWriteResult(
                outcome=ShadowDecisionWriteOutcome.CONFLICT,
                run_id=run_id,
                policy_version=existing_policy,
            )
        if existing_policy not in {None, record.policy_version}:
            return ShadowDecisionWriteResult(
                outcome=ShadowDecisionWriteOutcome.CONFLICT,
                run_id=run_id,
                policy_version=existing_policy,
            )

        self._session.execute(
            text(
                """
                update public.ask_runs
                set
                  decision_record = cast(:decision_record as jsonb),
                  policy_version = :policy_version,
                  updated_at = now()
                where id = :run_id and user_id = :user_id
                """
            ),
            {
                "run_id": run_id,
                "user_id": user_id,
                "decision_record": json.dumps(
                    canonical,
                    ensure_ascii=False,
                    separators=(",", ":"),
                    sort_keys=True,
                ),
                "policy_version": record.policy_version,
            },
        )
        return ShadowDecisionWriteResult(
            outcome=ShadowDecisionWriteOutcome.STORED,
            run_id=run_id,
            policy_version=record.policy_version,
        )


SessionScopeFactory = Callable[[], AbstractContextManager[Session]]


class ShadowDecisionPersistenceService:
    def __init__(
        self,
        session_scope_factory: SessionScopeFactory = session_scope,
    ) -> None:
        self._session_scope_factory = session_scope_factory

    def persist_owned_run(
        self,
        *,
        run_id: UUID,
        user_id: UUID,
        decision_record: DecisionRecord,
    ) -> ShadowDecisionWriteResult:
        with self._session_scope_factory() as database_session:
            return ShadowDecisionRunRepository(database_session).persist_owned(
                run_id=run_id,
                user_id=user_id,
                decision_record=decision_record,
            )
