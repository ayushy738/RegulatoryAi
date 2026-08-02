from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from backend.ask.decision import (
    DECISION_CALIBRATION_POLICY_VERSION,
    DECISION_CALIBRATION_SCHEMA_VERSION,
    DECISION_POLICY_VERSION,
    DecisionCalibrationCase,
    DecisionCalibrationDataset,
    DecisionCalibrationThresholds,
    calibration_payload_sha256,
    load_decision_calibration_dataset,
)
from backend.ask.decision.calibration_evaluation import (
    evaluate_decision_calibration,
    render_decision_calibration_report,
)

SYNTHETIC_APPROVAL_TIME = datetime(2026, 7, 27, 12, tzinfo=UTC)


def _synthetic_case(
    *,
    case_id: str = "synthetic-contract-case",
) -> dict[str, Any]:
    return {
        "case_id": case_id,
        "query": "When is the synthetic compliance deadline?",
        "source_kind": "synthetic",
        "source_template_id": "synthetic-contract-template",
        "evaluation_tags": ["high_risk", "temporal"],
        "holdout": True,
        "intent_signals": {
            "explicit_compliance": True,
            "explicit_deadline": True,
        },
        "intent_score": 0.90,
        "intent_competing_gap": 0.10,
        "intent_material_collision": False,
        "intent_shared_safe_scope": True,
        "entity_requests": [],
        "time_expression": "2026-07-31",
        "time_intent": "compliance_question",
        "plan_request": {
            "questions": [
                {
                    "question_id": "q1",
                    "intent": "compliance_question",
                    "secondary_intents": ["deadline"],
                }
            ]
        },
        "expected_primary_intent": "compliance_question",
        "expected_secondary_intents": ["deadline"],
        "expected_response_strategy": "compliance_checklist",
        "expected_intent_confidence_band": "certain",
        "expected_entity_canonical_ids": ["synthetic-regulation"],
        "expected_entity_min_confidence": 0.85,
        "expected_time_dimension": "publication_or_issue",
        "expected_plan_class": "focused_grounded",
        "clarification_required": False,
        "regulatory_rationale": "Synthetic test-only rationale.",
    }


def _synthetic_dataset_payload(
    *,
    cases: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    case_payloads = cases or [_synthetic_case()]
    typed_cases = tuple(
        DecisionCalibrationCase.model_validate(case) for case in case_payloads
    )
    thresholds = DecisionCalibrationThresholds(
        intent_certain_min=0.90,
        intent_certain_competing_gap_min=0.10,
        intent_strong_min=0.75,
        intent_bounded_min=0.55,
        entity_high_risk_min=0.85,
    )
    return {
        "schema_version": DECISION_CALIBRATION_SCHEMA_VERSION,
        "calibration_policy_version": DECISION_CALIBRATION_POLICY_VERSION,
        "decision_policy_version": DECISION_POLICY_VERSION,
        "dataset_kind": "contract_test",
        "dataset_version": "0.0.1",
        "entity_registry_version": "synthetic-catalog-v1",
        "fixed_clock": SYNTHETIC_APPROVAL_TIME.isoformat(),
        "thresholds": thresholds.model_dump(mode="json"),
        "approval": {
            "status": "approved",
            "reviewer_id": "synthetic-reviewer",
            "reviewer_role": "synthetic-regulatory-reviewer",
            "technical_reviewer_id": "synthetic-technical-reviewer",
            "technical_reviewer_role": "synthetic-principal-ai-engineer",
            "creator_id": "synthetic-evaluation-creator",
            "review_method": "independent_exact_agreement",
            "approved_at": SYNTHETIC_APPROVAL_TIME.isoformat(),
            "approval_reference": "synthetic-test-approval",
            "payload_sha256": calibration_payload_sha256(
                thresholds=thresholds,
                cases=typed_cases,
            ),
        },
        "cases": case_payloads,
    }


def test_synthetic_approved_dataset_round_trips_deterministically(
    tmp_path: Path,
) -> None:
    payload = _synthetic_dataset_payload()
    dataset = DecisionCalibrationDataset.model_validate(payload)
    artifact_path = tmp_path / "synthetic-calibration.json"
    artifact_path.write_text(
        json.dumps(dataset.model_dump(mode="json"), sort_keys=True),
        encoding="utf-8",
    )

    loaded = load_decision_calibration_dataset(artifact_path)

    assert loaded == dataset
    assert (
        calibration_payload_sha256(
            thresholds=loaded.thresholds,
            cases=loaded.cases,
        )
        == loaded.approval.payload_sha256
    )
    assert loaded.model_dump_json() == dataset.model_dump_json()


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("reviewer_id", "TODO"),
        ("reviewer_role", "placeholder"),
        ("approval_reference", "pending"),
    ],
)
def test_approval_provenance_rejects_placeholders(
    field: str,
    value: str,
) -> None:
    payload = _synthetic_dataset_payload()
    payload["approval"][field] = value

    with pytest.raises(ValidationError, match="placeholder"):
        DecisionCalibrationDataset.model_validate(payload)


def test_approval_requires_timezone_aware_timestamp() -> None:
    payload = _synthetic_dataset_payload()
    payload["approval"]["approved_at"] = "2026-07-27T12:00:00"

    with pytest.raises(ValidationError, match="timezone-aware"):
        DecisionCalibrationDataset.model_validate(payload)


def test_checksum_rejects_a_tampered_approved_case() -> None:
    payload = _synthetic_dataset_payload()
    payload["cases"][0]["clarification_required"] = True

    with pytest.raises(ValidationError, match="checksum"):
        DecisionCalibrationDataset.model_validate(payload)


def test_duplicate_case_ids_are_rejected_before_approval() -> None:
    duplicate_cases = [_synthetic_case(), _synthetic_case()]
    payload = _synthetic_dataset_payload(cases=duplicate_cases)

    with pytest.raises(ValidationError, match="case IDs"):
        DecisionCalibrationDataset.model_validate(payload)


def test_dataset_rejects_a_different_decision_policy_version() -> None:
    payload = _synthetic_dataset_payload()
    payload["decision_policy_version"] = "ask-ai-decision-v2"

    with pytest.raises(ValidationError):
        DecisionCalibrationDataset.model_validate(payload)


def test_dataset_and_nested_contracts_reject_unknown_fields() -> None:
    payload = _synthetic_dataset_payload()
    payload["cases"][0]["unreviewed_note"] = "must not be ignored"
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        DecisionCalibrationDataset.model_validate(payload)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("intent_certain_min", 0.75),
        ("intent_strong_min", 0.55),
        ("intent_bounded_min", 0.90),
    ],
)
def test_intent_thresholds_must_be_strictly_ordered(
    field: str,
    value: float,
) -> None:
    payload = _synthetic_dataset_payload()
    payload["thresholds"][field] = value

    with pytest.raises(ValidationError, match="strictly ordered"):
        DecisionCalibrationDataset.model_validate(payload)


def test_checksum_rejects_tampered_approved_thresholds() -> None:
    payload = _synthetic_dataset_payload()
    payload["thresholds"]["entity_high_risk_min"] = 0.90

    with pytest.raises(ValidationError, match="checksum"):
        DecisionCalibrationDataset.model_validate(payload)


def test_calibration_requires_at_least_one_reviewed_case() -> None:
    payload = _synthetic_dataset_payload()
    payload["cases"] = []

    with pytest.raises(ValidationError):
        DecisionCalibrationDataset.model_validate(payload)


def test_production_dataset_enforces_approved_minimum_size() -> None:
    cases = [
        _synthetic_case(case_id=f"synthetic-contract-case-{index:03d}")
        for index in range(599)
    ]
    payload = _synthetic_dataset_payload(cases=cases)
    payload["dataset_kind"] = "production_golden"

    with pytest.raises(ValidationError, match="requires 600 cases"):
        DecisionCalibrationDataset.model_validate(payload)


def test_creator_and_reviewers_must_be_distinct() -> None:
    payload = _synthetic_dataset_payload()
    payload["approval"]["creator_id"] = payload["approval"]["reviewer_id"]

    with pytest.raises(ValidationError, match="distinct identities"):
        DecisionCalibrationDataset.model_validate(payload)


def test_evaluator_scores_real_policy_modules_and_renders_bounded_report() -> None:
    dataset = DecisionCalibrationDataset.model_validate(
        _synthetic_dataset_payload()
    )

    report = evaluate_decision_calibration(
        dataset,
        entity_catalog=(),
        entity_registry_sha256="0" * 64,
        code_revision="test-revision",
        environment="unit-test",
    )

    assert report.acceptance_passed is True
    assert report.overall.primary_intent_accuracy == 1
    assert report.holdout.case_count == 1
    markdown = render_decision_calibration_report(report)
    assert "**Result:** PASS" in markdown
    assert dataset.cases[0].query not in markdown


def test_evaluator_fails_a_checksum_valid_but_incorrect_gold_label() -> None:
    payload = _synthetic_dataset_payload()
    payload["cases"][0]["expected_primary_intent"] = "stakeholder"
    typed_case = DecisionCalibrationCase.model_validate(payload["cases"][0])
    thresholds = DecisionCalibrationThresholds.model_validate(
        payload["thresholds"]
    )
    payload["approval"]["payload_sha256"] = calibration_payload_sha256(
        thresholds=thresholds,
        cases=(typed_case,),
    )
    dataset = DecisionCalibrationDataset.model_validate(payload)

    report = evaluate_decision_calibration(
        dataset,
        entity_catalog=(),
        entity_registry_sha256="0" * 64,
        code_revision="test-revision",
        environment="unit-test",
    )

    assert report.acceptance_passed is False
    assert report.overall.primary_intent_accuracy == 0
