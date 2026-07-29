from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Literal, Protocol
from uuid import UUID, uuid4

from pydantic import Field
from sqlalchemy.orm import Session

from backend.ask.orchestration.contracts import (
    CapabilityResult,
    CapabilityTerminalState,
    CapabilityTiming,
    ContractModel,
)
from backend.ask.orchestration.durability import (
    DurabilityError,
    DurableRunEvent,
    DurableRunRepository,
    DurableRunSnapshot,
    DurableRunStatus,
    LeaseConflict,
    StaleExecutionVersion,
    validate_orchestration_progress,
)
from backend.ask.orchestration.state_machine import (
    CapabilityWorkState,
    OrchestrationState,
    finish_capability,
)

RUN_EXECUTION_SCHEMA_VERSION = "1"
RUN_EXECUTION_POLICY_VERSION = "ask-ai-run-execution-v1"

TERMINAL_DURABLE_RUN_STATUSES = frozenset(
    {
        DurableRunStatus.COMPLETED,
        DurableRunStatus.PARTIAL,
        DurableRunStatus.FAILED,
        DurableRunStatus.CANCELLED,
    }
)


class RunExecutionOutcome(StrEnum):
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    ALREADY_TERMINAL = "already_terminal"


class RunExecutionResult(ContractModel):
    schema_version: Literal["1"] = RUN_EXECUTION_SCHEMA_VERSION
    policy_version: str = Field(
        default=RUN_EXECUTION_POLICY_VERSION,
        min_length=1,
    )
    outcome: RunExecutionOutcome
    snapshot: DurableRunSnapshot
    accepted_steps: int = Field(ge=0)
    recovered_node_ids: tuple[str, ...] = ()


class RunExecutionError(RuntimeError):
    pass


class RunExecutionInterrupted(RunExecutionError):
    pass


class StaleRunExecution(RunExecutionError):
    pass


class RunExecutionStalled(RunExecutionError):
    pass


class RunExecutionDriver(Protocol):
    async def advance(
        self,
        state: OrchestrationState,
    ) -> OrchestrationState: ...


class DurableRunExecutionStore:
    def __init__(self, session_factory: Callable[[], Session]) -> None:
        self._session_factory = session_factory

    async def load_snapshot(
        self,
        *,
        run_id: UUID,
        session_id: UUID,
        user_id: UUID,
    ) -> DurableRunSnapshot:
        return await asyncio.to_thread(
            self._load_snapshot,
            run_id,
            session_id,
            user_id,
        )

    async def acquire_lease(
        self,
        *,
        run_id: UUID,
        session_id: UUID,
        user_id: UUID,
        lease_id: UUID,
        event_id: UUID,
        now: datetime,
        ttl: timedelta,
    ) -> DurableRunEvent:
        return await asyncio.to_thread(
            self._acquire_lease,
            run_id,
            session_id,
            user_id,
            lease_id,
            event_id,
            now,
            ttl,
        )

    async def renew_lease(
        self,
        *,
        run_id: UUID,
        session_id: UUID,
        user_id: UUID,
        lease_id: UUID,
        event_id: UUID,
        expected_version: int,
        now: datetime,
        ttl: timedelta,
    ) -> DurableRunEvent:
        return await asyncio.to_thread(
            self._renew_lease,
            run_id,
            session_id,
            user_id,
            lease_id,
            event_id,
            expected_version,
            now,
            ttl,
        )

    async def append_state_transition(
        self,
        *,
        run_id: UUID,
        session_id: UUID,
        user_id: UUID,
        lease_id: UUID,
        event_id: UUID,
        expected_version: int,
        state: OrchestrationState,
        now: datetime,
    ) -> DurableRunEvent:
        return await asyncio.to_thread(
            self._append_state_transition,
            run_id,
            session_id,
            user_id,
            lease_id,
            event_id,
            expected_version,
            state,
            now,
        )

    async def apply_cancellation(
        self,
        *,
        run_id: UUID,
        session_id: UUID,
        user_id: UUID,
        lease_id: UUID,
        request_id: UUID,
        event_id: UUID,
        expected_version: int,
        state: OrchestrationState,
        now: datetime,
    ) -> DurableRunEvent:
        return await asyncio.to_thread(
            self._apply_cancellation,
            run_id,
            session_id,
            user_id,
            lease_id,
            request_id,
            event_id,
            expected_version,
            state,
            now,
        )

    def _load_snapshot(
        self,
        run_id: UUID,
        session_id: UUID,
        user_id: UUID,
    ) -> DurableRunSnapshot:
        with self._session_factory() as session:
            return DurableRunRepository(session).load_snapshot(
                run_id=run_id,
                session_id=session_id,
                user_id=user_id,
            )

    def _acquire_lease(
        self,
        run_id: UUID,
        session_id: UUID,
        user_id: UUID,
        lease_id: UUID,
        event_id: UUID,
        now: datetime,
        ttl: timedelta,
    ) -> DurableRunEvent:
        with self._session_factory() as session, session.begin():
            return DurableRunRepository(session).acquire_lease(
                run_id=run_id,
                session_id=session_id,
                user_id=user_id,
                lease_id=lease_id,
                event_id=event_id,
                now=now,
                ttl=ttl,
            )

    def _renew_lease(
        self,
        run_id: UUID,
        session_id: UUID,
        user_id: UUID,
        lease_id: UUID,
        event_id: UUID,
        expected_version: int,
        now: datetime,
        ttl: timedelta,
    ) -> DurableRunEvent:
        with self._session_factory() as session, session.begin():
            return DurableRunRepository(session).renew_lease(
                run_id=run_id,
                session_id=session_id,
                user_id=user_id,
                lease_id=lease_id,
                event_id=event_id,
                expected_version=expected_version,
                now=now,
                ttl=ttl,
            )

    def _append_state_transition(
        self,
        run_id: UUID,
        session_id: UUID,
        user_id: UUID,
        lease_id: UUID,
        event_id: UUID,
        expected_version: int,
        state: OrchestrationState,
        now: datetime,
    ) -> DurableRunEvent:
        with self._session_factory() as session, session.begin():
            return DurableRunRepository(session).append_state_transition(
                run_id=run_id,
                session_id=session_id,
                user_id=user_id,
                lease_id=lease_id,
                event_id=event_id,
                expected_version=expected_version,
                state=state,
                now=now,
            )

    def _apply_cancellation(
        self,
        run_id: UUID,
        session_id: UUID,
        user_id: UUID,
        lease_id: UUID,
        request_id: UUID,
        event_id: UUID,
        expected_version: int,
        state: OrchestrationState,
        now: datetime,
    ) -> DurableRunEvent:
        with self._session_factory() as session, session.begin():
            return DurableRunRepository(session).apply_cancellation(
                run_id=run_id,
                session_id=session_id,
                user_id=user_id,
                lease_id=lease_id,
                request_id=request_id,
                event_id=event_id,
                expected_version=expected_version,
                state=state,
                now=now,
            )


class DurableRunExecutionCoordinator:
    def __init__(
        self,
        *,
        store: DurableRunExecutionStore,
        driver: RunExecutionDriver,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        identity_factory: Callable[[], UUID] = uuid4,
    ) -> None:
        self._store = store
        self._driver = driver
        self._clock = clock
        self._identity_factory = identity_factory

    async def execute(
        self,
        *,
        run_id: UUID,
        session_id: UUID,
        user_id: UUID,
        lease_ttl: timedelta,
        max_steps: int = 100,
    ) -> RunExecutionResult:
        if lease_ttl <= timedelta(0):
            raise ValueError("Run execution lease TTL must be positive")
        if max_steps < 1 or max_steps > 10_000:
            raise ValueError("Run execution max steps must be between 1 and 10000")

        snapshot = await self._store.load_snapshot(
            run_id=run_id,
            session_id=session_id,
            user_id=user_id,
        )
        if snapshot.status in TERMINAL_DURABLE_RUN_STATUSES:
            return _execution_result(
                RunExecutionOutcome.ALREADY_TERMINAL,
                snapshot,
                accepted_steps=0,
            )

        lease_id = self._identity_factory()
        await self._store.acquire_lease(
            run_id=run_id,
            session_id=session_id,
            user_id=user_id,
            lease_id=lease_id,
            event_id=self._identity_factory(),
            now=self._now(),
            ttl=lease_ttl,
        )
        snapshot = await self._owned_snapshot(
            run_id=run_id,
            session_id=session_id,
            user_id=user_id,
            lease_id=lease_id,
        )

        if snapshot.cancellation is not None:
            cancelled = await self._apply_cancellation(
                snapshot=snapshot,
                lease_id=lease_id,
            )
            return _execution_result(
                RunExecutionOutcome.CANCELLED,
                cancelled,
                accepted_steps=0,
            )

        recovered_state, recovered_node_ids = recover_interrupted_capabilities(
            snapshot.orchestration_state,
            now=self._now(),
        )
        if recovered_node_ids:
            snapshot, cancelled = await self._append_state_or_cancel(
                snapshot=snapshot,
                lease_id=lease_id,
                state=recovered_state,
            )
            if cancelled:
                return _execution_result(
                    RunExecutionOutcome.CANCELLED,
                    snapshot,
                    accepted_steps=0,
                )

        accepted_steps = 0
        while snapshot.status not in TERMINAL_DURABLE_RUN_STATUSES:
            if snapshot.cancellation is not None:
                cancelled = await self._apply_cancellation(
                    snapshot=snapshot,
                    lease_id=lease_id,
                )
                return _execution_result(
                    RunExecutionOutcome.CANCELLED,
                    cancelled,
                    accepted_steps=accepted_steps,
                    recovered_node_ids=recovered_node_ids,
                )
            if snapshot.orchestration_state.terminal_state is not None:
                snapshot, cancelled = await self._append_state_or_cancel(
                    snapshot=snapshot,
                    lease_id=lease_id,
                    state=snapshot.orchestration_state,
                )
                if cancelled:
                    return _execution_result(
                        RunExecutionOutcome.CANCELLED,
                        snapshot,
                        accepted_steps=accepted_steps,
                        recovered_node_ids=recovered_node_ids,
                    )
                break
            if accepted_steps >= max_steps:
                raise RunExecutionStalled(
                    "Durable run exceeded its bounded execution steps"
                )
            if accepted_steps:
                try:
                    snapshot = await self._renew(
                        snapshot=snapshot,
                        lease_id=lease_id,
                        ttl=lease_ttl,
                    )
                except StaleRunExecution:
                    cancelled = await self._resolve_stale_cancellation(
                        run_id=run_id,
                        session_id=session_id,
                        user_id=user_id,
                        lease_id=lease_id,
                    )
                    if cancelled is not None:
                        return _execution_result(
                            RunExecutionOutcome.CANCELLED,
                            cancelled,
                            accepted_steps=accepted_steps,
                            recovered_node_ids=recovered_node_ids,
                        )
                    raise

            current_state = snapshot.orchestration_state
            try:
                async with asyncio.timeout(lease_ttl.total_seconds()):
                    candidate = await self._driver.advance(current_state)
            except asyncio.CancelledError:
                raise
            except TimeoutError as exc:
                raise RunExecutionInterrupted(
                    "Durable run step exceeded its worker lease"
                ) from exc
            except Exception as exc:
                raise RunExecutionInterrupted(
                    "Durable run step was interrupted"
                ) from exc
            try:
                snapshot = await self._owned_snapshot(
                    run_id=run_id,
                    session_id=session_id,
                    user_id=user_id,
                    lease_id=lease_id,
                )
            except StaleRunExecution:
                cancelled = await self._resolve_stale_cancellation(
                    run_id=run_id,
                    session_id=session_id,
                    user_id=user_id,
                    lease_id=lease_id,
                )
                if cancelled is not None:
                    return _execution_result(
                        RunExecutionOutcome.CANCELLED,
                        cancelled,
                        accepted_steps=accepted_steps,
                        recovered_node_ids=recovered_node_ids,
                    )
                raise
            if snapshot.cancellation is not None:
                cancelled = await self._apply_cancellation(
                    snapshot=snapshot,
                    lease_id=lease_id,
                )
                return _execution_result(
                    RunExecutionOutcome.CANCELLED,
                    cancelled,
                    accepted_steps=accepted_steps,
                    recovered_node_ids=recovered_node_ids,
                )
            if snapshot.orchestration_state != current_state:
                raise StaleRunExecution(
                    "Durable run changed while its worker step was active"
                )
            if not isinstance(candidate, OrchestrationState):
                raise RunExecutionError(
                    "Run execution driver returned an invalid state"
                )
            if candidate.run_id != run_id:
                raise RunExecutionError(
                    "Run execution driver crossed durable run identity"
                )
            if candidate == current_state:
                raise RunExecutionStalled(
                    "Run execution driver made no durable progress"
                )
            try:
                validate_orchestration_progress(current_state, candidate)
            except DurabilityError as exc:
                raise RunExecutionError(
                    "Run execution driver returned a regressive state"
                ) from exc
            snapshot, cancelled = await self._append_state_or_cancel(
                snapshot=snapshot,
                lease_id=lease_id,
                state=candidate,
            )
            if cancelled:
                return _execution_result(
                    RunExecutionOutcome.CANCELLED,
                    snapshot,
                    accepted_steps=accepted_steps,
                    recovered_node_ids=recovered_node_ids,
                )
            accepted_steps += 1

        return _execution_result(
            RunExecutionOutcome.COMPLETED,
            snapshot,
            accepted_steps=accepted_steps,
            recovered_node_ids=recovered_node_ids,
        )

    async def _owned_snapshot(
        self,
        *,
        run_id: UUID,
        session_id: UUID,
        user_id: UUID,
        lease_id: UUID,
    ) -> DurableRunSnapshot:
        snapshot = await self._store.load_snapshot(
            run_id=run_id,
            session_id=session_id,
            user_id=user_id,
        )
        now = self._now()
        if (
            snapshot.lease is None
            or snapshot.lease.lease_id != lease_id
            or snapshot.lease.expires_at <= now
        ):
            raise StaleRunExecution(
                "Durable run worker lease is stale or no longer owned"
            )
        return snapshot

    async def _renew(
        self,
        *,
        snapshot: DurableRunSnapshot,
        lease_id: UUID,
        ttl: timedelta,
    ) -> DurableRunSnapshot:
        try:
            await self._store.renew_lease(
                run_id=snapshot.run_id,
                session_id=snapshot.session_id,
                user_id=snapshot.user_id,
                lease_id=lease_id,
                event_id=self._identity_factory(),
                expected_version=snapshot.execution_version,
                now=self._now(),
                ttl=ttl,
            )
        except (LeaseConflict, StaleExecutionVersion) as exc:
            raise StaleRunExecution(
                "Durable run changed before lease renewal"
            ) from exc
        return await self._owned_snapshot(
            run_id=snapshot.run_id,
            session_id=snapshot.session_id,
            user_id=snapshot.user_id,
            lease_id=lease_id,
        )

    async def _append_state(
        self,
        *,
        snapshot: DurableRunSnapshot,
        lease_id: UUID,
        state: OrchestrationState,
    ) -> DurableRunSnapshot:
        try:
            await self._store.append_state_transition(
                run_id=snapshot.run_id,
                session_id=snapshot.session_id,
                user_id=snapshot.user_id,
                lease_id=lease_id,
                event_id=self._identity_factory(),
                expected_version=snapshot.execution_version,
                state=state,
                now=self._now(),
            )
        except (LeaseConflict, StaleExecutionVersion) as exc:
            raise StaleRunExecution(
                "Durable run changed before state persistence"
            ) from exc
        return await self._store.load_snapshot(
            run_id=snapshot.run_id,
            session_id=snapshot.session_id,
            user_id=snapshot.user_id,
        )

    async def _apply_cancellation(
        self,
        *,
        snapshot: DurableRunSnapshot,
        lease_id: UUID,
    ) -> DurableRunSnapshot:
        cancellation = snapshot.cancellation
        if cancellation is None:
            raise RunExecutionError("Durable cancellation request is missing")
        try:
            await self._store.apply_cancellation(
                run_id=snapshot.run_id,
                session_id=snapshot.session_id,
                user_id=snapshot.user_id,
                lease_id=lease_id,
                request_id=cancellation.request_id,
                event_id=self._identity_factory(),
                expected_version=snapshot.execution_version,
                state=snapshot.orchestration_state,
                now=self._now(),
            )
        except (LeaseConflict, StaleExecutionVersion) as exc:
            raise StaleRunExecution(
                "Durable run changed before cancellation persistence"
            ) from exc
        return await self._store.load_snapshot(
            run_id=snapshot.run_id,
            session_id=snapshot.session_id,
            user_id=snapshot.user_id,
        )

    async def _append_state_or_cancel(
        self,
        *,
        snapshot: DurableRunSnapshot,
        lease_id: UUID,
        state: OrchestrationState,
    ) -> tuple[DurableRunSnapshot, bool]:
        try:
            persisted = await self._append_state(
                snapshot=snapshot,
                lease_id=lease_id,
                state=state,
            )
            return persisted, False
        except StaleRunExecution:
            cancelled = await self._resolve_stale_cancellation(
                run_id=snapshot.run_id,
                session_id=snapshot.session_id,
                user_id=snapshot.user_id,
                lease_id=lease_id,
            )
            if cancelled is None:
                raise
            return cancelled, True

    async def _resolve_stale_cancellation(
        self,
        *,
        run_id: UUID,
        session_id: UUID,
        user_id: UUID,
        lease_id: UUID,
    ) -> DurableRunSnapshot | None:
        latest = await self._store.load_snapshot(
            run_id=run_id,
            session_id=session_id,
            user_id=user_id,
        )
        if latest.cancellation is None:
            return None
        if latest.status in TERMINAL_DURABLE_RUN_STATUSES:
            return latest
        now = self._now()
        if (
            latest.lease is None
            or latest.lease.lease_id != lease_id
            or latest.lease.expires_at <= now
        ):
            return None
        return await self._apply_cancellation(
            snapshot=latest,
            lease_id=lease_id,
        )

    def _now(self) -> datetime:
        now = self._clock()
        if now.tzinfo is None or now.utcoffset() is None:
            raise RunExecutionError(
                "Run execution clock must return timezone-aware values"
            )
        return now


def recover_interrupted_capabilities(
    state: OrchestrationState,
    *,
    now: datetime,
) -> tuple[OrchestrationState, tuple[str, ...]]:
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("Recovery timestamp must be timezone-aware")
    current = state
    recovered: list[str] = []
    for node in state.capabilities:
        if node.state is not CapabilityWorkState.ACTIVE:
            continue
        if node.request is None:
            raise RunExecutionError(
                "Active capability has no recoverable request identity"
            )
        current = finish_capability(
            current,
            node.node_id,
            CapabilityResult(
                policy_version=node.request.policy_version,
                request_id=node.request.request_id,
                run_id=node.request.run_id,
                capability=node.request.capability,
                terminal_state=CapabilityTerminalState.UNAVAILABLE,
                scope_echo=node.request.scope,
                timing=CapabilityTiming(
                    started_at=now,
                    completed_at=now,
                    duration_ms=0,
                ),
                safe_error_code="CAPABILITY_EXECUTION_INTERRUPTED",
            ),
        )
        recovered.append(node.node_id)
    return current, tuple(recovered)


def _execution_result(
    outcome: RunExecutionOutcome,
    snapshot: DurableRunSnapshot,
    *,
    accepted_steps: int,
    recovered_node_ids: tuple[str, ...] = (),
) -> RunExecutionResult:
    return RunExecutionResult(
        outcome=outcome,
        snapshot=snapshot,
        accepted_steps=accepted_steps,
        recovered_node_ids=recovered_node_ids,
    )
