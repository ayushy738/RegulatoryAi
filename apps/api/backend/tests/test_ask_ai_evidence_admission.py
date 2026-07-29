from __future__ import annotations

import json
from datetime import UTC, date, datetime

import pytest
from pydantic import ValidationError

from backend.ask.evidence_admission import (
    EVIDENCE_ADMISSION_POLICY_VERSION,
    AdmittedOfficialEvidence,
    EvidenceAdmissionRequest,
    EvidenceRejectionCode,
    OfficialEvidenceAdmissionResult,
    OfficialEvidenceCandidate,
    admit_official_evidence,
    official_source_id,
)
from backend.ask.orchestration.contracts import (
    ArtifactEnvelope,
    ArtifactProducer,
    CapabilityScope,
    CapabilityTerminalState,
    ConfidenceSignals,
    ContentDerivation,
    EvidenceUnitPayload,
    KnowledgeMode,
    ProvenanceClass,
    ProvenanceLineage,
    SourceIdentity,
    TimeDimension,
    VerificationStatus,
)
from backend.rag.models import RetrievalSource
from backend.rag.quality import (
    CanonicalEvidenceUnit,
    EvidenceScoreSnapshot,
    RetrievalMatchReason,
)
from backend.rag.version_status import (
    DocumentLegalStatus,
    OfficialVersionRecord,
    OfficialVersionRelationship,
    VersionEvidenceCoverage,
    VersionRelationshipKind,
    VersionStatusDecision,
    VersionStatusMode,
    VersionStatusOutcome,
    VersionStatusRequest,
    resolve_version_status,
)

NOW = datetime(2026, 7, 27, 10, 0, tzinfo=UTC)
ISSUE_DATE = date(2023, 6, 1)


def _scope(
    *,
    question_ids: tuple[str, ...] = ("question-1",),
    jurisdiction: str = "India",
    time_scope: str = "current",
) -> CapabilityScope:
    return CapabilityScope(
        atomic_question_ids=question_ids,
        section_keys=("official_sources",),
        entity_ids=("entity-1",),
        jurisdiction=jurisdiction,
        time_scope=time_scope,
        date_semantics=(TimeDimension.EFFECTIVE,),
    )


def _evidence(
    *,
    evidence_id: str = "evidence_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    document_id: int = 101,
    version_id: int | None = 201,
    family_id: int | None = 10,
    chunk_id: int | None = 301,
    question_ids: tuple[str, ...] = ("question-1",),
    text: str = "The regulated entity must submit the filing.",
    sources: tuple[RetrievalSource, ...] = ("vector",),
) -> CanonicalEvidenceUnit:
    return CanonicalEvidenceUnit(
        evidence_unit_id=evidence_id,
        policy_version="ask-ai-retrieval-quality-v1",
        document_id=document_id,
        version_id=version_id,
        family_id=family_id,
        chunk_id=chunk_id,
        title="Official regulation",
        source_url="https://official.example/regulation",
        issuer="Regulator",
        issue_date=ISSUE_DATE,
        text=text,
        retrieval_sources=sources,
        match_reasons=(RetrievalMatchReason.VECTOR_SIMILARITY,),
        question_ids=question_ids,
        scores=EvidenceScoreSnapshot(
            vector=0.94,
            keyword=0.82,
            graph=0,
            admitted_relevance=0.94,
        ),
    )


def _source(evidence: CanonicalEvidenceUnit) -> SourceIdentity:
    return SourceIdentity(
        source_id=official_source_id(evidence),
        provenance_class=ProvenanceClass.INTERNAL_REGULATORY_CORPUS,
        title=evidence.title,
        uri=evidence.source_url,
        issuer_or_publisher=evidence.issuer,
        issue_at=datetime.combine(evidence.issue_date, datetime.min.time(), UTC),
    )


def _artifact(
    evidence: CanonicalEvidenceUnit,
    scope: CapabilityScope,
    *,
    source_status: str | None = None,
    locator: str | None = "section 4, chunk 301",
) -> ArtifactEnvelope:
    return ArtifactEnvelope(
        artifact_id=evidence.evidence_unit_id,
        producer=ArtifactProducer.REGULATORY_RETRIEVER,
        scope=scope,
        payload=EvidenceUnitPayload(
            excerpt=evidence.text,
            locator=locator,
            source_status=source_status,
            match_reasons=tuple(item.value for item in evidence.match_reasons),
            duplicate_match_methods=(
                evidence.retrieval_sources
                if len(evidence.retrieval_sources) > 1
                else ()
            ),
        ),
        provenance=ProvenanceLineage(
            provenance_class=ProvenanceClass.INTERNAL_REGULATORY_CORPUS,
            knowledge_mode=KnowledgeMode.GROUNDED_REGULATORY,
            sources=(_source(evidence),),
            derivation=ContentDerivation.DIRECT,
            verification_status=VerificationStatus.PENDING,
        ),
        confidence_signals=ConfidenceSignals(
            evidence_authority=1,
            retrieval_relevance=evidence.scores.admitted_relevance,
        ),
        ancestry=("plan-1",),
        capability_status=CapabilityTerminalState.SATISFIED,
    )


def _record(
    registry_id: int,
    *,
    document_id: int,
    document_version_id: int,
    available_on: date,
    status: DocumentLegalStatus = DocumentLegalStatus.IN_FORCE,
) -> OfficialVersionRecord:
    return OfficialVersionRecord(
        registry_version_id=registry_id,
        family_id=10,
        document_id=document_id,
        document_version_id=document_version_id,
        version_number=registry_id,
        version_label=f"Version {registry_id}",
        publication_date=available_on,
        effective_date=available_on,
        declared_status=status,
        status_effective_on=available_on,
        status_observed_at=NOW,
        status_source_url=f"https://official.example/status/{registry_id}",
    )


def _status_bundle(
    *,
    mode: VersionStatusMode = VersionStatusMode.CURRENT,
    as_of: date | None = None,
    records: tuple[OfficialVersionRecord, ...] | None = None,
    relationships: tuple[OfficialVersionRelationship, ...] = (),
    coverage: VersionEvidenceCoverage = VersionEvidenceCoverage.COMPLETE,
) -> tuple[VersionStatusRequest, VersionStatusDecision]:
    status_request = VersionStatusRequest(
        family_id=10,
        mode=mode,
        evaluated_at=NOW,
        as_of=as_of,
        coverage=coverage,
        records=(
            records
            if records is not None
            else (
                _record(
                    1,
                    document_id=101,
                    document_version_id=201,
                    available_on=ISSUE_DATE,
                ),
            )
        ),
        relationships=relationships,
    )
    return status_request, resolve_version_status(status_request)


def _candidate(
    *,
    evidence: CanonicalEvidenceUnit | None = None,
    scope: CapabilityScope | None = None,
    artifact: ArtifactEnvelope | None = None,
    status_bundle: tuple[VersionStatusRequest, VersionStatusDecision] | None = None,
) -> OfficialEvidenceCandidate:
    canonical = evidence or _evidence()
    approved_scope = scope or _scope()
    status = status_bundle
    source_status = None
    if status is not None and status[1].selected_registry_version_ids:
        record_id = next(
            record.registry_version_id
            for record in status[0].records
            if record.document_id == canonical.document_id
            and record.document_version_id == canonical.version_id
        )
        source_status = next(
            (
                item.status.value
                for item in status[1].resolved_statuses
                if item.registry_version_id == record_id
            ),
            None,
        )
    return OfficialEvidenceCandidate(
        artifact=artifact
        or _artifact(canonical, approved_scope, source_status=source_status),
        canonical_evidence=canonical,
        version_request=status[0] if status is not None else None,
        version_decision=status[1] if status is not None else None,
    )


def _request(
    *candidates: OfficialEvidenceCandidate,
    scope: CapabilityScope | None = None,
    mode: VersionStatusMode | None = None,
    as_of: date | None = None,
) -> EvidenceAdmissionRequest:
    return EvidenceAdmissionRequest(
        approved_scope=scope or _scope(),
        evaluated_at=NOW,
        required_status_mode=mode,
        required_as_of=as_of,
        candidates=candidates,
    )


def _only_code(result: OfficialEvidenceAdmissionResult) -> EvidenceRejectionCode:
    assert result.admitted == ()
    assert len(result.exclusions) == 1
    return result.exclusions[0].code


def test_inspectable_official_evidence_is_admitted_without_claim_verification() -> None:
    candidate = _candidate()

    result = admit_official_evidence(_request(candidate))

    assert result == OfficialEvidenceAdmissionResult(
        policy_version=EVIDENCE_ADMISSION_POLICY_VERSION,
        admitted=(
            AdmittedOfficialEvidence(
                artifact=candidate.artifact,
                canonical_evidence=candidate.canonical_evidence,
            ),
        ),
        exclusions=(),
    )
    assert result.can_compose_official is True
    assert candidate.artifact.provenance is not None
    assert (
        candidate.artifact.provenance.verification_status
        is VerificationStatus.PENDING
    )


@pytest.mark.parametrize(
    ("mode", "as_of", "expected_outcome"),
    [
        (
            VersionStatusMode.CURRENT,
            None,
            VersionStatusOutcome.VALIDATED_CURRENT,
        ),
        (
            VersionStatusMode.AS_OF,
            date(2024, 1, 1),
            VersionStatusOutcome.VALIDATED_HISTORICAL,
        ),
        (
            VersionStatusMode.DRAFT,
            None,
            VersionStatusOutcome.VALIDATED_DRAFT,
        ),
    ],
)
def test_current_historical_and_draft_status_fitness_is_admitted(
    mode: VersionStatusMode,
    as_of: date | None,
    expected_outcome: VersionStatusOutcome,
) -> None:
    record = _record(
        1,
        document_id=101,
        document_version_id=201,
        available_on=date(2023, 6, 1),
        status=(
            DocumentLegalStatus.DRAFT
            if mode is VersionStatusMode.DRAFT
            else DocumentLegalStatus.IN_FORCE
        ),
    )
    bundle = _status_bundle(mode=mode, as_of=as_of, records=(record,))
    candidate = _candidate(status_bundle=bundle)

    result = admit_official_evidence(
        _request(candidate, mode=mode, as_of=as_of)
    )

    assert len(result.admitted) == 1
    assert result.admitted[0].status_decision is not None
    assert result.admitted[0].status_decision.outcome is expected_outcome
    assert result.exclusions == ()


def test_older_official_version_is_rejected_as_stale_for_current_scope() -> None:
    old = _record(
        1,
        document_id=101,
        document_version_id=201,
        available_on=date(2020, 1, 1),
    )
    current = _record(
        2,
        document_id=102,
        document_version_id=202,
        available_on=date(2023, 6, 1),
    )
    edge = OfficialVersionRelationship(
        from_registry_version_id=2,
        to_registry_version_id=1,
        relationship=VersionRelationshipKind.SUPERSEDES,
        effective_on=date(2023, 6, 1),
        observed_at=NOW,
        source_url="https://official.example/lineage/2/1",
    )
    bundle = _status_bundle(records=(old, current), relationships=(edge,))
    candidate = _candidate(status_bundle=bundle)

    result = admit_official_evidence(
        _request(candidate, mode=VersionStatusMode.CURRENT)
    )

    assert _only_code(result) is EvidenceRejectionCode.STALE_SOURCE


def test_historical_scope_admits_prior_version_and_excludes_later_version() -> None:
    old = _record(
        1,
        document_id=101,
        document_version_id=201,
        available_on=date(2020, 1, 1),
    )
    later = _record(
        2,
        document_id=102,
        document_version_id=202,
        available_on=date(2023, 6, 1),
    )
    edge = OfficialVersionRelationship(
        from_registry_version_id=2,
        to_registry_version_id=1,
        relationship=VersionRelationshipKind.SUPERSEDES,
        effective_on=date(2023, 6, 1),
        observed_at=NOW,
        source_url="https://official.example/lineage/2/1",
    )
    as_of = date(2022, 12, 31)
    bundle = _status_bundle(
        mode=VersionStatusMode.AS_OF,
        as_of=as_of,
        records=(old, later),
        relationships=(edge,),
    )
    prior = _candidate(status_bundle=bundle)
    future_evidence = _evidence(
        evidence_id="evidence_bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
        document_id=102,
        version_id=202,
    )
    future_artifact = _artifact(
        future_evidence,
        _scope(),
        source_status=DocumentLegalStatus.IN_FORCE.value,
    )
    future = _candidate(
        evidence=future_evidence,
        artifact=future_artifact,
        status_bundle=bundle,
    )

    result = admit_official_evidence(
        _request(prior, future, mode=VersionStatusMode.AS_OF, as_of=as_of)
    )

    assert tuple(item.artifact.artifact_id for item in result.admitted) == (
        prior.artifact.artifact_id,
    )
    assert result.exclusions[0].code is EvidenceRejectionCode.STALE_SOURCE


@pytest.mark.parametrize(
    ("case", "expected"),
    [
        ("no_match", EvidenceRejectionCode.STATUS_NO_MATCH),
        ("unknown", EvidenceRejectionCode.STATUS_UNVERIFIABLE),
        ("contradictory", EvidenceRejectionCode.STATUS_CONTRADICTORY),
        ("invalid_lineage", EvidenceRejectionCode.STATUS_INVALID_LINEAGE),
    ],
)
def test_nonvalidated_status_outcomes_are_never_admitted(
    case: str,
    expected: EvidenceRejectionCode,
) -> None:
    first = _record(
        1,
        document_id=101,
        document_version_id=201,
        available_on=ISSUE_DATE,
    )
    second = _record(
        2,
        document_id=102,
        document_version_id=202,
        available_on=ISSUE_DATE,
    )
    if case == "no_match":
        bundle = _status_bundle(records=())
    elif case == "unknown":
        bundle = _status_bundle(
            records=(first,),
            coverage=VersionEvidenceCoverage.PARTIAL,
        )
    elif case == "contradictory":
        bundle = _status_bundle(records=(first, second))
    else:
        invalid_edge = OfficialVersionRelationship(
            from_registry_version_id=2,
            to_registry_version_id=1,
            relationship=VersionRelationshipKind.SUPERSEDES,
            effective_on=ISSUE_DATE,
            observed_at=NOW,
            source_url="https://official.example/lineage/2/1",
        )
        bundle = _status_bundle(records=(first,), relationships=(invalid_edge,))
    candidate = _candidate(status_bundle=bundle)

    result = admit_official_evidence(
        _request(candidate, mode=VersionStatusMode.CURRENT)
    )

    assert _only_code(result) is expected


@pytest.mark.parametrize(
    ("mutation", "expected"),
    [
        ("artifact_id", EvidenceRejectionCode.ARTIFACT_IDENTITY_MISMATCH),
        ("title", EvidenceRejectionCode.SOURCE_IDENTITY_MISMATCH),
        ("uri", EvidenceRejectionCode.SOURCE_IDENTITY_MISMATCH),
        ("issuer", EvidenceRejectionCode.SOURCE_IDENTITY_MISMATCH),
        ("issue_date", EvidenceRejectionCode.SOURCE_IDENTITY_MISMATCH),
        ("missing_uri", EvidenceRejectionCode.SOURCE_NOT_INSPECTABLE),
        ("missing_locator", EvidenceRejectionCode.CHUNK_NOT_INSPECTABLE),
        ("missing_chunk", EvidenceRejectionCode.CHUNK_NOT_INSPECTABLE),
        ("excerpt", EvidenceRejectionCode.EXCERPT_MISMATCH),
    ],
)
def test_source_chunk_excerpt_and_locator_integrity_fail_closed(
    mutation: str,
    expected: EvidenceRejectionCode,
) -> None:
    evidence = _evidence()
    artifact = _artifact(evidence, _scope())
    source = artifact.provenance.sources[0]  # type: ignore[union-attr]
    if mutation == "artifact_id":
        artifact = artifact.model_copy(update={"artifact_id": "different-id"})
    elif mutation == "title":
        changed = source.model_copy(update={"title": "Different regulation"})
        artifact = _with_source(artifact, changed)
    elif mutation == "uri":
        changed = source.model_copy(update={"uri": "https://official.example/other"})
        artifact = _with_source(artifact, changed)
    elif mutation == "issuer":
        changed = source.model_copy(update={"issuer_or_publisher": "Other regulator"})
        artifact = _with_source(artifact, changed)
    elif mutation == "issue_date":
        changed = source.model_copy(
            update={"issue_at": datetime(2024, 1, 1, tzinfo=UTC)}
        )
        artifact = _with_source(artifact, changed)
    elif mutation == "missing_uri":
        changed = source.model_copy(update={"uri": None})
        artifact = _with_source(artifact, changed)
    elif mutation == "missing_locator":
        artifact = artifact.model_copy(
            update={"payload": artifact.payload.model_copy(update={"locator": None})}
        )
    elif mutation == "missing_chunk":
        evidence = evidence.model_copy(update={"chunk_id": None})
    else:
        artifact = artifact.model_copy(
            update={
                "payload": artifact.payload.model_copy(
                    update={"excerpt": "Different excerpt"}
                )
            }
        )

    result = admit_official_evidence(
        _request(_candidate(evidence=evidence, artifact=artifact))
    )

    assert _only_code(result) is expected


def _with_source(
    artifact: ArtifactEnvelope,
    source: SourceIdentity,
) -> ArtifactEnvelope:
    assert artifact.provenance is not None
    return artifact.model_copy(
        update={
            "provenance": artifact.provenance.model_copy(
                update={"sources": (source,)}
            )
        }
    )


def test_exact_scope_echo_and_atomic_question_membership_are_required() -> None:
    approved = _scope(question_ids=("question-1", "question-2"))
    evidence = _evidence(question_ids=("question-1",))
    wrong_scope_artifact = _artifact(
        evidence,
        _scope(
            question_ids=("question-1", "question-2"),
            jurisdiction="Singapore",
        ),
    )
    wrong_scope = _candidate(
        evidence=evidence,
        scope=approved,
        artifact=wrong_scope_artifact,
    )
    unknown_question_evidence = _evidence(
        evidence_id="evidence_bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
        question_ids=("question-3",),
    )
    unknown_question = _candidate(
        evidence=unknown_question_evidence,
        scope=approved,
    )

    result = admit_official_evidence(
        _request(wrong_scope, unknown_question, scope=approved)
    )

    assert tuple(item.code for item in result.exclusions) == (
        EvidenceRejectionCode.SCOPE_MISMATCH,
        EvidenceRejectionCode.QUESTION_SCOPE_MISMATCH,
    )


@pytest.mark.parametrize(
    ("mutation", "expected"),
    [
        ("news_producer", EvidenceRejectionCode.PROVENANCE_MISMATCH),
        ("live_lane", EvidenceRejectionCode.PROVENANCE_MISMATCH),
        ("preverified", EvidenceRejectionCode.PROVENANCE_MISMATCH),
        ("missing_ancestry", EvidenceRejectionCode.PROVENANCE_MISMATCH),
        ("unavailable", EvidenceRejectionCode.TERMINAL_STATUS_INVALID),
        ("conflict", EvidenceRejectionCode.CONFLICTING),
    ],
)
def test_provenance_terminal_state_and_conflict_integrity_fail_closed(
    mutation: str,
    expected: EvidenceRejectionCode,
) -> None:
    evidence = _evidence()
    artifact = _artifact(evidence, _scope())
    if mutation == "news_producer":
        artifact = artifact.model_copy(
            update={"producer": ArtifactProducer.NEWS_RETRIEVER}
        )
    elif mutation == "live_lane":
        assert artifact.provenance is not None
        live_source = artifact.provenance.sources[0].model_copy(
            update={
                "provenance_class": ProvenanceClass.LIVE_WEB_SOURCES,
                "publication_at": datetime(2023, 6, 1, tzinfo=UTC),
                "retrieved_at": NOW,
            }
        )
        artifact = artifact.model_copy(
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
    elif mutation == "preverified":
        assert artifact.provenance is not None
        artifact = artifact.model_copy(
            update={
                "provenance": artifact.provenance.model_copy(
                    update={"verification_status": VerificationStatus.SUPPORTED}
                )
            }
        )
    elif mutation == "missing_ancestry":
        artifact = artifact.model_copy(update={"ancestry": ()})
    elif mutation == "unavailable":
        artifact = artifact.model_copy(
            update={"capability_status": CapabilityTerminalState.UNAVAILABLE}
        )
    else:
        artifact = artifact.model_copy(update={"conflicts": ("status conflict",)})

    result = admit_official_evidence(
        _request(_candidate(evidence=evidence, artifact=artifact))
    )

    assert _only_code(result) is expected


@pytest.mark.parametrize("mutation", ["score", "reason", "duplicate_methods"])
def test_quality_admission_identity_must_match_e5_3(mutation: str) -> None:
    evidence = _evidence(
        sources=("vector", "keyword")
    )
    artifact = _artifact(evidence, _scope())
    if mutation == "score":
        assert artifact.confidence_signals is not None
        artifact = artifact.model_copy(
            update={
                "confidence_signals": artifact.confidence_signals.model_copy(
                    update={"retrieval_relevance": 0.93}
                )
            }
        )
    elif mutation == "reason":
        artifact = artifact.model_copy(
            update={
                "payload": artifact.payload.model_copy(
                    update={"match_reasons": ("keyword_match",)}
                )
            }
        )
    else:
        artifact = artifact.model_copy(
            update={
                "payload": artifact.payload.model_copy(
                    update={"duplicate_match_methods": ("vector",)}
                )
            }
        )

    result = admit_official_evidence(
        _request(_candidate(evidence=evidence, artifact=artifact))
    )

    assert _only_code(result) is EvidenceRejectionCode.RELEVANCE_MISMATCH


def test_status_is_required_for_current_scope_and_unverified_status_is_refused() -> None:
    without_bundle = _candidate()
    evidence = _evidence(
        evidence_id="evidence_bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
    )
    unverified_status = _candidate(
        evidence=evidence,
        artifact=_artifact(
            evidence,
            _scope(),
            source_status=DocumentLegalStatus.IN_FORCE.value,
        ),
    )

    current_result = admit_official_evidence(
        _request(without_bundle, mode=VersionStatusMode.CURRENT)
    )
    unverified_result = admit_official_evidence(_request(unverified_status))

    assert _only_code(current_result) is EvidenceRejectionCode.STATUS_REQUIRED
    assert (
        _only_code(unverified_result)
        is EvidenceRejectionCode.SOURCE_STATUS_MISMATCH
    )


@pytest.mark.parametrize(
    ("mutation", "expected"),
    [
        ("mode", EvidenceRejectionCode.STATUS_SCOPE_MISMATCH),
        ("as_of", EvidenceRejectionCode.STATUS_SCOPE_MISMATCH),
        ("evaluation_time", EvidenceRejectionCode.STATUS_SCOPE_MISMATCH),
        ("family", EvidenceRejectionCode.STATUS_SCOPE_MISMATCH),
        ("source_status", EvidenceRejectionCode.SOURCE_STATUS_MISMATCH),
        ("forged_decision", EvidenceRejectionCode.STATUS_UNVERIFIABLE),
    ],
)
def test_status_scope_identity_and_recomputed_decision_must_match(
    mutation: str,
    expected: EvidenceRejectionCode,
) -> None:
    bundle = _status_bundle()
    evidence = _evidence()
    candidate = _candidate(evidence=evidence, status_bundle=bundle)
    mode: VersionStatusMode | None = VersionStatusMode.CURRENT
    as_of: date | None = None
    evaluated_at = NOW
    if mutation == "mode":
        mode = VersionStatusMode.DRAFT
    elif mutation == "as_of":
        mode = VersionStatusMode.AS_OF
        as_of = date(2024, 1, 1)
    elif mutation == "evaluation_time":
        evaluated_at = datetime(2026, 7, 27, 10, 1, tzinfo=UTC)
    elif mutation == "family":
        evidence = evidence.model_copy(update={"family_id": 11})
        candidate = candidate.model_copy(update={"canonical_evidence": evidence})
    elif mutation == "source_status":
        candidate = candidate.model_copy(
            update={
                "artifact": candidate.artifact.model_copy(
                    update={
                        "payload": candidate.artifact.payload.model_copy(
                            update={"source_status": "superseded"}
                        )
                    }
                )
            }
        )
    else:
        assert candidate.version_decision is not None
        forged = candidate.version_decision.model_copy(
            update={"freshest_official_observation_at": None}
        )
        candidate = candidate.model_copy(update={"version_decision": forged})

    request = EvidenceAdmissionRequest(
        approved_scope=_scope(),
        evaluated_at=evaluated_at,
        required_status_mode=mode,
        required_as_of=as_of,
        candidates=(candidate,),
    )
    result = admit_official_evidence(request)

    assert _only_code(result) is expected


def test_valid_units_survive_invalid_neighbor_and_duplicates_are_excluded() -> None:
    valid = _candidate()
    bad_evidence = _evidence(
        evidence_id="evidence_bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
        document_id=102,
        version_id=None,
        family_id=None,
    )
    bad_artifact = _artifact(bad_evidence, _scope()).model_copy(
        update={"payload": EvidenceUnitPayload(excerpt="mismatch", locator="chunk 2")}
    )
    bad = _candidate(evidence=bad_evidence, artifact=bad_artifact)

    result = admit_official_evidence(_request(valid, bad, valid))

    assert tuple(item.artifact.artifact_id for item in result.admitted) == (
        valid.artifact.artifact_id,
    )
    assert tuple(item.code for item in result.exclusions) == (
        EvidenceRejectionCode.EXCERPT_MISMATCH,
        EvidenceRejectionCode.DUPLICATE_IDENTITY,
    )
    assert result.can_compose_official is True


def test_empty_admission_result_cannot_compose_official() -> None:
    result = admit_official_evidence(_request())

    assert result.admitted == ()
    assert result.exclusions == ()
    assert result.can_compose_official is False


def test_contracts_are_strict_frozen_and_reject_incomplete_status_pair() -> None:
    candidate = _candidate()
    with pytest.raises(ValidationError):
        EvidenceAdmissionRequest.model_validate(
            {
                **_request(candidate).model_dump(mode="python"),
                "unexpected": True,
            }
        )
    with pytest.raises(ValidationError):
        EvidenceAdmissionRequest(
            approved_scope=_scope(),
            evaluated_at=NOW.replace(tzinfo=None),
            candidates=(candidate,),
        )
    with pytest.raises(ValidationError):
        EvidenceAdmissionRequest(
            approved_scope=_scope(),
            evaluated_at=NOW,
            required_as_of=date(2024, 1, 1),
            candidates=(candidate,),
        )
    with pytest.raises(ValidationError):
        OfficialEvidenceCandidate(
            artifact=candidate.artifact,
            canonical_evidence=candidate.canonical_evidence,
            version_request=_status_bundle()[0],
        )
    with pytest.raises(ValidationError):
        candidate.artifact = candidate.artifact


def test_nested_model_copy_bypass_fails_closed_without_raw_detail() -> None:
    candidate = _candidate()
    neighbor_evidence = _evidence(
        evidence_id="evidence_bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
        document_id=102,
        version_id=None,
        family_id=None,
        chunk_id=302,
    )
    valid_neighbor = _candidate(evidence=neighbor_evidence)
    assert candidate.artifact.provenance is not None
    invalid_source = candidate.artifact.provenance.sources[0].model_copy(
        update={"issue_at": NOW.replace(tzinfo=None)}
    )
    invalid_artifact = _with_source(candidate.artifact, invalid_source)
    bypassed = candidate.model_copy(update={"artifact": invalid_artifact})
    bypassed_request = _request(bypassed, valid_neighbor)

    result = admit_official_evidence(bypassed_request)

    assert tuple(item.artifact.artifact_id for item in result.admitted) == (
        valid_neighbor.artifact.artifact_id,
    )
    assert tuple(item.code for item in result.exclusions) == (
        EvidenceRejectionCode.INVALID_CONTRACT,
    )
    serialized = result.model_dump_json()
    assert "timezone" not in serialized.lower()
    assert "2026-07-27T10:00:00" not in serialized


def test_admission_is_deterministic_serializable_and_input_immutable() -> None:
    first = _candidate()
    second_evidence = _evidence(
        evidence_id="evidence_bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
        document_id=102,
        version_id=None,
        family_id=None,
        chunk_id=302,
    )
    second = _candidate(evidence=second_evidence)
    request = _request(first, second)
    before = request.model_dump(mode="json")

    result_one = admit_official_evidence(request)
    result_two = admit_official_evidence(request)

    assert result_one == result_two
    assert request.model_dump(mode="json") == before
    assert json.loads(result_one.model_dump_json()) == result_one.model_dump(
        mode="json"
    )
    with pytest.raises(ValidationError):
        OfficialEvidenceAdmissionResult.model_validate(
            {**result_one.model_dump(mode="python"), "unexpected": True}
        )
