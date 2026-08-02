from __future__ import annotations

from typing import Any

import pytest

from backend.ask.orchestration import (
    ArtifactEnvelope,
    ArtifactKind,
    CapabilityInvocation,
    CapabilityResult,
    CapabilityTerminalState,
    FailurePolicyError,
    FailurePropagation,
    FailureSignal,
    FallbackAction,
    OrchestrationPhase,
    OrchestrationState,
    OrchestratorCapability,
    ParticipationClass,
    ProvenanceClass,
    SectionFailureDisposition,
    SectionNode,
    VerificationResultPayload,
    VerificationStatus,
    activate_capability,
    decide_failure_transition,
    failure_rule,
    failure_transition_json,
    finish_capability,
)
from backend.tests.test_ask_ai_orchestration_scheduler import (
    _fanout_state,
    _NodeSpec,
    _replace_phase,
    _RequestFactory,
    _scope,
    _success_result,
)
from backend.tests.test_ask_ai_orchestration_state_machine import (
    CLAIM_VERIFIER_NODE,
    EVIDENCE_VERIFIER_NODE,
    _complete_state_before_finalization,
)

MATRIX_CASES = (
    (
        OrchestratorCapability.INTENT_CLASSIFIER,
        FailureSignal.AMBIGUOUS,
        SectionFailureDisposition.NEEDS_CLARIFICATION,
        FallbackAction.EXPLICIT_ACTION_OR_CLARIFICATION,
    ),
    (
        OrchestratorCapability.ENTITY_RESOLVER,
        FailureSignal.UNAVAILABLE,
        SectionFailureDisposition.NEEDS_CLARIFICATION,
        FallbackAction.PRESENT_ENTITY_CANDIDATES,
    ),
    (
        OrchestratorCapability.REGULATORY_RETRIEVER,
        FailureSignal.HEALTHY_NO_MATCH,
        SectionFailureDisposition.EMPTY_BY_EVIDENCE,
        FallbackAction.GENERAL_AI_NO_DOCUMENTS_DISCLOSURE,
    ),
    (
        OrchestratorCapability.REGULATORY_RETRIEVER,
        FailureSignal.TIMED_OUT,
        SectionFailureDisposition.DEGRADED,
        FallbackAction.SAVED_EVIDENCE_OR_MANUAL_SEARCH,
    ),
    (
        OrchestratorCapability.KNOWLEDGE_GRAPH,
        FailureSignal.UNAVAILABLE,
        SectionFailureDisposition.DEGRADED,
        FallbackAction.OFFICIAL_DOCUMENT_FACTS,
    ),
    (
        OrchestratorCapability.TIMELINE_BUILDER,
        FailureSignal.INVALID_OUTPUT,
        SectionFailureDisposition.DEGRADED,
        FallbackAction.VERIFIED_DATE_CARDS_OR_SOURCES,
    ),
    (
        OrchestratorCapability.NEWS_RETRIEVER,
        FailureSignal.HEALTHY_NO_MATCH,
        SectionFailureDisposition.EMPTY_BY_EVIDENCE,
        FallbackAction.NO_VERIFIED_LIVE_UPDATES,
    ),
    (
        OrchestratorCapability.NEWS_RETRIEVER,
        FailureSignal.UNAVAILABLE,
        SectionFailureDisposition.DEGRADED,
        FallbackAction.INTERNAL_CORPUS_ONLY,
    ),
    (
        OrchestratorCapability.GENERAL_AI,
        FailureSignal.UNAVAILABLE,
        SectionFailureDisposition.READY_WITHOUT_SYNTHESIS,
        FallbackAction.INTERPRETATION_OR_MANUAL_SEARCH,
    ),
    (
        OrchestratorCapability.CITATION_VERIFIER,
        FailureSignal.EVIDENCE_REJECTED,
        SectionFailureDisposition.DEGRADED,
        FallbackAction.SAVED_EVIDENCE_OR_MANUAL_SEARCH,
    ),
    (
        OrchestratorCapability.CITATION_VERIFIER,
        FailureSignal.CLAIM_REJECTED,
        SectionFailureDisposition.DEGRADED,
        FallbackAction.NARROW_OR_REMOVE_CLAIM,
    ),
    (
        OrchestratorCapability.CITATION_VERIFIER,
        FailureSignal.ALL_CLAIMS_REJECTED,
        SectionFailureDisposition.READY_WITHOUT_SYNTHESIS,
        FallbackAction.OFFICIAL_SOURCE_CARDS,
    ),
    (
        OrchestratorCapability.RESPONSE_COMPOSER,
        FailureSignal.TIMED_OUT,
        SectionFailureDisposition.READY_WITHOUT_SYNTHESIS,
        FallbackAction.VERIFIED_ARTIFACTS_DIRECTLY,
    ),
    (
        OrchestratorCapability.FOLLOW_UP_GENERATOR,
        FailureSignal.UNAVAILABLE,
        SectionFailureDisposition.CORE_UNCHANGED,
        FallbackAction.OMIT_SUGGESTIONS,
    ),
)


@pytest.mark.parametrize(
    ("capability", "signal", "disposition", "fallback"),
    MATRIX_CASES,
)
def test_full_frozen_failure_matrix_is_typed_and_bounded(
    capability: OrchestratorCapability,
    signal: FailureSignal,
    disposition: SectionFailureDisposition,
    fallback: FallbackAction,
) -> None:
    rule = failure_rule(capability, signal)

    assert rule.capability is capability
    assert rule.signal is signal
    assert rule.section_disposition is disposition
    assert rule.fallback_action is fallback
    assert rule.max_fallback_transitions in {0, 1}
    assert rule.max_revision_passes in {0, 1}
    if rule.max_revision_passes:
        assert capability is OrchestratorCapability.CITATION_VERIFIER
        assert signal is FailureSignal.CLAIM_REJECTED


def test_failure_matrix_rejects_ineligible_or_nonfailure_signals() -> None:
    with pytest.raises(FailurePolicyError, match="not eligible"):
        failure_rule(
            OrchestratorCapability.FOLLOW_UP_GENERATOR,
            FailureSignal.HEALTHY_NO_MATCH,
        )
    with pytest.raises(FailurePolicyError, match="not eligible"):
        failure_rule(
            OrchestratorCapability.INTENT_CLASSIFIER,
            FailureSignal.CLAIM_REJECTED,
        )


def _terminalize(
    state: OrchestrationState,
    node_id: str,
    terminal_state: CapabilityTerminalState,
) -> OrchestrationState:
    node = next(item for item in state.capabilities if item.node_id == node_id)
    request = _RequestFactory()(state, node)
    if node.capability is OrchestratorCapability.TIMELINE_BUILDER:
        request_values = request.model_dump(mode="python")
        request_values["input_artifacts"] = ()
        request = type(request).model_validate(request_values)
    state = activate_capability(state, node_id, request)
    active = next(item for item in state.capabilities if item.node_id == node_id)
    result_values = _success_result(
        CapabilityInvocation(node=active, request=request)
    ).model_dump(mode="python")
    result_values["terminal_state"] = terminal_state
    result_values["safe_error_code"] = (
        "TEST_CAPABILITY_FAILURE"
        if terminal_state
        in {
            CapabilityTerminalState.TIMED_OUT,
            CapabilityTerminalState.UNAVAILABLE,
            CapabilityTerminalState.INVALID_OUTPUT,
        }
        else None
    )
    return finish_capability(
        state,
        node_id,
        CapabilityResult.model_validate(result_values),
    )


def _fallback_state() -> OrchestrationState:
    entity = OrchestratorCapability.ENTITY_RESOLVER.value
    regulatory = "regulatory:official"
    return _fanout_state(
        (
            _NodeSpec(
                node_id=regulatory,
                capability=OrchestratorCapability.REGULATORY_RETRIEVER,
                section_key="official",
                provenance_class=(
                    ProvenanceClass.INTERNAL_REGULATORY_CORPUS
                ),
                dependencies=(entity,),
                participation=ParticipationClass.MANDATORY,
            ),
            _NodeSpec(
                node_id="general:fallback",
                capability=OrchestratorCapability.GENERAL_AI,
                section_key="general",
                provenance_class=ProvenanceClass.GENERAL_AI_KNOWLEDGE,
                dependencies=(regulatory,),
                participation=ParticipationClass.FALLBACK,
            ),
            _NodeSpec(
                node_id="composer:general",
                capability=OrchestratorCapability.RESPONSE_COMPOSER,
                section_key="general",
                provenance_class=ProvenanceClass.GENERAL_AI_KNOWLEDGE,
                dependencies=("general:fallback",),
            ),
            _NodeSpec(
                node_id="timeline:official",
                capability=OrchestratorCapability.TIMELINE_BUILDER,
                section_key="official",
                provenance_class=(
                    ProvenanceClass.INTERNAL_REGULATORY_CORPUS
                ),
                dependencies=(regulatory,),
            ),
            _NodeSpec(
                node_id="news:independent",
                capability=OrchestratorCapability.NEWS_RETRIEVER,
                section_key="live",
                provenance_class=ProvenanceClass.LIVE_WEB_SOURCES,
                dependencies=(entity,),
            ),
        )
    )


def test_healthy_no_match_activates_only_declared_fallback_and_isolates_lanes() -> None:
    state = _terminalize(
        _fallback_state(),
        "regulatory:official",
        CapabilityTerminalState.NO_MATCH,
    )

    decision = decide_failure_transition(state, "regulatory:official")

    assert decision.signal is FailureSignal.HEALTHY_NO_MATCH
    assert decision.affected_section_ids == ("section:official",)
    assert decision.unaffected_section_ids == (
        "section:general",
        "section:live",
    )
    assert decision.declared_dependent_node_ids == (
        "timeline:official",
        "general:fallback",
        "composer:general",
    )
    assert decision.propagated_node_ids == ("timeline:official",)
    assert decision.fallback_node_ids == ("general:fallback",)
    assert decision.max_fallback_transitions == 1
    assert decision.preserved_artifact_ids == tuple(
        artifact.artifact_id for artifact in state.admitted_artifacts
    )
    assert failure_transition_json(decision) == failure_transition_json(
        type(decision).model_validate_json(failure_transition_json(decision))
    )


def test_unavailable_official_retrieval_never_becomes_healthy_no_match() -> None:
    state = _terminalize(
        _fallback_state(),
        "regulatory:official",
        CapabilityTerminalState.UNAVAILABLE,
    )

    decision = decide_failure_transition(state, "regulatory:official")

    assert decision.signal is FailureSignal.UNAVAILABLE
    assert decision.section_disposition is SectionFailureDisposition.DEGRADED
    assert decision.fallback_action is (
        FallbackAction.SAVED_EVIDENCE_OR_MANUAL_SEARCH
    )
    assert decision.safe_notice_code == "ASK_AI_OFFICIAL_COVERAGE_UNKNOWN"
    assert "NO_MATCH" not in decision.safe_notice_code


def test_fallback_is_ineligible_without_a_declared_dependency() -> None:
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
                participation=ParticipationClass.MANDATORY,
            ),
            _NodeSpec(
                node_id="general:unrelated",
                capability=OrchestratorCapability.GENERAL_AI,
                section_key="general",
                provenance_class=ProvenanceClass.GENERAL_AI_KNOWLEDGE,
                dependencies=(entity,),
                participation=ParticipationClass.FALLBACK,
            ),
        )
    )
    state = _terminalize(
        state,
        "regulatory:official",
        CapabilityTerminalState.NO_MATCH,
    )

    decision = decide_failure_transition(state, "regulatory:official")

    assert decision.declared_dependent_node_ids == ()
    assert decision.fallback_node_ids == ()
    assert decision.max_fallback_transitions == 0
    assert decision.fallback_action is FallbackAction.NO_ADDITIONAL_CAPABILITY


def test_declared_general_ai_requires_a_fallback_eligible_role() -> None:
    entity = OrchestratorCapability.ENTITY_RESOLVER.value
    regulatory = "regulatory:official"
    state = _fanout_state(
        (
            _NodeSpec(
                node_id=regulatory,
                capability=OrchestratorCapability.REGULATORY_RETRIEVER,
                section_key="official",
                provenance_class=(
                    ProvenanceClass.INTERNAL_REGULATORY_CORPUS
                ),
                dependencies=(entity,),
                participation=ParticipationClass.MANDATORY,
            ),
            _NodeSpec(
                node_id="general:supporting",
                capability=OrchestratorCapability.GENERAL_AI,
                section_key="general",
                provenance_class=ProvenanceClass.GENERAL_AI_KNOWLEDGE,
                dependencies=(regulatory,),
                participation=ParticipationClass.SUPPORTING,
            ),
        )
    )
    state = _terminalize(
        state,
        regulatory,
        CapabilityTerminalState.NO_MATCH,
    )

    decision = decide_failure_transition(state, regulatory)

    assert decision.declared_dependent_node_ids == ("general:supporting",)
    assert decision.fallback_node_ids == ()
    assert decision.propagated_node_ids == ("general:supporting",)
    assert decision.max_fallback_transitions == 0


@pytest.mark.parametrize(
    ("capability", "terminal_state"),
    (
        (
            OrchestratorCapability.NEWS_RETRIEVER,
            CapabilityTerminalState.NO_MATCH,
        ),
        (
            OrchestratorCapability.TIMELINE_BUILDER,
            CapabilityTerminalState.UNAVAILABLE,
        ),
    ),
)
def test_optional_live_or_timeline_failure_omits_only_its_section(
    capability: OrchestratorCapability,
    terminal_state: CapabilityTerminalState,
) -> None:
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
                node_id=f"{capability.value}:optional",
                capability=capability,
                section_key="optional",
                provenance_class=(
                    ProvenanceClass.LIVE_WEB_SOURCES
                    if capability is OrchestratorCapability.NEWS_RETRIEVER
                    else ProvenanceClass.INTERNAL_REGULATORY_CORPUS
                ),
                dependencies=(entity,),
                participation=ParticipationClass.OPTIONAL,
            ),
        )
    )
    failed_node_id = f"{capability.value}:optional"
    if capability is OrchestratorCapability.TIMELINE_BUILDER:
        state = _replace_phase(
            state,
            OrchestrationPhase.STRUCTURED_TRANSFORMATIONS,
        )
    state = _terminalize(state, failed_node_id, terminal_state)

    decision = decide_failure_transition(state, failed_node_id)

    assert decision.section_disposition is SectionFailureDisposition.OMITTED
    assert decision.affected_section_ids == ("section:optional",)
    assert decision.unaffected_section_ids == ("section:official",)


def test_scoped_graph_failure_does_not_propagate_into_independent_live_section() -> None:
    entity = OrchestratorCapability.ENTITY_RESOLVER.value
    graph = "graph:official"
    state = _fanout_state(
        (
            _NodeSpec(
                node_id=graph,
                capability=OrchestratorCapability.KNOWLEDGE_GRAPH,
                section_key="official",
                provenance_class=(
                    ProvenanceClass.INTERNAL_REGULATORY_CORPUS
                ),
                dependencies=(entity,),
            ),
            _NodeSpec(
                node_id="composer:official",
                capability=OrchestratorCapability.RESPONSE_COMPOSER,
                section_key="official",
                provenance_class=(
                    ProvenanceClass.INTERNAL_REGULATORY_CORPUS
                ),
                dependencies=(graph,),
            ),
            _NodeSpec(
                node_id="news:live",
                capability=OrchestratorCapability.NEWS_RETRIEVER,
                section_key="live",
                provenance_class=ProvenanceClass.LIVE_WEB_SOURCES,
                dependencies=(entity,),
            ),
        )
    )
    state = _terminalize(
        state,
        graph,
        CapabilityTerminalState.UNAVAILABLE,
    )

    decision = decide_failure_transition(state, graph)

    assert decision.affected_section_ids == ("section:official",)
    assert decision.unaffected_section_ids == ("section:live",)
    assert decision.declared_dependent_node_ids == ("composer:official",)
    assert decision.propagated_node_ids == ()
    assert decision.fallback_node_ids == ()
    assert failure_rule(
        OrchestratorCapability.KNOWLEDGE_GRAPH,
        FailureSignal.UNAVAILABLE,
    ).propagation is FailurePropagation.SCOPED_SECTION_ONLY


def _rejected_verifier_state(
    *,
    all_claims: bool,
) -> OrchestrationState:
    state = _complete_state_before_finalization(
        _scope(("official_sources",))
    )
    original = next(
        artifact
        for artifact in state.admitted_artifacts
        if artifact.artifact_id == "verification-1"
    )
    artifact_values = original.model_dump(mode="python")
    artifact_values["payload"] = VerificationResultPayload(
        target_artifact_id="claim-1",
        target_kind=ArtifactKind.CANDIDATE_CLAIM,
        status=VerificationStatus.UNSUPPORTED,
        reasons=("The cited evidence does not support this claim.",),
    )
    rejected = ArtifactEnvelope.model_validate(artifact_values)
    capabilities = list(state.capabilities)
    verifier_index = next(
        index
        for index, node in enumerate(capabilities)
        if node.node_id == CLAIM_VERIFIER_NODE
    )
    verifier = capabilities[verifier_index]
    assert verifier.result is not None
    result_values = verifier.result.model_dump(mode="python")
    result_values["artifacts"] = (rejected,)
    node_values = verifier.model_dump(mode="python")
    node_values["result"] = CapabilityResult.model_validate(result_values)
    capabilities[verifier_index] = type(verifier).model_validate(node_values)

    sections = state.sections
    if not all_claims:
        section_values: dict[str, Any] = sections[0].model_dump(mode="python")
        section_values["material_claim_ids"] = ("claim-1", "claim-2")
        section_values["terminal_verification_claim_ids"] = (
            "claim-1",
            "claim-2",
        )
        sections = (SectionNode.model_validate(section_values),)

    values = state.model_dump(mode="python")
    values["capabilities"] = tuple(capabilities)
    values["sections"] = sections
    values["admitted_artifacts"] = tuple(
        rejected if artifact.artifact_id == rejected.artifact_id else artifact
        for artifact in state.admitted_artifacts
    )
    return OrchestrationState.model_validate(values)


def test_evidence_integrity_failure_never_becomes_a_claim_revision() -> None:
    state = _complete_state_before_finalization(
        _scope(("official_sources",))
    )
    original = next(
        artifact
        for artifact in state.admitted_artifacts
        if artifact.artifact_id == "evidence-verification-1"
    )
    artifact_values = original.model_dump(mode="python")
    artifact_values["payload"] = VerificationResultPayload(
        target_artifact_id="evidence-1",
        target_kind=ArtifactKind.EVIDENCE_UNIT,
        status=VerificationStatus.UNSUPPORTED,
        reasons=("Evidence identity could not be verified.",),
    )
    rejected = ArtifactEnvelope.model_validate(artifact_values)
    capabilities = list(state.capabilities)
    verifier_index = next(
        index
        for index, node in enumerate(capabilities)
        if node.node_id == EVIDENCE_VERIFIER_NODE
    )
    verifier = capabilities[verifier_index]
    assert verifier.result is not None
    result_values = verifier.result.model_dump(mode="python")
    result_values["artifacts"] = (rejected,)
    node_values = verifier.model_dump(mode="python")
    node_values["result"] = CapabilityResult.model_validate(result_values)
    capabilities[verifier_index] = type(verifier).model_validate(node_values)
    values = state.model_dump(mode="python")
    values["capabilities"] = tuple(capabilities)
    values["admitted_artifacts"] = tuple(
        rejected if artifact.artifact_id == rejected.artifact_id else artifact
        for artifact in state.admitted_artifacts
    )
    state = OrchestrationState.model_validate(values)

    decision = decide_failure_transition(state, EVIDENCE_VERIFIER_NODE)

    assert decision.signal is FailureSignal.EVIDENCE_REJECTED
    assert decision.terminal_state is CapabilityTerminalState.SATISFIED
    assert decision.affected_section_ids == ("section-1",)
    assert decision.max_revision_passes == 0
    assert decision.fallback_action is (
        FallbackAction.SAVED_EVIDENCE_OR_MANUAL_SEARCH
    )


@pytest.mark.parametrize(
    ("all_claims", "expected_signal", "expected_disposition", "revisions"),
    (
        (
            False,
            FailureSignal.CLAIM_REJECTED,
            SectionFailureDisposition.DEGRADED,
            1,
        ),
        (
            True,
            FailureSignal.ALL_CLAIMS_REJECTED,
            SectionFailureDisposition.READY_WITHOUT_SYNTHESIS,
            0,
        ),
    ),
)
def test_verifier_distinguishes_single_and_all_claim_failure(
    all_claims: bool,
    expected_signal: FailureSignal,
    expected_disposition: SectionFailureDisposition,
    revisions: int,
) -> None:
    state = _rejected_verifier_state(all_claims=all_claims)

    decision = decide_failure_transition(state, CLAIM_VERIFIER_NODE)

    assert decision.signal is expected_signal
    assert decision.section_disposition is expected_disposition
    assert decision.rejected_claim_ids == ("claim-1",)
    assert decision.affected_section_ids == ("section-1",)
    assert decision.max_revision_passes == revisions


def test_nonfailure_or_unfinished_node_cannot_create_failure_decision() -> None:
    state = _fallback_state()
    with pytest.raises(FailurePolicyError, match="terminal result"):
        decide_failure_transition(state, "regulatory:official")

    state = _terminalize(
        state,
        "regulatory:official",
        CapabilityTerminalState.SATISFIED,
    )
    with pytest.raises(FailurePolicyError, match="does not require"):
        decide_failure_transition(state, "regulatory:official")
