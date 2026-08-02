from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from backend.ask.decision import ConfidenceLabel, Intent
from backend.ask.follow_ups import (
    DegradedCapability,
    FollowUpCategory,
    FollowUpGapKind,
    FollowUpRequest,
    FollowUpScope,
    FollowUpStatus,
    generate_follow_ups,
)
from backend.ask.orchestration import CapabilityTerminalState, OrchestratorCapability

ALL_CAPABILITIES = (
    OrchestratorCapability.REGULATORY_RETRIEVER,
    OrchestratorCapability.KNOWLEDGE_GRAPH,
    OrchestratorCapability.TIMELINE_BUILDER,
    OrchestratorCapability.NEWS_RETRIEVER,
)


def _request(**updates: object) -> FollowUpRequest:
    values: dict[str, object] = {
        "scope": FollowUpScope(
            entity_id="entity-dsm",
            entity_name="DSM",
            jurisdiction="India",
            stakeholder="generators",
            comparison_operands=("ABT",),
            related_entities=("CERC DSM Regulations",),
        ),
        "completed_intents": (Intent.ENTITY_LOOKUP,),
        "confidence_label": ConfidenceLabel.MEDIUM,
        "eligible_capabilities": ALL_CAPABILITIES,
    }
    values.update(updates)
    return FollowUpRequest(**values)


def test_selection_order_produces_five_distinct_typed_directions() -> None:
    result = generate_follow_ups(_request())

    assert result.status is FollowUpStatus.GENERATED
    assert [item.category for item in result.suggestions] == [
        FollowUpCategory.VERIFY,
        FollowUpCategory.COMPLIANCE,
        FollowUpCategory.CHANGE,
        FollowUpCategory.EXPLORE,
        FollowUpCategory.LIVE,
    ]
    assert result.suggestions[0].question == "Show the official provision for DSM"
    assert result.suggestions[3].question == "Compare DSM with ABT"
    assert result.required_for_completion is False


def test_below_high_always_deepens_evidence_when_retrieval_is_usable() -> None:
    for label in (ConfidenceLabel.UNKNOWN, ConfidenceLabel.LOW, ConfidenceLabel.MEDIUM):
        result = generate_follow_ups(_request(confidence_label=label))
        assert FollowUpCategory.VERIFY in {
            item.category for item in result.suggestions
        }


def test_below_high_uses_manual_evidence_path_when_retriever_is_ineligible() -> None:
    result = generate_follow_ups(
        _request(
            eligible_capabilities=(
                OrchestratorCapability.KNOWLEDGE_GRAPH,
                OrchestratorCapability.TIMELINE_BUILDER,
                OrchestratorCapability.NEWS_RETRIEVER,
            )
        )
    )

    assert result.suggestions[0].question == "Search official documents manually"


def test_high_confidence_does_not_force_evidence_deepening() -> None:
    result = generate_follow_ups(_request(confidence_label=ConfidenceLabel.HIGH))

    assert FollowUpCategory.VERIFY not in {item.category for item in result.suggestions}
    assert len(result.suggestions) == 4


def test_material_gap_or_assumption_is_selected_first_by_fixed_policy() -> None:
    forward = _request(
        gaps=(FollowUpGapKind.DEADLINE, FollowUpGapKind.JURISDICTION),
        assumptions=(FollowUpGapKind.STAKEHOLDER,),
    )
    reverse = _request(
        gaps=(FollowUpGapKind.JURISDICTION, FollowUpGapKind.DEADLINE),
        assumptions=(FollowUpGapKind.STAKEHOLDER,),
    )

    first = generate_follow_ups(forward)
    second = generate_follow_ups(reverse)

    assert first.suggestions[0].question == "Select the jurisdiction for DSM"
    assert first.model_dump_json() == second.model_dump_json()


def test_retrieval_failure_suggests_manual_search_not_false_absence() -> None:
    result = generate_follow_ups(
        _request(
            degraded_capabilities=(
                DegradedCapability(
                    capability=OrchestratorCapability.REGULATORY_RETRIEVER,
                    state=CapabilityTerminalState.UNAVAILABLE,
                ),
            )
        )
    )

    assert result.suggestions[0].question == "Search official documents manually"
    assert all("no official" not in item.question.casefold() for item in result.suggestions)
    assert all(
        item.capability is not OrchestratorCapability.REGULATORY_RETRIEVER
        for item in result.suggestions
    )


def test_answered_intents_are_not_repeated() -> None:
    result = generate_follow_ups(
        _request(
            completed_intents=(
                Intent.ENTITY_LOOKUP,
                Intent.COMPLIANCE_QUESTION,
                Intent.TIMELINE,
                Intent.NEWS,
            )
        )
    )

    categories = {item.category for item in result.suggestions}
    assert FollowUpCategory.COMPLIANCE not in categories
    assert FollowUpCategory.CHANGE not in categories
    assert FollowUpCategory.LIVE not in categories


def test_prior_questions_and_suggestions_are_excluded_after_normalization() -> None:
    result = generate_follow_ups(
        _request(
            prior_questions=("  SHOW   THE OFFICIAL PROVISION FOR DSM ",),
            prior_suggestions=("compare dsm with abt",),
        )
    )

    questions = {item.question.casefold() for item in result.suggestions}
    assert "show the official provision for dsm" not in questions
    assert "compare dsm with abt" not in questions


def test_live_and_comparison_require_resolved_eligibility_inputs() -> None:
    scope = FollowUpScope(
        entity_id="entity-dsm",
        entity_name="DSM",
        related_entities=("CERC DSM Regulations",),
    )
    result = generate_follow_ups(_request(scope=scope))
    questions = {item.question for item in result.suggestions}

    assert not any(item.startswith("Compare ") for item in questions)
    assert any(item.startswith("Find the latest DSM") for item in questions)

    unresolved = generate_follow_ups(
        _request(scope=FollowUpScope(selected_document_title="DSM Regulation"))
    )
    assert all(item.category is not FollowUpCategory.LIVE for item in unresolved.suggestions)


def test_degraded_optional_capabilities_are_not_presented_as_available() -> None:
    degraded = tuple(
        DegradedCapability(capability=capability, state=CapabilityTerminalState.TIMED_OUT)
        for capability in (
            OrchestratorCapability.KNOWLEDGE_GRAPH,
            OrchestratorCapability.TIMELINE_BUILDER,
            OrchestratorCapability.NEWS_RETRIEVER,
        )
    )
    result = generate_follow_ups(_request(degraded_capabilities=degraded))

    degraded_names = {entry.capability for entry in degraded}
    assert all(
        item.capability not in degraded_names
        for item in result.suggestions
    )


def test_optional_budget_exhaustion_is_valid_empty_and_nonblocking() -> None:
    result = generate_follow_ups(_request(optional_budget_available=False))

    assert result.status is FollowUpStatus.EMPTY
    assert result.suggestions == ()
    assert result.artifact.candidates == ()
    assert result.required_for_completion is False


def test_insufficient_safe_diversity_returns_zero_not_one_or_two() -> None:
    result = generate_follow_ups(
        _request(
            scope=FollowUpScope(),
            eligible_capabilities=(),
            confidence_label=ConfidenceLabel.HIGH,
        )
    )

    assert result.status is FollowUpStatus.EMPTY
    assert result.suggestions == ()


def test_typed_artifact_matches_suggestions_exactly() -> None:
    result = generate_follow_ups(_request())

    assert [item.question for item in result.artifact.candidates] == [
        item.question for item in result.suggestions
    ]
    assert [item.expected_response_strategy for item in result.artifact.candidates] == [
        item.expected_response_strategy.value for item in result.suggestions
    ]


def test_output_is_deterministic_and_round_trips_strictly() -> None:
    first = generate_follow_ups(_request())
    second = generate_follow_ups(_request())

    assert first.model_dump_json() == second.model_dump_json()
    assert json.loads(first.model_dump_json())["schema_version"] == "1"


def test_invalid_scope_prior_text_and_degradation_fail_closed() -> None:
    with pytest.raises(ValidationError, match="ID and name"):
        FollowUpScope(entity_id="entity-only")
    with pytest.raises(ValidationError, match="control characters"):
        FollowUpScope(entity_id="entity", entity_name="Unsafe\nname")
    with pytest.raises(ValidationError, match="Prior follow-up"):
        _request(prior_questions=("Same", " same "))
    with pytest.raises(ValidationError, match="degraded outcome"):
        _request(
            degraded_capabilities=(
                DegradedCapability(
                    capability=OrchestratorCapability.NEWS_RETRIEVER,
                    state=CapabilityTerminalState.NO_MATCH,
                ),
            )
        )
