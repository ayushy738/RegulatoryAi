from __future__ import annotations

from collections.abc import Iterable
from enum import StrEnum
from typing import Self

from pydantic import Field, field_validator, model_validator

from backend.ask.decision.models import (
    INTENT_SUBTYPE_PARENTS,
    AtomicQuestion,
    ConversationScope,
    DecisionModel,
    Intent,
    IntentSubtype,
)

CONTEXT_PRECEDENCE = (
    "interaction_context",
    "explicit_current_turn",
    "conversation_scope",
    "regulatory_defaults",
    "clarification",
)


class ScopeField(StrEnum):
    ENTITIES = "entities"
    JURISDICTION = "jurisdiction"
    STAKEHOLDER = "stakeholder"
    TIME_SCOPE = "time_scope"
    EXCLUSIONS = "exclusions"


class ScopeSource(StrEnum):
    INTERACTION_CONTEXT = "interaction_context"
    EXPLICIT_CURRENT_TURN = "explicit_current_turn"
    CONVERSATION_SCOPE = "conversation_scope"
    REGULATORY_DEFAULT = "regulatory_default"


class ContextResolutionStatus(StrEnum):
    RESOLVED = "resolved"
    CLARIFICATION_REQUIRED = "clarification_required"


class ScopeValues(DecisionModel):
    entity_ids: tuple[str, ...] | None = None
    jurisdiction: str | None = None
    stakeholder: str | None = None
    time_scope: str | None = None
    exclusions: tuple[str, ...] | None = None

    @field_validator("entity_ids", "exclusions")
    @classmethod
    def validate_unique_lists(
        cls,
        values: tuple[str, ...] | None,
    ) -> tuple[str, ...] | None:
        if values is None:
            return None
        normalized = tuple(value.strip() for value in values)
        if any(not value for value in normalized):
            raise ValueError("Scope values cannot contain blank text")
        if len(set(normalized)) != len(normalized):
            raise ValueError("Scope values must be unique")
        return normalized

    @field_validator("jurisdiction", "stakeholder", "time_scope")
    @classmethod
    def validate_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("Scope text cannot be blank")
        return normalized


class CurrentTurnScope(ScopeValues):
    reset_fields: frozenset[ScopeField] = frozenset()

    @model_validator(mode="after")
    def reject_reset_with_value(self) -> Self:
        values = {
            ScopeField.ENTITIES: self.entity_ids,
            ScopeField.JURISDICTION: self.jurisdiction,
            ScopeField.STAKEHOLDER: self.stakeholder,
            ScopeField.TIME_SCOPE: self.time_scope,
            ScopeField.EXCLUSIONS: self.exclusions,
        }
        collisions = tuple(
            field.value
            for field in self.reset_fields
            if values[field] is not None
        )
        if collisions:
            raise ValueError(
                "Current-turn scope cannot reset and set the same fields: "
                + ", ".join(collisions)
            )
        return self


class ReferenceCandidate(DecisionModel):
    canonical_id: str = Field(min_length=1)
    label: str = Field(min_length=1)

    @field_validator("canonical_id", "label")
    @classmethod
    def reject_blank_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Reference candidate text cannot be blank")
        return normalized


class ContextResolutionRequest(DecisionModel):
    interaction_context: ScopeValues = Field(default_factory=ScopeValues)
    current_turn: CurrentTurnScope = Field(default_factory=CurrentTurnScope)
    conversation_scope: ScopeValues = Field(default_factory=ScopeValues)
    regulatory_defaults: ScopeValues = Field(default_factory=ScopeValues)
    unresolved_reference: str | None = None
    reference_candidates: tuple[ReferenceCandidate, ...] = ()

    @field_validator("unresolved_reference")
    @classmethod
    def validate_reference(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("Unresolved reference cannot be blank")
        return normalized

    @model_validator(mode="after")
    def validate_reference_candidates(self) -> Self:
        ids = [candidate.canonical_id for candidate in self.reference_candidates]
        if len(ids) != len(set(ids)):
            raise ValueError("Reference candidate IDs must be unique")
        if self.reference_candidates and self.unresolved_reference is None:
            raise ValueError(
                "Reference candidates require an unresolved reference"
            )
        return self


class ContextResolution(DecisionModel):
    status: ContextResolutionStatus
    scope: ConversationScope
    sources: dict[ScopeField, ScopeSource] = Field(default_factory=dict)
    assumptions: tuple[str, ...] = ()
    clarification_question: str | None = None
    reference_candidates: tuple[ReferenceCandidate, ...] = ()

    @model_validator(mode="after")
    def validate_terminal_shape(self) -> Self:
        if self.status is ContextResolutionStatus.CLARIFICATION_REQUIRED:
            if self.clarification_question is None:
                raise ValueError("Clarification requires one focused question")
        elif self.clarification_question is not None:
            raise ValueError("Resolved context cannot include a clarification")
        return self


class AtomicClause(DecisionModel):
    question: str = Field(min_length=1)
    intent: Intent
    secondary_intents: tuple[Intent, ...] = ()
    subtypes: tuple[IntentSubtype, ...] = ()
    scope_override: ScopeValues = Field(default_factory=ScopeValues)

    @field_validator("question")
    @classmethod
    def reject_blank_question(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Atomic question cannot be blank")
        return normalized

    @model_validator(mode="after")
    def validate_intent_set(self) -> Self:
        if self.intent in self.secondary_intents:
            raise ValueError("An atomic primary intent cannot also be secondary")
        if len(set(self.secondary_intents)) != len(self.secondary_intents):
            raise ValueError("Atomic secondary intents must be unique")
        if len(set(self.subtypes)) != len(self.subtypes):
            raise ValueError("Atomic intent subtypes must be unique")
        for subtype in self.subtypes:
            if self.intent not in INTENT_SUBTYPE_PARENTS[subtype]:
                raise ValueError(
                    f"{subtype.value} is not valid for {self.intent.value}"
                )
        return self


class DecompositionRequest(DecisionModel):
    clauses: tuple[AtomicClause, ...] = Field(min_length=1)
    shared_scope: ConversationScope = Field(default_factory=ConversationScope)
    global_time_scope: str | None = None

    @field_validator("global_time_scope")
    @classmethod
    def validate_global_time(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("Global time scope cannot be blank")
        return normalized

    @model_validator(mode="after")
    def validate_distinct_clauses(self) -> Self:
        normalized = [
            " ".join(clause.question.casefold().split())
            for clause in self.clauses
        ]
        if len(normalized) != len(set(normalized)):
            raise ValueError("Atomic questions must be distinct")
        return self


class DecompositionResult(DecisionModel):
    overall_intent: Intent
    component_intents: tuple[Intent, ...]
    questions: tuple[AtomicQuestion, ...]
    shared_scope: ConversationScope
    scope_conflicts: tuple[ScopeField, ...] = ()
    coverage_summary_required: bool

    @model_validator(mode="after")
    def validate_multi_part_shape(self) -> Self:
        multi_part = len(self.questions) >= 2
        if multi_part != (self.overall_intent is Intent.MULTI_PART_QUESTION):
            raise ValueError("Overall intent must reflect atomic question count")
        if self.coverage_summary_required != multi_part:
            raise ValueError("Only multi-part results require coverage summaries")
        return self


def resolve_context(request: ContextResolutionRequest) -> ContextResolution:
    chosen_before_conversation = bool(
        request.interaction_context.entity_ids is not None
        or request.current_turn.entity_ids is not None
    )
    retained_entity_scope_reset = (
        ScopeField.ENTITIES in request.current_turn.reset_fields
    )
    reference_scope: tuple[str, ...] | None = None
    reference_is_ambiguous = False
    if request.unresolved_reference is not None and not chosen_before_conversation:
        if retained_entity_scope_reset or len(request.reference_candidates) != 1:
            reference_is_ambiguous = True
        else:
            reference_scope = (request.reference_candidates[0].canonical_id,)

    sources: dict[ScopeField, ScopeSource] = {}
    assumptions: list[str] = []
    if reference_is_ambiguous:
        entity_ids: object = ()
        if retained_entity_scope_reset:
            sources[ScopeField.ENTITIES] = ScopeSource.EXPLICIT_CURRENT_TURN
    else:
        entity_ids = _resolve_field(
            ScopeField.ENTITIES,
            request,
            sources,
            assumptions,
            conversation_override=reference_scope,
        )
    jurisdiction = _resolve_field(
        ScopeField.JURISDICTION,
        request,
        sources,
        assumptions,
    )
    stakeholder = _resolve_field(
        ScopeField.STAKEHOLDER,
        request,
        sources,
        assumptions,
    )
    time_scope = _resolve_field(
        ScopeField.TIME_SCOPE,
        request,
        sources,
        assumptions,
    )
    exclusions = _resolve_field(
        ScopeField.EXCLUSIONS,
        request,
        sources,
        assumptions,
    )
    scope = ConversationScope(
        entity_ids=entity_ids or (),
        jurisdiction=jurisdiction,
        stakeholder=stakeholder,
        time_scope=time_scope,
        exclusions=exclusions or (),
    )
    if reference_is_ambiguous:
        return _reference_clarification(
            request,
            scope=scope,
            sources=sources,
            assumptions=tuple(assumptions),
        )
    return ContextResolution(
        status=ContextResolutionStatus.RESOLVED,
        scope=scope,
        sources=sources,
        assumptions=tuple(assumptions),
    )


def decompose_questions(request: DecompositionRequest) -> DecompositionResult:
    questions = tuple(
        AtomicQuestion(
            id=f"question-{ordinal}",
            question=clause.question,
            intent=clause.intent,
            secondary_intents=clause.secondary_intents,
            subtypes=clause.subtypes,
            inherited_scope=_clause_scope(request, clause),
        )
        for ordinal, clause in enumerate(request.clauses, start=1)
    )
    component_intents = tuple(
        dict.fromkeys(question.intent for question in questions)
    )
    multi_part = len(questions) >= 2
    return DecompositionResult(
        overall_intent=(
            Intent.MULTI_PART_QUESTION if multi_part else questions[0].intent
        ),
        component_intents=component_intents,
        questions=questions,
        shared_scope=request.shared_scope,
        scope_conflicts=_scope_conflicts(questions),
        coverage_summary_required=multi_part,
    )


def _resolve_field(
    field: ScopeField,
    request: ContextResolutionRequest,
    sources: dict[ScopeField, ScopeSource],
    assumptions: list[str],
    *,
    conversation_override: tuple[str, ...] | None = None,
) -> object:
    attribute = _field_attribute(field)
    layers = (
        (
            getattr(request.interaction_context, attribute),
            ScopeSource.INTERACTION_CONTEXT,
        ),
        (
            getattr(request.current_turn, attribute),
            ScopeSource.EXPLICIT_CURRENT_TURN,
        ),
    )
    for value, source in layers:
        if value is not None:
            sources[field] = source
            return value

    reset = field in request.current_turn.reset_fields
    if field is ScopeField.ENTITIES and conversation_override is not None:
        sources[field] = ScopeSource.CONVERSATION_SCOPE
        return conversation_override
    conversation_value = getattr(request.conversation_scope, attribute)
    if not reset and conversation_value is not None:
        sources[field] = ScopeSource.CONVERSATION_SCOPE
        return conversation_value

    default_value = getattr(request.regulatory_defaults, attribute)
    if default_value is not None:
        sources[field] = ScopeSource.REGULATORY_DEFAULT
        assumptions.append(f"Assumed {field.value} from regulatory defaults.")
        return default_value
    if reset:
        sources[field] = ScopeSource.EXPLICIT_CURRENT_TURN
    return None


def _field_attribute(field: ScopeField) -> str:
    return {
        ScopeField.ENTITIES: "entity_ids",
        ScopeField.JURISDICTION: "jurisdiction",
        ScopeField.STAKEHOLDER: "stakeholder",
        ScopeField.TIME_SCOPE: "time_scope",
        ScopeField.EXCLUSIONS: "exclusions",
    }[field]


def _reference_clarification(
    request: ContextResolutionRequest,
    *,
    scope: ConversationScope,
    sources: dict[ScopeField, ScopeSource],
    assumptions: tuple[str, ...],
) -> ContextResolution:
    assert request.unresolved_reference is not None
    labels = tuple(candidate.label for candidate in request.reference_candidates)
    if labels:
        choices = " or ".join(labels[:3])
        question = (
            f"Which entity does '{request.unresolved_reference}' refer to: "
            f"{choices}?"
        )
    else:
        question = (
            f"Which entity does '{request.unresolved_reference}' refer to?"
        )
    return ContextResolution(
        status=ContextResolutionStatus.CLARIFICATION_REQUIRED,
        scope=scope,
        sources=sources,
        assumptions=assumptions,
        clarification_question=question,
        reference_candidates=request.reference_candidates,
    )


def _clause_scope(
    request: DecompositionRequest,
    clause: AtomicClause,
) -> ConversationScope:
    override = clause.scope_override
    return ConversationScope(
        entity_ids=(
            override.entity_ids
            if override.entity_ids is not None
            else request.shared_scope.entity_ids
        ),
        jurisdiction=(
            override.jurisdiction
            if override.jurisdiction is not None
            else request.shared_scope.jurisdiction
        ),
        stakeholder=(
            override.stakeholder
            if override.stakeholder is not None
            else request.shared_scope.stakeholder
        ),
        time_scope=(
            override.time_scope
            if override.time_scope is not None
            else request.global_time_scope or request.shared_scope.time_scope
        ),
        exclusions=(
            override.exclusions
            if override.exclusions is not None
            else request.shared_scope.exclusions
        ),
    )


def _scope_conflicts(
    questions: tuple[AtomicQuestion, ...],
) -> tuple[ScopeField, ...]:
    fields: list[ScopeField] = []
    if _multiple_non_null(
        question.inherited_scope.jurisdiction for question in questions
    ):
        fields.append(ScopeField.JURISDICTION)
    if _multiple_non_null(
        question.inherited_scope.stakeholder for question in questions
    ):
        fields.append(ScopeField.STAKEHOLDER)
    if _multiple_non_null(
        question.inherited_scope.time_scope for question in questions
    ):
        fields.append(ScopeField.TIME_SCOPE)
    if len(
        {
            question.inherited_scope.exclusions
            for question in questions
        }
    ) > 1:
        fields.append(ScopeField.EXCLUSIONS)
    return tuple(fields)


def _multiple_non_null(values: Iterable[object | None]) -> bool:
    materialized = {value for value in values if value is not None}
    return len(materialized) > 1
