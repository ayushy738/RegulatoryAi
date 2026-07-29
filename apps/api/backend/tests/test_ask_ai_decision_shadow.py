from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

import pytest

from backend.ask.decision.models import Intent, ResponseStrategy
from backend.ask.decision.shadow import (
    SHADOW_DECISION_POLICY_VERSION,
    SHADOW_DECISION_UNAVAILABLE,
    DecisionShadowService,
    DeterministicShadowDecisionEvaluator,
    LoggingShadowComparisonRecorder,
    ShadowComparisonOutcome,
)

NOW = datetime(2026, 7, 27, 12, tzinfo=UTC)


@pytest.mark.parametrize(
    ("query", "expected_intent", "expected_strategy"),
    [
        (
            "Compliance deadline for DSM",
            Intent.COMPLIANCE_QUESTION,
            ResponseStrategy.COMPLIANCE_CHECKLIST,
        ),
        ("Timeline of DSM", Intent.TIMELINE, ResponseStrategy.TIMELINE),
        ("What is DSM", Intent.DEFINITION, ResponseStrategy.DEFINITION_CARD),
        (
            "Latest DSM amendment",
            Intent.AMENDMENT,
            ResponseStrategy.AMENDMENT_CARDS,
        ),
        (
            "Summarize DSM",
            Intent.SUMMARIZATION,
            ResponseStrategy.EXECUTIVE_SUMMARY,
        ),
        (
            "DSM",
            Intent.ENTITY_LOOKUP,
            ResponseStrategy.ENTITY_INTELLIGENCE_PAGE,
        ),
    ],
)
def test_deterministic_shadow_adapter_builds_existing_decision_contract(
    query: str,
    expected_intent: Intent,
    expected_strategy: ResponseStrategy,
) -> None:
    evaluator = DeterministicShadowDecisionEvaluator()

    first = evaluator.evaluate(query=query, now=NOW, user_timezone="UTC")
    second = evaluator.evaluate(query=query, now=NOW, user_timezone="UTC")

    assert first == second
    assert first.intent.primary is expected_intent
    assert first.response_strategy is expected_strategy
    assert first.policy_version == "ask-ai-decision-v1"
    assert first.atomic_questions
    assert first.request.query == query
    assert first.time_interpretation.user_timezone == "UTC"
    assert len(first.capabilities) == 9


def test_shadow_service_records_agreement_and_precedence_disagreement() -> None:
    comparisons: list[Any] = []
    recorder = type(
        "Recorder",
        (),
        {"record": lambda self, comparison: comparisons.append(comparison)},
    )()
    service = DecisionShadowService(
        recorder=recorder,
        clock=lambda: NOW,
        monotonic=iter((1.0, 1.005, 2.0, 2.009)).__next__,
    )

    agreement = service.evaluate_and_record(
        query="Latest DSM amendment",
        legacy_intent="amendment",
    )
    disagreement = service.evaluate_and_record(
        query="Compliance deadline for DSM",
        legacy_intent="deadline",
    )

    assert agreement.comparison.outcome is ShadowComparisonOutcome.AGREEMENT
    assert agreement.comparison.duration_ms == 4
    assert disagreement.comparison.outcome is ShadowComparisonOutcome.DISAGREEMENT
    assert disagreement.comparison.legacy_canonical_intent is Intent.DEADLINE
    assert disagreement.comparison.shadow_intent is Intent.COMPLIANCE_QUESTION
    assert comparisons == [agreement.comparison, disagreement.comparison]


def test_shadow_failure_and_recorder_failure_are_safe_and_content_free() -> None:
    class RaisingEvaluator:
        def evaluate(self, **_: Any) -> Any:
            raise RuntimeError("raw provider detail")

    class RaisingRecorder:
        def record(self, _: Any) -> None:
            raise RuntimeError("sink unavailable")

    execution = DecisionShadowService(
        evaluator=RaisingEvaluator(),
        recorder=RaisingRecorder(),
        clock=lambda: NOW,
        monotonic=iter((1.0, 1.001)).__next__,
    ).evaluate_and_record(
        query="Secret compliance question",
        legacy_intent="obligation",
    )

    assert execution.decision_record is None
    assert execution.comparison.outcome is ShadowComparisonOutcome.UNAVAILABLE
    assert execution.comparison.safe_error_code == SHADOW_DECISION_UNAVAILABLE
    serialized = execution.comparison.model_dump_json()
    assert "Secret compliance question" not in serialized
    assert "raw provider detail" not in serialized


def test_logging_recorder_emits_only_declared_safe_comparison_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[tuple[str, dict[str, Any]]] = []
    monkeypatch.setattr(
        "backend.ask.decision.shadow.log_event",
        lambda event, **fields: events.append((event, fields)),
    )
    execution = DecisionShadowService(
        clock=lambda: NOW,
        monotonic=iter((1.0, 1.002)).__next__,
    ).evaluate_and_record(
        query="Compliance deadline with confidential details",
        legacy_intent="deadline",
    )

    LoggingShadowComparisonRecorder(correlation_id="correlation-1").record(
        execution.comparison
    )

    assert events[0][0] == "ask_decision_shadow"
    assert set(events[0][1]) == {
        "correlation_id",
        "schema_version",
        "policy_version",
        "decision_policy_version",
        "outcome",
        "legacy_intent",
        "legacy_canonical_intent",
        "shadow_intent",
        "shadow_response_strategy",
        "duration_ms",
        "safe_error_code",
    }
    assert events[0][1]["policy_version"] == SHADOW_DECISION_POLICY_VERSION
    serialized = json.dumps(events)
    assert "confidential details" not in serialized
