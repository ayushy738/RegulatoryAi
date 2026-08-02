from __future__ import annotations

from typing import Literal

from pydantic import Field

from backend.ask.decision.models import (
    DecisionModel,
    Intent,
    IntentConfidenceBand,
    IntentSubtype,
    ResponseStrategy,
)

INTENT_PRECEDENCE = (
    "interaction_context",
    "multi_part",
    "compliance",
    "comparison",
    "amendment_or_version_change",
    "deadline",
    "timeline",
    "consultation",
    "live_recency",
    "named_regulation",
    "definition",
    "bare_entity",
    "stakeholder",
    "known_result_summarization",
    "general_question",
)

INTENT_RESPONSE_STRATEGY = {
    Intent.DEFINITION: ResponseStrategy.DEFINITION_CARD,
    Intent.ENTITY_LOOKUP: ResponseStrategy.ENTITY_INTELLIGENCE_PAGE,
    Intent.REGULATION_LOOKUP: ResponseStrategy.OFFICIAL_DOCUMENTS_OVERVIEW,
    Intent.DEADLINE: ResponseStrategy.DEADLINE_CARDS_TIMELINE,
    Intent.STAKEHOLDER: ResponseStrategy.STAKEHOLDER_CARDS,
    Intent.COMPARISON: ResponseStrategy.COMPARISON_TABLE,
    Intent.NEWS: ResponseStrategy.LATEST_INTELLIGENCE,
    Intent.TIMELINE: ResponseStrategy.TIMELINE,
    Intent.COMPLIANCE_QUESTION: ResponseStrategy.COMPLIANCE_CHECKLIST,
    Intent.SUMMARIZATION: ResponseStrategy.EXECUTIVE_SUMMARY,
    Intent.DOCUMENT_EXPLANATION: ResponseStrategy.DOCUMENT_EXPLANATION,
    Intent.AMENDMENT: ResponseStrategy.AMENDMENT_CARDS,
    Intent.CONSULTATION: ResponseStrategy.CONSULTATION_DEADLINE_CARDS,
    Intent.GENERAL_QUESTION: ResponseStrategy.CONVERSATION,
    Intent.MULTI_PART_QUESTION: ResponseStrategy.RESEARCH_REPORT,
}

class IntentSignals(DecisionModel):
    interaction_action: Literal["explain", "summarize", "pronoun"] | None = None
    has_selected_referent: bool = False
    atomic_intents: tuple[Intent, ...] = ()
    explicit_compliance: bool = False
    explicit_comparison: bool = False
    resolved_comparison_operands: int = Field(default=0, ge=0)
    explicit_amendment: bool = False
    explicit_version_change: bool = False
    explicit_side_by_side_version_change: bool = False
    explicit_deadline: bool = False
    consultation_comment_deadline: bool = False
    explicit_timeline: bool = False
    explicit_consultation: bool = False
    explicit_live_recency: bool = False
    live_object_intent: (
        Literal["deadline", "amendment", "compliance_question"] | None
    ) = None
    named_regulation: bool = False
    explicit_definition: bool = False
    bare_resolved_entity: bool = False
    responsible_party_question: bool = False
    known_result_summarization: bool = False


class SelectedIntent(DecisionModel):
    primary: Intent
    secondary: tuple[Intent, ...] = ()
    subtypes: tuple[IntentSubtype, ...] = ()
    precedence_rule: str
    response_strategy: ResponseStrategy


def classify_intent_confidence(
    score: float,
    *,
    competing_gap: float,
    material_collision: bool,
    shared_safe_scope: bool,
) -> IntentConfidenceBand:
    if not 0 <= score <= 1:
        raise ValueError("Intent confidence must be between 0 and 1")
    if not 0 <= competing_gap <= 1:
        raise ValueError("The competing-intent gap must be between 0 and 1")
    if score >= 0.90 and competing_gap >= 0.10 and not material_collision:
        return IntentConfidenceBand.CERTAIN
    if 0.75 <= score < 0.90 and not material_collision:
        return IntentConfidenceBand.STRONG
    if 0.55 <= score < 0.75 and shared_safe_scope and not material_collision:
        return IntentConfidenceBand.BOUNDED
    return IntentConfidenceBand.AMBIGUOUS


def select_intent(signals: IntentSignals) -> SelectedIntent:
    if signals.has_selected_referent and signals.interaction_action is not None:
        intent = (
            Intent.DOCUMENT_EXPLANATION
            if signals.interaction_action in {"explain", "pronoun"}
            else Intent.SUMMARIZATION
        )
        return _selected(intent, "interaction_context")

    if len(signals.atomic_intents) >= 2:
        secondary = _unique(signals.atomic_intents)
        return _selected(
            Intent.MULTI_PART_QUESTION,
            "multi_part",
            secondary=secondary,
        )

    if signals.explicit_compliance:
        secondary = _unique(
            (
                *((Intent.DEADLINE,) if signals.explicit_deadline else ()),
                *((Intent.NEWS,) if signals.explicit_live_recency else ()),
            )
        )
        return _selected(
            Intent.COMPLIANCE_QUESTION,
            "compliance",
            secondary=secondary,
        )

    if signals.explicit_comparison and signals.resolved_comparison_operands >= 2:
        subtypes = (
            (IntentSubtype.VERSION_COMPARISON,)
            if signals.explicit_side_by_side_version_change
            else ()
        )
        return _selected(Intent.COMPARISON, "comparison", subtypes=subtypes)

    if signals.explicit_side_by_side_version_change:
        return _selected(
            Intent.COMPARISON,
            "amendment_or_version_change",
            subtypes=(IntentSubtype.VERSION_COMPARISON,),
        )

    if signals.explicit_amendment or signals.explicit_version_change:
        secondary = (Intent.NEWS,) if signals.explicit_live_recency else ()
        return _selected(
            Intent.AMENDMENT,
            "amendment_or_version_change",
            secondary=secondary,
        )

    if signals.explicit_deadline:
        secondary = (
            (Intent.CONSULTATION,)
            if signals.consultation_comment_deadline
            else ()
        )
        return _selected(Intent.DEADLINE, "deadline", secondary=secondary)

    if signals.explicit_timeline:
        return _selected(Intent.TIMELINE, "timeline")

    if signals.explicit_consultation:
        return _selected(Intent.CONSULTATION, "consultation")

    if signals.explicit_live_recency:
        if signals.live_object_intent is not None:
            primary = Intent(signals.live_object_intent)
            return _selected(primary, "live_recency", secondary=(Intent.NEWS,))
        return _selected(Intent.NEWS, "live_recency")

    if signals.named_regulation:
        return _selected(Intent.REGULATION_LOOKUP, "named_regulation")

    if signals.explicit_definition:
        return _selected(Intent.DEFINITION, "definition")

    if signals.bare_resolved_entity:
        return _selected(Intent.ENTITY_LOOKUP, "bare_entity")

    if signals.responsible_party_question:
        return _selected(
            Intent.STAKEHOLDER,
            "stakeholder",
            subtypes=(IntentSubtype.REGULATOR_LOOKUP,),
        )

    if signals.known_result_summarization:
        return _selected(Intent.SUMMARIZATION, "known_result_summarization")

    return _selected(Intent.GENERAL_QUESTION, "general_question")


def _selected(
    primary: Intent,
    precedence_rule: str,
    *,
    secondary: tuple[Intent, ...] = (),
    subtypes: tuple[IntentSubtype, ...] = (),
) -> SelectedIntent:
    return SelectedIntent(
        primary=primary,
        secondary=secondary,
        subtypes=subtypes,
        precedence_rule=precedence_rule,
        response_strategy=INTENT_RESPONSE_STRATEGY[primary],
    )


def _unique(intents: tuple[Intent, ...]) -> tuple[Intent, ...]:
    return tuple(dict.fromkeys(intents))
