from __future__ import annotations

import hashlib
import re
from enum import StrEnum
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from backend.ask.decision.models import ConfidenceLabel, Intent, ResponseStrategy
from backend.ask.orchestration.contracts import (
    CapabilityTerminalState,
    FollowUpCandidate,
    FollowUpCandidatesPayload,
    OrchestratorCapability,
)

FOLLOW_UP_SCHEMA_VERSION = "1"
FOLLOW_UP_POLICY_VERSION = "ask-ai-follow-up-v1"
_SPACE = re.compile(r"\s+")


class FollowUpModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        strict=True,
        str_strip_whitespace=True,
    )


class FollowUpCategory(StrEnum):
    RESOLVE = "resolve"
    VERIFY = "verify"
    COMPLIANCE = "compliance"
    CHANGE = "change"
    EXPLORE = "explore"
    LIVE = "live"
    UNDERSTAND = "understand"


class FollowUpGapKind(StrEnum):
    JURISDICTION = "jurisdiction"
    STAKEHOLDER = "stakeholder"
    OFFICIAL_EVIDENCE = "official_evidence"
    CURRENT_STATUS = "current_status"
    DEADLINE = "deadline"
    COMPARISON_OPERAND = "comparison_operand"
    HISTORICAL_RANGE = "historical_range"


class FollowUpStatus(StrEnum):
    GENERATED = "generated"
    EMPTY = "empty"


class DegradedCapability(FollowUpModel):
    capability: OrchestratorCapability
    state: CapabilityTerminalState

    @model_validator(mode="after")
    def validate_state(self) -> Self:
        if self.state in {
            CapabilityTerminalState.SATISFIED,
            CapabilityTerminalState.NO_MATCH,
            CapabilityTerminalState.SKIPPED,
            CapabilityTerminalState.SUPERSEDED,
        }:
            raise ValueError("Degraded capability requires a degraded outcome")
        return self


class FollowUpScope(FollowUpModel):
    entity_id: str | None = Field(default=None, max_length=200)
    entity_name: str | None = Field(default=None, max_length=500)
    jurisdiction: str | None = Field(default=None, max_length=500)
    stakeholder: str | None = Field(default=None, max_length=500)
    selected_document_title: str | None = Field(default=None, max_length=1_000)
    comparison_operands: tuple[str, ...] = ()
    related_entities: tuple[str, ...] = ()

    @field_validator(
        "entity_id",
        "entity_name",
        "jurisdiction",
        "stakeholder",
        "selected_document_title",
    )
    @classmethod
    def validate_optional_label(cls, value: str | None) -> str | None:
        if value is not None and _has_control(value):
            raise ValueError("Follow-up scope labels cannot contain control characters")
        return value

    @field_validator("comparison_operands", "related_entities")
    @classmethod
    def validate_unique_names(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(item.strip() for item in value)
        if (
            any(not item or _has_control(item) for item in normalized)
            or len(normalized) != len(set(normalized))
        ):
            raise ValueError("Follow-up scope names must be unique and nonblank")
        return normalized

    @model_validator(mode="after")
    def validate_entity(self) -> Self:
        if (self.entity_id is None) != (self.entity_name is None):
            raise ValueError("Resolved entity ID and name must appear together")
        return self


class FollowUpRequest(FollowUpModel):
    schema_version: Literal["1"] = FOLLOW_UP_SCHEMA_VERSION
    policy_version: Literal["ask-ai-follow-up-v1"] = FOLLOW_UP_POLICY_VERSION
    scope: FollowUpScope
    completed_intents: tuple[Intent, ...]
    confidence_label: ConfidenceLabel
    gaps: tuple[FollowUpGapKind, ...] = ()
    assumptions: tuple[FollowUpGapKind, ...] = ()
    prior_questions: tuple[str, ...] = ()
    prior_suggestions: tuple[str, ...] = ()
    eligible_capabilities: tuple[OrchestratorCapability, ...]
    degraded_capabilities: tuple[DegradedCapability, ...] = ()
    optional_budget_available: bool = True

    @field_validator(
        "completed_intents",
        "gaps",
        "assumptions",
        "eligible_capabilities",
    )
    @classmethod
    def validate_unique_enums(cls, value: tuple[object, ...]) -> tuple[object, ...]:
        if len(value) != len(set(value)):
            raise ValueError("Follow-up decision inputs must be unique")
        return value

    @field_validator("prior_questions", "prior_suggestions")
    @classmethod
    def validate_prior_text(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(_normalize(item) for item in value)
        if any(not item for item in normalized) or len(normalized) != len(set(normalized)):
            raise ValueError("Prior follow-up text must be unique and nonblank")
        return normalized

    @model_validator(mode="after")
    def validate_degraded_capabilities(self) -> Self:
        capability_ids = tuple(item.capability for item in self.degraded_capabilities)
        if len(capability_ids) != len(set(capability_ids)):
            raise ValueError("Degraded capabilities must be unique")
        if not set(capability_ids).issubset(self.eligible_capabilities):
            raise ValueError("Degraded capabilities must have been eligible")
        return self


class FollowUpSuggestion(FollowUpModel):
    suggestion_id: str = Field(pattern=r"^follow_up_[0-9a-f]{32}$")
    category: FollowUpCategory
    preview_label: str = Field(min_length=1, max_length=100)
    question: str = Field(min_length=1, max_length=1_000)
    expected_response_strategy: ResponseStrategy
    reason: str = Field(min_length=1, max_length=1_000)
    requires_fresh_retrieval: bool
    capability: OrchestratorCapability | None = None


class FollowUpResult(FollowUpModel):
    schema_version: Literal["1"] = FOLLOW_UP_SCHEMA_VERSION
    policy_version: Literal["ask-ai-follow-up-v1"] = FOLLOW_UP_POLICY_VERSION
    status: FollowUpStatus
    suggestions: tuple[FollowUpSuggestion, ...]
    artifact: FollowUpCandidatesPayload
    required_for_completion: Literal[False] = False

    @model_validator(mode="after")
    def validate_result(self) -> Self:
        if self.status is FollowUpStatus.GENERATED:
            if len(self.suggestions) not in {3, 4, 5}:
                raise ValueError("Generated follow-ups require three to five suggestions")
        elif self.suggestions:
            raise ValueError("Empty follow-up result cannot contain suggestions")
        questions = tuple(item.question for item in self.suggestions)
        categories = tuple(item.category for item in self.suggestions)
        if len(questions) != len(set(questions)) or len(categories) != len(set(categories)):
            raise ValueError("Follow-ups must be distinct by question and direction")
        if tuple(item.question for item in self.artifact.candidates) != questions:
            raise ValueError("Follow-up artifact must match typed suggestions")
        return self


def generate_follow_ups(request: FollowUpRequest) -> FollowUpResult:
    safe = FollowUpRequest.model_validate(request.model_dump(mode="python"))
    if not safe.optional_budget_available:
        return _result(())

    excluded = set((*safe.prior_questions, *safe.prior_suggestions))
    completed = set(safe.completed_intents)
    gap_rank = {item: index for index, item in enumerate(FollowUpGapKind)}
    gaps = tuple(
        sorted(set((*safe.gaps, *safe.assumptions)), key=gap_rank.__getitem__)
    )
    suggestions: list[FollowUpSuggestion] = []

    def add(candidate: FollowUpSuggestion | None) -> None:
        if candidate is None or len(suggestions) >= 5:
            return
        if _normalize(candidate.question) in excluded:
            return
        if any(item.category is candidate.category for item in suggestions):
            return
        excluded.add(_normalize(candidate.question))
        suggestions.append(candidate)

    for gap in gaps:
        add(_gap_suggestion(safe, gap))
        if suggestions:
            break

    retrieval_failed = any(
        item.capability is OrchestratorCapability.REGULATORY_RETRIEVER
        for item in safe.degraded_capabilities
    )
    if retrieval_failed:
        add(_manual_search_suggestion())
    elif safe.confidence_label is not ConfidenceLabel.HIGH:
        evidence = _official_evidence_suggestion(safe)
        add(evidence if evidence is not None else _manual_search_suggestion())

    if Intent.COMPLIANCE_QUESTION not in completed:
        add(_compliance_suggestion(safe))
    if Intent.TIMELINE not in completed and Intent.AMENDMENT not in completed:
        add(_timeline_suggestion(safe))
    add(_related_suggestion(safe))
    if Intent.NEWS not in completed:
        add(_live_suggestion(safe))
    if len(suggestions) < 3:
        add(_understand_suggestion(safe))
    if len(suggestions) < 3:
        return _result(())
    return _result(tuple(suggestions[:5]))


def _gap_suggestion(
    request: FollowUpRequest,
    gap: FollowUpGapKind,
) -> FollowUpSuggestion | None:
    entity = request.scope.entity_name or "this topic"
    if gap is FollowUpGapKind.JURISDICTION:
        return _suggestion(
            FollowUpCategory.RESOLVE,
            "Compliance",
            f"Select the jurisdiction for {entity}",
            ResponseStrategy.COMPLIANCE_CHECKLIST,
            "Jurisdiction is material to the unresolved scope.",
            True,
            None,
        )
    if gap is FollowUpGapKind.STAKEHOLDER:
        return _suggestion(
            FollowUpCategory.RESOLVE,
            "Compliance",
            f"Select the stakeholder scope for {entity}",
            ResponseStrategy.COMPLIANCE_CHECKLIST,
            "Stakeholder scope is material to applicability.",
            True,
            None,
        )
    if gap is FollowUpGapKind.OFFICIAL_EVIDENCE:
        return _official_evidence_suggestion(request, category=FollowUpCategory.RESOLVE)
    if gap is FollowUpGapKind.CURRENT_STATUS:
        if not _capability_usable(
            request,
            OrchestratorCapability.REGULATORY_RETRIEVER,
        ):
            return None
        return _suggestion(
            FollowUpCategory.RESOLVE,
            "Compliance",
            f"Is {entity} still current?",
            ResponseStrategy.COMPLIANCE_CHECKLIST,
            "Current legal status remains unresolved.",
            True,
            OrchestratorCapability.REGULATORY_RETRIEVER,
        )
    if gap is FollowUpGapKind.DEADLINE:
        if not _capability_usable(request, OrchestratorCapability.KNOWLEDGE_GRAPH):
            return None
        return _suggestion(
            FollowUpCategory.RESOLVE,
            "Compliance",
            f"What deadlines apply to {entity}?",
            ResponseStrategy.DEADLINE_CARDS_TIMELINE,
            "A material deadline field remains unresolved.",
            True,
            OrchestratorCapability.KNOWLEDGE_GRAPH,
        )
    if gap is FollowUpGapKind.COMPARISON_OPERAND:
        return _comparison_suggestion(request, category=FollowUpCategory.RESOLVE)
    if not _capability_usable(request, OrchestratorCapability.TIMELINE_BUILDER):
        return None
    return _suggestion(
        FollowUpCategory.RESOLVE,
        "Timeline",
        f"Show the complete historical range for {entity}",
        ResponseStrategy.TIMELINE,
        "The historical range remains incomplete.",
        True,
        OrchestratorCapability.TIMELINE_BUILDER,
    )


def _official_evidence_suggestion(
    request: FollowUpRequest,
    *,
    category: FollowUpCategory = FollowUpCategory.VERIFY,
) -> FollowUpSuggestion | None:
    if not _capability_usable(
        request,
        OrchestratorCapability.REGULATORY_RETRIEVER,
    ):
        return None
    subject = request.scope.entity_name or request.scope.selected_document_title
    if not subject:
        return None
    return _suggestion(
        category,
        "Official sources",
        f"Show the official provision for {subject}",
        ResponseStrategy.OFFICIAL_DOCUMENTS_OVERVIEW,
        "Official evidence would deepen support for the current result.",
        True,
        OrchestratorCapability.REGULATORY_RETRIEVER,
    )


def _manual_search_suggestion() -> FollowUpSuggestion:
    return _suggestion(
        FollowUpCategory.VERIFY,
        "Official sources",
        "Search official documents manually",
        ResponseStrategy.OFFICIAL_DOCUMENTS_OVERVIEW,
        "Manual official-document search safely deepens incomplete evidence.",
        True,
        None,
    )


def _compliance_suggestion(request: FollowUpRequest) -> FollowUpSuggestion | None:
    subject = request.scope.stakeholder or request.scope.entity_name
    if not subject or not _capability_usable(
        request,
        OrchestratorCapability.KNOWLEDGE_GRAPH,
    ):
        return None
    return _suggestion(
        FollowUpCategory.COMPLIANCE,
        "Compliance",
        f"What obligations apply to {subject}?",
        ResponseStrategy.COMPLIANCE_CHECKLIST,
        "This explores regulatory impact within the resolved scope.",
        True,
        OrchestratorCapability.KNOWLEDGE_GRAPH,
    )


def _timeline_suggestion(request: FollowUpRequest) -> FollowUpSuggestion | None:
    if not request.scope.entity_name or not _capability_usable(
        request,
        OrchestratorCapability.TIMELINE_BUILDER,
    ):
        return None
    return _suggestion(
        FollowUpCategory.CHANGE,
        "Timeline",
        f"Show the {request.scope.entity_name} regulatory timeline",
        ResponseStrategy.TIMELINE,
        "This explores change over time without altering current findings.",
        True,
        OrchestratorCapability.TIMELINE_BUILDER,
    )


def _comparison_suggestion(
    request: FollowUpRequest,
    *,
    category: FollowUpCategory = FollowUpCategory.EXPLORE,
) -> FollowUpSuggestion | None:
    if (
        not request.scope.entity_name
        or not request.scope.comparison_operands
        or not _capability_usable(
            request,
            OrchestratorCapability.REGULATORY_RETRIEVER,
        )
    ):
        return None
    operand = request.scope.comparison_operands[0]
    if _normalize(operand) == _normalize(request.scope.entity_name):
        return None
    return _suggestion(
        category,
        "Compare",
        f"Compare {request.scope.entity_name} with {operand}",
        ResponseStrategy.COMPARISON_TABLE,
        "A plausible second operand enables an independently evidenced comparison.",
        True,
        OrchestratorCapability.REGULATORY_RETRIEVER,
    )


def _related_suggestion(request: FollowUpRequest) -> FollowUpSuggestion | None:
    comparison = _comparison_suggestion(request)
    if comparison is not None:
        return comparison
    if (
        not request.scope.related_entities
        or not request.scope.entity_name
        or not _capability_usable(request, OrchestratorCapability.KNOWLEDGE_GRAPH)
    ):
        return None
    related = request.scope.related_entities[0]
    return _suggestion(
        FollowUpCategory.EXPLORE,
        "Official sources",
        f"How does {related} relate to {request.scope.entity_name}?",
        ResponseStrategy.ENTITY_INTELLIGENCE_PAGE,
        "This follows a resolved related-entity path.",
        True,
        OrchestratorCapability.KNOWLEDGE_GRAPH,
    )


def _live_suggestion(request: FollowUpRequest) -> FollowUpSuggestion | None:
    if (
        request.scope.entity_name is None
        or not _capability_usable(request, OrchestratorCapability.NEWS_RETRIEVER)
    ):
        return None
    return _suggestion(
        FollowUpCategory.LIVE,
        "Live",
        f"Find the latest {request.scope.entity_name} consultation",
        ResponseStrategy.LATEST_INTELLIGENCE,
        "Current intelligence is relevant and the live capability is eligible.",
        True,
        OrchestratorCapability.NEWS_RETRIEVER,
    )


def _understand_suggestion(request: FollowUpRequest) -> FollowUpSuggestion | None:
    subject = request.scope.entity_name or request.scope.selected_document_title
    if not subject or Intent.DEFINITION in request.completed_intents:
        return None
    return _suggestion(
        FollowUpCategory.UNDERSTAND,
        "Definition",
        f"Explain {subject} for a beginner",
        ResponseStrategy.DEFINITION_CARD,
        "This adds a distinct plain-language research view.",
        False,
        None,
    )


def _suggestion(
    category: FollowUpCategory,
    preview_label: str,
    question: str,
    strategy: ResponseStrategy,
    reason: str,
    fresh: bool,
    capability: OrchestratorCapability | None,
) -> FollowUpSuggestion:
    digest = hashlib.sha256(
        f"{category.value}\x1f{question}\x1f{strategy.value}".encode()
    ).hexdigest()[:32]
    return FollowUpSuggestion(
        suggestion_id=f"follow_up_{digest}",
        category=category,
        preview_label=preview_label,
        question=question,
        expected_response_strategy=strategy,
        reason=reason,
        requires_fresh_retrieval=fresh,
        capability=capability,
    )


def _result(suggestions: tuple[FollowUpSuggestion, ...]) -> FollowUpResult:
    artifact = FollowUpCandidatesPayload(
        candidates=tuple(
            FollowUpCandidate(
                question=item.question,
                expected_response_strategy=item.expected_response_strategy.value,
                reason=item.reason,
            )
            for item in suggestions
        )
    )
    return FollowUpResult(
        status=(FollowUpStatus.GENERATED if suggestions else FollowUpStatus.EMPTY),
        suggestions=suggestions,
        artifact=artifact,
    )


def _capability_usable(
    request: FollowUpRequest,
    capability: OrchestratorCapability,
) -> bool:
    return (
        capability in request.eligible_capabilities
        and all(item.capability is not capability for item in request.degraded_capabilities)
    )


def _normalize(value: str) -> str:
    return _SPACE.sub(" ", value.strip()).casefold()


def _has_control(value: str) -> bool:
    return any(ord(character) < 32 or ord(character) == 127 for character in value)
