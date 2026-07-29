from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from backend.ask.decision import (
    DECISION_POLICY_VERSION,
    DECISION_SCHEMA_VERSION,
    INTENT_PRECEDENCE,
    INTENT_RESPONSE_STRATEGY,
    INTENT_SUBTYPE_PARENTS,
    CapabilityDecision,
    CapabilityName,
    CapabilityRole,
    ConfidenceAssessment,
    ConfidenceLabel,
    ConversationScope,
    DecisionRecord,
    DecisionRequest,
    EntityClass,
    EntityDecision,
    Intent,
    IntentConfidenceBand,
    IntentDecision,
    IntentSignals,
    IntentSubtype,
    KnowledgeMode,
    ModeAssignment,
    ResponseStrategy,
    TimeDimension,
    TimeInterpretation,
    classify_intent_confidence,
    decision_record_json,
    select_intent,
)

CONTRACT_PATH = Path(__file__).parent / "fixtures" / "ask_decision_taxonomy.json"


@pytest.fixture(scope="module")
def contract() -> dict[str, Any]:
    return json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))


def test_frozen_taxonomy_fixture_covers_every_intent_and_precedence_rule(
    contract: dict[str, Any],
) -> None:
    assert contract["schema_version"] == DECISION_SCHEMA_VERSION
    assert contract["policy_version"] == DECISION_POLICY_VERSION
    assert tuple(contract["intent_precedence"]) == INTENT_PRECEDENCE
    assert {row["intent"] for row in contract["intents"]} == {
        intent.value for intent in Intent
    }
    assert {
        Intent(row["intent"]): ResponseStrategy(row["response_strategy"])
        for row in contract["intents"]
    } == INTENT_RESPONSE_STRATEGY
    assert {
        IntentSubtype(subtype): tuple(Intent(parent) for parent in parents)
        for subtype, parents in contract["subtypes"].items()
    } == INTENT_SUBTYPE_PARENTS
    assert len(contract["representative_queries"]) == 19


def test_every_representative_query_uses_only_frozen_taxonomy_values(
    contract: dict[str, Any],
) -> None:
    for fixture in contract["representative_queries"]:
        primary = Intent(fixture["primary"])
        secondary = tuple(Intent(value) for value in fixture["secondary"])
        subtypes = tuple(IntentSubtype(value) for value in fixture["subtypes"])
        strategy = ResponseStrategy(fixture["response_strategy"])

        assert primary not in secondary
        assert strategy == INTENT_RESPONSE_STRATEGY[primary]
        assert len(set(secondary)) == len(secondary)
        assert len(set(subtypes)) == len(subtypes)


@pytest.mark.parametrize(
    ("signals", "primary", "secondary", "subtypes", "rule"),
    [
        (
            IntentSignals(
                has_selected_referent=True,
                interaction_action="explain",
                atomic_intents=(Intent.DEFINITION, Intent.DEADLINE),
                explicit_compliance=True,
            ),
            Intent.DOCUMENT_EXPLANATION,
            (),
            (),
            "interaction_context",
        ),
        (
            IntentSignals(
                has_selected_referent=True,
                interaction_action="pronoun",
                explicit_compliance=True,
            ),
            Intent.DOCUMENT_EXPLANATION,
            (),
            (),
            "interaction_context",
        ),
        (
            IntentSignals(
                atomic_intents=(Intent.COMPARISON, Intent.CONSULTATION),
                explicit_compliance=True,
            ),
            Intent.MULTI_PART_QUESTION,
            (Intent.COMPARISON, Intent.CONSULTATION),
            (),
            "multi_part",
        ),
        (
            IntentSignals(
                explicit_compliance=True,
                explicit_comparison=True,
                resolved_comparison_operands=2,
                explicit_deadline=True,
                explicit_live_recency=True,
            ),
            Intent.COMPLIANCE_QUESTION,
            (Intent.DEADLINE, Intent.NEWS),
            (),
            "compliance",
        ),
        (
            IntentSignals(
                explicit_comparison=True,
                resolved_comparison_operands=2,
                explicit_amendment=True,
            ),
            Intent.COMPARISON,
            (),
            (),
            "comparison",
        ),
        (
            IntentSignals(explicit_side_by_side_version_change=True),
            Intent.COMPARISON,
            (),
            (IntentSubtype.VERSION_COMPARISON,),
            "amendment_or_version_change",
        ),
        (
            IntentSignals(explicit_amendment=True, explicit_live_recency=True),
            Intent.AMENDMENT,
            (Intent.NEWS,),
            (),
            "amendment_or_version_change",
        ),
        (
            IntentSignals(explicit_version_change=True),
            Intent.AMENDMENT,
            (),
            (),
            "amendment_or_version_change",
        ),
        (
            IntentSignals(
                explicit_deadline=True,
                consultation_comment_deadline=True,
            ),
            Intent.DEADLINE,
            (Intent.CONSULTATION,),
            (),
            "deadline",
        ),
        (
            IntentSignals(explicit_timeline=True, explicit_consultation=True),
            Intent.TIMELINE,
            (),
            (),
            "timeline",
        ),
        (
            IntentSignals(explicit_consultation=True, explicit_live_recency=True),
            Intent.CONSULTATION,
            (),
            (),
            "consultation",
        ),
        (
            IntentSignals(
                explicit_live_recency=True,
                live_object_intent="amendment",
            ),
            Intent.AMENDMENT,
            (Intent.NEWS,),
            (),
            "live_recency",
        ),
        (
            IntentSignals(explicit_live_recency=True, named_regulation=True),
            Intent.NEWS,
            (),
            (),
            "live_recency",
        ),
        (
            IntentSignals(named_regulation=True, explicit_definition=True),
            Intent.REGULATION_LOOKUP,
            (),
            (),
            "named_regulation",
        ),
        (
            IntentSignals(explicit_definition=True, bare_resolved_entity=True),
            Intent.DEFINITION,
            (),
            (),
            "definition",
        ),
        (
            IntentSignals(bare_resolved_entity=True),
            Intent.ENTITY_LOOKUP,
            (),
            (),
            "bare_entity",
        ),
        (
            IntentSignals(responsible_party_question=True),
            Intent.STAKEHOLDER,
            (),
            (IntentSubtype.REGULATOR_LOOKUP,),
            "stakeholder",
        ),
        (
            IntentSignals(known_result_summarization=True),
            Intent.SUMMARIZATION,
            (),
            (),
            "known_result_summarization",
        ),
        (
            IntentSignals(),
            Intent.GENERAL_QUESTION,
            (),
            (),
            "general_question",
        ),
    ],
)
def test_intent_precedence_is_deterministic(
    signals: IntentSignals,
    primary: Intent,
    secondary: tuple[Intent, ...],
    subtypes: tuple[IntentSubtype, ...],
    rule: str,
) -> None:
    first = select_intent(signals)
    second = select_intent(signals)

    assert first == second
    assert first.primary == primary
    assert first.secondary == secondary
    assert first.subtypes == subtypes
    assert first.precedence_rule == rule
    assert first.response_strategy == INTENT_RESPONSE_STRATEGY[primary]


@pytest.mark.parametrize(
    ("score", "gap", "collision", "safe_scope", "expected"),
    [
        (0.90, 0.10, False, False, IntentConfidenceBand.CERTAIN),
        (1.00, 1.00, False, False, IntentConfidenceBand.CERTAIN),
        (0.89, 0.01, False, False, IntentConfidenceBand.STRONG),
        (0.75, 0.00, False, False, IntentConfidenceBand.STRONG),
        (0.74, 0.20, False, True, IntentConfidenceBand.BOUNDED),
        (0.55, 0.00, False, True, IntentConfidenceBand.BOUNDED),
        (0.90, 0.09, False, False, IntentConfidenceBand.AMBIGUOUS),
        (0.74, 0.20, False, False, IntentConfidenceBand.AMBIGUOUS),
        (0.99, 0.50, True, True, IntentConfidenceBand.AMBIGUOUS),
        (0.54, 0.50, False, True, IntentConfidenceBand.AMBIGUOUS),
    ],
)
def test_intent_confidence_boundaries_are_frozen(
    score: float,
    gap: float,
    collision: bool,
    safe_scope: bool,
    expected: IntentConfidenceBand,
) -> None:
    assert classify_intent_confidence(
        score,
        competing_gap=gap,
        material_collision=collision,
        shared_safe_scope=safe_scope,
    ) == expected


def test_decision_record_is_immutable_strict_and_deterministically_serialized() -> None:
    record = _record()
    serialized = decision_record_json(record)

    assert decision_record_json(record) == serialized
    assert DecisionRecord.model_validate_json(serialized) == record
    assert f'"policy_version":"{DECISION_POLICY_VERSION}"' in serialized
    assert '"schema_version":"1"' in serialized
    with pytest.raises(ValidationError):
        record.intent = IntentDecision(  # type: ignore[misc]
            primary=Intent.NEWS,
            confidence=0.9,
            confidence_band=IntentConfidenceBand.CERTAIN,
        )

    payload = record.model_dump(mode="json")
    payload["unexpected"] = True
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        DecisionRecord.model_validate(payload)
    payload = record.model_dump(mode="json")
    payload["intent"]["primary"] = "invented_intent"
    with pytest.raises(ValidationError):
        DecisionRecord.model_validate(payload)


def test_record_validation_fails_closed_for_invalid_ranges_and_duplicate_intents() -> None:
    with pytest.raises(ValidationError, match="cannot be blank"):
        DecisionRequest(query="   ", user_timezone="Asia/Kolkata")
    with pytest.raises(ValidationError, match="reversed"):
        TimeInterpretation(
            dimension=TimeDimension.EFFECTIVE,
            start_at=datetime(2026, 8, 1, tzinfo=UTC),
            end_at=datetime(2026, 7, 1, tzinfo=UTC),
            user_timezone="Asia/Kolkata",
        )
    with pytest.raises(ValidationError, match="cannot also be secondary"):
        IntentDecision(
            primary=Intent.DEADLINE,
            secondary=(Intent.DEADLINE,),
            confidence=0.9,
            confidence_band=IntentConfidenceBand.CERTAIN,
        )
    with pytest.raises(ValueError, match="between 0 and 1"):
        classify_intent_confidence(
            1.01,
            competing_gap=0.2,
            material_collision=False,
            shared_safe_scope=False,
        )
    payload = _record().model_dump(mode="json")
    payload["capabilities"] = [*payload["capabilities"], *payload["capabilities"]]
    with pytest.raises(ValidationError, match="Capability decisions must be unique"):
        DecisionRecord.model_validate(payload)


def _record() -> DecisionRecord:
    return DecisionRecord(
        policy_version=DECISION_POLICY_VERSION,
        request=DecisionRequest(
            query="What is DSM?",
            selected_entity_id="dsm",
            user_timezone="Asia/Kolkata",
        ),
        conversation_scope=ConversationScope(
            entity_ids=("dsm",),
            jurisdiction="central",
        ),
        intent=IntentDecision(
            primary=Intent.DEFINITION,
            confidence=0.95,
            confidence_band=IntentConfidenceBand.CERTAIN,
            reasons=("Explicit definition language.",),
        ),
        entities=(
            EntityDecision(
                mention="DSM",
                canonical_id="dsm",
                canonical_name="Deviation Settlement Mechanism",
                entity_class=EntityClass.REGULATORY_CONCEPT,
                aliases=("DSM",),
                jurisdiction="central",
                confidence=0.95,
                reason="Exact approved acronym.",
            ),
        ),
        time_interpretation=TimeInterpretation(
            dimension=TimeDimension.VALIDITY_PERIOD,
            user_timezone="Asia/Kolkata",
            source_expression="current definition",
            assumed=True,
        ),
        assumptions=("Use the current official definition.",),
        capabilities=(
            CapabilityDecision(
                capability=CapabilityName.GLOSSARY,
                role=CapabilityRole.REQUIRED,
                reason="Resolve the acronym and definition.",
            ),
        ),
        knowledge_modes=(
            ModeAssignment(
                section_key="definition",
                mode=KnowledgeMode.GROUNDED_REGULATORY,
                reason="Official definition evidence is preferred.",
            ),
        ),
        response_strategy=ResponseStrategy.DEFINITION_CARD,
        confidence=ConfidenceAssessment(
            overall_label=ConfidenceLabel.UNKNOWN,
            reasons=("Evidence has not been assessed.",),
        ),
    )
