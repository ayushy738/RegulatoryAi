from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Literal, Protocol, cast

from pydantic import Field, model_validator

from backend.ask.orchestration.contracts import (
    CapabilityRequest,
    CapabilityResult,
    CapabilityTerminalState,
    CapabilityTiming,
    ContractModel,
    OrchestratorCapability,
)
from backend.ask.orchestration.latency import (
    BudgetStopReason,
    LatencyBudget,
    LatencyBudgetError,
)
from backend.ask.orchestration.state_machine import (
    CAPABILITY_TERMINAL_STATES,
    CapabilityNode,
    CapabilityWorkState,
    OrchestrationState,
    activate_capability,
    can_activate_in_phase,
    finish_capability,
)

SCHEDULER_SCHEMA_VERSION = "1"


class ExecutionMode(StrEnum):
    ASYNC = "async"
    BLOCKING_THREAD = "blocking_thread"


@dataclass(frozen=True, slots=True)
class CapabilityInvocation:
    node: CapabilityNode
    request: CapabilityRequest


class AsyncCapabilityExecutor(Protocol):
    async def execute(
        self,
        invocation: CapabilityInvocation,
    ) -> CapabilityResult: ...


class BlockingCapabilityExecutor(Protocol):
    def execute(
        self,
        invocation: CapabilityInvocation,
    ) -> CapabilityResult: ...


@dataclass(frozen=True, slots=True)
class CapabilityBinding:
    execution_mode: ExecutionMode
    executor: AsyncCapabilityExecutor | BlockingCapabilityExecutor

    def __post_init__(self) -> None:
        if not isinstance(self.execution_mode, ExecutionMode):
            raise TypeError("Capability binding requires a declared execution mode")


class CapabilityRequestFactory(Protocol):
    def __call__(
        self,
        state: OrchestrationState,
        node: CapabilityNode,
    ) -> CapabilityRequest: ...


class SchedulerConfig(ContractModel):
    max_concurrency: int = Field(default=4, ge=1, le=100)
    max_blocking_concurrency: int = Field(default=2, ge=1, le=100)

    @model_validator(mode="after")
    def validate_limits(self) -> SchedulerConfig:
        if self.max_blocking_concurrency > self.max_concurrency:
            raise ValueError(
                "Blocking concurrency cannot exceed overall concurrency"
            )
        return self


class SchedulerNodeOutcome(ContractModel):
    node_id: str = Field(min_length=1)
    capability: OrchestratorCapability
    terminal_state: CapabilityTerminalState
    safe_error_code: str | None = None


class SchedulerWave(ContractModel):
    index: int = Field(ge=0)
    node_ids: tuple[str, ...]
    outcomes: tuple[SchedulerNodeOutcome, ...]

    @model_validator(mode="after")
    def validate_wave(self) -> SchedulerWave:
        if not self.node_ids:
            raise ValueError("Scheduler waves cannot be empty")
        if len(set(self.node_ids)) != len(self.node_ids):
            raise ValueError("Scheduler wave node IDs must be unique")
        if tuple(outcome.node_id for outcome in self.outcomes) != self.node_ids:
            raise ValueError("Scheduler outcomes must retain stable node order")
        return self


class SchedulerReport(ContractModel):
    schema_version: Literal["1"] = SCHEDULER_SCHEMA_VERSION
    state: OrchestrationState
    waves: tuple[SchedulerWave, ...] = ()

    @model_validator(mode="after")
    def validate_report(self) -> SchedulerReport:
        node_ids = tuple(
            node_id
            for wave in self.waves
            for node_id in wave.node_ids
        )
        if len(set(node_ids)) != len(node_ids):
            raise ValueError("A scheduler report cannot execute a node twice")
        return self


class SchedulerError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class _ExecutionAttempt:
    invocation: CapabilityInvocation
    result: CapabilityResult


async def execute_ready_phase(
    state: OrchestrationState,
    *,
    request_factory: CapabilityRequestFactory,
    bindings: Mapping[OrchestratorCapability, CapabilityBinding],
    config: SchedulerConfig | None = None,
    clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    budget: LatencyBudget | None = None,
) -> SchedulerReport:
    actual_config = config or SchedulerConfig()
    if state.terminal_state is not None:
        raise SchedulerError("Terminal orchestration cannot execute")
    if any(
        node.state is CapabilityWorkState.ACTIVE
        and can_activate_in_phase(node.capability, node.operation, state.phase)
        for node in state.capabilities
    ):
        raise SchedulerError("Active capability resumption belongs to durability work")

    overall_limit = asyncio.Semaphore(actual_config.max_concurrency)
    blocking_limit = asyncio.Semaphore(actual_config.max_blocking_concurrency)
    current = state
    waves: list[SchedulerWave] = []

    while True:
        ready = _ready_nodes(current)
        if not ready:
            break
        active_state = current
        invocations: list[CapabilityInvocation] = []
        for node in ready:
            try:
                request = request_factory(active_state, node)
            except Exception as exc:
                raise SchedulerError(
                    f"Capability request construction failed for {node.node_id}"
                ) from exc
            if not isinstance(request, CapabilityRequest):
                raise SchedulerError(
                    f"Capability request factory returned an invalid value for "
                    f"{node.node_id}"
                )
            active_state = activate_capability(
                active_state,
                node.node_id,
                request,
            )
            active_node = next(
                item
                for item in active_state.capabilities
                if item.node_id == node.node_id
            )
            invocations.append(
                CapabilityInvocation(node=active_node, request=request)
            )

        attempts = await asyncio.gather(
            *(
                _execute_invocation(
                    invocation,
                    bindings.get(invocation.node.capability),
                    overall_limit,
                    blocking_limit,
                    clock,
                    budget,
                )
                for invocation in invocations
            )
        )
        current = active_state
        outcomes: list[SchedulerNodeOutcome] = []
        for attempt in attempts:
            result = attempt.result
            try:
                current = finish_capability(
                    current,
                    attempt.invocation.node.node_id,
                    result,
                )
            except (TypeError, ValueError):
                result = _failure_result(
                    attempt.invocation.request,
                    CapabilityTerminalState.INVALID_OUTPUT,
                    "CAPABILITY_INVALID_OUTPUT",
                    clock,
                    started_at=None,
                    started_monotonic=None,
                )
                current = finish_capability(
                    current,
                    attempt.invocation.node.node_id,
                    result,
                )
            outcomes.append(
                SchedulerNodeOutcome(
                    node_id=attempt.invocation.node.node_id,
                    capability=attempt.invocation.node.capability,
                    terminal_state=result.terminal_state,
                    safe_error_code=result.safe_error_code,
                )
            )
        waves.append(
            SchedulerWave(
                index=len(waves),
                node_ids=tuple(node.node_id for node in ready),
                outcomes=tuple(outcomes),
            )
        )

    unresolved = tuple(
        node.node_id
        for node in current.capabilities
        if node.state is CapabilityWorkState.QUEUED
        and can_activate_in_phase(node.capability, node.operation, current.phase)
    )
    if unresolved:
        raise SchedulerError(
            "Phase contains queued nodes with unresolved dependencies: "
            + ", ".join(unresolved)
        )
    return SchedulerReport(state=current, waves=tuple(waves))


def scheduler_report_json(report: SchedulerReport) -> str:
    return json.dumps(
        report.model_dump(mode="json"),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def _ready_nodes(state: OrchestrationState) -> tuple[CapabilityNode, ...]:
    nodes = {node.node_id: node for node in state.capabilities}
    return tuple(
        node
        for node in state.capabilities
        if node.state is CapabilityWorkState.QUEUED
        and can_activate_in_phase(node.capability, node.operation, state.phase)
        and all(
            nodes[dependency_id].state in CAPABILITY_TERMINAL_STATES
            for dependency_id in node.dependencies
        )
    )


async def _execute_invocation(
    invocation: CapabilityInvocation,
    binding: CapabilityBinding | None,
    overall_limit: asyncio.Semaphore,
    blocking_limit: asyncio.Semaphore,
    clock: Callable[[], datetime],
    budget: LatencyBudget | None,
) -> _ExecutionAttempt:
    started_at = clock()
    started_monotonic = time.perf_counter()
    stop_reason = (
        budget.stop_reason(
            invocation.node.participation,
            invocation.node.capability,
        )
        if budget is not None
        else None
    )
    if stop_reason is not None:
        return _budget_stopped_attempt(
            invocation,
            stop_reason,
            clock,
            started_at,
            started_monotonic,
        )
    if binding is None:
        return _ExecutionAttempt(
            invocation=invocation,
            result=_failure_result(
                invocation.request,
                CapabilityTerminalState.UNAVAILABLE,
                "CAPABILITY_ADAPTER_UNAVAILABLE",
                clock,
                started_at,
                started_monotonic,
            ),
        )
    try:
        if budget is None:
            result = await _invoke_binding(
                invocation,
                binding,
                overall_limit,
                blocking_limit,
            )
        else:
            timeout = asyncio.timeout(
                budget.remaining_execution_seconds(
                    invocation.node.participation,
                    invocation.node.capability,
                )
            )
            try:
                async with timeout:
                    result = await _invoke_binding(
                        invocation,
                        binding,
                        overall_limit,
                        blocking_limit,
                    )
            except TimeoutError:
                if not timeout.expired():
                    raise
                stop_reason = budget.deadline_stop_reason(
                    invocation.node.participation,
                    invocation.node.capability,
                )
                return _budget_stopped_attempt(
                    invocation,
                    stop_reason,
                    clock,
                    started_at,
                    started_monotonic,
                )
            stop_reason = budget.stop_reason(
                invocation.node.participation,
                invocation.node.capability,
            )
            if stop_reason is not None:
                return _budget_stopped_attempt(
                    invocation,
                    stop_reason,
                    clock,
                    started_at,
                    started_monotonic,
                )
        if not isinstance(result, CapabilityResult):
            return _ExecutionAttempt(
                invocation=invocation,
                result=_failure_result(
                    invocation.request,
                    CapabilityTerminalState.INVALID_OUTPUT,
                    "CAPABILITY_INVALID_OUTPUT",
                    clock,
                    started_at,
                    started_monotonic,
                ),
            )
        return _ExecutionAttempt(invocation=invocation, result=result)
    except LatencyBudgetError:
        raise
    except asyncio.CancelledError:
        raise
    except Exception:
        return _ExecutionAttempt(
            invocation=invocation,
            result=_failure_result(
                invocation.request,
                CapabilityTerminalState.UNAVAILABLE,
                "CAPABILITY_EXECUTION_UNAVAILABLE",
                clock,
                started_at,
                started_monotonic,
            ),
        )


async def _invoke_binding(
    invocation: CapabilityInvocation,
    binding: CapabilityBinding,
    overall_limit: asyncio.Semaphore,
    blocking_limit: asyncio.Semaphore,
) -> object:
    if binding.execution_mode is ExecutionMode.ASYNC:
        async with overall_limit:
            executor = cast(AsyncCapabilityExecutor, binding.executor)
            return await executor.execute(invocation)
    async with blocking_limit:
        async with overall_limit:
            executor = cast(BlockingCapabilityExecutor, binding.executor)
            return await asyncio.to_thread(
                executor.execute,
                invocation,
            )


def _budget_stopped_attempt(
    invocation: CapabilityInvocation,
    stop_reason: BudgetStopReason,
    clock: Callable[[], datetime],
    started_at: datetime,
    started_monotonic: float,
) -> _ExecutionAttempt:
    if stop_reason is BudgetStopReason.HARD_CUTOFF:
        terminal_state = CapabilityTerminalState.TIMED_OUT
        safe_error_code = "CAPABILITY_HARD_CUTOFF"
    elif stop_reason is BudgetStopReason.SOFT_CUTOFF:
        terminal_state = CapabilityTerminalState.TIMED_OUT
        safe_error_code = "CAPABILITY_SOFT_CUTOFF"
    else:
        terminal_state = CapabilityTerminalState.CANCELLED
        safe_error_code = None
    return _ExecutionAttempt(
        invocation=invocation,
        result=_terminal_result(
            invocation.request,
            terminal_state,
            safe_error_code,
            clock,
            started_at,
            started_monotonic,
        ),
    )


def _failure_result(
    request: CapabilityRequest,
    terminal_state: CapabilityTerminalState,
    safe_error_code: str,
    clock: Callable[[], datetime],
    started_at: datetime | None,
    started_monotonic: float | None,
) -> CapabilityResult:
    return _terminal_result(
        request,
        terminal_state,
        safe_error_code,
        clock,
        started_at,
        started_monotonic,
    )


def _terminal_result(
    request: CapabilityRequest,
    terminal_state: CapabilityTerminalState,
    safe_error_code: str | None,
    clock: Callable[[], datetime],
    started_at: datetime | None,
    started_monotonic: float | None,
) -> CapabilityResult:
    actual_started_at = started_at or clock()
    completed_at = clock()
    if actual_started_at.tzinfo is None or completed_at.tzinfo is None:
        raise SchedulerError("Scheduler clock must return timezone-aware values")
    duration_ms = (
        0
        if started_monotonic is None
        else max(0, round((time.perf_counter() - started_monotonic) * 1000))
    )
    return CapabilityResult(
        policy_version=request.policy_version,
        request_id=request.request_id,
        run_id=request.run_id,
        capability=request.capability,
        terminal_state=terminal_state,
        scope_echo=request.scope,
        timing=CapabilityTiming(
            started_at=actual_started_at,
            completed_at=completed_at,
            duration_ms=duration_ms,
        ),
        safe_error_code=safe_error_code,
    )
