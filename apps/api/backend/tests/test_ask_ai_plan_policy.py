from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from backend.ask.decision import (
    CAPABILITY_STAGES,
    DECISION_POLICY_VERSION,
    INTENT_CAPABILITY_ROLES,
    INTENT_RESPONSE_STRATEGY,
    PLANNING_STAGES,
    RESPONSE_BLUEPRINTS,
    CapabilityName,
    CapabilityRole,
    CapabilityStage,
    Intent,
    PlanClass,
    PlannedCapability,
    PlanningStageName,
    PlanQuestion,
    PlanRequest,
    ResponseStrategy,
    select_decision_plan,
)

MATRIX_PATH = Path(__file__).parent / "fixtures" / "ask_decision_plan_matrix.json"


@pytest.fixture(scope="module")
def matrix() -> dict[str, Any]:
    return json.loads(MATRIX_PATH.read_text(encoding="utf-8"))


def test_plan_fixture_is_versioned_and_covers_every_representative_query(
    matrix: dict[str, Any],
) -> None:
    assert matrix["schema_version"] == "1"
    assert matrix["policy_version"] == DECISION_POLICY_VERSION
    assert len(matrix["cases"]) == 19
    assert tuple(PLANNING_STAGES) == (
        PlanningStageName.RESOLVE_CHEAPLY,
        PlanningStageName.RUN_INTENT_EVIDENCE,
        PlanningStageName.ASSESS_SUFFICIENCY,
        PlanningStageName.ACTIVATE_CONDITIONAL_FALLBACKS,
        PlanningStageName.SELECT_RESPONSE_AND_VERIFICATION,
    )


def test_frozen_routing_table_covers_every_atomic_intent_and_capability() -> None:
    assert set(INTENT_CAPABILITY_ROLES) == set(Intent) - {
        Intent.MULTI_PART_QUESTION
    }
    assert all(
        set(roles) == set(CapabilityName)
        for roles in INTENT_CAPABILITY_ROLES.values()
    )
    assert set(CAPABILITY_STAGES) == set(CapabilityName)
    assert set(RESPONSE_BLUEPRINTS) == set(ResponseStrategy)


def test_every_golden_query_selects_exact_plan_roles_and_response(
    matrix: dict[str, Any],
) -> None:
    for case in matrix["cases"]:
        plan = select_decision_plan(
            PlanRequest(
                questions=tuple(
                    PlanQuestion.model_validate(question)
                    for question in case["questions"]
                )
            )
        )
        expected = case["expected"]
        selected = {
            capability.capability.value: capability.role.value
            for capability in plan.capabilities
        }
        skipped = [
            capability.capability.value
            for capability in plan.skipped_capabilities
        ]

        assert plan.plan_class.value == expected["plan_class"], case["query"]
        assert (
            plan.response_strategy.value == expected["response_strategy"]
        ), case["query"]
        assert selected == expected["selected"], case["query"]
        assert skipped == expected["skipped"], case["query"]
        assert plan.clarification_question == expected.get(
            "clarification"
        ), case["query"]
        if "modifiers" in expected:
            assert list(plan.response_blueprint.presentation_modifiers) == expected[
                "modifiers"
            ]


def test_general_ai_never_races_official_grounding() -> None:
    regulatory = select_decision_plan(
        PlanRequest(
            questions=(
                PlanQuestion(
                    question_id="q1",
                    intent=Intent.GENERAL_QUESTION,
                    has_resolved_entity=True,
                    has_term_like_entity=True,
                ),
            )
        )
    )
    general = select_decision_plan(
        PlanRequest(
            questions=(
                PlanQuestion(
                    question_id="q1",
                    intent=Intent.GENERAL_QUESTION,
                ),
            )
        )
    )
    regulatory_ai = _capability(regulatory.capabilities, CapabilityName.GENERAL_AI)
    general_ai = _capability(general.capabilities, CapabilityName.GENERAL_AI)

    assert regulatory_ai.role is CapabilityRole.CONDITIONAL
    assert regulatory_ai.stage is CapabilityStage.CONDITIONAL_FALLBACK
    assert regulatory_ai.activation_conditions == (
        "official_evidence_gate_no_match_or_unavailable",
    )
    assert "general_ai_activation_gate" in regulatory.retrieval_plan.evidence_gates
    assert general_ai.role is CapabilityRole.REQUIRED
    assert general_ai.stage is CapabilityStage.INTENT_EVIDENCE
    assert "general_ai_activation_gate" not in general.retrieval_plan.evidence_gates


def test_live_and_lineage_conditions_fail_closed_when_not_eligible() -> None:
    ordinary = select_decision_plan(
        PlanRequest(
            questions=(
                PlanQuestion(
                    question_id="q1",
                    intent=Intent.COMPARISON,
                    has_resolved_entity=True,
                ),
            )
        )
    )
    current_version = select_decision_plan(
        PlanRequest(
            questions=(
                PlanQuestion(
                    question_id="q1",
                    intent=Intent.COMPARISON,
                    has_resolved_entity=True,
                    live_eligible=True,
                    version_change=True,
                ),
            )
        )
    )

    assert CapabilityName.LIVE_NEWS in {
        item.capability for item in ordinary.skipped_capabilities
    }
    assert CapabilityName.VERSION_LINEAGE in {
        item.capability for item in ordinary.skipped_capabilities
    }
    assert _capability(
        current_version.capabilities,
        CapabilityName.LIVE_NEWS,
    ).role is CapabilityRole.SUPPORTING
    assert _capability(
        current_version.capabilities,
        CapabilityName.VERSION_LINEAGE,
    ).role is CapabilityRole.REQUIRED


def test_multi_part_capabilities_are_deduplicated_with_question_identity(
    matrix: dict[str, Any],
) -> None:
    fixture = next(
        case
        for case in matrix["cases"]
        if case["query"]
        == "Compare DSM and ABT and show the latest consultation"
    )
    plan = select_decision_plan(
        PlanRequest(
            questions=tuple(
                PlanQuestion.model_validate(question)
                for question in fixture["questions"]
            )
        )
    )
    entity = _capability(plan.capabilities, CapabilityName.ENTITY_INDEX)
    live = _capability(plan.capabilities, CapabilityName.LIVE_NEWS)

    assert plan.plan_class is PlanClass.COMPOSITE
    assert plan.response_strategy is ResponseStrategy.RESEARCH_REPORT
    assert entity.question_ids == ("q1", "q2")
    assert live.question_ids == ("q2",)
    assert len(
        [
            capability
            for capability in plan.capabilities
            if capability.capability is CapabilityName.ENTITY_INDEX
        ]
    ) == 1
    assert "per_atomic_question_sufficiency" in plan.retrieval_plan.evidence_gates


def test_stages_and_parallel_groups_obey_dependency_gates() -> None:
    plan = select_decision_plan(
        PlanRequest(
            questions=(
                PlanQuestion(
                    question_id="q1",
                    intent=Intent.NEWS,
                    has_resolved_entity=True,
                    live_eligible=True,
                    version_change=True,
                ),
            )
        )
    )

    assert tuple(stage.name for stage in plan.stages) == PLANNING_STAGES
    assert plan.stages[1].waits_for == (
        PlanningStageName.RESOLVE_CHEAPLY,
    )
    assert plan.stages[3].waits_for == (
        PlanningStageName.ASSESS_SUFFICIENCY,
    )
    evidence_group = plan.retrieval_plan.parallel_groups[-1]
    assert CapabilityName.INTERNAL_DOCUMENT_SEARCH in evidence_group
    assert CapabilityName.LIVE_NEWS in evidence_group
    assert CapabilityName.GENERAL_AI not in evidence_group


def test_missing_document_context_stops_speculative_planning(
    matrix: dict[str, Any],
) -> None:
    fixture = next(
        case for case in matrix["cases"] if case["query"] == "Explain clause 4"
    )
    plan = select_decision_plan(
        PlanRequest(
            questions=tuple(
                PlanQuestion.model_validate(question)
                for question in fixture["questions"]
            )
        )
    )

    assert plan.capabilities == ()
    assert len(plan.skipped_capabilities) == len(CapabilityName)
    assert plan.clarification_question == (
        "Which document or passage should I explain?"
    )
    assert plan.retrieval_plan.parallel_groups == ()


def test_accepted_unavailable_document_fallback_activates_only_general_ai() -> None:
    plan = select_decision_plan(
        PlanRequest(
            questions=(
                PlanQuestion(
                    question_id="q1",
                    intent=Intent.DOCUMENT_EXPLANATION,
                    has_document_target=True,
                    selected_document_available=False,
                    user_accepts_general_fallback=True,
                ),
            )
        )
    )

    assert [
        capability.capability for capability in plan.capabilities
    ] == [CapabilityName.GENERAL_AI]
    assert plan.capabilities[0].role is CapabilityRole.REQUIRED
    assert plan.capabilities[0].stage is CapabilityStage.INTENT_EVIDENCE
    assert plan.clarification_question is None
    assert "general_ai_activation_gate" not in plan.retrieval_plan.evidence_gates


def test_response_blueprints_include_secondary_surfaces_and_modifiers() -> None:
    plan = select_decision_plan(
        PlanRequest(
            questions=(
                PlanQuestion(
                    question_id="q1",
                    intent=Intent.COMPLIANCE_QUESTION,
                    secondary_intents=(Intent.DEADLINE,),
                    has_resolved_entity=True,
                ),
            )
        )
    )

    assert plan.response_blueprint.primary_surface is (
        INTENT_RESPONSE_STRATEGY[Intent.COMPLIANCE_QUESTION]
    )
    assert ResponseStrategy.DEADLINE_CARDS_TIMELINE.value in (
        plan.response_blueprint.supporting_cards
    )
    assert plan.response_blueprint.degraded_fallback


def test_plan_is_deterministic_strict_and_fail_closed() -> None:
    request = PlanRequest(
        questions=(
            PlanQuestion(
                question_id="q1",
                intent=Intent.DEFINITION,
                exact_match=True,
                has_resolved_entity=True,
            ),
        )
    )
    assert select_decision_plan(request) == select_decision_plan(request)
    with pytest.raises(ValidationError, match="already be atomic"):
        PlanQuestion(
            question_id="q1",
            intent=Intent.MULTI_PART_QUESTION,
        )
    with pytest.raises(ValidationError, match="requires resolved scope"):
        PlanQuestion(
            question_id="q1",
            intent=Intent.DEFINITION,
            scope_resolved=False,
        )
    with pytest.raises(ValidationError, match="must be unique"):
        PlanRequest(
            questions=(
                PlanQuestion(question_id="q1", intent=Intent.DEFINITION),
                PlanQuestion(question_id="q1", intent=Intent.DEFINITION),
            )
        )
    with pytest.raises(ValidationError, match="activation gate"):
        PlannedCapability(
            capability=CapabilityName.GENERAL_AI,
            role=CapabilityRole.CONDITIONAL,
            stage=CapabilityStage.CONDITIONAL_FALLBACK,
            reason="invalid",
        )


def _capability(
    capabilities: tuple[PlannedCapability, ...],
    name: CapabilityName,
) -> PlannedCapability:
    return next(
        capability
        for capability in capabilities
        if capability.capability is name
    )
