from __future__ import annotations

import json
from datetime import datetime
from enum import StrEnum
from typing import Literal, Self
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from backend.ask.compliance_cards import CardEvidenceReference
from backend.ask.core_cards import (
    StructuredDateField,
    StructuredFieldState,
    StructuredTextField,
)
from backend.ask.decision.models import ConfidenceLabel, KnowledgeMode
from backend.ask.orchestration.contracts import ProvenanceClass

CHANGE_CARD_SCHEMA_VERSION = "1"


class ChangeCardModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        strict=True,
        str_strip_whitespace=True,
    )


class EventOrigin(StrEnum):
    OFFICIAL = "official"
    LIVE = "live"


class LiveSourceReference(ChangeCardModel):
    claim_id: str = Field(min_length=1, max_length=200)
    source_id: str = Field(min_length=1, max_length=200)
    publisher: str = Field(min_length=1, max_length=500)
    source_type: str = Field(min_length=1, max_length=200)
    publication_at: datetime
    retrieved_at: datetime
    ui_badge: str = Field(min_length=1, max_length=200)
    attribution: str = Field(min_length=1, max_length=500)
    url: str = Field(min_length=1, max_length=4_000)

    @model_validator(mode="after")
    def validate_source(self) -> Self:
        if any(
            value.tzinfo is None or value.utcoffset() is None
            for value in (self.publication_at, self.retrieved_at)
        ):
            raise ValueError("Live source timestamps must be timezone-aware")
        if self.retrieved_at < self.publication_at:
            raise ValueError("Live retrieval cannot precede publication")
        parsed = urlsplit(self.url)
        if parsed.scheme != "https" or not parsed.hostname:
            raise ValueError("Live source URL must be absolute HTTPS")
        if parsed.username is not None or parsed.password is not None:
            raise ValueError("Live source URL cannot contain credentials")
        return self


class TimelineEventCardPayload(ChangeCardModel):
    schema_version: Literal["1"] = CHANGE_CARD_SCHEMA_VERSION
    date: StructuredDateField
    event_type: StructuredTextField
    event_title: StructuredTextField
    significance: StructuredTextField
    origin: EventOrigin
    source_label: StructuredTextField
    related_prior_event_id: str | None = Field(default=None, max_length=200)
    related_next_event_id: str | None = Field(default=None, max_length=200)
    official_evidence_references: tuple[CardEvidenceReference, ...] = ()
    live_source: LiveSourceReference | None = None

    @model_validator(mode="after")
    def validate_origin(self) -> Self:
        _validate_official_references(self.official_evidence_references)
        if self.origin is EventOrigin.OFFICIAL:
            if not self.official_evidence_references or self.live_source is not None:
                raise ValueError("Official timeline event requires official evidence only")
        elif self.live_source is None or self.official_evidence_references:
            raise ValueError("Live timeline event requires one live source only")
        if (
            self.related_prior_event_id is not None
            and self.related_prior_event_id == self.related_next_event_id
        ):
            raise ValueError("Prior and next event identities must differ")
        return self


class AmendmentCardPayload(ChangeCardModel):
    schema_version: Literal["1"] = CHANGE_CARD_SCHEMA_VERSION
    amending_instrument: StructuredTextField
    amended_instrument: StructuredTextField
    issue_date: StructuredDateField
    effective_date: StructuredDateField
    provisions_affected: tuple[str, ...]
    change_summary: StructuredTextField
    stakeholders_affected: tuple[str, ...]
    amending_source_id: str | None = Field(default=None, max_length=200)
    amended_source_id: str | None = Field(default=None, max_length=200)
    evidence_references: tuple[CardEvidenceReference, ...]

    @field_validator("provisions_affected", "stakeholders_affected")
    @classmethod
    def validate_lists(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        _validate_unique_text(value)
        return value

    @model_validator(mode="after")
    def validate_references(self) -> Self:
        _validate_official_references(self.evidence_references)
        return self


class ComparisonDimension(ChangeCardModel):
    dimension: str = Field(min_length=1, max_length=500)
    side_a: StructuredTextField
    side_b: StructuredTextField
    relationship_or_difference: StructuredTextField
    side_a_evidence_references: tuple[CardEvidenceReference, ...] = ()
    side_b_evidence_references: tuple[CardEvidenceReference, ...] = ()

    @model_validator(mode="after")
    def validate_sides(self) -> Self:
        _validate_official_references(self.side_a_evidence_references)
        _validate_official_references(self.side_b_evidence_references)
        side_a_citations = {
            item.citation_id for item in self.side_a_evidence_references
        }
        side_b_citations = {
            item.citation_id for item in self.side_b_evidence_references
        }
        if side_a_citations & side_b_citations:
            raise ValueError("Comparison sides require independent citations")
        for field, references in (
            (self.side_a, self.side_a_evidence_references),
            (self.side_b, self.side_b_evidence_references),
        ):
            if (field.state is StructuredFieldState.ESTABLISHED) != bool(references):
                raise ValueError("Each comparison side requires independent evidence")
        return self


class ComparisonCardPayload(ChangeCardModel):
    schema_version: Literal["1"] = CHANGE_CARD_SCHEMA_VERSION
    side_a_label: str = Field(min_length=1, max_length=500)
    side_b_label: str = Field(min_length=1, max_length=500)
    dimensions: tuple[ComparisonDimension, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_dimensions(self) -> Self:
        labels = tuple(item.dimension for item in self.dimensions)
        if len(labels) != len(set(labels)):
            raise ValueError("Comparison dimensions must be unique")
        return self


class LiveNewsCardPayload(ChangeCardModel):
    schema_version: Literal["1"] = CHANGE_CARD_SCHEMA_VERSION
    headline: str = Field(min_length=1, max_length=1_000)
    relevance_explanation: str = Field(min_length=1, max_length=2_000)
    live_source: LiveSourceReference


class RelatedRegulationCardPayload(ChangeCardModel):
    schema_version: Literal["1"] = CHANGE_CARD_SCHEMA_VERSION
    related_entity_or_document: StructuredTextField
    related_entity_id: str | None = Field(default=None, max_length=200)
    relationship_type: StructuredTextField
    explanation: StructuredTextField
    provenance_label: StructuredTextField
    evidence_references: tuple[CardEvidenceReference, ...]

    @model_validator(mode="after")
    def validate_references(self) -> Self:
        _validate_official_references(self.evidence_references)
        return self


_PAYLOADS: dict[str, type[ChangeCardModel]] = {
    "timeline_event": TimelineEventCardPayload,
    "amendment": AmendmentCardPayload,
    "comparison": ComparisonCardPayload,
    "live_news": LiveNewsCardPayload,
    "related_regulation": RelatedRegulationCardPayload,
}


def validate_change_card(
    *,
    card_type: str,
    card_state: str,
    knowledge_mode: KnowledgeMode,
    provenance_class: ProvenanceClass,
    confidence_label: ConfidenceLabel | None,
    claim_ids: tuple[str, ...],
    source_ids: tuple[str, ...],
    actions: tuple[tuple[str, str, str | None], ...],
    payload: dict[str, object],
) -> None:
    model = _PAYLOADS.get(card_type)
    if model is None:
        return
    try:
        parsed = model.model_validate_json(json.dumps(payload, allow_nan=False))
    except (TypeError, ValueError) as error:
        raise ValueError(f"Invalid {card_type} payload") from error
    if confidence_label is None:
        raise ValueError("Change and intelligence cards require confidence")

    expected_mode, expected_provenance = _expected_lane(card_type, parsed)
    if knowledge_mode is not expected_mode or provenance_class is not expected_provenance:
        raise ValueError("Change card mode and provenance do not match its source lane")

    reference_claims, reference_sources, citation_ids = _identities(parsed)
    if reference_claims != set(claim_ids) or reference_sources != set(source_ids):
        raise ValueError("Change card evidence must match envelope references")

    incomplete = _incomplete(parsed)
    if card_state == "ready" and incomplete:
        raise ValueError("Ready change cards require all frozen fields")
    if card_state == "partial" and (not incomplete or not reference_sources):
        raise ValueError("Partial change cards require evidence and visible gaps")
    if card_state not in {"ready", "partial"}:
        raise ValueError("Change cards support only Ready or Partial state")
    if card_state == "partial" and confidence_label is ConfidenceLabel.HIGH:
        raise ValueError("Partial change cards cannot be High confidence")

    _validate_actions(
        card_type=card_type,
        parsed=parsed,
        actions=actions,
        citation_ids=citation_ids,
        claim_ids=set(claim_ids),
    )


def _expected_lane(
    card_type: str,
    parsed: ChangeCardModel,
) -> tuple[KnowledgeMode, ProvenanceClass]:
    live = card_type == "live_news" or (
        isinstance(parsed, TimelineEventCardPayload)
        and parsed.origin is EventOrigin.LIVE
    )
    if live:
        return KnowledgeMode.LIVE_INTELLIGENCE, ProvenanceClass.LIVE_WEB_SOURCES
    return (
        KnowledgeMode.GROUNDED_REGULATORY,
        ProvenanceClass.INTERNAL_REGULATORY_CORPUS,
    )


def _identities(parsed: ChangeCardModel) -> tuple[set[str], set[str], set[str]]:
    official: list[CardEvidenceReference] = []
    live: list[LiveSourceReference] = []
    if isinstance(parsed, TimelineEventCardPayload):
        official.extend(parsed.official_evidence_references)
        if parsed.live_source is not None:
            live.append(parsed.live_source)
    elif isinstance(parsed, AmendmentCardPayload):
        official.extend(parsed.evidence_references)
    elif isinstance(parsed, ComparisonCardPayload):
        for dimension in parsed.dimensions:
            official.extend(dimension.side_a_evidence_references)
            official.extend(dimension.side_b_evidence_references)
    elif isinstance(parsed, LiveNewsCardPayload):
        live.append(parsed.live_source)
    else:
        assert isinstance(parsed, RelatedRegulationCardPayload)
        official.extend(parsed.evidence_references)
    return (
        {item.claim_id for item in (*official, *live)},
        {item.source_id for item in (*official, *live)},
        {item.citation_id for item in official},
    )


def _incomplete(parsed: ChangeCardModel) -> bool:
    missing = StructuredFieldState.NOT_ESTABLISHED
    if isinstance(parsed, TimelineEventCardPayload):
        return any(
            field.state is missing
            for field in (
                parsed.date,
                parsed.event_type,
                parsed.event_title,
                parsed.significance,
                parsed.source_label,
            )
        )
    if isinstance(parsed, AmendmentCardPayload):
        return (
            any(
                field.state is missing
                for field in (
                    parsed.amending_instrument,
                    parsed.amended_instrument,
                    parsed.issue_date,
                    parsed.effective_date,
                    parsed.change_summary,
                )
            )
            or not parsed.provisions_affected
            or not parsed.stakeholders_affected
            or parsed.amending_source_id is None
            or parsed.amended_source_id is None
        )
    if isinstance(parsed, ComparisonCardPayload):
        return any(
            field.state is missing
            for item in parsed.dimensions
            for field in (item.side_a, item.side_b, item.relationship_or_difference)
        )
    if isinstance(parsed, LiveNewsCardPayload):
        return False
    assert isinstance(parsed, RelatedRegulationCardPayload)
    return (
        any(
            field.state is missing
            for field in (
                parsed.related_entity_or_document,
                parsed.relationship_type,
                parsed.explanation,
                parsed.provenance_label,
            )
        )
        or parsed.related_entity_id is None
    )


def _validate_actions(
    *,
    card_type: str,
    parsed: ChangeCardModel,
    actions: tuple[tuple[str, str, str | None], ...],
    citation_ids: set[str],
    claim_ids: set[str],
) -> None:
    action_map = {name: (state, target) for name, state, target in actions}
    if card_type == "timeline_event":
        assert isinstance(parsed, TimelineEventCardPayload)
        expected = (
            {"inspect_evidence"}
            if parsed.origin is EventOrigin.OFFICIAL
            else {"open_source"}
        )
    elif card_type == "amendment":
        expected = {"inspect_evidence", "compare"}
    elif card_type == "comparison":
        expected = {"inspect_evidence"}
    elif card_type == "live_news":
        expected = {"open_source", "find_official_basis"}
    else:
        expected = {"inspect_evidence", "open_entity"}
    if set(action_map) != expected:
        raise ValueError(f"{card_type} card actions do not match policy")

    if "inspect_evidence" in expected:
        _require_available_target(action_map["inspect_evidence"], citation_ids)
    if "open_source" in expected:
        source = (
            parsed.live_source
            if isinstance(parsed, (TimelineEventCardPayload, LiveNewsCardPayload))
            else None
        )
        assert source is not None
        _require_available_target(action_map["open_source"], {source.url})
    if "find_official_basis" in expected:
        _require_available_target(action_map["find_official_basis"], claim_ids)
    if "compare" in expected:
        assert isinstance(parsed, AmendmentCardPayload)
        target = (
            f"{parsed.amending_source_id}:{parsed.amended_source_id}"
            if parsed.amending_source_id and parsed.amended_source_id
            else None
        )
        _require_optional_target(action_map["compare"], {target} if target else set())
    if "open_entity" in expected:
        assert isinstance(parsed, RelatedRegulationCardPayload)
        targets = {parsed.related_entity_id} if parsed.related_entity_id else set()
        _require_optional_target(action_map["open_entity"], targets)


def _require_available_target(
    action: tuple[str, str | None],
    allowed: set[str],
) -> None:
    if action[0] != "available" or action[1] not in allowed:
        raise ValueError("Change-card action has the wrong evidence target")


def _require_optional_target(
    action: tuple[str, str | None],
    allowed: set[str | None],
) -> None:
    targets = {item for item in allowed if item is not None}
    if targets:
        _require_available_target(action, targets)
    elif action != ("disabled", None):
        raise ValueError("Unavailable change-card action must be disabled")


def _validate_official_references(
    references: tuple[CardEvidenceReference, ...],
) -> None:
    citation_ids = tuple(item.citation_id for item in references)
    pairs = tuple((item.claim_id, item.source_id) for item in references)
    if len(citation_ids) != len(set(citation_ids)) or len(pairs) != len(set(pairs)):
        raise ValueError("Official evidence references must be unique")


def _validate_unique_text(values: tuple[str, ...]) -> None:
    if any(not item.strip() for item in values) or len(values) != len(set(values)):
        raise ValueError("Structured lists require unique nonblank values")
