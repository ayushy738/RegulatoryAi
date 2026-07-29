from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass

import pytest
from pydantic import ValidationError

from backend.ask.decision import PlanClass
from backend.ask.orchestration import (
    FROZEN_LATENCY_PROFILES,
    OPTIONAL_WORK_STOP_ORDER,
    BudgetCheckpoint,
    BudgetStopReason,
    CapabilityBinding,
    CapabilityInvocation,
    CapabilityTerminalState,
    ExecutionMode,
    LatencyBudget,
    LatencyBudgetError,
    LatencyProfile,
    LatencyProfileName,
    OptionalWorkClass,
    OrchestratorCapability,
    ParticipationClass,
    ProvenanceClass,
    SectionNode,
    SectionTerminalState,
    SectionWorkState,
    apply_hard_cutoff_to_sections,
    budget_checkpoint_json,
    execute_ready_phase,
    latency_budget_for_plan,
    latency_profile_for_plan_class,
    latency_profile_json,
)
from backend.tests.test_ask_ai_orchestration_scheduler import (
    _fanout_state,
    _NodeSpec,
    _RequestFactory,
    _success_result,
)

EXPECTED_PROFILES = {
    LatencyProfileName.FAST_EXACT: (1_000, 3_500, 5_000, 7_000, 1_050),
    LatencyProfileName.FOCUSED_GROUNDED: (
        1_500,
        7_000,
        10_000,
        14_000,
        2_100,
    ),
    LatencyProfileName.LIVE_COMBINED: (
        1_500,
        8_000,
        12_000,
        16_000,
        2_400,
    ),
    LatencyProfileName.DEEP_STRUCTURED: (
        2_000,
        12_000,
        18_000,
        25_000,
        3_750,
    ),
    LatencyProfileName.COMPOSITE_RESEARCH: (
        2_000,
        15_000,
        22_000,
        30_000,
        4_500,
    ),
}


@dataclass
class _FakeClock:
    value: float = 0

    def __call__(self) -> float:
        return self.value


class _RecordingExecutor:
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def execute(
        self,
        invocation: CapabilityInvocation,
    ):
        self.calls.append(invocation.node.node_id)
        return _success_result(invocation)


class _AdvancingExecutor:
    def __init__(self, clock: _FakeClock, completed_at: float) -> None:
        self.clock = clock
        self.completed_at = completed_at
        self.calls = 0

    async def execute(
        self,
        invocation: CapabilityInvocation,
    ):
        self.calls += 1
        self.clock.value = self.completed_at
        return _success_result(invocation)


class _SlowExecutor:
    async def execute(
        self,
        invocation: CapabilityInvocation,
    ):
        await asyncio.sleep(0.1)
        return _success_result(invocation)


def test_frozen_profiles_and_decision_mapping_match_every_exact_boundary() -> None:
    assert set(FROZEN_LATENCY_PROFILES) == set(LatencyProfileName)
    for name, expected in EXPECTED_PROFILES.items():
        profile = FROZEN_LATENCY_PROFILES[name]
        assert (
            profile.first_result_target_ms,
            profile.core_result_target_ms,
            profile.soft_cutoff_ms,
            profile.hard_cutoff_ms,
            profile.verification_reserve_ms,
        ) == expected
        assert profile.optional_stop_order == OPTIONAL_WORK_STOP_ORDER
        assert profile.optional_admission_deadline_ms <= (
            profile.verification_reserve_starts_at_ms
        )
        assert latency_profile_json(profile) == latency_profile_json(
            LatencyProfile.model_validate_json(latency_profile_json(profile))
        )

    assert {
        plan_class: latency_profile_for_plan_class(plan_class).name
        for plan_class in PlanClass
    } == {
        PlanClass.FAST_EXACT: LatencyProfileName.FAST_EXACT,
        PlanClass.FOCUSED_GROUNDED: LatencyProfileName.FOCUSED_GROUNDED,
        PlanClass.LIVE_COMBINED: LatencyProfileName.LIVE_COMBINED,
        PlanClass.DEEP_RESEARCH: LatencyProfileName.DEEP_STRUCTURED,
        PlanClass.COMPOSITE: LatencyProfileName.COMPOSITE_RESEARCH,
    }


def test_profile_contract_rejects_inverted_or_borrowed_verification_time() -> None:
    values = FROZEN_LATENCY_PROFILES[
        LatencyProfileName.FAST_EXACT
    ].model_dump(mode="python")
    values["core_result_target_ms"] = 500
    with pytest.raises(ValidationError, match="monotonic"):
        LatencyProfile.model_validate(values)

    values = FROZEN_LATENCY_PROFILES[
        LatencyProfileName.FAST_EXACT
    ].model_dump(mode="python")
    values["verification_reserve_ms"] = 2_500
    with pytest.raises(ValidationError, match="cannot borrow"):
        LatencyProfile.model_validate(values)


@pytest.mark.parametrize("profile_name", tuple(LatencyProfileName))
def test_fake_clock_checkpoints_enforce_soft_hard_and_reserved_boundaries(
    profile_name: LatencyProfileName,
) -> None:
    profile = FROZEN_LATENCY_PROFILES[profile_name]
    clock = _FakeClock()
    budget = LatencyBudget(profile=profile, started_at=0, clock=clock)

    clock.value = profile.soft_cutoff_ms / 1_000
    soft = budget.checkpoint()
    assert soft.soft_cutoff_reached
    assert not soft.optional_admission_open
    assert budget.stop_reason(ParticipationClass.OPTIONAL) is (
        BudgetStopReason.OPTIONAL_CUTOFF
    )
    assert budget.stop_reason(ParticipationClass.SUPPORTING) is (
        BudgetStopReason.SOFT_CUTOFF
    )
    assert budget.stop_reason(ParticipationClass.MANDATORY) is None

    clock.value = profile.verification_reserve_starts_at_ms / 1_000
    reserved = budget.checkpoint()
    assert reserved.verification_reserve_active
    assert reserved.hard_remaining_ms == profile.verification_reserve_ms
    assert budget.stop_reason(ParticipationClass.MANDATORY) is None
    assert (
        budget.stop_reason(
            ParticipationClass.SUPPORTING,
            OrchestratorCapability.CITATION_VERIFIER,
        )
        is None
    )
    assert budget.remaining_execution_seconds(
        ParticipationClass.SUPPORTING,
        OrchestratorCapability.CITATION_VERIFIER,
    ) == pytest.approx(profile.verification_reserve_ms / 1_000)

    clock.value = profile.hard_cutoff_ms / 1_000
    hard = budget.checkpoint()
    assert hard.hard_cutoff_reached
    assert hard.hard_remaining_ms == 0
    assert budget.stop_reason(ParticipationClass.MANDATORY) is (
        BudgetStopReason.HARD_CUTOFF
    )
    assert budget_checkpoint_json(hard) == budget_checkpoint_json(
        BudgetCheckpoint.model_validate_json(budget_checkpoint_json(hard))
    )


def test_optional_stopping_order_is_complete_and_exact() -> None:
    assert OPTIONAL_WORK_STOP_ORDER == (
        OptionalWorkClass.FOLLOW_UPS,
        OptionalWorkClass.RELATED_ENTITY_EXPANSION,
        OptionalWorkClass.NON_PRIMARY_NEWS,
        OptionalWorkClass.TIMELINE_ENRICHMENT,
        OptionalWorkClass.REPLACEABLE_GRAPH_ENRICHMENT,
        OptionalWorkClass.NARRATIVE_POLISH,
        OptionalWorkClass.SURPLUS_EVIDENCE,
    )


def test_soft_cutoff_cancels_optional_without_blocking_required_work() -> None:
    entity = OrchestratorCapability.ENTITY_RESOLVER.value
    state = _fanout_state(
        (
            _NodeSpec(
                node_id="regulatory:required",
                capability=OrchestratorCapability.REGULATORY_RETRIEVER,
                section_key="official",
                provenance_class=(
                    ProvenanceClass.INTERNAL_REGULATORY_CORPUS
                ),
                dependencies=(entity,),
                participation=ParticipationClass.MANDATORY,
            ),
            _NodeSpec(
                node_id="graph:supporting",
                capability=OrchestratorCapability.KNOWLEDGE_GRAPH,
                section_key="official",
                provenance_class=(
                    ProvenanceClass.INTERNAL_REGULATORY_CORPUS
                ),
                dependencies=(entity,),
            ),
            _NodeSpec(
                node_id="news:optional",
                capability=OrchestratorCapability.NEWS_RETRIEVER,
                section_key="live",
                provenance_class=ProvenanceClass.LIVE_WEB_SOURCES,
                dependencies=(entity,),
                participation=ParticipationClass.OPTIONAL,
            ),
        )
    )
    clock = _FakeClock(value=10)
    budget = latency_budget_for_plan(
        state.approved_plan,
        clock=clock,
        started_at=0,
    )
    executor = _RecordingExecutor()
    binding = CapabilityBinding(ExecutionMode.ASYNC, executor)

    report = asyncio.run(
        execute_ready_phase(
            state,
            request_factory=_RequestFactory(),
            bindings={
                OrchestratorCapability.REGULATORY_RETRIEVER: binding,
                OrchestratorCapability.KNOWLEDGE_GRAPH: binding,
                OrchestratorCapability.NEWS_RETRIEVER: binding,
            },
            budget=budget,
        )
    )

    outcomes = {
        outcome.node_id: outcome for outcome in report.waves[0].outcomes
    }
    assert executor.calls == ["regulatory:required"]
    assert outcomes["regulatory:required"].terminal_state is (
        CapabilityTerminalState.SATISFIED
    )
    assert outcomes["news:optional"].terminal_state is (
        CapabilityTerminalState.CANCELLED
    )
    assert outcomes["news:optional"].safe_error_code is None
    assert outcomes["graph:supporting"].terminal_state is (
        CapabilityTerminalState.TIMED_OUT
    )
    assert outcomes["graph:supporting"].safe_error_code == (
        "CAPABILITY_SOFT_CUTOFF"
    )


def test_fake_clock_late_result_is_withheld_and_terminalized_as_timeout() -> None:
    entity = OrchestratorCapability.ENTITY_RESOLVER.value
    state = _fanout_state(
        (
            _NodeSpec(
                node_id="regulatory:official",
                capability=OrchestratorCapability.REGULATORY_RETRIEVER,
                section_key="official",
                provenance_class=(
                    ProvenanceClass.INTERNAL_REGULATORY_CORPUS
                ),
                dependencies=(entity,),
            ),
        )
    )
    clock = _FakeClock()
    executor = _AdvancingExecutor(clock, completed_at=7)
    budget = LatencyBudget(
        profile=FROZEN_LATENCY_PROFILES[LatencyProfileName.FAST_EXACT],
        started_at=0,
        clock=clock,
    )

    report = asyncio.run(
        execute_ready_phase(
            state,
            request_factory=_RequestFactory(),
            bindings={
                OrchestratorCapability.REGULATORY_RETRIEVER: (
                    CapabilityBinding(ExecutionMode.ASYNC, executor)
                )
            },
            budget=budget,
        )
    )

    outcome = report.waves[0].outcomes[0]
    assert executor.calls == 1
    assert outcome.terminal_state is CapabilityTerminalState.TIMED_OUT
    assert outcome.safe_error_code == "CAPABILITY_HARD_CUTOFF"
    node = next(
        item
        for item in report.state.capabilities
        if item.node_id == "regulatory:official"
    )
    assert node.result is not None
    assert not node.result.artifacts


def test_real_deadline_interrupts_async_work_at_the_hard_cutoff() -> None:
    entity = OrchestratorCapability.ENTITY_RESOLVER.value
    state = _fanout_state(
        (
            _NodeSpec(
                node_id="regulatory:official",
                capability=OrchestratorCapability.REGULATORY_RETRIEVER,
                section_key="official",
                provenance_class=(
                    ProvenanceClass.INTERNAL_REGULATORY_CORPUS
                ),
                dependencies=(entity,),
            ),
        )
    )
    profile = FROZEN_LATENCY_PROFILES[LatencyProfileName.FAST_EXACT]
    budget = LatencyBudget(
        profile=profile,
        started_at=time.perf_counter()
        - ((profile.hard_cutoff_ms - 25) / 1_000),
    )

    started = time.perf_counter()
    report = asyncio.run(
        execute_ready_phase(
            state,
            request_factory=_RequestFactory(),
            bindings={
                OrchestratorCapability.REGULATORY_RETRIEVER: (
                    CapabilityBinding(ExecutionMode.ASYNC, _SlowExecutor())
                )
            },
            budget=budget,
        )
    )

    assert time.perf_counter() - started < 0.09
    assert report.waves[0].outcomes[0].terminal_state is (
        CapabilityTerminalState.TIMED_OUT
    )


def test_hard_cutoff_degrades_sections_and_withholds_unverified_claims() -> None:
    entity = OrchestratorCapability.ENTITY_RESOLVER.value
    state = _fanout_state(
        (
            _NodeSpec(
                node_id="regulatory:official",
                capability=OrchestratorCapability.REGULATORY_RETRIEVER,
                section_key="official",
                provenance_class=(
                    ProvenanceClass.INTERNAL_REGULATORY_CORPUS
                ),
                dependencies=(entity,),
            ),
            _NodeSpec(
                node_id="news:optional",
                capability=OrchestratorCapability.NEWS_RETRIEVER,
                section_key="live",
                provenance_class=ProvenanceClass.LIVE_WEB_SOURCES,
                dependencies=(entity,),
            ),
        )
    )
    required = state.sections[0]
    values = state.model_dump(mode="python")
    values["sections"] = (
        SectionNode(
            **required.model_dump(
                mode="python",
                exclude={
                    "state",
                    "material_claim_ids",
                    "terminal_verification_claim_ids",
                },
            ),
            state=SectionWorkState.VERIFYING,
            material_claim_ids=("claim-verified", "claim-unverified"),
            terminal_verification_claim_ids=("claim-verified",),
        ),
        state.sections[1],
    )
    state = type(state).model_validate(values)
    clock = _FakeClock(value=14)
    budget = LatencyBudget(
        profile=FROZEN_LATENCY_PROFILES[
            LatencyProfileName.FOCUSED_GROUNDED
        ],
        started_at=0,
        clock=clock,
    )
    admitted_before = state.admitted_artifacts

    terminalized = apply_hard_cutoff_to_sections(state, budget)

    assert terminalized.sections[0].state is SectionTerminalState.DEGRADED
    assert terminalized.sections[0].material_claim_ids == ("claim-verified",)
    assert terminalized.sections[1].state is SectionTerminalState.OMITTED
    assert terminalized.admitted_artifacts == admitted_before

    clock.value = 13.999
    with pytest.raises(LatencyBudgetError, match="hard boundary"):
        apply_hard_cutoff_to_sections(state, budget)
