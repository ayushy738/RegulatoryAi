from __future__ import annotations

import math
import re
from enum import StrEnum
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from backend.ask.change_cards import validate_change_card
from backend.ask.compliance_cards import validate_compliance_card
from backend.ask.core_cards import validate_core_card
from backend.ask.decision.models import (
    ConfidenceLabel,
    KnowledgeMode,
    ResponseStrategy,
)
from backend.ask.orchestration.contracts import (
    ProvenanceClass,
    SectionTerminalState,
)

RESPONSE_CONTRACT_SCHEMA_VERSION = "1"
RESPONSE_CONTRACT_POLICY_VERSION = "ask-ai-response-contract-v1"
SAFE_CODE = re.compile(r"^[A-Z][A-Z0-9_]{0,99}$")
CARD_TYPE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")


class ResponseCardType(StrEnum):
    ANSWER_SUMMARY = "answer_summary"
    DEFINITION = "definition"
    OFFICIAL_SOURCE = "official_source"
    LIVE_NEWS = "live_news"
    OBLIGATION = "obligation"
    DEADLINE = "deadline"
    TIMELINE_EVENT = "timeline_event"
    AMENDMENT = "amendment"
    COMPARISON = "comparison"
    STAKEHOLDER = "stakeholder"
    RELATED_REGULATION = "related_regulation"
    CONFIDENCE_COVERAGE = "confidence_coverage"


class CardRendering(StrEnum):
    KNOWN = "known"
    UNKNOWN_FALLBACK = "unknown_fallback"


class CardContentState(StrEnum):
    READY = "ready"
    PARTIAL = "partial"
    NOT_ESTABLISHED = "not_established"
    UNAVAILABLE = "unavailable"


class CardActionType(StrEnum):
    INSPECT_EVIDENCE = "inspect_evidence"
    OPEN_SOURCE = "open_source"
    SAVE = "save"
    ADD_TO_WORKSPACE = "add_to_workspace"
    COMPARE = "compare"
    OPEN_ENTITY = "open_entity"
    ASK_FOLLOW_UP = "ask_follow_up"
    FIND_OFFICIAL_BASIS = "find_official_basis"
    CHECK_APPLICABILITY = "check_applicability"
    ADD_TO_TRACKER = "add_to_tracker"


class CardActionState(StrEnum):
    AVAILABLE = "available"
    DISABLED = "disabled"


class ResponseContractModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        strict=True,
        str_strip_whitespace=True,
    )


def _unique_text(values: tuple[str, ...], label: str) -> tuple[str, ...]:
    normalized = tuple(value.strip() for value in values)
    if any(not value for value in normalized):
        raise ValueError(f"{label} cannot contain blank values")
    if len(set(normalized)) != len(normalized):
        raise ValueError(f"{label} must be unique")
    return normalized


class ResponseConfidenceSnapshot(ResponseContractModel):
    score: float = Field(ge=0, le=100)
    label: ConfidenceLabel
    reasons: tuple[str, ...] = ()

    @field_validator("score")
    @classmethod
    def reject_nonfinite_score(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("Response confidence score must be finite")
        return value

    @field_validator("reasons")
    @classmethod
    def validate_reasons(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return _unique_text(value, "Confidence reasons")


class CardActionDescriptor(ResponseContractModel):
    action: CardActionType
    state: CardActionState
    target: str | None = Field(default=None, max_length=2_000)
    disabled_reason_code: str | None = None

    @model_validator(mode="after")
    def validate_action_state(self) -> Self:
        if self.state is CardActionState.AVAILABLE:
            if self.target is None or not self.target.strip():
                raise ValueError("Available card actions require a target")
            if self.disabled_reason_code is not None:
                raise ValueError("Available card actions cannot be disabled")
        else:
            if self.target is not None:
                raise ValueError("Disabled card actions cannot expose a target")
            if (
                self.disabled_reason_code is None
                or SAFE_CODE.fullmatch(self.disabled_reason_code) is None
            ):
                raise ValueError("Disabled card actions require a safe reason code")
        return self


class ResponseCardEnvelope(ResponseContractModel):
    schema_version: Literal["1"] = RESPONSE_CONTRACT_SCHEMA_VERSION
    card_id: str = Field(min_length=1, max_length=200)
    order: int = Field(ge=0)
    card_type: str = Field(min_length=1, max_length=64)
    known_type: ResponseCardType | None
    rendering: CardRendering
    fallback_title: str | None = Field(default=None, max_length=200)
    title: str = Field(min_length=1, max_length=500)
    state: CardContentState
    knowledge_mode: KnowledgeMode
    provenance_class: ProvenanceClass
    confidence: ResponseConfidenceSnapshot | None = None
    claim_ids: tuple[str, ...] = ()
    source_ids: tuple[str, ...] = ()
    actions: tuple[CardActionDescriptor, ...] = ()
    payload: dict[str, object] = Field(min_length=1)

    @field_validator("card_id", "title")
    @classmethod
    def normalize_required_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Card identity text cannot be blank")
        return normalized

    @field_validator("claim_ids", "source_ids")
    @classmethod
    def validate_references(
        cls,
        value: tuple[str, ...],
        info: object,
    ) -> tuple[str, ...]:
        field_name = getattr(info, "field_name", "Card references")
        return _unique_text(value, field_name)

    @field_validator("payload")
    @classmethod
    def validate_json_payload(
        cls,
        value: dict[str, object],
    ) -> dict[str, object]:
        _require_json(value)
        return value

    @model_validator(mode="after")
    def validate_card(self) -> Self:
        if CARD_TYPE.fullmatch(self.card_type) is None:
            raise ValueError("Card type must use lower snake case")
        known = (
            ResponseCardType(self.card_type)
            if self.card_type in {item.value for item in ResponseCardType}
            else None
        )
        if known is not None:
            if (
                self.known_type is not known
                or self.rendering is not CardRendering.KNOWN
                or self.fallback_title is not None
            ):
                raise ValueError("Known cards require exact known rendering identity")
        elif (
            self.known_type is not None
            or self.rendering is not CardRendering.UNKNOWN_FALLBACK
            or self.fallback_title is None
            or not self.fallback_title.strip()
        ):
            raise ValueError("Unknown cards require explicit fallback identity")
        if len({item.action for item in self.actions}) != len(self.actions):
            raise ValueError("Card actions must be unique")
        validate_core_card(
            card_type=self.card_type,
            state=self.state.value,
            knowledge_mode=self.knowledge_mode,
            provenance_class=self.provenance_class,
            confidence_score=(
                self.confidence.score if self.confidence is not None else None
            ),
            confidence_label=(
                self.confidence.label if self.confidence is not None else None
            ),
            confidence_reasons=(
                self.confidence.reasons
                if self.confidence is not None
                else ()
            ),
            source_ids=self.source_ids,
            actions=tuple(
                (action.action.value, action.state.value, action.target)
                for action in self.actions
            ),
            payload=self.payload,
        )
        validate_compliance_card(
            card_type=self.card_type,
            card_state=self.state.value,
            knowledge_mode=self.knowledge_mode,
            provenance_class=self.provenance_class,
            confidence_score=(
                self.confidence.score if self.confidence is not None else None
            ),
            confidence_label=(
                self.confidence.label if self.confidence is not None else None
            ),
            claim_ids=self.claim_ids,
            source_ids=self.source_ids,
            actions=tuple(
                (action.action.value, action.state.value, action.target)
                for action in self.actions
            ),
            payload=self.payload,
        )
        validate_change_card(
            card_type=self.card_type,
            card_state=self.state.value,
            knowledge_mode=self.knowledge_mode,
            provenance_class=self.provenance_class,
            confidence_label=(
                self.confidence.label if self.confidence is not None else None
            ),
            claim_ids=self.claim_ids,
            source_ids=self.source_ids,
            actions=tuple(
                (action.action.value, action.state.value, action.target)
                for action in self.actions
            ),
            payload=self.payload,
        )
        return self


class StructuredResponseSection(ResponseContractModel):
    schema_version: Literal["1"] = RESPONSE_CONTRACT_SCHEMA_VERSION
    section_id: str = Field(min_length=1, max_length=200)
    section_key: str = Field(min_length=1, max_length=200)
    order: int = Field(ge=0)
    strategy: ResponseStrategy
    title: str = Field(min_length=1, max_length=500)
    state: SectionTerminalState
    knowledge_mode: KnowledgeMode
    provenance_class: ProvenanceClass
    confidence: ResponseConfidenceSnapshot
    claim_ids: tuple[str, ...] = ()
    source_ids: tuple[str, ...] = ()
    assumptions: tuple[str, ...] = ()
    gaps: tuple[str, ...] = ()
    cards: tuple[ResponseCardEnvelope, ...]

    @field_validator("section_id", "section_key", "title")
    @classmethod
    def normalize_required_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Section identity text cannot be blank")
        return normalized

    @field_validator("claim_ids", "source_ids", "assumptions", "gaps")
    @classmethod
    def validate_unique_text(
        cls,
        value: tuple[str, ...],
        info: object,
    ) -> tuple[str, ...]:
        field_name = getattr(info, "field_name", "Section metadata")
        return _unique_text(value, field_name)

    @model_validator(mode="after")
    def validate_section(self) -> Self:
        expected_provenance = {
            KnowledgeMode.GROUNDED_REGULATORY: (
                ProvenanceClass.INTERNAL_REGULATORY_CORPUS
            ),
            KnowledgeMode.GENERAL_AI: ProvenanceClass.GENERAL_AI_KNOWLEDGE,
            KnowledgeMode.LIVE_INTELLIGENCE: ProvenanceClass.LIVE_WEB_SOURCES,
        }[self.knowledge_mode]
        if self.provenance_class is not expected_provenance:
            raise ValueError("Section mode and provenance must remain pure")
        if tuple(card.order for card in self.cards) != tuple(range(len(self.cards))):
            raise ValueError("Cards must use contiguous zero-based order")
        card_ids = tuple(card.card_id for card in self.cards)
        if len(set(card_ids)) != len(card_ids):
            raise ValueError("Card IDs must be unique within a section")
        if any(
            card.knowledge_mode is not self.knowledge_mode
            or card.provenance_class is not self.provenance_class
            for card in self.cards
        ):
            raise ValueError("Cards cannot cross their section provenance lane")
        if any(
            not set(card.claim_ids).issubset(self.claim_ids)
            or not set(card.source_ids).issubset(self.source_ids)
            for card in self.cards
        ):
            raise ValueError("Card references must belong to their section")
        return self


class StructuredResponseEnvelope(ResponseContractModel):
    schema_version: Literal["1"] = RESPONSE_CONTRACT_SCHEMA_VERSION
    policy_version: str = Field(
        default=RESPONSE_CONTRACT_POLICY_VERSION,
        min_length=1,
    )
    response_id: str = Field(min_length=1, max_length=200)
    response_strategy: ResponseStrategy
    sections: tuple[StructuredResponseSection, ...] = Field(min_length=1)
    overall_confidence: ResponseConfidenceSnapshot
    compatibility_summary: str = Field(min_length=1, max_length=50_000)
    assumptions: tuple[str, ...] = ()
    gaps: tuple[str, ...] = ()

    @field_validator("response_id", "compatibility_summary")
    @classmethod
    def normalize_required_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Response text cannot be blank")
        return normalized

    @field_validator("assumptions", "gaps")
    @classmethod
    def validate_unique_text(
        cls,
        value: tuple[str, ...],
        info: object,
    ) -> tuple[str, ...]:
        field_name = getattr(info, "field_name", "Response metadata")
        return _unique_text(value, field_name)

    @model_validator(mode="after")
    def validate_response(self) -> Self:
        if tuple(section.order for section in self.sections) != tuple(
            range(len(self.sections))
        ):
            raise ValueError("Sections must use contiguous zero-based order")
        section_ids = tuple(section.section_id for section in self.sections)
        section_keys = tuple(section.section_key for section in self.sections)
        if len(set(section_ids)) != len(section_ids):
            raise ValueError("Response section IDs must be unique")
        if len(set(section_keys)) != len(section_keys):
            raise ValueError("Response section keys must be unique")
        card_ids = tuple(
            card.card_id
            for section in self.sections
            for card in section.cards
        )
        if len(set(card_ids)) != len(card_ids):
            raise ValueError("Card IDs must be unique across a response")
        return self


def _require_json(value: object) -> None:
    if value is None or isinstance(value, str | bool | int):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("Card payload numbers must be finite")
        return
    if isinstance(value, list):
        for item in value:
            _require_json(item)
        return
    if isinstance(value, dict):
        if any(not isinstance(key, str) for key in value):
            raise ValueError("Card payload object keys must be strings")
        for item in value.values():
            _require_json(item)
        return
    raise ValueError("Card payload must contain JSON values only")
