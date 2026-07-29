from __future__ import annotations

import json
import math
import re
from datetime import date
from enum import StrEnum
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from backend.ask.decision.models import ConfidenceLabel, KnowledgeMode
from backend.ask.orchestration.contracts import ProvenanceClass
from backend.rag.version_status import DocumentLegalStatus

CORE_CARD_SCHEMA_VERSION = "1"
INTROSPECTION_PATTERN = re.compile(
    r"\b(?:chain[- ]of[- ]thought|internal reasoning|hidden reasoning|"
    r"model reasoning|system prompt|i think|i believe)\b",
    re.IGNORECASE,
)
ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class CoreCardModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        strict=True,
        str_strip_whitespace=True,
    )


class StructuredFieldState(StrEnum):
    ESTABLISHED = "established"
    NOT_ESTABLISHED = "not_established"


class StructuredTextField(CoreCardModel):
    state: StructuredFieldState
    value: str | None = Field(default=None, max_length=50_000)

    @model_validator(mode="after")
    def validate_state(self) -> Self:
        if self.state is StructuredFieldState.ESTABLISHED:
            if self.value is None or not self.value.strip():
                raise ValueError("Established text requires a value")
        elif self.value is not None:
            raise ValueError("Not-established text cannot contain a value")
        return self


class StructuredDateField(CoreCardModel):
    state: StructuredFieldState
    value: str | None = None

    @model_validator(mode="after")
    def validate_state(self) -> Self:
        if self.state is StructuredFieldState.ESTABLISHED:
            if self.value is None or ISO_DATE.fullmatch(self.value) is None:
                raise ValueError("Established date requires ISO YYYY-MM-DD")
            try:
                date.fromisoformat(self.value)
            except ValueError as error:
                raise ValueError("Established date must be a calendar date") from error
        elif self.value is not None:
            raise ValueError("Not-established date cannot contain a value")
        return self


def _unique_text(values: tuple[str, ...], label: str) -> tuple[str, ...]:
    normalized = tuple(value.strip() for value in values)
    if any(not value for value in normalized):
        raise ValueError(f"{label} cannot contain blank values")
    if len(set(normalized)) != len(normalized):
        raise ValueError(f"{label} must be unique")
    return normalized


class AnswerSummaryPayload(CoreCardModel):
    schema_version: Literal["1"] = CORE_CARD_SCHEMA_VERSION
    direct_answer: str = Field(min_length=1, max_length=50_000)
    why_it_matters: StructuredTextField
    unresolved_assumptions: tuple[str, ...] = ()
    source_count: int = Field(ge=0)

    @field_validator("direct_answer")
    @classmethod
    def normalize_answer(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Direct answer cannot be blank")
        return normalized

    @field_validator("unresolved_assumptions")
    @classmethod
    def validate_assumptions(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return _unique_text(value, "Summary assumptions")


class DefinitionPayload(CoreCardModel):
    schema_version: Literal["1"] = CORE_CARD_SCHEMA_VERSION
    term: str = Field(min_length=1, max_length=500)
    official_definition: StructuredTextField
    plain_language_explanation: str = Field(min_length=1, max_length=50_000)
    acronym_expansion: StructuredTextField
    common_confusion: StructuredTextField
    official_source_label: StructuredTextField

    @field_validator("term", "plain_language_explanation")
    @classmethod
    def normalize_required_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Definition text cannot be blank")
        return normalized


class OfficialSourcePayload(CoreCardModel):
    schema_version: Literal["1"] = CORE_CARD_SCHEMA_VERSION
    source_id: str = Field(min_length=1, max_length=200)
    document_title: str = Field(min_length=1, max_length=1_000)
    issuer: str = Field(min_length=1, max_length=500)
    document_type: str = Field(min_length=1, max_length=300)
    issue_date: StructuredDateField
    effective_date: StructuredDateField
    current_status: DocumentLegalStatus
    cited_locator: str = Field(min_length=1, max_length=1_000)
    excerpt: str = Field(min_length=1, max_length=50_000)
    relationship: str = Field(min_length=1, max_length=2_000)

    @field_validator(
        "source_id",
        "document_title",
        "issuer",
        "document_type",
        "cited_locator",
        "excerpt",
        "relationship",
    )
    @classmethod
    def normalize_required_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Official source text cannot be blank")
        return normalized


class ConfidenceReasonKind(StrEnum):
    EVIDENCE = "evidence"
    COVERAGE = "coverage"
    FRESHNESS = "freshness"
    SCOPE = "scope"
    CAPABILITY = "capability"


class ConfidenceReason(CoreCardModel):
    kind: ConfidenceReasonKind
    text: str = Field(min_length=1, max_length=2_000)

    @field_validator("text")
    @classmethod
    def validate_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Confidence reason cannot be blank")
        if INTROSPECTION_PATTERN.search(normalized):
            raise ValueError("Confidence reason cannot expose model introspection")
        return normalized


class ConfidenceCoveragePayload(CoreCardModel):
    schema_version: Literal["1"] = CORE_CARD_SCHEMA_VERSION
    modes_used: tuple[KnowledgeMode, ...] = Field(min_length=1)
    coverage_percent: float = Field(ge=0, le=100)
    official_documents_found: int = Field(ge=0)
    live_sources_found: int = Field(ge=0)
    reasons: tuple[ConfidenceReason, ...] = Field(min_length=1)
    unsupported_or_inferred_areas: tuple[str, ...] = ()
    corpus_freshness: StructuredTextField
    what_would_improve_confidence: tuple[str, ...] = ()

    @field_validator("coverage_percent")
    @classmethod
    def validate_coverage(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("Coverage percent must be finite")
        return value

    @field_validator(
        "unsupported_or_inferred_areas",
        "what_would_improve_confidence",
    )
    @classmethod
    def validate_unique_text(
        cls,
        value: tuple[str, ...],
        info: object,
    ) -> tuple[str, ...]:
        field_name = getattr(info, "field_name", "Confidence metadata")
        return _unique_text(value, field_name)

    @model_validator(mode="after")
    def validate_unique_reasons_and_modes(self) -> Self:
        if len(set(self.modes_used)) != len(self.modes_used):
            raise ValueError("Confidence modes must be unique")
        reason_text = tuple(reason.text for reason in self.reasons)
        if len(set(reason_text)) != len(reason_text):
            raise ValueError("Confidence reason text must be unique")
        return self


_CORE_PAYLOADS: dict[str, type[CoreCardModel]] = {
    "answer_summary": AnswerSummaryPayload,
    "definition": DefinitionPayload,
    "official_source": OfficialSourcePayload,
    "confidence_coverage": ConfidenceCoveragePayload,
}

_LABEL_RANK = {
    ConfidenceLabel.UNKNOWN: 0,
    ConfidenceLabel.LOW: 1,
    ConfidenceLabel.MEDIUM: 2,
    ConfidenceLabel.HIGH: 3,
}


def _numeric_label(score: float) -> ConfidenceLabel:
    if score >= 80:
        return ConfidenceLabel.HIGH
    if score >= 60:
        return ConfidenceLabel.MEDIUM
    if score >= 35:
        return ConfidenceLabel.LOW
    return ConfidenceLabel.UNKNOWN


def _parse_payload(
    card_type: str,
    payload: dict[str, object],
) -> CoreCardModel | None:
    model = _CORE_PAYLOADS.get(card_type)
    if model is None:
        return None
    try:
        return model.model_validate_json(json.dumps(payload, allow_nan=False))
    except (TypeError, ValueError) as error:
        raise ValueError(f"Invalid {card_type} payload") from error


def validate_core_card(
    *,
    card_type: str,
    state: str,
    knowledge_mode: KnowledgeMode,
    provenance_class: ProvenanceClass,
    confidence_score: float | None,
    confidence_label: ConfidenceLabel | None,
    confidence_reasons: tuple[str, ...],
    source_ids: tuple[str, ...],
    actions: tuple[tuple[str, str, str | None], ...],
    payload: dict[str, object],
) -> None:
    parsed = _parse_payload(card_type, payload)
    if parsed is None:
        return

    if state not in {"ready", "partial"}:
        raise ValueError("Core cards must expose ready or partial content")
    expected_provenance = {
        KnowledgeMode.GROUNDED_REGULATORY: (
            ProvenanceClass.INTERNAL_REGULATORY_CORPUS
        ),
        KnowledgeMode.GENERAL_AI: ProvenanceClass.GENERAL_AI_KNOWLEDGE,
        KnowledgeMode.LIVE_INTELLIGENCE: ProvenanceClass.LIVE_WEB_SOURCES,
    }[knowledge_mode]
    if provenance_class is not expected_provenance:
        raise ValueError("Core Card mode and provenance must remain pure")
    if confidence_score is not None and confidence_label is not None:
        if _LABEL_RANK[confidence_label] > _LABEL_RANK[
            _numeric_label(confidence_score)
        ]:
            raise ValueError("Confidence label cannot exceed its numeric band")
        if (
            knowledge_mode is KnowledgeMode.GENERAL_AI
            and confidence_label is ConfidenceLabel.HIGH
        ):
            raise ValueError("General AI confidence cannot be High")

    if isinstance(parsed, AnswerSummaryPayload):
        if confidence_score is None or confidence_label is None:
            raise ValueError("Answer Summary requires confidence")
        if parsed.source_count != len(source_ids):
            raise ValueError("Summary source count must match card sources")
        if (
            knowledge_mode is KnowledgeMode.GENERAL_AI
            and (parsed.source_count != 0 or source_ids)
        ):
            raise ValueError("General AI Summary cannot expose sources")
        if (
            knowledge_mode is not KnowledgeMode.GENERAL_AI
            and parsed.source_count == 0
        ):
            raise ValueError("Evidence-backed Summary requires sources")
        if (
            parsed.why_it_matters.state is StructuredFieldState.NOT_ESTABLISHED
            and state != "partial"
        ):
            raise ValueError("Missing Summary fields require partial state")
        return

    if isinstance(parsed, DefinitionPayload):
        if knowledge_mode is KnowledgeMode.LIVE_INTELLIGENCE:
            raise ValueError("Definition cards cannot use live provenance")
        if confidence_score is None or confidence_label is None:
            raise ValueError("Definition Card requires confidence")
        if knowledge_mode is KnowledgeMode.GROUNDED_REGULATORY:
            if (
                provenance_class
                is not ProvenanceClass.INTERNAL_REGULATORY_CORPUS
                or not source_ids
                or parsed.official_definition.state
                is not StructuredFieldState.ESTABLISHED
                or parsed.official_source_label.state
                is not StructuredFieldState.ESTABLISHED
            ):
                raise ValueError(
                    "Grounded Definition requires official definition and source"
                )
        elif (
            source_ids
            or parsed.official_definition.state
            is not StructuredFieldState.NOT_ESTABLISHED
            or parsed.official_source_label.state
            is not StructuredFieldState.NOT_ESTABLISHED
        ):
            raise ValueError(
                "General AI Definition cannot claim official definition or source"
            )
        return

    if isinstance(parsed, OfficialSourcePayload):
        if (
            knowledge_mode is not KnowledgeMode.GROUNDED_REGULATORY
            or provenance_class
            is not ProvenanceClass.INTERNAL_REGULATORY_CORPUS
        ):
            raise ValueError("Official Source Card requires grounded provenance")
        if source_ids != (parsed.source_id,):
            raise ValueError("Official Source Card requires its exact one source")
        action_types = {action for action, _, _ in actions}
        if action_types != {"open_source", "save", "compare"}:
            raise ValueError("Official Source Card requires Open, Save, and Compare")
        for action, action_state, target in actions:
            if (
                action in {"open_source", "save"}
                and action_state == "available"
                and target != parsed.source_id
            ):
                raise ValueError("Official Source action must target its source")
        incomplete = (
            parsed.issue_date.state is StructuredFieldState.NOT_ESTABLISHED
            or parsed.effective_date.state
            is StructuredFieldState.NOT_ESTABLISHED
            or parsed.current_status is DocumentLegalStatus.UNKNOWN
        )
        if incomplete != (state == "partial"):
            raise ValueError("Official Source state must reflect missing metadata")
        return

    assert isinstance(parsed, ConfidenceCoveragePayload)
    if confidence_score is None or confidence_label is None:
        raise ValueError("Confidence and Coverage Card requires confidence")
    if parsed.modes_used != (knowledge_mode,):
        raise ValueError("Confidence Card cannot flatten provenance modes")
    if tuple(reason.text for reason in parsed.reasons) != confidence_reasons:
        raise ValueError("Confidence Card reasons must match its snapshot")
    expected_official = (
        len(source_ids)
        if knowledge_mode is KnowledgeMode.GROUNDED_REGULATORY
        else 0
    )
    expected_live = (
        len(source_ids)
        if knowledge_mode is KnowledgeMode.LIVE_INTELLIGENCE
        else 0
    )
    if (
        parsed.official_documents_found != expected_official
        or parsed.live_sources_found != expected_live
    ):
        raise ValueError("Confidence evidence counts must match card provenance")
    if (
        knowledge_mode is KnowledgeMode.GENERAL_AI
        and parsed.corpus_freshness.state
        is not StructuredFieldState.NOT_ESTABLISHED
    ):
        raise ValueError("General AI cannot claim corpus freshness")
    if any(action != "inspect_evidence" for action, _, _ in actions):
        raise ValueError("Confidence Card permits only Inspect evidence")
