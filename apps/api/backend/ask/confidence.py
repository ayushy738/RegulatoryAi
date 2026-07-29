from __future__ import annotations

import math
from decimal import Decimal
from enum import StrEnum
from types import MappingProxyType
from typing import Literal, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from backend.ask.decision.models import ConfidenceLabel, KnowledgeMode
from backend.ask.knowledge_modes import KnowledgeModeSectionPolicy

CONFIDENCE_SCHEMA_VERSION = "1"
CONFIDENCE_POLICY_VERSION = "ask-ai-confidence-v1"

DIMENSION_WEIGHTS = MappingProxyType({
    "evidence_authority": Decimal("0.25"),
    "retrieval_relevance": Decimal("0.15"),
    "claim_coverage": Decimal("0.20"),
    "source_agreement": Decimal("0.15"),
    "freshness_status_validity": Decimal("0.15"),
    "scope_resolution": Decimal("0.10"),
})


class ConfidencePenalty(StrEnum):
    UNRESOLVED_MATERIAL_CONTRADICTION = (
        "unresolved_material_contradiction"
    )
    STALE_FOR_CURRENT_QUERY = "stale_for_current_query"
    REQUIRED_EVIDENCE_CAPABILITY_UNAVAILABLE = (
        "required_evidence_capability_unavailable"
    )
    INFERRED_LEGAL_APPLICABILITY = "inferred_legal_applicability"
    SINGLE_SOURCE_HIGH_IMPACT_CLAIM = "single_source_high_impact_claim"
    INFERRED_MATERIAL_DATE_TYPE = "inferred_material_date_type"


PENALTY_POINTS = MappingProxyType({
    ConfidencePenalty.UNRESOLVED_MATERIAL_CONTRADICTION: Decimal("25"),
    ConfidencePenalty.STALE_FOR_CURRENT_QUERY: Decimal("20"),
    ConfidencePenalty.REQUIRED_EVIDENCE_CAPABILITY_UNAVAILABLE: Decimal("15"),
    ConfidencePenalty.INFERRED_LEGAL_APPLICABILITY: Decimal("10"),
    ConfidencePenalty.SINGLE_SOURCE_HIGH_IMPACT_CLAIM: Decimal("10"),
    ConfidencePenalty.INFERRED_MATERIAL_DATE_TYPE: Decimal("5"),
})


class HardUnknownCondition(StrEnum):
    DOCUMENT_NOT_INSPECTABLE = "document_not_inspectable"
    JURISDICTION_MATERIALLY_UNRESOLVED = (
        "jurisdiction_materially_unresolved"
    )
    CURRENT_STATUS_EVIDENCE_UNAVAILABLE = (
        "current_status_evidence_unavailable"
    )
    CENTRAL_CREDIBLE_SOURCE_CONFLICT = "central_credible_source_conflict"
    DEADLINE_OR_OBLIGATION_WITHOUT_INSPECTABLE_BASIS = (
        "deadline_or_obligation_without_inspectable_basis"
    )


class HighGateFailure(StrEnum):
    AUTHORITATIVE_EVIDENCE_REQUIRED = "authoritative_evidence_required"
    COVERAGE_BELOW_85 = "coverage_below_85"
    SCOPE_RESOLUTION_BELOW_85 = "scope_resolution_below_85"
    UNRESOLVED_CONTRADICTION = "unresolved_contradiction"
    FRESHNESS_NOT_FIT = "freshness_not_fit"


class StrictConfidenceReason(StrEnum):
    COMPLIANCE = "compliance"
    DEADLINE = "deadline"
    CURRENT_STATUS = "current_status"
    VERSION_COMPARISON = "version_comparison"


class ConfidenceModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        strict=True,
        str_strip_whitespace=True,
    )


class ConfidenceDimensions(ConfidenceModel):
    evidence_authority: float = Field(ge=0, le=100)
    retrieval_relevance: float = Field(ge=0, le=100)
    claim_coverage: float = Field(ge=0, le=100)
    source_agreement: float = Field(ge=0, le=100)
    freshness_status_validity: float = Field(ge=0, le=100)
    scope_resolution: float = Field(ge=0, le=100)

    @field_validator("*")
    @classmethod
    def reject_nonfinite(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("Confidence dimensions must be finite")
        return value


class ClaimConfidenceInput(ConfidenceModel):
    claim_id: str = Field(min_length=1)
    section_policy: KnowledgeModeSectionPolicy
    dimensions: ConfidenceDimensions
    penalties: tuple[ConfidencePenalty, ...] = ()
    hard_unknowns: tuple[HardUnknownCondition, ...] = ()
    authoritative_evidence: bool
    freshness_meets_query: bool
    critical_input_ceiling: ConfidenceLabel = ConfidenceLabel.HIGH

    @field_validator("claim_id")
    @classmethod
    def normalize_claim_id(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Claim ID cannot be blank")
        return normalized

    @model_validator(mode="after")
    def validate_conditions(self) -> Self:
        if len(set(self.penalties)) != len(self.penalties):
            raise ValueError("Confidence penalties must be unique")
        if len(set(self.hard_unknowns)) != len(self.hard_unknowns):
            raise ValueError("Hard Unknown conditions must be unique")
        return self


class SectionConfidenceInput(ConfidenceModel):
    section_key: str = Field(min_length=1)
    claim_ids: tuple[str, ...] = Field(min_length=1)
    importance_weight: float = Field(gt=0, le=100)
    critical: bool = True

    @field_validator("section_key")
    @classmethod
    def normalize_section_key(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Section key cannot be blank")
        return normalized

    @field_validator("claim_ids")
    @classmethod
    def validate_claim_ids(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(item.strip() for item in value)
        if any(not item for item in normalized):
            raise ValueError("Section claim IDs cannot be blank")
        if len(set(normalized)) != len(normalized):
            raise ValueError("Section claim IDs must be unique")
        return normalized

    @field_validator("importance_weight")
    @classmethod
    def reject_nonfinite_weight(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("Section importance must be finite")
        return value


class ConfidenceCalculationRequest(ConfidenceModel):
    schema_version: Literal["1"] = CONFIDENCE_SCHEMA_VERSION
    policy_version: str = Field(
        default=CONFIDENCE_POLICY_VERSION,
        min_length=1,
    )
    claims: tuple[ClaimConfidenceInput, ...] = Field(min_length=1)
    sections: tuple[SectionConfidenceInput, ...] = Field(min_length=1)
    strict_reasons: tuple[StrictConfidenceReason, ...] = ()

    @model_validator(mode="after")
    def validate_graph(self) -> Self:
        claim_ids = tuple(item.claim_id for item in self.claims)
        section_keys = tuple(item.section_key for item in self.sections)
        if len(set(claim_ids)) != len(claim_ids):
            raise ValueError("Confidence claim IDs must be unique")
        if len(set(section_keys)) != len(section_keys):
            raise ValueError("Confidence section keys must be unique")
        if len(set(self.strict_reasons)) != len(self.strict_reasons):
            raise ValueError("Strict confidence reasons must be unique")
        if not any(section.critical for section in self.sections):
            raise ValueError("Overall confidence requires a critical section")

        referenced = tuple(
            claim_id
            for section in self.sections
            for claim_id in section.claim_ids
        )
        if len(set(referenced)) != len(referenced):
            raise ValueError("A claim can belong to only one section")
        if set(referenced) != set(claim_ids):
            raise ValueError("Sections must cover every confidence claim exactly")

        claims_by_id = {item.claim_id: item for item in self.claims}
        for section in self.sections:
            section_claims = tuple(
                claims_by_id[claim_id] for claim_id in section.claim_ids
            )
            if any(
                claim.section_policy.section_key != section.section_key
                for claim in section_claims
            ):
                raise ValueError("Claim section policy must match its section")
            if len({claim.section_policy.mode for claim in section_claims}) != 1:
                raise ValueError("A confidence section must use one knowledge mode")
        return self


class ClaimConfidenceResult(ConfidenceModel):
    claim_id: str
    section_key: str
    mode: KnowledgeMode
    base_score: float = Field(ge=0, le=100)
    penalty_points: int = Field(ge=0)
    final_score: float = Field(ge=0, le=100)
    numeric_label: ConfidenceLabel
    final_label: ConfidenceLabel
    applied_ceiling: ConfidenceLabel
    penalties: tuple[ConfidencePenalty, ...]
    hard_unknowns: tuple[HardUnknownCondition, ...]
    high_gate_failures: tuple[HighGateFailure, ...]


class SectionConfidenceResult(ConfidenceModel):
    section_key: str
    mode: KnowledgeMode
    claim_ids: tuple[str, ...]
    coverage_weighted_mean: float = Field(ge=0, le=100)
    lowest_claim_score: float = Field(ge=0, le=100)
    score: float = Field(ge=0, le=100)
    label: ConfidenceLabel
    importance_weight: float = Field(gt=0, le=100)
    critical: bool


class OverallConfidenceResult(ConfidenceModel):
    importance_weighted_mean: float = Field(ge=0, le=100)
    lowest_critical_section_score: float = Field(ge=0, le=100)
    score: float = Field(ge=0, le=100)
    label: ConfidenceLabel
    strict_reasons: tuple[StrictConfidenceReason, ...]


class ConfidenceCalculationResult(ConfidenceModel):
    schema_version: Literal["1"] = CONFIDENCE_SCHEMA_VERSION
    policy_version: str = Field(min_length=1)
    claims: tuple[ClaimConfidenceResult, ...]
    sections: tuple[SectionConfidenceResult, ...]
    overall: OverallConfidenceResult


def calculate_confidence(
    request: ConfidenceCalculationRequest,
) -> ConfidenceCalculationResult:
    validated = ConfidenceCalculationRequest.model_validate(
        request.model_dump(mode="python"),
        strict=True,
    )
    claim_results: list[ClaimConfidenceResult] = []
    claim_scores: dict[str, Decimal] = {}
    claim_inputs = {item.claim_id: item for item in validated.claims}

    for claim in validated.claims:
        result, score = _calculate_claim(claim)
        claim_results.append(result)
        claim_scores[claim.claim_id] = score

    result_by_claim = {item.claim_id: item for item in claim_results}
    section_results: list[SectionConfidenceResult] = []
    section_scores: dict[str, Decimal] = {}
    for section in validated.sections:
        result, score = _calculate_section(
            section,
            claim_inputs,
            result_by_claim,
            claim_scores,
        )
        section_results.append(result)
        section_scores[section.section_key] = score

    overall = _calculate_overall(
        validated,
        tuple(claim_results),
        tuple(section_results),
        section_scores,
    )
    return ConfidenceCalculationResult(
        policy_version=validated.policy_version,
        claims=tuple(claim_results),
        sections=tuple(section_results),
        overall=overall,
    )


def _calculate_claim(
    claim: ClaimConfidenceInput,
) -> tuple[ClaimConfidenceResult, Decimal]:
    dimensions = claim.dimensions.model_dump(mode="python")
    base_score = sum(
        Decimal(str(dimensions[name])) * weight
        for name, weight in DIMENSION_WEIGHTS.items()
    )
    penalty_points = sum(PENALTY_POINTS[item] for item in claim.penalties)
    final_score = min(Decimal("100"), max(Decimal("0"), base_score - penalty_points))
    numeric_label = _label_for_score(final_score)
    high_gate_failures = _high_gate_failures(claim)
    ceiling = _minimum_label(
        claim.section_policy.confidence_ceiling,
        claim.critical_input_ceiling,
    )
    final_label = _minimum_label(numeric_label, ceiling)
    if numeric_label is ConfidenceLabel.HIGH and high_gate_failures:
        final_label = _minimum_label(final_label, ConfidenceLabel.MEDIUM)
    if claim.hard_unknowns:
        final_label = ConfidenceLabel.UNKNOWN

    return (
        ClaimConfidenceResult(
            claim_id=claim.claim_id,
            section_key=claim.section_policy.section_key,
            mode=claim.section_policy.mode,
            base_score=float(base_score),
            penalty_points=int(penalty_points),
            final_score=float(final_score),
            numeric_label=numeric_label,
            final_label=final_label,
            applied_ceiling=ceiling,
            penalties=claim.penalties,
            hard_unknowns=claim.hard_unknowns,
            high_gate_failures=high_gate_failures,
        ),
        final_score,
    )


def _calculate_section(
    section: SectionConfidenceInput,
    claim_inputs: dict[str, ClaimConfidenceInput],
    claim_results: dict[str, ClaimConfidenceResult],
    claim_scores: dict[str, Decimal],
) -> tuple[SectionConfidenceResult, Decimal]:
    coverage_weights = {
        claim_id: Decimal(
            str(claim_inputs[claim_id].dimensions.claim_coverage)
        )
        for claim_id in section.claim_ids
    }
    weight_total = sum(coverage_weights.values())
    weighted_mean = (
        sum(
            claim_scores[claim_id] * coverage_weights[claim_id]
            for claim_id in section.claim_ids
        )
        / weight_total
        if weight_total
        else Decimal("0")
    )
    lowest_score = min(claim_scores[claim_id] for claim_id in section.claim_ids)
    score = Decimal("0.70") * weighted_mean + Decimal("0.30") * lowest_score
    weakest_claim_label = _minimum_label(
        *(claim_results[claim_id].final_label for claim_id in section.claim_ids)
    )
    label = _minimum_label(_label_for_score(score), weakest_claim_label)
    first_claim = claim_inputs[section.claim_ids[0]]
    return (
        SectionConfidenceResult(
            section_key=section.section_key,
            mode=first_claim.section_policy.mode,
            claim_ids=section.claim_ids,
            coverage_weighted_mean=float(weighted_mean),
            lowest_claim_score=float(lowest_score),
            score=float(score),
            label=label,
            importance_weight=section.importance_weight,
            critical=section.critical,
        ),
        score,
    )


def _calculate_overall(
    request: ConfidenceCalculationRequest,
    claims: tuple[ClaimConfidenceResult, ...],
    sections: tuple[SectionConfidenceResult, ...],
    section_scores: dict[str, Decimal],
) -> OverallConfidenceResult:
    importance_total = sum(
        Decimal(str(section.importance_weight)) for section in request.sections
    )
    weighted_mean = sum(
        section_scores[section.section_key]
        * Decimal(str(section.importance_weight))
        for section in request.sections
    ) / importance_total
    critical_sections = tuple(
        section for section in sections if section.critical
    )
    lowest_critical_score = min(
        section_scores[section.section_key] for section in critical_sections
    )
    score = (
        Decimal("0.70") * weighted_mean
        + Decimal("0.30") * lowest_critical_score
    )
    weakest_critical_label = _minimum_label(
        *(section.label for section in critical_sections)
    )
    label = _minimum_label(_label_for_score(score), weakest_critical_label)
    if request.strict_reasons:
        label = _minimum_label(
            label,
            _minimum_label(*(claim.final_label for claim in claims)),
        )
    return OverallConfidenceResult(
        importance_weighted_mean=float(weighted_mean),
        lowest_critical_section_score=float(lowest_critical_score),
        score=float(score),
        label=label,
        strict_reasons=request.strict_reasons,
    )


def _high_gate_failures(
    claim: ClaimConfidenceInput,
) -> tuple[HighGateFailure, ...]:
    failures: list[HighGateFailure] = []
    if not claim.authoritative_evidence:
        failures.append(HighGateFailure.AUTHORITATIVE_EVIDENCE_REQUIRED)
    if claim.dimensions.claim_coverage < 85:
        failures.append(HighGateFailure.COVERAGE_BELOW_85)
    if claim.dimensions.scope_resolution < 85:
        failures.append(HighGateFailure.SCOPE_RESOLUTION_BELOW_85)
    if (
        ConfidencePenalty.UNRESOLVED_MATERIAL_CONTRADICTION
        in claim.penalties
    ):
        failures.append(HighGateFailure.UNRESOLVED_CONTRADICTION)
    if (
        not claim.freshness_meets_query
        or ConfidencePenalty.STALE_FOR_CURRENT_QUERY in claim.penalties
    ):
        failures.append(HighGateFailure.FRESHNESS_NOT_FIT)
    return tuple(failures)


def _label_for_score(score: Decimal) -> ConfidenceLabel:
    if score >= Decimal("80"):
        return ConfidenceLabel.HIGH
    if score >= Decimal("60"):
        return ConfidenceLabel.MEDIUM
    if score >= Decimal("35"):
        return ConfidenceLabel.LOW
    return ConfidenceLabel.UNKNOWN


_LABEL_ORDER = {
    ConfidenceLabel.UNKNOWN: 0,
    ConfidenceLabel.LOW: 1,
    ConfidenceLabel.MEDIUM: 2,
    ConfidenceLabel.HIGH: 3,
}


def _minimum_label(
    first: ConfidenceLabel,
    *rest: ConfidenceLabel,
) -> ConfidenceLabel:
    return min((first, *rest), key=_LABEL_ORDER.__getitem__)
