from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from backend.ask.decision import (
    CONTEXT_PRECEDENCE,
    DECISION_POLICY_VERSION,
    AtomicClause,
    AtomicQuestion,
    ContextResolutionRequest,
    ContextResolutionStatus,
    ConversationScope,
    CurrentTurnScope,
    DecompositionRequest,
    Intent,
    IntentSubtype,
    ScopeField,
    ScopeSource,
    ScopeValues,
    decompose_questions,
    resolve_context,
)

CASES_PATH = Path(__file__).parent / "fixtures" / "ask_context_policy_cases.json"


@pytest.fixture(scope="module")
def cases() -> dict[str, Any]:
    return json.loads(CASES_PATH.read_text(encoding="utf-8"))


def test_context_fixture_is_versioned_and_freezes_precedence(
    cases: dict[str, Any],
) -> None:
    assert cases["schema_version"] == "1"
    assert cases["policy_version"] == DECISION_POLICY_VERSION
    assert tuple(cases["context_precedence"]) == CONTEXT_PRECEDENCE


def test_recorded_context_precedence_and_clarification_cases(
    cases: dict[str, Any],
) -> None:
    for case in cases["context_cases"]:
        result = resolve_context(
            ContextResolutionRequest.model_validate(case["request"])
        )
        expected = case["expected"]

        assert result.status.value == expected["status"], case["name"]
        if result.status is ContextResolutionStatus.CLARIFICATION_REQUIRED:
            assert len(result.reference_candidates) == expected["candidate_count"]
            assert result.clarification_question is not None
            assert result.clarification_question.count("?") == 1
            continue

        if "entity_ids" in expected:
            assert list(result.scope.entity_ids) == expected["entity_ids"]
        if "entity_source" in expected:
            assert (
                result.sources[ScopeField.ENTITIES].value
                == expected["entity_source"]
            )
        if "jurisdiction" in expected:
            assert result.scope.jurisdiction == expected["jurisdiction"]
        if "jurisdiction_source" in expected:
            assert (
                result.sources[ScopeField.JURISDICTION].value
                == expected["jurisdiction_source"]
            )
        if "stakeholder" in expected:
            assert result.scope.stakeholder == expected["stakeholder"]
        if "stakeholder_source" in expected:
            assert (
                result.sources[ScopeField.STAKEHOLDER].value
                == expected["stakeholder_source"]
            )
        if "assumption_count" in expected:
            assert len(result.assumptions) == expected["assumption_count"]


def test_context_precedence_is_field_specific() -> None:
    result = resolve_context(
        ContextResolutionRequest(
            interaction_context=ScopeValues(
                entity_ids=("in.central.dsm",),
            ),
            current_turn=CurrentTurnScope(
                jurisdiction="India/Gujarat",
                stakeholder="distribution licensee",
            ),
            conversation_scope=ScopeValues(
                entity_ids=("in.central.abt",),
                jurisdiction="India/Central",
                time_scope="historical",
            ),
            regulatory_defaults=ScopeValues(time_scope="current"),
        )
    )

    assert result.scope == ConversationScope(
        entity_ids=("in.central.dsm",),
        jurisdiction="India/Gujarat",
        stakeholder="distribution licensee",
        time_scope="historical",
    )
    assert result.sources == {
        ScopeField.ENTITIES: ScopeSource.INTERACTION_CONTEXT,
        ScopeField.JURISDICTION: ScopeSource.EXPLICIT_CURRENT_TURN,
        ScopeField.STAKEHOLDER: ScopeSource.EXPLICIT_CURRENT_TURN,
        ScopeField.TIME_SCOPE: ScopeSource.CONVERSATION_SCOPE,
    }
    assert result.assumptions == ()


@pytest.mark.parametrize(
    ("field", "attribute", "current_value", "conversation_value"),
    [
        (
            ScopeField.ENTITIES,
            "entity_ids",
            ("in.central.mnre",),
            ("in.central.dsm",),
        ),
        (
            ScopeField.JURISDICTION,
            "jurisdiction",
            "India/Central",
            "India/Gujarat",
        ),
        (
            ScopeField.STAKEHOLDER,
            "stakeholder",
            "generator",
            "distribution licensee",
        ),
        (ScopeField.TIME_SCOPE, "time_scope", "current", "historical"),
        (
            ScopeField.EXCLUSIONS,
            "exclusions",
            ("draft",),
            ("in_force",),
        ),
    ],
)
def test_current_turn_property_overrides_every_conversation_scope_field(
    field: ScopeField,
    attribute: str,
    current_value: object,
    conversation_value: object,
) -> None:
    result = resolve_context(
        ContextResolutionRequest(
            current_turn=CurrentTurnScope(
                **{attribute: current_value},
            ),
            conversation_scope=ScopeValues(
                **{attribute: conversation_value},
            ),
        )
    )

    assert getattr(result.scope, attribute) == current_value
    assert result.sources[field] is ScopeSource.EXPLICIT_CURRENT_TURN


def test_explicit_current_entity_removes_pronoun_ambiguity() -> None:
    result = resolve_context(
        ContextResolutionRequest(
            current_turn=CurrentTurnScope(
                entity_ids=("in.central.mnre",),
            ),
            unresolved_reference="it",
            reference_candidates=(
                {
                    "canonical_id": "in.central.dsm",
                    "label": "Deviation Settlement Mechanism",
                },
                {
                    "canonical_id": "in.central.abt",
                    "label": "Availability Based Tariff",
                },
            ),
        )
    )

    assert result.status is ContextResolutionStatus.RESOLVED
    assert result.scope.entity_ids == ("in.central.mnre",)
    assert (
        result.sources[ScopeField.ENTITIES]
        is ScopeSource.EXPLICIT_CURRENT_TURN
    )


def test_clarification_preserves_non_ambiguous_scope_and_reset_blocks_antecedent() -> None:
    result = resolve_context(
        ContextResolutionRequest(
            current_turn=CurrentTurnScope(
                jurisdiction="India/Central",
                reset_fields=frozenset({ScopeField.ENTITIES}),
            ),
            conversation_scope=ScopeValues(
                entity_ids=("in.central.dsm",),
                stakeholder="generator",
            ),
            unresolved_reference="it",
            reference_candidates=(
                {
                    "canonical_id": "in.central.dsm",
                    "label": "Deviation Settlement Mechanism",
                },
            ),
        )
    )

    assert result.status is ContextResolutionStatus.CLARIFICATION_REQUIRED
    assert result.scope.entity_ids == ()
    assert result.scope.jurisdiction == "India/Central"
    assert result.scope.stakeholder == "generator"
    assert (
        result.sources[ScopeField.JURISDICTION]
        is ScopeSource.EXPLICIT_CURRENT_TURN
    )
    assert (
        result.sources[ScopeField.STAKEHOLDER]
        is ScopeSource.CONVERSATION_SCOPE
    )


def test_recorded_decomposition_cases(
    cases: dict[str, Any],
) -> None:
    for case in cases["decomposition_cases"]:
        result = decompose_questions(
            DecompositionRequest.model_validate(case["request"])
        )
        expected = case["expected"]

        assert result.overall_intent.value == expected["overall_intent"], case[
            "name"
        ]
        assert [intent.value for intent in result.component_intents] == expected[
            "component_intents"
        ]
        assert [question.id for question in result.questions] == expected[
            "question_ids"
        ]
        assert [field.value for field in result.scope_conflicts] == expected[
            "scope_conflicts"
        ]
        assert result.coverage_summary_required is True
        if "time_scopes" in expected:
            assert [
                question.inherited_scope.time_scope
                for question in result.questions
            ] == expected["time_scopes"]
        if "jurisdictions" in expected:
            assert [
                question.inherited_scope.jurisdiction
                for question in result.questions
            ] == expected["jurisdictions"]


def test_entities_and_stakeholders_are_shared_unless_clause_overrides() -> None:
    result = decompose_questions(
        DecompositionRequest(
            shared_scope=ConversationScope(
                entity_ids=("in.central.dsm",),
                jurisdiction="India/Central",
                stakeholder="generator",
                exclusions=("historical",),
            ),
            clauses=(
                AtomicClause(
                    question="Explain DSM.",
                    intent=Intent.DEFINITION,
                ),
                AtomicClause(
                    question="Compare ABT.",
                    intent=Intent.COMPARISON,
                    secondary_intents=(Intent.ENTITY_LOOKUP,),
                    subtypes=(IntentSubtype.VERSION_COMPARISON,),
                    scope_override=ScopeValues(
                        entity_ids=("in.central.abt",),
                        stakeholder="distribution licensee",
                        exclusions=(),
                    ),
                ),
            ),
        )
    )

    first, second = result.questions
    assert first.inherited_scope.entity_ids == ("in.central.dsm",)
    assert first.inherited_scope.stakeholder == "generator"
    assert first.inherited_scope.exclusions == ("historical",)
    assert second.inherited_scope.entity_ids == ("in.central.abt",)
    assert second.inherited_scope.jurisdiction == "India/Central"
    assert second.inherited_scope.stakeholder == "distribution licensee"
    assert second.inherited_scope.exclusions == ()
    assert second.secondary_intents == (Intent.ENTITY_LOOKUP,)
    assert second.subtypes == (IntentSubtype.VERSION_COMPARISON,)


def test_single_clause_keeps_its_intent_without_coverage_summary() -> None:
    result = decompose_questions(
        DecompositionRequest(
            clauses=(
                AtomicClause(
                    question="What is DSM?",
                    intent=Intent.DEFINITION,
                ),
            )
        )
    )

    assert result.overall_intent is Intent.DEFINITION
    assert result.component_intents == (Intent.DEFINITION,)
    assert result.questions[0].id == "question-1"
    assert result.coverage_summary_required is False
    assert result.scope_conflicts == ()


def test_context_and_decomposition_validation_fail_closed() -> None:
    with pytest.raises(ValidationError, match="reset and set"):
        CurrentTurnScope(
            jurisdiction="India/Central",
            reset_fields=frozenset({ScopeField.JURISDICTION}),
        )
    with pytest.raises(ValidationError, match="require an unresolved reference"):
        ContextResolutionRequest(
            reference_candidates=(
                {
                    "canonical_id": "in.central.dsm",
                    "label": "DSM",
                },
            )
        )
    with pytest.raises(ValidationError, match="Atomic questions must be distinct"):
        DecompositionRequest(
            clauses=(
                AtomicClause(question="Explain DSM.", intent=Intent.DEFINITION),
                AtomicClause(question="explain dsm.", intent=Intent.DEFINITION),
            )
        )
    with pytest.raises(ValidationError, match="not valid"):
        AtomicClause(
            question="Explain DSM.",
            intent=Intent.DEFINITION,
            subtypes=(IntentSubtype.VERSION_COMPARISON,),
        )
    with pytest.raises(ValidationError, match="cannot also be secondary"):
        AtomicQuestion(
            id="q1",
            question="Explain DSM.",
            intent=Intent.DEFINITION,
            secondary_intents=(Intent.DEFINITION,),
        )
    with pytest.raises(ValidationError, match="not valid"):
        AtomicQuestion(
            id="q1",
            question="Explain DSM.",
            intent=Intent.DEFINITION,
            subtypes=(IntentSubtype.VERSION_COMPARISON,),
        )
    with pytest.raises(ValidationError, match="cannot be blank"):
        AtomicQuestion(
            id=" ",
            question="Explain DSM.",
            intent=Intent.DEFINITION,
        )
