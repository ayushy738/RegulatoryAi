from __future__ import annotations

import json
from datetime import UTC, date, datetime

import pytest
from pydantic import ValidationError

from backend.ask.candidate_claims import (
    CANDIDATE_CLAIM_POLICY_VERSION,
    CandidateClaimBatchRequest,
    CandidateClaimBatchResult,
    CandidateClaimRejectionCode,
    admit_candidate_claims,
)
from backend.ask.evidence_admission import (
    EVIDENCE_ADMISSION_POLICY_VERSION,
    EvidenceAdmissionRequest,
    EvidenceExclusion,
    EvidenceRejectionCode,
    OfficialEvidenceAdmissionResult,
    OfficialEvidenceCandidate,
    admit_official_evidence,
    official_source_id,
)
from backend.ask.orchestration.contracts import (
    ArtifactEnvelope,
    ArtifactProducer,
    CandidateClaimPayload,
    CapabilityScope,
    CapabilityTerminalState,
    ConfidenceSignals,
    ContentDerivation,
    EvidenceUnitPayload,
    KnowledgeMode,
    OrchestratorCapability,
    ProvenanceClass,
    ProvenanceLineage,
    SectionDraftPayload,
    SourceIdentity,
    TimeDimension,
    TransformationStep,
    VerificationStatus,
)
from backend.rag.quality import (
    CanonicalEvidenceUnit,
    EvidenceScoreSnapshot,
    RetrievalMatchReason,
)

NOW = datetime(2026, 7, 27, 10, 0, tzinfo=UTC)
ISSUE_DATE = date(2023, 6, 1)


def _parent_scope() -> CapabilityScope:
    return CapabilityScope(
        atomic_question_ids=("question-1", "question-2"),
        section_keys=("official-one", "official-two"),
        entity_ids=("entity-1",),
        jurisdiction="India",
        stakeholder="regulated entity",
        time_scope="current",
        date_semantics=(TimeDimension.EFFECTIVE,),
        constraints=("official sources only",),
    )


def _scope(
    question_id: str = "question-1",
    section_key: str = "official-one",
    *,
    jurisdiction: str = "India",
    entity_ids: tuple[str, ...] = ("entity-1",),
    time_scope: str = "current",
) -> CapabilityScope:
    return CapabilityScope(
        atomic_question_ids=(question_id,),
        section_keys=(section_key,),
        entity_ids=entity_ids,
        jurisdiction=jurisdiction,
        stakeholder="regulated entity",
        time_scope=time_scope,
        date_semantics=(TimeDimension.EFFECTIVE,),
        constraints=("official sources only",),
    )


def _canonical_evidence(
    evidence_id: str = "evidence_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    *,
    document_id: int = 101,
    chunk_id: int = 301,
    question_id: str = "question-1",
) -> CanonicalEvidenceUnit:
    return CanonicalEvidenceUnit(
        evidence_unit_id=evidence_id,
        policy_version="ask-ai-retrieval-quality-v1",
        document_id=document_id,
        version_id=None,
        family_id=None,
        chunk_id=chunk_id,
        title=f"Official regulation {document_id}",
        source_url=f"https://official.example/regulation/{document_id}",
        issuer="Regulator",
        issue_date=ISSUE_DATE,
        text=f"Official provision from document {document_id}.",
        retrieval_sources=("vector",),
        match_reasons=(RetrievalMatchReason.VECTOR_SIMILARITY,),
        question_ids=(question_id,),
        scores=EvidenceScoreSnapshot(
            vector=0.94,
            keyword=0,
            graph=0,
            admitted_relevance=0.94,
        ),
    )


def _evidence_artifact(
    evidence: CanonicalEvidenceUnit,
    scope: CapabilityScope,
) -> ArtifactEnvelope:
    source = SourceIdentity(
        source_id=official_source_id(evidence),
        provenance_class=ProvenanceClass.INTERNAL_REGULATORY_CORPUS,
        title=evidence.title,
        uri=evidence.source_url,
        issuer_or_publisher=evidence.issuer,
        issue_at=datetime(2023, 6, 1, tzinfo=UTC),
    )
    return ArtifactEnvelope(
        artifact_id=evidence.evidence_unit_id,
        producer=ArtifactProducer.REGULATORY_RETRIEVER,
        scope=scope,
        payload=EvidenceUnitPayload(
            excerpt=evidence.text,
            locator=f"chunk {evidence.chunk_id}",
            match_reasons=("vector_similarity",),
        ),
        provenance=ProvenanceLineage(
            provenance_class=ProvenanceClass.INTERNAL_REGULATORY_CORPUS,
            knowledge_mode=KnowledgeMode.GROUNDED_REGULATORY,
            sources=(source,),
            derivation=ContentDerivation.DIRECT,
            verification_status=VerificationStatus.PENDING,
        ),
        confidence_signals=ConfidenceSignals(retrieval_relevance=0.94),
        ancestry=("plan-1",),
        capability_status=CapabilityTerminalState.SATISFIED,
    )


def _admission(
    evidence_id: str = "evidence_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    *,
    document_id: int = 101,
    chunk_id: int = 301,
    question_id: str = "question-1",
    section_key: str = "official-one",
) -> OfficialEvidenceAdmissionResult:
    scope = _scope(question_id, section_key)
    evidence = _canonical_evidence(
        evidence_id,
        document_id=document_id,
        chunk_id=chunk_id,
        question_id=question_id,
    )
    candidate = OfficialEvidenceCandidate(
        artifact=_evidence_artifact(evidence, scope),
        canonical_evidence=evidence,
    )
    result = admit_official_evidence(
        EvidenceAdmissionRequest(
            approved_scope=scope,
            evaluated_at=NOW,
            candidates=(candidate,),
        )
    )
    assert len(result.admitted) == 1
    return result


def _claim(
    claim_id: str = "claim-1",
    *,
    scope: CapabilityScope | None = None,
    support_ids: tuple[str, ...] = (
        "evidence_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    ),
    material: bool = True,
    text: str = "The filing is required.",
    transform_support_ids: tuple[str, ...] | None = None,
    transform_capability: OrchestratorCapability = (
        OrchestratorCapability.RESPONSE_COMPOSER
    ),
    verification_status: VerificationStatus = VerificationStatus.PENDING,
    capability_status: CapabilityTerminalState = (
        CapabilityTerminalState.SATISFIED
    ),
    conflicts: tuple[str, ...] = (),
) -> ArtifactEnvelope:
    claim_scope = scope or _scope()
    transformation_ids = transform_support_ids or support_ids or (
        "evidence_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    )
    source = SourceIdentity(
        source_id="document-101",
        provenance_class=ProvenanceClass.INTERNAL_REGULATORY_CORPUS,
        title="Official regulation 101",
        uri="https://official.example/regulation/101",
        issuer_or_publisher="Regulator",
        issue_at=datetime(2023, 6, 1, tzinfo=UTC),
    )
    lineage = ProvenanceLineage(
        provenance_class=ProvenanceClass.INTERNAL_REGULATORY_CORPUS,
        knowledge_mode=KnowledgeMode.GROUNDED_REGULATORY,
        sources=(source,),
        derivation=ContentDerivation.SUMMARIZED,
        transformations=(
            TransformationStep(
                capability=transform_capability,
                derivation=ContentDerivation.SUMMARIZED,
                input_artifact_ids=transformation_ids,
                input_provenance=(
                    ProvenanceClass.INTERNAL_REGULATORY_CORPUS,
                ),
                output_provenance=ProvenanceClass.INTERNAL_REGULATORY_CORPUS,
            ),
        ),
        verification_status=verification_status,
    )
    ancestry = tuple(dict.fromkeys((*support_ids, *transformation_ids, "plan-1")))
    return ArtifactEnvelope(
        artifact_id=claim_id,
        producer=ArtifactProducer.RESPONSE_COMPOSER,
        scope=claim_scope,
        payload=CandidateClaimPayload(
            claim_text=text,
            material=material,
            supporting_artifact_ids=support_ids,
        ),
        provenance=lineage,
        ancestry=ancestry,
        capability_status=capability_status,
        conflicts=conflicts,
    )


def _request(
    *claims: ArtifactEnvelope,
    admissions: tuple[OfficialEvidenceAdmissionResult, ...] | None = None,
    approved_scope: CapabilityScope | None = None,
) -> CandidateClaimBatchRequest:
    return CandidateClaimBatchRequest(
        approved_scope=approved_scope or _parent_scope(),
        evidence_admissions=(
            admissions if admissions is not None else (_admission(),)
        ),
        candidate_claims=claims,
    )


def _only_code(result: CandidateClaimBatchResult) -> CandidateClaimRejectionCode:
    assert result.accepted_claims == ()
    assert len(result.exclusions) == 1
    return result.exclusions[0].code


def test_material_mode_1_claim_referencing_admitted_evidence_is_accepted() -> None:
    claim = _claim()

    result = admit_candidate_claims(_request(claim))

    assert result.accepted_claims == (claim,)
    assert result.exclusions == ()
    assert result.ready_for_verification is True
    assert claim.provenance is not None
    assert claim.provenance.verification_status is VerificationStatus.PENDING


def test_contract_admission_does_not_pretend_to_judge_semantic_support() -> None:
    claim = _claim(
        text="This deliberately unrelated assertion is not judged in E7.2."
    )

    result = admit_candidate_claims(_request(claim))

    assert result.accepted_claims == (claim,)
    assert result.accepted_claims[0].provenance is not None
    assert (
        result.accepted_claims[0].provenance.verification_status
        is VerificationStatus.PENDING
    )


def test_multi_question_claims_keep_separate_scopes_and_stable_order() -> None:
    first_admission = _admission()
    second_admission = _admission(
        "evidence_bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
        document_id=102,
        chunk_id=302,
        question_id="question-2",
        section_key="official-two",
    )
    first = _claim()
    second = _claim(
        "claim-2",
        scope=_scope("question-2", "official-two"),
        support_ids=("evidence_bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",),
        text="The second provision applies.",
    )

    result = admit_candidate_claims(
        _request(
            first,
            second,
            admissions=(first_admission, second_admission),
        )
    )

    assert tuple(item.artifact_id for item in result.accepted_claims) == (
        "claim-1",
        "claim-2",
    )
    assert result.exclusions == ()


def test_one_claim_can_reference_multiple_admitted_units_in_exact_order() -> None:
    first = _admission()
    second = _admission(
        "evidence_bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
        document_id=102,
        chunk_id=302,
    )
    supports = (
        "evidence_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        "evidence_bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
    )
    claim = _claim(support_ids=supports)

    result = admit_candidate_claims(
        _request(claim, admissions=(first, second))
    )

    assert result.accepted_claims == (claim,)


def test_nonmaterial_and_supportless_outputs_are_not_candidate_claims() -> None:
    nonmaterial = _claim(material=False)
    supportless = _claim(
        "claim-2",
        support_ids=(),
        transform_support_ids=(
            "evidence_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        ),
    )

    result = admit_candidate_claims(_request(nonmaterial, supportless))

    assert tuple(item.code for item in result.exclusions) == (
        CandidateClaimRejectionCode.NOT_MATERIAL,
        CandidateClaimRejectionCode.SUPPORT_REQUIRED,
    )


def test_duplicate_unknown_and_excluded_support_references_are_refused() -> None:
    evidence_id = "evidence_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    duplicate = _claim(
        support_ids=(evidence_id, evidence_id),
        transform_support_ids=(evidence_id,),
    )
    unknown = _claim(
        "claim-2",
        support_ids=("evidence_cccccccccccccccccccccccccccccccc",),
    )
    excluded = OfficialEvidenceAdmissionResult(
        policy_version=EVIDENCE_ADMISSION_POLICY_VERSION,
        admitted=(),
        exclusions=(
            EvidenceExclusion(
                artifact_id="artifact-rejected",
                evidence_unit_id="evidence_dddddddddddddddddddddddddddddddd",
                code=EvidenceRejectionCode.STALE_SOURCE,
            ),
        ),
    )
    excluded_reference = _claim(
        "claim-3",
        support_ids=("evidence_dddddddddddddddddddddddddddddddd",),
    )

    result = admit_candidate_claims(
        _request(
            duplicate,
            unknown,
            excluded_reference,
            admissions=(_admission(), excluded),
        )
    )

    assert tuple(item.code for item in result.exclusions) == (
        CandidateClaimRejectionCode.SUPPORT_DUPLICATE,
        CandidateClaimRejectionCode.SUPPORT_NOT_ADMITTED,
        CandidateClaimRejectionCode.SUPPORT_NOT_ADMITTED,
    )


@pytest.mark.parametrize(
    "scope",
    [
        CapabilityScope(
            atomic_question_ids=("question-1", "question-2"),
            section_keys=("official-one",),
            entity_ids=("entity-1",),
            jurisdiction="India",
            stakeholder="regulated entity",
            time_scope="current",
            date_semantics=(TimeDimension.EFFECTIVE,),
            constraints=("official sources only",),
        ),
        _scope(section_key="unknown-section"),
        _scope(jurisdiction="Singapore"),
        _scope(entity_ids=("entity-2",)),
        _scope(time_scope="historical"),
    ],
)
def test_claim_scope_must_be_one_exact_narrowing_of_approved_scope(
    scope: CapabilityScope,
) -> None:
    result = admit_candidate_claims(_request(_claim(scope=scope)))

    assert _only_code(result) is CandidateClaimRejectionCode.SCOPE_MISMATCH


def test_support_must_share_the_claim_atomic_question_and_section_scope() -> None:
    evidence = _admission()
    crossed = _claim(scope=_scope("question-2", "official-two"))

    result = admit_candidate_claims(
        _request(crossed, admissions=(evidence,))
    )

    assert (
        _only_code(result)
        is CandidateClaimRejectionCode.SUPPORT_SCOPE_MISMATCH
    )


def test_crossed_live_evidence_lane_is_refused_even_if_forged_as_admitted() -> None:
    admission = _admission()
    unit = admission.admitted[0]
    assert unit.artifact.provenance is not None
    official_source = unit.artifact.provenance.sources[0]
    live_source = official_source.model_copy(
        update={
            "provenance_class": ProvenanceClass.LIVE_WEB_SOURCES,
            "publication_at": datetime(2023, 6, 1, tzinfo=UTC),
            "retrieved_at": NOW,
        }
    )
    live_artifact = unit.artifact.model_copy(
        update={
            "provenance": ProvenanceLineage(
                provenance_class=ProvenanceClass.LIVE_WEB_SOURCES,
                knowledge_mode=KnowledgeMode.LIVE_INTELLIGENCE,
                sources=(live_source,),
                derivation=ContentDerivation.DIRECT,
                verification_status=VerificationStatus.PENDING,
            )
        }
    )
    forged_unit = unit.model_copy(update={"artifact": live_artifact})
    forged_admission = admission.model_copy(update={"admitted": (forged_unit,)})

    result = admit_candidate_claims(
        _request(_claim(), admissions=(forged_admission,))
    )

    assert (
        _only_code(result)
        is CandidateClaimRejectionCode.SUPPORT_PROVENANCE_MISMATCH
    )


@pytest.mark.parametrize(
    ("mutation", "expected"),
    [
        ("general_lane", CandidateClaimRejectionCode.PROVENANCE_MISMATCH),
        ("preverified", CandidateClaimRejectionCode.PROVENANCE_MISMATCH),
        ("wrong_transform_input", CandidateClaimRejectionCode.LINEAGE_MISMATCH),
        ("wrong_transform_capability", CandidateClaimRejectionCode.LINEAGE_MISMATCH),
        (
            "terminal_unavailable",
            CandidateClaimRejectionCode.TERMINAL_STATUS_INVALID,
        ),
        ("conflict", CandidateClaimRejectionCode.CONFLICTING),
    ],
)
def test_claim_mode_lineage_terminal_state_and_conflicts_fail_closed(
    mutation: str,
    expected: CandidateClaimRejectionCode,
) -> None:
    claim = _claim()
    if mutation == "general_lane":
        general_lineage = ProvenanceLineage(
            provenance_class=ProvenanceClass.GENERAL_AI_KNOWLEDGE,
            knowledge_mode=KnowledgeMode.GENERAL_AI,
            derivation=ContentDerivation.GENERATED,
            verification_status=VerificationStatus.NOT_APPLICABLE,
        )
        claim = claim.model_copy(update={"provenance": general_lineage})
    elif mutation == "preverified":
        assert claim.provenance is not None
        claim = claim.model_copy(
            update={
                "provenance": claim.provenance.model_copy(
                    update={"verification_status": VerificationStatus.SUPPORTED}
                )
            }
        )
    elif mutation == "wrong_transform_input":
        claim = _claim(
            transform_support_ids=(
                "evidence_bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
            )
        )
    elif mutation == "wrong_transform_capability":
        claim = _claim(
            transform_capability=OrchestratorCapability.TIMELINE_BUILDER
        )
    elif mutation == "terminal_unavailable":
        claim = _claim(capability_status=CapabilityTerminalState.UNAVAILABLE)
    else:
        claim = _claim(conflicts=("composer conflict",))

    result = admit_candidate_claims(_request(claim))

    assert _only_code(result) is expected


def test_wrong_artifact_kind_is_not_a_candidate_claim() -> None:
    claim = _claim()
    wrong_payload = SectionDraftPayload(
        section_type="official",
        content_blocks=(),
    )
    wrong = claim.model_copy(update={"payload": wrong_payload})

    result = admit_candidate_claims(_request(wrong))

    assert _only_code(result) is CandidateClaimRejectionCode.INVALID_CONTRACT


def test_duplicate_claim_identity_and_evidence_identity_collision_are_refused() -> None:
    first = _claim()
    duplicate = _claim(text="A different claim with a duplicate ID.")
    colliding = _claim(
        "evidence_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        support_ids=("evidence_bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",),
        text="A claim ID cannot reuse an evidence artifact ID.",
    )
    second_admission = _admission(
        "evidence_bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
        document_id=102,
        chunk_id=302,
    )

    result = admit_candidate_claims(
        _request(
            first,
            duplicate,
            colliding,
            admissions=(_admission(), second_admission),
        )
    )

    assert result.accepted_claims == (first,)
    assert tuple(item.code for item in result.exclusions) == (
        CandidateClaimRejectionCode.DUPLICATE_IDENTITY,
        CandidateClaimRejectionCode.IDENTITY_COLLISION,
    )


def test_malformed_claim_is_isolated_without_suppressing_valid_neighbor() -> None:
    malformed = _claim()
    assert malformed.provenance is not None
    source = malformed.provenance.sources[0].model_copy(
        update={"issue_at": NOW.replace(tzinfo=None)}
    )
    malformed_lineage = malformed.provenance.model_copy(
        update={"sources": (source,)}
    )
    malformed = malformed.model_copy(update={"provenance": malformed_lineage})
    valid = _claim("claim-2")

    result = admit_candidate_claims(_request(malformed, valid))

    assert result.accepted_claims == (valid,)
    assert tuple(item.code for item in result.exclusions) == (
        CandidateClaimRejectionCode.INVALID_CONTRACT,
    )


def test_invalid_or_duplicate_admission_input_blocks_all_claims_safely() -> None:
    admission = _admission()
    wrong_policy = admission.model_copy(update={"policy_version": "old-policy"})
    wrong_policy_request = _request(_claim()).model_copy(
        update={"evidence_admissions": (wrong_policy,)}
    )
    invalid_policy_result = admit_candidate_claims(
        wrong_policy_request
    )
    duplicate_result = admit_candidate_claims(
        _request(_claim(), admissions=(admission, admission))
    )

    assert (
        _only_code(invalid_policy_result)
        is CandidateClaimRejectionCode.ADMISSION_INPUT_INVALID
    )
    assert (
        _only_code(duplicate_result)
        is CandidateClaimRejectionCode.ADMISSION_INPUT_INVALID
    )


def test_admitted_and_excluded_identity_collision_invalidates_input() -> None:
    admission = _admission()
    collision = admission.model_copy(
        update={
            "exclusions": (
                EvidenceExclusion(
                    artifact_id=admission.admitted[0].artifact.artifact_id,
                    evidence_unit_id=(
                        admission.admitted[0].canonical_evidence.evidence_unit_id
                    ),
                    code=EvidenceRejectionCode.DUPLICATE_IDENTITY,
                ),
            )
        }
    )

    result = admit_candidate_claims(
        _request(_claim(), admissions=(collision,))
    )

    assert (
        _only_code(result)
        is CandidateClaimRejectionCode.ADMISSION_INPUT_INVALID
    )


def test_empty_batch_is_valid_but_not_ready_for_verification() -> None:
    result = admit_candidate_claims(
        _request(admissions=(), approved_scope=_parent_scope())
    )

    assert result.accepted_claims == ()
    assert result.exclusions == ()
    assert result.ready_for_verification is False


def test_contracts_are_strict_frozen_and_fail_closed_on_nested_bypass() -> None:
    request = _request(_claim())
    with pytest.raises(ValidationError):
        CandidateClaimBatchRequest.model_validate(
            {**request.model_dump(mode="python"), "unexpected": True}
        )
    with pytest.raises(ValidationError):
        request.policy_version = "different"

    bypassed_scope = request.approved_scope.model_copy(
        update={"atomic_question_ids": ()}
    )
    bypassed_request = request.model_copy(
        update={"approved_scope": bypassed_scope}
    )
    result = admit_candidate_claims(bypassed_request)

    assert _only_code(result) is CandidateClaimRejectionCode.INVALID_CONTRACT


def test_result_is_deterministic_serializable_and_input_immutable() -> None:
    first = _claim()
    second = _claim("claim-2", text="A second material claim.")
    request = _request(first, second)
    before = request.model_dump(mode="json")

    result_one = admit_candidate_claims(request)
    result_two = admit_candidate_claims(request)

    assert result_one == result_two
    assert request.model_dump(mode="json") == before
    assert result_one.policy_version == CANDIDATE_CLAIM_POLICY_VERSION
    assert json.loads(result_one.model_dump_json()) == result_one.model_dump(
        mode="json"
    )
    with pytest.raises(ValidationError):
        CandidateClaimBatchResult.model_validate(
            {**result_one.model_dump(mode="python"), "unexpected": True}
        )
