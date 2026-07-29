from __future__ import annotations

from datetime import date
from typing import Any

import pytest
from pydantic import ValidationError

from backend.ask.decision import (
    EntityClass,
    EntityDecision,
    EntityResolution,
    EntityResolutionStatus,
)
from backend.rag.entity_graph import (
    EntityGraphCandidate,
    EntityGraphExclusionReason,
    EntityGraphRequest,
    EntityGraphStatus,
    GraphDirection,
    GraphRelationType,
    entity_graph_request_from_resolution,
    entity_graph_result_json,
    retrieve_entity_graph,
)
from backend.rag.quality import (
    CanonicalEvidenceUnit,
    EvidenceScoreSnapshot,
    RetrievalMatchReason,
)


def _resolution() -> EntityResolution:
    return EntityResolution(
        status=EntityResolutionStatus.RESOLVED,
        match_rule="exact_alias",
        selected=EntityDecision(
            mention="DSM",
            canonical_id="regulation.dsm",
            canonical_name="Deviation Settlement Mechanism",
            entity_class=EntityClass.REGULATION_FAMILY,
            aliases=("DSM",),
            jurisdiction="India",
            confidence=0.95,
        ),
        candidates=(),
        query_expansion=("DSM", "Deviation Settlement Mechanism"),
        required_confidence=0.5,
        direct_answer_allowed=True,
    )


def _request(
    *relations: GraphRelationType,
) -> EntityGraphRequest:
    return entity_graph_request_from_resolution(
        _resolution(),
        relation_types=relations or (GraphRelationType.REGULATED_BY,),
        question_ids=("q1",),
        section_keys=("relationships",),
    )


def _evidence(
    *,
    evidence_id: str = "evidence_11111111111111111111111111111111",
    question_ids: tuple[str, ...] = ("q1",),
) -> CanonicalEvidenceUnit:
    return CanonicalEvidenceUnit(
        policy_version="ask-ai-retrieval-quality-v1",
        evidence_unit_id=evidence_id,
        document_id=10,
        version_id=11,
        title="Official regulation",
        source_url="https://official.example/regulation",
        issuer="CERC",
        issue_date=date(2026, 7, 27),
        text="CERC regulates DSM.",
        retrieval_sources=("graph",),
        match_reasons=(RetrievalMatchReason.GRAPH_FACT,),
        question_ids=question_ids,
        scores=EvidenceScoreSnapshot(graph=0.9, admitted_relevance=0.9),
    )


def _candidate(
    *,
    edge_id: str = "edge-1",
    relationship: GraphRelationType = GraphRelationType.REGULATED_BY,
    subject_id: str = "regulation.dsm",
    object_id: str = "regulator.cerc",
    direction: GraphDirection = GraphDirection.OUTBOUND,
    evidence_ids: tuple[str, ...] = (
        "evidence_11111111111111111111111111111111",
    ),
) -> EntityGraphCandidate:
    return EntityGraphCandidate(
        edge_id=edge_id,
        subject_id=subject_id,
        subject_name="Deviation Settlement Mechanism",
        relationship=relationship,
        object_id_or_value=object_id,
        object_label="Central Electricity Regulatory Commission",
        direction=direction,
        qualifiers=(("jurisdiction", "India"),),
        extraction_confidence=0.9,
        backing_evidence_unit_ids=evidence_ids,
    )


class _Provider:
    def __init__(self, candidates: object) -> None:
        self.candidates = candidates
        self.requests: list[EntityGraphRequest] = []

    def search(self, request: EntityGraphRequest) -> Any:
        self.requests.append(request)
        if isinstance(self.candidates, Exception):
            raise self.candidates
        return self.candidates


def test_request_uses_canonical_entity_and_only_approved_expansion_terms() -> None:
    request = _request(GraphRelationType.REGULATED_BY)

    assert request.canonical_entity_id == "regulation.dsm"
    assert request.canonical_name == "Deviation Settlement Mechanism"
    assert request.jurisdiction == "India"
    assert request.approved_query_terms == (
        "Deviation Settlement Mechanism",
        "DSM",
    )
    assert request.relation_types == (GraphRelationType.REGULATED_BY,)


def test_clarification_or_missing_canonical_identity_cannot_query_graph() -> None:
    unresolved = _resolution().model_copy(
        update={
            "status": EntityResolutionStatus.CLARIFICATION_REQUIRED,
            "clarification_question": "Which DSM?",
            "direct_answer_allowed": False,
        }
    )

    with pytest.raises(ValueError, match="resolved entity"):
        entity_graph_request_from_resolution(
            unresolved,
            relation_types=(GraphRelationType.RELATES_TO,),
            question_ids=("q1",),
            section_keys=("related",),
        )


def test_distinct_backed_edges_become_distinct_structured_facts() -> None:
    candidates = (
        _candidate(edge_id="edge-2"),
        _candidate(edge_id="edge-1"),
    )
    provider = _Provider(candidates)

    result = retrieve_entity_graph(
        _request(),
        provider=provider,
        admitted_evidence=(_evidence(),),
    )

    assert result.status is EntityGraphStatus.SATISFIED
    assert tuple(fact.edge_id for fact in result.facts) == ("edge-1", "edge-2")
    assert len({fact.fact_id for fact in result.facts}) == 2
    assert all(not fact.payload.discovery_only for fact in result.facts)
    assert all(fact.backing_evidence == (_evidence(),) for fact in result.facts)
    assert provider.requests == [_request()]
    serialized = entity_graph_result_json(result)
    assert serialized == entity_graph_result_json(
        type(result).model_validate_json(serialized)
    )


def test_unbacked_and_relates_to_edges_remain_discovery_only() -> None:
    candidates = (
        _candidate(edge_id="edge-unbacked", evidence_ids=()),
        _candidate(
            edge_id="edge-related",
            relationship=GraphRelationType.RELATES_TO,
        ),
    )

    result = retrieve_entity_graph(
        _request(
            GraphRelationType.REGULATED_BY,
            GraphRelationType.RELATES_TO,
        ),
        provider=_Provider(candidates),
        admitted_evidence=(_evidence(),),
    )

    assert result.status is EntityGraphStatus.SATISFIED
    assert all(fact.payload.discovery_only for fact in result.facts)


@pytest.mark.parametrize(
    ("candidate", "reason"),
    [
        (
            _candidate(relationship=GraphRelationType.APPLIES_TO),
            EntityGraphExclusionReason.OUTSIDE_RELATION_SCOPE,
        ),
        (
            _candidate(subject_id="regulation.other"),
            EntityGraphExclusionReason.OUTSIDE_ENTITY_SCOPE,
        ),
        (
            _candidate(evidence_ids=("evidence_22222222222222222222222222222222",)),
            EntityGraphExclusionReason.UNKNOWN_EVIDENCE,
        ),
    ],
)
def test_invalid_neighbor_is_excluded_without_suppressing_valid_fact(
    candidate: EntityGraphCandidate,
    reason: EntityGraphExclusionReason,
) -> None:
    result = retrieve_entity_graph(
        _request(),
        provider=_Provider((_candidate(edge_id="valid"), candidate)),
        admitted_evidence=(_evidence(),),
    )

    assert result.status is EntityGraphStatus.PARTIAL
    assert tuple(fact.edge_id for fact in result.facts) == ("valid",)
    assert result.exclusions[-1].reason is reason


def test_crossed_question_evidence_and_duplicate_edges_are_isolated() -> None:
    result = retrieve_entity_graph(
        _request(),
        provider=_Provider(
            (
                _candidate(edge_id="crossed"),
                _candidate(edge_id="valid"),
                _candidate(edge_id="valid"),
            )
        ),
        admitted_evidence=(
            _evidence(question_ids=("q2",)),
            _evidence(
                evidence_id="evidence_33333333333333333333333333333333",
            ),
        ),
    )

    assert result.status is EntityGraphStatus.INVALID_OUTPUT
    assert result.safe_error_code == "ENTITY_GRAPH_INVALID_OUTPUT"


def test_inbound_scope_uses_object_identity() -> None:
    candidate = _candidate(
        subject_id="regulator.cerc",
        object_id="regulation.dsm",
        direction=GraphDirection.INBOUND,
    )

    result = retrieve_entity_graph(
        _request(),
        provider=_Provider((candidate,)),
        admitted_evidence=(_evidence(),),
    )

    assert result.status is EntityGraphStatus.SATISFIED
    assert result.facts[0].payload.subject_id == "regulator.cerc"


def test_provider_no_match_failure_and_malformed_output_remain_distinct() -> None:
    no_match = retrieve_entity_graph(
        _request(),
        provider=_Provider(()),
        admitted_evidence=(),
    )
    unavailable = retrieve_entity_graph(
        _request(),
        provider=_Provider(RuntimeError("secret database detail")),
        admitted_evidence=(),
    )
    invalid = retrieve_entity_graph(
        _request(),
        provider=_Provider({"not": "a sequence"}),
        admitted_evidence=(),
    )

    assert no_match.status is EntityGraphStatus.NO_MATCH
    assert no_match.safe_error_code is None
    assert unavailable.status is EntityGraphStatus.UNAVAILABLE
    assert unavailable.safe_error_code == "ENTITY_GRAPH_UNAVAILABLE"
    assert "secret" not in unavailable.model_dump_json()
    assert invalid.status is EntityGraphStatus.INVALID_OUTPUT
    assert invalid.safe_error_code == "ENTITY_GRAPH_INVALID_OUTPUT"

    malformed_evidence = _evidence().model_copy(
        update={"evidence_unit_id": "invalid"}
    )
    invalid_evidence = retrieve_entity_graph(
        _request(),
        provider=_Provider((_candidate(),)),
        admitted_evidence=(malformed_evidence,),
    )
    assert invalid_evidence.status is EntityGraphStatus.INVALID_OUTPUT


def test_contracts_reject_duplicates_unknown_fields_and_mutation() -> None:
    request = _request()
    payload = request.model_dump(mode="python")
    payload["unknown"] = True

    with pytest.raises(ValidationError):
        EntityGraphRequest.model_validate(payload)
    with pytest.raises(ValidationError, match="unique"):
        EntityGraphRequest.model_validate(
            {
                **request.model_dump(mode="python"),
                "relation_types": ["regulated_by", "regulated_by"],
            }
        )
    with pytest.raises(ValidationError, match="unique"):
        _candidate().model_copy(
            update={
                "qualifiers": (
                    ("jurisdiction", "India"),
                    ("jurisdiction", "India"),
                )
            }
        ).model_validate(
            _candidate().model_copy(
                update={
                    "qualifiers": (
                        ("jurisdiction", "India"),
                        ("jurisdiction", "India"),
                    )
                }
            ).model_dump(mode="python")
        )
    with pytest.raises(ValidationError):
        request.limit = 1  # type: ignore[misc]
