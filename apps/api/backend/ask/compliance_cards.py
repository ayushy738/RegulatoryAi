from __future__ import annotations

import json
import math
from enum import StrEnum
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from backend.ask.core_cards import (
    StructuredDateField,
    StructuredFieldState,
    StructuredTextField,
)
from backend.ask.decision.models import ConfidenceLabel, KnowledgeMode
from backend.ask.orchestration.contracts import ProvenanceClass

COMPLIANCE_CARD_SCHEMA_VERSION = "1"


class ComplianceCardModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        strict=True,
        str_strip_whitespace=True,
    )


class CardEvidenceReference(ComplianceCardModel):
    citation_id: str = Field(min_length=1, max_length=200)
    claim_id: str = Field(min_length=1, max_length=200)
    source_id: str = Field(min_length=1, max_length=200)
    marker: str = Field(min_length=1, max_length=50)
    locator: StructuredTextField


class DeadlineStatus(StrEnum):
    UPCOMING = "upcoming"
    TODAY = "today"
    ELAPSED = "elapsed"
    EXTENDED = "extended"
    UNVERIFIED = "unverified"


class ObligationPayload(ComplianceCardModel):
    schema_version: Literal["1"] = COMPLIANCE_CARD_SCHEMA_VERSION
    responsible_party: StructuredTextField
    required_action: StructuredTextField
    timing_or_frequency: StructuredTextField
    trigger_or_scope: StructuredTextField
    jurisdiction: StructuredTextField
    official_basis: StructuredTextField
    evidence_references: tuple[CardEvidenceReference, ...]

    @model_validator(mode="after")
    def validate_references(self) -> Self:
        _validate_references(self.evidence_references)
        return self


class DeadlinePayload(ComplianceCardModel):
    schema_version: Literal["1"] = COMPLIANCE_CARD_SCHEMA_VERSION
    date: StructuredDateField
    deadline_type: StructuredTextField
    responsible_stakeholder: StructuredTextField
    status: DeadlineStatus
    source_label: StructuredTextField
    evidence_references: tuple[CardEvidenceReference, ...]

    @model_validator(mode="after")
    def validate_references(self) -> Self:
        _validate_references(self.evidence_references)
        return self


class StakeholderPayload(ComplianceCardModel):
    schema_version: Literal["1"] = COMPLIANCE_CARD_SCHEMA_VERSION
    stakeholder: StructuredTextField
    stakeholder_entity_id: str | None = Field(default=None, max_length=200)
    role: StructuredTextField
    impact: StructuredTextField
    obligations: tuple[str, ...]
    relevant_regulations: tuple[str, ...]
    jurisdiction: StructuredTextField
    evidence_coverage_percent: float = Field(ge=0, le=100)
    evidence_references: tuple[CardEvidenceReference, ...]

    @field_validator("obligations", "relevant_regulations")
    @classmethod
    def validate_unique_text(
        cls,
        value: tuple[str, ...],
        info: object,
    ) -> tuple[str, ...]:
        normalized = tuple(item.strip() for item in value)
        if any(not item for item in normalized):
            raise ValueError(f"{getattr(info, 'field_name', 'Values')} cannot be blank")
        if len(normalized) != len(set(normalized)):
            raise ValueError(f"{getattr(info, 'field_name', 'Values')} must be unique")
        return normalized

    @field_validator("evidence_coverage_percent")
    @classmethod
    def validate_coverage(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("Evidence coverage must be finite")
        return value

    @model_validator(mode="after")
    def validate_references(self) -> Self:
        _validate_references(self.evidence_references)
        if self.stakeholder_entity_id is not None and not self.stakeholder_entity_id.strip():
            raise ValueError("Stakeholder entity ID cannot be blank")
        return self


_PAYLOADS: dict[str, type[ComplianceCardModel]] = {
    "obligation": ObligationPayload,
    "deadline": DeadlinePayload,
    "stakeholder": StakeholderPayload,
}


def validate_compliance_card(
    *,
    card_type: str,
    card_state: str,
    knowledge_mode: KnowledgeMode,
    provenance_class: ProvenanceClass,
    confidence_score: float | None,
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
    if (
        knowledge_mode is not KnowledgeMode.GROUNDED_REGULATORY
        or provenance_class is not ProvenanceClass.INTERNAL_REGULATORY_CORPUS
    ):
        raise ValueError("Compliance cards require grounded official provenance")
    if confidence_score is None or confidence_label is None:
        raise ValueError("Compliance cards require confidence")

    references = parsed.evidence_references  # type: ignore[attr-defined]
    reference_claims = {reference.claim_id for reference in references}
    reference_sources = {reference.source_id for reference in references}
    if reference_claims != set(claim_ids) or reference_sources != set(source_ids):
        raise ValueError("Compliance card evidence must match envelope references")
    incomplete = _payload_incomplete(parsed)
    if card_state == "ready":
        if incomplete or not references:
            raise ValueError("Ready compliance cards require complete cited fields")
    elif card_state == "partial":
        if not incomplete or not references:
            raise ValueError("Partial compliance cards require cited missing fields")
        if confidence_label is ConfidenceLabel.HIGH:
            raise ValueError("Partial compliance cards cannot be High confidence")
    elif card_state == "not_established":
        if (
            references
            or claim_ids
            or source_ids
            or not incomplete
            or _payload_has_established_content(parsed)
        ):
            raise ValueError("Not-established compliance cards cannot claim evidence")
        if confidence_label is not ConfidenceLabel.UNKNOWN:
            raise ValueError("Not-established compliance cards must be Unknown")
    else:
        raise ValueError("Compliance cards cannot use unavailable state")

    action_map = {action: (state, target) for action, state, target in actions}
    expected = {
        "obligation": {"inspect_evidence", "check_applicability"},
        "deadline": {"inspect_evidence", "add_to_tracker"},
        "stakeholder": {"inspect_evidence", "open_entity"},
    }[card_type]
    if set(action_map) != expected:
        raise ValueError(f"{card_type} card actions do not match policy")
    citation_ids = {reference.citation_id for reference in references}
    _validate_reference_action(action_map["inspect_evidence"], citation_ids)

    if card_type == "obligation":
        _validate_optional_action(action_map["check_applicability"], set(claim_ids))
    elif card_type == "deadline":
        if action_map["add_to_tracker"] != ("disabled", None):
            raise ValueError("Deadline tracking remains disabled in this phase")
    else:
        assert isinstance(parsed, StakeholderPayload)
        entity_targets = (
            {parsed.stakeholder_entity_id}
            if parsed.stakeholder_entity_id is not None
            else set()
        )
        _validate_optional_action(action_map["open_entity"], entity_targets)


def _validate_references(references: tuple[CardEvidenceReference, ...]) -> None:
    citation_ids = tuple(item.citation_id for item in references)
    pairs = tuple((item.claim_id, item.source_id) for item in references)
    if len(citation_ids) != len(set(citation_ids)) or len(pairs) != len(set(pairs)):
        raise ValueError("Card evidence references must be unique")


def _payload_incomplete(parsed: ComplianceCardModel) -> bool:
    if isinstance(parsed, ObligationPayload):
        fields = (
            parsed.responsible_party,
            parsed.required_action,
            parsed.timing_or_frequency,
            parsed.trigger_or_scope,
            parsed.jurisdiction,
            parsed.official_basis,
        )
        return any(field.state is StructuredFieldState.NOT_ESTABLISHED for field in fields)
    if isinstance(parsed, DeadlinePayload):
        fields = (
            parsed.deadline_type,
            parsed.responsible_stakeholder,
            parsed.source_label,
        )
        return (
            parsed.date.state is StructuredFieldState.NOT_ESTABLISHED
            or any(field.state is StructuredFieldState.NOT_ESTABLISHED for field in fields)
            or parsed.status is DeadlineStatus.UNVERIFIED
        )
    assert isinstance(parsed, StakeholderPayload)
    fields = (parsed.stakeholder, parsed.role, parsed.impact, parsed.jurisdiction)
    return (
        any(field.state is StructuredFieldState.NOT_ESTABLISHED for field in fields)
        or not parsed.obligations
        or not parsed.relevant_regulations
        or parsed.evidence_coverage_percent == 0
    )


def _payload_has_established_content(parsed: ComplianceCardModel) -> bool:
    if isinstance(parsed, ObligationPayload):
        fields = (
            parsed.responsible_party,
            parsed.required_action,
            parsed.timing_or_frequency,
            parsed.trigger_or_scope,
            parsed.jurisdiction,
            parsed.official_basis,
        )
        return any(field.state is StructuredFieldState.ESTABLISHED for field in fields)
    if isinstance(parsed, DeadlinePayload):
        fields = (
            parsed.deadline_type,
            parsed.responsible_stakeholder,
            parsed.source_label,
        )
        return (
            parsed.date.state is StructuredFieldState.ESTABLISHED
            or any(field.state is StructuredFieldState.ESTABLISHED for field in fields)
            or parsed.status is not DeadlineStatus.UNVERIFIED
        )
    assert isinstance(parsed, StakeholderPayload)
    fields = (parsed.stakeholder, parsed.role, parsed.impact, parsed.jurisdiction)
    return (
        any(field.state is StructuredFieldState.ESTABLISHED for field in fields)
        or bool(parsed.obligations)
        or bool(parsed.relevant_regulations)
        or parsed.evidence_coverage_percent > 0
        or parsed.stakeholder_entity_id is not None
    )


def _validate_reference_action(
    action: tuple[str, str | None],
    allowed_targets: set[str],
) -> None:
    state, target = action
    if allowed_targets:
        if state != "available" or target not in allowed_targets:
            raise ValueError("Inspect evidence must target a card citation")
    elif state != "disabled" or target is not None:
        raise ValueError("Inspect evidence must disable without citations")


def _validate_optional_action(
    action: tuple[str, str | None],
    allowed_targets: set[str | None],
) -> None:
    state, target = action
    allowed = {item for item in allowed_targets if item is not None}
    if allowed:
        if state != "available" or target not in allowed:
            raise ValueError("Available card action has the wrong target")
    elif state != "disabled" or target is not None:
        raise ValueError("Unavailable card action must be disabled")
