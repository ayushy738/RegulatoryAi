from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from enum import StrEnum
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from backend.ask.decision import TimeDimension
from backend.ask.orchestration import ProvenanceClass, TimelineEventPayload

TIMELINE_BUILDER_SCHEMA_VERSION = "1"
TIMELINE_BUILDER_POLICY_VERSION = "ask-ai-timeline-builder-v1"


class TimelineModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class TimelineInputKind(StrEnum):
    OFFICIAL_EVIDENCE = "official_evidence"
    STRUCTURED_FACT = "structured_fact"
    LIVE_EVENT = "live_event"


class TimelineBuildStatus(StrEnum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    NO_EVENTS = "no_events"


class TimelineExclusionReason(StrEnum):
    OUTSIDE_MATERIAL_SCOPE = "outside_material_scope"
    OUTSIDE_QUESTION_SCOPE = "outside_question_scope"
    OUTSIDE_SECTION_SCOPE = "outside_section_scope"
    OUTSIDE_ENTITY_SCOPE = "outside_entity_scope"
    PROVENANCE_KIND_MISMATCH = "provenance_kind_mismatch"


class TimelineInputEvent(TimelineModel):
    input_artifact_id: str = Field(min_length=1)
    input_kind: TimelineInputKind
    event_key: str = Field(min_length=1)
    label: str = Field(min_length=1)
    event_type: str = Field(min_length=1)
    date_value: datetime | None = None
    date_semantic: TimeDimension
    date_confidence: float = Field(ge=0, le=1)
    critical_source_confidence: float = Field(ge=0, le=1)
    inferred_order: bool = False
    provenance_class: ProvenanceClass
    source_ids: tuple[str, ...] = Field(min_length=1)
    question_ids: tuple[str, ...] = Field(min_length=1)
    section_keys: tuple[str, ...] = Field(min_length=1)
    entity_ids: tuple[str, ...] = ()
    related_input_artifact_ids: tuple[str, ...] = ()
    discovery_only: bool = False
    material: bool = True

    @field_validator(
        "source_ids",
        "question_ids",
        "section_keys",
        "entity_ids",
        "related_input_artifact_ids",
    )
    @classmethod
    def validate_unique_text(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(item.strip() for item in value)
        if any(not item for item in normalized):
            raise ValueError("Timeline input identities cannot be blank")
        if len(normalized) != len(set(normalized)):
            raise ValueError("Timeline input identities must be unique")
        return normalized

    @model_validator(mode="after")
    def validate_input(self) -> Self:
        if self.date_value is not None and (
            self.date_value.tzinfo is None
            or self.date_value.utcoffset() is None
        ):
            raise ValueError("Timeline input dates must be timezone-aware")
        expected_provenance = {
            TimelineInputKind.OFFICIAL_EVIDENCE: (
                ProvenanceClass.INTERNAL_REGULATORY_CORPUS
            ),
            TimelineInputKind.STRUCTURED_FACT: (
                ProvenanceClass.INTERNAL_REGULATORY_CORPUS
            ),
            TimelineInputKind.LIVE_EVENT: ProvenanceClass.LIVE_WEB_SOURCES,
        }[self.input_kind]
        if self.provenance_class is not expected_provenance:
            raise ValueError("Timeline input kind and provenance do not match")
        if self.input_artifact_id in self.related_input_artifact_ids:
            raise ValueError("Timeline input cannot relate to itself")
        if self.date_confidence > self.critical_source_confidence:
            raise ValueError(
                "Timeline date confidence cannot exceed its critical source"
            )
        return self


class TimelineBuildRequest(TimelineModel):
    schema_version: Literal["1"] = TIMELINE_BUILDER_SCHEMA_VERSION
    policy_version: str = Field(
        default=TIMELINE_BUILDER_POLICY_VERSION,
        min_length=1,
    )
    question_id: str = Field(min_length=1)
    section_key: str = Field(min_length=1)
    entity_ids: tuple[str, ...] = ()
    evidence_input_cutoff_reached: bool
    inputs: tuple[TimelineInputEvent, ...]

    @model_validator(mode="after")
    def validate_request(self) -> Self:
        input_ids = tuple(item.input_artifact_id for item in self.inputs)
        if len(input_ids) != len(set(input_ids)):
            raise ValueError("Timeline input artifact IDs must be unique")
        if len(self.entity_ids) != len(set(self.entity_ids)):
            raise ValueError("Timeline request entity IDs must be unique")
        if any(not entity_id.strip() for entity_id in self.entity_ids):
            raise ValueError("Timeline request entity IDs cannot be blank")
        return self


class TimelineEventRecord(TimelineModel):
    event_id: str = Field(pattern=r"^timeline_event_[0-9a-f]{32}$")
    event_key: str = Field(min_length=1)
    payload: TimelineEventPayload
    provenance_class: ProvenanceClass
    source_ids: tuple[str, ...] = Field(min_length=1)
    ancestry: tuple[str, ...] = Field(min_length=1)
    discovery_only: bool
    conflict_group_id: str | None = None
    warnings: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_record(self) -> Self:
        if self.provenance_class is ProvenanceClass.GENERAL_AI_KNOWLEDGE:
            raise ValueError("General AI cannot produce Timeline Events")
        if self.payload.date_value is None and not self.payload.inferred_order:
            raise ValueError("Undated Timeline Events must mark inferred order")
        if len(self.source_ids) != len(set(self.source_ids)):
            raise ValueError("Timeline Event source IDs must be unique")
        if len(self.ancestry) != len(set(self.ancestry)):
            raise ValueError("Timeline Event ancestry must be unique")
        if len(self.warnings) != len(set(self.warnings)):
            raise ValueError("Timeline Event warnings must be unique")
        return self


class TimelineConflictSet(TimelineModel):
    conflict_group_id: str = Field(pattern=r"^timeline_conflict_[0-9a-f]{32}$")
    event_key: str = Field(min_length=1)
    date_semantic: TimeDimension
    event_ids: tuple[str, ...] = Field(min_length=2)

    @field_validator("event_ids")
    @classmethod
    def validate_event_ids(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if len(value) != len(set(value)):
            raise ValueError("Timeline conflict event IDs must be unique")
        return value


class TimelineInputExclusion(TimelineModel):
    input_artifact_id: str
    reason: TimelineExclusionReason


class TimelineBuildResult(TimelineModel):
    schema_version: Literal["1"] = TIMELINE_BUILDER_SCHEMA_VERSION
    policy_version: str = Field(
        default=TIMELINE_BUILDER_POLICY_VERSION,
        min_length=1,
    )
    status: TimelineBuildStatus
    events: tuple[TimelineEventRecord, ...] = ()
    conflicts: tuple[TimelineConflictSet, ...] = ()
    exclusions: tuple[TimelineInputExclusion, ...] = ()
    notes: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_result(self) -> Self:
        if self.status is TimelineBuildStatus.NO_EVENTS and self.events:
            raise ValueError("No-events Timeline result cannot contain events")
        if self.status is TimelineBuildStatus.COMPLETE and (
            not self.events or self.conflicts or self.exclusions
        ):
            raise ValueError("Complete Timeline result has no gaps or conflicts")
        if self.status is TimelineBuildStatus.PARTIAL and not (
            self.events or self.exclusions
        ):
            raise ValueError("Partial Timeline result requires retained state")
        event_ids = {event.event_id for event in self.events}
        if any(
            not set(conflict.event_ids).issubset(event_ids)
            for conflict in self.conflicts
        ):
            raise ValueError("Timeline conflicts must reference retained events")
        return self


def build_timeline(request: TimelineBuildRequest) -> TimelineBuildResult:
    safe_request = TimelineBuildRequest.model_validate(
        request.model_dump(mode="python")
    )
    if not safe_request.evidence_input_cutoff_reached:
        raise ValueError("Timeline cannot finalize before evidence input cutoff")

    admitted: list[TimelineInputEvent] = []
    exclusions: list[TimelineInputExclusion] = []
    for item in safe_request.inputs:
        reason = _scope_exclusion(safe_request, item)
        if reason is None:
            admitted.append(item)
        else:
            exclusions.append(
                TimelineInputExclusion(
                    input_artifact_id=item.input_artifact_id,
                    reason=reason,
                )
            )

    records = [_event_record(item) for item in admitted]
    event_id_by_input = {
        item.input_artifact_id: record.event_id
        for item, record in zip(admitted, records, strict=True)
    }
    records = [
        _attach_event_relationships(item, record, event_id_by_input)
        for item, record in zip(admitted, records, strict=True)
    ]
    conflicts = _conflicts(records)
    conflict_by_event = {
        event_id: conflict.conflict_group_id
        for conflict in conflicts
        for event_id in conflict.event_ids
    }
    records = [
        record.model_copy(
            update={
                "conflict_group_id": conflict_by_event.get(record.event_id),
                "warnings": tuple(
                    (
                        *record.warnings,
                        *(
                            ("conflicting_date_evidence",)
                            if record.event_id in conflict_by_event
                            else ()
                        ),
                    )
                ),
            }
        )
        for record in records
    ]
    records.sort(key=_event_sort_key)
    notes = tuple(
        (
            *(("undated_events_retained",) if any(
                event.payload.date_value is None for event in records
            ) else ()),
            *(("date_conflicts_retained",) if conflicts else ()),
            *(("out_of_scope_inputs_excluded",) if exclusions else ()),
        )
    )
    status = (
        TimelineBuildStatus.NO_EVENTS
        if not records
        else (
            TimelineBuildStatus.PARTIAL
            if conflicts
            or exclusions
            or any(event.payload.date_value is None for event in records)
            else TimelineBuildStatus.COMPLETE
        )
    )
    return TimelineBuildResult(
        status=status,
        events=tuple(records),
        conflicts=conflicts,
        exclusions=tuple(exclusions),
        notes=notes,
    )


def timeline_build_result_json(result: TimelineBuildResult) -> str:
    return json.dumps(
        result.model_dump(mode="json"),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def _scope_exclusion(
    request: TimelineBuildRequest,
    item: TimelineInputEvent,
) -> TimelineExclusionReason | None:
    if not item.material:
        return TimelineExclusionReason.OUTSIDE_MATERIAL_SCOPE
    if request.question_id not in item.question_ids:
        return TimelineExclusionReason.OUTSIDE_QUESTION_SCOPE
    if request.section_key not in item.section_keys:
        return TimelineExclusionReason.OUTSIDE_SECTION_SCOPE
    if request.entity_ids and not set(request.entity_ids) & set(item.entity_ids):
        return TimelineExclusionReason.OUTSIDE_ENTITY_SCOPE
    return None


def _event_record(item: TimelineInputEvent) -> TimelineEventRecord:
    warnings = tuple(
        (
            *(("missing_date",) if item.date_value is None else ()),
            *(("discovery_only_graph_fact",) if item.discovery_only else ()),
        )
    )
    return TimelineEventRecord(
        event_id=_event_id(item),
        event_key=item.event_key,
        payload=TimelineEventPayload(
            label=item.label,
            event_type=item.event_type,
            date_value=item.date_value,
            date_semantic=item.date_semantic,
            date_confidence=item.date_confidence,
            inferred_order=item.inferred_order or item.date_value is None,
            related_event_ids=(),
        ),
        provenance_class=item.provenance_class,
        source_ids=item.source_ids,
        ancestry=(item.input_artifact_id,),
        discovery_only=item.discovery_only,
        warnings=warnings,
    )


def _conflicts(
    records: list[TimelineEventRecord],
) -> tuple[TimelineConflictSet, ...]:
    groups: dict[tuple[str, TimeDimension], list[TimelineEventRecord]] = {}
    for record in records:
        groups.setdefault(
            (record.event_key, record.payload.date_semantic),
            [],
        ).append(record)
    output: list[TimelineConflictSet] = []
    for (event_key, semantic), grouped in sorted(
        groups.items(),
        key=lambda item: (item[0][0], item[0][1].value),
    ):
        dated = [item for item in grouped if item.payload.date_value is not None]
        if len({item.payload.date_value for item in dated}) < 2:
            continue
        event_ids = tuple(sorted(item.event_id for item in dated))
        output.append(
            TimelineConflictSet(
                conflict_group_id=_conflict_id(event_key, semantic, event_ids),
                event_key=event_key,
                date_semantic=semantic,
                event_ids=event_ids,
            )
        )
    return tuple(output)


def _attach_event_relationships(
    item: TimelineInputEvent,
    record: TimelineEventRecord,
    event_id_by_input: dict[str, str],
) -> TimelineEventRecord:
    related_event_ids = tuple(
        event_id_by_input[input_id]
        for input_id in item.related_input_artifact_ids
        if input_id in event_id_by_input
    )
    unresolved = any(
        input_id not in event_id_by_input
        for input_id in item.related_input_artifact_ids
    )
    values = record.model_dump(mode="python")
    values["payload"]["related_event_ids"] = related_event_ids
    if unresolved:
        values["warnings"] = (*record.warnings, "unresolved_event_relationship")
    return TimelineEventRecord.model_validate(values)


def _event_sort_key(
    event: TimelineEventRecord,
) -> tuple[bool, datetime, str, str, str]:
    return (
        event.payload.date_value is None,
        event.payload.date_value or datetime.max.replace(tzinfo=UTC),
        event.payload.date_semantic.value,
        event.event_key,
        event.event_id,
    )


def _event_id(item: TimelineInputEvent) -> str:
    payload = "|".join(
        (
            item.input_artifact_id,
            item.event_key,
            item.date_semantic.value,
            item.date_value.isoformat() if item.date_value is not None else "",
            item.provenance_class.value,
        )
    )
    return "timeline_event_" + hashlib.sha256(
        payload.encode("utf-8")
    ).hexdigest()[:32]


def _conflict_id(
    event_key: str,
    semantic: TimeDimension,
    event_ids: tuple[str, ...],
) -> str:
    payload = "|".join((event_key, semantic.value, *event_ids))
    return "timeline_conflict_" + hashlib.sha256(
        payload.encode("utf-8")
    ).hexdigest()[:32]
