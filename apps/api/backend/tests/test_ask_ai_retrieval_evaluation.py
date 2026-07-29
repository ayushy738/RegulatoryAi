from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from pydantic import ValidationError

from backend.rag.evaluation import (
    BranchEvaluationObservation,
    EvaluationReviewStatus,
    EvaluationVerdict,
    RetrievalEvaluationCase,
    RetrievalEvaluationDataset,
    RetrievalEvaluationThreshold,
    evaluate_retrieval,
    retrieval_evaluation_payload_sha256,
    retrieval_evaluation_report_json,
)


def _case(
    *,
    case_id: str = "synthetic-obligation",
    intent: str = "compliance_question",
) -> RetrievalEvaluationCase:
    return RetrievalEvaluationCase(
        case_id=case_id,
        query="Synthetic regulatory query",
        intent=intent,
        expected_relevant_evidence_ids=("evidence-1", "evidence-2"),
        expected_no_match=False,
        observed_ranked_evidence_ids=("evidence-1", "noise"),
        end_to_end_latency_ms=50,
        branch_observations=(
            BranchEvaluationObservation(
                branch="vector",
                status="satisfied",
                health="healthy",
                latency_ms=10,
            ),
            BranchEvaluationObservation(
                branch="graph",
                status="unavailable",
                health="failed",
                latency_ms=50,
            ),
            BranchEvaluationObservation(
                branch="summary",
                status="skipped",
                health="not_run",
                latency_ms=0,
            ),
        ),
        regulatory_rationale="Synthetic test-only relevance judgment.",
    )


def _threshold(
    *,
    intent: str = "compliance_question",
    minimum_precision: float = 0.5,
) -> RetrievalEvaluationThreshold:
    return RetrievalEvaluationThreshold(
        intent=intent,
        minimum_precision_at_k=minimum_precision,
        minimum_recall_at_k=0.5,
        minimum_case_coverage=1.0,
        minimum_branch_health_rate=0.5,
        maximum_p95_latency_ms=50,
    )


def _payload(
    *,
    review_status: EvaluationReviewStatus = EvaluationReviewStatus.DRAFT,
    threshold: RetrievalEvaluationThreshold | None = None,
) -> dict[str, Any]:
    cases = (_case(),)
    thresholds = (threshold or _threshold(),)
    payload: dict[str, Any] = {
        "review_status": review_status.value,
        "precision_recall_k": 2,
        "cases": [case.model_dump(mode="json") for case in cases],
        "thresholds": [
            item.model_dump(mode="json") for item in thresholds
        ],
    }
    if review_status is EvaluationReviewStatus.APPROVED:
        payload["approval"] = {
            "reviewer_id": "synthetic-reviewer",
            "reviewer_role": "synthetic-regulatory-role",
            "approved_at": datetime(2026, 7, 27, tzinfo=UTC).isoformat(),
            "approval_reference": "synthetic-test-approval",
            "payload_sha256": retrieval_evaluation_payload_sha256(
                precision_recall_k=2,
                cases=cases,
                thresholds=thresholds,
            ),
        }
    return payload


def test_draft_metrics_are_exact_but_can_never_receive_pass_verdict() -> None:
    dataset = RetrievalEvaluationDataset.model_validate(_payload())

    report = evaluate_retrieval(dataset)

    assert report.verdict is EvaluationVerdict.UNAPPROVED
    metrics = report.per_intent[0]
    assert metrics.precision_at_k == 0.5
    assert metrics.recall_at_k == 0.5
    assert metrics.case_coverage == 1.0
    assert metrics.branch_health_rate == 0.5
    assert metrics.p95_latency_ms == 50
    assert metrics.threshold_passed is True


def test_expected_healthy_no_match_scores_exactly_without_fake_gold_ids() -> None:
    no_match_case = _case(case_id="synthetic-no-match").model_copy(
        update={
            "expected_relevant_evidence_ids": (),
            "expected_no_match": True,
            "observed_ranked_evidence_ids": (),
        }
    )
    threshold = _threshold()
    dataset = RetrievalEvaluationDataset(
        review_status=EvaluationReviewStatus.DRAFT,
        precision_recall_k=2,
        cases=(no_match_case,),
        thresholds=(threshold,),
    )

    metrics = evaluate_retrieval(dataset).per_intent[0]

    assert metrics.precision_at_k == 1.0
    assert metrics.recall_at_k == 1.0
    assert metrics.case_coverage == 1.0


def test_approved_dataset_produces_pass_or_fail_from_exact_thresholds() -> None:
    passing = evaluate_retrieval(
        RetrievalEvaluationDataset.model_validate(
            _payload(review_status=EvaluationReviewStatus.APPROVED)
        )
    )
    failing = evaluate_retrieval(
        RetrievalEvaluationDataset.model_validate(
            _payload(
                review_status=EvaluationReviewStatus.APPROVED,
                threshold=_threshold(minimum_precision=0.75),
            )
        )
    )

    assert passing.verdict is EvaluationVerdict.PASS
    assert failing.verdict is EvaluationVerdict.FAIL
    assert failing.per_intent[0].threshold_passed is False


def test_report_is_deterministic_and_binds_complete_dataset_payload() -> None:
    dataset = RetrievalEvaluationDataset.model_validate(_payload())
    first = evaluate_retrieval(dataset)
    second = evaluate_retrieval(dataset)
    serialized = retrieval_evaluation_report_json(first)

    assert first == second
    assert serialized == retrieval_evaluation_report_json(
        type(first).model_validate_json(serialized)
    )
    assert first.dataset_payload_sha256 == (
        retrieval_evaluation_payload_sha256(
            precision_recall_k=dataset.precision_recall_k,
            cases=dataset.cases,
            thresholds=dataset.thresholds,
        )
    )


def test_approved_checksum_rejects_label_observation_or_threshold_tampering() -> None:
    payload = _payload(review_status=EvaluationReviewStatus.APPROVED)
    payload["cases"][0]["observed_ranked_evidence_ids"] = ["noise"]

    with pytest.raises(ValidationError, match="checksum"):
        RetrievalEvaluationDataset.model_validate(payload)

    payload = _payload(review_status=EvaluationReviewStatus.APPROVED)
    payload["thresholds"][0]["minimum_recall_at_k"] = 0.75
    with pytest.raises(ValidationError, match="checksum"):
        RetrievalEvaluationDataset.model_validate(payload)


def test_draft_cannot_claim_approval_and_approved_cannot_omit_it() -> None:
    draft = _payload()
    draft["approval"] = _payload(
        review_status=EvaluationReviewStatus.APPROVED
    )["approval"]
    with pytest.raises(ValidationError, match="Only approved"):
        RetrievalEvaluationDataset.model_validate(draft)

    approved = _payload(review_status=EvaluationReviewStatus.APPROVED)
    approved.pop("approval")
    with pytest.raises(ValidationError, match="Only approved"):
        RetrievalEvaluationDataset.model_validate(approved)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("reviewer_id", "TODO"),
        ("reviewer_role", "pending"),
        ("approval_reference", "placeholder"),
    ],
)
def test_approval_provenance_rejects_placeholders(
    field: str,
    value: str,
) -> None:
    payload = _payload(review_status=EvaluationReviewStatus.APPROVED)
    payload["approval"][field] = value

    with pytest.raises(ValidationError, match="placeholders"):
        RetrievalEvaluationDataset.model_validate(payload)


def test_branch_status_health_mismatch_is_rejected() -> None:
    with pytest.raises(ValidationError, match="disagree"):
        BranchEvaluationObservation(
            branch="vector",
            status="satisfied",
            health="failed",
            latency_ms=1,
        )


def test_case_and_threshold_identity_must_be_unique_and_exact() -> None:
    payload = _payload()
    payload["cases"].append(payload["cases"][0])
    with pytest.raises(ValidationError, match="case IDs"):
        RetrievalEvaluationDataset.model_validate(payload)

    payload = _payload()
    payload["thresholds"][0]["intent"] = "deadline"
    with pytest.raises(ValidationError, match="exactly cover"):
        RetrievalEvaluationDataset.model_validate(payload)


def test_contracts_reject_unknown_fields_naive_time_and_mutation() -> None:
    payload = _payload()
    payload["unknown"] = True
    with pytest.raises(ValidationError):
        RetrievalEvaluationDataset.model_validate(payload)

    payload = _payload(review_status=EvaluationReviewStatus.APPROVED)
    payload["approval"]["approved_at"] = "2026-07-27T00:00:00"
    with pytest.raises(ValidationError, match="timezone-aware"):
        RetrievalEvaluationDataset.model_validate(payload)

    dataset = RetrievalEvaluationDataset.model_validate(_payload())
    with pytest.raises(ValidationError):
        dataset.precision_recall_k = 1  # type: ignore[misc]
