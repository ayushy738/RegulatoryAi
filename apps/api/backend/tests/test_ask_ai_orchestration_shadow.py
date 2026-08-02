from __future__ import annotations

import asyncio
from typing import Any

import pytest
from pydantic import ValidationError

from backend.ask.orchestration import (
    SHADOW_ORCHESTRATION_UNAVAILABLE,
    CapabilityBinding,
    CapabilityTerminalState,
    ExecutionMode,
    LoggingShadowOrchestrationRecorder,
    OrchestrationPhase,
    OrchestrationShadowService,
    SchedulerNodeOutcome,
    SchedulerShadowOrchestrationEvaluator,
    ShadowOrchestrationComparison,
    ShadowOrchestrationExpectation,
    ShadowOrchestrationOutcome,
    shadow_orchestration_comparison_json,
)
from backend.ask.orchestration import shadow as shadow_module
from backend.tests.test_ask_ai_orchestration_scheduler import (
    _AsyncExecutor,
    _fanout_state,
    _RequestFactory,
    _three_branch_specs,
)


def _expected_outcomes(
    terminal_state: CapabilityTerminalState = (
        CapabilityTerminalState.SATISFIED
    ),
    safe_error_code: str | None = None,
) -> tuple[SchedulerNodeOutcome, ...]:
    return tuple(
        SchedulerNodeOutcome(
            node_id=spec.node_id,
            capability=spec.capability,
            terminal_state=terminal_state,
            safe_error_code=safe_error_code,
        )
        for spec in _three_branch_specs()
    )


def _expectation(
    *,
    outcomes: tuple[SchedulerNodeOutcome, ...] | None = None,
) -> ShadowOrchestrationExpectation:
    state = _fanout_state(_three_branch_specs())
    return ShadowOrchestrationExpectation(
        fixture_id="e4.7-three-branch",
        initial_phase=state.phase,
        expected_final_phase=state.phase,
        expected_node_outcomes=outcomes or _expected_outcomes(),
    )


def _scheduler_evaluator() -> SchedulerShadowOrchestrationEvaluator:
    executor = _AsyncExecutor(delay=0)
    binding = CapabilityBinding(ExecutionMode.ASYNC, executor)
    return SchedulerShadowOrchestrationEvaluator(
        request_factory=_RequestFactory(),
        bindings={
            spec.capability: binding for spec in _three_branch_specs()
        },
    )


def test_selected_fixture_executes_real_scheduler_and_records_agreement() -> None:
    state = _fanout_state(_three_branch_specs())
    original = state.model_dump(mode="json")
    recorded: list[ShadowOrchestrationComparison] = []
    recorder = type(
        "Recorder",
        (),
        {"record": lambda self, comparison: recorded.append(comparison)},
    )()
    service = OrchestrationShadowService(
        evaluator=_scheduler_evaluator(),
        recorder=recorder,
        monotonic=iter((1.0, 1.010)).__next__,
    )

    execution = asyncio.run(
        service.execute_and_record(
            state=state,
            expectation=_expectation(),
            kill_switch_enabled=True,
        )
    )

    assert execution is not None
    assert execution.report is not None
    assert execution.comparison.outcome is ShadowOrchestrationOutcome.AGREEMENT
    assert execution.comparison.duration_ms == 10
    assert execution.comparison.actual_node_outcomes == _expected_outcomes()
    assert recorded == [execution.comparison]
    assert state.model_dump(mode="json") == original
    serialized = shadow_orchestration_comparison_json(
        execution.comparison
    )
    assert serialized == shadow_orchestration_comparison_json(
        ShadowOrchestrationComparison.model_validate_json(serialized)
    )


def test_valid_execution_records_exact_disagreement_without_serving_effect() -> None:
    state = _fanout_state(_three_branch_specs())
    expectation = _expectation(
        outcomes=_expected_outcomes(
            CapabilityTerminalState.TIMED_OUT,
            "CAPABILITY_TIMED_OUT",
        )
    )
    service = OrchestrationShadowService(
        evaluator=_scheduler_evaluator(),
    )

    execution = asyncio.run(
        service.execute_and_record(
            state=state,
            expectation=expectation,
            kill_switch_enabled=True,
        )
    )

    assert execution is not None
    assert execution.report is not None
    assert execution.comparison.outcome is (
        ShadowOrchestrationOutcome.DISAGREEMENT
    )
    assert execution.comparison.expected_node_outcomes == (
        expectation.expected_node_outcomes
    )
    assert execution.comparison.actual_node_outcomes == _expected_outcomes()


def test_kill_switch_performs_zero_validation_execution_timing_or_recording() -> None:
    calls: list[str] = []

    class Evaluator:
        async def evaluate(self, state: Any) -> Any:
            calls.append("evaluate")
            raise AssertionError(state)

    class Recorder:
        def record(self, comparison: Any) -> None:
            calls.append("record")
            raise AssertionError(comparison)

    service = OrchestrationShadowService(
        evaluator=Evaluator(),
        recorder=Recorder(),
        monotonic=lambda: calls.append("clock") or 0.0,
    )

    result = asyncio.run(
        service.execute_and_record(
            state=_fanout_state(_three_branch_specs()),
            expectation=_expectation(),
            kill_switch_enabled=False,
        )
    )

    assert result is None
    assert calls == []

    fail_closed_result = asyncio.run(
        service.execute_and_record(
            state=_fanout_state(_three_branch_specs()),
            expectation=_expectation(),
            kill_switch_enabled="true",  # type: ignore[arg-type]
        )
    )
    assert fail_closed_result is None
    assert calls == []


@pytest.mark.parametrize("malformed", [None, {}, object()])
def test_evaluator_failure_or_malformed_output_fails_closed(
    malformed: object,
) -> None:
    class Evaluator:
        async def evaluate(self, state: Any) -> Any:
            if malformed is None:
                raise RuntimeError("secret provider credential")
            return malformed

    service = OrchestrationShadowService(evaluator=Evaluator())

    execution = asyncio.run(
        service.execute_and_record(
            state=_fanout_state(_three_branch_specs()),
            expectation=_expectation(),
            kill_switch_enabled=True,
        )
    )

    assert execution is not None
    assert execution.report is None
    assert execution.comparison.outcome is (
        ShadowOrchestrationOutcome.UNAVAILABLE
    )
    assert execution.comparison.safe_error_code == (
        SHADOW_ORCHESTRATION_UNAVAILABLE
    )
    assert "secret" not in execution.model_dump_json()


def test_recorder_failure_cannot_change_a_completed_shadow_result() -> None:
    class Recorder:
        def record(self, comparison: Any) -> None:
            raise RuntimeError(f"telemetry down: {comparison.fixture_id}")

    service = OrchestrationShadowService(
        evaluator=_scheduler_evaluator(),
        recorder=Recorder(),
    )

    execution = asyncio.run(
        service.execute_and_record(
            state=_fanout_state(_three_branch_specs()),
            expectation=_expectation(),
            kill_switch_enabled=True,
        )
    )

    assert execution is not None
    assert execution.comparison.outcome is ShadowOrchestrationOutcome.AGREEMENT


def test_initial_phase_mismatch_is_unavailable_without_invoking_evaluator() -> None:
    calls: list[str] = []

    class Evaluator:
        async def evaluate(self, state: Any) -> Any:
            calls.append(state.phase.value)
            raise AssertionError

    expectation = _expectation().model_copy(
        update={"initial_phase": OrchestrationPhase.REQUEST_SCOPE}
    )
    service = OrchestrationShadowService(evaluator=Evaluator())

    execution = asyncio.run(
        service.execute_and_record(
            state=_fanout_state(_three_branch_specs()),
            expectation=expectation,
            kill_switch_enabled=True,
        )
    )

    assert execution is not None
    assert execution.comparison.outcome is (
        ShadowOrchestrationOutcome.UNAVAILABLE
    )
    assert calls == []


def test_forged_copied_inputs_cannot_escape_failure_isolation() -> None:
    state = _fanout_state(_three_branch_specs()).model_copy(
        update={"policy_version": ""}
    )
    expectation = _expectation().model_copy(
        update={"fixture_id": "query content must not escape"}
    )
    service = OrchestrationShadowService(evaluator=_scheduler_evaluator())

    execution = asyncio.run(
        service.execute_and_record(
            state=state,
            expectation=expectation,
            kill_switch_enabled=True,
        )
    )

    assert execution is not None
    assert execution.report is None
    assert execution.comparison.fixture_id == "unavailable"
    assert execution.comparison.orchestration_policy_version == (
        "ask-ai-orchestrator-v1"
    )
    assert execution.comparison.safe_error_code == (
        SHADOW_ORCHESTRATION_UNAVAILABLE
    )


def test_task_cancellation_is_not_hidden_as_shadow_unavailability() -> None:
    class Evaluator:
        async def evaluate(self, state: Any) -> Any:
            raise asyncio.CancelledError

    async def invoke() -> None:
        service = OrchestrationShadowService(evaluator=Evaluator())
        await service.execute_and_record(
            state=_fanout_state(_three_branch_specs()),
            expectation=_expectation(),
            kill_switch_enabled=True,
        )

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(invoke())


def test_logging_recorder_emits_only_content_free_fixed_aggregates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[tuple[str, dict[str, Any]]] = []
    monkeypatch.setattr(
        shadow_module,
        "log_event",
        lambda event, **fields: events.append((event, fields)),
    )
    comparison = ShadowOrchestrationComparison(
        orchestration_policy_version="ask-ai-orchestrator-v1",
        fixture_id="contains-private-fixture-name",
        outcome=ShadowOrchestrationOutcome.AGREEMENT,
        initial_phase="evidence_fan_out",
        expected_final_phase="evidence_fan_out",
        actual_final_phase="evidence_fan_out",
        expected_node_outcomes=_expected_outcomes(),
        actual_node_outcomes=_expected_outcomes(),
        duration_ms=3,
    )

    LoggingShadowOrchestrationRecorder(
        correlation_id="correlation-1"
    ).record(comparison)

    assert events[0][0] == "ask_orchestration_shadow"
    fields = events[0][1]
    assert "fixture_id" not in fields
    assert "node_id" not in json_text(fields)
    assert "query" not in json_text(fields)
    assert fields["expected_outcome_counts"]["satisfied"] == 3
    assert fields["actual_outcome_counts"]["satisfied"] == 3


def json_text(value: object) -> str:
    return str(value).casefold()


def test_expectation_and_comparison_contracts_are_strict_and_immutable() -> None:
    expectation = _expectation()

    with pytest.raises(ValidationError):
        ShadowOrchestrationExpectation.model_validate(
            {**expectation.model_dump(mode="python"), "unknown": True}
        )
    with pytest.raises(ValidationError, match="unique"):
        ShadowOrchestrationExpectation(
            fixture_id="duplicate",
            initial_phase=expectation.initial_phase,
            expected_final_phase=expectation.expected_final_phase,
            expected_node_outcomes=(
                expectation.expected_node_outcomes[0],
                expectation.expected_node_outcomes[0],
            ),
        )
    with pytest.raises(ValidationError, match="outcome"):
        ShadowOrchestrationComparison(
            orchestration_policy_version="ask-ai-orchestrator-v1",
            fixture_id="wrong-outcome",
            outcome=ShadowOrchestrationOutcome.AGREEMENT,
            initial_phase=expectation.initial_phase,
            expected_final_phase=expectation.expected_final_phase,
            actual_final_phase=expectation.expected_final_phase,
            expected_node_outcomes=expectation.expected_node_outcomes,
            actual_node_outcomes=(),
            duration_ms=1,
        )
    with pytest.raises(ValidationError):
        expectation.fixture_id = "changed"  # type: ignore[misc]
