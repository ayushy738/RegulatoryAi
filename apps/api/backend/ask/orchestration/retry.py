from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Literal, Protocol
from uuid import UUID, uuid4

from pydantic import Field, model_validator
from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.ask.orchestration.contracts import (
    CapabilityRequest,
    CapabilityResult,
    CapabilityTerminalState,
    ContractModel,
    OrchestratorCapability,
    validate_capability_exchange,
)
from backend.ask.orchestration.durability import (
    DurableRunRepository,
    DurableRunSnapshot,
    DurableRunStatus,
)
from backend.ask.orchestration.failure_policy import (
    FailureTransitionDecision,
    decide_failure_transition,
)
from backend.ask.orchestration.state_machine import (
    CAPABILITY_TERMINAL_STATES,
    FAILURE_TERMINAL_STATES,
    CapabilityNode,
)
from backend.core.db import session_scope

CAPABILITY_RETRY_SCHEMA_VERSION = "1"
CAPABILITY_RETRY_POLICY_VERSION = "ask-ai-capability-retry-v1"
CAPABILITY_RETRY_SAFE_ERROR_CODE = "ASK_CAPABILITY_RETRY_UNAVAILABLE"
CAPABILITY_RETRY_STALE_CODE = "ASK_CAPABILITY_RETRY_STALE"
CAPABILITY_RETRY_CANCELLED_CODE = "ASK_CAPABILITY_RETRY_CANCELLED"
MAX_CAPABILITY_RETRY_TTL = timedelta(seconds=30)

RETRYABLE_CAPABILITIES = frozenset(
    {
        OrchestratorCapability.REGULATORY_RETRIEVER,
        OrchestratorCapability.NEWS_RETRIEVER,
        OrchestratorCapability.GENERAL_AI,
        OrchestratorCapability.CITATION_VERIFIER,
    }
)
RETRYABLE_TERMINAL_STATES = frozenset(
    {
        CapabilityTerminalState.TIMED_OUT,
        CapabilityTerminalState.UNAVAILABLE,
        CapabilityTerminalState.INVALID_OUTPUT,
    }
)


class CapabilityRetryStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class CapabilityRetryRequestBody(ContractModel):
    schema_version: Literal["1"] = CAPABILITY_RETRY_SCHEMA_VERSION
    idempotency_key: UUID
    node_id: str = Field(min_length=1, max_length=200)


class CapabilityRetryPlan(ContractModel):
    schema_version: Literal["1"] = CAPABILITY_RETRY_SCHEMA_VERSION
    policy_version: str = Field(
        default=CAPABILITY_RETRY_POLICY_VERSION,
        min_length=1,
    )
    retry_id: UUID
    run_id: UUID
    node_id: str = Field(min_length=1)
    capability: OrchestratorCapability
    original_request_id: UUID
    original_execution_version: int = Field(gt=0)
    request: CapabilityRequest
    failure_decision: FailureTransitionDecision
    preserved_artifact_ids: tuple[str, ...]

    @model_validator(mode="after")
    def validate_retry_plan(self) -> CapabilityRetryPlan:
        if self.capability not in RETRYABLE_CAPABILITIES:
            raise ValueError("Capability is not independently retryable")
        if self.request.request_id != self.retry_id:
            raise ValueError("Retry request identity must equal its idempotency key")
        if (
            self.request.run_id != self.run_id
            or self.request.capability is not self.capability
        ):
            raise ValueError("Retry request crossed its selected capability")
        if self.failure_decision.failed_node_id != self.node_id:
            raise ValueError("Retry decision crossed its selected node")
        if self.failure_decision.capability is not self.capability:
            raise ValueError("Retry decision crossed its capability")
        if (
            self.failure_decision.terminal_state
            not in RETRYABLE_TERMINAL_STATES
        ):
            raise ValueError("Retry requires a transient terminal failure")
        if (
            self.failure_decision.preserved_artifact_ids
            != self.preserved_artifact_ids
        ):
            raise ValueError("Retry must preserve the exact admitted artifacts")
        return self


class CapabilityRetryRecord(ContractModel):
    schema_version: Literal["1"] = CAPABILITY_RETRY_SCHEMA_VERSION
    policy_version: str = Field(
        default=CAPABILITY_RETRY_POLICY_VERSION,
        min_length=1,
    )
    retry_id: UUID
    run_id: UUID
    session_id: UUID
    user_id: UUID
    plan: CapabilityRetryPlan
    status: CapabilityRetryStatus
    result: CapabilityResult | None = None
    safe_error_code: str | None = Field(
        default=None,
        pattern=r"^[A-Z][A-Z0-9_]{0,99}$",
    )
    lease_id: UUID | None = None
    lease_expires_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None = None

    @model_validator(mode="after")
    def validate_record(self) -> CapabilityRetryRecord:
        for value in (
            self.created_at,
            self.updated_at,
            self.completed_at,
            self.lease_expires_at,
        ):
            if value is not None and (
                value.tzinfo is None or value.utcoffset() is None
            ):
                raise ValueError("Retry timestamps must be timezone-aware")
        if self.retry_id != self.plan.retry_id or self.run_id != self.plan.run_id:
            raise ValueError("Retry record identity does not match its plan")
        leased = self.lease_id is not None or self.lease_expires_at is not None
        if self.status is CapabilityRetryStatus.PENDING:
            valid = (
                self.result is None
                and self.safe_error_code is None
                and not leased
                and self.completed_at is None
            )
        elif self.status is CapabilityRetryStatus.RUNNING:
            valid = (
                self.result is None
                and self.safe_error_code is None
                and self.lease_id is not None
                and self.lease_expires_at is not None
                and self.completed_at is None
            )
        elif self.status is CapabilityRetryStatus.SUCCEEDED:
            valid = (
                self.result is not None
                and self.result.terminal_state not in FAILURE_TERMINAL_STATES
                and self.safe_error_code is None
                and not leased
                and self.completed_at is not None
            )
        else:
            valid = (
                (self.result is not None or self.safe_error_code is not None)
                and not leased
                and self.completed_at is not None
            )
        if not valid:
            raise ValueError("Retry record lifecycle is inconsistent")
        return self


class CapabilityRetryResponse(ContractModel):
    schema_version: Literal["1"] = CAPABILITY_RETRY_SCHEMA_VERSION
    policy_version: str = Field(
        default=CAPABILITY_RETRY_POLICY_VERSION,
        min_length=1,
    )
    retry_id: UUID
    run_id: UUID
    node_id: str
    capability: OrchestratorCapability
    status: CapabilityRetryStatus
    original_execution_version: int = Field(gt=0)
    terminal_state: CapabilityTerminalState | None = None
    artifact_ids: tuple[str, ...] = ()
    safe_error_code: str | None = Field(
        default=None,
        pattern=r"^[A-Z][A-Z0-9_]{0,99}$",
    )

    @classmethod
    def from_record(
        cls,
        record: CapabilityRetryRecord,
    ) -> CapabilityRetryResponse:
        return cls(
            retry_id=record.retry_id,
            run_id=record.run_id,
            node_id=record.plan.node_id,
            capability=record.plan.capability,
            status=record.status,
            original_execution_version=(
                record.plan.original_execution_version
            ),
            terminal_state=(
                record.result.terminal_state
                if record.result is not None
                else None
            ),
            artifact_ids=(
                tuple(
                    artifact.artifact_id
                    for artifact in record.result.artifacts
                )
                if record.result is not None
                else ()
            ),
            safe_error_code=(
                record.safe_error_code
                if record.safe_error_code is not None
                else (
                    record.result.safe_error_code
                    if record.result is not None
                    else None
                )
            ),
        )


@dataclass(frozen=True)
class CapabilityRetryClaim:
    record: CapabilityRetryRecord
    acquired: bool


class CapabilityRetryStore(Protocol):
    async def load_owned_snapshot(
        self,
        *,
        run_id: UUID,
        user_id: UUID,
    ) -> DurableRunSnapshot | None: ...

    async def create(
        self,
        *,
        snapshot: DurableRunSnapshot,
        plan: CapabilityRetryPlan,
        now: datetime,
    ) -> CapabilityRetryRecord: ...

    async def claim(
        self,
        *,
        retry_id: UUID,
        user_id: UUID,
        lease_id: UUID,
        now: datetime,
        ttl: timedelta,
    ) -> CapabilityRetryClaim: ...

    async def finish(
        self,
        *,
        retry_id: UUID,
        user_id: UUID,
        lease_id: UUID,
        result: CapabilityResult | None,
        safe_error_code: str | None,
        now: datetime,
    ) -> CapabilityRetryRecord: ...


class CapabilityRetryExecutor(Protocol):
    async def execute(
        self,
        *,
        node_id: str,
        request: CapabilityRequest,
    ) -> CapabilityResult: ...


class CapabilityRetryError(RuntimeError):
    pass


class CapabilityRetryNotFound(CapabilityRetryError):
    pass


class CapabilityRetryNotEligible(CapabilityRetryError):
    pass


class CapabilityRetryConflict(CapabilityRetryError):
    pass


class CapabilityRetryStale(CapabilityRetryError):
    pass


def plan_capability_retry(
    snapshot: DurableRunSnapshot,
    *,
    node_id: str,
    idempotency_key: UUID,
) -> CapabilityRetryPlan:
    if snapshot.status in {
        DurableRunStatus.FAILED,
        DurableRunStatus.CANCELLED,
    }:
        raise CapabilityRetryNotEligible("Run is not retryable")
    if snapshot.cancellation is not None:
        raise CapabilityRetryNotEligible("Cancelled runs cannot retry")
    try:
        node = next(
            item
            for item in snapshot.orchestration_state.capabilities
            if item.node_id == node_id
        )
    except StopIteration as exc:
        raise CapabilityRetryNotFound("Capability node is inaccessible") from exc
    _validate_retry_node(snapshot, node, idempotency_key)
    assert node.request is not None
    decision = decide_failure_transition(
        snapshot.orchestration_state,
        node.node_id,
    )
    request = node.request.model_copy(
        update={"request_id": idempotency_key},
    )
    return CapabilityRetryPlan(
        retry_id=idempotency_key,
        run_id=snapshot.run_id,
        node_id=node.node_id,
        capability=node.capability,
        original_request_id=node.request.request_id,
        original_execution_version=snapshot.execution_version,
        request=request,
        failure_decision=decision,
        preserved_artifact_ids=tuple(
            artifact.artifact_id
            for artifact in snapshot.orchestration_state.admitted_artifacts
        ),
    )


def _validate_retry_node(
    snapshot: DurableRunSnapshot,
    node: CapabilityNode,
    idempotency_key: UUID,
) -> None:
    if node.capability not in RETRYABLE_CAPABILITIES:
        raise CapabilityRetryNotEligible(
            "Capability cannot be retried independently"
        )
    if node.state not in RETRYABLE_TERMINAL_STATES:
        raise CapabilityRetryNotEligible(
            "Capability is not in a retryable terminal state"
        )
    if node.request is None or node.result is None:
        raise CapabilityRetryNotEligible("Capability has no completed request")
    if any(
        item.request is not None
        and item.request.request_id == idempotency_key
        for item in snapshot.orchestration_state.capabilities
    ):
        raise CapabilityRetryConflict(
            "Retry identity collides with existing capability work"
        )
    nodes = {
        item.node_id: item
        for item in snapshot.orchestration_state.capabilities
    }
    if any(
        nodes[dependency].state not in CAPABILITY_TERMINAL_STATES
        or nodes[dependency].state in FAILURE_TERMINAL_STATES
        for dependency in node.dependencies
    ):
        raise CapabilityRetryNotEligible(
            "Capability retry dependencies are not healthy"
        )
    admitted_ids = {
        artifact.artifact_id
        for artifact in snapshot.orchestration_state.admitted_artifacts
    }
    if not set(node.request.input_artifact_ids).issubset(admitted_ids):
        raise CapabilityRetryNotEligible(
            "Capability retry inputs are no longer admitted"
        )


class CapabilityRetryService:
    def __init__(
        self,
        store: CapabilityRetryStore,
        *,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        identity_factory: Callable[[], UUID] = uuid4,
    ) -> None:
        self._store = store
        self._clock = clock
        self._identity_factory = identity_factory

    async def request(
        self,
        *,
        run_id: UUID,
        user_id: UUID,
        node_id: str,
        idempotency_key: UUID,
    ) -> CapabilityRetryRecord:
        snapshot = await self._store.load_owned_snapshot(
            run_id=run_id,
            user_id=user_id,
        )
        if snapshot is None:
            raise CapabilityRetryNotFound("Run is inaccessible")
        plan = plan_capability_retry(
            snapshot,
            node_id=node_id,
            idempotency_key=idempotency_key,
        )
        return await self._store.create(
            snapshot=snapshot,
            plan=plan,
            now=self._now(),
        )

    async def execute(
        self,
        *,
        retry_id: UUID,
        user_id: UUID,
        executor: CapabilityRetryExecutor,
        lease_ttl: timedelta,
    ) -> CapabilityRetryRecord:
        if lease_ttl <= timedelta(0):
            raise ValueError("Capability retry TTL must be positive")
        if lease_ttl > MAX_CAPABILITY_RETRY_TTL:
            raise ValueError("Capability retry TTL exceeds the hard budget")
        lease_id = self._identity_factory()
        claim = await self._store.claim(
            retry_id=retry_id,
            user_id=user_id,
            lease_id=lease_id,
            now=self._now(),
            ttl=lease_ttl,
        )
        if not claim.acquired:
            return claim.record
        try:
            async with asyncio.timeout(lease_ttl.total_seconds()):
                result = await executor.execute(
                    node_id=claim.record.plan.node_id,
                    request=claim.record.plan.request,
                )
            if not isinstance(result, CapabilityResult):
                raise TypeError("Retry executor returned an invalid result")
            validate_capability_exchange(claim.record.plan.request, result)
            artifact_ids = tuple(
                artifact.artifact_id for artifact in result.artifacts
            )
            if (
                len(set(artifact_ids)) != len(artifact_ids)
                or set(artifact_ids)
                & set(claim.record.plan.preserved_artifact_ids)
            ):
                raise ValueError("Retry result artifact identity is invalid")
            return await self._store.finish(
                retry_id=retry_id,
                user_id=user_id,
                lease_id=lease_id,
                result=result,
                safe_error_code=None,
                now=self._now(),
            )
        except asyncio.CancelledError:
            raise
        except Exception:
            return await self._store.finish(
                retry_id=retry_id,
                user_id=user_id,
                lease_id=lease_id,
                result=None,
                safe_error_code=CAPABILITY_RETRY_SAFE_ERROR_CODE,
                now=self._now(),
            )

    def _now(self) -> datetime:
        now = self._clock()
        if now.tzinfo is None or now.utcoffset() is None:
            raise CapabilityRetryError(
                "Capability retry clock must be timezone-aware"
            )
        return now


class PostgresCapabilityRetryStore:
    def __init__(
        self,
        session_scope_factory: Callable[
            [], AbstractContextManager[Session]
        ] = session_scope,
    ) -> None:
        self._session_scope_factory = session_scope_factory

    async def load_owned_snapshot(
        self,
        *,
        run_id: UUID,
        user_id: UUID,
    ) -> DurableRunSnapshot | None:
        return await asyncio.to_thread(
            self._load_owned_snapshot,
            run_id,
            user_id,
        )

    async def create(
        self,
        *,
        snapshot: DurableRunSnapshot,
        plan: CapabilityRetryPlan,
        now: datetime,
    ) -> CapabilityRetryRecord:
        return await asyncio.to_thread(
            self._create,
            snapshot,
            plan,
            now,
        )

    async def claim(
        self,
        *,
        retry_id: UUID,
        user_id: UUID,
        lease_id: UUID,
        now: datetime,
        ttl: timedelta,
    ) -> CapabilityRetryClaim:
        return await asyncio.to_thread(
            self._claim,
            retry_id,
            user_id,
            lease_id,
            now,
            ttl,
        )

    async def finish(
        self,
        *,
        retry_id: UUID,
        user_id: UUID,
        lease_id: UUID,
        result: CapabilityResult | None,
        safe_error_code: str | None,
        now: datetime,
    ) -> CapabilityRetryRecord:
        return await asyncio.to_thread(
            self._finish,
            retry_id,
            user_id,
            lease_id,
            result,
            safe_error_code,
            now,
        )

    def _load_owned_snapshot(
        self,
        run_id: UUID,
        user_id: UUID,
    ) -> DurableRunSnapshot | None:
        with (
            self._session_scope_factory() as database_session,
            database_session.begin(),
        ):
            session_id = _owned_session_id(
                database_session,
                run_id=run_id,
                user_id=user_id,
                lock=False,
            )
            if session_id is None:
                return None
            return DurableRunRepository(database_session).load_snapshot(
                run_id=run_id,
                session_id=session_id,
                user_id=user_id,
            )

    def _create(
        self,
        snapshot: DurableRunSnapshot,
        plan: CapabilityRetryPlan,
        now: datetime,
    ) -> CapabilityRetryRecord:
        with (
            self._session_scope_factory() as database_session,
            database_session.begin(),
        ):
            session_id = _owned_session_id(
                database_session,
                run_id=snapshot.run_id,
                user_id=snapshot.user_id,
                lock=True,
            )
            if session_id != snapshot.session_id:
                raise CapabilityRetryNotFound("Run is inaccessible")
            current = DurableRunRepository(database_session).load_snapshot(
                run_id=snapshot.run_id,
                session_id=snapshot.session_id,
                user_id=snapshot.user_id,
            )
            if (
                current.execution_version != plan.original_execution_version
                or current.cancellation is not None
            ):
                raise CapabilityRetryStale(
                    "Run changed before retry persistence"
                )
            identity_row = database_session.execute(
                text(
                    """
                    select *
                    from public.ask_capability_retries
                    where id = :retry_id
                    """
                ),
                {"retry_id": plan.retry_id},
            ).mappings().one_or_none()
            if identity_row is not None:
                identity_record = _retry_record(identity_row)
                if (
                    identity_record.user_id == snapshot.user_id
                    and identity_record.plan == plan
                ):
                    return identity_record
                raise CapabilityRetryConflict(
                    "Retry identity was reused for another action"
                )
            existing = database_session.execute(
                text(
                    """
                    select *
                    from public.ask_capability_retries
                    where run_id = :run_id
                      and node_id = :node_id
                      and original_request_id = :original_request_id
                    """
                ),
                {
                    "run_id": plan.run_id,
                    "node_id": plan.node_id,
                    "original_request_id": plan.original_request_id,
                },
            ).mappings().one_or_none()
            if existing is not None:
                if existing["id"] != plan.retry_id:
                    raise CapabilityRetryConflict(
                        "Capability already has its bounded retry"
                    )
                record = _retry_record(existing)
                if record.plan != plan:
                    raise CapabilityRetryConflict(
                        "Retry identity was reused for another action"
                    )
                return record
            inserted = database_session.execute(
                text(
                    """
                    insert into public.ask_capability_retries (
                      id,
                      run_id,
                      session_id,
                      user_id,
                      node_id,
                      capability,
                      original_request_id,
                      original_execution_version,
                      retry_plan,
                      created_at,
                      updated_at
                    )
                    values (
                      :id,
                      :run_id,
                      :session_id,
                      :user_id,
                      :node_id,
                      :capability,
                      :original_request_id,
                      :original_execution_version,
                      cast(:retry_plan as jsonb),
                      :now,
                      :now
                    )
                    on conflict do nothing
                    """
                ),
                {
                    "id": plan.retry_id,
                    "run_id": plan.run_id,
                    "session_id": snapshot.session_id,
                    "user_id": snapshot.user_id,
                    "node_id": plan.node_id,
                    "capability": plan.capability.value,
                    "original_request_id": plan.original_request_id,
                    "original_execution_version": (
                        plan.original_execution_version
                    ),
                    "retry_plan": json.dumps(plan.model_dump(mode="json")),
                    "now": now,
                },
            )
            if inserted.rowcount != 1:
                raise CapabilityRetryConflict(
                    "Retry identity was reused for another action"
                )
            return _load_retry(
                database_session,
                retry_id=plan.retry_id,
                user_id=snapshot.user_id,
                lock=False,
            )

    def _claim(
        self,
        retry_id: UUID,
        user_id: UUID,
        lease_id: UUID,
        now: datetime,
        ttl: timedelta,
    ) -> CapabilityRetryClaim:
        with (
            self._session_scope_factory() as database_session,
            database_session.begin(),
        ):
            record = _load_retry(
                database_session,
                retry_id=retry_id,
                user_id=user_id,
                lock=True,
            )
            if record.status in {
                CapabilityRetryStatus.SUCCEEDED,
                CapabilityRetryStatus.FAILED,
            }:
                return CapabilityRetryClaim(record=record, acquired=False)
            if (
                record.status is CapabilityRetryStatus.RUNNING
                and record.lease_expires_at is not None
                and record.lease_expires_at > now
            ):
                return CapabilityRetryClaim(record=record, acquired=False)
            current = DurableRunRepository(database_session).load_snapshot(
                run_id=record.run_id,
                session_id=record.session_id,
                user_id=record.user_id,
            )
            if (
                current.execution_version
                != record.plan.original_execution_version
                or current.cancellation is not None
            ):
                return CapabilityRetryClaim(
                    record=_fail_locked_retry(
                        database_session,
                        record=record,
                        safe_error_code=(
                            CAPABILITY_RETRY_CANCELLED_CODE
                            if current.cancellation is not None
                            else CAPABILITY_RETRY_STALE_CODE
                        ),
                        now=now,
                    ),
                    acquired=False,
                )
            database_session.execute(
                text(
                    """
                    update public.ask_capability_retries
                    set
                      status = 'running',
                      lease_id = :lease_id,
                      lease_expires_at = :lease_expires_at,
                      updated_at = :now
                    where id = :retry_id
                      and user_id = :user_id
                    """
                ),
                {
                    "retry_id": retry_id,
                    "user_id": user_id,
                    "lease_id": lease_id,
                    "lease_expires_at": now + ttl,
                    "now": now,
                },
            )
            return CapabilityRetryClaim(
                record=_load_retry(
                    database_session,
                    retry_id=retry_id,
                    user_id=user_id,
                    lock=False,
                ),
                acquired=True,
            )

    def _finish(
        self,
        retry_id: UUID,
        user_id: UUID,
        lease_id: UUID,
        result: CapabilityResult | None,
        safe_error_code: str | None,
        now: datetime,
    ) -> CapabilityRetryRecord:
        with (
            self._session_scope_factory() as database_session,
            database_session.begin(),
        ):
            record = _load_retry(
                database_session,
                retry_id=retry_id,
                user_id=user_id,
                lock=True,
            )
            if record.status in {
                CapabilityRetryStatus.SUCCEEDED,
                CapabilityRetryStatus.FAILED,
            }:
                return record
            if (
                record.status is not CapabilityRetryStatus.RUNNING
                or record.lease_id != lease_id
                or record.lease_expires_at is None
                or record.lease_expires_at <= now
            ):
                raise CapabilityRetryStale(
                    "Capability retry worker lease is stale"
                )
            current = DurableRunRepository(database_session).load_snapshot(
                run_id=record.run_id,
                session_id=record.session_id,
                user_id=record.user_id,
            )
            if (
                current.execution_version
                != record.plan.original_execution_version
                or current.cancellation is not None
            ):
                return _fail_locked_retry(
                    database_session,
                    record=record,
                    safe_error_code=(
                        CAPABILITY_RETRY_CANCELLED_CODE
                        if current.cancellation is not None
                        else CAPABILITY_RETRY_STALE_CODE
                    ),
                    now=now,
                )
            failed_result = (
                result is not None
                and result.terminal_state in FAILURE_TERMINAL_STATES
            )
            status = (
                CapabilityRetryStatus.FAILED
                if result is None or failed_result
                else CapabilityRetryStatus.SUCCEEDED
            )
            database_session.execute(
                text(
                    """
                    update public.ask_capability_retries
                    set
                      status = :status,
                      result = cast(:result as jsonb),
                      safe_error_code = :safe_error_code,
                      lease_id = null,
                      lease_expires_at = null,
                      completed_at = :now,
                      updated_at = :now
                    where id = :retry_id
                      and user_id = :user_id
                    """
                ),
                {
                    "retry_id": retry_id,
                    "user_id": user_id,
                    "status": status.value,
                    "result": (
                        json.dumps(result.model_dump(mode="json"))
                        if result is not None
                        else None
                    ),
                    "safe_error_code": (
                        safe_error_code
                        if result is None
                        else None
                    ),
                    "now": now,
                },
            )
            return _load_retry(
                database_session,
                retry_id=retry_id,
                user_id=user_id,
                lock=False,
            )


def _owned_session_id(
    database_session: Session,
    *,
    run_id: UUID,
    user_id: UUID,
    lock: bool,
) -> UUID | None:
    statement = """
        select ar.session_id
        from public.ask_runs ar
        join public.chat_sessions cs
          on cs.id = ar.session_id
         and cs.user_id = ar.user_id
        where ar.id = :run_id
          and ar.user_id = :user_id
          and cs.deleted_at is null
    """
    if lock:
        statement += " for update of ar"
    row = database_session.execute(
        text(statement),
        {"run_id": run_id, "user_id": user_id},
    ).mappings().one_or_none()
    return row["session_id"] if row is not None else None


def _load_retry(
    database_session: Session,
    *,
    retry_id: UUID,
    user_id: UUID,
    lock: bool,
) -> CapabilityRetryRecord:
    statement = """
        select acr.*
        from public.ask_capability_retries acr
        join public.chat_sessions cs
          on cs.id = acr.session_id
         and cs.user_id = acr.user_id
        where acr.id = :retry_id
          and acr.user_id = :user_id
          and cs.deleted_at is null
    """
    if lock:
        statement += " for update of acr"
    row = database_session.execute(
        text(statement),
        {"retry_id": retry_id, "user_id": user_id},
    ).mappings().one_or_none()
    if row is None:
        raise CapabilityRetryNotFound("Capability retry is inaccessible")
    return _retry_record(row)


def _retry_record(row) -> CapabilityRetryRecord:
    return CapabilityRetryRecord(
        retry_id=row["id"],
        run_id=row["run_id"],
        session_id=row["session_id"],
        user_id=row["user_id"],
        plan=CapabilityRetryPlan.model_validate(row["retry_plan"]),
        status=CapabilityRetryStatus(row["status"]),
        result=(
            CapabilityResult.model_validate(row["result"])
            if row["result"] is not None
            else None
        ),
        safe_error_code=row["safe_error_code"],
        lease_id=row["lease_id"],
        lease_expires_at=row["lease_expires_at"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        completed_at=row["completed_at"],
    )


def _fail_locked_retry(
    database_session: Session,
    *,
    record: CapabilityRetryRecord,
    safe_error_code: str,
    now: datetime,
) -> CapabilityRetryRecord:
    database_session.execute(
        text(
            """
            update public.ask_capability_retries
            set
              status = 'failed',
              safe_error_code = :safe_error_code,
              lease_id = null,
              lease_expires_at = null,
              completed_at = :now,
              updated_at = :now
            where id = :retry_id
              and user_id = :user_id
            """
        ),
        {
            "retry_id": record.retry_id,
            "user_id": record.user_id,
            "safe_error_code": safe_error_code,
            "now": now,
        },
    )
    return _load_retry(
        database_session,
        retry_id=record.retry_id,
        user_id=record.user_id,
        lock=False,
    )
