from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from backend.ask.orchestration.contracts import (
    ArtifactEnvelope,
    ArtifactProducer,
    CapabilityScope,
    CapabilityTerminalState,
    ContentDerivation,
    EvidenceUnitPayload,
    KnowledgeMode,
    ProvenanceClass,
    VerificationStatus,
)
from backend.rag.quality import CanonicalEvidenceUnit
from backend.rag.version_status import (
    VersionStatusDecision,
    VersionStatusMode,
    VersionStatusOutcome,
    VersionStatusRequest,
    resolve_version_status,
)

EVIDENCE_ADMISSION_SCHEMA_VERSION = "1"
EVIDENCE_ADMISSION_POLICY_VERSION = "ask-ai-evidence-admission-v1"


class EvidenceRejectionCode(StrEnum):
    INVALID_CONTRACT = "EVIDENCE_INVALID_CONTRACT"
    DUPLICATE_IDENTITY = "EVIDENCE_DUPLICATE_IDENTITY"
    ARTIFACT_IDENTITY_MISMATCH = "EVIDENCE_ARTIFACT_IDENTITY_MISMATCH"
    SOURCE_IDENTITY_MISMATCH = "EVIDENCE_SOURCE_IDENTITY_MISMATCH"
    SOURCE_NOT_INSPECTABLE = "EVIDENCE_SOURCE_NOT_INSPECTABLE"
    CHUNK_NOT_INSPECTABLE = "EVIDENCE_CHUNK_NOT_INSPECTABLE"
    EXCERPT_MISMATCH = "EVIDENCE_EXCERPT_MISMATCH"
    SCOPE_MISMATCH = "EVIDENCE_SCOPE_MISMATCH"
    QUESTION_SCOPE_MISMATCH = "EVIDENCE_QUESTION_SCOPE_MISMATCH"
    PROVENANCE_MISMATCH = "EVIDENCE_PROVENANCE_MISMATCH"
    RELEVANCE_MISMATCH = "EVIDENCE_RELEVANCE_MISMATCH"
    TERMINAL_STATUS_INVALID = "EVIDENCE_TERMINAL_STATUS_INVALID"
    CONFLICTING = "EVIDENCE_CONFLICTING"
    STATUS_REQUIRED = "EVIDENCE_STATUS_REQUIRED"
    STATUS_SCOPE_MISMATCH = "EVIDENCE_STATUS_SCOPE_MISMATCH"
    STATUS_NO_MATCH = "EVIDENCE_STATUS_NO_MATCH"
    STATUS_UNVERIFIABLE = "EVIDENCE_STATUS_UNVERIFIABLE"
    STATUS_CONTRADICTORY = "EVIDENCE_STATUS_CONTRADICTORY"
    STATUS_INVALID_LINEAGE = "EVIDENCE_STATUS_INVALID_LINEAGE"
    STALE_SOURCE = "EVIDENCE_STALE_SOURCE"
    SOURCE_STATUS_MISMATCH = "EVIDENCE_SOURCE_STATUS_MISMATCH"


class EvidenceAdmissionModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        strict=True,
        str_strip_whitespace=True,
    )


class OfficialEvidenceCandidate(EvidenceAdmissionModel):
    artifact: ArtifactEnvelope
    canonical_evidence: CanonicalEvidenceUnit
    version_request: VersionStatusRequest | None = None
    version_decision: VersionStatusDecision | None = None

    @model_validator(mode="after")
    def require_complete_status_bundle(self) -> Self:
        if (self.version_request is None) != (self.version_decision is None):
            raise ValueError(
                "Version status admission requires both request and decision"
            )
        return self


class EvidenceAdmissionRequest(EvidenceAdmissionModel):
    schema_version: Literal["1"] = EVIDENCE_ADMISSION_SCHEMA_VERSION
    policy_version: str = Field(
        default=EVIDENCE_ADMISSION_POLICY_VERSION,
        min_length=1,
    )
    approved_scope: CapabilityScope
    evaluated_at: datetime
    required_status_mode: VersionStatusMode | None = None
    required_as_of: date | None = None
    candidates: tuple[OfficialEvidenceCandidate, ...]

    @model_validator(mode="after")
    def validate_time_requirement(self) -> Self:
        if self.evaluated_at.tzinfo is None:
            raise ValueError("Evidence admission time must be timezone-aware")
        if (
            self.required_status_mode is VersionStatusMode.AS_OF
        ) != (self.required_as_of is not None):
            raise ValueError("Only as-of evidence admission requires an as-of date")
        if (
            self.required_as_of is not None
            and self.required_as_of > self.evaluated_at.date()
        ):
            raise ValueError("Evidence admission as-of date cannot be in the future")
        return self


class AdmittedOfficialEvidence(EvidenceAdmissionModel):
    artifact: ArtifactEnvelope
    canonical_evidence: CanonicalEvidenceUnit
    status_decision: VersionStatusDecision | None = None


class EvidenceExclusion(EvidenceAdmissionModel):
    artifact_id: str
    evidence_unit_id: str
    code: EvidenceRejectionCode


class OfficialEvidenceAdmissionResult(EvidenceAdmissionModel):
    schema_version: Literal["1"] = EVIDENCE_ADMISSION_SCHEMA_VERSION
    policy_version: str = Field(min_length=1)
    admitted: tuple[AdmittedOfficialEvidence, ...]
    exclusions: tuple[EvidenceExclusion, ...]

    @property
    def can_compose_official(self) -> bool:
        return bool(self.admitted)


def admit_official_evidence(
    request: EvidenceAdmissionRequest,
) -> OfficialEvidenceAdmissionResult:
    try:
        validated_request = EvidenceAdmissionRequest.model_validate(
            {
                **request.model_dump(mode="python"),
                "candidates": (),
            },
            strict=True,
        )
    except ValidationError:
        return _invalid_request_result(request)

    admitted: list[AdmittedOfficialEvidence] = []
    exclusions: list[EvidenceExclusion] = []
    artifact_ids: set[str] = set()
    evidence_ids: set[str] = set()

    for untrusted_candidate in request.candidates:
        try:
            candidate = OfficialEvidenceCandidate.model_validate(
                untrusted_candidate.model_dump(mode="python"),
                strict=True,
            )
        except (AttributeError, ValidationError):
            exclusions.append(
                EvidenceExclusion(
                    artifact_id=_safe_artifact_id(untrusted_candidate),
                    evidence_unit_id=_safe_evidence_id(untrusted_candidate),
                    code=EvidenceRejectionCode.INVALID_CONTRACT,
                )
            )
            continue
        artifact_id = candidate.artifact.artifact_id
        evidence_id = candidate.canonical_evidence.evidence_unit_id
        if artifact_id in artifact_ids or evidence_id in evidence_ids:
            exclusions.append(
                _exclusion(candidate, EvidenceRejectionCode.DUPLICATE_IDENTITY)
            )
            continue
        artifact_ids.add(artifact_id)
        evidence_ids.add(evidence_id)

        rejection = _integrity_rejection(validated_request, candidate)
        if rejection is not None:
            exclusions.append(_exclusion(candidate, rejection))
            continue
        admitted.append(
            AdmittedOfficialEvidence(
                artifact=candidate.artifact,
                canonical_evidence=candidate.canonical_evidence,
                status_decision=candidate.version_decision,
            )
        )

    return OfficialEvidenceAdmissionResult(
        policy_version=validated_request.policy_version,
        admitted=tuple(admitted),
        exclusions=tuple(exclusions),
    )


def official_source_id(evidence: CanonicalEvidenceUnit) -> str:
    return f"document-{evidence.document_id}"


def _invalid_request_result(
    request: EvidenceAdmissionRequest,
) -> OfficialEvidenceAdmissionResult:
    exclusions = tuple(
        EvidenceExclusion(
            artifact_id=_safe_artifact_id(candidate),
            evidence_unit_id=_safe_evidence_id(candidate),
            code=EvidenceRejectionCode.INVALID_CONTRACT,
        )
        for candidate in getattr(request, "candidates", ())
    )
    return OfficialEvidenceAdmissionResult(
        policy_version=EVIDENCE_ADMISSION_POLICY_VERSION,
        admitted=(),
        exclusions=exclusions,
    )


def _integrity_rejection(
    request: EvidenceAdmissionRequest,
    candidate: OfficialEvidenceCandidate,
) -> EvidenceRejectionCode | None:
    artifact = candidate.artifact
    evidence = candidate.canonical_evidence

    if artifact.artifact_id != evidence.evidence_unit_id:
        return EvidenceRejectionCode.ARTIFACT_IDENTITY_MISMATCH
    if artifact.scope != request.approved_scope:
        return EvidenceRejectionCode.SCOPE_MISMATCH
    if not set(evidence.question_ids).issubset(
        request.approved_scope.atomic_question_ids
    ):
        return EvidenceRejectionCode.QUESTION_SCOPE_MISMATCH
    if artifact.producer is not ArtifactProducer.REGULATORY_RETRIEVER:
        return EvidenceRejectionCode.PROVENANCE_MISMATCH
    if artifact.capability_status not in {
        CapabilityTerminalState.SATISFIED,
        CapabilityTerminalState.PARTIAL,
    }:
        return EvidenceRejectionCode.TERMINAL_STATUS_INVALID
    if artifact.conflicts:
        return EvidenceRejectionCode.CONFLICTING
    if not isinstance(artifact.payload, EvidenceUnitPayload):
        return EvidenceRejectionCode.INVALID_CONTRACT
    if artifact.payload.excerpt != evidence.text:
        return EvidenceRejectionCode.EXCERPT_MISMATCH
    if (
        evidence.chunk_id is None
        or evidence.chunk_id < 1
        or artifact.payload.locator is None
        or not artifact.payload.locator.strip()
    ):
        return EvidenceRejectionCode.CHUNK_NOT_INSPECTABLE
    expected_reasons = tuple(reason.value for reason in evidence.match_reasons)
    expected_duplicates = (
        evidence.retrieval_sources
        if len(evidence.retrieval_sources) > 1
        else ()
    )
    if (
        artifact.payload.match_reasons != expected_reasons
        or artifact.payload.duplicate_match_methods != expected_duplicates
    ):
        return EvidenceRejectionCode.RELEVANCE_MISMATCH
    if (
        artifact.confidence_signals is None
        or artifact.confidence_signals.retrieval_relevance
        != evidence.scores.admitted_relevance
    ):
        return EvidenceRejectionCode.RELEVANCE_MISMATCH
    if not artifact.ancestry:
        return EvidenceRejectionCode.PROVENANCE_MISMATCH

    lineage = artifact.provenance
    if (
        lineage is None
        or lineage.provenance_class
        is not ProvenanceClass.INTERNAL_REGULATORY_CORPUS
        or lineage.knowledge_mode is not KnowledgeMode.GROUNDED_REGULATORY
        or lineage.derivation is not ContentDerivation.DIRECT
        or lineage.transformations
        or lineage.verification_status is not VerificationStatus.PENDING
    ):
        return EvidenceRejectionCode.PROVENANCE_MISMATCH
    if len(lineage.sources) != 1:
        return EvidenceRejectionCode.SOURCE_IDENTITY_MISMATCH
    source = lineage.sources[0]
    if source.provenance_class is not ProvenanceClass.INTERNAL_REGULATORY_CORPUS:
        return EvidenceRejectionCode.PROVENANCE_MISMATCH
    if source.uri is None or not source.uri.strip():
        return EvidenceRejectionCode.SOURCE_NOT_INSPECTABLE
    if (
        source.source_id != official_source_id(evidence)
        or source.title != evidence.title
        or source.uri != evidence.source_url
        or source.issuer_or_publisher != evidence.issuer
    ):
        return EvidenceRejectionCode.SOURCE_IDENTITY_MISMATCH
    source_issue_date = source.issue_at.date() if source.issue_at is not None else None
    if source_issue_date != evidence.issue_date:
        return EvidenceRejectionCode.SOURCE_IDENTITY_MISMATCH

    return _status_rejection(request, candidate)


def _status_rejection(
    request: EvidenceAdmissionRequest,
    candidate: OfficialEvidenceCandidate,
) -> EvidenceRejectionCode | None:
    status_request = candidate.version_request
    decision = candidate.version_decision
    payload = candidate.artifact.payload
    evidence = candidate.canonical_evidence

    if status_request is None or decision is None:
        if request.required_status_mode is not None:
            return EvidenceRejectionCode.STATUS_REQUIRED
        if payload.source_status is not None:
            return EvidenceRejectionCode.SOURCE_STATUS_MISMATCH
        return None

    if (
        status_request.evaluated_at != request.evaluated_at
        or status_request.mode is not request.required_status_mode
        or status_request.as_of != request.required_as_of
    ):
        return EvidenceRejectionCode.STATUS_SCOPE_MISMATCH
    try:
        recomputed = resolve_version_status(status_request)
    except (TypeError, ValueError):
        return EvidenceRejectionCode.STATUS_UNVERIFIABLE
    if recomputed != decision:
        return EvidenceRejectionCode.STATUS_UNVERIFIABLE

    outcome_rejection = {
        VersionStatusOutcome.NO_MATCH: EvidenceRejectionCode.STATUS_NO_MATCH,
        VersionStatusOutcome.UNKNOWN: EvidenceRejectionCode.STATUS_UNVERIFIABLE,
        VersionStatusOutcome.CONTRADICTORY: (
            EvidenceRejectionCode.STATUS_CONTRADICTORY
        ),
        VersionStatusOutcome.INVALID_LINEAGE: (
            EvidenceRejectionCode.STATUS_INVALID_LINEAGE
        ),
    }.get(decision.outcome)
    if outcome_rejection is not None:
        return outcome_rejection

    expected_outcome = {
        VersionStatusMode.CURRENT: VersionStatusOutcome.VALIDATED_CURRENT,
        VersionStatusMode.AS_OF: VersionStatusOutcome.VALIDATED_HISTORICAL,
        VersionStatusMode.DRAFT: VersionStatusOutcome.VALIDATED_DRAFT,
    }.get(request.required_status_mode)
    if expected_outcome is None or decision.outcome is not expected_outcome:
        return EvidenceRejectionCode.STATUS_SCOPE_MISMATCH
    if (
        evidence.family_id is None
        or evidence.version_id is None
        or evidence.family_id != status_request.family_id
        or evidence.family_id != decision.family_id
    ):
        return EvidenceRejectionCode.STATUS_SCOPE_MISMATCH

    matching_records = tuple(
        record
        for record in status_request.records
        if record.document_id == evidence.document_id
        and record.document_version_id == evidence.version_id
    )
    if len(matching_records) != 1:
        return EvidenceRejectionCode.STATUS_UNVERIFIABLE
    record = matching_records[0]
    if record.registry_version_id not in decision.selected_registry_version_ids:
        return EvidenceRejectionCode.STALE_SOURCE
    resolved = tuple(
        item
        for item in decision.resolved_statuses
        if item.registry_version_id == record.registry_version_id
    )
    if len(resolved) != 1:
        return EvidenceRejectionCode.STATUS_UNVERIFIABLE
    if payload.source_status != resolved[0].status.value:
        return EvidenceRejectionCode.SOURCE_STATUS_MISMATCH
    return None


def _exclusion(
    candidate: OfficialEvidenceCandidate,
    code: EvidenceRejectionCode,
) -> EvidenceExclusion:
    return EvidenceExclusion(
        artifact_id=_safe_artifact_id(candidate),
        evidence_unit_id=_safe_evidence_id(candidate),
        code=code,
    )


def _safe_artifact_id(candidate: object) -> str:
    artifact = getattr(candidate, "artifact", None)
    value = getattr(artifact, "artifact_id", None)
    return value if isinstance(value, str) and value.strip() else "unknown-artifact"


def _safe_evidence_id(candidate: object) -> str:
    evidence = getattr(candidate, "canonical_evidence", None)
    value = getattr(evidence, "evidence_unit_id", None)
    return value if isinstance(value, str) and value.strip() else "unknown-evidence"
