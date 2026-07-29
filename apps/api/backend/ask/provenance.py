from __future__ import annotations

import json
from enum import StrEnum
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from backend.ask.evidence_admission import AdmittedOfficialEvidence
from backend.ask.orchestration.contracts import (
    PROVENANCE_AUTHORITY,
    ArtifactEnvelope,
    ArtifactKind,
    ArtifactProducer,
    CandidateClaimPayload,
    CapabilityScope,
    CapabilityTerminalState,
    ContentDerivation,
    EvidenceUnitPayload,
    GeneralKnowledgeUnitPayload,
    KnowledgeMode,
    OrchestratorCapability,
    ProvenanceClass,
    SectionDraftPayload,
    SourceIdentity,
    StructuredFactPayload,
    VerificationStatus,
)
from backend.rag.entity_graph import EntityGraphFact
from backend.rag.timeline import TimelineEventRecord

PROVENANCE_TRACE_SCHEMA_VERSION = "1"
PROVENANCE_TRACE_POLICY_VERSION = "ask-ai-provenance-trace-v1"

TRACEABLE_ARTIFACT_KINDS = frozenset(
    {
        ArtifactKind.EVIDENCE_UNIT,
        ArtifactKind.STRUCTURED_FACT,
        ArtifactKind.TIMELINE_EVENT,
        ArtifactKind.GENERAL_KNOWLEDGE_UNIT,
        ArtifactKind.CANDIDATE_CLAIM,
        ArtifactKind.SECTION_DRAFT,
    }
)


class ProvenanceTraceModel(BaseModel):
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
    if len(normalized) != len(set(normalized)):
        raise ValueError(f"{label} must be unique")
    return normalized


class ProvenanceTraceStatus(StrEnum):
    COMPLETE = "complete"


class LineageArtifactRecord(ProvenanceTraceModel):
    schema_version: Literal["1"] = PROVENANCE_TRACE_SCHEMA_VERSION
    artifact_id: str = Field(min_length=1)
    artifact_kind: ArtifactKind
    scope: CapabilityScope
    provenance_class: ProvenanceClass
    knowledge_mode: KnowledgeMode
    derivation: ContentDerivation
    source_ids: tuple[str, ...] = ()
    source_identities: tuple[SourceIdentity, ...] = ()
    parent_artifact_ids: tuple[str, ...] = ()
    declared_input_provenance: tuple[ProvenanceClass, ...] = ()
    transformation_capability: OrchestratorCapability | None = None
    verification_status: VerificationStatus
    discovery_only: bool = False

    @field_validator("artifact_id")
    @classmethod
    def normalize_artifact_id(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Lineage artifact ID cannot be blank")
        return normalized

    @field_validator("source_ids", "parent_artifact_ids")
    @classmethod
    def validate_unique_ids(
        cls,
        value: tuple[str, ...],
        info: object,
    ) -> tuple[str, ...]:
        return _unique_text(value, getattr(info, "field_name", "Lineage IDs"))

    @model_validator(mode="after")
    def validate_record_shape(self) -> Self:
        if self.artifact_kind not in TRACEABLE_ARTIFACT_KINDS:
            raise ValueError("Artifact kind is not traceable")
        expected_mode = {
            ProvenanceClass.INTERNAL_REGULATORY_CORPUS: (
                KnowledgeMode.GROUNDED_REGULATORY
            ),
            ProvenanceClass.LIVE_WEB_SOURCES: KnowledgeMode.LIVE_INTELLIGENCE,
            ProvenanceClass.GENERAL_AI_KNOWLEDGE: KnowledgeMode.GENERAL_AI,
        }[self.provenance_class]
        if self.knowledge_mode is not expected_mode:
            raise ValueError("Knowledge mode must match the provenance lane")
        identity_ids = tuple(source.source_id for source in self.source_identities)
        if len(identity_ids) != len(set(identity_ids)):
            raise ValueError("Lineage source identities must be unique")
        if identity_ids and set(identity_ids) != set(self.source_ids):
            raise ValueError("Lineage source identities must match source IDs")
        if any(
            source.provenance_class is not self.provenance_class
            for source in self.source_identities
        ):
            raise ValueError("Declared source identities cannot cross lanes")
        if len(self.declared_input_provenance) != len(
            set(self.declared_input_provenance)
        ):
            raise ValueError("Declared input provenance must be unique")
        if self.artifact_id in self.parent_artifact_ids:
            raise ValueError("A lineage artifact cannot parent itself")

        root_kind = self.artifact_kind in {
            ArtifactKind.EVIDENCE_UNIT,
            ArtifactKind.GENERAL_KNOWLEDGE_UNIT,
        }
        unbacked_discovery = (
            self.artifact_kind is ArtifactKind.STRUCTURED_FACT
            and self.discovery_only
            and not self.parent_artifact_ids
        )
        if root_kind or unbacked_discovery:
            if (
                self.transformation_capability is not None
                or self.declared_input_provenance
            ):
                raise ValueError("Lineage roots cannot declare a transformation")
        elif (
            not self.parent_artifact_ids
            or not self.declared_input_provenance
            or self.transformation_capability is None
        ):
            raise ValueError("Derived lineage requires parents and transformation")

        if self.artifact_kind is ArtifactKind.EVIDENCE_UNIT:
            if (
                self.derivation is not ContentDerivation.DIRECT
                or not self.source_ids
                or not self.source_identities
                or self.discovery_only
            ):
                raise ValueError("Evidence roots require direct inspectable sources")
        if self.artifact_kind is ArtifactKind.GENERAL_KNOWLEDGE_UNIT:
            if (
                self.provenance_class
                is not ProvenanceClass.GENERAL_AI_KNOWLEDGE
                or self.derivation is not ContentDerivation.GENERATED
                or self.source_ids
                or self.source_identities
                or self.discovery_only
            ):
                raise ValueError("General AI roots cannot claim source identity")
        if unbacked_discovery and (
            self.source_ids
            or self.source_identities
            or self.derivation is not ContentDerivation.EXTRACTED
        ):
            raise ValueError("Unbacked graph discovery cannot claim a source")
        if self.artifact_kind in {
            ArtifactKind.CANDIDATE_CLAIM,
            ArtifactKind.SECTION_DRAFT,
        } and self.discovery_only:
            raise ValueError("Claims and sections cannot be discovery-only")
        expected_capability = {
            ArtifactKind.STRUCTURED_FACT: OrchestratorCapability.KNOWLEDGE_GRAPH,
            ArtifactKind.TIMELINE_EVENT: OrchestratorCapability.TIMELINE_BUILDER,
            ArtifactKind.CANDIDATE_CLAIM: OrchestratorCapability.RESPONSE_COMPOSER,
            ArtifactKind.SECTION_DRAFT: OrchestratorCapability.RESPONSE_COMPOSER,
        }.get(self.artifact_kind)
        if (
            not unbacked_discovery
            and expected_capability is not None
            and self.transformation_capability is not expected_capability
        ):
            raise ValueError("Artifact kind and transformation capability disagree")
        if (
            expected_capability is not None
            and not unbacked_discovery
            and self.derivation
            not in {
                ContentDerivation.EXTRACTED,
                ContentDerivation.INFERRED,
                ContentDerivation.SUMMARIZED,
            }
        ):
            raise ValueError("Derived lineage requires a derivation")
        return self


class ProvenanceArtifactTrace(ProvenanceTraceModel):
    artifact_id: str = Field(min_length=1)
    artifact_kind: ArtifactKind
    provenance_class: ProvenanceClass
    knowledge_mode: KnowledgeMode
    origin_provenance: tuple[ProvenanceClass, ...] = Field(min_length=1)
    origin_source_ids: tuple[str, ...]
    citable_source_ids: tuple[str, ...]
    parent_artifact_ids: tuple[str, ...]
    effective_authority: int = Field(ge=0, le=3)
    discovery_only: bool
    verification_status: VerificationStatus


class ProvenanceTraceResult(ProvenanceTraceModel):
    schema_version: Literal["1"] = PROVENANCE_TRACE_SCHEMA_VERSION
    policy_version: Literal[
        "ask-ai-provenance-trace-v1"
    ] = PROVENANCE_TRACE_POLICY_VERSION
    status: Literal[ProvenanceTraceStatus.COMPLETE] = ProvenanceTraceStatus.COMPLETE
    traces: tuple[ProvenanceArtifactTrace, ...] = Field(min_length=1)
    source_catalog: tuple[SourceIdentity, ...]

    @model_validator(mode="after")
    def validate_result(self) -> Self:
        artifact_ids = tuple(trace.artifact_id for trace in self.traces)
        if artifact_ids != tuple(sorted(artifact_ids)):
            raise ValueError("Provenance traces must use deterministic order")
        if len(artifact_ids) != len(set(artifact_ids)):
            raise ValueError("Provenance trace artifact IDs must be unique")
        source_ids = tuple(source.source_id for source in self.source_catalog)
        if source_ids != tuple(sorted(source_ids)):
            raise ValueError("Provenance source catalog must use deterministic order")
        if len(source_ids) != len(set(source_ids)):
            raise ValueError("Provenance source catalog IDs must be unique")
        return self


def lineage_record_from_admitted_evidence(
    admitted: AdmittedOfficialEvidence,
) -> LineageArtifactRecord:
    safe = AdmittedOfficialEvidence.model_validate(
        admitted.model_dump(mode="python"),
        strict=True,
    )
    artifact = safe.artifact
    evidence = safe.canonical_evidence
    lineage = artifact.provenance
    if (
        artifact.artifact_id != evidence.evidence_unit_id
        or not isinstance(artifact.payload, EvidenceUnitPayload)
        or artifact.payload.excerpt != evidence.text
        or artifact.payload.locator is None
        or not artifact.payload.locator.strip()
        or artifact.payload.match_reasons
        != tuple(reason.value for reason in evidence.match_reasons)
        or artifact.payload.duplicate_match_methods
        != (
            evidence.retrieval_sources
            if len(evidence.retrieval_sources) > 1
            else ()
        )
        or artifact.producer is not ArtifactProducer.REGULATORY_RETRIEVER
        or artifact.capability_status
        not in {
            CapabilityTerminalState.SATISFIED,
            CapabilityTerminalState.PARTIAL,
        }
        or artifact.conflicts
        or not artifact.ancestry
        or artifact.confidence_signals is None
        or artifact.confidence_signals.retrieval_relevance
        != evidence.scores.admitted_relevance
        or lineage is None
        or lineage.provenance_class
        is not ProvenanceClass.INTERNAL_REGULATORY_CORPUS
        or lineage.knowledge_mode is not KnowledgeMode.GROUNDED_REGULATORY
        or lineage.derivation is not ContentDerivation.DIRECT
        or lineage.transformations
        or len(lineage.sources) != 1
        or lineage.verification_status is not VerificationStatus.PENDING
        or evidence.chunk_id is None
        or evidence.chunk_id < 1
        or not set(evidence.question_ids).issubset(
            artifact.scope.atomic_question_ids
        )
    ):
        raise ValueError("Official lineage requires exact admitted evidence")
    source = lineage.sources[0]
    issue_date = source.issue_at.date() if source.issue_at is not None else None
    if (
        source.source_id != f"document-{evidence.document_id}"
        or source.title != evidence.title
        or source.uri != evidence.source_url
        or source.issuer_or_publisher != evidence.issuer
        or issue_date != evidence.issue_date
    ):
        raise ValueError("Official lineage source does not match admitted evidence")
    return _lineage_record_from_artifact(artifact)


def lineage_record_from_artifact(
    artifact: ArtifactEnvelope,
) -> LineageArtifactRecord:
    safe = ArtifactEnvelope.model_validate(
        artifact.model_dump(mode="python"),
        strict=True,
    )
    kind = safe.payload.kind
    if kind not in TRACEABLE_ARTIFACT_KINDS:
        raise ValueError("Artifact kind is not traceable")
    if kind is ArtifactKind.EVIDENCE_UNIT:
        raise ValueError("Evidence lineage requires an admission boundary")
    return _lineage_record_from_artifact(safe)


def _lineage_record_from_artifact(
    safe: ArtifactEnvelope,
) -> LineageArtifactRecord:
    kind = safe.payload.kind
    if safe.provenance is None:
        raise ValueError("Traceable artifacts require provenance")

    root_kind = kind in {
        ArtifactKind.EVIDENCE_UNIT,
        ArtifactKind.GENERAL_KNOWLEDGE_UNIT,
    }
    if not root_kind and len(safe.provenance.transformations) != 1:
        raise ValueError("A derived artifact requires one local transformation")
    transformation = (
        safe.provenance.transformations[-1]
        if safe.provenance.transformations
        else None
    )
    if (
        transformation is not None
        and transformation.derivation is not safe.provenance.derivation
    ):
        raise ValueError("Artifact derivation and transformation disagree")
    parent_ids = (
        transformation.input_artifact_ids
        if transformation is not None
        else ()
    )
    if isinstance(safe.payload, CandidateClaimPayload):
        if set(parent_ids) != set(safe.payload.supporting_artifact_ids):
            raise ValueError("Claim lineage must exactly cover its support")
    if isinstance(safe.payload, SectionDraftPayload):
        if not set(safe.payload.candidate_claim_ids).issubset(parent_ids):
            raise ValueError("Section claim lineage is incomplete")
    if isinstance(safe.payload, GeneralKnowledgeUnitPayload) and parent_ids:
        raise ValueError("General knowledge units are lineage roots")

    discovery_only = (
        safe.payload.discovery_only
        if isinstance(safe.payload, StructuredFactPayload)
        else False
    )
    return LineageArtifactRecord(
        artifact_id=safe.artifact_id,
        artifact_kind=kind,
        scope=safe.scope,
        provenance_class=safe.provenance.provenance_class,
        knowledge_mode=safe.provenance.knowledge_mode,
        derivation=safe.provenance.derivation,
        source_ids=tuple(source.source_id for source in safe.provenance.sources),
        source_identities=safe.provenance.sources,
        parent_artifact_ids=parent_ids,
        declared_input_provenance=(
            transformation.input_provenance
            if transformation is not None
            else ()
        ),
        transformation_capability=(
            transformation.capability
            if transformation is not None
            else None
        ),
        verification_status=safe.provenance.verification_status,
        discovery_only=discovery_only,
    )


def lineage_record_from_graph_fact(
    fact: EntityGraphFact,
    *,
    scope: CapabilityScope,
) -> LineageArtifactRecord:
    safe_fact = EntityGraphFact.model_validate(
        fact.model_dump(mode="python"),
        strict=True,
    )
    safe_scope = CapabilityScope.model_validate(
        scope.model_dump(mode="python"),
        strict=True,
    )
    parent_ids = tuple(
        evidence.evidence_unit_id for evidence in safe_fact.backing_evidence
    )
    source_ids = tuple(
        dict.fromkeys(
            f"document-{evidence.document_id}"
            for evidence in safe_fact.backing_evidence
        )
    )
    return LineageArtifactRecord(
        artifact_id=safe_fact.fact_id,
        artifact_kind=ArtifactKind.STRUCTURED_FACT,
        scope=safe_scope,
        provenance_class=ProvenanceClass.INTERNAL_REGULATORY_CORPUS,
        knowledge_mode=KnowledgeMode.GROUNDED_REGULATORY,
        derivation=ContentDerivation.EXTRACTED,
        source_ids=source_ids,
        parent_artifact_ids=parent_ids,
        declared_input_provenance=(
            (ProvenanceClass.INTERNAL_REGULATORY_CORPUS,)
            if parent_ids
            else ()
        ),
        transformation_capability=(
            OrchestratorCapability.KNOWLEDGE_GRAPH
            if parent_ids
            else None
        ),
        verification_status=VerificationStatus.PENDING,
        discovery_only=safe_fact.payload.discovery_only,
    )


def lineage_record_from_timeline_event(
    event: TimelineEventRecord,
    *,
    scope: CapabilityScope,
) -> LineageArtifactRecord:
    safe_event = TimelineEventRecord.model_validate(
        event.model_dump(mode="python"),
        strict=True,
    )
    safe_scope = CapabilityScope.model_validate(
        scope.model_dump(mode="python"),
        strict=True,
    )
    expected_mode = {
        ProvenanceClass.INTERNAL_REGULATORY_CORPUS: (
            KnowledgeMode.GROUNDED_REGULATORY
        ),
        ProvenanceClass.LIVE_WEB_SOURCES: KnowledgeMode.LIVE_INTELLIGENCE,
        ProvenanceClass.GENERAL_AI_KNOWLEDGE: KnowledgeMode.GENERAL_AI,
    }[safe_event.provenance_class]
    return LineageArtifactRecord(
        artifact_id=safe_event.event_id,
        artifact_kind=ArtifactKind.TIMELINE_EVENT,
        scope=safe_scope,
        provenance_class=safe_event.provenance_class,
        knowledge_mode=expected_mode,
        derivation=ContentDerivation.EXTRACTED,
        source_ids=safe_event.source_ids,
        parent_artifact_ids=safe_event.ancestry,
        declared_input_provenance=(safe_event.provenance_class,),
        transformation_capability=OrchestratorCapability.TIMELINE_BUILDER,
        verification_status=VerificationStatus.PENDING,
        discovery_only=safe_event.discovery_only,
    )


def build_provenance_trace(
    records: tuple[LineageArtifactRecord, ...],
) -> ProvenanceTraceResult:
    if not records:
        raise ValueError("Provenance tracing requires artifacts")
    safe_records = tuple(
        LineageArtifactRecord.model_validate(
            record.model_dump(mode="python"),
            strict=True,
        )
        for record in records
    )
    by_id: dict[str, LineageArtifactRecord] = {}
    for record in safe_records:
        if record.artifact_id in by_id:
            raise ValueError("Provenance artifact IDs must be unique")
        by_id[record.artifact_id] = record

    traces: dict[str, ProvenanceArtifactTrace] = {}
    source_catalog: dict[str, SourceIdentity] = {}
    visiting: set[str] = set()

    def visit(artifact_id: str) -> ProvenanceArtifactTrace:
        existing = traces.get(artifact_id)
        if existing is not None:
            return existing
        if artifact_id in visiting:
            raise ValueError("Provenance ancestry must be acyclic")
        record = by_id.get(artifact_id)
        if record is None:
            raise ValueError("Provenance parent artifact is missing")
        visiting.add(artifact_id)
        parents = tuple(visit(parent_id) for parent_id in record.parent_artifact_ids)
        trace = _trace_record(record, parents, by_id, source_catalog)
        visiting.remove(artifact_id)
        traces[artifact_id] = trace
        return trace

    for artifact_id in sorted(by_id):
        visit(artifact_id)

    return ProvenanceTraceResult(
        traces=tuple(traces[artifact_id] for artifact_id in sorted(traces)),
        source_catalog=tuple(
            source_catalog[source_id] for source_id in sorted(source_catalog)
        ),
    )


def provenance_trace_json(result: ProvenanceTraceResult) -> str:
    return json.dumps(
        result.model_dump(mode="json"),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def _trace_record(
    record: LineageArtifactRecord,
    parents: tuple[ProvenanceArtifactTrace, ...],
    records: dict[str, LineageArtifactRecord],
    source_catalog: dict[str, SourceIdentity],
) -> ProvenanceArtifactTrace:
    for source in record.source_identities:
        existing = source_catalog.get(source.source_id)
        if existing is not None and existing != source:
            raise ValueError("Source identity changed within provenance lineage")
        source_catalog[source.source_id] = source

    if not parents:
        origin_provenance = (record.provenance_class,)
        origin_source_ids = tuple(sorted(record.source_ids))
        citable_source_ids = origin_source_ids
        effective_authority = (
            0
            if record.discovery_only
            else PROVENANCE_AUTHORITY[record.provenance_class]
        )
    else:
        for parent_id in record.parent_artifact_ids:
            if not _scope_is_within(record.scope, records[parent_id].scope):
                raise ValueError("Derived artifact scope exceeds its parent")
        parent_provenance = tuple(
            dict.fromkeys(parent.provenance_class for parent in parents)
        )
        if set(record.declared_input_provenance) != set(parent_provenance):
            raise ValueError("Declared transformation provenance hides an input")
        weakest = min(
            parent_provenance,
            key=lambda item: PROVENANCE_AUTHORITY[item],
        )
        if record.provenance_class is not weakest:
            raise ValueError(
                "Derived artifact provenance must equal its weakest input"
            )
        inherited_discovery = any(parent.discovery_only for parent in parents)
        if record.artifact_kind in {
            ArtifactKind.CANDIDATE_CLAIM,
            ArtifactKind.SECTION_DRAFT,
        } and inherited_discovery:
            raise ValueError("Discovery-only ancestry cannot support claims or sections")
        if inherited_discovery and not record.discovery_only:
            raise ValueError("Derived artifact cannot clear discovery-only ancestry")

        origin_provenance = tuple(
            sorted(
                {
                    item
                    for parent in parents
                    for item in parent.origin_provenance
                },
                key=lambda item: item.value,
            )
        )
        origin_source_ids = tuple(
            sorted(
                {
                    source_id
                    for parent in parents
                    for source_id in parent.origin_source_ids
                }
            )
        )
        citable_source_ids = tuple(
            source_id
            for source_id in origin_source_ids
            if source_catalog[source_id].provenance_class
            is record.provenance_class
        )
        if record.provenance_class is ProvenanceClass.GENERAL_AI_KNOWLEDGE:
            citable_source_ids = ()
        if set(record.source_ids) != set(citable_source_ids):
            raise ValueError("Derived artifact source lineage is incomplete or crossed")
        for source in record.source_identities:
            canonical = source_catalog.get(source.source_id)
            if canonical is None or canonical != source:
                raise ValueError("Derived artifact source identity changed")
        effective_authority = (
            0
            if record.discovery_only or inherited_discovery
            else PROVENANCE_AUTHORITY[record.provenance_class]
        )

    return ProvenanceArtifactTrace(
        artifact_id=record.artifact_id,
        artifact_kind=record.artifact_kind,
        provenance_class=record.provenance_class,
        knowledge_mode=record.knowledge_mode,
        origin_provenance=origin_provenance,
        origin_source_ids=origin_source_ids,
        citable_source_ids=citable_source_ids,
        parent_artifact_ids=record.parent_artifact_ids,
        effective_authority=effective_authority,
        discovery_only=record.discovery_only,
        verification_status=record.verification_status,
    )


def _scope_is_within(child: CapabilityScope, parent: CapabilityScope) -> bool:
    return (
        set(child.atomic_question_ids).issubset(parent.atomic_question_ids)
        and set(child.section_keys).issubset(parent.section_keys)
        and (
            not parent.entity_ids
            or (
                bool(child.entity_ids)
                and set(child.entity_ids).issubset(parent.entity_ids)
            )
        )
        and (
            parent.jurisdiction is None
            or child.jurisdiction == parent.jurisdiction
        )
        and (
            parent.stakeholder is None
            or child.stakeholder == parent.stakeholder
        )
        and (
            parent.time_scope is None
            or child.time_scope == parent.time_scope
        )
        and (
            not parent.date_semantics
            or (
                bool(child.date_semantics)
                and set(child.date_semantics).issubset(parent.date_semantics)
            )
        )
        and set(parent.constraints).issubset(child.constraints)
    )
