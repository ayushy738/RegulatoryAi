from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from collections.abc import Iterable
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Literal, Self

from pydantic import Field, field_validator, model_validator

from backend.ask.decision.entity_policy import EntityResolutionRequest
from backend.ask.decision.models import (
    DECISION_POLICY_VERSION,
    DecisionModel,
    Intent,
    IntentConfidenceBand,
    ResponseStrategy,
    TimeDimension,
)
from backend.ask.decision.plan_policy import PlanClass, PlanRequest
from backend.ask.decision.policy import IntentSignals

DECISION_CALIBRATION_SCHEMA_VERSION = "1"
DECISION_CALIBRATION_POLICY_VERSION = "ask-ai-decision-calibration-v1"
_UNAPPROVED_MARKERS = frozenset(
    {"n/a", "none", "pending", "placeholder", "tbd", "todo", "unknown"}
)
_UNAPPROVED_MARKER_PATTERN = re.compile(
    r"(?<![a-z0-9])(?:pending|placeholder|tbd|todo|unknown)(?![a-z0-9])",
    re.IGNORECASE,
)


class CalibrationSourceKind(StrEnum):
    PUBLIC = "public"
    DEIDENTIFIED = "deidentified"
    SYNTHETIC = "synthetic"


class CalibrationTag(StrEnum):
    HIGH_RISK = "high_risk"
    AMBIGUITY = "ambiguity"
    ENTITY = "entity"
    TEMPORAL = "temporal"
    MULTI_PART = "multi_part"
    CONVERSATION_CONTEXT = "conversation_context"
    CURRENT_INTELLIGENCE = "current_intelligence"
    ADVERSARIAL = "adversarial"


class DecisionCalibrationThresholds(DecisionModel):
    intent_certain_min: float = Field(ge=0, le=1)
    intent_certain_competing_gap_min: float = Field(ge=0, le=1)
    intent_strong_min: float = Field(ge=0, le=1)
    intent_bounded_min: float = Field(ge=0, le=1)
    entity_high_risk_min: float = Field(ge=0, le=1)

    @model_validator(mode="after")
    def validate_intent_threshold_order(self) -> Self:
        if not (
            self.intent_certain_min
            > self.intent_strong_min
            > self.intent_bounded_min
        ):
            raise ValueError(
                "Intent confidence thresholds must be strictly ordered"
            )
        return self


class DecisionCalibrationCase(DecisionModel):
    case_id: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]{0,199}$")
    query: str = Field(min_length=1)
    source_kind: CalibrationSourceKind
    source_template_id: str = Field(
        pattern=r"^[a-z0-9][a-z0-9._-]{0,199}$"
    )
    evaluation_tags: tuple[CalibrationTag, ...] = ()
    holdout: bool
    intent_signals: IntentSignals
    intent_score: float = Field(ge=0, le=1)
    intent_competing_gap: float = Field(ge=0, le=1)
    intent_material_collision: bool
    intent_shared_safe_scope: bool
    entity_requests: tuple[EntityResolutionRequest, ...] = ()
    time_expression: str | None = None
    time_intent: Intent
    plan_request: PlanRequest
    expected_primary_intent: Intent
    expected_secondary_intents: tuple[Intent, ...] = ()
    expected_response_strategy: ResponseStrategy
    expected_intent_confidence_band: IntentConfidenceBand
    expected_entity_canonical_ids: tuple[str, ...] = ()
    expected_entity_min_confidence: float | None = Field(
        default=None,
        ge=0,
        le=1,
    )
    expected_time_dimension: TimeDimension | None = None
    expected_plan_class: PlanClass
    clarification_required: bool
    regulatory_rationale: str = Field(min_length=1)

    @field_validator(
        "case_id",
        "query",
        "regulatory_rationale",
    )
    @classmethod
    def normalize_required_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Calibration case text cannot be blank")
        return normalized

    @field_validator("regulatory_rationale")
    @classmethod
    def reject_placeholder_rationale(cls, value: str) -> str:
        if value.casefold() in _UNAPPROVED_MARKERS:
            raise ValueError("Regulatory rationale cannot use a placeholder")
        return value

    @field_validator("expected_entity_canonical_ids")
    @classmethod
    def validate_entity_ids(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(entity_id.strip() for entity_id in value)
        if any(not entity_id for entity_id in normalized):
            raise ValueError("Expected entity IDs cannot be blank")
        if len(normalized) != len(set(normalized)):
            raise ValueError("Expected entity IDs must be unique")
        return normalized

    @field_validator("evaluation_tags")
    @classmethod
    def validate_tags(
        cls,
        value: tuple[CalibrationTag, ...],
    ) -> tuple[CalibrationTag, ...]:
        if len(value) != len(set(value)):
            raise ValueError("Calibration evaluation tags must be unique")
        return value

    @model_validator(mode="after")
    def validate_distinct_intents(self) -> Self:
        if self.expected_primary_intent in self.expected_secondary_intents:
            raise ValueError("The expected primary intent cannot also be secondary")
        if len(self.expected_secondary_intents) != len(
            set(self.expected_secondary_intents)
        ):
            raise ValueError("Expected secondary intents must be unique")
        return self


class DecisionCalibrationApproval(DecisionModel):
    status: Literal["approved"]
    reviewer_id: str = Field(min_length=1)
    reviewer_role: str = Field(min_length=1)
    technical_reviewer_id: str = Field(min_length=1)
    technical_reviewer_role: str = Field(min_length=1)
    creator_id: str = Field(min_length=1)
    review_method: Literal["independent_exact_agreement"]
    approved_at: datetime
    approval_reference: str = Field(min_length=1)
    payload_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @field_validator(
        "reviewer_id",
        "reviewer_role",
        "technical_reviewer_id",
        "technical_reviewer_role",
        "creator_id",
        "approval_reference",
    )
    @classmethod
    def validate_approval_provenance(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Approval provenance cannot be blank")
        normalized_casefold = normalized.casefold()
        if (
            normalized_casefold in _UNAPPROVED_MARKERS
            or _UNAPPROVED_MARKER_PATTERN.search(normalized) is not None
        ):
            raise ValueError("Approval provenance cannot use a placeholder")
        return normalized

    @model_validator(mode="after")
    def require_separated_review_identities(self) -> Self:
        identities = (
            self.creator_id,
            self.technical_reviewer_id,
            self.reviewer_id,
        )
        if len(set(identities)) != len(identities):
            raise ValueError(
                "Calibration creator and reviewers must be distinct identities"
            )
        return self

    @field_validator("approved_at")
    @classmethod
    def require_aware_approval_time(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("The approval time must be timezone-aware")
        return value


class DecisionCalibrationDataset(DecisionModel):
    schema_version: Literal["1"] = DECISION_CALIBRATION_SCHEMA_VERSION
    calibration_policy_version: Literal[
        "ask-ai-decision-calibration-v1"
    ] = DECISION_CALIBRATION_POLICY_VERSION
    decision_policy_version: Literal[
        "ask-ai-decision-v1"
    ] = DECISION_POLICY_VERSION
    dataset_kind: Literal["contract_test", "production_golden"]
    dataset_version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    entity_registry_version: str = Field(min_length=1)
    fixed_clock: datetime
    thresholds: DecisionCalibrationThresholds
    approval: DecisionCalibrationApproval
    cases: tuple[DecisionCalibrationCase, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_approved_case_set(self) -> Self:
        case_ids = tuple(case.case_id for case in self.cases)
        if len(case_ids) != len(set(case_ids)):
            raise ValueError("Calibration case IDs must be unique")
        expected_digest = calibration_payload_sha256(
            thresholds=self.thresholds,
            cases=self.cases,
        )
        if self.approval.payload_sha256 != expected_digest:
            raise ValueError(
                "The approved calibration payload checksum does not match"
            )
        if self.fixed_clock.tzinfo is None or self.fixed_clock.utcoffset() is None:
            raise ValueError("The calibration fixed clock must be timezone-aware")
        if self.dataset_kind == "production_golden":
            _validate_production_composition(self.cases)
        return self


def _validate_production_composition(
    cases: tuple[DecisionCalibrationCase, ...],
) -> None:
    if len(cases) < 600:
        raise ValueError("The approved production calibration requires 600 cases")
    intent_counts = Counter(case.expected_primary_intent for case in cases)
    if any(intent_counts[intent] < 30 for intent in Intent):
        raise ValueError("Every primary intent requires at least 30 cases")
    tag_minimums = {
        CalibrationTag.HIGH_RISK: 120,
        CalibrationTag.AMBIGUITY: 100,
        CalibrationTag.ENTITY: 100,
        CalibrationTag.TEMPORAL: 100,
        CalibrationTag.MULTI_PART: 75,
        CalibrationTag.CONVERSATION_CONTEXT: 75,
        CalibrationTag.CURRENT_INTELLIGENCE: 60,
    }
    tag_counts = Counter(
        tag for case in cases for tag in case.evaluation_tags
    )
    for tag, minimum in tag_minimums.items():
        if tag_counts[tag] < minimum:
            raise ValueError(
                f"Calibration composition requires at least {minimum} {tag.value} cases"
            )
    if sum(case.holdout for case in cases) < len(cases) * 0.20:
        raise ValueError("At least 20% of calibration cases must be holdout cases")
    template_counts = Counter(case.source_template_id for case in cases)
    if max(template_counts.values()) > len(cases) * 0.10:
        raise ValueError("A source template cannot contribute more than 10% of cases")
    if all(case.source_kind is CalibrationSourceKind.SYNTHETIC for case in cases):
        raise ValueError("The production calibration cannot be synthetic-only")
    strategy_counts = Counter(case.expected_response_strategy for case in cases)
    if any(strategy_counts[strategy] < 10 for strategy in ResponseStrategy):
        raise ValueError("Every response strategy requires at least 10 cases")
    plan_counts = Counter(case.expected_plan_class for case in cases)
    if any(plan_counts[plan_class] < 10 for plan_class in PlanClass):
        raise ValueError("Every plan class requires at least 10 cases")


def calibration_payload_sha256(
    *,
    thresholds: DecisionCalibrationThresholds,
    cases: Iterable[DecisionCalibrationCase],
) -> str:
    payload = json.dumps(
        {
            "calibration_policy_version": DECISION_CALIBRATION_POLICY_VERSION,
            "cases": [case.model_dump(mode="json") for case in cases],
            "decision_policy_version": DECISION_POLICY_VERSION,
            "schema_version": DECISION_CALIBRATION_SCHEMA_VERSION,
            "thresholds": thresholds.model_dump(mode="json"),
        },
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def load_decision_calibration_dataset(
    path: str | Path,
) -> DecisionCalibrationDataset:
    return DecisionCalibrationDataset.model_validate_json(
        Path(path).read_text(encoding="utf-8")
    )
