from __future__ import annotations

import json
import time
from collections import Counter
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from enum import StrEnum
from typing import Literal, Protocol, Self

from pydantic import Field, field_validator, model_validator

from backend.ask.orchestration.contracts import (
    ORCHESTRATION_POLICY_VERSION,
    CapabilityTerminalState,
    ContractModel,
    OrchestratorCapability,
)
from backend.ask.orchestration.latency import LatencyBudget
from backend.ask.orchestration.scheduler import (
    CapabilityBinding,
    CapabilityRequestFactory,
    SchedulerConfig,
    SchedulerNodeOutcome,
    SchedulerReport,
    execute_ready_phase,
)
from backend.ask.orchestration.state_machine import (
    OrchestrationPhase,
    OrchestrationState,
    RunTerminalState,
)
from backend.core.logging import log_event

SHADOW_ORCHESTRATION_SCHEMA_VERSION = "1"
SHADOW_ORCHESTRATION_POLICY_VERSION = "ask-ai-orchestrator-shadow-v1"
SHADOW_ORCHESTRATION_UNAVAILABLE = "ORCHESTRATION_SHADOW_UNAVAILABLE"


class ShadowOrchestrationOutcome(StrEnum):
    AGREEMENT = "agreement"
    DISAGREEMENT = "disagreement"
    UNAVAILABLE = "unavailable"


class ShadowOrchestrationExpectation(ContractModel):
    schema_version: Literal["1"] = SHADOW_ORCHESTRATION_SCHEMA_VERSION
    fixture_id: str = Field(
        min_length=1,
        max_length=100,
        pattern=r"^[a-z0-9][a-z0-9._:-]*$",
    )
    initial_phase: OrchestrationPhase
    expected_final_phase: OrchestrationPhase
    expected_terminal_state: RunTerminalState | None = None
    expected_node_outcomes: tuple[SchedulerNodeOutcome, ...] = ()

    @model_validator(mode="after")
    def validate_expected_nodes(self) -> Self:
        node_ids = tuple(
            outcome.node_id for outcome in self.expected_node_outcomes
        )
        if len(node_ids) != len(set(node_ids)):
            raise ValueError("Expected shadow node IDs must be unique")
        return self


class ShadowOrchestrationComparison(ContractModel):
    schema_version: Literal["1"] = SHADOW_ORCHESTRATION_SCHEMA_VERSION
    policy_version: str = Field(
        default=SHADOW_ORCHESTRATION_POLICY_VERSION,
        min_length=1,
    )
    orchestration_policy_version: str = Field(min_length=1)
    fixture_id: str = Field(
        min_length=1,
        max_length=100,
        pattern=r"^[a-z0-9][a-z0-9._:-]*$",
    )
    outcome: ShadowOrchestrationOutcome
    initial_phase: OrchestrationPhase
    expected_final_phase: OrchestrationPhase
    actual_final_phase: OrchestrationPhase | None = None
    expected_terminal_state: RunTerminalState | None = None
    actual_terminal_state: RunTerminalState | None = None
    expected_node_outcomes: tuple[SchedulerNodeOutcome, ...] = ()
    actual_node_outcomes: tuple[SchedulerNodeOutcome, ...] = ()
    duration_ms: int = Field(ge=0)
    safe_error_code: str | None = Field(
        default=None,
        pattern=r"^[A-Z][A-Z0-9_]{0,99}$",
    )

    @field_validator("expected_node_outcomes", "actual_node_outcomes")
    @classmethod
    def validate_unique_node_ids(
        cls,
        value: tuple[SchedulerNodeOutcome, ...],
    ) -> tuple[SchedulerNodeOutcome, ...]:
        node_ids = tuple(outcome.node_id for outcome in value)
        if len(node_ids) != len(set(node_ids)):
            raise ValueError("Shadow comparison node IDs must be unique")
        return value

    @model_validator(mode="after")
    def validate_outcome(self) -> Self:
        unavailable = self.outcome is ShadowOrchestrationOutcome.UNAVAILABLE
        if unavailable != (self.safe_error_code is not None):
            raise ValueError(
                "Only unavailable shadow comparisons have an error code"
            )
        if unavailable:
            if (
                self.actual_final_phase is not None
                or self.actual_terminal_state is not None
                or self.actual_node_outcomes
            ):
                raise ValueError(
                    "Unavailable shadow comparisons have no actual result"
                )
            return self

        if self.actual_final_phase is None:
            raise ValueError(
                "Completed shadow comparisons require a final phase"
            )
        agrees = (
            self.actual_final_phase is self.expected_final_phase
            and self.actual_terminal_state is self.expected_terminal_state
            and self.actual_node_outcomes == self.expected_node_outcomes
        )
        if agrees != (
            self.outcome is ShadowOrchestrationOutcome.AGREEMENT
        ):
            raise ValueError(
                "Shadow comparison outcome does not match actual execution"
            )
        return self


class ShadowOrchestrationExecution(ContractModel):
    comparison: ShadowOrchestrationComparison
    report: SchedulerReport | None = None

    @model_validator(mode="after")
    def validate_execution(self) -> Self:
        unavailable = (
            self.comparison.outcome
            is ShadowOrchestrationOutcome.UNAVAILABLE
        )
        if unavailable != (self.report is None):
            raise ValueError(
                "Shadow report availability must match comparison outcome"
            )
        return self


class ShadowOrchestrationEvaluator(Protocol):
    async def evaluate(self, state: OrchestrationState) -> SchedulerReport: ...


class ShadowOrchestrationRecorder(Protocol):
    def record(self, comparison: ShadowOrchestrationComparison) -> None: ...


class SchedulerShadowOrchestrationEvaluator:
    def __init__(
        self,
        *,
        request_factory: CapabilityRequestFactory,
        bindings: Mapping[OrchestratorCapability, CapabilityBinding],
        config: SchedulerConfig | None = None,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        budget: LatencyBudget | None = None,
    ) -> None:
        self._request_factory = request_factory
        self._bindings = dict(bindings)
        self._config = config
        self._clock = clock
        self._budget = budget

    async def evaluate(self, state: OrchestrationState) -> SchedulerReport:
        return await execute_ready_phase(
            state,
            request_factory=self._request_factory,
            bindings=self._bindings,
            config=self._config,
            clock=self._clock,
            budget=self._budget,
        )


class LoggingShadowOrchestrationRecorder:
    def __init__(self, *, correlation_id: str) -> None:
        self._correlation_id = correlation_id

    def record(self, comparison: ShadowOrchestrationComparison) -> None:
        log_event(
            "ask_orchestration_shadow",
            correlation_id=self._correlation_id,
            schema_version=comparison.schema_version,
            policy_version=comparison.policy_version,
            orchestration_policy_version=(
                comparison.orchestration_policy_version
            ),
            outcome=comparison.outcome.value,
            initial_phase=comparison.initial_phase.value,
            expected_final_phase=comparison.expected_final_phase.value,
            actual_final_phase=(
                comparison.actual_final_phase.value
                if comparison.actual_final_phase is not None
                else None
            ),
            expected_terminal_state=(
                comparison.expected_terminal_state.value
                if comparison.expected_terminal_state is not None
                else None
            ),
            actual_terminal_state=(
                comparison.actual_terminal_state.value
                if comparison.actual_terminal_state is not None
                else None
            ),
            expected_outcome_counts=_outcome_counts(
                comparison.expected_node_outcomes
            ),
            actual_outcome_counts=_outcome_counts(
                comparison.actual_node_outcomes
            ),
            duration_ms=comparison.duration_ms,
            safe_error_code=comparison.safe_error_code,
        )


class OrchestrationShadowService:
    def __init__(
        self,
        *,
        evaluator: ShadowOrchestrationEvaluator,
        recorder: ShadowOrchestrationRecorder | None = None,
        monotonic: Callable[[], float] = time.perf_counter,
    ) -> None:
        self._evaluator = evaluator
        self._recorder = recorder
        self._monotonic = monotonic

    async def execute_and_record(
        self,
        *,
        state: OrchestrationState,
        expectation: ShadowOrchestrationExpectation,
        kill_switch_enabled: bool,
    ) -> ShadowOrchestrationExecution | None:
        if kill_switch_enabled is not True:
            return None

        orchestration_policy_version = ORCHESTRATION_POLICY_VERSION
        fixture_id = "unavailable"
        initial_phase = OrchestrationPhase.REQUEST_SCOPE
        expected_final_phase = OrchestrationPhase.REQUEST_SCOPE
        expected_terminal_state: RunTerminalState | None = None
        expected_node_outcomes: tuple[SchedulerNodeOutcome, ...] = ()
        started = self._monotonic()
        try:
            safe_expectation = ShadowOrchestrationExpectation.model_validate(
                expectation.model_dump(mode="python")
            )
            fixture_id = safe_expectation.fixture_id
            initial_phase = safe_expectation.initial_phase
            expected_final_phase = safe_expectation.expected_final_phase
            expected_terminal_state = (
                safe_expectation.expected_terminal_state
            )
            expected_node_outcomes = (
                safe_expectation.expected_node_outcomes
            )
            safe_state = OrchestrationState.model_validate(
                state.model_dump(mode="python")
            )
            orchestration_policy_version = safe_state.policy_version
            if safe_state.phase is not safe_expectation.initial_phase:
                raise ValueError(
                    "Shadow expectation does not match the initial phase"
                )
            report = await self._evaluator.evaluate(safe_state)
            safe_report = SchedulerReport.model_validate(
                report.model_dump(mode="python")
            )
            actual_outcomes = tuple(
                outcome
                for wave in safe_report.waves
                for outcome in wave.outcomes
            )
            agrees = (
                safe_report.state.phase
                is safe_expectation.expected_final_phase
                and safe_report.state.terminal_state
                is safe_expectation.expected_terminal_state
                and actual_outcomes
                == safe_expectation.expected_node_outcomes
            )
            comparison = ShadowOrchestrationComparison(
                orchestration_policy_version=safe_state.policy_version,
                fixture_id=safe_expectation.fixture_id,
                outcome=(
                    ShadowOrchestrationOutcome.AGREEMENT
                    if agrees
                    else ShadowOrchestrationOutcome.DISAGREEMENT
                ),
                initial_phase=safe_expectation.initial_phase,
                expected_final_phase=safe_expectation.expected_final_phase,
                actual_final_phase=safe_report.state.phase,
                expected_terminal_state=(
                    safe_expectation.expected_terminal_state
                ),
                actual_terminal_state=safe_report.state.terminal_state,
                expected_node_outcomes=(
                    safe_expectation.expected_node_outcomes
                ),
                actual_node_outcomes=actual_outcomes,
                duration_ms=_duration_ms(started, self._monotonic()),
            )
            execution = ShadowOrchestrationExecution(
                comparison=comparison,
                report=safe_report,
            )
        except Exception:
            comparison = ShadowOrchestrationComparison(
                orchestration_policy_version=orchestration_policy_version,
                fixture_id=fixture_id,
                outcome=ShadowOrchestrationOutcome.UNAVAILABLE,
                initial_phase=initial_phase,
                expected_final_phase=expected_final_phase,
                expected_terminal_state=expected_terminal_state,
                expected_node_outcomes=expected_node_outcomes,
                duration_ms=_duration_ms(started, self._monotonic()),
                safe_error_code=SHADOW_ORCHESTRATION_UNAVAILABLE,
            )
            execution = ShadowOrchestrationExecution(
                comparison=comparison,
            )

        if self._recorder is not None:
            try:
                self._recorder.record(execution.comparison)
            except Exception:
                pass
        return execution


def shadow_orchestration_comparison_json(
    comparison: ShadowOrchestrationComparison,
) -> str:
    return json.dumps(
        comparison.model_dump(mode="json"),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def _outcome_counts(
    outcomes: tuple[SchedulerNodeOutcome, ...],
) -> dict[str, int]:
    counts = Counter(outcome.terminal_state.value for outcome in outcomes)
    return {
        terminal_state.value: counts.get(terminal_state.value, 0)
        for terminal_state in CapabilityTerminalState
    }


def _duration_ms(started: float, finished: float) -> int:
    return max(0, int((finished - started) * 1000))
