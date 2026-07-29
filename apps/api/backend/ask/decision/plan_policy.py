from __future__ import annotations

from enum import StrEnum
from typing import Self

from pydantic import Field, field_validator, model_validator

from backend.ask.decision.models import (
    INTENT_SUBTYPE_PARENTS,
    CapabilityName,
    CapabilityRole,
    DecisionModel,
    Intent,
    IntentSubtype,
    ResponseStrategy,
    RetrievalPlan,
)
from backend.ask.decision.policy import INTENT_RESPONSE_STRATEGY


class PlanClass(StrEnum):
    FAST_EXACT = "fast_exact"
    FOCUSED_GROUNDED = "focused_grounded"
    LIVE_COMBINED = "live_combined"
    DEEP_RESEARCH = "deep_research"
    COMPOSITE = "composite"


class CapabilityStage(StrEnum):
    CHEAP_RESOLUTION = "cheap_resolution"
    INTENT_EVIDENCE = "intent_evidence"
    CONDITIONAL_FALLBACK = "conditional_fallback"


class PlanningStageName(StrEnum):
    RESOLVE_CHEAPLY = "resolve_cheaply"
    RUN_INTENT_EVIDENCE = "run_intent_evidence"
    ASSESS_SUFFICIENCY = "assess_sufficiency"
    ACTIVATE_CONDITIONAL_FALLBACKS = "activate_conditional_fallbacks"
    SELECT_RESPONSE_AND_VERIFICATION = "select_response_and_verification"


PLANNING_STAGES = tuple(PlanningStageName)

CAPABILITY_STAGES = {
    CapabilityName.GLOSSARY: CapabilityStage.CHEAP_RESOLUTION,
    CapabilityName.ENTITY_INDEX: CapabilityStage.CHEAP_RESOLUTION,
    CapabilityName.DOCUMENT_METADATA: CapabilityStage.CHEAP_RESOLUTION,
    CapabilityName.CONVERSATION_CONTEXT: CapabilityStage.CHEAP_RESOLUTION,
    CapabilityName.INTERNAL_DOCUMENT_SEARCH: CapabilityStage.INTENT_EVIDENCE,
    CapabilityName.KNOWLEDGE_GRAPH: CapabilityStage.INTENT_EVIDENCE,
    CapabilityName.VERSION_LINEAGE: CapabilityStage.INTENT_EVIDENCE,
    CapabilityName.LIVE_NEWS: CapabilityStage.INTENT_EVIDENCE,
    CapabilityName.GENERAL_AI: CapabilityStage.CONDITIONAL_FALLBACK,
}

_S = CapabilityRole.SKIPPED
_R = CapabilityRole.REQUIRED
_P = CapabilityRole.SUPPORTING
_C = CapabilityRole.CONDITIONAL

INTENT_CAPABILITY_ROLES: dict[Intent, dict[CapabilityName, CapabilityRole]] = {
    Intent.DEFINITION: {
        CapabilityName.GLOSSARY: _R,
        CapabilityName.ENTITY_INDEX: _P,
        CapabilityName.INTERNAL_DOCUMENT_SEARCH: _P,
        CapabilityName.DOCUMENT_METADATA: _S,
        CapabilityName.KNOWLEDGE_GRAPH: _S,
        CapabilityName.VERSION_LINEAGE: _S,
        CapabilityName.LIVE_NEWS: _S,
        CapabilityName.GENERAL_AI: _C,
        CapabilityName.CONVERSATION_CONTEXT: _S,
    },
    Intent.ENTITY_LOOKUP: {
        CapabilityName.GLOSSARY: _P,
        CapabilityName.ENTITY_INDEX: _R,
        CapabilityName.INTERNAL_DOCUMENT_SEARCH: _R,
        CapabilityName.DOCUMENT_METADATA: _P,
        CapabilityName.KNOWLEDGE_GRAPH: _R,
        CapabilityName.VERSION_LINEAGE: _P,
        CapabilityName.LIVE_NEWS: _C,
        CapabilityName.GENERAL_AI: _C,
        CapabilityName.CONVERSATION_CONTEXT: _S,
    },
    Intent.REGULATION_LOOKUP: {
        CapabilityName.GLOSSARY: _S,
        CapabilityName.ENTITY_INDEX: _P,
        CapabilityName.INTERNAL_DOCUMENT_SEARCH: _R,
        CapabilityName.DOCUMENT_METADATA: _R,
        CapabilityName.KNOWLEDGE_GRAPH: _P,
        CapabilityName.VERSION_LINEAGE: _P,
        CapabilityName.LIVE_NEWS: _S,
        CapabilityName.GENERAL_AI: _C,
        CapabilityName.CONVERSATION_CONTEXT: _S,
    },
    Intent.DEADLINE: {
        CapabilityName.GLOSSARY: _S,
        CapabilityName.ENTITY_INDEX: _P,
        CapabilityName.INTERNAL_DOCUMENT_SEARCH: _R,
        CapabilityName.DOCUMENT_METADATA: _P,
        CapabilityName.KNOWLEDGE_GRAPH: _R,
        CapabilityName.VERSION_LINEAGE: _P,
        CapabilityName.LIVE_NEWS: _C,
        CapabilityName.GENERAL_AI: _C,
        CapabilityName.CONVERSATION_CONTEXT: _S,
    },
    Intent.STAKEHOLDER: {
        CapabilityName.GLOSSARY: _S,
        CapabilityName.ENTITY_INDEX: _R,
        CapabilityName.INTERNAL_DOCUMENT_SEARCH: _R,
        CapabilityName.DOCUMENT_METADATA: _S,
        CapabilityName.KNOWLEDGE_GRAPH: _R,
        CapabilityName.VERSION_LINEAGE: _S,
        CapabilityName.LIVE_NEWS: _S,
        CapabilityName.GENERAL_AI: _C,
        CapabilityName.CONVERSATION_CONTEXT: _S,
    },
    Intent.COMPARISON: {
        CapabilityName.GLOSSARY: _P,
        CapabilityName.ENTITY_INDEX: _R,
        CapabilityName.INTERNAL_DOCUMENT_SEARCH: _R,
        CapabilityName.DOCUMENT_METADATA: _P,
        CapabilityName.KNOWLEDGE_GRAPH: _P,
        CapabilityName.VERSION_LINEAGE: _C,
        CapabilityName.LIVE_NEWS: _C,
        CapabilityName.GENERAL_AI: _C,
        CapabilityName.CONVERSATION_CONTEXT: _S,
    },
    Intent.NEWS: {
        CapabilityName.GLOSSARY: _P,
        CapabilityName.ENTITY_INDEX: _R,
        CapabilityName.INTERNAL_DOCUMENT_SEARCH: _P,
        CapabilityName.DOCUMENT_METADATA: _P,
        CapabilityName.KNOWLEDGE_GRAPH: _P,
        CapabilityName.VERSION_LINEAGE: _C,
        CapabilityName.LIVE_NEWS: _R,
        CapabilityName.GENERAL_AI: _C,
        CapabilityName.CONVERSATION_CONTEXT: _S,
    },
    Intent.TIMELINE: {
        CapabilityName.GLOSSARY: _S,
        CapabilityName.ENTITY_INDEX: _R,
        CapabilityName.INTERNAL_DOCUMENT_SEARCH: _R,
        CapabilityName.DOCUMENT_METADATA: _P,
        CapabilityName.KNOWLEDGE_GRAPH: _R,
        CapabilityName.VERSION_LINEAGE: _R,
        CapabilityName.LIVE_NEWS: _C,
        CapabilityName.GENERAL_AI: _C,
        CapabilityName.CONVERSATION_CONTEXT: _S,
    },
    Intent.COMPLIANCE_QUESTION: {
        CapabilityName.GLOSSARY: _P,
        CapabilityName.ENTITY_INDEX: _R,
        CapabilityName.INTERNAL_DOCUMENT_SEARCH: _R,
        CapabilityName.DOCUMENT_METADATA: _P,
        CapabilityName.KNOWLEDGE_GRAPH: _R,
        CapabilityName.VERSION_LINEAGE: _P,
        CapabilityName.LIVE_NEWS: _C,
        CapabilityName.GENERAL_AI: _C,
        CapabilityName.CONVERSATION_CONTEXT: _S,
    },
    Intent.SUMMARIZATION: {
        CapabilityName.GLOSSARY: _S,
        CapabilityName.ENTITY_INDEX: _C,
        CapabilityName.INTERNAL_DOCUMENT_SEARCH: _C,
        CapabilityName.DOCUMENT_METADATA: _C,
        CapabilityName.KNOWLEDGE_GRAPH: _S,
        CapabilityName.VERSION_LINEAGE: _S,
        CapabilityName.LIVE_NEWS: _C,
        CapabilityName.GENERAL_AI: _C,
        CapabilityName.CONVERSATION_CONTEXT: _S,
    },
    Intent.DOCUMENT_EXPLANATION: {
        CapabilityName.GLOSSARY: _P,
        CapabilityName.ENTITY_INDEX: _P,
        CapabilityName.INTERNAL_DOCUMENT_SEARCH: _R,
        CapabilityName.DOCUMENT_METADATA: _R,
        CapabilityName.KNOWLEDGE_GRAPH: _P,
        CapabilityName.VERSION_LINEAGE: _C,
        CapabilityName.LIVE_NEWS: _S,
        CapabilityName.GENERAL_AI: _C,
        CapabilityName.CONVERSATION_CONTEXT: _S,
    },
    Intent.AMENDMENT: {
        CapabilityName.GLOSSARY: _S,
        CapabilityName.ENTITY_INDEX: _R,
        CapabilityName.INTERNAL_DOCUMENT_SEARCH: _R,
        CapabilityName.DOCUMENT_METADATA: _R,
        CapabilityName.KNOWLEDGE_GRAPH: _P,
        CapabilityName.VERSION_LINEAGE: _R,
        CapabilityName.LIVE_NEWS: _C,
        CapabilityName.GENERAL_AI: _C,
        CapabilityName.CONVERSATION_CONTEXT: _S,
    },
    Intent.CONSULTATION: {
        CapabilityName.GLOSSARY: _S,
        CapabilityName.ENTITY_INDEX: _R,
        CapabilityName.INTERNAL_DOCUMENT_SEARCH: _R,
        CapabilityName.DOCUMENT_METADATA: _R,
        CapabilityName.KNOWLEDGE_GRAPH: _P,
        CapabilityName.VERSION_LINEAGE: _P,
        CapabilityName.LIVE_NEWS: _C,
        CapabilityName.GENERAL_AI: _C,
        CapabilityName.CONVERSATION_CONTEXT: _S,
    },
    Intent.GENERAL_QUESTION: {
        CapabilityName.GLOSSARY: _C,
        CapabilityName.ENTITY_INDEX: _C,
        CapabilityName.INTERNAL_DOCUMENT_SEARCH: _C,
        CapabilityName.DOCUMENT_METADATA: _C,
        CapabilityName.KNOWLEDGE_GRAPH: _S,
        CapabilityName.VERSION_LINEAGE: _S,
        CapabilityName.LIVE_NEWS: _C,
        CapabilityName.GENERAL_AI: _R,
        CapabilityName.CONVERSATION_CONTEXT: _S,
    },
}


class PlanQuestion(DecisionModel):
    question_id: str = Field(min_length=1)
    intent: Intent
    secondary_intents: tuple[Intent, ...] = ()
    subtypes: tuple[IntentSubtype, ...] = ()
    scope_resolved: bool = True
    exact_match: bool = False
    historical_scope: bool = False
    live_eligible: bool = False
    current_intelligence_requested: bool = False
    has_resolved_entity: bool = False
    has_term_like_entity: bool = False
    has_document_target: bool = False
    has_known_sources: bool = False
    general_source_set: bool = False
    strict_selected_document: bool = False
    selected_document_available: bool = True
    user_accepts_general_fallback: bool = False
    version_change: bool = False
    requires_conversation_context: bool = False

    @field_validator("question_id")
    @classmethod
    def reject_blank_id(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Plan question ID cannot be blank")
        return normalized

    @model_validator(mode="after")
    def validate_intent_and_context(self) -> Self:
        if self.intent is Intent.MULTI_PART_QUESTION:
            raise ValueError("Plan questions must already be atomic")
        if not self.scope_resolved:
            raise ValueError("Capability planning requires resolved scope")
        if self.intent in self.secondary_intents:
            raise ValueError("A plan primary intent cannot also be secondary")
        if len(set(self.secondary_intents)) != len(self.secondary_intents):
            raise ValueError("Plan secondary intents must be unique")
        if len(set(self.subtypes)) != len(self.subtypes):
            raise ValueError("Plan subtypes must be unique")
        for subtype in self.subtypes:
            if self.intent not in INTENT_SUBTYPE_PARENTS[subtype]:
                raise ValueError(
                    f"{subtype.value} is not valid for {self.intent.value}"
                )
        if self.strict_selected_document and not self.has_document_target:
            raise ValueError(
                "Strict selected-document planning requires a document target"
            )
        return self


class PlanRequest(DecisionModel):
    questions: tuple[PlanQuestion, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_question_ids(self) -> Self:
        ids = [question.question_id for question in self.questions]
        if len(ids) != len(set(ids)):
            raise ValueError("Plan question IDs must be unique")
        return self


class PlannedCapability(DecisionModel):
    capability: CapabilityName
    role: CapabilityRole
    stage: CapabilityStage
    activation_conditions: tuple[str, ...] = ()
    question_ids: tuple[str, ...] = ()
    reason: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_conditions(self) -> Self:
        if (
            self.role is CapabilityRole.CONDITIONAL
            and not self.activation_conditions
        ):
            raise ValueError("Conditional capabilities require an activation gate")
        if (
            self.role is not CapabilityRole.CONDITIONAL
            and self.activation_conditions
        ):
            raise ValueError(
                "Only conditional capabilities retain activation gates"
            )
        return self


class ResponseBlueprint(DecisionModel):
    primary_surface: ResponseStrategy
    supporting_cards: tuple[str, ...] = ()
    degraded_fallback: str = Field(min_length=1)
    presentation_modifiers: tuple[str, ...] = ()


class PlanningStage(DecisionModel):
    name: PlanningStageName
    capabilities: tuple[CapabilityName, ...] = ()
    waits_for: tuple[PlanningStageName, ...] = ()


class QuestionPlan(DecisionModel):
    question_id: str = Field(min_length=1)
    intent: Intent
    plan_class: PlanClass
    capabilities: tuple[PlannedCapability, ...]
    skipped_capabilities: tuple[PlannedCapability, ...]
    response_blueprint: ResponseBlueprint
    clarification_question: str | None = None

    @model_validator(mode="after")
    def validate_capability_partition(self) -> Self:
        selected = [item.capability for item in self.capabilities]
        skipped = [item.capability for item in self.skipped_capabilities]
        if len(selected) != len(set(selected)) or len(skipped) != len(set(skipped)):
            raise ValueError("Question-plan capabilities must be unique")
        if set(selected) & set(skipped):
            raise ValueError("Selected and skipped capabilities cannot overlap")
        if set((*selected, *skipped)) != set(CapabilityName):
            raise ValueError("Question plans must decide every capability")
        if (
            self.response_blueprint.primary_surface
            is not INTENT_RESPONSE_STRATEGY[self.intent]
        ):
            raise ValueError("Question response does not match its primary intent")
        return self


class SelectedDecisionPlan(DecisionModel):
    plan_class: PlanClass
    response_strategy: ResponseStrategy
    capabilities: tuple[PlannedCapability, ...]
    skipped_capabilities: tuple[PlannedCapability, ...]
    question_plans: tuple[QuestionPlan, ...]
    stages: tuple[PlanningStage, ...]
    retrieval_plan: RetrievalPlan
    response_blueprint: ResponseBlueprint
    clarification_question: str | None = None

    @model_validator(mode="after")
    def validate_plan_shape(self) -> Self:
        selected = [item.capability for item in self.capabilities]
        skipped = [item.capability for item in self.skipped_capabilities]
        if len(selected) != len(set(selected)) or len(skipped) != len(set(skipped)):
            raise ValueError("Aggregate capabilities must be unique")
        if set(selected) & set(skipped):
            raise ValueError("Aggregate selected and skipped capabilities cannot overlap")
        if set((*selected, *skipped)) != set(CapabilityName):
            raise ValueError("Aggregate plan must decide every capability")
        if tuple(stage.name for stage in self.stages) != PLANNING_STAGES:
            raise ValueError("Planning stages must use the frozen order")
        if self.response_blueprint.primary_surface is not self.response_strategy:
            raise ValueError("Plan response strategy and blueprint must match")
        question_ids = [plan.question_id for plan in self.question_plans]
        if len(question_ids) != len(set(question_ids)):
            raise ValueError("Question-plan IDs must be unique")
        return self


def select_decision_plan(request: PlanRequest) -> SelectedDecisionPlan:
    question_plans = tuple(_question_plan(question) for question in request.questions)
    multi_part = len(question_plans) >= 2
    selected = _aggregate_capabilities(question_plans, skipped=False)
    skipped = _aggregate_capabilities(question_plans, skipped=True)
    plan_class = (
        PlanClass.COMPOSITE
        if multi_part
        else question_plans[0].plan_class
    )
    response_strategy = (
        ResponseStrategy.RESEARCH_REPORT
        if multi_part
        else question_plans[0].response_blueprint.primary_surface
    )
    blueprint = (
        _response_blueprint(
            ResponseStrategy.RESEARCH_REPORT,
            (),
            (),
        )
        if multi_part
        else question_plans[0].response_blueprint
    )
    clarification_questions = tuple(
        plan.clarification_question
        for plan in question_plans
        if plan.clarification_question is not None
    )
    return SelectedDecisionPlan(
        plan_class=plan_class,
        response_strategy=response_strategy,
        capabilities=selected,
        skipped_capabilities=skipped,
        question_plans=question_plans,
        stages=_planning_stages(selected),
        retrieval_plan=_retrieval_plan(selected, request),
        response_blueprint=blueprint,
        clarification_question=(
            clarification_questions[0] if clarification_questions else None
        ),
    )


def _question_plan(question: PlanQuestion) -> QuestionPlan:
    clarification = _document_clarification(question)
    selected: list[PlannedCapability] = []
    skipped: list[PlannedCapability] = []
    for capability in CapabilityName:
        role, condition, reason = _capability_role(
            question,
            capability,
            force_skip=clarification is not None,
        )
        planned = PlannedCapability(
            capability=capability,
            role=role,
            stage=_capability_stage(capability, role),
            activation_conditions=(condition,) if condition is not None else (),
            question_ids=(question.question_id,),
            reason=reason,
        )
        (skipped if role is CapabilityRole.SKIPPED else selected).append(planned)
    return QuestionPlan(
        question_id=question.question_id,
        intent=question.intent,
        plan_class=_plan_class(question, selected),
        capabilities=tuple(selected),
        skipped_capabilities=tuple(skipped),
        response_blueprint=_response_blueprint(
            INTENT_RESPONSE_STRATEGY[question.intent],
            question.secondary_intents,
            question.subtypes,
        ),
        clarification_question=clarification,
    )


def _capability_role(
    question: PlanQuestion,
    capability: CapabilityName,
    *,
    force_skip: bool,
) -> tuple[CapabilityRole, str | None, str]:
    if force_skip:
        return (
            CapabilityRole.SKIPPED,
            None,
            "Document context is unresolved; speculative capability work is forbidden.",
        )
    if (
        capability is CapabilityName.CONVERSATION_CONTEXT
        and question.requires_conversation_context
    ):
        return (
            CapabilityRole.REQUIRED,
            None,
            "Resolved follow-up scope requires conversation context.",
        )
    if (
        question.intent is Intent.DOCUMENT_EXPLANATION
        and not question.selected_document_available
    ):
        if (
            capability is CapabilityName.GENERAL_AI
            and question.user_accepts_general_fallback
        ):
            return (
                CapabilityRole.REQUIRED,
                None,
                "The user accepted degraded general background for an unavailable document.",
            )
        return (
            CapabilityRole.SKIPPED,
            None,
            "Unavailable document content forbids document-specific capability work.",
        )
    base_role = INTENT_CAPABILITY_ROLES[question.intent][capability]
    if capability is CapabilityName.CONVERSATION_CONTEXT:
        return CapabilityRole.SKIPPED, None, "Current turn does not require retained scope."
    if (
        capability is CapabilityName.ENTITY_INDEX
        and question.strict_selected_document
    ):
        return (
            CapabilityRole.SKIPPED,
            None,
            "Strict selected-document work does not require entity-index retrieval.",
        )
    if (
        capability is CapabilityName.GENERAL_AI
        and question.intent is Intent.GENERAL_QUESTION
        and question.has_resolved_entity
    ):
        return (
            CapabilityRole.CONDITIONAL,
            "official_evidence_gate_no_match_or_unavailable",
            "Regulatory context makes General AI wait for official grounding.",
        )
    if base_role is not CapabilityRole.CONDITIONAL:
        return base_role, None, _role_reason(question.intent, capability, base_role)
    return _resolve_conditional(question, capability)


def _resolve_conditional(
    question: PlanQuestion,
    capability: CapabilityName,
) -> tuple[CapabilityRole, str | None, str]:
    if capability is CapabilityName.LIVE_NEWS:
        live = (
            question.intent is Intent.NEWS
            or question.live_eligible
            or question.current_intelligence_requested
        )
        if not live:
            return _ineligible("No live/current scope activates live retrieval.")
        role = (
            CapabilityRole.REQUIRED
            if question.intent in {Intent.NEWS, Intent.CONSULTATION}
            else CapabilityRole.SUPPORTING
        )
        return role, None, "Live/current intent activates a separate live branch."

    if capability is CapabilityName.VERSION_LINEAGE:
        if not question.version_change:
            return _ineligible("No version/change scope activates lineage.")
        role = (
            CapabilityRole.REQUIRED
            if question.intent is Intent.COMPARISON
            else CapabilityRole.SUPPORTING
        )
        return role, None, "Version/change scope activates lineage."

    if capability is CapabilityName.GENERAL_AI:
        if question.intent is Intent.GENERAL_QUESTION and not question.has_resolved_entity:
            return (
                CapabilityRole.REQUIRED,
                None,
                "Explicit non-regulatory general work selects General AI.",
            )
        if question.intent is Intent.SUMMARIZATION:
            if question.general_source_set:
                return (
                    CapabilityRole.REQUIRED,
                    None,
                    "A general source set requires General AI summarization.",
                )
            return _ineligible(
                "Official/selected-source summarization does not use General AI knowledge."
            )
        if question.intent is Intent.DOCUMENT_EXPLANATION:
            if not question.user_accepts_general_fallback:
                return _ineligible(
                    "Document explanation cannot use General AI without user acceptance."
                )
            condition = "document_unavailable_and_user_accepts_general_fallback"
        elif question.intent is Intent.COMPARISON:
            condition = "unsupported_side_after_official_evidence_gate"
        elif question.intent is Intent.NEWS:
            condition = "background_only_after_official_and_live_evidence_gates"
        elif question.intent is Intent.COMPLIANCE_QUESTION:
            condition = "healthy_official_no_match_only"
        else:
            condition = "official_evidence_gate_no_match_or_unavailable"
        return (
            CapabilityRole.CONDITIONAL,
            condition,
            "General AI waits for its declared evidence gate.",
        )

    if question.intent is Intent.GENERAL_QUESTION:
        eligible = question.has_resolved_entity
        if capability is CapabilityName.GLOSSARY:
            eligible = eligible and question.has_term_like_entity
        if capability is CapabilityName.DOCUMENT_METADATA:
            eligible = question.has_document_target
        if not eligible:
            return _ineligible("No regulatory target makes this branch eligible.")
        return (
            CapabilityRole.SUPPORTING,
            None,
            "Resolved regulatory context activates supporting grounding.",
        )

    if question.intent is Intent.SUMMARIZATION:
        if capability is CapabilityName.ENTITY_INDEX:
            eligible = question.has_resolved_entity
        elif capability in {
            CapabilityName.INTERNAL_DOCUMENT_SEARCH,
            CapabilityName.DOCUMENT_METADATA,
        }:
            eligible = question.has_known_sources or question.has_document_target
        else:
            eligible = question.live_eligible
        if not eligible:
            return _ineligible("The summarization source set does not activate this branch.")
        role = (
            CapabilityRole.REQUIRED
            if capability is CapabilityName.INTERNAL_DOCUMENT_SEARCH
            else CapabilityRole.SUPPORTING
        )
        return role, None, "Known source type activates this summarization branch."

    return _ineligible("The conditional capability activation rule was not met.")


def _ineligible(reason: str) -> tuple[CapabilityRole, None, str]:
    return CapabilityRole.SKIPPED, None, reason


def _role_reason(
    intent: Intent,
    capability: CapabilityName,
    role: CapabilityRole,
) -> str:
    return (
        f"{capability.value} is {role.value} for the frozen "
        f"{intent.value} routing row."
    )


def _plan_class(
    question: PlanQuestion,
    selected: list[PlannedCapability],
) -> PlanClass:
    if any(
        capability.capability is CapabilityName.LIVE_NEWS
        for capability in selected
    ):
        return PlanClass.LIVE_COMBINED
    if question.historical_scope or question.intent in {
        Intent.TIMELINE,
        Intent.AMENDMENT,
        Intent.COMPARISON,
    }:
        return PlanClass.DEEP_RESEARCH
    if question.exact_match and question.intent in {
        Intent.DEFINITION,
        Intent.ENTITY_LOOKUP,
        Intent.REGULATION_LOOKUP,
    }:
        return PlanClass.FAST_EXACT
    if question.intent is Intent.GENERAL_QUESTION:
        return PlanClass.FAST_EXACT
    return PlanClass.FOCUSED_GROUNDED


def _aggregate_capabilities(
    plans: tuple[QuestionPlan, ...],
    *,
    skipped: bool,
) -> tuple[PlannedCapability, ...]:
    result = []
    for capability in CapabilityName:
        matches = tuple(
            planned
            for plan in plans
            for planned in (
                plan.skipped_capabilities if skipped else plan.capabilities
            )
            if planned.capability is capability
        )
        if not matches:
            continue
        if skipped and any(
            selected.capability is capability
            for plan in plans
            for selected in plan.capabilities
        ):
            continue
        role = (
            CapabilityRole.SKIPPED
            if skipped
            else min(
                (match.role for match in matches),
                key=_role_priority,
            )
        )
        conditions = tuple(
            dict.fromkeys(
                condition
                for match in matches
                for condition in match.activation_conditions
            )
        )
        if role is not CapabilityRole.CONDITIONAL:
            conditions = ()
        result.append(
            PlannedCapability(
                capability=capability,
                role=role,
                stage=_capability_stage(capability, role),
                activation_conditions=conditions,
                question_ids=tuple(
                    dict.fromkeys(
                        question_id
                        for match in matches
                        for question_id in match.question_ids
                    )
                ),
                reason=(
                    "Deduplicated across atomic questions."
                    if len(plans) > 1
                    else matches[0].reason
                ),
            )
        )
    return tuple(result)


def _role_priority(role: CapabilityRole) -> int:
    return {
        CapabilityRole.REQUIRED: 0,
        CapabilityRole.SUPPORTING: 1,
        CapabilityRole.CONDITIONAL: 2,
        CapabilityRole.SKIPPED: 3,
    }[role]


def _capability_stage(
    capability: CapabilityName,
    role: CapabilityRole,
) -> CapabilityStage:
    if (
        capability is CapabilityName.GENERAL_AI
        and role is CapabilityRole.REQUIRED
    ):
        return CapabilityStage.INTENT_EVIDENCE
    return CAPABILITY_STAGES[capability]


def _planning_stages(
    capabilities: tuple[PlannedCapability, ...],
) -> tuple[PlanningStage, ...]:
    by_stage = {
        stage: tuple(
            planned.capability
            for planned in capabilities
            if planned.stage is stage
        )
        for stage in CapabilityStage
    }
    return (
        PlanningStage(
            name=PlanningStageName.RESOLVE_CHEAPLY,
            capabilities=by_stage[CapabilityStage.CHEAP_RESOLUTION],
        ),
        PlanningStage(
            name=PlanningStageName.RUN_INTENT_EVIDENCE,
            capabilities=by_stage[CapabilityStage.INTENT_EVIDENCE],
            waits_for=(PlanningStageName.RESOLVE_CHEAPLY,),
        ),
        PlanningStage(
            name=PlanningStageName.ASSESS_SUFFICIENCY,
            waits_for=(PlanningStageName.RUN_INTENT_EVIDENCE,),
        ),
        PlanningStage(
            name=PlanningStageName.ACTIVATE_CONDITIONAL_FALLBACKS,
            capabilities=by_stage[CapabilityStage.CONDITIONAL_FALLBACK],
            waits_for=(PlanningStageName.ASSESS_SUFFICIENCY,),
        ),
        PlanningStage(
            name=PlanningStageName.SELECT_RESPONSE_AND_VERIFICATION,
            waits_for=(
                PlanningStageName.ASSESS_SUFFICIENCY,
                PlanningStageName.ACTIVATE_CONDITIONAL_FALLBACKS,
            ),
        ),
    )


def _retrieval_plan(
    capabilities: tuple[PlannedCapability, ...],
    request: PlanRequest,
) -> RetrievalPlan:
    selected = {planned.capability for planned in capabilities}
    planned_by_capability = {
        planned.capability: planned for planned in capabilities
    }
    cheap = tuple(
        capability
        for capability in CapabilityName
        if capability in selected
        and planned_by_capability[capability].stage
        is CapabilityStage.CHEAP_RESOLUTION
    )
    evidence = tuple(
        capability
        for capability in CapabilityName
        if capability in selected
        and planned_by_capability[capability].stage
        is CapabilityStage.INTENT_EVIDENCE
    )
    gates = []
    fallbacks = []
    if CapabilityName.INTERNAL_DOCUMENT_SEARCH in selected:
        gates.append("official_evidence_sufficiency")
        fallbacks.append(
            "manual_document_search_if_internal_unavailable_or_ambiguity_remains"
        )
    if CapabilityName.LIVE_NEWS in selected:
        gates.append("live_evidence_coverage")
        fallbacks.append("internal_recent_documents_if_live_unavailable")
    if any(question.strict_selected_document for question in request.questions):
        gates.append("selected_document_readability")
    general_ai = next(
        (
            capability
            for capability in capabilities
            if capability.capability is CapabilityName.GENERAL_AI
        ),
        None,
    )
    if (
        general_ai is not None
        and general_ai.role is CapabilityRole.CONDITIONAL
    ):
        gates.append("general_ai_activation_gate")
        fallbacks.append("general_ai_only_after_declared_evidence_gate")
    if CapabilityName.KNOWLEDGE_GRAPH in selected:
        fallbacks.append("document_relationship_extraction_if_graph_unavailable")
    if len(request.questions) > 1:
        gates.append("per_atomic_question_sufficiency")
    return RetrievalPlan(
        parallel_groups=tuple(group for group in (cheap, evidence) if group),
        evidence_gates=tuple(gates),
        conditional_fallbacks=tuple(fallbacks),
    )


def _document_clarification(question: PlanQuestion) -> str | None:
    if question.intent is not Intent.DOCUMENT_EXPLANATION:
        return None
    if not question.has_document_target:
        return "Which document or passage should I explain?"
    if (
        not question.selected_document_available
        and not question.user_accepts_general_fallback
    ):
        return "Which document or passage should I explain?"
    return None


def _response_blueprint(
    strategy: ResponseStrategy,
    secondary_intents: tuple[Intent, ...],
    subtypes: tuple[IntentSubtype, ...],
) -> ResponseBlueprint:
    supporting, fallback = RESPONSE_BLUEPRINTS[strategy]
    secondary_cards = tuple(
        INTENT_RESPONSE_STRATEGY[intent].value
        for intent in secondary_intents
        if INTENT_RESPONSE_STRATEGY[intent] is not strategy
    )
    return ResponseBlueprint(
        primary_surface=strategy,
        supporting_cards=tuple(dict.fromkeys((*supporting, *secondary_cards))),
        degraded_fallback=fallback,
        presentation_modifiers=tuple(subtype.value for subtype in subtypes),
    )


RESPONSE_BLUEPRINTS: dict[
    ResponseStrategy,
    tuple[tuple[str, ...], str],
] = {
    ResponseStrategy.DEFINITION_CARD: (
        ("official_source", "related_terms"),
        "mode_2_definition_card",
    ),
    ResponseStrategy.ENTITY_INTELLIGENCE_PAGE: (
        (
            "definition",
            "timeline",
            "official_documents",
            "stakeholders",
            "obligations",
            "related_regulations",
        ),
        "partial_entity_page",
    ),
    ResponseStrategy.OFFICIAL_DOCUMENTS_OVERVIEW: (
        ("source", "amendment", "related_regulation"),
        "search_guidance_or_general_background",
    ),
    ResponseStrategy.DEADLINE_CARDS_TIMELINE: (
        ("official_source", "stakeholder", "timeline"),
        "retrieved_dates_with_verification_warning",
    ),
    ResponseStrategy.STAKEHOLDER_CARDS: (
        ("obligations", "related_regulations"),
        "document_derived_roles_or_qualified_explanation",
    ),
    ResponseStrategy.COMPARISON_TABLE: (
        ("source", "confidence_coverage"),
        "partial_comparison_with_not_established_cells",
    ),
    ResponseStrategy.LATEST_INTELLIGENCE: (
        ("news", "official_source", "timeline"),
        "internal_only_or_general_background",
    ),
    ResponseStrategy.TIMELINE: (
        ("amendment", "source", "confidence"),
        "partial_timeline_with_missing_range",
    ),
    ResponseStrategy.COMPLIANCE_CHECKLIST: (
        ("obligation", "deadline", "source", "applicability_assumptions"),
        "qualified_non_authoritative_education_checklist",
    ),
    ResponseStrategy.EXECUTIVE_SUMMARY: (
        ("source_list", "key_dates", "obligations"),
        "extractive_structured_source_view",
    ),
    ResponseStrategy.DOCUMENT_EXPLANATION: (
        ("definition", "source_excerpt", "related_provisions"),
        "request_document_or_passage",
    ),
    ResponseStrategy.AMENDMENT_CARDS: (
        ("comparison", "timeline", "official_source"),
        "known_documents_without_unsupported_change_summary",
    ),
    ResponseStrategy.CONSULTATION_DEADLINE_CARDS: (
        ("deadline", "live_news", "official_source"),
        "internal_consultation_documents_or_no_live_results",
    ),
    ResponseStrategy.CONVERSATION: (
        ("optional_definitions", "related_entities"),
        "short_general_ai_unavailable_state",
    ),
    ResponseStrategy.RESEARCH_REPORT: (
        ("coverage_summary", "intent_specific_sections"),
        "partial_report_with_section_failures",
    ),
}
