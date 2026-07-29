from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from enum import StrEnum
from typing import Literal, Protocol, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from backend.ask.decision import (
    EntityResolution,
    EntityResolutionStatus,
)
from backend.ask.orchestration import StructuredFactPayload
from backend.rag.quality import CanonicalEvidenceUnit

ENTITY_GRAPH_SCHEMA_VERSION = "1"
ENTITY_GRAPH_POLICY_VERSION = "ask-ai-entity-graph-v1"


class EntityGraphModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class GraphRelationType(StrEnum):
    CANONICAL_IDENTITY = "canonical_identity"
    ALIAS = "alias"
    REGULATED_BY = "regulated_by"
    ISSUED_BY = "issued_by"
    AMENDS = "amends"
    SUPERSEDES = "supersedes"
    APPLIES_TO = "applies_to"
    CREATES_OBLIGATION = "creates_obligation"
    HAS_DEADLINE = "has_deadline"
    RELATES_TO = "relates_to"


class GraphDirection(StrEnum):
    OUTBOUND = "outbound"
    INBOUND = "inbound"


class EntityGraphStatus(StrEnum):
    SATISFIED = "satisfied"
    PARTIAL = "partial"
    NO_MATCH = "no_match"
    UNAVAILABLE = "unavailable"
    INVALID_OUTPUT = "invalid_output"


class EntityGraphExclusionReason(StrEnum):
    INVALID_CANDIDATE = "invalid_candidate"
    OUTSIDE_RELATION_SCOPE = "outside_relation_scope"
    OUTSIDE_ENTITY_SCOPE = "outside_entity_scope"
    UNKNOWN_EVIDENCE = "unknown_evidence"
    CROSSED_QUESTION_SCOPE = "crossed_question_scope"
    DUPLICATE_EDGE_ID = "duplicate_edge_id"


class EntityGraphRequest(EntityGraphModel):
    schema_version: Literal["1"] = ENTITY_GRAPH_SCHEMA_VERSION
    policy_version: str = Field(default=ENTITY_GRAPH_POLICY_VERSION, min_length=1)
    canonical_entity_id: str = Field(
        pattern=r"^[a-z0-9][a-z0-9._:-]{0,199}$"
    )
    canonical_name: str = Field(min_length=1)
    jurisdiction: str = Field(min_length=1)
    resolution_confidence: float = Field(ge=0, le=1)
    assumed: bool
    approved_query_terms: tuple[str, ...] = Field(min_length=1)
    relation_types: tuple[GraphRelationType, ...] = Field(min_length=1)
    question_ids: tuple[str, ...] = Field(min_length=1)
    section_keys: tuple[str, ...] = Field(min_length=1)
    limit: int = Field(default=25, ge=1, le=100)

    @field_validator(
        "approved_query_terms",
        "relation_types",
        "question_ids",
        "section_keys",
    )
    @classmethod
    def validate_unique_values(cls, value: tuple[object, ...]) -> tuple[object, ...]:
        if len(value) != len(set(value)):
            raise ValueError("Entity graph request values must be unique")
        if any(isinstance(item, str) and not item.strip() for item in value):
            raise ValueError("Entity graph request values cannot be blank")
        return value


class EntityGraphCandidate(EntityGraphModel):
    edge_id: str = Field(
        min_length=1,
        max_length=200,
        pattern=r"^[a-zA-Z0-9][a-zA-Z0-9._:-]*$",
    )
    subject_id: str = Field(min_length=1)
    subject_name: str = Field(min_length=1)
    relationship: GraphRelationType
    object_id_or_value: str = Field(min_length=1)
    object_label: str = Field(min_length=1)
    direction: GraphDirection
    qualifiers: tuple[tuple[str, str], ...] = ()
    extraction_confidence: float = Field(ge=0, le=1)
    backing_evidence_unit_ids: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_candidate(self) -> Self:
        qualifier_keys = tuple(key for key, _ in self.qualifiers)
        if len(qualifier_keys) != len(set(qualifier_keys)):
            raise ValueError("Graph qualifier keys must be unique")
        if any(not key.strip() or not value.strip() for key, value in self.qualifiers):
            raise ValueError("Graph qualifiers cannot be blank")
        if len(self.backing_evidence_unit_ids) != len(
            set(self.backing_evidence_unit_ids)
        ):
            raise ValueError("Graph evidence references must be unique")
        return self


class EntityGraphFact(EntityGraphModel):
    fact_id: str = Field(pattern=r"^graph_fact_[0-9a-f]{32}$")
    edge_id: str = Field(min_length=1)
    payload: StructuredFactPayload
    backing_evidence: tuple[CanonicalEvidenceUnit, ...] = ()

    @model_validator(mode="after")
    def validate_discovery_boundary(self) -> Self:
        if not self.backing_evidence and not self.payload.discovery_only:
            raise ValueError("Unbacked graph facts must remain discovery-only")
        if (
            self.payload.relationship == GraphRelationType.RELATES_TO.value
            and not self.payload.discovery_only
        ):
            raise ValueError("Relates-to facts are always discovery-only")
        return self


class EntityGraphExclusion(EntityGraphModel):
    edge_id: str | None = None
    reason: EntityGraphExclusionReason


class EntityGraphResult(EntityGraphModel):
    schema_version: Literal["1"] = ENTITY_GRAPH_SCHEMA_VERSION
    policy_version: str = Field(default=ENTITY_GRAPH_POLICY_VERSION, min_length=1)
    status: EntityGraphStatus
    facts: tuple[EntityGraphFact, ...] = ()
    exclusions: tuple[EntityGraphExclusion, ...] = ()
    safe_error_code: str | None = Field(
        default=None,
        pattern=r"^[A-Z][A-Z0-9_]{0,99}$",
    )

    @model_validator(mode="after")
    def validate_status(self) -> Self:
        failed = self.status in {
            EntityGraphStatus.UNAVAILABLE,
            EntityGraphStatus.INVALID_OUTPUT,
        }
        if failed != (self.safe_error_code is not None):
            raise ValueError("Only failed graph results have a safe error code")
        if failed and self.facts:
            raise ValueError("Failed graph results cannot contain facts")
        if self.status is EntityGraphStatus.NO_MATCH and (
            self.facts or self.exclusions
        ):
            raise ValueError("Healthy graph no-match has no candidates")
        if self.status is EntityGraphStatus.SATISFIED and (
            not self.facts or self.exclusions
        ):
            raise ValueError("Satisfied graph results contain only valid facts")
        if self.status is EntityGraphStatus.PARTIAL and (
            not self.facts or not self.exclusions
        ):
            raise ValueError("Partial graph results require facts and exclusions")
        return self


class EntityGraphProvider(Protocol):
    def search(
        self,
        request: EntityGraphRequest,
    ) -> Sequence[EntityGraphCandidate]: ...


def entity_graph_request_from_resolution(
    resolution: EntityResolution,
    *,
    relation_types: tuple[GraphRelationType, ...],
    question_ids: tuple[str, ...],
    section_keys: tuple[str, ...],
    limit: int = 25,
) -> EntityGraphRequest:
    safe_resolution = EntityResolution.model_validate(
        resolution.model_dump(mode="python")
    )
    if (
        safe_resolution.status
        is EntityResolutionStatus.CLARIFICATION_REQUIRED
        or safe_resolution.selected is None
        or safe_resolution.selected.canonical_id is None
        or safe_resolution.selected.canonical_name is None
        or safe_resolution.selected.jurisdiction is None
    ):
        raise ValueError("Entity graph retrieval requires one resolved entity")
    terms = tuple(
        dict.fromkeys(
            (
                safe_resolution.selected.canonical_name,
                *safe_resolution.query_expansion,
            )
        )
    )
    return EntityGraphRequest(
        canonical_entity_id=safe_resolution.selected.canonical_id,
        canonical_name=safe_resolution.selected.canonical_name,
        jurisdiction=safe_resolution.selected.jurisdiction,
        resolution_confidence=safe_resolution.selected.confidence,
        assumed=safe_resolution.selected.assumed,
        approved_query_terms=terms,
        relation_types=relation_types,
        question_ids=question_ids,
        section_keys=section_keys,
        limit=limit,
    )


def retrieve_entity_graph(
    request: EntityGraphRequest,
    *,
    provider: EntityGraphProvider,
    admitted_evidence: Sequence[CanonicalEvidenceUnit],
) -> EntityGraphResult:
    safe_request = EntityGraphRequest.model_validate(
        request.model_dump(mode="python")
    )
    try:
        evidence_by_id = _evidence_map(admitted_evidence)
    except Exception:
        return EntityGraphResult(
            status=EntityGraphStatus.INVALID_OUTPUT,
            safe_error_code="ENTITY_GRAPH_INVALID_OUTPUT",
        )
    try:
        raw_candidates = provider.search(safe_request)
    except Exception:
        return EntityGraphResult(
            status=EntityGraphStatus.UNAVAILABLE,
            safe_error_code="ENTITY_GRAPH_UNAVAILABLE",
        )
    if not isinstance(raw_candidates, Sequence) or isinstance(
        raw_candidates, (str, bytes)
    ):
        return EntityGraphResult(
            status=EntityGraphStatus.INVALID_OUTPUT,
            safe_error_code="ENTITY_GRAPH_INVALID_OUTPUT",
        )
    if not raw_candidates:
        return EntityGraphResult(status=EntityGraphStatus.NO_MATCH)

    facts: list[EntityGraphFact] = []
    exclusions: list[EntityGraphExclusion] = []
    seen_edges: set[str] = set()
    for raw_candidate in raw_candidates:
        try:
            candidate = EntityGraphCandidate.model_validate(
                raw_candidate.model_dump(mode="python")
            )
        except Exception:
            exclusions.append(
                EntityGraphExclusion(
                    reason=EntityGraphExclusionReason.INVALID_CANDIDATE
                )
            )
            continue
        reason = _exclusion_reason(
            safe_request,
            candidate,
            evidence_by_id,
            seen_edges,
        )
        if reason is not None:
            exclusions.append(
                EntityGraphExclusion(edge_id=candidate.edge_id, reason=reason)
            )
            continue
        seen_edges.add(candidate.edge_id)
        evidence = tuple(
            evidence_by_id[evidence_id]
            for evidence_id in candidate.backing_evidence_unit_ids
        )
        discovery_only = (
            not evidence
            or candidate.relationship is GraphRelationType.RELATES_TO
        )
        facts.append(
            EntityGraphFact(
                fact_id=_fact_id(candidate),
                edge_id=candidate.edge_id,
                payload=StructuredFactPayload(
                    subject_id=candidate.subject_id,
                    relationship=candidate.relationship.value,
                    object_id_or_value=candidate.object_id_or_value,
                    qualifiers=tuple(
                        {"key": key, "value": value}
                        for key, value in candidate.qualifiers
                    ),
                    extraction_confidence=candidate.extraction_confidence,
                    discovery_only=discovery_only,
                ),
                backing_evidence=evidence,
            )
        )
        if len(facts) == safe_request.limit:
            break
    facts.sort(
        key=lambda fact: (
            fact.payload.relationship,
            fact.payload.subject_id,
            fact.payload.object_id_or_value,
            fact.edge_id,
        )
    )
    if facts and exclusions:
        status = EntityGraphStatus.PARTIAL
    elif facts:
        status = EntityGraphStatus.SATISFIED
    elif exclusions:
        status = EntityGraphStatus.INVALID_OUTPUT
    else:
        status = EntityGraphStatus.NO_MATCH
    return EntityGraphResult(
        status=status,
        facts=tuple(facts) if status is not EntityGraphStatus.INVALID_OUTPUT else (),
        exclusions=tuple(exclusions),
        safe_error_code=(
            "ENTITY_GRAPH_INVALID_OUTPUT"
            if status is EntityGraphStatus.INVALID_OUTPUT
            else None
        ),
    )


def entity_graph_result_json(result: EntityGraphResult) -> str:
    return json.dumps(
        result.model_dump(mode="json"),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def _evidence_map(
    evidence: Sequence[CanonicalEvidenceUnit],
) -> Mapping[str, CanonicalEvidenceUnit]:
    output: dict[str, CanonicalEvidenceUnit] = {}
    for raw_unit in evidence:
        unit = CanonicalEvidenceUnit.model_validate(
            raw_unit.model_dump(mode="python")
        )
        if unit.evidence_unit_id in output:
            raise ValueError("Admitted graph evidence IDs must be unique")
        output[unit.evidence_unit_id] = unit
    return output


def _exclusion_reason(
    request: EntityGraphRequest,
    candidate: EntityGraphCandidate,
    evidence_by_id: Mapping[str, CanonicalEvidenceUnit],
    seen_edges: set[str],
) -> EntityGraphExclusionReason | None:
    if candidate.edge_id in seen_edges:
        return EntityGraphExclusionReason.DUPLICATE_EDGE_ID
    if candidate.relationship not in request.relation_types:
        return EntityGraphExclusionReason.OUTSIDE_RELATION_SCOPE
    scoped_id = (
        candidate.subject_id
        if candidate.direction is GraphDirection.OUTBOUND
        else candidate.object_id_or_value
    )
    if scoped_id != request.canonical_entity_id:
        return EntityGraphExclusionReason.OUTSIDE_ENTITY_SCOPE
    for evidence_id in candidate.backing_evidence_unit_ids:
        evidence = evidence_by_id.get(evidence_id)
        if evidence is None:
            return EntityGraphExclusionReason.UNKNOWN_EVIDENCE
        if not set(evidence.question_ids) & set(request.question_ids):
            return EntityGraphExclusionReason.CROSSED_QUESTION_SCOPE
    return None


def _fact_id(candidate: EntityGraphCandidate) -> str:
    payload = "|".join(
        (
            candidate.edge_id,
            candidate.subject_id,
            candidate.relationship.value,
            candidate.object_id_or_value,
            ",".join(candidate.backing_evidence_unit_ids),
        )
    )
    return "graph_fact_" + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]
