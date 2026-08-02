from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from backend.ask.degradation import (
    CapabilityDegradationProjection,
    DegradationActionKind,
    DegradationActionType,
    DegradationConfidenceEffect,
    DegradationProjectionRequest,
    DegradationSeverity,
    degradation_projection_json,
    project_capability_degradation,
)
from backend.ask.knowledge_modes import (
    LIVE_REFRESH_UNAVAILABLE_NOTICE,
    NO_OFFICIAL_DOCUMENTS_DISCLOSURE,
    NO_VERIFIED_LIVE_UPDATES_NOTICE,
    OFFICIAL_SEARCH_UNAVAILABLE_DISCLOSURE,
)
from backend.ask.orchestration.contracts import (
    CapabilityTerminalState,
    OrchestratorCapability,
)
from backend.ask.orchestration.failure_policy import (
    FailureSignal,
    FailureTransitionDecision,
    SectionFailureDisposition,
    failure_rule,
)

CONTRACT_PATH = Path(__file__).parent / "fixtures" / "ask_degradation_contract.json"


def _terminal(signal: FailureSignal) -> CapabilityTerminalState:
    return {
        FailureSignal.PARTIAL: CapabilityTerminalState.PARTIAL,
        FailureSignal.HEALTHY_NO_MATCH: CapabilityTerminalState.NO_MATCH,
        FailureSignal.AMBIGUOUS: CapabilityTerminalState.AMBIGUOUS,
        FailureSignal.TIMED_OUT: CapabilityTerminalState.TIMED_OUT,
        FailureSignal.UNAVAILABLE: CapabilityTerminalState.UNAVAILABLE,
        FailureSignal.INVALID_OUTPUT: CapabilityTerminalState.INVALID_OUTPUT,
        FailureSignal.EVIDENCE_REJECTED: CapabilityTerminalState.PARTIAL,
        FailureSignal.CLAIM_REJECTED: CapabilityTerminalState.PARTIAL,
        FailureSignal.ALL_CLAIMS_REJECTED: CapabilityTerminalState.PARTIAL,
    }[signal]


def _decision(
    capability: OrchestratorCapability,
    signal: FailureSignal,
    *,
    node_id: str | None = None,
    disposition: SectionFailureDisposition | None = None,
) -> FailureTransitionDecision:
    rule = failure_rule(capability, signal)
    fallback_node_ids = ("fallback-node",) if rule.max_fallback_transitions else ()
    return FailureTransitionDecision(
        failed_node_id=node_id or f"{capability.value}-node",
        capability=capability,
        terminal_state=_terminal(signal),
        signal=signal,
        section_disposition=disposition or rule.section_disposition,
        fallback_action=rule.fallback_action,
        propagation=rule.propagation,
        safe_notice_code=rule.safe_notice_code,
        affected_section_ids=("section-a",),
        unaffected_section_ids=("section-b",),
        declared_dependent_node_ids=fallback_node_ids,
        propagated_node_ids=(),
        fallback_node_ids=fallback_node_ids,
        rejected_claim_ids=(
            ("claim-1",)
            if signal
            in {FailureSignal.CLAIM_REJECTED, FailureSignal.ALL_CLAIMS_REJECTED}
            else ()
        ),
        preserved_artifact_ids=("artifact-1",),
        max_fallback_transitions=rule.max_fallback_transitions,
        max_revision_passes=rule.max_revision_passes,
    )


def _project(
    capability: OrchestratorCapability,
    signal: FailureSignal,
    *,
    explicitly_requested: bool = True,
    retry: bool = False,
    node_id: str | None = None,
    disposition: SectionFailureDisposition | None = None,
) -> CapabilityDegradationProjection:
    return project_capability_degradation(
        DegradationProjectionRequest(
            decision=_decision(
                capability,
                signal,
                node_id=node_id,
                disposition=disposition,
            ),
            explicitly_requested=explicitly_requested,
            capability_retry_available=retry,
        )
    )


@pytest.mark.parametrize(
    ("capability", "signal", "severity", "confidence"),
    [
        (
            OrchestratorCapability.INTENT_CLASSIFIER,
            FailureSignal.AMBIGUOUS,
            DegradationSeverity.NEEDS_INPUT,
            DegradationConfidenceEffect.UNKNOWN,
        ),
        (
            OrchestratorCapability.ENTITY_RESOLVER,
            FailureSignal.UNAVAILABLE,
            DegradationSeverity.NEEDS_INPUT,
            DegradationConfidenceEffect.UNKNOWN,
        ),
        (
            OrchestratorCapability.REGULATORY_RETRIEVER,
            FailureSignal.HEALTHY_NO_MATCH,
            DegradationSeverity.INFORMATION,
            DegradationConfidenceEffect.LIMITED,
        ),
        (
            OrchestratorCapability.KNOWLEDGE_GRAPH,
            FailureSignal.UNAVAILABLE,
            DegradationSeverity.LIMITED,
            DegradationConfidenceEffect.LIMITED,
        ),
        (
            OrchestratorCapability.TIMELINE_BUILDER,
            FailureSignal.INVALID_OUTPUT,
            DegradationSeverity.LIMITED,
            DegradationConfidenceEffect.LIMITED,
        ),
        (
            OrchestratorCapability.NEWS_RETRIEVER,
            FailureSignal.HEALTHY_NO_MATCH,
            DegradationSeverity.INFORMATION,
            DegradationConfidenceEffect.UNCHANGED,
        ),
        (
            OrchestratorCapability.GENERAL_AI,
            FailureSignal.UNAVAILABLE,
            DegradationSeverity.UNAVAILABLE,
            DegradationConfidenceEffect.UNCHANGED,
        ),
        (
            OrchestratorCapability.CITATION_VERIFIER,
            FailureSignal.CLAIM_REJECTED,
            DegradationSeverity.LIMITED,
            DegradationConfidenceEffect.LIMITED,
        ),
        (
            OrchestratorCapability.RESPONSE_COMPOSER,
            FailureSignal.TIMED_OUT,
            DegradationSeverity.UNAVAILABLE,
            DegradationConfidenceEffect.UNCHANGED,
        ),
    ],
)
def test_frozen_failure_matrix_projects_safe_copy_and_confidence_effect(
    capability: OrchestratorCapability,
    signal: FailureSignal,
    severity: DegradationSeverity,
    confidence: DegradationConfidenceEffect,
) -> None:
    projection = _project(capability, signal)

    assert projection.visible
    assert projection.severity is severity
    assert projection.confidence_effect is confidence
    assert projection.title
    assert projection.body
    assert projection.affected_section_ids == ("section-a",)
    assert projection.unaffected_section_ids == ("section-b",)
    assert projection.preserved_artifact_ids == ("artifact-1",)
    assert "HTTP" not in projection.body
    assert "Traceback" not in projection.body
    assert "provider" not in projection.body.casefold()


def test_official_no_match_and_failure_use_different_exact_copy() -> None:
    no_match = _project(
        OrchestratorCapability.REGULATORY_RETRIEVER,
        FailureSignal.HEALTHY_NO_MATCH,
        retry=True,
    )
    unavailable = _project(
        OrchestratorCapability.REGULATORY_RETRIEVER,
        FailureSignal.UNAVAILABLE,
        retry=True,
    )

    assert no_match.body == NO_OFFICIAL_DOCUMENTS_DISCLOSURE
    assert unavailable.body == OFFICIAL_SEARCH_UNAVAILABLE_DISCLOSURE
    assert "no official regulatory documents were found" not in unavailable.body
    assert tuple(item.action for item in no_match.actions) == (
        DegradationActionType.SEARCH_OFFICIAL_DOCUMENTS_MANUALLY,
    )
    assert tuple(item.action for item in unavailable.actions) == (
        DegradationActionType.RETRY_OFFICIAL_SEARCH,
        DegradationActionType.SEARCH_OFFICIAL_DOCUMENTS_MANUALLY,
    )


def test_live_no_match_is_hidden_unless_explicit_and_failure_can_refresh() -> None:
    hidden = _project(
        OrchestratorCapability.NEWS_RETRIEVER,
        FailureSignal.HEALTHY_NO_MATCH,
        explicitly_requested=False,
    )
    explicit = _project(
        OrchestratorCapability.NEWS_RETRIEVER,
        FailureSignal.HEALTHY_NO_MATCH,
    )
    unavailable = _project(
        OrchestratorCapability.NEWS_RETRIEVER,
        FailureSignal.UNAVAILABLE,
        retry=True,
    )

    assert not hidden.visible
    assert hidden.title is hidden.body is hidden.severity is None
    assert explicit.body == NO_VERIFIED_LIVE_UPDATES_NOTICE
    assert unavailable.title == LIVE_REFRESH_UNAVAILABLE_NOTICE
    assert unavailable.actions[0].action is DegradationActionType.REFRESH_LIVE_SOURCES


def test_only_transient_retryable_capabilities_get_exact_retry_actions() -> None:
    cases = (
        (
            OrchestratorCapability.REGULATORY_RETRIEVER,
            DegradationActionType.RETRY_OFFICIAL_SEARCH,
        ),
        (
            OrchestratorCapability.NEWS_RETRIEVER,
            DegradationActionType.REFRESH_LIVE_SOURCES,
        ),
        (
            OrchestratorCapability.GENERAL_AI,
            DegradationActionType.RETRY_EXPLANATION,
        ),
        (
            OrchestratorCapability.CITATION_VERIFIER,
            DegradationActionType.RETRY_CITATION_VERIFICATION,
        ),
    )
    for capability, action in cases:
        projection = _project(capability, FailureSignal.TIMED_OUT, retry=True)
        retry_action = projection.actions[0]
        assert retry_action.action is action
        assert retry_action.kind is DegradationActionKind.CAPABILITY_RETRY
        assert retry_action.capability is capability
        assert retry_action.target == f"{capability.value}-node"

    partial = _project(
        OrchestratorCapability.REGULATORY_RETRIEVER,
        FailureSignal.PARTIAL,
        retry=True,
    )
    assert all(
        item.kind is not DegradationActionKind.CAPABILITY_RETRY
        for item in partial.actions
    )


def test_manual_search_is_safe_and_limited_to_relevant_degradations() -> None:
    evidence = _project(
        OrchestratorCapability.CITATION_VERIFIER,
        FailureSignal.EVIDENCE_REJECTED,
    )
    claim = _project(
        OrchestratorCapability.CITATION_VERIFIER,
        FailureSignal.CLAIM_REJECTED,
    )

    assert evidence.actions[0].action is (
        DegradationActionType.SEARCH_OFFICIAL_DOCUMENTS_MANUALLY
    )
    assert evidence.actions[0].target == "/browse"
    assert not claim.actions
    with pytest.raises(ValidationError, match="safe local path"):
        DegradationProjectionRequest(
            decision=_decision(
                OrchestratorCapability.REGULATORY_RETRIEVER,
                FailureSignal.UNAVAILABLE,
            ),
            manual_search_target="https://attacker.example",
        )


def test_clarification_actions_are_input_scoped_not_retries() -> None:
    intent = _project(
        OrchestratorCapability.INTENT_CLASSIFIER,
        FailureSignal.AMBIGUOUS,
    )
    entity = _project(
        OrchestratorCapability.ENTITY_RESOLVER,
        FailureSignal.AMBIGUOUS,
    )

    assert intent.actions[0].action is DegradationActionType.CLARIFY_REQUEST
    assert entity.actions[0].action is DegradationActionType.CHOOSE_ENTITY
    assert all(
        item.kind is DegradationActionKind.PROVIDE_INPUT
        for item in (*intent.actions, *entity.actions)
    )


def test_optional_timeline_and_followups_are_omitted_without_empty_chrome() -> None:
    timeline = _project(
        OrchestratorCapability.TIMELINE_BUILDER,
        FailureSignal.HEALTHY_NO_MATCH,
        disposition=SectionFailureDisposition.OMITTED,
    )
    followups = _project(
        OrchestratorCapability.FOLLOW_UP_GENERATOR,
        FailureSignal.UNAVAILABLE,
    )

    assert not timeline.visible
    assert not followups.visible
    assert not timeline.actions and not followups.actions
    assert timeline.unaffected_section_ids == followups.unaffected_section_ids == (
        "section-b",
    )


def test_all_claim_verification_failure_withholds_synthesis_but_preserves_evidence() -> None:
    projection = _project(
        OrchestratorCapability.CITATION_VERIFIER,
        FailureSignal.ALL_CLAIMS_REJECTED,
    )

    assert projection.severity is DegradationSeverity.UNAVAILABLE
    assert projection.confidence_effect is DegradationConfidenceEffect.UNKNOWN
    assert "synthesized claims are withheld" in (projection.body or "")
    assert projection.preserved_artifact_ids == ("artifact-1",)


def test_recorded_backend_frontend_contract_and_serialization_are_exact() -> None:
    projection = _project(
        OrchestratorCapability.REGULATORY_RETRIEVER,
        FailureSignal.UNAVAILABLE,
        retry=True,
        node_id="official-node",
    )
    expected = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))

    assert projection.model_dump(mode="json") == expected
    assert json.loads(degradation_projection_json(projection)) == expected


def test_projection_contract_rejects_crossed_retry_and_raw_extra_fields() -> None:
    expected = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    expected["actions"][0]["capability"] = "news_retriever"
    with pytest.raises(ValidationError, match="crossed"):
        CapabilityDegradationProjection.model_validate_json(json.dumps(expected))

    expected = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    expected["raw_error"] = "upstream secret"
    with pytest.raises(ValidationError):
        CapabilityDegradationProjection.model_validate_json(json.dumps(expected))
