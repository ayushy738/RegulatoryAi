from __future__ import annotations

import re
import time
from collections.abc import Callable
from datetime import UTC, datetime
from enum import StrEnum
from typing import Literal, Protocol

from pydantic import Field, model_validator

from backend.ask.decision.models import (
    DECISION_POLICY_VERSION,
    AtomicQuestion,
    CapabilityDecision,
    CapabilityName,
    ConversationScope,
    DecisionModel,
    DecisionRecord,
    DecisionRequest,
    Intent,
    IntentConfidenceBand,
    IntentDecision,
    ResponseStrategy,
)
from backend.ask.decision.plan_policy import (
    PlanQuestion,
    PlanRequest,
    select_decision_plan,
)
from backend.ask.decision.policy import IntentSignals, select_intent
from backend.ask.decision.time_policy import normalize_time
from backend.core.logging import log_event
from backend.rag.models import IntentName

SHADOW_DECISION_SCHEMA_VERSION = "1"
SHADOW_DECISION_POLICY_VERSION = "ask-ai-decision-shadow-v1"
SHADOW_DECISION_UNAVAILABLE = "DECISION_SHADOW_UNAVAILABLE"


class ShadowComparisonOutcome(StrEnum):
    AGREEMENT = "agreement"
    DISAGREEMENT = "disagreement"
    UNAVAILABLE = "unavailable"


class ShadowDecisionComparison(DecisionModel):
    schema_version: Literal["1"] = SHADOW_DECISION_SCHEMA_VERSION
    policy_version: str = Field(
        default=SHADOW_DECISION_POLICY_VERSION,
        min_length=1,
    )
    decision_policy_version: str = Field(min_length=1)
    outcome: ShadowComparisonOutcome
    legacy_intent: str = Field(min_length=1)
    legacy_canonical_intent: Intent
    shadow_intent: Intent | None = None
    shadow_response_strategy: ResponseStrategy | None = None
    duration_ms: int = Field(ge=0)
    safe_error_code: str | None = Field(
        default=None,
        pattern=r"^[A-Z][A-Z0-9_]{0,99}$",
    )

    @model_validator(mode="after")
    def validate_outcome(self) -> ShadowDecisionComparison:
        unavailable = self.outcome is ShadowComparisonOutcome.UNAVAILABLE
        if unavailable != (self.safe_error_code is not None):
            raise ValueError("Only unavailable shadow comparisons have an error code")
        if unavailable:
            if (
                self.shadow_intent is not None
                or self.shadow_response_strategy is not None
            ):
                raise ValueError("Unavailable shadow comparisons have no decision")
        elif (
            self.shadow_intent is None
            or self.shadow_response_strategy is None
        ):
            raise ValueError("Completed shadow comparisons require a decision")
        return self


class ShadowDecisionExecution(DecisionModel):
    comparison: ShadowDecisionComparison
    decision_record: DecisionRecord | None = None

    @model_validator(mode="after")
    def validate_execution(self) -> ShadowDecisionExecution:
        unavailable = (
            self.comparison.outcome is ShadowComparisonOutcome.UNAVAILABLE
        )
        if unavailable != (self.decision_record is None):
            raise ValueError("Shadow execution record availability is inconsistent")
        return self


class ShadowDecisionEvaluator(Protocol):
    def evaluate(
        self,
        *,
        query: str,
        now: datetime,
        user_timezone: str,
    ) -> DecisionRecord: ...


class ShadowComparisonRecorder(Protocol):
    def record(self, comparison: ShadowDecisionComparison) -> None: ...


class DeterministicShadowDecisionEvaluator:
    def evaluate(
        self,
        *,
        query: str,
        now: datetime,
        user_timezone: str,
    ) -> DecisionRecord:
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("Shadow decision clocks must be timezone-aware")
        normalized_query = " ".join(query.split())
        if not normalized_query:
            raise ValueError("Shadow decision queries cannot be blank")
        clauses = _atomic_clauses(normalized_query)
        clause_selections = tuple(
            select_intent(_signals_for_query(clause)) for clause in clauses
        )
        aggregate_signals = _signals_for_query(normalized_query)
        if len(clause_selections) > 1:
            aggregate_signals = aggregate_signals.model_copy(
                update={
                    "atomic_intents": tuple(
                        selection.primary for selection in clause_selections
                    )
                }
            )
        selected = select_intent(aggregate_signals)
        atomic_questions = tuple(
            AtomicQuestion(
                id=f"q{index}",
                question=clause,
                intent=selection.primary,
                secondary_intents=selection.secondary,
                subtypes=selection.subtypes,
            )
            for index, (clause, selection) in enumerate(
                zip(clauses, clause_selections, strict=True),
                start=1,
            )
        )
        plan = select_decision_plan(
            PlanRequest(
                questions=tuple(
                    _plan_question(question, normalized_query)
                    for question in atomic_questions
                )
            )
        )
        planned_by_capability = {
            capability.capability: capability
            for capability in (*plan.capabilities, *plan.skipped_capabilities)
        }
        explicit = selected.precedence_rule != "general_question"
        confidence = 0.92 if explicit else 0.50
        confidence_band = (
            IntentConfidenceBand.CERTAIN
            if explicit
            else IntentConfidenceBand.AMBIGUOUS
        )
        primary_for_time = (
            atomic_questions[0].intent
            if selected.primary is Intent.MULTI_PART_QUESTION
            else selected.primary
        )
        return DecisionRecord(
            policy_version=DECISION_POLICY_VERSION,
            request=DecisionRequest(
                query=normalized_query,
                user_timezone=user_timezone,
            ),
            conversation_scope=ConversationScope(),
            intent=IntentDecision(
                primary=selected.primary,
                secondary=selected.secondary,
                subtypes=selected.subtypes,
                confidence=confidence,
                confidence_band=confidence_band,
                reasons=(selected.precedence_rule,),
            ),
            atomic_questions=atomic_questions,
            time_interpretation=normalize_time(
                _time_expression(normalized_query),
                now=now,
                user_timezone=user_timezone,
                intent=primary_for_time,
            ),
            assumptions=(
                "Shadow interpretation uses deterministic lexical signals.",
            ),
            capabilities=tuple(
                CapabilityDecision(
                    capability=capability,
                    role=planned_by_capability[capability].role,
                    reason=planned_by_capability[capability].reason,
                )
                for capability in CapabilityName
            ),
            retrieval_plan=plan.retrieval_plan,
            response_strategy=plan.response_strategy,
        )


class LoggingShadowComparisonRecorder:
    def __init__(self, *, correlation_id: str) -> None:
        self._correlation_id = correlation_id

    def record(self, comparison: ShadowDecisionComparison) -> None:
        log_event(
            "ask_decision_shadow",
            correlation_id=self._correlation_id,
            schema_version=comparison.schema_version,
            policy_version=comparison.policy_version,
            decision_policy_version=comparison.decision_policy_version,
            outcome=comparison.outcome.value,
            legacy_intent=comparison.legacy_intent,
            legacy_canonical_intent=comparison.legacy_canonical_intent.value,
            shadow_intent=(
                comparison.shadow_intent.value
                if comparison.shadow_intent is not None
                else None
            ),
            shadow_response_strategy=(
                comparison.shadow_response_strategy.value
                if comparison.shadow_response_strategy is not None
                else None
            ),
            duration_ms=comparison.duration_ms,
            safe_error_code=comparison.safe_error_code,
        )


class DecisionShadowService:
    def __init__(
        self,
        *,
        evaluator: ShadowDecisionEvaluator | None = None,
        recorder: ShadowComparisonRecorder | None = None,
        clock: Callable[[], datetime] | None = None,
        monotonic: Callable[[], float] | None = None,
    ) -> None:
        self._evaluator = evaluator or DeterministicShadowDecisionEvaluator()
        self._recorder = recorder
        self._clock = clock or (lambda: datetime.now(UTC))
        self._monotonic = monotonic or time.perf_counter

    def evaluate_and_record(
        self,
        *,
        query: str,
        legacy_intent: IntentName,
        user_timezone: str = "UTC",
    ) -> ShadowDecisionExecution:
        started = self._monotonic()
        canonical_legacy = LEGACY_CANONICAL_INTENTS[legacy_intent]
        log_event(
            "decision_shadow_started",
            legacy_intent=legacy_intent,
            legacy_canonical_intent=canonical_legacy.value,
        )
        try:
            record = DecisionRecord.model_validate(
                self._evaluator.evaluate(
                    query=query,
                    now=self._clock(),
                    user_timezone=user_timezone,
                ).model_dump(mode="python")
            )
            outcome = (
                ShadowComparisonOutcome.AGREEMENT
                if record.intent.primary is canonical_legacy
                else ShadowComparisonOutcome.DISAGREEMENT
            )
            comparison = ShadowDecisionComparison(
                decision_policy_version=record.policy_version,
                outcome=outcome,
                legacy_intent=legacy_intent,
                legacy_canonical_intent=canonical_legacy,
                shadow_intent=record.intent.primary,
                shadow_response_strategy=record.response_strategy,
                duration_ms=_duration_ms(started, self._monotonic()),
            )
            execution = ShadowDecisionExecution(
                comparison=comparison,
                decision_record=record,
            )
        except Exception:
            comparison = ShadowDecisionComparison(
                decision_policy_version=DECISION_POLICY_VERSION,
                outcome=ShadowComparisonOutcome.UNAVAILABLE,
                legacy_intent=legacy_intent,
                legacy_canonical_intent=canonical_legacy,
                duration_ms=_duration_ms(started, self._monotonic()),
                safe_error_code=SHADOW_DECISION_UNAVAILABLE,
            )
            execution = ShadowDecisionExecution(comparison=comparison)
        if self._recorder is not None:
            try:
                self._recorder.record(comparison)
            except Exception:
                pass
        log_event(
            "decision_shadow_finished",
            outcome=comparison.outcome.value,
            legacy_intent=legacy_intent,
            legacy_canonical_intent=canonical_legacy.value,
            shadow_intent=(
                comparison.shadow_intent.value
                if comparison.shadow_intent is not None
                else None
            ),
            shadow_response_strategy=(
                comparison.shadow_response_strategy.value
                if comparison.shadow_response_strategy is not None
                else None
            ),
            duration_ms=comparison.duration_ms,
            safe_error_code=comparison.safe_error_code,
        )
        return execution


LEGACY_CANONICAL_INTENTS: dict[IntentName, Intent] = {
    "deadline": Intent.DEADLINE,
    "stakeholder": Intent.STAKEHOLDER,
    "obligation": Intent.COMPLIANCE_QUESTION,
    "consultation": Intent.CONSULTATION,
    "tender": Intent.REGULATION_LOOKUP,
    "regulation_lookup": Intent.REGULATION_LOOKUP,
    "amendment": Intent.AMENDMENT,
    "comparison": Intent.COMPARISON,
    "summary": Intent.SUMMARIZATION,
    "semantic_search": Intent.REGULATION_LOOKUP,
    "general": Intent.GENERAL_QUESTION,
}


def _signals_for_query(query: str) -> IntentSignals:
    normalized = query.casefold()
    compliance = _contains(
        normalized,
        "compliance",
        "comply",
        "obligation",
        "shall",
        "must",
        "required",
    )
    comparison = _contains(
        normalized,
        "compare",
        "difference",
        "versus",
        " vs ",
        "before and after",
    )
    amendment = _contains(
        normalized,
        "amendment",
        "amended",
        "corrigendum",
        "version change",
        "what changed",
    )
    deadline = _contains(
        normalized,
        "deadline",
        "due date",
        "last date",
        "hearing date",
    )
    consultation = _contains(
        normalized,
        "consultation",
        "public hearing",
        "comments",
    )
    live = _contains(
        normalized,
        "latest",
        "recent",
        "today",
        "current",
        "breaking",
    )
    live_object: Literal["deadline", "amendment", "compliance_question"] | None
    if compliance:
        live_object = "compliance_question"
    elif deadline:
        live_object = "deadline"
    elif amendment:
        live_object = "amendment"
    else:
        live_object = None
    return IntentSignals(
        explicit_compliance=compliance,
        explicit_comparison=comparison,
        resolved_comparison_operands=2 if comparison else 0,
        explicit_amendment=amendment,
        explicit_version_change=amendment,
        explicit_side_by_side_version_change=(
            comparison and _contains(normalized, "version", "before and after")
        ),
        explicit_deadline=deadline,
        consultation_comment_deadline=consultation and deadline,
        explicit_timeline=_contains(
            normalized,
            "timeline",
            "chronology",
            "history of",
        ),
        explicit_consultation=consultation,
        explicit_live_recency=live,
        live_object_intent=live_object,
        named_regulation=_contains(
            normalized,
            "regulation",
            "rules",
            " act",
            "notification",
            "order",
            "code",
            "policy",
        ),
        explicit_definition=(
            normalized.startswith(("what is ", "define ", "meaning of "))
            or _contains(normalized, "definition")
        ),
        bare_resolved_entity=bool(
            re.fullmatch(r"[A-Z][A-Z0-9.-]{1,15}", query.strip())
        ),
        responsible_party_question=_contains(
            normalized,
            "who is responsible",
            "who regulates",
            "stakeholder",
            "affected party",
            "impact on",
        ),
        known_result_summarization=_contains(
            normalized,
            "summarize",
            "summary",
        ),
    )


def _atomic_clauses(query: str) -> tuple[str, ...]:
    semicolon_parts = tuple(
        part.strip() for part in query.split(";") if part.strip()
    )
    if len(semicolon_parts) > 1:
        return semicolon_parts
    if " before and after " in query.casefold():
        return (query,)
    parts = tuple(
        part.strip()
        for part in re.split(r"\s+(?:and also|also)\s+", query, flags=re.IGNORECASE)
        if part.strip()
    )
    return parts or (query,)


def _plan_question(
    question: AtomicQuestion,
    full_query: str,
) -> PlanQuestion:
    normalized = full_query.casefold()
    return PlanQuestion(
        question_id=question.id,
        intent=question.intent,
        secondary_intents=question.secondary_intents,
        subtypes=question.subtypes,
        live_eligible=_contains(
            normalized,
            "latest",
            "recent",
            "today",
            "current",
            "breaking",
            "consultation",
        ),
        current_intelligence_requested=_contains(
            normalized,
            "latest",
            "recent",
            "today",
            "breaking",
        ),
        general_source_set=question.intent is Intent.GENERAL_QUESTION,
        version_change=question.intent in {Intent.AMENDMENT, Intent.COMPARISON},
    )


def _time_expression(query: str) -> str | None:
    normalized = query.casefold()
    for expression in (
        "latest draft",
        "this week",
        "this month",
        "breaking",
        "today",
        "recent",
        "latest",
        "current",
        "draft",
        "consultation",
    ):
        if expression in normalized:
            return expression
    explicit_range = re.search(
        r"\b\d{4}-\d{2}-\d{2}\s+(?:to|through)\s+\d{4}-\d{2}-\d{2}\b",
        normalized,
    )
    if explicit_range is not None:
        return explicit_range.group(0)
    explicit_date = re.search(r"\b\d{4}-\d{2}-\d{2}\b", normalized)
    if explicit_date is not None:
        return explicit_date.group(0)
    year_bound = re.search(r"\b(?:before|after|since)\s+\d{4}\b", normalized)
    if year_bound is not None:
        return year_bound.group(0)
    year = re.search(r"\b(?:19|20)\d{2}\b", normalized)
    return year.group(0) if year is not None else None


def _contains(value: str, *markers: str) -> bool:
    return any(marker in value for marker in markers)


def _duration_ms(started: float, finished: float) -> int:
    return max(0, int((finished - started) * 1000))
