from __future__ import annotations

from enum import StrEnum
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from backend.ask.evidence_admission import (
    EVIDENCE_ADMISSION_POLICY_VERSION,
    AdmittedOfficialEvidence,
    OfficialEvidenceAdmissionResult,
)
from backend.ask.orchestration.contracts import (
    ArtifactEnvelope,
    CandidateClaimPayload,
    CapabilityScope,
    CapabilityTerminalState,
    ContentDerivation,
    KnowledgeMode,
    OrchestratorCapability,
    ProvenanceClass,
    VerificationStatus,
)

CANDIDATE_CLAIM_SCHEMA_VERSION = "1"
CANDIDATE_CLAIM_POLICY_VERSION = "ask-ai-candidate-claim-v1"


class CandidateClaimRejectionCode(StrEnum):
    INVALID_CONTRACT = "CLAIM_INVALID_CONTRACT"
    ADMISSION_INPUT_INVALID = "CLAIM_ADMISSION_INPUT_INVALID"
    DUPLICATE_IDENTITY = "CLAIM_DUPLICATE_IDENTITY"
    IDENTITY_COLLISION = "CLAIM_IDENTITY_COLLISION"
    SCOPE_MISMATCH = "CLAIM_SCOPE_MISMATCH"
    NOT_MATERIAL = "CLAIM_NOT_MATERIAL"
    SUPPORT_REQUIRED = "CLAIM_SUPPORT_REQUIRED"
    SUPPORT_DUPLICATE = "CLAIM_SUPPORT_DUPLICATE"
    SUPPORT_NOT_ADMITTED = "CLAIM_SUPPORT_NOT_ADMITTED"
    SUPPORT_SCOPE_MISMATCH = "CLAIM_SUPPORT_SCOPE_MISMATCH"
    SUPPORT_PROVENANCE_MISMATCH = "CLAIM_SUPPORT_PROVENANCE_MISMATCH"
    PROVENANCE_MISMATCH = "CLAIM_PROVENANCE_MISMATCH"
    LINEAGE_MISMATCH = "CLAIM_LINEAGE_MISMATCH"
    TERMINAL_STATUS_INVALID = "CLAIM_TERMINAL_STATUS_INVALID"
    CONFLICTING = "CLAIM_CONFLICTING"


class CandidateClaimModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        strict=True,
        str_strip_whitespace=True,
    )


class CandidateClaimBatchRequest(CandidateClaimModel):
    schema_version: Literal["1"] = CANDIDATE_CLAIM_SCHEMA_VERSION
    policy_version: str = Field(
        default=CANDIDATE_CLAIM_POLICY_VERSION,
        min_length=1,
    )
    approved_scope: CapabilityScope
    evidence_admissions: tuple[OfficialEvidenceAdmissionResult, ...]
    candidate_claims: tuple[ArtifactEnvelope, ...]

    @model_validator(mode="after")
    def require_current_admission_policy(self) -> Self:
        if any(
            admission.policy_version != EVIDENCE_ADMISSION_POLICY_VERSION
            for admission in self.evidence_admissions
        ):
            raise ValueError("Candidate claims require the current admission policy")
        return self


class CandidateClaimExclusion(CandidateClaimModel):
    claim_id: str
    code: CandidateClaimRejectionCode


class CandidateClaimBatchResult(CandidateClaimModel):
    schema_version: Literal["1"] = CANDIDATE_CLAIM_SCHEMA_VERSION
    policy_version: str = Field(min_length=1)
    accepted_claims: tuple[ArtifactEnvelope, ...]
    exclusions: tuple[CandidateClaimExclusion, ...]

    @property
    def ready_for_verification(self) -> bool:
        return bool(self.accepted_claims)


def admit_candidate_claims(
    request: CandidateClaimBatchRequest,
) -> CandidateClaimBatchResult:
    try:
        validated_request = CandidateClaimBatchRequest.model_validate(
            {
                **request.model_dump(mode="python"),
                "evidence_admissions": (),
                "candidate_claims": (),
            },
            strict=True,
        )
    except ValidationError:
        return _invalid_request_result(request)

    evidence = _validated_evidence(request.evidence_admissions)
    if evidence is None:
        return CandidateClaimBatchResult(
            policy_version=validated_request.policy_version,
            accepted_claims=(),
            exclusions=tuple(
                CandidateClaimExclusion(
                    claim_id=_safe_claim_id(claim),
                    code=CandidateClaimRejectionCode.ADMISSION_INPUT_INVALID,
                )
                for claim in request.candidate_claims
            ),
        )

    accepted: list[ArtifactEnvelope] = []
    exclusions: list[CandidateClaimExclusion] = []
    seen_claim_ids: set[str] = set()

    for untrusted_claim in request.candidate_claims:
        try:
            claim = ArtifactEnvelope.model_validate(
                untrusted_claim.model_dump(mode="python"),
                strict=True,
            )
        except (AttributeError, ValidationError):
            exclusions.append(
                CandidateClaimExclusion(
                    claim_id=_safe_claim_id(untrusted_claim),
                    code=CandidateClaimRejectionCode.INVALID_CONTRACT,
                )
            )
            continue

        claim_id = claim.artifact_id
        if claim_id in seen_claim_ids:
            exclusions.append(
                _exclusion(claim, CandidateClaimRejectionCode.DUPLICATE_IDENTITY)
            )
            continue
        seen_claim_ids.add(claim_id)
        if claim_id in evidence:
            exclusions.append(
                _exclusion(claim, CandidateClaimRejectionCode.IDENTITY_COLLISION)
            )
            continue

        rejection = _claim_rejection(validated_request, claim, evidence)
        if rejection is not None:
            exclusions.append(_exclusion(claim, rejection))
            continue
        accepted.append(claim)

    return CandidateClaimBatchResult(
        policy_version=validated_request.policy_version,
        accepted_claims=tuple(accepted),
        exclusions=tuple(exclusions),
    )


def _validated_evidence(
    admissions: tuple[OfficialEvidenceAdmissionResult, ...],
) -> dict[str, AdmittedOfficialEvidence] | None:
    output: dict[str, AdmittedOfficialEvidence] = {}
    excluded_ids: set[str] = set()
    for untrusted_admission in admissions:
        try:
            admission = OfficialEvidenceAdmissionResult.model_validate(
                untrusted_admission.model_dump(mode="python"),
                strict=True,
            )
        except (AttributeError, ValidationError):
            return None
        if admission.policy_version != EVIDENCE_ADMISSION_POLICY_VERSION:
            return None
        for exclusion in admission.exclusions:
            if exclusion.evidence_unit_id in excluded_ids:
                return None
            excluded_ids.add(exclusion.evidence_unit_id)
        for unit in admission.admitted:
            artifact_id = unit.artifact.artifact_id
            if (
                artifact_id != unit.canonical_evidence.evidence_unit_id
                or artifact_id in output
                or artifact_id in excluded_ids
            ):
                return None
            output[artifact_id] = unit
    if set(output).intersection(excluded_ids):
        return None
    return output


def _claim_rejection(
    request: CandidateClaimBatchRequest,
    claim: ArtifactEnvelope,
    evidence: dict[str, AdmittedOfficialEvidence],
) -> CandidateClaimRejectionCode | None:
    if not isinstance(claim.payload, CandidateClaimPayload):
        return CandidateClaimRejectionCode.INVALID_CONTRACT
    if not _is_narrowed_scope(claim.scope, request.approved_scope):
        return CandidateClaimRejectionCode.SCOPE_MISMATCH
    if not claim.payload.material:
        return CandidateClaimRejectionCode.NOT_MATERIAL

    support_ids = claim.payload.supporting_artifact_ids
    if not support_ids or any(not item.strip() for item in support_ids):
        return CandidateClaimRejectionCode.SUPPORT_REQUIRED
    if len(set(support_ids)) != len(support_ids):
        return CandidateClaimRejectionCode.SUPPORT_DUPLICATE
    if any(item not in evidence for item in support_ids):
        return CandidateClaimRejectionCode.SUPPORT_NOT_ADMITTED
    if claim.capability_status not in {
        CapabilityTerminalState.SATISFIED,
        CapabilityTerminalState.PARTIAL,
    }:
        return CandidateClaimRejectionCode.TERMINAL_STATUS_INVALID
    if claim.conflicts:
        return CandidateClaimRejectionCode.CONFLICTING

    lineage = claim.provenance
    if (
        lineage is None
        or lineage.provenance_class
        is not ProvenanceClass.INTERNAL_REGULATORY_CORPUS
        or lineage.knowledge_mode is not KnowledgeMode.GROUNDED_REGULATORY
        or lineage.verification_status is not VerificationStatus.PENDING
        or lineage.derivation
        not in {
            ContentDerivation.EXTRACTED,
            ContentDerivation.INFERRED,
            ContentDerivation.SUMMARIZED,
        }
    ):
        return CandidateClaimRejectionCode.PROVENANCE_MISMATCH
    if not lineage.transformations:
        return CandidateClaimRejectionCode.LINEAGE_MISMATCH
    final_step = lineage.transformations[-1]
    if (
        final_step.capability is not OrchestratorCapability.RESPONSE_COMPOSER
        or final_step.derivation is not lineage.derivation
        or final_step.input_artifact_ids != support_ids
        or final_step.input_provenance
        != (ProvenanceClass.INTERNAL_REGULATORY_CORPUS,)
        or final_step.output_provenance
        is not ProvenanceClass.INTERNAL_REGULATORY_CORPUS
    ):
        return CandidateClaimRejectionCode.LINEAGE_MISMATCH

    question_id = claim.scope.atomic_question_ids[0]
    for support_id in support_ids:
        unit = evidence[support_id]
        if (
            unit.artifact.scope != claim.scope
            or question_id not in unit.canonical_evidence.question_ids
        ):
            return CandidateClaimRejectionCode.SUPPORT_SCOPE_MISMATCH
        support_lineage = unit.artifact.provenance
        if (
            support_lineage is None
            or support_lineage.provenance_class
            is not ProvenanceClass.INTERNAL_REGULATORY_CORPUS
            or support_lineage.knowledge_mode
            is not KnowledgeMode.GROUNDED_REGULATORY
        ):
            return CandidateClaimRejectionCode.SUPPORT_PROVENANCE_MISMATCH
    return None


def _is_narrowed_scope(
    claim_scope: CapabilityScope,
    approved_scope: CapabilityScope,
) -> bool:
    return (
        len(claim_scope.atomic_question_ids) == 1
        and len(claim_scope.section_keys) == 1
        and set(claim_scope.atomic_question_ids).issubset(
            approved_scope.atomic_question_ids
        )
        and set(claim_scope.section_keys).issubset(approved_scope.section_keys)
        and claim_scope.entity_ids == approved_scope.entity_ids
        and claim_scope.jurisdiction == approved_scope.jurisdiction
        and claim_scope.stakeholder == approved_scope.stakeholder
        and claim_scope.time_scope == approved_scope.time_scope
        and claim_scope.date_semantics == approved_scope.date_semantics
        and claim_scope.constraints == approved_scope.constraints
    )


def _invalid_request_result(
    request: CandidateClaimBatchRequest,
) -> CandidateClaimBatchResult:
    return CandidateClaimBatchResult(
        policy_version=CANDIDATE_CLAIM_POLICY_VERSION,
        accepted_claims=(),
        exclusions=tuple(
            CandidateClaimExclusion(
                claim_id=_safe_claim_id(claim),
                code=CandidateClaimRejectionCode.INVALID_CONTRACT,
            )
            for claim in getattr(request, "candidate_claims", ())
        ),
    )


def _exclusion(
    claim: ArtifactEnvelope,
    code: CandidateClaimRejectionCode,
) -> CandidateClaimExclusion:
    return CandidateClaimExclusion(claim_id=claim.artifact_id, code=code)


def _safe_claim_id(claim: object) -> str:
    value = getattr(claim, "artifact_id", None)
    return value if isinstance(value, str) and value.strip() else "unknown-claim"
