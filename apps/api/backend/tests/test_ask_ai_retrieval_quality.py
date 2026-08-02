from __future__ import annotations

import asyncio
from datetime import date

import pytest
from pydantic import ValidationError

from backend.ask.decision import Intent, PlanQuestion, PlanRequest, select_decision_plan
from backend.rag.models import (
    RetrievalBranch,
    RetrievalBranchHealth,
    RetrievalBranchOutcome,
    RetrievalBranchStatus,
    RetrievalHit,
)
from backend.rag.outcomes import RetrievalBranchExecution
from backend.rag.quality import (
    EvidenceExclusionReason,
    RelevanceThreshold,
    RetrievalMatchReason,
    RetrievalRelevancePolicy,
    admit_retrieval_evidence,
)
from backend.rag.selective import execute_selective_retrieval

BRANCH_SOURCE = {
    RetrievalBranch.VECTOR: "vector",
    RetrievalBranch.KEYWORD: "keyword",
    RetrievalBranch.GRAPH: "graph",
    RetrievalBranch.FAMILY_VERSION: "family",
    RetrievalBranch.SUMMARY: "summary",
}


def _plan(*questions: PlanQuestion):
    return select_decision_plan(PlanRequest(questions=questions))


def _policy(
    minimum: float = 0.5,
    *overrides: RelevanceThreshold,
) -> RetrievalRelevancePolicy:
    return RetrievalRelevancePolicy(
        thresholds=(
            *(
                RelevanceThreshold(branch=branch, minimum_score=minimum)
                for branch in RetrievalBranch
            ),
            *overrides,
        )
    )


def _hit(
    branch: RetrievalBranch,
    *,
    document_id: int = 1,
    version_id: int | None = 2,
    chunk_id: int | None = 3,
    text: str = "Official evidence",
    score: float = 0.8,
) -> RetrievalHit:
    scores = {
        "vector_score": score if branch is RetrievalBranch.VECTOR else 0,
        "keyword_score": (
            score
            if branch in {RetrievalBranch.KEYWORD, RetrievalBranch.SUMMARY}
            else 0
        ),
        "graph_score": (
            score
            if branch
            in {RetrievalBranch.GRAPH, RetrievalBranch.FAMILY_VERSION}
            else 0
        ),
    }
    return RetrievalHit(
        source=BRANCH_SOURCE[branch],  # type: ignore[arg-type]
        document_id=document_id,
        version_id=version_id,
        family_id=4,
        chunk_id=(
            chunk_id
            if branch in {RetrievalBranch.VECTOR, RetrievalBranch.KEYWORD}
            else None
        ),
        title=f"Document {document_id}",
        source_url=f"https://cerc.example/{document_id}",
        issuer="CERC",
        issue_date=date(2026, 7, 27),
        text=text,
        **scores,
    )


class _Provider:
    def __init__(
        self,
        hits: dict[RetrievalBranch, tuple[RetrievalHit, ...]],
    ) -> None:
        self.hits = hits

    def branch_search(
        self,
        branch: RetrievalBranch,
        query: str,
        *,
        limit: int,
        event_id: int | None = None,
    ) -> RetrievalBranchExecution:
        del query, limit, event_id
        hits = self.hits.get(branch, ())
        return RetrievalBranchExecution(
            outcome=RetrievalBranchOutcome(
                branch=branch,
                status=(
                    RetrievalBranchStatus.SATISFIED
                    if hits
                    else RetrievalBranchStatus.NO_MATCH
                ),
                health=RetrievalBranchHealth.HEALTHY,
                duration_ms=4,
                match_count=len(hits),
            ),
            hits=hits,
        )


def _retrieve(plan, hits):
    return asyncio.run(
        execute_selective_retrieval(
            plan,
            query="approved query",
            provider=_Provider(hits),
            limit=10,
        )
    )


def test_relevance_policy_requires_unique_complete_finite_branch_defaults() -> None:
    with pytest.raises(ValidationError, match="every branch default"):
        RetrievalRelevancePolicy(
            thresholds=(
                RelevanceThreshold(
                    branch=RetrievalBranch.VECTOR,
                    minimum_score=0.5,
                ),
            )
        )
    with pytest.raises(ValidationError, match="keys must be unique"):
        _policy(
            0.5,
            RelevanceThreshold(
                branch=RetrievalBranch.VECTOR,
                minimum_score=0.6,
            ),
        )
    with pytest.raises(ValidationError):
        RelevanceThreshold(
            branch=RetrievalBranch.VECTOR,
            minimum_score=float("nan"),
        )
    with pytest.raises(ValidationError, match="atomic intents"):
        RelevanceThreshold(
            branch=RetrievalBranch.VECTOR,
            minimum_score=0.5,
            intent=Intent.MULTI_PART_QUESTION,
        )


def test_exact_threshold_is_admitted_and_weaker_hit_becomes_healthy_no_match() -> None:
    plan = _plan(
        PlanQuestion(
            question_id="q1",
            intent=Intent.DEFINITION,
            has_resolved_entity=True,
            has_term_like_entity=True,
        )
    )
    retrieval = _retrieve(
        plan,
        {
            RetrievalBranch.VECTOR: (
                _hit(RetrievalBranch.VECTOR, score=0.5),
            ),
            RetrievalBranch.KEYWORD: (
                _hit(
                    RetrievalBranch.KEYWORD,
                    document_id=2,
                    score=0.499,
                ),
            ),
        },
    )

    result = admit_retrieval_evidence(plan, retrieval, policy=_policy())

    assert len(result.evidence_units) == 1
    assert result.evidence_units[0].scores.admitted_relevance == 0.5
    assert result.exclusions[0].reason is EvidenceExclusionReason.BELOW_THRESHOLD
    assert result.exclusions[0].observed_score == 0.499
    assert result.branch_outcomes[0].status is RetrievalBranchStatus.SATISFIED
    assert result.branch_outcomes[1].status is RetrievalBranchStatus.NO_MATCH
    assert result.branch_outcomes[1].health is RetrievalBranchHealth.HEALTHY


def test_vector_and_keyword_same_passage_become_one_canonical_evidence_unit() -> None:
    plan = _plan(
        PlanQuestion(
            question_id="q1",
            intent=Intent.DEFINITION,
            has_resolved_entity=True,
            has_term_like_entity=True,
        )
    )
    retrieval = _retrieve(
        plan,
        {
            RetrievalBranch.VECTOR: (
                _hit(
                    RetrievalBranch.VECTOR,
                    text="Short evidence",
                    score=0.7,
                ),
            ),
            RetrievalBranch.KEYWORD: (
                _hit(
                    RetrievalBranch.KEYWORD,
                    text="Longer official evidence excerpt",
                    score=0.9,
                ),
            ),
        },
    )

    result = admit_retrieval_evidence(plan, retrieval, policy=_policy())
    unit = result.evidence_units[0]

    assert len(result.evidence_units) == 1
    assert unit.retrieval_sources == ("vector", "keyword")
    assert unit.match_reasons == (
        RetrievalMatchReason.VECTOR_SIMILARITY,
        RetrievalMatchReason.KEYWORD_MATCH,
    )
    assert unit.text == "Longer official evidence excerpt"
    assert unit.scores.vector == 0.7
    assert unit.scores.keyword == 0.9
    assert unit.scores.admitted_relevance == 0.9


def test_distinct_graph_facts_from_same_document_remain_distinct() -> None:
    plan = _plan(
        PlanQuestion(
            question_id="q1",
            intent=Intent.STAKEHOLDER,
            has_resolved_entity=True,
        )
    )
    retrieval = _retrieve(
        plan,
        {
            RetrievalBranch.GRAPH: (
                _hit(
                    RetrievalBranch.GRAPH,
                    text="Generator is regulated by CERC",
                ),
                _hit(
                    RetrievalBranch.GRAPH,
                    text="Generator must submit monthly data",
                ),
            )
        },
    )

    result = admit_retrieval_evidence(plan, retrieval, policy=_policy())

    assert len(result.evidence_units) == 2
    assert len({unit.evidence_unit_id for unit in result.evidence_units}) == 2
    assert [unit.text for unit in result.evidence_units] == [
        "Generator is regulated by CERC",
        "Generator must submit monthly data",
    ]


def test_text_identical_graph_rows_remain_distinct_without_durable_fact_identity() -> None:
    plan = _plan(
        PlanQuestion(
            question_id="q1",
            intent=Intent.STAKEHOLDER,
            has_resolved_entity=True,
        )
    )
    retrieval = _retrieve(
        plan,
        {
            RetrievalBranch.GRAPH: (
                _hit(RetrievalBranch.GRAPH, text="CERC regulates DSM", score=0.7),
                _hit(RetrievalBranch.GRAPH, text="CERC  regulates   DSM", score=0.8),
            )
        },
    )

    result = admit_retrieval_evidence(plan, retrieval, policy=_policy())

    assert len(result.evidence_units) == 2
    assert [unit.scores.graph for unit in result.evidence_units] == [0.7, 0.8]
    assert all(unit.match_reasons == (
        RetrievalMatchReason.GRAPH_FACT,
    ) for unit in result.evidence_units)


def test_invalid_score_fails_closed_without_becoming_healthy_no_match() -> None:
    plan = _plan(
        PlanQuestion(
            question_id="q1",
            intent=Intent.DEFINITION,
            has_resolved_entity=True,
            has_term_like_entity=True,
        )
    )
    retrieval = _retrieve(
        plan,
        {
            RetrievalBranch.VECTOR: (
                _hit(RetrievalBranch.VECTOR, score=float("nan")),
            )
        },
    )

    result = admit_retrieval_evidence(plan, retrieval, policy=_policy())

    assert result.evidence_units == ()
    assert result.exclusions[0].reason is EvidenceExclusionReason.INVALID_SCORE
    assert result.exclusions[0].observed_score is None
    assert result.branch_outcomes[0].status is RetrievalBranchStatus.INVALID_OUTPUT
    assert result.branch_outcomes[0].health is RetrievalBranchHealth.FAILED
    assert (
        result.branch_outcomes[0].safe_failure_code
        == "RETRIEVAL_RELEVANCE_INVALID_SCORE"
    )


def test_valid_and_invalid_hits_produce_partial_degraded_quality() -> None:
    plan = _plan(
        PlanQuestion(
            question_id="q1",
            intent=Intent.DEFINITION,
            has_resolved_entity=True,
            has_term_like_entity=True,
        )
    )
    retrieval = _retrieve(
        plan,
        {
            RetrievalBranch.VECTOR: (
                _hit(RetrievalBranch.VECTOR, document_id=1, score=0.8),
                _hit(
                    RetrievalBranch.VECTOR,
                    document_id=2,
                    score=float("inf"),
                ),
            )
        },
    )

    result = admit_retrieval_evidence(plan, retrieval, policy=_policy())

    assert len(result.evidence_units) == 1
    assert result.branch_outcomes[0].status is RetrievalBranchStatus.PARTIAL
    assert result.branch_outcomes[0].health is RetrievalBranchHealth.DEGRADED
    assert result.branch_outcomes[0].match_count == 1


@pytest.mark.parametrize(
    "invalid_hit",
    (
        _hit(RetrievalBranch.VECTOR, document_id=0),
        _hit(RetrievalBranch.VECTOR, text=" "),
        RetrievalHit(
            **{
                **_hit(RetrievalBranch.VECTOR).__dict__,
                "keyword_score": float("nan"),
            }
        ),
    ),
)
def test_invalid_evidence_identity_content_or_secondary_score_fails_closed(
    invalid_hit: RetrievalHit,
) -> None:
    plan = _plan(
        PlanQuestion(
            question_id="q1",
            intent=Intent.DEFINITION,
            has_resolved_entity=True,
            has_term_like_entity=True,
        )
    )
    retrieval = _retrieve(
        plan,
        {RetrievalBranch.VECTOR: (invalid_hit,)},
    )

    result = admit_retrieval_evidence(plan, retrieval, policy=_policy())

    assert result.evidence_units == ()
    assert result.exclusions[0].reason is EvidenceExclusionReason.INVALID_EVIDENCE
    assert result.branch_outcomes[0].status is RetrievalBranchStatus.INVALID_OUTPUT


def test_intent_override_admits_only_atomic_questions_meeting_their_floor() -> None:
    plan = _plan(
        PlanQuestion(
            question_id="q1",
            intent=Intent.COMPARISON,
            has_resolved_entity=True,
        ),
        PlanQuestion(
            question_id="q2",
            intent=Intent.DEFINITION,
            has_resolved_entity=True,
            has_term_like_entity=True,
        ),
    )
    retrieval = _retrieve(
        plan,
        {
            RetrievalBranch.VECTOR: (
                _hit(RetrievalBranch.VECTOR, score=0.6),
            )
        },
    )
    policy = _policy(
        0.5,
        RelevanceThreshold(
            branch=RetrievalBranch.VECTOR,
            intent=Intent.COMPARISON,
            minimum_score=0.8,
        ),
        RelevanceThreshold(
            branch=RetrievalBranch.VECTOR,
            intent=Intent.DEFINITION,
            minimum_score=0.6,
        ),
    )

    result = admit_retrieval_evidence(plan, retrieval, policy=policy)

    assert result.evidence_units[0].question_ids == ("q2",)


def test_branch_specific_primary_scores_and_stable_branch_order() -> None:
    plan = _plan(
        PlanQuestion(
            question_id="q1",
            intent=Intent.SUMMARIZATION,
            has_known_sources=True,
        )
    )
    retrieval = _retrieve(
        plan,
        {
            RetrievalBranch.VECTOR: (
                _hit(RetrievalBranch.VECTOR, document_id=1),
            ),
            RetrievalBranch.KEYWORD: (
                _hit(RetrievalBranch.KEYWORD, document_id=2),
            ),
            RetrievalBranch.FAMILY_VERSION: (
                _hit(RetrievalBranch.FAMILY_VERSION, document_id=3),
            ),
            RetrievalBranch.SUMMARY: (
                _hit(RetrievalBranch.SUMMARY, document_id=4),
            ),
        },
    )

    result = admit_retrieval_evidence(plan, retrieval, policy=_policy())

    assert [unit.retrieval_sources for unit in result.evidence_units] == [
        ("vector",),
        ("keyword",),
        ("family",),
        ("summary",),
    ]
    assert tuple(item.branch for item in result.branch_outcomes) == tuple(
        RetrievalBranch
    )


def test_plan_retrieval_mismatch_is_rejected() -> None:
    source_plan = _plan(
        PlanQuestion(
            question_id="q1",
            intent=Intent.DEFINITION,
            has_resolved_entity=True,
            has_term_like_entity=True,
        )
    )
    other_plan = _plan(
        PlanQuestion(question_id="q1", intent=Intent.GENERAL_QUESTION)
    )
    retrieval = _retrieve(source_plan, {})

    with pytest.raises(ValueError, match="approved plan"):
        admit_retrieval_evidence(other_plan, retrieval, policy=_policy())


def test_quality_result_is_deterministic_and_strictly_serializable() -> None:
    plan = _plan(
        PlanQuestion(
            question_id="q1",
            intent=Intent.DEFINITION,
            has_resolved_entity=True,
            has_term_like_entity=True,
        )
    )
    retrieval = _retrieve(
        plan,
        {
            RetrievalBranch.VECTOR: (
                _hit(RetrievalBranch.VECTOR, score=0.8),
            )
        },
    )

    first = admit_retrieval_evidence(plan, retrieval, policy=_policy())
    second = admit_retrieval_evidence(plan, retrieval, policy=_policy())

    assert first == second
    assert first.model_dump_json() == second.model_dump_json()
    with pytest.raises(ValidationError):
        type(first).model_validate(
            {**first.model_dump(), "unexpected": "forbidden"}
        )
