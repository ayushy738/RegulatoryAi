from __future__ import annotations

from datetime import UTC, date, datetime
from itertools import product

import pytest
from pydantic import ValidationError

from backend.ask.evidence_admission import AdmittedOfficialEvidence
from backend.ask.orchestration.contracts import (
    ArtifactEnvelope,
    ArtifactKind,
    ArtifactProducer,
    CandidateClaimPayload,
    CapabilityScope,
    CapabilityTerminalState,
    ConfidenceSignals,
    ContentDerivation,
    EvidenceUnitPayload,
    GeneralKnowledgeUnitPayload,
    KnowledgeMode,
    OrchestratorCapability,
    ProvenanceClass,
    ProvenanceLineage,
    SectionContentBlock,
    SectionDraftPayload,
    SourceIdentity,
    TimeDimension,
    TransformationStep,
    VerificationStatus,
)
from backend.ask.provenance import (
    LineageArtifactRecord,
    build_provenance_trace,
    lineage_record_from_admitted_evidence,
    lineage_record_from_artifact,
    lineage_record_from_graph_fact,
    lineage_record_from_timeline_event,
    provenance_trace_json,
)
from backend.rag.entity_graph import EntityGraphFact
from backend.rag.quality import (
    CanonicalEvidenceUnit,
    EvidenceScoreSnapshot,
    RetrievalMatchReason,
)
from backend.rag.timeline import TimelineEventRecord

NOW = datetime(2026, 7, 27, 12, 0, tzinfo=UTC)
EVIDENCE_1 = "evidence_" + "1" * 32
EVIDENCE_2 = "evidence_" + "2" * 32


def _scope(
    *,
    question_ids: tuple[str, ...] = ("question-1",),
    section_keys: tuple[str, ...] = ("section-1",),
) -> CapabilityScope:
    return CapabilityScope(
        atomic_question_ids=question_ids,
        section_keys=section_keys,
        entity_ids=("entity-1",),
        jurisdiction="India",
        stakeholder="regulated entity",
        time_scope="current",
        date_semantics=(TimeDimension.EFFECTIVE,),
        constraints=("approved plan",),
    )


def _source(
    source_id: str = "document-101",
    *,
    lane: ProvenanceClass = ProvenanceClass.INTERNAL_REGULATORY_CORPUS,
    title: str = "Official regulation",
) -> SourceIdentity:
    if lane is ProvenanceClass.LIVE_WEB_SOURCES:
        return SourceIdentity(
            source_id=source_id,
            provenance_class=lane,
            title=title,
            uri=f"https://live.example/{source_id}",
            issuer_or_publisher="Publisher",
            publication_at=NOW,
            retrieved_at=NOW,
        )
    return SourceIdentity(
        source_id=source_id,
        provenance_class=lane,
        title=title,
        uri=f"https://official.example/{source_id}",
        issuer_or_publisher="Regulator",
        issue_at=NOW,
    )


def _evidence_artifact(
    artifact_id: str = EVIDENCE_1,
    *,
    source: SourceIdentity | None = None,
    scope: CapabilityScope | None = None,
) -> ArtifactEnvelope:
    actual_source = source or _source()
    lane = actual_source.provenance_class
    mode = (
        KnowledgeMode.GROUNDED_REGULATORY
        if lane is ProvenanceClass.INTERNAL_REGULATORY_CORPUS
        else KnowledgeMode.LIVE_INTELLIGENCE
    )
    producer = (
        ArtifactProducer.REGULATORY_RETRIEVER
        if lane is ProvenanceClass.INTERNAL_REGULATORY_CORPUS
        else ArtifactProducer.NEWS_RETRIEVER
    )
    return ArtifactEnvelope(
        artifact_id=artifact_id,
        producer=producer,
        scope=scope or _scope(),
        payload=EvidenceUnitPayload(
            excerpt="Official evidence.",
            locator="page 1",
            match_reasons=("vector_similarity",),
        ),
        provenance=ProvenanceLineage(
            provenance_class=lane,
            knowledge_mode=mode,
            sources=(actual_source,),
            derivation=ContentDerivation.DIRECT,
            verification_status=VerificationStatus.PENDING,
        ),
        confidence_signals=ConfidenceSignals(retrieval_relevance=0.9),
        ancestry=("plan-1",),
        capability_status=CapabilityTerminalState.SATISFIED,
    )


def _canonical_evidence(
    evidence_id: str = EVIDENCE_1,
    *,
    document_id: int = 101,
    title: str = "Official regulation",
) -> CanonicalEvidenceUnit:
    return CanonicalEvidenceUnit(
        evidence_unit_id=evidence_id,
        policy_version="ask-ai-retrieval-quality-v1",
        document_id=document_id,
        version_id=None,
        family_id=None,
        chunk_id=1,
        title=title,
        source_url=f"https://official.example/document-{document_id}",
        issuer="Regulator",
        issue_date=date(2026, 7, 27),
        text="Official evidence.",
        retrieval_sources=("vector",),
        match_reasons=(RetrievalMatchReason.VECTOR_SIMILARITY,),
        question_ids=("question-1",),
        scores=EvidenceScoreSnapshot(
            vector=0.9,
            keyword=0,
            graph=0,
            admitted_relevance=0.9,
        ),
    )


def _evidence_record(
    artifact_id: str = EVIDENCE_1,
    *,
    source: SourceIdentity | None = None,
    scope: CapabilityScope | None = None,
) -> LineageArtifactRecord:
    actual_source = source or _source()
    document_id = int(actual_source.source_id.removeprefix("document-"))
    artifact = _evidence_artifact(
        artifact_id,
        source=actual_source,
        scope=scope,
    )
    return lineage_record_from_admitted_evidence(
        AdmittedOfficialEvidence(
            artifact=artifact,
            canonical_evidence=_canonical_evidence(
                artifact_id,
                document_id=document_id,
                title=actual_source.title,
            ),
        )
    )


def _live_evidence_record(source: SourceIdentity) -> LineageArtifactRecord:
    return LineageArtifactRecord(
        artifact_id="live-evidence",
        artifact_kind=ArtifactKind.EVIDENCE_UNIT,
        scope=_scope(),
        provenance_class=ProvenanceClass.LIVE_WEB_SOURCES,
        knowledge_mode=KnowledgeMode.LIVE_INTELLIGENCE,
        derivation=ContentDerivation.DIRECT,
        source_ids=(source.source_id,),
        source_identities=(source,),
        verification_status=VerificationStatus.PENDING,
    )


def _graph_fact(
    *,
    backed: bool = True,
    discovery_only: bool = False,
) -> EntityGraphFact:
    evidence = (_canonical_evidence(),) if backed else ()
    return EntityGraphFact(
        fact_id="graph_fact_" + "a" * 32,
        edge_id="edge-1",
        payload={
            "kind": ArtifactKind.STRUCTURED_FACT,
            "subject_id": "entity-1",
            "relationship": "regulated_by",
            "object_id_or_value": "regulator-1",
            "extraction_confidence": 0.85,
            "discovery_only": discovery_only or not backed,
        },
        backing_evidence=evidence,
    )


def _timeline_event(
    *,
    parent_id: str = "graph_fact_" + "a" * 32,
    discovery_only: bool = False,
) -> TimelineEventRecord:
    return TimelineEventRecord(
        event_id="timeline_event_" + "b" * 32,
        event_key="effective-date",
        payload={
            "kind": ArtifactKind.TIMELINE_EVENT,
            "label": "Rule became effective",
            "event_type": "effective",
            "date_value": NOW,
            "date_semantic": TimeDimension.EFFECTIVE,
            "date_confidence": 0.8,
        },
        provenance_class=ProvenanceClass.INTERNAL_REGULATORY_CORPUS,
        source_ids=("document-101",),
        ancestry=(parent_id,),
        discovery_only=discovery_only,
    )


def _derived_artifact(
    *,
    artifact_id: str,
    parent_ids: tuple[str, ...],
    parent_provenance: tuple[ProvenanceClass, ...],
    output_provenance: ProvenanceClass,
    sources: tuple[SourceIdentity, ...],
    section: bool = False,
    verification_status: VerificationStatus = VerificationStatus.PENDING,
    scope: CapabilityScope | None = None,
) -> ArtifactEnvelope:
    mode = {
        ProvenanceClass.INTERNAL_REGULATORY_CORPUS: (
            KnowledgeMode.GROUNDED_REGULATORY
        ),
        ProvenanceClass.LIVE_WEB_SOURCES: KnowledgeMode.LIVE_INTELLIGENCE,
        ProvenanceClass.GENERAL_AI_KNOWLEDGE: KnowledgeMode.GENERAL_AI,
    }[output_provenance]
    payload = (
        SectionDraftPayload(
            section_type="summary",
            content_blocks=(
                SectionContentBlock(block_type="paragraph", content="Summary."),
            ),
            candidate_claim_ids=parent_ids,
        )
        if section
        else CandidateClaimPayload(
            claim_text="A material claim.",
            material=True,
            supporting_artifact_ids=parent_ids,
        )
    )
    return ArtifactEnvelope(
        artifact_id=artifact_id,
        producer=ArtifactProducer.RESPONSE_COMPOSER,
        scope=scope or _scope(),
        payload=payload,
        provenance=ProvenanceLineage(
            provenance_class=output_provenance,
            knowledge_mode=mode,
            sources=sources,
            derivation=ContentDerivation.SUMMARIZED,
            transformations=(
                TransformationStep(
                    capability=OrchestratorCapability.RESPONSE_COMPOSER,
                    derivation=ContentDerivation.SUMMARIZED,
                    input_artifact_ids=parent_ids,
                    input_provenance=parent_provenance,
                    output_provenance=output_provenance,
                ),
            ),
            verification_status=verification_status,
        ),
        ancestry=(*parent_ids, "plan-1"),
        capability_status=CapabilityTerminalState.SATISFIED,
    )


def _record(
    artifact_id: str,
    *,
    parent_ids: tuple[str, ...],
    lane: ProvenanceClass = ProvenanceClass.INTERNAL_REGULATORY_CORPUS,
    source_ids: tuple[str, ...] = ("document-101",),
    scope: CapabilityScope | None = None,
    kind: ArtifactKind = ArtifactKind.STRUCTURED_FACT,
    discovery_only: bool = False,
) -> LineageArtifactRecord:
    mode = {
        ProvenanceClass.INTERNAL_REGULATORY_CORPUS: (
            KnowledgeMode.GROUNDED_REGULATORY
        ),
        ProvenanceClass.LIVE_WEB_SOURCES: KnowledgeMode.LIVE_INTELLIGENCE,
        ProvenanceClass.GENERAL_AI_KNOWLEDGE: KnowledgeMode.GENERAL_AI,
    }[lane]
    return LineageArtifactRecord(
        artifact_id=artifact_id,
        artifact_kind=kind,
        scope=scope or _scope(),
        provenance_class=lane,
        knowledge_mode=mode,
        derivation=ContentDerivation.EXTRACTED,
        source_ids=source_ids,
        parent_artifact_ids=parent_ids,
        declared_input_provenance=(lane,),
        transformation_capability=OrchestratorCapability.KNOWLEDGE_GRAPH,
        verification_status=VerificationStatus.PENDING,
        discovery_only=discovery_only,
    )


def test_full_graph_timeline_claim_section_lineage_is_transitive() -> None:
    evidence = _evidence_artifact()
    admitted = AdmittedOfficialEvidence(
        artifact=evidence,
        canonical_evidence=_canonical_evidence(),
    )
    graph = lineage_record_from_graph_fact(_graph_fact(), scope=_scope())
    timeline = lineage_record_from_timeline_event(_timeline_event(), scope=_scope())
    claim = _derived_artifact(
        artifact_id="claim-1",
        parent_ids=(timeline.artifact_id,),
        parent_provenance=(ProvenanceClass.INTERNAL_REGULATORY_CORPUS,),
        output_provenance=ProvenanceClass.INTERNAL_REGULATORY_CORPUS,
        sources=(_source(),),
    )
    section = _derived_artifact(
        artifact_id="section-1",
        parent_ids=("claim-1",),
        parent_provenance=(ProvenanceClass.INTERNAL_REGULATORY_CORPUS,),
        output_provenance=ProvenanceClass.INTERNAL_REGULATORY_CORPUS,
        sources=(_source(),),
        section=True,
    )

    result = build_provenance_trace(
        (
            lineage_record_from_artifact(section),
            timeline,
            lineage_record_from_admitted_evidence(admitted),
            lineage_record_from_artifact(claim),
            graph,
        )
    )
    section_trace = next(
        trace for trace in result.traces if trace.artifact_id == "section-1"
    )

    assert section_trace.origin_source_ids == ("document-101",)
    assert section_trace.citable_source_ids == ("document-101",)
    assert section_trace.effective_authority == 3
    assert section_trace.discovery_only is False
    assert tuple(trace.artifact_id for trace in result.traces) == tuple(
        sorted(trace.artifact_id for trace in result.traces)
    )


def test_summary_retains_union_of_independent_official_sources() -> None:
    source_1 = _source()
    source_2 = _source("document-102", title="Second regulation")
    evidence_1 = _evidence_record(EVIDENCE_1, source=source_1)
    evidence_2 = _evidence_record(EVIDENCE_2, source=source_2)
    claim = _derived_artifact(
        artifact_id="claim-1",
        parent_ids=(EVIDENCE_1, EVIDENCE_2),
        parent_provenance=(ProvenanceClass.INTERNAL_REGULATORY_CORPUS,),
        output_provenance=ProvenanceClass.INTERNAL_REGULATORY_CORPUS,
        sources=(source_1, source_2),
    )

    result = build_provenance_trace(
        (lineage_record_from_artifact(claim), evidence_2, evidence_1)
    )

    claim_trace = next(
        trace for trace in result.traces if trace.artifact_id == "claim-1"
    )
    assert claim_trace.origin_source_ids == (
        "document-101",
        "document-102",
    )
    assert tuple(source.source_id for source in result.source_catalog) == (
        "document-101",
        "document-102",
    )


def test_mixed_origins_use_weakest_lane_without_cross_lane_citations() -> None:
    official = _evidence_record()
    general = lineage_record_from_artifact(
        ArtifactEnvelope(
            artifact_id="general-1",
            producer=ArtifactProducer.GENERAL_AI,
            scope=_scope(),
            payload=GeneralKnowledgeUnitPayload(content="General inference."),
            provenance=ProvenanceLineage(
                provenance_class=ProvenanceClass.GENERAL_AI_KNOWLEDGE,
                knowledge_mode=KnowledgeMode.GENERAL_AI,
                derivation=ContentDerivation.GENERATED,
                verification_status=VerificationStatus.NOT_APPLICABLE,
            ),
            ancestry=("plan-1",),
            capability_status=CapabilityTerminalState.SATISFIED,
        )
    )
    mixed_claim = _derived_artifact(
        artifact_id="claim-mixed",
        parent_ids=(EVIDENCE_1, "general-1"),
        parent_provenance=(
            ProvenanceClass.INTERNAL_REGULATORY_CORPUS,
            ProvenanceClass.GENERAL_AI_KNOWLEDGE,
        ),
        output_provenance=ProvenanceClass.GENERAL_AI_KNOWLEDGE,
        sources=(),
    )

    result = build_provenance_trace(
        (official, general, lineage_record_from_artifact(mixed_claim))
    )
    trace = next(
        item for item in result.traces if item.artifact_id == "claim-mixed"
    )

    assert trace.origin_provenance == (
        ProvenanceClass.GENERAL_AI_KNOWLEDGE,
        ProvenanceClass.INTERNAL_REGULATORY_CORPUS,
    )
    assert trace.origin_source_ids == ("document-101",)
    assert trace.citable_source_ids == ()
    assert trace.provenance_class is ProvenanceClass.GENERAL_AI_KNOWLEDGE
    assert trace.effective_authority == 1


@pytest.mark.parametrize(
    ("left_lane", "right_lane"),
    tuple(product(tuple(ProvenanceClass), repeat=2)),
)
def test_authority_is_monotonic_for_every_provenance_pair(
    left_lane: ProvenanceClass,
    right_lane: ProvenanceClass,
) -> None:
    def root(label: str, lane: ProvenanceClass) -> LineageArtifactRecord:
        mode = {
            ProvenanceClass.INTERNAL_REGULATORY_CORPUS: (
                KnowledgeMode.GROUNDED_REGULATORY
            ),
            ProvenanceClass.LIVE_WEB_SOURCES: KnowledgeMode.LIVE_INTELLIGENCE,
            ProvenanceClass.GENERAL_AI_KNOWLEDGE: KnowledgeMode.GENERAL_AI,
        }[lane]
        if lane is ProvenanceClass.GENERAL_AI_KNOWLEDGE:
            return LineageArtifactRecord(
                artifact_id=f"{label}-root",
                artifact_kind=ArtifactKind.GENERAL_KNOWLEDGE_UNIT,
                scope=_scope(),
                provenance_class=lane,
                knowledge_mode=mode,
                derivation=ContentDerivation.GENERATED,
                verification_status=VerificationStatus.NOT_APPLICABLE,
            )
        source = _source(
            f"{lane.value}-{label}",
            lane=lane,
            title=f"{lane.value} {label}",
        )
        return LineageArtifactRecord(
            artifact_id=f"{label}-root",
            artifact_kind=ArtifactKind.EVIDENCE_UNIT,
            scope=_scope(),
            provenance_class=lane,
            knowledge_mode=mode,
            derivation=ContentDerivation.DIRECT,
            source_ids=(source.source_id,),
            source_identities=(source,),
            verification_status=VerificationStatus.PENDING,
        )

    left = root("left", left_lane)
    right = root("right", right_lane)
    authority = {
        ProvenanceClass.INTERNAL_REGULATORY_CORPUS: 3,
        ProvenanceClass.LIVE_WEB_SOURCES: 2,
        ProvenanceClass.GENERAL_AI_KNOWLEDGE: 1,
    }
    weakest = min((left_lane, right_lane), key=authority.__getitem__)
    input_lanes = tuple(dict.fromkeys((left_lane, right_lane)))
    source_ids = tuple(
        record.source_ids[0]
        for record in (left, right)
        if record.provenance_class is weakest and record.source_ids
    )
    derived = LineageArtifactRecord(
        artifact_id="derived",
        artifact_kind=ArtifactKind.STRUCTURED_FACT,
        scope=_scope(),
        provenance_class=weakest,
        knowledge_mode={
            ProvenanceClass.INTERNAL_REGULATORY_CORPUS: (
                KnowledgeMode.GROUNDED_REGULATORY
            ),
            ProvenanceClass.LIVE_WEB_SOURCES: KnowledgeMode.LIVE_INTELLIGENCE,
            ProvenanceClass.GENERAL_AI_KNOWLEDGE: KnowledgeMode.GENERAL_AI,
        }[weakest],
        derivation=ContentDerivation.INFERRED,
        source_ids=source_ids,
        parent_artifact_ids=(left.artifact_id, right.artifact_id),
        declared_input_provenance=input_lanes,
        transformation_capability=OrchestratorCapability.KNOWLEDGE_GRAPH,
        verification_status=VerificationStatus.PENDING,
    )

    trace = build_provenance_trace((derived, right, left)).traces[0]

    assert trace.artifact_id == "derived"
    assert trace.effective_authority == min(
        authority[left_lane],
        authority[right_lane],
    )
    assert trace.effective_authority <= authority[left_lane]
    assert trace.effective_authority <= authority[right_lane]


def test_authority_upgrade_and_hidden_input_provenance_fail_closed() -> None:
    official = _evidence_record()
    live_source = _source(
        "live-1",
        lane=ProvenanceClass.LIVE_WEB_SOURCES,
        title="Live report",
    )
    live = _live_evidence_record(live_source)
    upgraded = LineageArtifactRecord(
        artifact_id="fact-upgraded",
        artifact_kind=ArtifactKind.STRUCTURED_FACT,
        scope=_scope(),
        provenance_class=ProvenanceClass.INTERNAL_REGULATORY_CORPUS,
        knowledge_mode=KnowledgeMode.GROUNDED_REGULATORY,
        derivation=ContentDerivation.EXTRACTED,
        source_ids=("document-101",),
        parent_artifact_ids=(EVIDENCE_1, "live-evidence"),
        declared_input_provenance=(
            ProvenanceClass.INTERNAL_REGULATORY_CORPUS,
        ),
        transformation_capability=OrchestratorCapability.KNOWLEDGE_GRAPH,
        verification_status=VerificationStatus.PENDING,
    )

    with pytest.raises(ValueError, match="hides an input"):
        build_provenance_trace((official, live, upgraded))

    visible = upgraded.model_copy(
        update={
            "declared_input_provenance": (
                ProvenanceClass.INTERNAL_REGULATORY_CORPUS,
                ProvenanceClass.LIVE_WEB_SOURCES,
            )
        }
    )
    with pytest.raises(ValueError, match="weakest input"):
        build_provenance_trace((official, live, visible))


def test_missing_or_cross_lane_sources_cannot_be_declared() -> None:
    official = _evidence_record()
    live_source = _source(
        "live-1",
        lane=ProvenanceClass.LIVE_WEB_SOURCES,
        title="Live report",
    )
    live = _live_evidence_record(live_source)
    crossed = LineageArtifactRecord(
        artifact_id="fact-live",
        artifact_kind=ArtifactKind.STRUCTURED_FACT,
        scope=_scope(),
        provenance_class=ProvenanceClass.LIVE_WEB_SOURCES,
        knowledge_mode=KnowledgeMode.LIVE_INTELLIGENCE,
        derivation=ContentDerivation.EXTRACTED,
        source_ids=("document-101", "live-1"),
        parent_artifact_ids=(EVIDENCE_1, "live-evidence"),
        declared_input_provenance=(
            ProvenanceClass.INTERNAL_REGULATORY_CORPUS,
            ProvenanceClass.LIVE_WEB_SOURCES,
        ),
        transformation_capability=OrchestratorCapability.KNOWLEDGE_GRAPH,
        verification_status=VerificationStatus.PENDING,
    )

    with pytest.raises(ValueError, match="incomplete or crossed"):
        build_provenance_trace((official, live, crossed))

    hidden = _record(
        "fact-hidden",
        parent_ids=(EVIDENCE_1,),
        source_ids=(),
    )
    with pytest.raises(ValueError, match="incomplete or crossed"):
        build_provenance_trace((official, hidden))


def test_source_identity_cannot_change_during_transformation() -> None:
    evidence = _evidence_record()
    changed = _derived_artifact(
        artifact_id="claim-1",
        parent_ids=(EVIDENCE_1,),
        parent_provenance=(ProvenanceClass.INTERNAL_REGULATORY_CORPUS,),
        output_provenance=ProvenanceClass.INTERNAL_REGULATORY_CORPUS,
        sources=(_source(title="Changed title"),),
    )

    with pytest.raises(ValueError, match="Source identity changed"):
        build_provenance_trace((evidence, lineage_record_from_artifact(changed)))


def test_missing_parent_cycle_and_duplicate_identity_are_refused() -> None:
    missing = _record("fact-1", parent_ids=("absent",))
    with pytest.raises(ValueError, match="parent artifact is missing"):
        build_provenance_trace((missing,))

    first = _record("fact-1", parent_ids=("fact-2",))
    second = _record("fact-2", parent_ids=("fact-1",))
    with pytest.raises(ValueError, match="acyclic"):
        build_provenance_trace((first, second))

    root = _evidence_record()
    with pytest.raises(ValueError, match="must be unique"):
        build_provenance_trace((root, root))


def test_derived_scope_may_narrow_but_cannot_broaden() -> None:
    parent = _evidence_record(
        scope=_scope(
            question_ids=("question-1", "question-2"),
            section_keys=("section-1", "section-2"),
        )
    )
    narrowed = _record(
        "fact-narrow",
        parent_ids=(EVIDENCE_1,),
        scope=_scope(),
    )

    assert build_provenance_trace((parent, narrowed)).status == "complete"

    broadened = narrowed.model_copy(
        update={
            "scope": _scope(
                question_ids=("question-1", "question-3"),
                section_keys=("section-1",),
            )
        }
    )
    with pytest.raises(ValueError, match="scope exceeds"):
        build_provenance_trace((parent, broadened))


def test_discovery_only_taint_survives_timeline_and_cannot_support_claim() -> None:
    evidence = _evidence_record()
    graph = lineage_record_from_graph_fact(
        _graph_fact(discovery_only=True),
        scope=_scope(),
    )
    event = lineage_record_from_timeline_event(
        _timeline_event(discovery_only=True),
        scope=_scope(),
    )
    result = build_provenance_trace((evidence, graph, event))
    timeline_trace = next(
        trace for trace in result.traces if trace.artifact_id == event.artifact_id
    )

    assert timeline_trace.discovery_only is True
    assert timeline_trace.effective_authority == 0
    assert timeline_trace.origin_source_ids == ("document-101",)

    claim = _derived_artifact(
        artifact_id="claim-1",
        parent_ids=(event.artifact_id,),
        parent_provenance=(ProvenanceClass.INTERNAL_REGULATORY_CORPUS,),
        output_provenance=ProvenanceClass.INTERNAL_REGULATORY_CORPUS,
        sources=(_source(),),
    )
    with pytest.raises(ValueError, match="cannot support claims"):
        build_provenance_trace(
            (evidence, graph, event, lineage_record_from_artifact(claim))
        )


def test_unbacked_graph_relation_retains_zero_authority_discovery_lineage() -> None:
    graph = lineage_record_from_graph_fact(
        _graph_fact(backed=False),
        scope=_scope(),
    )

    result = build_provenance_trace((graph,))
    trace = result.traces[0]

    assert trace.discovery_only is True
    assert trace.effective_authority == 0
    assert trace.origin_source_ids == ()
    assert result.source_catalog == ()


def test_multiple_chunks_from_one_document_keep_distinct_parents_one_source() -> None:
    first = _evidence_record()
    second = _evidence_record(EVIDENCE_2)
    fact = _graph_fact().model_copy(
        update={
            "backing_evidence": (
                _canonical_evidence(EVIDENCE_1),
                _canonical_evidence(EVIDENCE_2),
            )
        }
    )
    graph = lineage_record_from_graph_fact(fact, scope=_scope())

    result = build_provenance_trace((first, second, graph))
    trace = next(
        item for item in result.traces if item.artifact_id == graph.artifact_id
    )

    assert graph.parent_artifact_ids == (EVIDENCE_1, EVIDENCE_2)
    assert trace.origin_source_ids == ("document-101",)
    assert trace.citable_source_ids == ("document-101",)


def test_verification_status_changes_support_not_origin() -> None:
    evidence = _evidence_record()
    pending = _derived_artifact(
        artifact_id="claim-1",
        parent_ids=(EVIDENCE_1,),
        parent_provenance=(ProvenanceClass.INTERNAL_REGULATORY_CORPUS,),
        output_provenance=ProvenanceClass.INTERNAL_REGULATORY_CORPUS,
        sources=(_source(),),
    )
    supported = _derived_artifact(
        artifact_id="claim-1",
        parent_ids=(EVIDENCE_1,),
        parent_provenance=(ProvenanceClass.INTERNAL_REGULATORY_CORPUS,),
        output_provenance=ProvenanceClass.INTERNAL_REGULATORY_CORPUS,
        sources=(_source(),),
        verification_status=VerificationStatus.SUPPORTED,
    )

    pending_trace = build_provenance_trace(
        (evidence, lineage_record_from_artifact(pending))
    ).traces[0]
    supported_trace = build_provenance_trace(
        (evidence, lineage_record_from_artifact(supported))
    ).traces[0]

    assert pending_trace.origin_source_ids == supported_trace.origin_source_ids
    assert pending_trace.citable_source_ids == supported_trace.citable_source_ids


def test_trace_is_input_order_independent_and_json_is_deterministic() -> None:
    evidence = _evidence_record()
    graph = lineage_record_from_graph_fact(_graph_fact(), scope=_scope())

    first = build_provenance_trace((graph, evidence))
    second = build_provenance_trace((evidence, graph))

    assert first == second
    assert provenance_trace_json(first) == provenance_trace_json(second)


def test_artifact_adapter_rejects_incomplete_claim_and_section_lineage() -> None:
    claim = _derived_artifact(
        artifact_id="claim-1",
        parent_ids=(EVIDENCE_1,),
        parent_provenance=(ProvenanceClass.INTERNAL_REGULATORY_CORPUS,),
        output_provenance=ProvenanceClass.INTERNAL_REGULATORY_CORPUS,
        sources=(_source(),),
    )
    bad_claim = claim.model_copy(
        update={
            "payload": claim.payload.model_copy(
                update={"supporting_artifact_ids": (EVIDENCE_2,)}
            )
        }
    )
    with pytest.raises(ValueError, match="Claim support"):
        lineage_record_from_artifact(bad_claim)

    section = _derived_artifact(
        artifact_id="section-1",
        parent_ids=("claim-1",),
        parent_provenance=(ProvenanceClass.INTERNAL_REGULATORY_CORPUS,),
        output_provenance=ProvenanceClass.INTERNAL_REGULATORY_CORPUS,
        sources=(_source(),),
        section=True,
    )
    bad_section = section.model_copy(
        update={
            "payload": section.payload.model_copy(
                update={"candidate_claim_ids": ("claim-2",)}
            )
        }
    )
    with pytest.raises(ValueError, match="claim lineage is incomplete"):
        lineage_record_from_artifact(bad_section)

    step = claim.provenance.transformations[0]  # type: ignore[union-attr]
    hidden_history = claim.model_copy(
        update={
            "provenance": claim.provenance.model_copy(  # type: ignore[union-attr]
                update={"transformations": (step, step)}
            )
        }
    )
    with pytest.raises(ValueError, match="one local transformation"):
        lineage_record_from_artifact(hidden_history)


def test_contracts_are_strict_and_immutable() -> None:
    record = _evidence_record()
    values = record.model_dump(mode="python")
    values["unexpected"] = True
    with pytest.raises(ValidationError):
        LineageArtifactRecord.model_validate(values, strict=True)
    with pytest.raises(ValidationError):
        record.artifact_id = "changed"  # type: ignore[misc]


def test_official_evidence_cannot_bypass_the_admission_adapter() -> None:
    with pytest.raises(ValueError, match="admission boundary"):
        lineage_record_from_artifact(_evidence_artifact())


def test_artifact_kind_cannot_borrow_another_capability() -> None:
    values = _record(
        "timeline-1",
        parent_ids=(EVIDENCE_1,),
    ).model_dump(mode="python")
    values["artifact_kind"] = ArtifactKind.TIMELINE_EVENT
    values["transformation_capability"] = OrchestratorCapability.KNOWLEDGE_GRAPH
    with pytest.raises(ValidationError, match="capability disagree"):
        LineageArtifactRecord.model_validate(values, strict=True)
