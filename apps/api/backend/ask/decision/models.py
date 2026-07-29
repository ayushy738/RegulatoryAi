from __future__ import annotations

import json
from collections.abc import Hashable, Iterable
from datetime import datetime
from enum import StrEnum
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

DECISION_SCHEMA_VERSION = "1"
DECISION_POLICY_VERSION = "ask-ai-decision-v1"


class Intent(StrEnum):
    DEFINITION = "definition"
    ENTITY_LOOKUP = "entity_lookup"
    REGULATION_LOOKUP = "regulation_lookup"
    DEADLINE = "deadline"
    STAKEHOLDER = "stakeholder"
    COMPARISON = "comparison"
    NEWS = "news"
    TIMELINE = "timeline"
    COMPLIANCE_QUESTION = "compliance_question"
    SUMMARIZATION = "summarization"
    DOCUMENT_EXPLANATION = "document_explanation"
    AMENDMENT = "amendment"
    CONSULTATION = "consultation"
    GENERAL_QUESTION = "general_question"
    MULTI_PART_QUESTION = "multi_part_question"


class IntentSubtype(StrEnum):
    REGULATOR_LOOKUP = "regulator_lookup"
    OBLIGATION_DISCOVERY = "obligation_discovery"
    VERSION_COMPARISON = "version_comparison"
    BEGINNER_EXPLANATION = "beginner_explanation"
    OFFICIAL_DOCUMENT_SEARCH = "official_document_search"


INTENT_SUBTYPE_PARENTS = {
    IntentSubtype.REGULATOR_LOOKUP: (Intent.STAKEHOLDER,),
    IntentSubtype.OBLIGATION_DISCOVERY: (Intent.COMPLIANCE_QUESTION,),
    IntentSubtype.VERSION_COMPARISON: (Intent.COMPARISON,),
    IntentSubtype.BEGINNER_EXPLANATION: (
        Intent.DEFINITION,
        Intent.DOCUMENT_EXPLANATION,
    ),
    IntentSubtype.OFFICIAL_DOCUMENT_SEARCH: (Intent.REGULATION_LOOKUP,),
}


class IntentConfidenceBand(StrEnum):
    CERTAIN = "certain"
    STRONG = "strong"
    BOUNDED = "bounded"
    AMBIGUOUS = "ambiguous"


class EntityClass(StrEnum):
    REGULATORY_CONCEPT = "regulatory_concept"
    REGULATION_FAMILY = "regulation_family"
    LEGAL_INSTRUMENT = "legal_instrument"
    REGULATOR = "regulator"
    SCHEME_OR_POLICY = "scheme_or_policy"
    MARKET_OR_COMMODITY = "market_or_commodity"
    STAKEHOLDER = "stakeholder"
    OBLIGATION = "obligation"
    DOCUMENT = "document"
    JURISDICTION = "jurisdiction"
    STATUS = "status"


class TimeDimension(StrEnum):
    PUBLICATION_OR_ISSUE = "publication_or_issue"
    EFFECTIVE = "effective"
    COMPLIANCE_DEADLINE = "compliance_deadline"
    CONSULTATION = "consultation"
    EVENT = "event"
    VALIDITY_PERIOD = "validity_period"
    DOCUMENT_VERSION = "document_version"
    RETRIEVAL = "retrieval"


class KnowledgeMode(StrEnum):
    GROUNDED_REGULATORY = "grounded_regulatory"
    GENERAL_AI = "general_ai"
    LIVE_INTELLIGENCE = "live_intelligence"


class CapabilityName(StrEnum):
    GLOSSARY = "glossary"
    ENTITY_INDEX = "entity_index"
    INTERNAL_DOCUMENT_SEARCH = "internal_document_search"
    DOCUMENT_METADATA = "document_metadata"
    KNOWLEDGE_GRAPH = "knowledge_graph"
    VERSION_LINEAGE = "version_lineage"
    LIVE_NEWS = "live_news"
    GENERAL_AI = "general_ai"
    CONVERSATION_CONTEXT = "conversation_context"


class CapabilityRole(StrEnum):
    REQUIRED = "required"
    SUPPORTING = "supporting"
    CONDITIONAL = "conditional"
    SKIPPED = "skipped"


class CapabilityOutcome(StrEnum):
    SUCCESS = "success"
    PARTIAL = "partial"
    NO_MATCH = "no_match"
    UNAVAILABLE = "unavailable"
    TIMED_OUT = "timed_out"
    CONTRADICTORY = "contradictory"
    SKIPPED = "skipped"


class ResponseStrategy(StrEnum):
    DEFINITION_CARD = "definition_card"
    ENTITY_INTELLIGENCE_PAGE = "entity_intelligence_page"
    OFFICIAL_DOCUMENTS_OVERVIEW = "official_documents_overview"
    DEADLINE_CARDS_TIMELINE = "deadline_cards_timeline"
    STAKEHOLDER_CARDS = "stakeholder_cards"
    COMPARISON_TABLE = "comparison_table"
    LATEST_INTELLIGENCE = "latest_intelligence"
    TIMELINE = "timeline"
    COMPLIANCE_CHECKLIST = "compliance_checklist"
    EXECUTIVE_SUMMARY = "executive_summary"
    DOCUMENT_EXPLANATION = "document_explanation"
    AMENDMENT_CARDS = "amendment_cards"
    CONSULTATION_DEADLINE_CARDS = "consultation_deadline_cards"
    CONVERSATION = "conversation"
    RESEARCH_REPORT = "research_report"


class ConfidenceLabel(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    UNKNOWN = "unknown"


class TerminalProductState(StrEnum):
    COMPLETE = "complete"
    DEGRADED_COMPLETE = "degraded_complete"
    CLARIFICATION_RESULT = "clarification_result"


class DecisionModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class DecisionRequest(DecisionModel):
    query: str = Field(min_length=1)
    selected_document_id: int | None = None
    selected_card_id: str | None = None
    selected_entity_id: str | None = None
    highlighted_text: str | None = None
    user_timezone: str

    @field_validator("query", "user_timezone")
    @classmethod
    def reject_blank_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Decision request text cannot be blank")
        return normalized


class ConversationScope(DecisionModel):
    entity_ids: tuple[str, ...] = ()
    jurisdiction: str | None = None
    stakeholder: str | None = None
    time_scope: str | None = None
    exclusions: tuple[str, ...] = ()


class IntentDecision(DecisionModel):
    primary: Intent
    secondary: tuple[Intent, ...] = ()
    subtypes: tuple[IntentSubtype, ...] = ()
    confidence: float = Field(ge=0, le=1)
    confidence_band: IntentConfidenceBand
    alternatives: tuple[Intent, ...] = ()
    reasons: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_distinct_intents(self) -> Self:
        if self.primary in self.secondary:
            raise ValueError("The primary intent cannot also be secondary")
        if len(set(self.secondary)) != len(self.secondary):
            raise ValueError("Secondary intents must be unique")
        return self


class AtomicQuestion(DecisionModel):
    id: str = Field(min_length=1)
    question: str = Field(min_length=1)
    intent: Intent
    secondary_intents: tuple[Intent, ...] = ()
    subtypes: tuple[IntentSubtype, ...] = ()
    inherited_scope: ConversationScope = Field(default_factory=ConversationScope)

    @field_validator("id", "question")
    @classmethod
    def reject_blank_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Atomic question text cannot be blank")
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


class EntityDecision(DecisionModel):
    mention: str = Field(min_length=1)
    canonical_id: str | None = None
    canonical_name: str | None = None
    entity_class: EntityClass
    aliases: tuple[str, ...] = ()
    jurisdiction: str | None = None
    confidence: float = Field(ge=0, le=1)
    assumed: bool = False
    reason: str | None = None


class TimeInterpretation(DecisionModel):
    dimension: TimeDimension | None = None
    start_at: datetime | None = None
    end_at: datetime | None = None
    status_filters: tuple[str, ...] = ()
    user_timezone: str
    source_expression: str | None = None
    assumed: bool = False
    end_exclusive: bool = True
    precedence_rule: str | None = None
    freshness_requirements: tuple[str, ...] = ()
    live_eligible: bool = False

    @model_validator(mode="after")
    def validate_range(self) -> Self:
        for boundary in (self.start_at, self.end_at):
            if (
                boundary is not None
                and (boundary.tzinfo is None or boundary.utcoffset() is None)
            ):
                raise ValueError("Normalized time boundaries must be timezone-aware")
        if (
            self.start_at is not None
            and self.end_at is not None
            and self.end_at < self.start_at
        ):
            raise ValueError("The normalized time range is reversed")
        return self


class CapabilityDecision(DecisionModel):
    capability: CapabilityName
    role: CapabilityRole
    reason: str = Field(min_length=1)


class RetrievalPlan(DecisionModel):
    parallel_groups: tuple[tuple[CapabilityName, ...], ...] = ()
    evidence_gates: tuple[str, ...] = ()
    conditional_fallbacks: tuple[str, ...] = ()


class CapabilityResult(DecisionModel):
    capability: CapabilityName
    outcome: CapabilityOutcome
    reason: str | None = None


class ModeAssignment(DecisionModel):
    section_key: str = Field(min_length=1)
    mode: KnowledgeMode
    reason: str = Field(min_length=1)


class EvidenceAssessment(DecisionModel):
    authority: float | None = Field(default=None, ge=0, le=100)
    relevance: float | None = Field(default=None, ge=0, le=100)
    coverage: float | None = Field(default=None, ge=0, le=100)
    agreement: float | None = Field(default=None, ge=0, le=100)
    freshness: float | None = Field(default=None, ge=0, le=100)
    scope_fit: float | None = Field(default=None, ge=0, le=100)
    reasons: tuple[str, ...] = ()


class ConfidenceAssessment(DecisionModel):
    claim_labels: dict[str, ConfidenceLabel] = Field(default_factory=dict)
    section_labels: dict[str, ConfidenceLabel] = Field(default_factory=dict)
    overall_label: ConfidenceLabel = ConfidenceLabel.UNKNOWN
    reasons: tuple[str, ...] = ()


class DegradationAssessment(DecisionModel):
    missing_capabilities: tuple[CapabilityName, ...] = ()
    retained_output: tuple[str, ...] = ()
    reasons: tuple[str, ...] = ()


class DecisionExplanation(DecisionModel):
    interpretation: tuple[str, ...] = ()
    source_selection: tuple[str, ...] = ()
    mode_selection: tuple[str, ...] = ()
    confidence: tuple[str, ...] = ()
    gaps: tuple[str, ...] = ()


class DecisionRecord(DecisionModel):
    schema_version: Literal["1"] = DECISION_SCHEMA_VERSION
    policy_version: str = Field(min_length=1)
    request: DecisionRequest
    conversation_scope: ConversationScope
    intent: IntentDecision
    atomic_questions: tuple[AtomicQuestion, ...] = ()
    entities: tuple[EntityDecision, ...] = ()
    time_interpretation: TimeInterpretation
    assumptions: tuple[str, ...] = ()
    capabilities: tuple[CapabilityDecision, ...] = ()
    retrieval_plan: RetrievalPlan = Field(default_factory=RetrievalPlan)
    capability_outcomes: tuple[CapabilityResult, ...] = ()
    knowledge_modes: tuple[ModeAssignment, ...] = ()
    response_strategy: ResponseStrategy
    evidence_assessment: EvidenceAssessment = Field(
        default_factory=EvidenceAssessment
    )
    confidence: ConfidenceAssessment = Field(default_factory=ConfidenceAssessment)
    degradation: DegradationAssessment = Field(
        default_factory=DegradationAssessment
    )
    explanation: DecisionExplanation = Field(default_factory=DecisionExplanation)
    terminal_state: TerminalProductState | None = None

    @model_validator(mode="after")
    def validate_unique_record_keys(self) -> Self:
        _require_unique(
            (question.id for question in self.atomic_questions),
            "Atomic question IDs",
        )
        _require_unique(
            (decision.capability for decision in self.capabilities),
            "Capability decisions",
        )
        _require_unique(
            (result.capability for result in self.capability_outcomes),
            "Capability outcomes",
        )
        _require_unique(
            (assignment.section_key for assignment in self.knowledge_modes),
            "Knowledge-mode section keys",
        )
        return self


def decision_record_json(record: DecisionRecord) -> str:
    return json.dumps(
        record.model_dump(mode="json"),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def _require_unique(values: Iterable[Hashable], label: str) -> None:
    materialized = tuple(values)
    if len(materialized) != len(set(materialized)):
        raise ValueError(f"{label} must be unique")
