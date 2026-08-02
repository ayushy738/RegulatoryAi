from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from collections.abc import Iterable
from datetime import UTC, datetime
from enum import StrEnum
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from backend.ask.decision import TimeDimension
from backend.ask.orchestration import ProvenanceClass
from backend.rag.timeline import TimelineEventRecord

EVENT_RECONCILIATION_SCHEMA_VERSION = "1"
EVENT_RECONCILIATION_POLICY_VERSION = "ask-ai-event-reconciliation-v1"


class EventReconciliationModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        strict=True,
        str_strip_whitespace=True,
    )


class EventReconciliationStatus(StrEnum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    NO_EVENTS = "no_events"


class EventMatchKind(StrEnum):
    STANDALONE = "standalone"
    EXACT_DUPLICATE = "exact_duplicate"
    NEAR_DUPLICATE = "near_duplicate"
    CONFLICT = "conflict"


class ConflictField(StrEnum):
    EVENT_IDENTITY = "event_identity"
    DATE = "date"
    EVENT_TYPE = "event_type"
    DESCRIPTION = "description"
    LEGAL_STATUS = "legal_status"


class ConfidenceEffect(StrEnum):
    NONE = "none"
    CONTRADICTION_PENALTY_REQUIRED = "contradiction_penalty_required"


class EventOriginObservation(EventReconciliationModel):
    event: TimelineEventRecord
    entity_ids: tuple[str, ...] = Field(min_length=1)
    event_fingerprint: str = Field(min_length=1, max_length=500)
    description_fingerprint: str = Field(min_length=1, max_length=500)
    published_at: datetime | None = None
    retrieved_at: datetime
    legal_status: str | None = Field(default=None, min_length=1, max_length=200)
    status_is_established: bool = False

    @field_validator("entity_ids")
    @classmethod
    def validate_entity_ids(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(item.strip() for item in value)
        if any(not item for item in normalized):
            raise ValueError("Event entity IDs cannot be blank")
        if len(normalized) != len(set(normalized)):
            raise ValueError("Event entity IDs must be unique")
        return normalized

    @field_validator("event_fingerprint", "description_fingerprint")
    @classmethod
    def validate_fingerprint(cls, value: str) -> str:
        normalized = _normalize(value)
        if not normalized:
            raise ValueError("Event fingerprints cannot be blank")
        return normalized

    @model_validator(mode="after")
    def validate_origin(self) -> Self:
        if self.event.provenance_class is ProvenanceClass.GENERAL_AI_KNOWLEDGE:
            raise ValueError("General AI cannot participate in event reconciliation")
        if self.event.provenance_class not in {
            ProvenanceClass.INTERNAL_REGULATORY_CORPUS,
            ProvenanceClass.LIVE_WEB_SOURCES,
        }:
            raise ValueError("Event origin uses an unsupported provenance lane")
        if not _aware(self.retrieved_at) or (
            self.published_at is not None and not _aware(self.published_at)
        ):
            raise ValueError("Event provenance times must be timezone-aware")
        if (
            self.event.provenance_class is ProvenanceClass.LIVE_WEB_SOURCES
            and self.published_at is None
        ):
            raise ValueError("Live event observations require publication time")
        if (
            self.event.provenance_class is ProvenanceClass.LIVE_WEB_SOURCES
            and self.status_is_established
        ):
            raise ValueError("Live reporting cannot establish legal status")
        if self.status_is_established and self.legal_status is None:
            raise ValueError("Established status requires an official status value")
        if (
            self.event.provenance_class
            is ProvenanceClass.INTERNAL_REGULATORY_CORPUS
            and self.legal_status is not None
            and not self.status_is_established
        ):
            raise ValueError("Official legal status must be explicitly established")
        return self


class EventReconciliationRequest(EventReconciliationModel):
    schema_version: Literal["1"] = EVENT_RECONCILIATION_SCHEMA_VERSION
    policy_version: Literal[
        "ask-ai-event-reconciliation-v1"
    ] = EVENT_RECONCILIATION_POLICY_VERSION
    question_id: str = Field(min_length=1)
    section_key: str = Field(min_length=1)
    evidence_input_cutoff_reached: bool
    origins: tuple[EventOriginObservation, ...]

    @model_validator(mode="after")
    def validate_request(self) -> Self:
        event_ids = tuple(item.event.event_id for item in self.origins)
        if len(event_ids) != len(set(event_ids)):
            raise ValueError("Event origin IDs must be unique")
        return self


class EventOriginView(EventReconciliationModel):
    event_id: str = Field(pattern=r"^timeline_event_[0-9a-f]{32}$")
    provenance_class: ProvenanceClass
    label: str = Field(min_length=1)
    event_type: str = Field(min_length=1)
    date_value: datetime | None
    date_semantic: TimeDimension
    source_ids: tuple[str, ...] = Field(min_length=1)
    ancestry: tuple[str, ...] = Field(min_length=1)
    published_at: datetime | None
    retrieved_at: datetime
    legal_status: str | None
    status_is_established: bool

    @model_validator(mode="after")
    def validate_view(self) -> Self:
        if self.provenance_class is ProvenanceClass.GENERAL_AI_KNOWLEDGE:
            raise ValueError("General AI cannot appear in an event origin view")
        if not _aware(self.retrieved_at) or (
            self.published_at is not None and not _aware(self.published_at)
        ):
            raise ValueError("Event origin view times must be timezone-aware")
        if len(self.source_ids) != len(set(self.source_ids)):
            raise ValueError("Event origin source IDs must be unique")
        if len(self.ancestry) != len(set(self.ancestry)):
            raise ValueError("Event origin ancestry must be unique")
        return self


class ConflictObservation(EventReconciliationModel):
    event_id: str = Field(pattern=r"^timeline_event_[0-9a-f]{32}$")
    provenance_class: ProvenanceClass
    value: str = Field(min_length=1)


class EventConflict(EventReconciliationModel):
    field: ConflictField
    observations: tuple[ConflictObservation, ...] = Field(min_length=2)

    @model_validator(mode="after")
    def validate_observations(self) -> Self:
        event_ids = tuple(item.event_id for item in self.observations)
        if len(event_ids) != len(set(event_ids)):
            raise ValueError("Conflict observations must reference unique events")
        return self


class ReconciledEvent(EventReconciliationModel):
    visual_event_id: str = Field(pattern=r"^visual_event_[0-9a-f]{32}$")
    event_fingerprint: str = Field(min_length=1)
    entity_ids: tuple[str, ...] = Field(min_length=1)
    event_key: str = Field(min_length=1)
    display_label: str = Field(min_length=1)
    display_event_type: str = Field(min_length=1)
    date_value: datetime | None
    date_semantic: TimeDimension | None
    match_kind: EventMatchKind
    official_basis: tuple[EventOriginView, ...] = ()
    live_coverage: tuple[EventOriginView, ...] = ()
    all_source_ids: tuple[str, ...] = Field(min_length=1)
    established_legal_status: str | None = None
    live_reported_statuses: tuple[str, ...] = ()
    conflicts: tuple[EventConflict, ...] = ()
    conflict_group_id: str | None = Field(
        default=None,
        pattern=r"^event_conflict_[0-9a-f]{32}$",
    )
    near_duplicate_group_id: str | None = Field(
        default=None,
        pattern=r"^event_near_[0-9a-f]{32}$",
    )
    confidence_effect: ConfidenceEffect
    high_confidence_allowed: bool

    @model_validator(mode="after")
    def validate_event(self) -> Self:
        if not self.official_basis and not self.live_coverage:
            raise ValueError("A reconciled event requires retained provenance")
        if any(
            item.provenance_class
            is not ProvenanceClass.INTERNAL_REGULATORY_CORPUS
            for item in self.official_basis
        ):
            raise ValueError("Official basis cannot contain another lane")
        if any(
            item.provenance_class is not ProvenanceClass.LIVE_WEB_SOURCES
            for item in self.live_coverage
        ):
            raise ValueError("Live coverage cannot contain another lane")
        expected_sources = _ordered_unique(
            source_id
            for item in (*self.official_basis, *self.live_coverage)
            for source_id in item.source_ids
        )
        if self.all_source_ids != expected_sources:
            raise ValueError("Reconciled source IDs must retain every origin")
        origin_count = len(self.official_basis) + len(self.live_coverage)
        if self.match_kind is EventMatchKind.STANDALONE and (
            origin_count != 1
            or self.conflicts
            or self.near_duplicate_group_id is not None
        ):
            raise ValueError("Standalone event shape is invalid")
        if self.match_kind is EventMatchKind.NEAR_DUPLICATE and (
            origin_count != 1
            or self.near_duplicate_group_id is None
            or self.conflicts
        ):
            raise ValueError("Near-duplicate events must remain inspectable")
        if self.match_kind is EventMatchKind.EXACT_DUPLICATE and (
            origin_count < 2 or self.conflicts
        ):
            raise ValueError("Exact duplicate requires multiple agreeing origins")
        if self.match_kind is EventMatchKind.CONFLICT and (
            not self.conflicts or self.conflict_group_id is None
        ):
            raise ValueError("Conflicting events require visible conflict detail")
        if bool(self.conflicts) != (
            self.confidence_effect
            is ConfidenceEffect.CONTRADICTION_PENALTY_REQUIRED
        ):
            raise ValueError("Conflict and confidence effect must agree")
        if self.high_confidence_allowed is bool(self.conflicts):
            raise ValueError("High confidence is forbidden for a conflict")
        return self


class EventReconciliationResult(EventReconciliationModel):
    schema_version: Literal["1"] = EVENT_RECONCILIATION_SCHEMA_VERSION
    policy_version: Literal[
        "ask-ai-event-reconciliation-v1"
    ] = EVENT_RECONCILIATION_POLICY_VERSION
    status: EventReconciliationStatus
    events: tuple[ReconciledEvent, ...] = ()
    notes: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_result(self) -> Self:
        if self.status is EventReconciliationStatus.NO_EVENTS and self.events:
            raise ValueError("No-events reconciliation cannot retain events")
        if self.status is EventReconciliationStatus.COMPLETE and (
            not self.events or any(event.conflicts for event in self.events)
        ):
            raise ValueError("Complete reconciliation cannot contain conflicts")
        if self.status is EventReconciliationStatus.PARTIAL and not any(
            event.conflicts for event in self.events
        ):
            raise ValueError("Partial reconciliation requires a visible conflict")
        visual_ids = tuple(event.visual_event_id for event in self.events)
        if len(visual_ids) != len(set(visual_ids)):
            raise ValueError("Visual event IDs must be unique")
        if len(self.notes) != len(set(self.notes)):
            raise ValueError("Reconciliation notes must be unique")
        return self


def reconcile_internal_live_events(
    request: EventReconciliationRequest,
) -> EventReconciliationResult:
    safe_request = EventReconciliationRequest.model_validate(
        request.model_dump(mode="python")
    )
    if not safe_request.evidence_input_cutoff_reached:
        raise ValueError("Event reconciliation cannot finalize before evidence cutoff")
    if not safe_request.origins:
        return EventReconciliationResult(
            status=EventReconciliationStatus.NO_EVENTS,
            notes=("no_events_to_reconcile",),
        )

    fingerprint_groups: dict[str, list[EventOriginObservation]] = {}
    for origin in safe_request.origins:
        fingerprint_groups.setdefault(origin.event_fingerprint, []).append(origin)

    events = [
        _reconcile_fingerprint_group(fingerprint, tuple(group))
        for fingerprint, group in sorted(fingerprint_groups.items())
    ]
    events = _mark_near_duplicates(events)
    events.sort(key=_event_sort_key)
    conflicts_present = any(event.conflicts for event in events)
    near_duplicates_present = any(
        event.match_kind is EventMatchKind.NEAR_DUPLICATE for event in events
    )
    notes: list[str] = []
    if any(
        event.match_kind is EventMatchKind.EXACT_DUPLICATE for event in events
    ):
        notes.append("exact_duplicates_consolidated")
    if near_duplicates_present:
        notes.append("near_duplicates_retained")
    if conflicts_present:
        notes.append("material_conflicts_retained")
    return EventReconciliationResult(
        status=(
            EventReconciliationStatus.PARTIAL
            if conflicts_present
            else EventReconciliationStatus.COMPLETE
        ),
        events=tuple(events),
        notes=tuple(notes),
    )


def event_reconciliation_result_json(result: EventReconciliationResult) -> str:
    return json.dumps(
        result.model_dump(mode="json"),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def _reconcile_fingerprint_group(
    fingerprint: str,
    origins: tuple[EventOriginObservation, ...],
) -> ReconciledEvent:
    ordered = tuple(sorted(origins, key=_origin_sort_key))
    official = tuple(
        _origin_view(origin)
        for origin in ordered
        if origin.event.provenance_class
        is ProvenanceClass.INTERNAL_REGULATORY_CORPUS
    )
    live = tuple(
        _origin_view(origin)
        for origin in ordered
        if origin.event.provenance_class is ProvenanceClass.LIVE_WEB_SOURCES
    )
    conflicts = _material_conflicts(ordered)
    established_values = _distinct_values(
        origin.legal_status
        for origin in ordered
        if origin.status_is_established
    )
    live_statuses = _distinct_values(
        origin.legal_status
        for origin in ordered
        if origin.event.provenance_class is ProvenanceClass.LIVE_WEB_SOURCES
    )
    dates = {
        (origin.event.payload.date_semantic, origin.event.payload.date_value)
        for origin in ordered
        if origin.event.payload.date_value is not None
    }
    date_semantics = {semantic for semantic, _ in dates}
    date_values = {value for _, value in dates}
    canonical_date = next(iter(date_values)) if len(date_values) == 1 else None
    canonical_semantic = (
        next(iter(date_semantics)) if len(date_semantics) == 1 else None
    )
    primary = ordered[0]
    match_kind = (
        EventMatchKind.CONFLICT
        if conflicts
        else (
            EventMatchKind.EXACT_DUPLICATE
            if len(ordered) > 1
            else EventMatchKind.STANDALONE
        )
    )
    visual_id = _stable_id(
        "visual_event_",
        fingerprint,
        *(origin.event.event_id for origin in ordered),
    )
    conflict_group_id = (
        _stable_id(
            "event_conflict_",
            fingerprint,
            *(conflict.field.value for conflict in conflicts),
            *(origin.event.event_id for origin in ordered),
        )
        if conflicts
        else None
    )
    return ReconciledEvent(
        visual_event_id=visual_id,
        event_fingerprint=fingerprint,
        entity_ids=tuple(sorted({item for origin in ordered for item in origin.entity_ids})),
        event_key=primary.event.event_key,
        display_label=primary.event.payload.label,
        display_event_type=primary.event.payload.event_type,
        date_value=canonical_date,
        date_semantic=canonical_semantic,
        match_kind=match_kind,
        official_basis=official,
        live_coverage=live,
        all_source_ids=_ordered_unique(
            source_id
            for item in (*official, *live)
            for source_id in item.source_ids
        ),
        established_legal_status=(
            established_values[0] if len(established_values) == 1 else None
        ),
        live_reported_statuses=live_statuses,
        conflicts=conflicts,
        conflict_group_id=conflict_group_id,
        confidence_effect=(
            ConfidenceEffect.CONTRADICTION_PENALTY_REQUIRED
            if conflicts
            else ConfidenceEffect.NONE
        ),
        high_confidence_allowed=not conflicts,
    )


def _material_conflicts(
    origins: tuple[EventOriginObservation, ...],
) -> tuple[EventConflict, ...]:
    candidates: tuple[
        tuple[
            ConflictField,
            tuple[tuple[EventOriginObservation, str, str], ...],
        ],
        ...,
    ] = (
        (
            ConflictField.EVENT_IDENTITY,
            tuple(
                (
                    origin,
                    "|".join(
                        (
                            _normalize(origin.event.event_key),
                            *sorted(origin.entity_ids),
                        )
                    ),
                    f"{origin.event.event_key} — "
                    f"{', '.join(sorted(origin.entity_ids))}",
                )
                for origin in origins
            ),
        ),
        (
            ConflictField.DATE,
            tuple(
                (
                    origin,
                    "|".join(
                        (
                            origin.event.payload.date_semantic.value,
                            origin.event.payload.date_value.isoformat(),
                        )
                    ),
                    " · ".join(
                        (
                            origin.event.payload.date_semantic.value,
                            origin.event.payload.date_value.isoformat(),
                        )
                    ),
                )
                for origin in origins
                if origin.event.payload.date_value is not None
            ),
        ),
        (
            ConflictField.EVENT_TYPE,
            tuple(
                (
                    origin,
                    origin.event.payload.event_type,
                    origin.event.payload.event_type,
                )
                for origin in origins
            ),
        ),
        (
            ConflictField.DESCRIPTION,
            tuple(
                (
                    origin,
                    origin.description_fingerprint,
                    origin.event.payload.label,
                )
                for origin in origins
            ),
        ),
        (
            ConflictField.LEGAL_STATUS,
            tuple(
                (origin, origin.legal_status, origin.legal_status)
                for origin in origins
                if origin.legal_status is not None
            ),
        ),
    )
    conflicts: list[EventConflict] = []
    for field, values in candidates:
        if len({_normalize(comparison) for _, comparison, _ in values}) < 2:
            continue
        conflicts.append(
            EventConflict(
                field=field,
                observations=tuple(
                    ConflictObservation(
                        event_id=origin.event.event_id,
                        provenance_class=origin.event.provenance_class,
                        value=display,
                    )
                    for origin, _, display in values
                ),
            )
        )
    return tuple(conflicts)


def _mark_near_duplicates(events: list[ReconciledEvent]) -> list[ReconciledEvent]:
    groups: dict[tuple[tuple[str, ...], str, str], list[int]] = {}
    for index, event in enumerate(events):
        if event.match_kind is not EventMatchKind.STANDALONE:
            continue
        groups.setdefault(
            (
                event.entity_ids,
                _normalize(event.event_key),
                _normalize(event.display_event_type),
            ),
            [],
        ).append(index)
    output = list(events)
    for key, indices in sorted(groups.items()):
        if len(indices) < 2:
            continue
        event_ids = tuple(output[index].visual_event_id for index in indices)
        group_id = _stable_id(
            "event_near_",
            *key[0],
            key[1],
            key[2],
            *event_ids,
        )
        for index in indices:
            values = output[index].model_dump(mode="python")
            values.update(
                {
                    "match_kind": EventMatchKind.NEAR_DUPLICATE,
                    "near_duplicate_group_id": group_id,
                }
            )
            output[index] = ReconciledEvent.model_validate(values)
    return output


def _origin_view(origin: EventOriginObservation) -> EventOriginView:
    return EventOriginView(
        event_id=origin.event.event_id,
        provenance_class=origin.event.provenance_class,
        label=origin.event.payload.label,
        event_type=origin.event.payload.event_type,
        date_value=origin.event.payload.date_value,
        date_semantic=origin.event.payload.date_semantic,
        source_ids=origin.event.source_ids,
        ancestry=origin.event.ancestry,
        published_at=origin.published_at,
        retrieved_at=origin.retrieved_at,
        legal_status=origin.legal_status,
        status_is_established=origin.status_is_established,
    )


def _origin_sort_key(
    origin: EventOriginObservation,
) -> tuple[int, str]:
    return (
        0
        if origin.event.provenance_class
        is ProvenanceClass.INTERNAL_REGULATORY_CORPUS
        else 1,
        origin.event.event_id,
    )


def _event_sort_key(
    event: ReconciledEvent,
) -> tuple[bool, datetime, str, str]:
    return (
        event.date_value is None,
        event.date_value or datetime.max.replace(tzinfo=UTC),
        event.event_key,
        event.visual_event_id,
    )


def _distinct_values(values: Iterable[str | None]) -> tuple[str, ...]:
    unique: dict[str, str] = {}
    for value in values:
        if value is None:
            continue
        unique.setdefault(_normalize(value), value.strip())
    return tuple(unique[key] for key in sorted(unique))


def _ordered_unique(values: Iterable[str]) -> tuple[str, ...]:
    output: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value not in seen:
            seen.add(value)
            output.append(value)
    return tuple(output)


def _aware(value: datetime) -> bool:
    return value.tzinfo is not None and value.utcoffset() is not None


def _normalize(value: str) -> str:
    return re.sub(
        r"\s+",
        " ",
        unicodedata.normalize("NFKC", value).casefold(),
    ).strip()


def _stable_id(prefix: str, *values: str) -> str:
    payload = "|".join(values)
    return prefix + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]
