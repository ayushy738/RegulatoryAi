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
    ARTIFACT_ADAPTER,
    ARTIFACT_PRODUCERS,
    CAPABILITY_CONTRACTS,
    CAPABILITY_RESULT_ADAPTER,
    ORCHESTRATION_POLICY_VERSION,
    ORCHESTRATION_SCHEMA_VERSION,
    ApprovedWorkPlanPayload,
    ArtifactAdapter,
    ArtifactAttribute,
    ArtifactEnvelope,
    ArtifactKind,
    ArtifactProducer,
    CandidateClaimPayload,
    CapabilityDependency,
    CapabilityParticipation,
    CapabilityRequest,
    CapabilityResult,
    CapabilityScope,
    CapabilityTerminalState,
    CapabilityTiming,
    ConfidenceSignals,
    ContentDerivation,
    EvidenceUnitPayload,
    FollowUpCandidate,
    FollowUpCandidatesPayload,
    GeneralKnowledgeUnitPayload,
    InterpretationResultPayload,
    OrchestratorCapability,
    ParticipationClass,
    ProvenanceClass,
    ProvenanceLineage,
    ResearchRequestPayload,
    ResolutionSetPayload,
    SectionContentBlock,
    SectionDraftPayload,
    SectionTerminalState,
    SourceIdentity,
    StructuredFactPayload,
    TimelineEventPayload,
    TransformationStep,
    VerificationResultPayload,
    VerificationStatus,
    artifact_json,
    capability_result_json,
    validate_capability_exchange,
)

CONTRACT_PATH = Path(__file__).parent / "fixtures" / "ask_orchestration_contract.json"
REQUEST_ID = UUID("11111111-1111-4111-8111-111111111111")
RUN_ID = UUID("22222222-2222-4222-8222-222222222222")
STARTED_AT = datetime(2026, 7, 27, 8, 0, tzinfo=UTC)


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


def _official_lineage() -> ProvenanceLineage:
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
        derivation=ContentDerivation.DIRECT,
        verification_status=VerificationStatus.SUPPORTED,
    )


def _official_evidence(scope: CapabilityScope) -> ArtifactEnvelope:
    return ArtifactEnvelope(
        artifact_id="evidence-1",
        producer=ArtifactProducer.REGULATORY_RETRIEVER,
        scope=scope,
        payload=EvidenceUnitPayload(
            excerpt="The regulated entity must submit the filing.",
            locator="section 4",
            match_reasons=("entity", "obligation"),
        ),
        provenance=_official_lineage(),
        confidence_signals=ConfidenceSignals(
            evidence_authority=1,
            retrieval_relevance=0.95,
            claim_coverage=0.8,
            reasons=("direct official provision",),
        ),
        ancestry=("plan-1", "resolution-1"),
        capability_status=CapabilityTerminalState.SATISFIED,
    )


def _timing() -> CapabilityTiming:
    return CapabilityTiming(
        started_at=STARTED_AT,
        completed_at=STARTED_AT + timedelta(milliseconds=125),
        duration_ms=125,
    )


def _derived_official_lineage(
    capability: OrchestratorCapability,
    input_artifact_id: str,
) -> ProvenanceLineage:
    return ProvenanceLineage(
        provenance_class=ProvenanceClass.INTERNAL_REGULATORY_CORPUS,
        knowledge_mode=KnowledgeMode.GROUNDED_REGULATORY,
        sources=_official_lineage().sources,
        derivation=ContentDerivation.SUMMARIZED,
        transformations=(
            TransformationStep(
                capability=capability,
                derivation=ContentDerivation.SUMMARIZED,
                input_artifact_ids=(input_artifact_id,),
                input_provenance=(
                    ProvenanceClass.INTERNAL_REGULATORY_CORPUS,
                ),
                output_provenance=(
                    ProvenanceClass.INTERNAL_REGULATORY_CORPUS
                ),
            ),
        ),
        verification_status=VerificationStatus.PENDING,
    )


def _all_artifacts(scope: CapabilityScope) -> tuple[ArtifactEnvelope, ...]:
    official_status = {"capability_status": CapabilityTerminalState.SATISFIED}
    return (
        ArtifactEnvelope(
            artifact_id="request-1",
            producer=ArtifactProducer.DECISION_ENGINE,
            scope=scope,
            payload=ResearchRequestPayload(
                query="What filing is required?",
                selected_object_ids=("entity-1",),
            ),
        ),
        ArtifactEnvelope(
            artifact_id="interpretation-1",
            producer=ArtifactProducer.INTENT_CLASSIFIER,
            scope=scope,
            payload=InterpretationResultPayload(
                primary_intent="compliance_question",
                atomic_questions=("What filing is required?",),
                audience="compliance manager",
                requested_form="compliance checklist",
                interpretation_confidence=0.95,
            ),
        ),
        ArtifactEnvelope(
            artifact_id="resolution-1",
            producer=ArtifactProducer.ENTITY_RESOLVER,
            scope=scope,
            payload=ResolutionSetPayload(
                canonical_entity_ids=("entity-1",),
                original_mentions=("regulated entity",),
                resolution_confidence=0.9,
            ),
        ),
        ArtifactEnvelope(
            artifact_id="plan-1",
            producer=ArtifactProducer.DECISION_ENGINE,
            scope=scope,
            payload=ApprovedWorkPlanPayload(
                plan_id="plan-1",
                capability_roles=(
                    CapabilityParticipation(
                        capability=OrchestratorCapability.REGULATORY_RETRIEVER,
                        participation=ParticipationClass.MANDATORY,
                    ),
                ),
                dependencies=(
                    CapabilityDependency(
                        capability=OrchestratorCapability.REGULATORY_RETRIEVER,
                    ),
                ),
                mode_eligibility=(KnowledgeMode.GROUNDED_REGULATORY,),
                budget_profile="focused_grounded",
            ),
        ),
        _official_evidence(scope),
        ArtifactEnvelope(
            artifact_id="fact-1",
            producer=ArtifactProducer.KNOWLEDGE_GRAPH,
            scope=scope,
            payload=StructuredFactPayload(
                subject_id="entity-1",
                relationship="must_submit",
                object_id_or_value="filing-1",
                qualifiers=(
                    ArtifactAttribute(key="frequency", value="annual"),
                ),
                extraction_confidence=0.9,
            ),
            provenance=_derived_official_lineage(
                OrchestratorCapability.KNOWLEDGE_GRAPH,
                "evidence-1",
            ),
            ancestry=("evidence-1",),
            **official_status,
        ),
        ArtifactEnvelope(
            artifact_id="event-1",
            producer=ArtifactProducer.TIMELINE_BUILDER,
            scope=scope,
            payload=TimelineEventPayload(
                label="Filing deadline",
                event_type="compliance_deadline",
                date_value=STARTED_AT,
                date_semantic=TimeDimension.COMPLIANCE_DEADLINE,
                date_confidence=0.9,
            ),
            provenance=_derived_official_lineage(
                OrchestratorCapability.TIMELINE_BUILDER,
                "evidence-1",
            ),
            ancestry=("evidence-1",),
            **official_status,
        ),
        ArtifactEnvelope(
            artifact_id="general-1",
            producer=ArtifactProducer.GENERAL_AI,
            scope=scope,
            payload=GeneralKnowledgeUnitPayload(
                content="General educational orientation.",
                required_disclosure="General AI knowledge.",
            ),
            provenance=ProvenanceLineage(
                provenance_class=ProvenanceClass.GENERAL_AI_KNOWLEDGE,
                knowledge_mode=KnowledgeMode.GENERAL_AI,
                derivation=ContentDerivation.GENERATED,
                verification_status=VerificationStatus.NOT_APPLICABLE,
            ),
            ancestry=("plan-1",),
            **official_status,
        ),
        ArtifactEnvelope(
            artifact_id="claim-1",
            producer=ArtifactProducer.RESPONSE_COMPOSER,
            scope=scope,
            payload=CandidateClaimPayload(
                claim_text="The entity must submit an annual filing.",
                material=True,
                supporting_artifact_ids=("evidence-1",),
            ),
            provenance=_derived_official_lineage(
                OrchestratorCapability.RESPONSE_COMPOSER,
                "evidence-1",
            ),
            ancestry=("evidence-1",),
            **official_status,
        ),
        ArtifactEnvelope(
            artifact_id="verification-1",
            producer=ArtifactProducer.CITATION_VERIFIER,
            scope=scope,
            payload=VerificationResultPayload(
                target_artifact_id="claim-1",
                target_kind=ArtifactKind.CANDIDATE_CLAIM,
                status=VerificationStatus.SUPPORTED,
                reasons=("The source directly states the obligation.",),
            ),
            ancestry=("claim-1", "evidence-1"),
        ),
        ArtifactEnvelope(
            artifact_id="section-1",
            producer=ArtifactProducer.RESPONSE_COMPOSER,
            scope=scope,
            payload=SectionDraftPayload(
                section_type="compliance_checklist",
                title="Obligations",
                content_blocks=(
                    SectionContentBlock(
                        block_type="obligation",
                        content="Submit the annual filing.",
                    ),
                ),
                candidate_claim_ids=("claim-1",),
            ),
            provenance=_derived_official_lineage(
                OrchestratorCapability.RESPONSE_COMPOSER,
                "claim-1",
            ),
            ancestry=("claim-1", "evidence-1"),
            **official_status,
        ),
        ArtifactEnvelope(
            artifact_id="follow-ups-1",
            producer=ArtifactProducer.FOLLOW_UP_GENERATOR,
            scope=scope,
            payload=FollowUpCandidatesPayload(),
        ),
        ArtifactEnvelope(
            artifact_id="completion-1",
            producer=ArtifactProducer.ORCHESTRATOR,
            scope=scope,
            payload={
                "kind": ArtifactKind.COMPLETION_SUMMARY,
                "sections": (
                    {
                        "section_key": "official_sources",
                        "state": SectionTerminalState.READY,
                        "knowledge_mode": KnowledgeMode.GROUNDED_REGULATORY,
                        "source_coverage": 1,
                        "confidence_score": 0.9,
                    },
                ),
            },
        ),
    )


def test_fixture_freezes_every_orchestration_contract_variant(
    contract: dict[str, Any],
) -> None:
    assert contract["schema_version"] == ORCHESTRATION_SCHEMA_VERSION
    assert contract["policy_version"] == ORCHESTRATION_POLICY_VERSION
    assert contract["participation_classes"] == [
        value.value for value in ParticipationClass
    ]
    assert contract["capability_terminal_states"] == [
        value.value for value in CapabilityTerminalState
    ]
    assert contract["section_terminal_states"] == [
        value.value for value in SectionTerminalState
    ]
    assert contract["artifact_kinds"] == [value.value for value in ArtifactKind]
    assert contract["provenance_classes"] == [
        value.value for value in ProvenanceClass
    ]
    assert contract["content_derivations"] == [
        value.value for value in ContentDerivation
    ]
    assert contract["verification_statuses"] == [
        value.value for value in VerificationStatus
    ]


def test_registry_declares_every_capability_and_frozen_output(
    contract: dict[str, Any],
) -> None:
    expected = {
        OrchestratorCapability(capability): tuple(
            ArtifactKind(kind) for kind in outputs
        )
        for capability, outputs in contract["capabilities"].items()
    }
    assert set(CAPABILITY_CONTRACTS) == set(OrchestratorCapability)
    assert {
        capability: declaration.allowed_outputs
        for capability, declaration in CAPABILITY_CONTRACTS.items()
    } == expected
    assert set(ARTIFACT_PRODUCERS) == set(ArtifactKind)
    with pytest.raises(TypeError):
        CAPABILITY_CONTRACTS[OrchestratorCapability.GENERAL_AI] = (  # type: ignore[index]
            CAPABILITY_CONTRACTS[OrchestratorCapability.GENERAL_AI]
        )


def test_official_artifact_round_trip_is_stable_and_immutable(
    scope: CapabilityScope,
) -> None:
    artifact = _official_evidence(scope)
    serialized = artifact_json(artifact)

    assert artifact_json(ARTIFACT_ADAPTER.validate_json(serialized)) == serialized
    assert json.loads(serialized)["payload"]["kind"] == "evidence_unit"
    with pytest.raises(ValidationError):
        artifact.artifact_id = "changed"  # type: ignore[misc]
    with pytest.raises(TypeError):
        artifact.ancestry[0] = "changed"  # type: ignore[index]


def test_every_shared_artifact_variant_has_a_stable_typed_round_trip(
    scope: CapabilityScope,
) -> None:
    artifacts = _all_artifacts(scope)

    assert {artifact.payload.kind for artifact in artifacts} == set(ArtifactKind)
    for artifact in artifacts:
        serialized = artifact_json(artifact)
        restored = ARTIFACT_ADAPTER.validate_json(serialized)

        assert type(restored.payload) is type(artifact.payload)
        assert artifact_json(restored) == serialized


def test_general_ai_artifact_has_disclosure_without_source_identity(
    scope: CapabilityScope,
) -> None:
    artifact = ArtifactEnvelope(
        artifact_id="general-1",
        producer=ArtifactProducer.GENERAL_AI,
        scope=scope,
        payload=GeneralKnowledgeUnitPayload(
            content="General educational orientation.",
            assumptions=("No official match was found.",),
            uncertainty_statements=("This is not legal advice.",),
            required_disclosure="No relevant documents were found in the library.",
        ),
        provenance=ProvenanceLineage(
            provenance_class=ProvenanceClass.GENERAL_AI_KNOWLEDGE,
            knowledge_mode=KnowledgeMode.GENERAL_AI,
            derivation=ContentDerivation.GENERATED,
            verification_status=VerificationStatus.NOT_APPLICABLE,
        ),
        confidence_signals=ConfidenceSignals(
            critical_input_ceiling=0.5,
            reasons=("healthy official no-match",),
        ),
        ancestry=("plan-1",),
        capability_status=CapabilityTerminalState.SATISFIED,
    )

    assert artifact.provenance is not None
    assert artifact.provenance.sources == ()
    assert "source_id" not in artifact_json(artifact)


@pytest.mark.parametrize(
    "mutation",
    [
        {
            "provenance_class": ProvenanceClass.GENERAL_AI_KNOWLEDGE,
            "knowledge_mode": KnowledgeMode.GENERAL_AI,
            "sources": (
                SourceIdentity(
                    source_id="source-1",
                    provenance_class=ProvenanceClass.INTERNAL_REGULATORY_CORPUS,
                    title="Fabricated source",
                ),
            ),
            "derivation": ContentDerivation.GENERATED,
        },
        {
            "provenance_class": ProvenanceClass.INTERNAL_REGULATORY_CORPUS,
            "knowledge_mode": KnowledgeMode.LIVE_INTELLIGENCE,
            "sources": (),
            "derivation": ContentDerivation.DIRECT,
        },
        {
            "provenance_class": ProvenanceClass.LIVE_WEB_SOURCES,
            "knowledge_mode": KnowledgeMode.LIVE_INTELLIGENCE,
            "sources": (),
            "derivation": ContentDerivation.DIRECT,
        },
    ],
)
def test_provenance_lane_violations_fail_closed(
    mutation: dict[str, Any],
) -> None:
    with pytest.raises(ValidationError):
        ProvenanceLineage.model_validate(mutation)


def test_live_source_requires_complete_publisher_and_time_identity() -> None:
    with pytest.raises(ValidationError, match="publisher, publication, and retrieval"):
        SourceIdentity(
            source_id="live-1",
            provenance_class=ProvenanceClass.LIVE_WEB_SOURCES,
            title="Live report",
            issuer_or_publisher="Publisher",
            publication_at=STARTED_AT,
        )
    with pytest.raises(ValidationError, match="timezone"):
        SourceIdentity(
            source_id="live-1",
            provenance_class=ProvenanceClass.LIVE_WEB_SOURCES,
            title="Live report",
            issuer_or_publisher="Publisher",
            publication_at=STARTED_AT.replace(tzinfo=None),
            retrieved_at=STARTED_AT,
        )


def test_transformation_lineage_cannot_upgrade_or_hide_inputs(
    scope: CapabilityScope,
) -> None:
    with pytest.raises(ValidationError, match="increase provenance authority"):
        TransformationStep(
            capability=OrchestratorCapability.RESPONSE_COMPOSER,
            derivation=ContentDerivation.SUMMARIZED,
            input_artifact_ids=("live-1",),
            input_provenance=(ProvenanceClass.LIVE_WEB_SOURCES,),
            output_provenance=ProvenanceClass.INTERNAL_REGULATORY_CORPUS,
        )

    lineage = ProvenanceLineage(
        provenance_class=ProvenanceClass.INTERNAL_REGULATORY_CORPUS,
        knowledge_mode=KnowledgeMode.GROUNDED_REGULATORY,
        sources=_official_lineage().sources,
        derivation=ContentDerivation.SUMMARIZED,
        transformations=(
            TransformationStep(
                capability=OrchestratorCapability.RESPONSE_COMPOSER,
                derivation=ContentDerivation.SUMMARIZED,
                input_artifact_ids=("evidence-1",),
                input_provenance=(
                    ProvenanceClass.INTERNAL_REGULATORY_CORPUS,
                ),
                output_provenance=(
                    ProvenanceClass.INTERNAL_REGULATORY_CORPUS
                ),
            ),
        ),
    )
    with pytest.raises(ValidationError, match="present in artifact ancestry"):
        ArtifactEnvelope(
            artifact_id="claim-1",
            producer=ArtifactProducer.RESPONSE_COMPOSER,
            scope=scope,
            payload=CandidateClaimPayload(
                claim_text="A grounded claim.",
                material=True,
            ),
            provenance=lineage,
            capability_status=CapabilityTerminalState.SATISFIED,
        )


def test_artifact_refuses_wrong_authority_missing_lineage_and_unknown_fields(
    scope: CapabilityScope,
) -> None:
    evidence = _official_evidence(scope)
    invalid = evidence.model_dump(mode="json")
    invalid["producer"] = ArtifactProducer.RESPONSE_COMPOSER
    with pytest.raises(ValidationError, match="not authoritative"):
        ArtifactEnvelope.model_validate(invalid)
    invalid = evidence.model_dump(mode="json")
    invalid["unexpected"] = True
    with pytest.raises(ValidationError, match="Extra inputs"):
        ARTIFACT_ADAPTER.validate_python(invalid)
    invalid = evidence.model_dump(mode="json")
    invalid["provenance"] = None
    with pytest.raises(ValidationError, match="require provenance"):
        ARTIFACT_ADAPTER.validate_python(invalid)


def test_candidate_claim_support_must_be_admitted_ancestry(
    scope: CapabilityScope,
) -> None:
    with pytest.raises(ValidationError, match="support must be present"):
        ArtifactEnvelope(
            artifact_id="claim-1",
            producer=ArtifactProducer.RESPONSE_COMPOSER,
            scope=scope,
            payload=CandidateClaimPayload(
                claim_text="A grounded claim.",
                material=True,
                supporting_artifact_ids=("evidence-1",),
            ),
            provenance=ProvenanceLineage(
                provenance_class=ProvenanceClass.INTERNAL_REGULATORY_CORPUS,
                knowledge_mode=KnowledgeMode.GROUNDED_REGULATORY,
                sources=_official_lineage().sources,
                derivation=ContentDerivation.SUMMARIZED,
                transformations=(
                    TransformationStep(
                        capability=OrchestratorCapability.RESPONSE_COMPOSER,
                        derivation=ContentDerivation.SUMMARIZED,
                        input_artifact_ids=("evidence-1",),
                        input_provenance=(
                            ProvenanceClass.INTERNAL_REGULATORY_CORPUS,
                        ),
                        output_provenance=(
                            ProvenanceClass.INTERNAL_REGULATORY_CORPUS
                        ),
                    ),
                ),
            ),
            ancestry=("plan-1",),
            capability_status=CapabilityTerminalState.SATISFIED,
        )


def test_request_result_exchange_round_trip_and_scope_admission(
    scope: CapabilityScope,
) -> None:
    artifacts = {
        artifact.artifact_id: artifact for artifact in _all_artifacts(scope)
    }
    request = CapabilityRequest(
        request_id=REQUEST_ID,
        run_id=RUN_ID,
        plan_id="plan-1",
        capability=OrchestratorCapability.REGULATORY_RETRIEVER,
        participation=ParticipationClass.MANDATORY,
        scope=scope,
        input_artifacts=(artifacts["plan-1"], artifacts["resolution-1"]),
    )
    result = CapabilityResult(
        request_id=REQUEST_ID,
        run_id=RUN_ID,
        capability=OrchestratorCapability.REGULATORY_RETRIEVER,
        terminal_state=CapabilityTerminalState.SATISFIED,
        scope_echo=scope,
        artifacts=(_official_evidence(scope),),
        timing=_timing(),
    )

    validate_capability_exchange(request, result)
    serialized = capability_result_json(result)
    assert (
        capability_result_json(CAPABILITY_RESULT_ADAPTER.validate_json(serialized))
        == serialized
    )

    foreign_request = request.model_copy(
        update={"input_artifacts": (artifacts["plan-1"],)}
    )
    with pytest.raises(ValueError, match="exceeds admitted inputs"):
        validate_capability_exchange(foreign_request, result)
    wrong_kind_request = request.model_copy(
        update={"input_artifacts": (artifacts["request-1"],)}
    )
    with pytest.raises(ValueError, match="undeclared artifact kind"):
        validate_capability_exchange(wrong_kind_request, result)
    with pytest.raises(ValueError, match="identity"):
        validate_capability_exchange(
            request.model_copy(update={"request_id": UUID(int=3)}),
            result,
        )


@pytest.mark.parametrize(
    "terminal_state",
    list(CapabilityTerminalState),
)
def test_every_capability_terminal_state_has_distinct_valid_contract(
    terminal_state: CapabilityTerminalState,
    scope: CapabilityScope,
) -> None:
    failure = terminal_state in {
        CapabilityTerminalState.TIMED_OUT,
        CapabilityTerminalState.UNAVAILABLE,
        CapabilityTerminalState.INVALID_OUTPUT,
    }
    result = CapabilityResult(
        request_id=REQUEST_ID,
        run_id=RUN_ID,
        capability=OrchestratorCapability.REGULATORY_RETRIEVER,
        terminal_state=terminal_state,
        scope_echo=scope,
        timing=None if terminal_state is CapabilityTerminalState.SKIPPED else _timing(),
        safe_error_code="CAPABILITY_FAILURE" if failure else None,
    )

    assert result.terminal_state is terminal_state
    if terminal_state is CapabilityTerminalState.NO_MATCH:
        assert result.safe_error_code is None


def test_failure_and_skip_contracts_cannot_collapse_states(
    scope: CapabilityScope,
) -> None:
    base = {
        "request_id": REQUEST_ID,
        "run_id": RUN_ID,
        "capability": OrchestratorCapability.REGULATORY_RETRIEVER,
        "scope_echo": scope,
    }
    with pytest.raises(ValidationError, match="safe error code"):
        CapabilityResult(
            **base,
            terminal_state=CapabilityTerminalState.UNAVAILABLE,
            timing=_timing(),
        )
    with pytest.raises(ValidationError, match="Only failed"):
        CapabilityResult(
            **base,
            terminal_state=CapabilityTerminalState.NO_MATCH,
            timing=_timing(),
            safe_error_code="NO_MATCH",
        )
    with pytest.raises(ValidationError, match="Skipped results"):
        CapabilityResult(
            **base,
            terminal_state=CapabilityTerminalState.SKIPPED,
            timing=_timing(),
        )
    with pytest.raises(ValueError, match="must agree"):
        validate_capability_exchange(
            CapabilityRequest(
                request_id=REQUEST_ID,
                run_id=RUN_ID,
                plan_id="plan-1",
                capability=OrchestratorCapability.REGULATORY_RETRIEVER,
                participation=ParticipationClass.SKIPPED,
                scope=scope,
            ),
            CapabilityResult(
                **base,
                terminal_state=CapabilityTerminalState.NO_MATCH,
                timing=_timing(),
            ),
        )


def test_invalid_artifact_kind_status_confidence_and_timing_are_refused(
    scope: CapabilityScope,
) -> None:
    result_data = {
        "request_id": str(REQUEST_ID),
        "run_id": str(RUN_ID),
        "capability": "not_a_capability",
        "terminal_state": "satisfied",
        "scope_echo": scope.model_dump(mode="json"),
        "timing": _timing().model_dump(mode="json"),
    }
    with pytest.raises(ValidationError):
        CAPABILITY_RESULT_ADAPTER.validate_python(result_data)
    with pytest.raises(ValidationError):
        ConfidenceSignals(retrieval_relevance=1.01)
    with pytest.raises(ValidationError, match="Extra inputs"):
        ConfidenceSignals.model_validate({"final_label": "high"})
    with pytest.raises(ValidationError, match="cannot precede"):
        CapabilityTiming(
            started_at=STARTED_AT,
            completed_at=STARTED_AT - timedelta(seconds=1),
            duration_ms=1,
        )
    with pytest.raises(ValidationError, match="include a timezone"):
        CapabilityTiming(
            started_at=STARTED_AT.replace(tzinfo=None),
            completed_at=STARTED_AT,
            duration_ms=1,
        )
    other_scope = scope.model_copy(update={"section_keys": ("timeline",)})
    with pytest.raises(ValidationError, match="scope must match"):
        CapabilityResult(
            request_id=REQUEST_ID,
            run_id=RUN_ID,
            capability=OrchestratorCapability.REGULATORY_RETRIEVER,
            terminal_state=CapabilityTerminalState.SATISFIED,
            scope_echo=scope,
            artifacts=(
                _official_evidence(scope).model_copy(
                    update={"scope": other_scope}
                ),
            ),
            timing=_timing(),
        )


def test_follow_up_contract_allows_zero_or_three_to_five_unique_candidates() -> None:
    candidate = FollowUpCandidate(
        question="What changed?",
        expected_response_strategy="timeline",
        reason="A chronology gap remains.",
    )
    assert FollowUpCandidatesPayload().candidates == ()
    assert len(
        FollowUpCandidatesPayload(
            candidates=(
                candidate,
                candidate.model_copy(update={"question": "What applies?"}),
                candidate.model_copy(update={"question": "What is next?"}),
            )
        ).candidates
    ) == 3
    with pytest.raises(ValidationError, match="zero or three to five"):
        FollowUpCandidatesPayload(candidates=(candidate,))
    with pytest.raises(ValidationError, match="unique"):
        FollowUpCandidatesPayload(candidates=(candidate, candidate, candidate))


def test_adapter_protocol_is_a_boundary_seam_without_execution(
    scope: CapabilityScope,
) -> None:
    class ExistingEvidenceAdapter:
        def adapt(
            self,
            source: object,
            *,
            scope: CapabilityScope,
        ) -> ArtifactEnvelope:
            assert source == {"legacy_id": 7}
            return _official_evidence(scope)

    adapter: ArtifactAdapter = ExistingEvidenceAdapter()

    assert adapter.adapt({"legacy_id": 7}, scope=scope).artifact_id == "evidence-1"
