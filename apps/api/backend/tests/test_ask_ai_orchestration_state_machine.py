from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
from pydantic import ValidationError

from backend.ask.decision import KnowledgeMode, TimeDimension
from backend.ask.orchestration import (
    ORCHESTRATION_POLICY_VERSION,
    ORCHESTRATION_STATE_SCHEMA_VERSION,
    PHASE_ORDER,
    ApprovedWorkPlanPayload,
    ArtifactEnvelope,
    ArtifactKind,
    ArtifactProducer,
    CandidateClaimPayload,
    CapabilityDependency,
    CapabilityLifecycleState,
    CapabilityNode,
    CapabilityNodePlan,
    CapabilityOperation,
    CapabilityParticipation,
    CapabilityRequest,
    CapabilityResult,
    CapabilityScope,
    CapabilityTerminalState,
    CapabilityTiming,
    CapabilityWorkState,
    ContentDerivation,
    EvidenceUnitPayload,
    InterpretationResultPayload,
    OrchestrationPhase,
    OrchestrationState,
    OrchestratorCapability,
    ParticipationClass,
    ProvenanceClass,
    ProvenanceLineage,
    ResearchRequestPayload,
    ResolutionSetPayload,
    RunTerminalState,
    SectionContentBlock,
    SectionDraftPayload,
    SectionLifecycleState,
    SectionNode,
    SectionTerminalState,
    SectionWorkState,
    SourceIdentity,
    TransformationStep,
    VerificationResultPayload,
    VerificationStatus,
    activate_capability,
    advance_phase,
    approve_work_plan,
    can_activate_in_phase,
    can_advance_phase,
    can_transition_capability,
    can_transition_section,
    finalize_clarification,
    finalize_orchestration,
    finish_capability,
    initialize_orchestration,
    orchestration_state_json,
    transition_section,
)

CONTRACT_PATH = (
    Path(__file__).parent
    / "fixtures"
    / "ask_orchestration_state_machine.json"
)
RUN_ID = UUID("11111111-1111-4111-8111-111111111111")
REQUEST_IDS = {
    capability: UUID(int=index + 2)
    for index, capability in enumerate(OrchestratorCapability)
}
STARTED_AT = datetime(2026, 7, 27, 9, 0, tzinfo=UTC)
PLAN_ID = "plan-1"
REGULATORY_NODE = "regulatory:question-1:official_sources"
EVIDENCE_VERIFIER_NODE = "citation:evidence:question-1:official_sources"
COMPOSER_NODE = "composer:question-1:official_sources"
CLAIM_VERIFIER_NODE = "citation:claims:question-1:official_sources"
EVIDENCE_VERIFIER_REQUEST_ID = UUID(int=100)
CLAIM_VERIFIER_REQUEST_ID = UUID(int=101)


@pytest.fixture(scope="module")
def contract() -> dict[str, Any]:
    return json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))


@pytest.fixture
def scope() -> CapabilityScope:
    return CapabilityScope(
        atomic_question_ids=("question-1",),
        section_keys=("official_sources",),
        entity_ids=("entity-1",),
        jurisdiction="India",
        time_scope="current",
        date_semantics=(TimeDimension.EFFECTIVE,),
    )


def _timing(index: int = 0) -> CapabilityTiming:
    started = STARTED_AT + timedelta(milliseconds=index * 100)
    return CapabilityTiming(
        started_at=started,
        completed_at=started + timedelta(milliseconds=50),
        duration_ms=50,
    )


def _research_request(scope: CapabilityScope) -> ArtifactEnvelope:
    return ArtifactEnvelope(
        artifact_id="research-1",
        producer=ArtifactProducer.DECISION_ENGINE,
        scope=scope,
        payload=ResearchRequestPayload(
            query="What filing is required?",
            selected_object_ids=("entity-1",),
        ),
    )


def _request(
    capability: OrchestratorCapability,
    participation: ParticipationClass,
    scope: CapabilityScope,
    inputs: tuple[ArtifactEnvelope, ...],
    request_id: UUID | None = None,
) -> CapabilityRequest:
    return CapabilityRequest(
        request_id=request_id or REQUEST_IDS[capability],
        run_id=RUN_ID,
        plan_id=PLAN_ID,
        capability=capability,
        participation=participation,
        scope=scope,
        input_artifacts=inputs,
    )


def _result(
    capability: OrchestratorCapability,
    state: CapabilityTerminalState,
    scope: CapabilityScope,
    artifacts: tuple[ArtifactEnvelope, ...] = (),
    index: int = 0,
    request_id: UUID | None = None,
) -> CapabilityResult:
    return CapabilityResult(
        request_id=request_id or REQUEST_IDS[capability],
        run_id=RUN_ID,
        capability=capability,
        terminal_state=state,
        scope_echo=scope,
        artifacts=artifacts,
        timing=_timing(index),
        safe_error_code=(
            "CAPABILITY_UNAVAILABLE"
            if state
            in {
                CapabilityTerminalState.TIMED_OUT,
                CapabilityTerminalState.UNAVAILABLE,
                CapabilityTerminalState.INVALID_OUTPUT,
            }
            else None
        ),
    )


def _interpretation_artifact(scope: CapabilityScope) -> ArtifactEnvelope:
    return ArtifactEnvelope(
        artifact_id="interpretation-1",
        producer=ArtifactProducer.INTENT_CLASSIFIER,
        scope=scope,
        payload=InterpretationResultPayload(
            primary_intent="compliance_question",
            atomic_questions=("What filing is required?",),
            interpretation_confidence=0.95,
        ),
    )


def _resolution_artifact(scope: CapabilityScope) -> ArtifactEnvelope:
    return ArtifactEnvelope(
        artifact_id="resolution-1",
        producer=ArtifactProducer.ENTITY_RESOLVER,
        scope=scope,
        payload=ResolutionSetPayload(
            canonical_entity_ids=("entity-1",),
            original_mentions=("entity",),
            resolution_confidence=0.95,
        ),
    )


def _interpreted_state(
    scope: CapabilityScope,
    *,
    entity_state: CapabilityTerminalState = CapabilityTerminalState.SATISFIED,
) -> OrchestrationState:
    research = _research_request(scope)
    state = initialize_orchestration(
        run_id=RUN_ID,
        plan_id=PLAN_ID,
        policy_version=ORCHESTRATION_POLICY_VERSION,
        research_request=research,
    )
    state = advance_phase(state, OrchestrationPhase.INTERPRETATION)
    intent_request = _request(
        OrchestratorCapability.INTENT_CLASSIFIER,
        ParticipationClass.MANDATORY,
        scope,
        (research,),
    )
    state = activate_capability(
        state,
        OrchestratorCapability.INTENT_CLASSIFIER.value,
        intent_request,
    )
    interpretation = _interpretation_artifact(scope)
    state = finish_capability(
        state,
        OrchestratorCapability.INTENT_CLASSIFIER.value,
        _result(
            OrchestratorCapability.INTENT_CLASSIFIER,
            CapabilityTerminalState.SATISFIED,
            scope,
            (interpretation,),
        ),
    )
    entity_request = _request(
        OrchestratorCapability.ENTITY_RESOLVER,
        ParticipationClass.MANDATORY,
        scope,
        (research, interpretation),
    )
    state = activate_capability(
        state,
        OrchestratorCapability.ENTITY_RESOLVER.value,
        entity_request,
    )
    return finish_capability(
        state,
        OrchestratorCapability.ENTITY_RESOLVER.value,
        _result(
            OrchestratorCapability.ENTITY_RESOLVER,
            entity_state,
            scope,
            (_resolution_artifact(scope),),
            1,
        ),
    )


def _plan_roles() -> dict[OrchestratorCapability, ParticipationClass]:
    selected = {
        OrchestratorCapability.INTENT_CLASSIFIER,
        OrchestratorCapability.ENTITY_RESOLVER,
        OrchestratorCapability.REGULATORY_RETRIEVER,
        OrchestratorCapability.CITATION_VERIFIER,
        OrchestratorCapability.RESPONSE_COMPOSER,
    }
    return {
        capability: (
            ParticipationClass.MANDATORY
            if capability in selected
            else ParticipationClass.SKIPPED
        )
        for capability in OrchestratorCapability
    }


def _plan_dependencies() -> dict[
    OrchestratorCapability,
    tuple[OrchestratorCapability, ...],
]:
    return {
        capability: {
            OrchestratorCapability.REGULATORY_RETRIEVER: (
                OrchestratorCapability.ENTITY_RESOLVER,
            ),
            OrchestratorCapability.RESPONSE_COMPOSER: (
                OrchestratorCapability.REGULATORY_RETRIEVER,
                OrchestratorCapability.CITATION_VERIFIER,
            ),
            OrchestratorCapability.CITATION_VERIFIER: (
                OrchestratorCapability.REGULATORY_RETRIEVER,
                OrchestratorCapability.RESPONSE_COMPOSER,
            ),
        }.get(capability, ())
        for capability in OrchestratorCapability
    }


def _capability_node_plans(
    roles: dict[OrchestratorCapability, ParticipationClass] | None = None,
) -> tuple[CapabilityNodePlan, ...]:
    resolved_roles = roles or _plan_roles()
    nodes: list[CapabilityNodePlan] = []
    for capability in OrchestratorCapability:
        role = resolved_roles[capability]
        if capability is OrchestratorCapability.INTENT_CLASSIFIER:
            nodes.append(
                CapabilityNodePlan(
                    node_id=capability.value,
                    capability=capability,
                    participation=role,
                )
            )
        elif capability is OrchestratorCapability.ENTITY_RESOLVER:
            nodes.append(
                CapabilityNodePlan(
                    node_id=capability.value,
                    capability=capability,
                    participation=role,
                )
            )
        elif (
            capability is OrchestratorCapability.REGULATORY_RETRIEVER
            and role is not ParticipationClass.SKIPPED
        ):
            nodes.append(
                CapabilityNodePlan(
                    node_id=REGULATORY_NODE,
                    capability=capability,
                    participation=role,
                    atomic_question_id="question-1",
                    section_key="official_sources",
                    provenance_class=(
                        ProvenanceClass.INTERNAL_REGULATORY_CORPUS
                    ),
                    dependencies=(OrchestratorCapability.ENTITY_RESOLVER.value,),
                )
            )
        elif (
            capability is OrchestratorCapability.CITATION_VERIFIER
            and role is not ParticipationClass.SKIPPED
        ):
            nodes.extend(
                (
                    CapabilityNodePlan(
                        node_id=EVIDENCE_VERIFIER_NODE,
                        capability=capability,
                        participation=role,
                        operation=CapabilityOperation.EVIDENCE_INTEGRITY,
                        atomic_question_id="question-1",
                        section_key="official_sources",
                        provenance_class=(
                            ProvenanceClass.INTERNAL_REGULATORY_CORPUS
                        ),
                        dependencies=(REGULATORY_NODE,),
                    ),
                    CapabilityNodePlan(
                        node_id=CLAIM_VERIFIER_NODE,
                        capability=capability,
                        participation=role,
                        operation=CapabilityOperation.CLAIM_SUPPORT,
                        atomic_question_id="question-1",
                        section_key="official_sources",
                        provenance_class=(
                            ProvenanceClass.INTERNAL_REGULATORY_CORPUS
                        ),
                        dependencies=(
                            EVIDENCE_VERIFIER_NODE,
                            COMPOSER_NODE,
                        ),
                    ),
                )
            )
        elif (
            capability is OrchestratorCapability.RESPONSE_COMPOSER
            and role is not ParticipationClass.SKIPPED
        ):
            nodes.append(
                CapabilityNodePlan(
                    node_id=COMPOSER_NODE,
                    capability=capability,
                    participation=role,
                    atomic_question_id="question-1",
                    section_key="official_sources",
                    provenance_class=(
                        ProvenanceClass.INTERNAL_REGULATORY_CORPUS
                    ),
                    dependencies=(EVIDENCE_VERIFIER_NODE,),
                )
            )
        else:
            nodes.append(
                CapabilityNodePlan(
                    node_id=capability.value,
                    capability=capability,
                    participation=role,
                )
            )
    return tuple(nodes)


def _approved_plan(
    scope: CapabilityScope,
    *,
    dependencies: dict[
        OrchestratorCapability,
        tuple[OrchestratorCapability, ...],
    ]
    | None = None,
    roles: dict[OrchestratorCapability, ParticipationClass] | None = None,
    mode_eligibility: tuple[KnowledgeMode, ...] = (
        KnowledgeMode.GROUNDED_REGULATORY,
    ),
) -> ArtifactEnvelope:
    resolved_roles = roles or _plan_roles()
    resolved_dependencies = dependencies or _plan_dependencies()
    return ArtifactEnvelope(
        artifact_id="approved-plan-1",
        producer=ArtifactProducer.DECISION_ENGINE,
        scope=scope,
        payload=ApprovedWorkPlanPayload(
            plan_id=PLAN_ID,
            capability_roles=tuple(
                CapabilityParticipation(
                    capability=capability,
                    participation=resolved_roles[capability],
                )
                for capability in OrchestratorCapability
            ),
            dependencies=tuple(
                CapabilityDependency(
                    capability=capability,
                    dependencies=resolved_dependencies[capability],
                )
                for capability in OrchestratorCapability
            ),
            mode_eligibility=mode_eligibility,
            budget_profile="focused_grounded",
        ),
    )


def _section() -> SectionNode:
    return SectionNode(
        section_id="section-1",
        atomic_question_id="question-1",
        section_key="official_sources",
        required=True,
        knowledge_mode=KnowledgeMode.GROUNDED_REGULATORY,
        provenance_class=ProvenanceClass.INTERNAL_REGULATORY_CORPUS,
    )


def _official_lineage(
    capability: OrchestratorCapability | None = None,
    input_id: str | None = None,
) -> ProvenanceLineage:
    transformations = (
        (
            TransformationStep(
                capability=capability,
                derivation=ContentDerivation.SUMMARIZED,
                input_artifact_ids=(input_id,),
                input_provenance=(
                    ProvenanceClass.INTERNAL_REGULATORY_CORPUS,
                ),
                output_provenance=(
                    ProvenanceClass.INTERNAL_REGULATORY_CORPUS
                ),
            ),
        )
        if capability is not None and input_id is not None
        else ()
    )
    return ProvenanceLineage(
        provenance_class=ProvenanceClass.INTERNAL_REGULATORY_CORPUS,
        knowledge_mode=KnowledgeMode.GROUNDED_REGULATORY,
        sources=(
            SourceIdentity(
                source_id="document-1",
                provenance_class=ProvenanceClass.INTERNAL_REGULATORY_CORPUS,
                title="Official regulation",
                issue_at=STARTED_AT,
            ),
        ),
        derivation=(
            ContentDerivation.SUMMARIZED
            if transformations
            else ContentDerivation.DIRECT
        ),
        transformations=transformations,
        verification_status=VerificationStatus.SUPPORTED,
    )


def _evidence(scope: CapabilityScope) -> ArtifactEnvelope:
    return ArtifactEnvelope(
        artifact_id="evidence-1",
        producer=ArtifactProducer.REGULATORY_RETRIEVER,
        scope=scope,
        payload=EvidenceUnitPayload(
            excerpt="The entity must submit an annual filing.",
            locator="section 4",
        ),
        provenance=_official_lineage(),
        ancestry=("approved-plan-1", "resolution-1"),
        capability_status=CapabilityTerminalState.SATISFIED,
    )


def _claim(scope: CapabilityScope) -> ArtifactEnvelope:
    return ArtifactEnvelope(
        artifact_id="claim-1",
        producer=ArtifactProducer.RESPONSE_COMPOSER,
        scope=scope,
        payload=CandidateClaimPayload(
            claim_text="The entity must submit an annual filing.",
            material=True,
            supporting_artifact_ids=("evidence-1",),
        ),
        provenance=_official_lineage(
            OrchestratorCapability.RESPONSE_COMPOSER,
            "evidence-1",
        ),
        ancestry=("approved-plan-1", "evidence-1"),
        capability_status=CapabilityTerminalState.SATISFIED,
    )


def _section_draft(scope: CapabilityScope) -> ArtifactEnvelope:
    return ArtifactEnvelope(
        artifact_id="section-draft-1",
        producer=ArtifactProducer.RESPONSE_COMPOSER,
        scope=scope,
        payload=SectionDraftPayload(
            section_type="compliance_checklist",
            content_blocks=(
                SectionContentBlock(
                    block_type="obligation",
                    content="Submit the annual filing.",
                ),
            ),
            candidate_claim_ids=("claim-1",),
        ),
        provenance=_official_lineage(
            OrchestratorCapability.RESPONSE_COMPOSER,
            "evidence-1",
        ),
        ancestry=("approved-plan-1", "evidence-1"),
        capability_status=CapabilityTerminalState.SATISFIED,
    )


def _verification(scope: CapabilityScope) -> ArtifactEnvelope:
    return ArtifactEnvelope(
        artifact_id="verification-1",
        producer=ArtifactProducer.CITATION_VERIFIER,
        scope=scope,
        payload=VerificationResultPayload(
            target_artifact_id="claim-1",
            target_kind=ArtifactKind.CANDIDATE_CLAIM,
            status=VerificationStatus.SUPPORTED,
            reasons=("Direct official support.",),
        ),
        ancestry=("claim-1", "evidence-1"),
    )


def _evidence_verification(scope: CapabilityScope) -> ArtifactEnvelope:
    return ArtifactEnvelope(
        artifact_id="evidence-verification-1",
        producer=ArtifactProducer.CITATION_VERIFIER,
        scope=scope,
        payload=VerificationResultPayload(
            target_artifact_id="evidence-1",
            target_kind=ArtifactKind.EVIDENCE_UNIT,
            status=VerificationStatus.SUPPORTED,
            reasons=("Inspectable official identity and excerpt.",),
        ),
        ancestry=("evidence-1",),
    )


def _approved_state(scope: CapabilityScope) -> OrchestrationState:
    return approve_work_plan(
        _interpreted_state(scope),
        approved_plan=_approved_plan(scope),
        capability_nodes=_capability_node_plans(),
        sections=(_section(),),
    )


def _complete_state_before_finalization(
    scope: CapabilityScope,
) -> OrchestrationState:
    state = _approved_state(scope)
    state = advance_phase(state, OrchestrationPhase.EVIDENCE_FAN_OUT)
    plan = state.approved_plan
    assert plan is not None
    resolution = next(
        artifact
        for artifact in state.admitted_artifacts
        if artifact.artifact_id == "resolution-1"
    )
    regulatory_request = _request(
        OrchestratorCapability.REGULATORY_RETRIEVER,
        ParticipationClass.MANDATORY,
        scope,
        (plan, resolution),
    )
    state = activate_capability(state, REGULATORY_NODE, regulatory_request)
    evidence = _evidence(scope)
    state = finish_capability(
        state,
        REGULATORY_NODE,
        _result(
            OrchestratorCapability.REGULATORY_RETRIEVER,
            CapabilityTerminalState.SATISFIED,
            scope,
            (evidence,),
            2,
        ),
    )
    state = transition_section(
        state,
        "section-1",
        SectionWorkState.COLLECTING,
    )
    state = transition_section(
        state,
        "section-1",
        SectionWorkState.DRAFTABLE,
    )
    state = advance_phase(state, OrchestrationPhase.EVIDENCE_ADMISSION)
    evidence_verifier_request = _request(
        OrchestratorCapability.CITATION_VERIFIER,
        ParticipationClass.MANDATORY,
        scope,
        (evidence,),
        EVIDENCE_VERIFIER_REQUEST_ID,
    )
    state = activate_capability(
        state,
        EVIDENCE_VERIFIER_NODE,
        evidence_verifier_request,
    )
    evidence_verification = _evidence_verification(scope)
    state = finish_capability(
        state,
        EVIDENCE_VERIFIER_NODE,
        _result(
            OrchestratorCapability.CITATION_VERIFIER,
            CapabilityTerminalState.SATISFIED,
            scope,
            (evidence_verification,),
            3,
            EVIDENCE_VERIFIER_REQUEST_ID,
        ),
    )
    state = advance_phase(
        state,
        OrchestrationPhase.STRUCTURED_TRANSFORMATIONS,
    )
    state = advance_phase(state, OrchestrationPhase.SECTION_COMPOSITION)
    state = transition_section(
        state,
        "section-1",
        SectionWorkState.COMPOSING,
    )
    composer_request = _request(
        OrchestratorCapability.RESPONSE_COMPOSER,
        ParticipationClass.MANDATORY,
        scope,
        (plan, evidence, evidence_verification),
    )
    state = activate_capability(state, COMPOSER_NODE, composer_request)
    claim = _claim(scope)
    state = finish_capability(
        state,
        COMPOSER_NODE,
        _result(
            OrchestratorCapability.RESPONSE_COMPOSER,
            CapabilityTerminalState.SATISFIED,
            scope,
            (claim, _section_draft(scope)),
            4,
        ),
    )
    state = transition_section(
        state,
        "section-1",
        SectionWorkState.VERIFYING,
    )
    state = advance_phase(state, OrchestrationPhase.VERIFICATION)
    verifier_request = _request(
        OrchestratorCapability.CITATION_VERIFIER,
        ParticipationClass.MANDATORY,
        scope,
        (evidence, claim),
        CLAIM_VERIFIER_REQUEST_ID,
    )
    state = activate_capability(state, CLAIM_VERIFIER_NODE, verifier_request)
    state = finish_capability(
        state,
        CLAIM_VERIFIER_NODE,
        _result(
            OrchestratorCapability.CITATION_VERIFIER,
            CapabilityTerminalState.SATISFIED,
            scope,
            (_verification(scope),),
            5,
            CLAIM_VERIFIER_REQUEST_ID,
        ),
    )
    state = transition_section(
        state,
        "section-1",
        SectionTerminalState.READY,
    )
    state = advance_phase(state, OrchestrationPhase.DETERMINISTIC_MERGE)
    return advance_phase(state, OrchestrationPhase.COMPLETION)


def _replace_sections(
    state: OrchestrationState,
    sections: tuple[SectionNode, ...],
) -> OrchestrationState:
    values = state.model_dump(mode="python")
    values["sections"] = sections
    values["terminal_state"] = None
    return OrchestrationState.model_validate(values)


def test_fixture_freezes_all_phase_and_run_states(
    contract: dict[str, Any],
) -> None:
    assert contract["schema_version"] == ORCHESTRATION_STATE_SCHEMA_VERSION
    assert contract["phases"] == [phase.value for phase in PHASE_ORDER]
    assert contract["capability_work_states"] == [
        state.value for state in CapabilityWorkState
    ]
    assert contract["capability_operations"] == [
        operation.value for operation in CapabilityOperation
    ]
    assert contract["section_work_states"] == [
        state.value for state in SectionWorkState
    ]
    assert contract["run_terminal_states"] == [
        state.value for state in RunTerminalState
    ]


def test_every_capability_state_pair_matches_the_frozen_transition_table(
    contract: dict[str, Any],
) -> None:
    states: tuple[CapabilityLifecycleState, ...] = (
        *CapabilityWorkState,
        *CapabilityTerminalState,
    )
    allowed = {
        (current, target)
        for current, target in contract["capability_transitions"]
    }
    for current in states:
        for target in states:
            assert can_transition_capability(current, target) is (
                (current.value, target.value) in allowed
            )


def test_every_section_state_pair_matches_the_frozen_transition_table(
    contract: dict[str, Any],
) -> None:
    states: tuple[SectionLifecycleState, ...] = (
        *SectionWorkState,
        *SectionTerminalState,
    )
    allowed = {
        (current, target) for current, target in contract["section_transitions"]
    }
    for current in states:
        for target in states:
            assert can_transition_section(current, target) is (
                (current.value, target.value) in allowed
            )


def test_phase_transitions_are_strictly_forward_and_adjacent() -> None:
    for current_index, current in enumerate(OrchestrationPhase):
        for target_index, target in enumerate(OrchestrationPhase):
            assert can_advance_phase(current, target) is (
                target_index == current_index + 1
            )


def test_every_capability_operation_uses_only_its_frozen_activation_phases(
    contract: dict[str, Any],
) -> None:
    allowed = {
        tuple(key.split(":")): set(phases)
        for key, phases in contract["activation_phases"].items()
    }
    for capability in OrchestratorCapability:
        for operation in CapabilityOperation:
            for phase in OrchestrationPhase:
                assert can_activate_in_phase(capability, operation, phase) is (
                    phase.value
                    in allowed.get(
                        (capability.value, operation.value),
                        set(),
                    )
                )


def test_initial_state_is_immutable_stable_and_pre_plan_only(
    scope: CapabilityScope,
) -> None:
    state = initialize_orchestration(
        run_id=RUN_ID,
        plan_id=PLAN_ID,
        policy_version=ORCHESTRATION_POLICY_VERSION,
        research_request=_research_request(scope),
    )
    serialized = orchestration_state_json(state)
    restored = OrchestrationState.model_validate_json(serialized)

    assert orchestration_state_json(restored) == serialized
    assert state.phase is OrchestrationPhase.REQUEST_SCOPE
    assert {node.capability for node in state.capabilities} == {
        OrchestratorCapability.INTENT_CLASSIFIER,
        OrchestratorCapability.ENTITY_RESOLVER,
    }
    assert all(
        node.state is CapabilityWorkState.QUEUED for node in state.capabilities
    )
    with pytest.raises(ValidationError):
        state.phase = OrchestrationPhase.INTERPRETATION  # type: ignore[misc]


def test_phase_cannot_skip_regress_or_bypass_plan_approval(
    scope: CapabilityScope,
) -> None:
    state = initialize_orchestration(
        run_id=RUN_ID,
        plan_id=PLAN_ID,
        policy_version=ORCHESTRATION_POLICY_VERSION,
        research_request=_research_request(scope),
    )
    with pytest.raises(ValueError, match="one step"):
        advance_phase(state, OrchestrationPhase.PLAN_APPROVAL)
    state = advance_phase(state, OrchestrationPhase.INTERPRETATION)
    with pytest.raises(ValueError, match="approve_work_plan"):
        advance_phase(state, OrchestrationPhase.PLAN_APPROVAL)
    with pytest.raises(ValueError, match="one step"):
        advance_phase(state, OrchestrationPhase.REQUEST_SCOPE)


def test_plan_approval_requires_terminal_interpretation_and_acyclic_complete_plan(
    scope: CapabilityScope,
) -> None:
    research = _research_request(scope)
    state = advance_phase(
        initialize_orchestration(
            run_id=RUN_ID,
            plan_id=PLAN_ID,
            policy_version=ORCHESTRATION_POLICY_VERSION,
            research_request=research,
        ),
        OrchestrationPhase.INTERPRETATION,
    )
    with pytest.raises(ValueError, match="must be terminal"):
        approve_work_plan(
            state,
            approved_plan=_approved_plan(scope),
            capability_nodes=_capability_node_plans(),
            sections=(_section(),),
        )

    cycle_nodes = list(_capability_node_plans())
    evidence_index = next(
        index
        for index, node in enumerate(cycle_nodes)
        if node.node_id == EVIDENCE_VERIFIER_NODE
    )
    cycle_nodes[evidence_index] = cycle_nodes[evidence_index].model_copy(
        update={"dependencies": (CLAIM_VERIFIER_NODE,)}
    )
    with pytest.raises(ValueError, match="cycle"):
        approve_work_plan(
            _interpreted_state(scope),
            approved_plan=_approved_plan(scope),
            capability_nodes=tuple(cycle_nodes),
            sections=(_section(),),
        )

    roles = _plan_roles()
    roles[OrchestratorCapability.REGULATORY_RETRIEVER] = (
        ParticipationClass.SKIPPED
    )
    dependencies = _plan_dependencies()
    dependencies[OrchestratorCapability.REGULATORY_RETRIEVER] = ()
    skipped_nodes = list(_capability_node_plans(roles))
    evidence_index = next(
        index
        for index, node in enumerate(skipped_nodes)
        if node.node_id == EVIDENCE_VERIFIER_NODE
    )
    skipped_nodes[evidence_index] = skipped_nodes[evidence_index].model_copy(
        update={
            "dependencies": (
                OrchestratorCapability.REGULATORY_RETRIEVER.value,
            )
        }
    )
    with pytest.raises(ValueError, match="dependencies cannot be skipped"):
        approve_work_plan(
            _interpreted_state(scope),
            approved_plan=_approved_plan(
                scope,
                dependencies=dependencies,
                roles=roles,
            ),
            capability_nodes=tuple(skipped_nodes),
            sections=(_section(),),
        )


def test_clearly_general_plan_can_skip_entity_bootstrap(
    scope: CapabilityScope,
) -> None:
    research = _research_request(scope)
    state = initialize_orchestration(
        run_id=RUN_ID,
        plan_id=PLAN_ID,
        policy_version=ORCHESTRATION_POLICY_VERSION,
        research_request=research,
        entity_participation=ParticipationClass.SKIPPED,
    )
    state = advance_phase(state, OrchestrationPhase.INTERPRETATION)
    intent_request = _request(
        OrchestratorCapability.INTENT_CLASSIFIER,
        ParticipationClass.MANDATORY,
        scope,
        (research,),
    )
    state = activate_capability(
        state,
        OrchestratorCapability.INTENT_CLASSIFIER.value,
        intent_request,
    )
    state = finish_capability(
        state,
        OrchestratorCapability.INTENT_CLASSIFIER.value,
        _result(
            OrchestratorCapability.INTENT_CLASSIFIER,
            CapabilityTerminalState.SATISFIED,
            scope,
            (_interpretation_artifact(scope),),
        ),
    )
    roles = {
        capability: ParticipationClass.SKIPPED
        for capability in OrchestratorCapability
    }
    roles[OrchestratorCapability.INTENT_CLASSIFIER] = ParticipationClass.MANDATORY
    roles[OrchestratorCapability.GENERAL_AI] = ParticipationClass.MANDATORY
    roles[OrchestratorCapability.RESPONSE_COMPOSER] = ParticipationClass.MANDATORY
    dependencies = {
        capability: ()
        for capability in OrchestratorCapability
    }
    dependencies[OrchestratorCapability.RESPONSE_COMPOSER] = (
        OrchestratorCapability.GENERAL_AI,
    )
    section = SectionNode(
        section_id="section-general",
        atomic_question_id="question-1",
        section_key="official_sources",
        required=True,
        knowledge_mode=KnowledgeMode.GENERAL_AI,
        provenance_class=ProvenanceClass.GENERAL_AI_KNOWLEDGE,
    )
    general_nodes = tuple(
        CapabilityNodePlan(
            node_id=capability.value,
            capability=capability,
            participation=roles[capability],
            atomic_question_id=(
                "question-1"
                if capability
                in {
                    OrchestratorCapability.GENERAL_AI,
                    OrchestratorCapability.RESPONSE_COMPOSER,
                }
                else None
            ),
            section_key=(
                "official_sources"
                if capability
                in {
                    OrchestratorCapability.GENERAL_AI,
                    OrchestratorCapability.RESPONSE_COMPOSER,
                }
                else None
            ),
            provenance_class=(
                ProvenanceClass.GENERAL_AI_KNOWLEDGE
                if capability
                in {
                    OrchestratorCapability.GENERAL_AI,
                    OrchestratorCapability.RESPONSE_COMPOSER,
                }
                else None
            ),
            dependencies=(
                (OrchestratorCapability.GENERAL_AI.value,)
                if capability is OrchestratorCapability.RESPONSE_COMPOSER
                else ()
            ),
        )
        for capability in OrchestratorCapability
    )

    approved = approve_work_plan(
        state,
        approved_plan=_approved_plan(
            scope,
            dependencies=dependencies,
            roles=roles,
            mode_eligibility=(KnowledgeMode.GENERAL_AI,),
        ),
        capability_nodes=general_nodes,
        sections=(section,),
    )

    entity = next(
        node
        for node in approved.capabilities
        if node.capability is OrchestratorCapability.ENTITY_RESOLVER
    )
    assert entity.state is CapabilityTerminalState.SKIPPED


def test_capability_instances_are_isolated_by_question_section_and_lane(
    scope: CapabilityScope,
) -> None:
    expanded_scope = scope.model_copy(
        update={"section_keys": ("official_sources", "timeline")}
    )
    nodes = (
        *_capability_node_plans(),
        CapabilityNodePlan(
            node_id="regulatory:question-1:timeline",
            capability=OrchestratorCapability.REGULATORY_RETRIEVER,
            participation=ParticipationClass.MANDATORY,
            atomic_question_id="question-1",
            section_key="timeline",
            provenance_class=ProvenanceClass.INTERNAL_REGULATORY_CORPUS,
            dependencies=(OrchestratorCapability.ENTITY_RESOLVER.value,),
        ),
    )
    timeline = SectionNode(
        section_id="section-timeline",
        atomic_question_id="question-1",
        section_key="timeline",
        required=False,
        knowledge_mode=KnowledgeMode.GROUNDED_REGULATORY,
        provenance_class=ProvenanceClass.INTERNAL_REGULATORY_CORPUS,
    )

    state = approve_work_plan(
        _interpreted_state(expanded_scope),
        approved_plan=_approved_plan(expanded_scope),
        capability_nodes=nodes,
        sections=(_section(), timeline),
    )

    regulatory_nodes = tuple(
        node
        for node in state.capabilities
        if node.capability is OrchestratorCapability.REGULATORY_RETRIEVER
    )
    assert {node.section_key for node in regulatory_nodes} == {
        "official_sources",
        "timeline",
    }
    assert len({node.node_id for node in regulatory_nodes}) == 2
    state = advance_phase(state, OrchestrationPhase.EVIDENCE_FAN_OUT)
    plan = state.approved_plan
    assert plan is not None
    resolution = next(
        artifact
        for artifact in state.admitted_artifacts
        if artifact.artifact_id == "resolution-1"
    )
    broad_request = _request(
        OrchestratorCapability.REGULATORY_RETRIEVER,
        ParticipationClass.MANDATORY,
        expanded_scope,
        (plan, resolution),
    )
    with pytest.raises(ValueError, match="scope"):
        activate_capability(
            state,
            "regulatory:question-1:timeline",
            broad_request,
        )
    timeline_scope = expanded_scope.model_copy(
        update={"section_keys": ("timeline",)}
    )
    timeline_request = _request(
        OrchestratorCapability.REGULATORY_RETRIEVER,
        ParticipationClass.MANDATORY,
        timeline_scope,
        (plan, resolution),
    )
    activated = activate_capability(
        state,
        "regulatory:question-1:timeline",
        timeline_request,
    )
    assert next(
        node
        for node in activated.capabilities
        if node.node_id == "regulatory:question-1:timeline"
    ).state is CapabilityWorkState.ACTIVE


def test_capability_activation_requires_admitted_inputs_and_terminal_dependencies(
    scope: CapabilityScope,
) -> None:
    state = _approved_state(scope)
    plan = state.approved_plan
    assert plan is not None
    resolution = next(
        artifact
        for artifact in state.admitted_artifacts
        if artifact.artifact_id == "resolution-1"
    )
    state = advance_phase(state, OrchestrationPhase.EVIDENCE_FAN_OUT)
    composer_request = _request(
        OrchestratorCapability.RESPONSE_COMPOSER,
        ParticipationClass.MANDATORY,
        scope,
        (plan,),
    )
    with pytest.raises(ValueError, match="current phase"):
        activate_capability(state, COMPOSER_NODE, composer_request)
    later = advance_phase(state, OrchestrationPhase.EVIDENCE_ADMISSION)
    later = advance_phase(
        later,
        OrchestrationPhase.STRUCTURED_TRANSFORMATIONS,
    )
    later = advance_phase(later, OrchestrationPhase.SECTION_COMPOSITION)
    with pytest.raises(ValueError, match="dependency is not terminal"):
        activate_capability(later, COMPOSER_NODE, composer_request)

    unadmitted = _evidence(scope).model_copy(
        update={"artifact_id": "foreign-evidence"}
    )
    regulatory_request = _request(
        OrchestratorCapability.REGULATORY_RETRIEVER,
        ParticipationClass.MANDATORY,
        scope,
        (plan, resolution),
    ).model_copy(
        update={"input_artifacts": (plan, resolution, unadmitted)}
    )
    with pytest.raises(ValueError, match="unadmitted input"):
        activate_capability(state, REGULATORY_NODE, regulatory_request)


def test_full_grounded_lifecycle_retains_artifacts_and_completes(
    scope: CapabilityScope,
) -> None:
    state = _complete_state_before_finalization(scope)
    completed = finalize_orchestration(state)

    assert completed.terminal_state is RunTerminalState.COMPLETE
    assert all(
        node.state not in {CapabilityWorkState.QUEUED, CapabilityWorkState.ACTIVE}
        for node in completed.capabilities
    )
    assert completed.sections[0].state is SectionTerminalState.READY
    assert completed.sections[0].material_claim_ids == ("claim-1",)
    assert completed.sections[0].terminal_verification_claim_ids == ("claim-1",)
    verifier_nodes = tuple(
        node
        for node in completed.capabilities
        if node.capability is OrchestratorCapability.CITATION_VERIFIER
    )
    assert {node.operation for node in verifier_nodes} == {
        CapabilityOperation.EVIDENCE_INTEGRITY,
        CapabilityOperation.CLAIM_SUPPORT,
    }
    assert all(
        node.atomic_question_id == "question-1"
        and node.section_key == "official_sources"
        and node.provenance_class
        is ProvenanceClass.INTERNAL_REGULATORY_CORPUS
        for node in verifier_nodes
    )
    assert {
        artifact.artifact_id for artifact in completed.admitted_artifacts
    } >= {
        "research-1",
        "interpretation-1",
        "resolution-1",
        "approved-plan-1",
        "evidence-1",
        "claim-1",
        "section-draft-1",
        "verification-1",
    }
    with pytest.raises(ValueError, match="immutable"):
        transition_section(
            completed,
            "section-1",
            SectionTerminalState.CANCELLED,
        )


def test_grounded_section_cannot_be_ready_before_material_claim_verification(
    scope: CapabilityScope,
) -> None:
    state = _approved_state(scope)
    values = state.sections[0].model_dump(mode="python")
    values["state"] = SectionWorkState.VERIFYING
    values["material_claim_ids"] = ("claim-1",)
    section = SectionNode.model_validate(values)
    state = _replace_sections(state, (section,))

    with pytest.raises(ValidationError, match="must be terminal"):
        transition_section(state, "section-1", SectionTerminalState.READY)


def test_required_section_cannot_be_omitted_and_terminal_state_is_monotonic(
    scope: CapabilityScope,
) -> None:
    state = _approved_state(scope)
    state = transition_section(
        state,
        "section-1",
        SectionWorkState.COLLECTING,
    )
    state = transition_section(state, "section-1", SectionWorkState.EMPTY)
    with pytest.raises(ValueError, match="cannot be omitted"):
        transition_section(state, "section-1", SectionTerminalState.OMITTED)
    terminal = transition_section(
        state,
        "section-1",
        SectionTerminalState.EMPTY_BY_EVIDENCE,
    )
    with pytest.raises(ValueError, match="forbidden"):
        transition_section(
            terminal,
            "section-1",
            SectionTerminalState.READY,
        )


def test_nonterminal_optional_section_does_not_block_core_merge(
    scope: CapabilityScope,
) -> None:
    completed_phase = _complete_state_before_finalization(scope)
    optional = SectionNode(
        section_id="section-news",
        atomic_question_id="question-1",
        section_key="latest_news",
        required=False,
        knowledge_mode=KnowledgeMode.LIVE_INTELLIGENCE,
        provenance_class=ProvenanceClass.LIVE_WEB_SOURCES,
        state=SectionWorkState.COLLECTING,
    )
    values = completed_phase.model_dump(mode="python")
    values["phase"] = OrchestrationPhase.VERIFICATION
    values["sections"] = (completed_phase.sections[0], optional)
    state = OrchestrationState.model_validate(values)

    state = advance_phase(state, OrchestrationPhase.DETERMINISTIC_MERGE)
    state = advance_phase(state, OrchestrationPhase.COMPLETION)
    with pytest.raises(ValueError, match="Every response section"):
        finalize_orchestration(state)
    state = transition_section(
        state,
        "section-news",
        SectionTerminalState.CANCELLED,
    )

    assert finalize_orchestration(state).terminal_state is RunTerminalState.COMPLETE


@pytest.mark.parametrize(
    ("section_state", "expected"),
    [
        (SectionTerminalState.READY, RunTerminalState.COMPLETE),
        (SectionTerminalState.DEGRADED, RunTerminalState.DEGRADED_COMPLETE),
        (
            SectionTerminalState.NEEDS_CLARIFICATION,
            RunTerminalState.CLARIFICATION_RESULT,
        ),
        (SectionTerminalState.CANCELLED, RunTerminalState.CANCELLED),
    ],
)
def test_run_finalizer_derives_every_terminal_product_state(
    scope: CapabilityScope,
    section_state: SectionTerminalState,
    expected: RunTerminalState,
) -> None:
    state = _complete_state_before_finalization(scope)
    section = SectionNode(
        section_id="section-1",
        atomic_question_id="question-1",
        section_key="official_sources",
        required=True,
        knowledge_mode=KnowledgeMode.GROUNDED_REGULATORY,
        provenance_class=ProvenanceClass.INTERNAL_REGULATORY_CORPUS,
        state=section_state,
        material_claim_ids=("claim-1",),
        terminal_verification_claim_ids=("claim-1",),
    )
    state = _replace_sections(state, (section,))

    assert finalize_orchestration(state).terminal_state is expected


def test_early_material_ambiguity_finishes_as_clarification(
    scope: CapabilityScope,
) -> None:
    state = _interpreted_state(
        scope,
        entity_state=CapabilityTerminalState.AMBIGUOUS,
    )
    terminal = finalize_clarification(state)

    assert terminal.terminal_state is RunTerminalState.CLARIFICATION_RESULT
    with pytest.raises(ValueError, match="immutable"):
        approve_work_plan(
            terminal,
            approved_plan=_approved_plan(scope),
            capability_nodes=_capability_node_plans(),
            sections=(_section(),),
        )


def test_finalization_refuses_nonterminal_sections_capabilities_and_wrong_phase(
    scope: CapabilityScope,
) -> None:
    state = _approved_state(scope)
    with pytest.raises(ValueError, match="completion phase"):
        finalize_orchestration(state)

    values = _complete_state_before_finalization(scope).model_dump(mode="python")
    capabilities = list(values["capabilities"])
    capabilities[2] = CapabilityNode(
        node_id=REGULATORY_NODE,
        capability=OrchestratorCapability.REGULATORY_RETRIEVER,
        participation=ParticipationClass.MANDATORY,
        atomic_question_id="question-1",
        section_key="official_sources",
        provenance_class=ProvenanceClass.INTERNAL_REGULATORY_CORPUS,
        dependencies=(OrchestratorCapability.ENTITY_RESOLVER.value,),
        state=CapabilityWorkState.QUEUED,
    )
    values["capabilities"] = tuple(capabilities)
    with pytest.raises(ValidationError, match="Terminal runs|active capabilities"):
        OrchestrationState.model_validate(
            {
                **values,
                "terminal_state": RunTerminalState.COMPLETE,
            }
        )

    complete_values = _complete_state_before_finalization(scope).model_dump(
        mode="python"
    )
    complete_values["terminal_state"] = RunTerminalState.DEGRADED_COMPLETE
    with pytest.raises(ValidationError, match="does not match"):
        OrchestrationState.model_validate(complete_values)
