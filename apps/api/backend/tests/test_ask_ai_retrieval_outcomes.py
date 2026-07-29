from __future__ import annotations

import json
from collections.abc import Callable
from datetime import date

import pytest
from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError

from backend.rag import retrieval as retrieval_module
from backend.rag.models import (
    RETRIEVAL_OUTCOME_POLICY_VERSION,
    RetrievalBranch,
    RetrievalBranchHealth,
    RetrievalBranchOutcome,
    RetrievalBranchStatus,
    RetrievalHit,
)
from backend.rag.outcomes import (
    PartialRetrievalBranchResult,
    execute_retrieval_branch,
)
from backend.rag.retrieval import SupabaseHybridRetrieval

BRANCH_SOURCE = {
    RetrievalBranch.VECTOR: "vector",
    RetrievalBranch.KEYWORD: "keyword",
    RetrievalBranch.GRAPH: "graph",
    RetrievalBranch.FAMILY_VERSION: "family",
    RetrievalBranch.SUMMARY: "summary",
}
RAW_METHOD = {
    RetrievalBranch.VECTOR: "_vector_search",
    RetrievalBranch.KEYWORD: "_keyword_search",
    RetrievalBranch.GRAPH: "_graph_search",
    RetrievalBranch.FAMILY_VERSION: "_family_search",
    RetrievalBranch.SUMMARY: "_summary_search",
}
PUBLIC_METHOD = {
    RetrievalBranch.VECTOR: "vector_search",
    RetrievalBranch.KEYWORD: "keyword_search",
    RetrievalBranch.GRAPH: "graph_search",
    RetrievalBranch.FAMILY_VERSION: "family_search",
    RetrievalBranch.SUMMARY: "summary_search",
}


def _hit(branch: RetrievalBranch, index: int = 1) -> RetrievalHit:
    return RetrievalHit(
        source=BRANCH_SOURCE[branch],  # type: ignore[arg-type]
        document_id=index,
        title=f"Document {index}",
        source_url=f"https://example.test/{index}",
        issuer="CERC",
        issue_date=date(2026, 7, index),
        chunk_id=index if branch in {RetrievalBranch.VECTOR, RetrievalBranch.KEYWORD} else None,
        text=f"Evidence {index}",
    )


def _clock(
    started: float = 10.0,
    completed: float = 10.25,
) -> Callable[[], float]:
    values = iter((started, completed))
    return lambda: next(values)


@pytest.mark.parametrize("branch", tuple(RetrievalBranch))
def test_every_branch_reports_satisfied_health_and_timing(
    branch: RetrievalBranch,
) -> None:
    hit = _hit(branch)

    execution = execute_retrieval_branch(
        branch=branch,
        worker=lambda: [hit],
        clock=_clock(),
    )

    assert execution.hits == (hit,)
    assert execution.outcome == RetrievalBranchOutcome(
        branch=branch,
        status=RetrievalBranchStatus.SATISFIED,
        health=RetrievalBranchHealth.HEALTHY,
        duration_ms=250,
        match_count=1,
    )


@pytest.mark.parametrize("branch", tuple(RetrievalBranch))
def test_every_branch_distinguishes_healthy_no_match(
    branch: RetrievalBranch,
) -> None:
    execution = execute_retrieval_branch(
        branch=branch,
        worker=lambda: [],
        clock=_clock(),
    )

    assert execution.hits == ()
    assert execution.outcome.status is RetrievalBranchStatus.NO_MATCH
    assert execution.outcome.health is RetrievalBranchHealth.HEALTHY
    assert execution.outcome.safe_failure_code is None


@pytest.mark.parametrize("branch", tuple(RetrievalBranch))
def test_every_branch_maps_exceptions_to_safe_unavailable(
    branch: RetrievalBranch,
) -> None:
    def fail() -> object:
        raise RuntimeError("secret-provider-detail")

    execution = execute_retrieval_branch(
        branch=branch,
        worker=fail,
        clock=_clock(),
    )

    assert execution.hits == ()
    assert execution.outcome.status is RetrievalBranchStatus.UNAVAILABLE
    assert execution.outcome.health is RetrievalBranchHealth.FAILED
    assert execution.outcome.safe_failure_code == "RETRIEVAL_BRANCH_UNAVAILABLE"
    assert "secret-provider-detail" not in execution.outcome.model_dump_json()


@pytest.mark.parametrize("branch", tuple(RetrievalBranch))
def test_every_branch_preserves_timeout_as_distinct_failure(
    branch: RetrievalBranch,
) -> None:
    def time_out() -> object:
        raise TimeoutError("upstream timeout detail")

    execution = execute_retrieval_branch(
        branch=branch,
        worker=time_out,
        clock=_clock(),
    )

    assert execution.outcome.status is RetrievalBranchStatus.TIMED_OUT
    assert execution.outcome.safe_failure_code == "RETRIEVAL_BRANCH_TIMED_OUT"


@pytest.mark.parametrize("branch", tuple(RetrievalBranch))
def test_every_branch_rejects_malformed_or_wrong_lane_hits(
    branch: RetrievalBranch,
) -> None:
    wrong_branch = next(candidate for candidate in RetrievalBranch if candidate is not branch)

    malformed = execute_retrieval_branch(
        branch=branch,
        worker=lambda: [_hit(wrong_branch)],
        clock=_clock(),
    )

    assert malformed.hits == ()
    assert malformed.outcome.status is RetrievalBranchStatus.INVALID_OUTPUT
    assert (
        malformed.outcome.safe_failure_code
        == "RETRIEVAL_BRANCH_INVALID_OUTPUT"
    )


@pytest.mark.parametrize("branch", tuple(RetrievalBranch))
def test_provider_branch_seam_observes_each_legacy_worker(
    branch: RetrievalBranch,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = SupabaseHybridRetrieval()
    hit = _hit(branch)
    calls: list[tuple[str, int, int | None]] = []

    def worker(
        query: str,
        *,
        limit: int,
        event_id: int | None,
    ) -> list[RetrievalHit]:
        calls.append((query, limit, event_id))
        return [hit]

    monkeypatch.setattr(provider, RAW_METHOD[branch], worker)

    execution = provider.branch_search(
        branch,
        "DSM",
        limit=7,
        event_id=42,
        clock=_clock(),
    )

    assert calls == [("DSM", 7, 42)]
    assert execution.hits == (hit,)
    assert execution.outcome.branch is branch


@pytest.mark.parametrize("branch", tuple(RetrievalBranch))
def test_provider_branch_seam_reports_each_legacy_worker_failure(
    branch: RetrievalBranch,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = SupabaseHybridRetrieval()

    def fail(*_args, **_kwargs):
        raise RuntimeError("private branch failure detail")

    monkeypatch.setattr(provider, RAW_METHOD[branch], fail)

    execution = provider.branch_search(
        branch,
        "DSM",
        limit=7,
        event_id=42,
        clock=_clock(),
    )

    assert execution.hits == ()
    assert execution.outcome.status is RetrievalBranchStatus.UNAVAILABLE
    assert "private branch failure detail" not in execution.outcome.model_dump_json()


@pytest.mark.parametrize("branch", tuple(RetrievalBranch))
def test_legacy_public_branch_methods_keep_empty_list_failure_behavior(
    branch: RetrievalBranch,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = SupabaseHybridRetrieval()

    def fail(*_args, **_kwargs):
        raise RuntimeError("legacy must remain fail-closed")

    monkeypatch.setattr(provider, RAW_METHOD[branch], fail)

    result = getattr(provider, PUBLIC_METHOD[branch])(
        "DSM",
        limit=5,
        event_id=None,
    )

    assert result == []


def test_hybrid_result_exposes_stable_outcomes_without_changing_ranked_hits(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = SupabaseHybridRetrieval()
    returned = {
        RetrievalBranch.VECTOR: [_hit(RetrievalBranch.VECTOR, 1)],
        RetrievalBranch.KEYWORD: [_hit(RetrievalBranch.KEYWORD, 2)],
        RetrievalBranch.GRAPH: [_hit(RetrievalBranch.GRAPH, 3)],
        RetrievalBranch.FAMILY_VERSION: TimeoutError("family unavailable"),
        RetrievalBranch.SUMMARY: [],
    }

    for branch in returned:
        def worker(*_args, selected=branch, **_kwargs):
            result = returned[selected]
            if isinstance(result, Exception):
                raise result
            return result

        monkeypatch.setattr(provider, RAW_METHOD[branch], worker)

    result = provider.hybrid_search("DSM", limit=5)

    assert {hit.document_id for hit in result.hits} == {1, 2, 3}
    assert [outcome.branch for outcome in result.branch_outcomes] == list(
        RetrievalBranch
    )
    assert [outcome.status for outcome in result.branch_outcomes] == [
        RetrievalBranchStatus.SATISFIED,
        RetrievalBranchStatus.SATISFIED,
        RetrievalBranchStatus.SATISFIED,
        RetrievalBranchStatus.TIMED_OUT,
        RetrievalBranchStatus.NO_MATCH,
    ]


def test_graph_partial_failure_preserves_healthy_units_and_is_not_no_match(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = SupabaseHybridRetrieval()
    graph_hit = _hit(RetrievalBranch.GRAPH)

    def fail(*_args, **_kwargs):
        raise SQLAlchemyError("one graph table is unavailable")

    monkeypatch.setattr(retrieval_module, "_deadline_hits", fail)
    monkeypatch.setattr(
        retrieval_module,
        "_obligation_hits",
        lambda *_args, **_kwargs: [graph_hit],
    )
    monkeypatch.setattr(
        retrieval_module,
        "_stakeholder_hits",
        lambda *_args, **_kwargs: [],
    )
    monkeypatch.setattr(
        retrieval_module,
        "_relationship_hits",
        lambda *_args, **_kwargs: [],
    )

    execution = provider.branch_search(
        RetrievalBranch.GRAPH,
        "DSM",
        limit=5,
        clock=_clock(),
    )

    assert execution.hits == (graph_hit,)
    assert execution.outcome.status is RetrievalBranchStatus.PARTIAL
    assert execution.outcome.health is RetrievalBranchHealth.DEGRADED
    assert execution.outcome.safe_failure_code == "RETRIEVAL_BRANCH_PARTIAL"
    assert provider.graph_search("DSM", limit=5) == [graph_hit]


def test_partial_worker_output_is_valid_even_when_healthy_units_find_no_match() -> None:
    execution = execute_retrieval_branch(
        branch=RetrievalBranch.GRAPH,
        worker=lambda: PartialRetrievalBranchResult(hits=()),
        clock=_clock(),
    )

    assert execution.outcome.status is RetrievalBranchStatus.PARTIAL
    assert execution.outcome.match_count == 0
    assert execution.outcome.health is RetrievalBranchHealth.DEGRADED


def test_invalid_shapes_and_negative_clock_fail_closed() -> None:
    malformed = execute_retrieval_branch(
        branch=RetrievalBranch.VECTOR,
        worker=lambda: "not-a-hit-sequence",
        clock=_clock(started=10.0, completed=9.0),
    )

    assert malformed.outcome.status is RetrievalBranchStatus.INVALID_OUTPUT
    assert malformed.outcome.duration_ms == 0


def test_outcome_contract_is_strict_immutable_and_deterministic() -> None:
    outcome = RetrievalBranchOutcome(
        branch=RetrievalBranch.KEYWORD,
        status=RetrievalBranchStatus.NO_MATCH,
        health=RetrievalBranchHealth.HEALTHY,
        duration_ms=4,
        match_count=0,
    )

    assert outcome.policy_version == RETRIEVAL_OUTCOME_POLICY_VERSION
    assert RetrievalBranchOutcome.model_validate_json(
        outcome.model_dump_json()
    ) == outcome
    assert "secret" not in json.dumps(outcome.model_dump(mode="json"))
    with pytest.raises(ValidationError):
        RetrievalBranchOutcome.model_validate(
            {**outcome.model_dump(mode="python"), "unknown": True}
        )
    with pytest.raises(ValidationError, match="health"):
        RetrievalBranchOutcome(
            branch=RetrievalBranch.KEYWORD,
            status=RetrievalBranchStatus.NO_MATCH,
            health=RetrievalBranchHealth.FAILED,
            duration_ms=4,
            match_count=0,
            safe_failure_code="RETRIEVAL_BRANCH_UNAVAILABLE",
        )
