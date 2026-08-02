from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

VERSION_STATUS_SCHEMA_VERSION = "1"
VERSION_STATUS_POLICY_VERSION = "ask-ai-version-status-v1"


class DocumentLegalStatus(StrEnum):
    DRAFT = "draft"
    CONSULTATION = "consultation"
    IN_FORCE = "in_force"
    SUPERSEDED = "superseded"
    REPEALED = "repealed"
    UNKNOWN = "unknown"


class VersionRelationshipKind(StrEnum):
    PARENT = "parent"
    AMENDS = "amends"
    SUPERSEDES = "supersedes"
    REPEALS = "repeals"
    EXTENDS = "extends"


class VersionStatusMode(StrEnum):
    CURRENT = "current"
    AS_OF = "as_of"
    DRAFT = "draft"


class VersionEvidenceCoverage(StrEnum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    UNAVAILABLE = "unavailable"


class VersionStatusOutcome(StrEnum):
    VALIDATED_CURRENT = "validated_current"
    VALIDATED_HISTORICAL = "validated_historical"
    VALIDATED_DRAFT = "validated_draft"
    NO_MATCH = "no_match"
    UNKNOWN = "unknown"
    CONTRADICTORY = "contradictory"
    INVALID_LINEAGE = "invalid_lineage"


class VersionStatusHealth(StrEnum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    FAILED = "failed"


class OfficialVersionRecord(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
    )

    registry_version_id: int = Field(ge=1)
    family_id: int = Field(ge=1)
    document_id: int = Field(ge=1)
    document_version_id: int = Field(ge=1)
    version_number: int | None = Field(default=None, ge=1)
    version_label: str | None = None
    publication_date: date | None = None
    issue_date: date | None = None
    effective_date: date | None = None
    declared_status: DocumentLegalStatus
    status_effective_on: date
    status_observed_at: datetime
    status_source_url: str = Field(min_length=1)
    source_authority: Literal["official"] = "official"

    @model_validator(mode="after")
    def validate_record(self) -> Self:
        if self.status_observed_at.tzinfo is None:
            raise ValueError("Version status observation must be timezone-aware")
        if self.version_label == "":
            raise ValueError("Version labels cannot be blank")
        return self

    @property
    def available_on(self) -> date:
        return (
            self.publication_date
            or self.issue_date
            or self.effective_date
            or self.status_effective_on
        )


class OfficialVersionRelationship(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
    )

    from_registry_version_id: int = Field(ge=1)
    to_registry_version_id: int = Field(ge=1)
    relationship: VersionRelationshipKind
    effective_on: date
    observed_at: datetime
    source_url: str = Field(min_length=1)
    source_authority: Literal["official"] = "official"

    @model_validator(mode="after")
    def validate_relationship(self) -> Self:
        if self.from_registry_version_id == self.to_registry_version_id:
            raise ValueError("Version relationships cannot be self-referential")
        if self.observed_at.tzinfo is None:
            raise ValueError("Version relationship observation must be timezone-aware")
        return self


class VersionStatusRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1"] = VERSION_STATUS_SCHEMA_VERSION
    policy_version: str = Field(
        default=VERSION_STATUS_POLICY_VERSION,
        min_length=1,
    )
    family_id: int = Field(ge=1)
    mode: VersionStatusMode
    evaluated_at: datetime
    as_of: date | None = None
    coverage: VersionEvidenceCoverage
    records: tuple[OfficialVersionRecord, ...]
    relationships: tuple[OfficialVersionRelationship, ...] = ()

    @model_validator(mode="after")
    def validate_request(self) -> Self:
        if self.evaluated_at.tzinfo is None:
            raise ValueError("Version evaluation time must be timezone-aware")
        if (self.mode is VersionStatusMode.AS_OF) != (self.as_of is not None):
            raise ValueError("Only as-of requests require an as-of date")
        if self.as_of is not None and self.as_of > self.evaluated_at.date():
            raise ValueError("Historical as-of date cannot be in the future")
        if any(
            item.status_observed_at > self.evaluated_at
            for item in self.records
        ) or any(
            item.observed_at > self.evaluated_at
            for item in self.relationships
        ):
            raise ValueError("Version evidence cannot be observed in the future")
        record_ids = tuple(item.registry_version_id for item in self.records)
        document_version_ids = tuple(
            item.document_version_id for item in self.records
        )
        if len(set(record_ids)) != len(record_ids):
            raise ValueError("Registry version IDs must be unique")
        if len(set(document_version_ids)) != len(document_version_ids):
            raise ValueError("Document version IDs must be unique")
        edge_keys = tuple(
            (
                item.from_registry_version_id,
                item.to_registry_version_id,
                item.relationship,
            )
            for item in self.relationships
        )
        if len(set(edge_keys)) != len(edge_keys):
            raise ValueError("Version relationships must be unique")
        return self


class ResolvedVersionStatus(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    registry_version_id: int = Field(ge=1)
    status: DocumentLegalStatus
    status_effective_on: date
    supporting_relationships: tuple[VersionRelationshipKind, ...] = ()


class VersionStatusDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1"] = VERSION_STATUS_SCHEMA_VERSION
    policy_version: str = Field(min_length=1)
    family_id: int = Field(ge=1)
    mode: VersionStatusMode
    outcome: VersionStatusOutcome
    health: VersionStatusHealth
    evaluated_for: date
    selected_registry_version_ids: tuple[int, ...] = ()
    resolved_statuses: tuple[ResolvedVersionStatus, ...] = ()
    freshest_official_observation_at: datetime | None = None
    can_support_current_claim: bool = False
    safe_code: str | None = Field(
        default=None,
        pattern=r"^[A-Z][A-Z0-9_]{0,99}$",
    )

    @model_validator(mode="after")
    def validate_decision(self) -> Self:
        healthy = self.outcome in {
            VersionStatusOutcome.VALIDATED_CURRENT,
            VersionStatusOutcome.VALIDATED_HISTORICAL,
            VersionStatusOutcome.VALIDATED_DRAFT,
            VersionStatusOutcome.NO_MATCH,
        }
        degraded = self.outcome is VersionStatusOutcome.UNKNOWN
        expected_health = (
            VersionStatusHealth.HEALTHY
            if healthy
            else (
                VersionStatusHealth.DEGRADED
                if degraded
                else VersionStatusHealth.FAILED
            )
        )
        if self.health is not expected_health:
            raise ValueError("Version status outcome and health must agree")
        if healthy != (self.safe_code is None):
            raise ValueError("Only nonhealthy version decisions require a safe code")
        expected_current = (
            self.outcome is VersionStatusOutcome.VALIDATED_CURRENT
        )
        if self.can_support_current_claim is not expected_current:
            raise ValueError("Only validated-current evidence supports current claims")
        if bool(self.selected_registry_version_ids) != (
            self.outcome
            in {
                VersionStatusOutcome.VALIDATED_CURRENT,
                VersionStatusOutcome.VALIDATED_HISTORICAL,
                VersionStatusOutcome.VALIDATED_DRAFT,
            }
        ):
            raise ValueError("Selected versions require a validated outcome")
        if len(set(self.selected_registry_version_ids)) != len(
            self.selected_registry_version_ids
        ):
            raise ValueError("Selected registry versions must be unique")
        return self


def resolve_version_status(
    request: VersionStatusRequest,
) -> VersionStatusDecision:
    evaluated_for = request.as_of or request.evaluated_at.date()
    freshest = _freshest_observation(request)
    if request.coverage is not VersionEvidenceCoverage.COMPLETE:
        return _decision(
            request,
            evaluated_for=evaluated_for,
            outcome=VersionStatusOutcome.UNKNOWN,
            freshest=freshest,
            safe_code=(
                "VERSION_LINEAGE_UNAVAILABLE"
                if request.coverage is VersionEvidenceCoverage.UNAVAILABLE
                else "VERSION_LINEAGE_PARTIAL"
            ),
        )
    invalid_code = _invalid_lineage_code(request)
    if invalid_code is not None:
        return _decision(
            request,
            evaluated_for=evaluated_for,
            outcome=VersionStatusOutcome.INVALID_LINEAGE,
            freshest=freshest,
            safe_code=invalid_code,
        )

    eligible = tuple(
        sorted(
            (
                record
                for record in request.records
                if record.available_on <= evaluated_for
            ),
            key=lambda item: (
                item.available_on,
                item.version_number or 0,
                item.registry_version_id,
            ),
        )
    )
    statuses, contradiction = _statuses_as_of(
        eligible,
        request.relationships,
        evaluated_for,
    )
    resolved = tuple(
        ResolvedVersionStatus(
            registry_version_id=record.registry_version_id,
            status=statuses[record.registry_version_id][0],
            status_effective_on=statuses[record.registry_version_id][1],
            supporting_relationships=statuses[record.registry_version_id][2],
        )
        for record in eligible
    )
    if contradiction:
        return _decision(
            request,
            evaluated_for=evaluated_for,
            outcome=VersionStatusOutcome.CONTRADICTORY,
            freshest=freshest,
            resolved=resolved,
            safe_code="VERSION_STATUS_CONTRADICTORY",
        )

    if request.mode is VersionStatusMode.DRAFT:
        drafts = tuple(
            record
            for record in eligible
            if statuses[record.registry_version_id][0]
            in {
                DocumentLegalStatus.DRAFT,
                DocumentLegalStatus.CONSULTATION,
            }
        )
        if not drafts:
            return _decision(
                request,
                evaluated_for=evaluated_for,
                outcome=VersionStatusOutcome.NO_MATCH,
                freshest=freshest,
                resolved=resolved,
            )
        selected = _newest(drafts)
        return _decision(
            request,
            evaluated_for=evaluated_for,
            outcome=VersionStatusOutcome.VALIDATED_DRAFT,
            freshest=freshest,
            resolved=resolved,
            selected=(selected.registry_version_id,),
        )

    active = tuple(
        record
        for record in eligible
        if statuses[record.registry_version_id][0]
        is DocumentLegalStatus.IN_FORCE
    )
    unknown = tuple(
        record
        for record in eligible
        if statuses[record.registry_version_id][0]
        is DocumentLegalStatus.UNKNOWN
    )
    if not active:
        terminal = tuple(
            record
            for record in eligible
            if statuses[record.registry_version_id][0]
            in {
                DocumentLegalStatus.SUPERSEDED,
                DocumentLegalStatus.REPEALED,
            }
        )
        if terminal and not unknown:
            selected = _newest(terminal)
            outcome = (
                VersionStatusOutcome.VALIDATED_CURRENT
                if request.mode is VersionStatusMode.CURRENT
                else VersionStatusOutcome.VALIDATED_HISTORICAL
            )
            return _decision(
                request,
                evaluated_for=evaluated_for,
                outcome=outcome,
                freshest=freshest,
                resolved=resolved,
                selected=(selected.registry_version_id,),
            )
        return _decision(
            request,
            evaluated_for=evaluated_for,
            outcome=(
                VersionStatusOutcome.UNKNOWN
                if unknown
                else VersionStatusOutcome.NO_MATCH
            ),
            freshest=freshest,
            resolved=resolved,
            safe_code="VERSION_STATUS_UNKNOWN" if unknown else None,
        )
    selected = _newest(active)
    if any(record.available_on >= selected.available_on for record in unknown):
        return _decision(
            request,
            evaluated_for=evaluated_for,
            outcome=VersionStatusOutcome.UNKNOWN,
            freshest=freshest,
            resolved=resolved,
            safe_code="VERSION_STATUS_UNKNOWN",
        )
    ordered_active = tuple(
        sorted(
            active,
            key=lambda item: (
                item.available_on,
                item.version_number or 0,
                item.registry_version_id,
            ),
            reverse=True,
        )
    )
    if any(
        record.registry_version_id != selected.registry_version_id
        and not _has_active_lineage_path(
            selected.registry_version_id,
            record.registry_version_id,
            request.relationships,
            evaluated_for,
        )
        for record in ordered_active
    ):
        return _decision(
            request,
            evaluated_for=evaluated_for,
            outcome=VersionStatusOutcome.CONTRADICTORY,
            freshest=freshest,
            resolved=resolved,
            safe_code="VERSION_STATUS_CONTRADICTORY",
        )
    outcome = (
        VersionStatusOutcome.VALIDATED_CURRENT
        if request.mode is VersionStatusMode.CURRENT
        else VersionStatusOutcome.VALIDATED_HISTORICAL
    )
    return _decision(
        request,
        evaluated_for=evaluated_for,
        outcome=outcome,
        freshest=freshest,
        resolved=resolved,
        selected=tuple(
            record.registry_version_id for record in ordered_active
        ),
    )


def _statuses_as_of(
    records: tuple[OfficialVersionRecord, ...],
    relationships: tuple[OfficialVersionRelationship, ...],
    evaluated_for: date,
) -> tuple[
    dict[
        int,
        tuple[
            DocumentLegalStatus,
            date,
            tuple[VersionRelationshipKind, ...],
        ],
    ],
    bool,
]:
    active_edges = tuple(
        sorted(
            (
                edge
                for edge in relationships
                if edge.effective_on <= evaluated_for
            ),
            key=lambda item: (
                item.to_registry_version_id,
                item.effective_on,
                item.relationship.value,
                item.from_registry_version_id,
            ),
        )
    )
    terminal: dict[
        int,
        list[tuple[DocumentLegalStatus, OfficialVersionRelationship]],
    ] = {}
    for edge in active_edges:
        status = {
            VersionRelationshipKind.SUPERSEDES: DocumentLegalStatus.SUPERSEDED,
            VersionRelationshipKind.REPEALS: DocumentLegalStatus.REPEALED,
        }.get(edge.relationship)
        if status is not None:
            terminal.setdefault(edge.to_registry_version_id, []).append(
                (status, edge)
            )
    contradiction = False
    output = {}
    for record in records:
        transitions = terminal.get(record.registry_version_id, [])
        declared = record.declared_status
        if record.status_effective_on > evaluated_for and declared in {
            DocumentLegalStatus.SUPERSEDED,
            DocumentLegalStatus.REPEALED,
        }:
            declared = DocumentLegalStatus.IN_FORCE
            effective_on = record.available_on
        elif record.status_effective_on > evaluated_for:
            declared = DocumentLegalStatus.UNKNOWN
            effective_on = record.available_on
        else:
            effective_on = record.status_effective_on
        events: list[
            tuple[
                DocumentLegalStatus,
                date,
                VersionRelationshipKind | None,
            ]
        ] = [(declared, effective_on, None)]
        events.extend(
            (status, edge.effective_on, edge.relationship)
            for status, edge in transitions
        )
        newest_date = max(event[1] for event in events)
        newest = tuple(event for event in events if event[1] == newest_date)
        newest_statuses = {event[0] for event in newest}
        contradiction = contradiction or len(newest_statuses) > 1
        reasons = tuple(
            dict.fromkeys(
                relationship
                for _, _, relationship in newest
                if relationship is not None
            )
        )
        output[record.registry_version_id] = (
            newest[0][0],
            newest_date,
            reasons,
        )
    return output, contradiction


def _invalid_lineage_code(request: VersionStatusRequest) -> str | None:
    record_ids = {record.registry_version_id for record in request.records}
    records = {
        record.registry_version_id: record for record in request.records
    }
    if any(record.family_id != request.family_id for record in request.records):
        return "VERSION_LINEAGE_FAMILY_MISMATCH"
    if any(
        edge.from_registry_version_id not in record_ids
        or edge.to_registry_version_id not in record_ids
        for edge in request.relationships
    ):
        return "VERSION_LINEAGE_MISSING_ENDPOINT"
    if any(
        edge.effective_on < records[edge.from_registry_version_id].available_on
        for edge in request.relationships
    ):
        return "VERSION_LINEAGE_INVALID_CHRONOLOGY"
    adjacency: dict[int, list[int]] = {record_id: [] for record_id in record_ids}
    for edge in request.relationships:
        adjacency[edge.from_registry_version_id].append(
            edge.to_registry_version_id
        )
    visiting: set[int] = set()
    visited: set[int] = set()

    def visit(node: int) -> bool:
        if node in visiting:
            return True
        if node in visited:
            return False
        visiting.add(node)
        if any(visit(target) for target in adjacency[node]):
            return True
        visiting.remove(node)
        visited.add(node)
        return False

    if any(visit(record_id) for record_id in record_ids):
        return "VERSION_LINEAGE_CYCLE"
    return None


def _has_active_lineage_path(
    source_id: int,
    target_id: int,
    relationships: tuple[OfficialVersionRelationship, ...],
    evaluated_for: date,
) -> bool:
    allowed = {
        VersionRelationshipKind.PARENT,
        VersionRelationshipKind.AMENDS,
        VersionRelationshipKind.EXTENDS,
    }
    adjacency: dict[int, list[int]] = {}
    for edge in relationships:
        if edge.effective_on <= evaluated_for and edge.relationship in allowed:
            adjacency.setdefault(edge.from_registry_version_id, []).append(
                edge.to_registry_version_id
            )
    pending = [source_id]
    visited = set()
    while pending:
        current = pending.pop()
        if current == target_id:
            return True
        if current in visited:
            continue
        visited.add(current)
        pending.extend(adjacency.get(current, ()))
    return False


def _newest(
    records: tuple[OfficialVersionRecord, ...],
) -> OfficialVersionRecord:
    return max(
        records,
        key=lambda item: (
            item.available_on,
            item.version_number or 0,
            item.registry_version_id,
        ),
    )


def _freshest_observation(
    request: VersionStatusRequest,
) -> datetime | None:
    observations = (
        *(record.status_observed_at for record in request.records),
        *(edge.observed_at for edge in request.relationships),
    )
    return max(observations, default=None)


def _decision(
    request: VersionStatusRequest,
    *,
    evaluated_for: date,
    outcome: VersionStatusOutcome,
    freshest: datetime | None,
    resolved: tuple[ResolvedVersionStatus, ...] = (),
    selected: tuple[int, ...] = (),
    safe_code: str | None = None,
) -> VersionStatusDecision:
    health = (
        VersionStatusHealth.HEALTHY
        if outcome
        in {
            VersionStatusOutcome.VALIDATED_CURRENT,
            VersionStatusOutcome.VALIDATED_HISTORICAL,
            VersionStatusOutcome.VALIDATED_DRAFT,
            VersionStatusOutcome.NO_MATCH,
        }
        else (
            VersionStatusHealth.DEGRADED
            if outcome is VersionStatusOutcome.UNKNOWN
            else VersionStatusHealth.FAILED
        )
    )
    return VersionStatusDecision(
        policy_version=request.policy_version,
        family_id=request.family_id,
        mode=request.mode,
        outcome=outcome,
        health=health,
        evaluated_for=evaluated_for,
        selected_registry_version_ids=selected,
        resolved_statuses=resolved,
        freshest_official_observation_at=freshest,
        can_support_current_claim=(
            outcome is VersionStatusOutcome.VALIDATED_CURRENT
        ),
        safe_code=safe_code,
    )
