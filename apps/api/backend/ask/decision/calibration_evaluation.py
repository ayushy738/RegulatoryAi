from __future__ import annotations

import hashlib
import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from typing import Literal

from pydantic import Field

from backend.ask.decision.calibration import (
    CalibrationTag,
    DecisionCalibrationCase,
    DecisionCalibrationDataset,
)
from backend.ask.decision.entity_policy import (
    EntityCatalogEntry,
    EntityResolutionStatus,
    resolve_entity,
)
from backend.ask.decision.models import (
    DecisionModel,
    Intent,
    IntentConfidenceBand,
    ResponseStrategy,
    TimeDimension,
)
from backend.ask.decision.plan_policy import PlanClass, select_decision_plan
from backend.ask.decision.policy import (
    classify_intent_confidence,
    select_intent,
)
from backend.ask.decision.time_policy import normalize_time

DECISION_CALIBRATION_REPORT_VERSION = "ask-ai-decision-calibration-report-v1"
HIGH_RISK_INTENTS = frozenset(
    {
        Intent.COMPLIANCE_QUESTION,
        Intent.DEADLINE,
        Intent.AMENDMENT,
        Intent.CONSULTATION,
        Intent.COMPARISON,
        Intent.REGULATION_LOOKUP,
    }
)


class DecisionCalibrationPrediction(DecisionModel):
    case_id: str
    primary_intent: Intent
    secondary_intents: tuple[Intent, ...]
    response_strategy: ResponseStrategy
    intent_confidence_band: IntentConfidenceBand
    entity_canonical_ids: tuple[str, ...]
    entity_min_confidence: float | None = Field(default=None, ge=0, le=1)
    time_dimension: TimeDimension | None
    plan_class: PlanClass
    clarification_required: bool
    wrong_jurisdiction_selection: bool
    entity_confidence_gate_violation: bool


class DecisionCalibrationMetrics(DecisionModel):
    case_count: int = Field(ge=0)
    primary_intent_accuracy: float = Field(ge=0, le=1)
    high_risk_primary_intent_accuracy: float = Field(ge=0, le=1)
    high_risk_intent_precision: float = Field(ge=0, le=1)
    high_risk_intent_recall: float = Field(ge=0, le=1)
    secondary_intent_micro_f1: float = Field(ge=0, le=1)
    response_strategy_accuracy: float = Field(ge=0, le=1)
    plan_class_accuracy: float = Field(ge=0, le=1)
    intent_confidence_band_accuracy: float = Field(ge=0, le=1)
    entity_exact_set_accuracy: float = Field(ge=0, le=1)
    high_risk_entity_exact_set_accuracy: float = Field(ge=0, le=1)
    wrong_jurisdiction_high_risk_count: int = Field(ge=0)
    entity_confidence_gate_violation_count: int = Field(ge=0)
    time_dimension_accuracy: float = Field(ge=0, le=1)
    clarification_precision: float = Field(ge=0, le=1)
    clarification_recall: float = Field(ge=0, le=1)
    unsafe_direct_answer_count: int = Field(ge=0)
    deterministic_repeat_agreement: float = Field(ge=0, le=1)
    per_intent_accuracy: dict[str, float]


class DecisionCalibrationReport(DecisionModel):
    report_version: Literal[
        "ask-ai-decision-calibration-report-v1"
    ] = DECISION_CALIBRATION_REPORT_VERSION
    generated_at: datetime
    code_revision: str = Field(min_length=1)
    dataset_version: str
    dataset_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    entity_registry_version: str
    entity_registry_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    calibration_policy_version: str
    decision_policy_version: str
    rule_version: str
    fixed_clock: datetime
    environment: str = Field(min_length=1)
    duration_ms: int = Field(ge=0)
    overall: DecisionCalibrationMetrics
    holdout: DecisionCalibrationMetrics
    acceptance_passed: bool


def load_entity_catalog(path: str | Path) -> tuple[EntityCatalogEntry, ...]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return tuple(
        EntityCatalogEntry.model_validate(row) for row in payload["entities"]
    )


def file_sha256(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def render_decision_calibration_report(
    report: DecisionCalibrationReport,
) -> str:
    status = "PASS" if report.acceptance_passed else "FAIL"
    overall = report.overall
    holdout = report.holdout
    rows = (
        (
            "Primary intent accuracy",
            overall.primary_intent_accuracy,
            holdout.primary_intent_accuracy,
        ),
        (
            "High-risk primary intent accuracy",
            overall.high_risk_primary_intent_accuracy,
            holdout.high_risk_primary_intent_accuracy,
        ),
        (
            "High-risk intent precision",
            overall.high_risk_intent_precision,
            holdout.high_risk_intent_precision,
        ),
        (
            "High-risk intent recall",
            overall.high_risk_intent_recall,
            holdout.high_risk_intent_recall,
        ),
        (
            "Secondary-intent micro F1",
            overall.secondary_intent_micro_f1,
            holdout.secondary_intent_micro_f1,
        ),
        (
            "Response-strategy accuracy",
            overall.response_strategy_accuracy,
            holdout.response_strategy_accuracy,
        ),
        (
            "Plan-class accuracy",
            overall.plan_class_accuracy,
            holdout.plan_class_accuracy,
        ),
        (
            "Confidence-band accuracy",
            overall.intent_confidence_band_accuracy,
            holdout.intent_confidence_band_accuracy,
        ),
        (
            "Entity exact-set accuracy",
            overall.entity_exact_set_accuracy,
            holdout.entity_exact_set_accuracy,
        ),
        (
            "High-risk entity exact-set accuracy",
            overall.high_risk_entity_exact_set_accuracy,
            holdout.high_risk_entity_exact_set_accuracy,
        ),
        (
            "Time-dimension accuracy",
            overall.time_dimension_accuracy,
            holdout.time_dimension_accuracy,
        ),
        (
            "Clarification precision",
            overall.clarification_precision,
            holdout.clarification_precision,
        ),
        (
            "Clarification recall",
            overall.clarification_recall,
            holdout.clarification_recall,
        ),
        (
            "Deterministic repeat agreement",
            overall.deterministic_repeat_agreement,
            holdout.deterministic_repeat_agreement,
        ),
    )
    metric_rows = tuple(
        f"| {label} | {full:.4f} | {held:.4f} |"
        for label, full, held in rows
    )
    per_intent_rows = tuple(
        f"| `{intent}` | {accuracy:.4f} |"
        for intent, accuracy in sorted(overall.per_intent_accuracy.items())
    )
    return "\n".join(
        (
            "# E3.7 Decision Engine Calibration Report",
            "",
            f"**Result:** {status}",
            f"**Dataset:** `{report.dataset_version}`",
            f"**Dataset SHA-256:** `{report.dataset_sha256}`",
            f"**Entity registry:** `{report.entity_registry_version}`",
            f"**Entity registry SHA-256:** `{report.entity_registry_sha256}`",
            f"**Decision policy:** `{report.decision_policy_version}`",
            f"**Calibration policy:** `{report.calibration_policy_version}`",
            f"**Code revision:** `{report.code_revision}`",
            f"**Fixed clock:** `{report.fixed_clock.isoformat()}`",
            f"**Environment:** `{report.environment}`",
            "",
            "## Accuracy gates",
            "",
            "| Metric | Full set | Holdout |",
            "|---|---:|---:|",
            *metric_rows,
            "",
            "## Zero-tolerance gates",
            "",
            (
                "- Wrong-jurisdiction high-risk selections: "
                f"{overall.wrong_jurisdiction_high_risk_count}"
            ),
            (
                "- Entity confidence-gate violations: "
                f"{overall.entity_confidence_gate_violation_count}"
            ),
            f"- Unsafe direct answers: {overall.unsafe_direct_answer_count}",
            "",
            "## Per-intent exact accuracy",
            "",
            "| Intent | Accuracy |",
            "|---|---:|",
            *per_intent_rows,
            "",
            (
                "The report contains bounded metrics and artifact identities "
                "only; it does not reproduce calibration queries."
            ),
            "",
        )
    )


def evaluate_decision_calibration(
    dataset: DecisionCalibrationDataset,
    *,
    entity_catalog: tuple[EntityCatalogEntry, ...],
    entity_registry_sha256: str,
    code_revision: str,
    environment: str,
) -> DecisionCalibrationReport:
    started = perf_counter()
    first = tuple(
        _predict(case, dataset=dataset, entity_catalog=entity_catalog)
        for case in dataset.cases
    )
    second = tuple(
        _predict(case, dataset=dataset, entity_catalog=entity_catalog)
        for case in dataset.cases
    )
    repeat_matches = {
        prediction.case_id: prediction == repeated
        for prediction, repeated in zip(first, second, strict=True)
    }
    overall = _score(dataset.cases, first, repeat_matches)
    holdout_pairs = tuple(
        (case, prediction)
        for case, prediction in zip(dataset.cases, first, strict=True)
        if case.holdout
    )
    holdout = _score(
        tuple(case for case, _ in holdout_pairs),
        tuple(prediction for _, prediction in holdout_pairs),
        repeat_matches,
    )
    return DecisionCalibrationReport(
        generated_at=datetime.now(UTC),
        code_revision=code_revision,
        dataset_version=dataset.dataset_version,
        dataset_sha256=dataset.approval.payload_sha256,
        entity_registry_version=dataset.entity_registry_version,
        entity_registry_sha256=entity_registry_sha256,
        calibration_policy_version=dataset.calibration_policy_version,
        decision_policy_version=dataset.decision_policy_version,
        rule_version=dataset.decision_policy_version,
        fixed_clock=dataset.fixed_clock,
        environment=environment,
        duration_ms=max(0, round((perf_counter() - started) * 1000)),
        overall=overall,
        holdout=holdout,
        acceptance_passed=_passes(overall) and _passes(holdout),
    )


def _predict(
    case: DecisionCalibrationCase,
    *,
    dataset: DecisionCalibrationDataset,
    entity_catalog: tuple[EntityCatalogEntry, ...],
) -> DecisionCalibrationPrediction:
    intent = select_intent(case.intent_signals)
    confidence_band = classify_intent_confidence(
        case.intent_score,
        competing_gap=case.intent_competing_gap,
        material_collision=case.intent_material_collision,
        shared_safe_scope=case.intent_shared_safe_scope,
    )
    plan = select_decision_plan(case.plan_request)
    time = normalize_time(
        case.time_expression,
        now=dataset.fixed_clock,
        user_timezone="Asia/Kolkata",
        intent=case.time_intent,
    )
    entity_ids: list[str] = []
    entity_confidences: list[float] = []
    wrong_jurisdiction = False
    gate_violation = False
    entity_requires_clarification = False
    for request in case.entity_requests:
        resolution = resolve_entity(request, entity_catalog)
        entity_requires_clarification = entity_requires_clarification or (
            resolution.status is EntityResolutionStatus.CLARIFICATION_REQUIRED
        )
        if resolution.selected is None:
            continue
        selected = resolution.selected
        if resolution.direct_answer_allowed:
            if selected.canonical_id is not None:
                entity_ids.append(selected.canonical_id)
            entity_confidences.append(selected.confidence)
        gate_violation = gate_violation or (
            resolution.direct_answer_allowed
            and selected.confidence < resolution.required_confidence
        )
        wrong_jurisdiction = wrong_jurisdiction or (
            resolution.direct_answer_allowed
            and request.active_jurisdiction is not None
            and selected.jurisdiction is not None
            and not _jurisdiction_compatible(
                request.active_jurisdiction,
                selected.jurisdiction,
            )
        )
    clarification = (
        confidence_band is IntentConfidenceBand.AMBIGUOUS
        or entity_requires_clarification
        or plan.clarification_question is not None
    )
    return DecisionCalibrationPrediction(
        case_id=case.case_id,
        primary_intent=intent.primary,
        secondary_intents=intent.secondary,
        response_strategy=plan.response_strategy,
        intent_confidence_band=confidence_band,
        entity_canonical_ids=tuple(dict.fromkeys(entity_ids)),
        entity_min_confidence=(
            min(entity_confidences) if entity_confidences else None
        ),
        time_dimension=time.dimension,
        plan_class=plan.plan_class,
        clarification_required=clarification,
        wrong_jurisdiction_selection=wrong_jurisdiction,
        entity_confidence_gate_violation=gate_violation,
    )


def _score(
    cases: tuple[DecisionCalibrationCase, ...],
    predictions: tuple[DecisionCalibrationPrediction, ...],
    repeat_matches: dict[str, bool],
) -> DecisionCalibrationMetrics:
    if not cases:
        raise ValueError("Calibration metric slices cannot be empty")
    pairs = tuple(zip(cases, predictions, strict=True))
    high_risk_pairs = tuple(
        pair for pair in pairs if CalibrationTag.HIGH_RISK in pair[0].evaluation_tags
    )
    entity_pairs = tuple(
        pair for pair in pairs if CalibrationTag.ENTITY in pair[0].evaluation_tags
    )
    high_risk_entity_pairs = tuple(
        pair
        for pair in entity_pairs
        if CalibrationTag.HIGH_RISK in pair[0].evaluation_tags
    )
    temporal_pairs = tuple(
        pair for pair in pairs if CalibrationTag.TEMPORAL in pair[0].evaluation_tags
    )
    secondary_tp = secondary_fp = secondary_fn = 0
    for case, prediction in pairs:
        expected = set(case.expected_secondary_intents)
        actual = set(prediction.secondary_intents)
        secondary_tp += len(expected & actual)
        secondary_fp += len(actual - expected)
        secondary_fn += len(expected - actual)
    clarification_tp = sum(
        case.clarification_required and prediction.clarification_required
        for case, prediction in pairs
    )
    clarification_fp = sum(
        not case.clarification_required and prediction.clarification_required
        for case, prediction in pairs
    )
    clarification_fn = sum(
        case.clarification_required and not prediction.clarification_required
        for case, prediction in pairs
    )
    expected_high_risk = tuple(
        case.expected_primary_intent in HIGH_RISK_INTENTS for case, _ in pairs
    )
    predicted_high_risk = tuple(
        prediction.primary_intent in HIGH_RISK_INTENTS for _, prediction in pairs
    )
    high_risk_tp = sum(
        expected and actual
        for expected, actual in zip(
            expected_high_risk,
            predicted_high_risk,
            strict=True,
        )
    )
    high_risk_fp = sum(
        not expected and actual
        for expected, actual in zip(
            expected_high_risk,
            predicted_high_risk,
            strict=True,
        )
    )
    high_risk_fn = sum(
        expected and not actual
        for expected, actual in zip(
            expected_high_risk,
            predicted_high_risk,
            strict=True,
        )
    )
    intent_totals = Counter(case.expected_primary_intent for case in cases)
    intent_correct = Counter(
        case.expected_primary_intent
        for case, prediction in pairs
        if case.expected_primary_intent is prediction.primary_intent
    )
    return DecisionCalibrationMetrics(
        case_count=len(cases),
        primary_intent_accuracy=_accuracy(
            pairs,
            lambda case, prediction: (
                case.expected_primary_intent is prediction.primary_intent
            ),
        ),
        high_risk_primary_intent_accuracy=_accuracy(
            high_risk_pairs,
            lambda case, prediction: (
                case.expected_primary_intent is prediction.primary_intent
            ),
        ),
        high_risk_intent_precision=_ratio(
            high_risk_tp,
            high_risk_tp + high_risk_fp,
        ),
        high_risk_intent_recall=_ratio(
            high_risk_tp,
            high_risk_tp + high_risk_fn,
        ),
        secondary_intent_micro_f1=_f1(
            secondary_tp,
            secondary_fp,
            secondary_fn,
        ),
        response_strategy_accuracy=_accuracy(
            pairs,
            lambda case, prediction: (
                case.expected_response_strategy is prediction.response_strategy
            ),
        ),
        plan_class_accuracy=_accuracy(
            pairs,
            lambda case, prediction: (
                case.expected_plan_class is prediction.plan_class
            ),
        ),
        intent_confidence_band_accuracy=_accuracy(
            pairs,
            lambda case, prediction: (
                case.expected_intent_confidence_band
                is prediction.intent_confidence_band
            ),
        ),
        entity_exact_set_accuracy=_accuracy(
            entity_pairs,
            lambda case, prediction: (
                set(case.expected_entity_canonical_ids)
                == set(prediction.entity_canonical_ids)
            ),
        ),
        high_risk_entity_exact_set_accuracy=_accuracy(
            high_risk_entity_pairs,
            lambda case, prediction: (
                set(case.expected_entity_canonical_ids)
                == set(prediction.entity_canonical_ids)
            ),
        ),
        wrong_jurisdiction_high_risk_count=sum(
            prediction.wrong_jurisdiction_selection
            for _, prediction in high_risk_entity_pairs
        ),
        entity_confidence_gate_violation_count=sum(
            prediction.entity_confidence_gate_violation
            for _, prediction in entity_pairs
        ),
        time_dimension_accuracy=_accuracy(
            temporal_pairs,
            lambda case, prediction: (
                case.expected_time_dimension is prediction.time_dimension
            ),
        ),
        clarification_precision=_ratio(
            clarification_tp,
            clarification_tp + clarification_fp,
        ),
        clarification_recall=_ratio(
            clarification_tp,
            clarification_tp + clarification_fn,
        ),
        unsafe_direct_answer_count=clarification_fn,
        deterministic_repeat_agreement=sum(
            repeat_matches[case.case_id] for case in cases
        )
        / len(cases),
        per_intent_accuracy={
            intent.value: intent_correct[intent] / intent_totals[intent]
            for intent in Intent
            if intent_totals[intent]
        },
    )


def _passes(metrics: DecisionCalibrationMetrics) -> bool:
    return all(
        (
            metrics.primary_intent_accuracy >= 0.96,
            metrics.high_risk_primary_intent_accuracy >= 0.98,
            metrics.high_risk_intent_precision >= 0.97,
            metrics.high_risk_intent_recall >= 0.97,
            metrics.secondary_intent_micro_f1 >= 0.92,
            metrics.response_strategy_accuracy >= 0.96,
            metrics.plan_class_accuracy >= 0.97,
            metrics.intent_confidence_band_accuracy >= 0.94,
            metrics.entity_exact_set_accuracy >= 0.98,
            metrics.high_risk_entity_exact_set_accuracy >= 0.99,
            metrics.wrong_jurisdiction_high_risk_count == 0,
            metrics.entity_confidence_gate_violation_count == 0,
            metrics.time_dimension_accuracy >= 0.97,
            metrics.clarification_precision >= 0.95,
            metrics.clarification_recall >= 0.95,
            metrics.unsafe_direct_answer_count == 0,
            metrics.deterministic_repeat_agreement == 1,
            all(value >= 0.90 for value in metrics.per_intent_accuracy.values()),
        )
    )


def _accuracy(pairs: tuple, predicate) -> float:
    if not pairs:
        return 1.0
    return sum(predicate(*pair) for pair in pairs) / len(pairs)


def _ratio(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 1.0


def _f1(true_positive: int, false_positive: int, false_negative: int) -> float:
    denominator = 2 * true_positive + false_positive + false_negative
    return (2 * true_positive) / denominator if denominator else 1.0


def _jurisdiction_compatible(active: str, selected: str) -> bool:
    left = active.casefold().strip()
    right = selected.casefold().strip()
    return left == right or left.startswith(f"{right}/") or right.startswith(
        f"{left}/"
    )
