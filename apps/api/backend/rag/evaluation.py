from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime
from enum import StrEnum
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from backend.ask.decision import Intent
from backend.rag.models import (
    RetrievalBranch,
    RetrievalBranchHealth,
    RetrievalBranchStatus,
)

RETRIEVAL_EVALUATION_SCHEMA_VERSION = "1"
RETRIEVAL_EVALUATION_POLICY_VERSION = "ask-ai-retrieval-evaluation-v1"


class EvaluationModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class EvaluationReviewStatus(StrEnum):
    DRAFT = "draft"
    APPROVED = "approved"


class EvaluationVerdict(StrEnum):
    UNAPPROVED = "unapproved"
    PASS = "pass"
    FAIL = "fail"


class BranchEvaluationObservation(EvaluationModel):
    branch: RetrievalBranch
    status: RetrievalBranchStatus
    health: RetrievalBranchHealth
    latency_ms: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_health(self) -> Self:
        expected_health = {
            RetrievalBranchStatus.SATISFIED: RetrievalBranchHealth.HEALTHY,
            RetrievalBranchStatus.NO_MATCH: RetrievalBranchHealth.HEALTHY,
            RetrievalBranchStatus.PARTIAL: RetrievalBranchHealth.DEGRADED,
            RetrievalBranchStatus.SKIPPED: RetrievalBranchHealth.NOT_RUN,
            RetrievalBranchStatus.TIMED_OUT: RetrievalBranchHealth.FAILED,
            RetrievalBranchStatus.UNAVAILABLE: RetrievalBranchHealth.FAILED,
            RetrievalBranchStatus.INVALID_OUTPUT: RetrievalBranchHealth.FAILED,
        }[self.status]
        if self.health is not expected_health:
            raise ValueError("Retrieval evaluation status and health disagree")
        return self


class RetrievalEvaluationCase(EvaluationModel):
    case_id: str = Field(pattern=r"^[a-z0-9][a-z0-9._:-]{0,199}$")
    query: str = Field(min_length=1)
    intent: Intent
    expected_relevant_evidence_ids: tuple[str, ...] = ()
    expected_no_match: bool = False
    observed_ranked_evidence_ids: tuple[str, ...]
    end_to_end_latency_ms: int = Field(ge=0)
    branch_observations: tuple[BranchEvaluationObservation, ...] = Field(
        min_length=1
    )
    regulatory_rationale: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_case(self) -> Self:
        for values, label in (
            (self.expected_relevant_evidence_ids, "Expected evidence IDs"),
            (self.observed_ranked_evidence_ids, "Observed evidence IDs"),
        ):
            if len(values) != len(set(values)):
                raise ValueError(f"{label} must be unique")
            if any(not value.strip() for value in values):
                raise ValueError(f"{label} cannot be blank")
        branches = tuple(item.branch for item in self.branch_observations)
        if len(branches) != len(set(branches)):
            raise ValueError("Evaluation branch observations must be unique")
        if self.expected_no_match == bool(self.expected_relevant_evidence_ids):
            raise ValueError(
                "A case requires relevant evidence or expected no-match"
            )
        return self


class RetrievalEvaluationThreshold(EvaluationModel):
    intent: Intent
    minimum_precision_at_k: float = Field(ge=0, le=1)
    minimum_recall_at_k: float = Field(ge=0, le=1)
    minimum_case_coverage: float = Field(ge=0, le=1)
    minimum_branch_health_rate: float = Field(ge=0, le=1)
    maximum_p95_latency_ms: int = Field(ge=0)


class RetrievalEvaluationApproval(EvaluationModel):
    reviewer_id: str = Field(min_length=1)
    reviewer_role: str = Field(min_length=1)
    approved_at: datetime
    approval_reference: str = Field(min_length=1)
    payload_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @field_validator("reviewer_id", "reviewer_role", "approval_reference")
    @classmethod
    def reject_placeholder(cls, value: str) -> str:
        normalized = value.strip()
        lowered = normalized.casefold()
        if not normalized or any(
            marker in lowered
            for marker in ("placeholder", "pending", "todo", "tbd", "unknown")
        ):
            raise ValueError("Evaluation approval cannot use placeholders")
        return normalized

    @field_validator("approved_at")
    @classmethod
    def require_aware_time(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Evaluation approval time must be timezone-aware")
        return value


class RetrievalEvaluationDataset(EvaluationModel):
    schema_version: Literal["1"] = RETRIEVAL_EVALUATION_SCHEMA_VERSION
    policy_version: Literal[
        "ask-ai-retrieval-evaluation-v1"
    ] = RETRIEVAL_EVALUATION_POLICY_VERSION
    review_status: EvaluationReviewStatus
    precision_recall_k: int = Field(default=5, ge=1, le=100)
    cases: tuple[RetrievalEvaluationCase, ...] = Field(min_length=1)
    thresholds: tuple[RetrievalEvaluationThreshold, ...] = Field(min_length=1)
    approval: RetrievalEvaluationApproval | None = None

    @model_validator(mode="after")
    def validate_dataset(self) -> Self:
        case_ids = tuple(case.case_id for case in self.cases)
        if len(case_ids) != len(set(case_ids)):
            raise ValueError("Retrieval evaluation case IDs must be unique")
        threshold_intents = tuple(item.intent for item in self.thresholds)
        if len(threshold_intents) != len(set(threshold_intents)):
            raise ValueError("Retrieval evaluation threshold intents must be unique")
        if {case.intent for case in self.cases} != set(threshold_intents):
            raise ValueError("Thresholds must exactly cover evaluated intents")
        approved = self.review_status is EvaluationReviewStatus.APPROVED
        if approved != (self.approval is not None):
            raise ValueError("Only approved datasets carry approval provenance")
        if (
            self.approval is not None
            and self.approval.payload_sha256
            != retrieval_evaluation_payload_sha256(
                precision_recall_k=self.precision_recall_k,
                cases=self.cases,
                thresholds=self.thresholds,
            )
        ):
            raise ValueError("Approved retrieval evaluation checksum does not match")
        return self


class RetrievalIntentMetrics(EvaluationModel):
    intent: Intent
    case_count: int = Field(ge=1)
    precision_at_k: float = Field(ge=0, le=1)
    recall_at_k: float = Field(ge=0, le=1)
    case_coverage: float = Field(ge=0, le=1)
    branch_health_rate: float = Field(ge=0, le=1)
    p95_latency_ms: int = Field(ge=0)
    threshold_passed: bool


class RetrievalEvaluationReport(EvaluationModel):
    schema_version: Literal["1"] = RETRIEVAL_EVALUATION_SCHEMA_VERSION
    policy_version: Literal[
        "ask-ai-retrieval-evaluation-v1"
    ] = RETRIEVAL_EVALUATION_POLICY_VERSION
    dataset_payload_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    review_status: EvaluationReviewStatus
    verdict: EvaluationVerdict
    precision_recall_k: int = Field(ge=1, le=100)
    per_intent: tuple[RetrievalIntentMetrics, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_verdict(self) -> Self:
        if self.review_status is EvaluationReviewStatus.DRAFT:
            if self.verdict is not EvaluationVerdict.UNAPPROVED:
                raise ValueError("Draft evaluation must remain unapproved")
        else:
            passed = all(item.threshold_passed for item in self.per_intent)
            if (self.verdict is EvaluationVerdict.PASS) != passed:
                raise ValueError("Approved evaluation verdict disagrees with metrics")
        return self


def evaluate_retrieval(
    dataset: RetrievalEvaluationDataset,
) -> RetrievalEvaluationReport:
    safe_dataset = RetrievalEvaluationDataset.model_validate(
        dataset.model_dump(mode="python")
    )
    thresholds = {item.intent: item for item in safe_dataset.thresholds}
    metrics = tuple(
        _intent_metrics(
            intent,
            tuple(case for case in safe_dataset.cases if case.intent is intent),
            thresholds[intent],
            safe_dataset.precision_recall_k,
        )
        for intent in sorted(thresholds, key=lambda item: item.value)
    )
    verdict = (
        EvaluationVerdict.UNAPPROVED
        if safe_dataset.review_status is EvaluationReviewStatus.DRAFT
        else (
            EvaluationVerdict.PASS
            if all(item.threshold_passed for item in metrics)
            else EvaluationVerdict.FAIL
        )
    )
    return RetrievalEvaluationReport(
        dataset_payload_sha256=retrieval_evaluation_payload_sha256(
            precision_recall_k=safe_dataset.precision_recall_k,
            cases=safe_dataset.cases,
            thresholds=safe_dataset.thresholds,
        ),
        review_status=safe_dataset.review_status,
        verdict=verdict,
        precision_recall_k=safe_dataset.precision_recall_k,
        per_intent=metrics,
    )


def retrieval_evaluation_payload_sha256(
    *,
    precision_recall_k: int,
    cases: tuple[RetrievalEvaluationCase, ...],
    thresholds: tuple[RetrievalEvaluationThreshold, ...],
) -> str:
    payload = json.dumps(
        {
            "cases": [case.model_dump(mode="json") for case in cases],
            "policy_version": RETRIEVAL_EVALUATION_POLICY_VERSION,
            "precision_recall_k": precision_recall_k,
            "schema_version": RETRIEVAL_EVALUATION_SCHEMA_VERSION,
            "thresholds": [
                threshold.model_dump(mode="json") for threshold in thresholds
            ],
        },
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def retrieval_evaluation_report_json(
    report: RetrievalEvaluationReport,
) -> str:
    return json.dumps(
        report.model_dump(mode="json"),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def _intent_metrics(
    intent: Intent,
    cases: tuple[RetrievalEvaluationCase, ...],
    threshold: RetrievalEvaluationThreshold,
    k: int,
) -> RetrievalIntentMetrics:
    precisions: list[float] = []
    recalls: list[float] = []
    covered = 0
    healthy = 0
    branches = 0
    latencies: list[int] = []
    for case in cases:
        expected = set(case.expected_relevant_evidence_ids)
        observed = case.observed_ranked_evidence_ids[:k]
        true_positives = len(expected & set(observed))
        if case.expected_no_match:
            no_match_correct = not observed
            precisions.append(float(no_match_correct))
            recalls.append(float(no_match_correct))
            covered += int(no_match_correct)
        else:
            precisions.append(true_positives / k)
            recalls.append(true_positives / len(expected))
            covered += int(true_positives > 0)
        latencies.append(case.end_to_end_latency_ms)
        for branch in case.branch_observations:
            if branch.status is RetrievalBranchStatus.SKIPPED:
                continue
            branches += 1
            healthy += int(branch.health is RetrievalBranchHealth.HEALTHY)
    precision = sum(precisions) / len(cases)
    recall = sum(recalls) / len(cases)
    coverage = covered / len(cases)
    health_rate = healthy / branches if branches else 0.0
    p95_latency = _nearest_rank_percentile(latencies, 0.95)
    passed = (
        precision >= threshold.minimum_precision_at_k
        and recall >= threshold.minimum_recall_at_k
        and coverage >= threshold.minimum_case_coverage
        and health_rate >= threshold.minimum_branch_health_rate
        and p95_latency <= threshold.maximum_p95_latency_ms
    )
    return RetrievalIntentMetrics(
        intent=intent,
        case_count=len(cases),
        precision_at_k=precision,
        recall_at_k=recall,
        case_coverage=coverage,
        branch_health_rate=health_rate,
        p95_latency_ms=p95_latency,
        threshold_passed=passed,
    )


def _nearest_rank_percentile(values: list[int], percentile: float) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    index = max(0, math.ceil(percentile * len(ordered)) - 1)
    return ordered[index]
