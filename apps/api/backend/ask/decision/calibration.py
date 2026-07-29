from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable
from datetime import datetime
from pathlib import Path
from typing import Literal, Self

from pydantic import Field, field_validator, model_validator

from backend.ask.decision.models import (
    DECISION_POLICY_VERSION,
    DecisionModel,
    Intent,
    IntentConfidenceBand,
    ResponseStrategy,
    TimeDimension,
)
from backend.ask.decision.plan_policy import PlanClass

DECISION_CALIBRATION_SCHEMA_VERSION = "1"
DECISION_CALIBRATION_POLICY_VERSION = "ask-ai-decision-calibration-v1"
_UNAPPROVED_MARKERS = frozenset(
    {"n/a", "none", "pending", "placeholder", "tbd", "todo", "unknown"}
)
_UNAPPROVED_MARKER_PATTERN = re.compile(
    r"(?<![a-z0-9])(?:pending|placeholder|tbd|todo|unknown)(?![a-z0-9])",
    re.IGNORECASE,
)


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
    case_id: str = Field(min_length=1)
    query: str = Field(min_length=1)
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
    approved_at: datetime
    approval_reference: str = Field(min_length=1)
    payload_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @field_validator("reviewer_id", "reviewer_role", "approval_reference")
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
        return self


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
