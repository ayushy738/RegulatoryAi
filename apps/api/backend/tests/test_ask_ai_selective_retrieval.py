from __future__ import annotations

import asyncio
import json
import threading
import time
from collections.abc import Mapping
from datetime import date
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from backend.ask.decision import (
    CapabilityName,
    Intent,
    PlanQuestion,
    PlanRequest,
    SelectedDecisionPlan,
    select_decision_plan,
)
from backend.rag import retrieval as retrieval_module
from backend.rag.models import (
    RetrievalBranch,
    RetrievalBranchHealth,
    RetrievalBranchOutcome,
    RetrievalBranchStatus,
    RetrievalHit,
)
from backend.rag.outcomes import RetrievalBranchExecution
from backend.rag.retrieval import SupabaseHybridRetrieval
from backend.rag.selective import (
    SelectiveRetrievalConfig,
    execute_selective_retrieval,
    select_retrieval_branches,
)

MATRIX_PATH = Path(__file__).parent / "fixtures" / "ask_decision_plan_matrix.json"
BRANCH_SOURCE = {
    RetrievalBranch.VECTOR: "vector",
    RetrievalBranch.KEYWORD: "keyword",
    RetrievalBranch.GRAPH: "graph",
    RetrievalBranch.FAMILY_VERSION: "family",
    RetrievalBranch.SUMMARY: "summary",
}


def _plan(*questions: PlanQuestion) -> SelectedDecisionPlan:
    return select_decision_plan(PlanRequest(questions=questions))


def _hit(branch: RetrievalBranch, index: int = 1) -> RetrievalHit:
    return RetrievalHit(
        source=BRANCH_SOURCE[branch],  # type: ignore[arg-type]
        document_id=index,
        title=f"{branch.value}-{index}",
        source_url=f"https://example.test/{branch.value}/{index}",
        issuer="CERC",
        issue_date=date(2026, 7, 27),
        text=f"{branch.value} evidence",
    )


def _execution(
    branch: RetrievalBranch,
    *,
    hits: tuple[RetrievalHit, ...] | None = None,
    status: RetrievalBranchStatus = RetrievalBranchStatus.SATISFIED,
) -> RetrievalBranchExecution:
    actual_hits = hits if hits is not None else (_hit(branch),)
    health = (
        RetrievalBranchHealth.HEALTHY
        if status
        in {
            RetrievalBranchStatus.SATISFIED,
            RetrievalBranchStatus.NO_MATCH,
        }
        else RetrievalBranchHealth.FAILED
    )
    return RetrievalBranchExecution(
        outcome=RetrievalBranchOutcome(
            branch=branch,
            status=status,
            health=health,
            duration_ms=5,
            match_count=len(actual_hits),
            safe_failure_code=(
                None
                if health is RetrievalBranchHealth.HEALTHY
                else "RETRIEVAL_BRANCH_UNAVAILABLE"
            ),
        ),
        hits=actual_hits,
    )


class _RecordingProvider:
    def __init__(
        self,
        executions: Mapping[RetrievalBranch, RetrievalBranchExecution] | None = None,
        *,
        failures: frozenset[RetrievalBranch] = frozenset(),
        malformed: frozenset[RetrievalBranch] = frozenset(),
        delays: Mapping[RetrievalBranch, float] | None = None,
    ) -> None:
        self.executions = executions or {}
        self.failures = failures
        self.malformed = malformed
        self.delays = delays or {}
        self.calls: list[tuple[RetrievalBranch, str, int, int | None]] = []
        self.active = 0
        self.max_active = 0
        self._lock = threading.Lock()

    def branch_search(
        self,
        branch: RetrievalBranch,
        query: str,
        *,
        limit: int,
        event_id: int | None = None,
    ) -> RetrievalBranchExecution:
        with self._lock:
            self.calls.append((branch, query, limit, event_id))
            self.active += 1
            self.max_active = max(self.max_active, self.active)
        try:
            time.sleep(self.delays.get(branch, 0))
            if branch in self.failures:
                raise RuntimeError("private provider failure")
            if branch in self.malformed:
                return object()  # type: ignore[return-value]
            return self.executions.get(branch, _execution(branch))
        finally:
            with self._lock:
                self.active -= 1


def test_frozen_decision_matrix_routes_exact_retrieval_branch_ownership() -> None:
    matrix: dict[str, Any] = json.loads(MATRIX_PATH.read_text(encoding="utf-8"))

    for case in matrix["cases"]:
        plan = _plan(
            *(
                PlanQuestion.model_validate(question)
                for question in case["questions"]
            )
        )
        selections = select_retrieval_branches(plan)
        selected_capabilities = set(case["expected"]["selected"])
        expected = set()
        if CapabilityName.INTERNAL_DOCUMENT_SEARCH.value in selected_capabilities:
            expected.update({RetrievalBranch.VECTOR, RetrievalBranch.KEYWORD})
        if CapabilityName.KNOWLEDGE_GRAPH.value in selected_capabilities:
            expected.add(RetrievalBranch.GRAPH)
        if selected_capabilities & {
            CapabilityName.DOCUMENT_METADATA.value,
            CapabilityName.VERSION_LINEAGE.value,
        }:
            expected.add(RetrievalBranch.FAMILY_VERSION)
        if any(
            question["intent"] == Intent.SUMMARIZATION.value
            for question in case["questions"]
        ) and CapabilityName.INTERNAL_DOCUMENT_SEARCH.value in selected_capabilities:
            expected.add(RetrievalBranch.SUMMARY)

        assert {
            selection.branch for selection in selections if selection.selected
        } == expected, case["query"]
        assert tuple(selection.branch for selection in selections) == tuple(
            RetrievalBranch
        )


def test_multi_question_selection_deduplicates_branches_and_question_ids() -> None:
    plan = _plan(
        PlanQuestion(
            question_id="q1",
            intent=Intent.COMPARISON,
            has_resolved_entity=True,
            version_change=True,
        ),
        PlanQuestion(
            question_id="q2",
            intent=Intent.CONSULTATION,
            has_resolved_entity=True,
            has_document_target=True,
            live_eligible=True,
        ),
    )

    selections = {
        selection.branch: selection for selection in select_retrieval_branches(plan)
    }

    assert selections[RetrievalBranch.VECTOR].question_ids == ("q1", "q2")
    assert selections[RetrievalBranch.KEYWORD].question_ids == ("q1", "q2")
    assert selections[RetrievalBranch.GRAPH].question_ids == ("q1", "q2")
    assert selections[RetrievalBranch.FAMILY_VERSION].question_ids == ("q1", "q2")
    assert selections[RetrievalBranch.SUMMARY].selected is False


def test_general_ai_only_plan_skips_every_official_retrieval_branch() -> None:
    provider = _RecordingProvider()
    plan = _plan(
        PlanQuestion(question_id="q1", intent=Intent.GENERAL_QUESTION)
    )

    result = asyncio.run(
        execute_selective_retrieval(
            plan,
            query="Write a poem about electricity",
            provider=provider,
            limit=5,
        )
    )

    assert provider.calls == []
    assert result.hits == ()
    assert all(
        outcome.status is RetrievalBranchStatus.SKIPPED
        and outcome.health is RetrievalBranchHealth.NOT_RUN
        and outcome.duration_ms == 0
        and outcome.safe_failure_code is None
        for outcome in result.outcomes
    )


def test_only_selected_branches_execute_once_with_stable_aggregation() -> None:
    plan = _plan(
        PlanQuestion(
            question_id="q1",
            intent=Intent.AMENDMENT,
            has_resolved_entity=True,
            has_document_target=True,
            version_change=True,
        )
    )
    delays = {
        RetrievalBranch.VECTOR: 0.04,
        RetrievalBranch.KEYWORD: 0.03,
        RetrievalBranch.GRAPH: 0.02,
        RetrievalBranch.FAMILY_VERSION: 0.01,
    }
    provider = _RecordingProvider(delays=delays)

    result = asyncio.run(
        execute_selective_retrieval(
            plan,
            query="What changed in the DSM amendment?",
            provider=provider,
            limit=7,
            event_id=13,
            config=SelectiveRetrievalConfig(max_concurrency=4),
        )
    )

    assert {call[0] for call in provider.calls} == {
        RetrievalBranch.VECTOR,
        RetrievalBranch.KEYWORD,
        RetrievalBranch.GRAPH,
        RetrievalBranch.FAMILY_VERSION,
    }
    assert len(provider.calls) == 4
    assert all(call[1:] == ("What changed in the DSM amendment?", 7, 13) for call in provider.calls)
    assert [hit.source for hit in result.hits] == [
        "vector",
        "keyword",
        "graph",
        "family",
    ]
    assert result.outcomes[-1].status is RetrievalBranchStatus.SKIPPED


def test_selected_failure_and_no_match_do_not_activate_skipped_work() -> None:
    plan = _plan(
        PlanQuestion(
            question_id="q1",
            intent=Intent.DEFINITION,
            has_resolved_entity=True,
            has_term_like_entity=True,
        )
    )
    provider = _RecordingProvider(
        executions={
            RetrievalBranch.KEYWORD: _execution(
                RetrievalBranch.KEYWORD,
                hits=(),
                status=RetrievalBranchStatus.NO_MATCH,
            )
        },
        failures=frozenset({RetrievalBranch.VECTOR}),
    )

    result = asyncio.run(
        execute_selective_retrieval(
            plan,
            query="What is DSM?",
            provider=provider,
            limit=5,
        )
    )

    assert {call[0] for call in provider.calls} == {
        RetrievalBranch.VECTOR,
        RetrievalBranch.KEYWORD,
    }
    assert [outcome.status for outcome in result.outcomes] == [
        RetrievalBranchStatus.UNAVAILABLE,
        RetrievalBranchStatus.NO_MATCH,
        RetrievalBranchStatus.SKIPPED,
        RetrievalBranchStatus.SKIPPED,
        RetrievalBranchStatus.SKIPPED,
    ]


def test_malformed_selected_result_is_isolated_and_safe() -> None:
    plan = _plan(
        PlanQuestion(
            question_id="q1",
            intent=Intent.STAKEHOLDER,
            has_resolved_entity=True,
        )
    )
    provider = _RecordingProvider(
        malformed=frozenset({RetrievalBranch.GRAPH})
    )

    result = asyncio.run(
        execute_selective_retrieval(
            plan,
            query="Who regulates DSM?",
            provider=provider,
            limit=5,
        )
    )

    graph = result.outcomes[list(RetrievalBranch).index(RetrievalBranch.GRAPH)]
    assert graph.status is RetrievalBranchStatus.INVALID_OUTPUT
    assert graph.safe_failure_code == "RETRIEVAL_BRANCH_INVALID_OUTPUT"
    assert "private provider failure" not in repr(result)


def test_blocking_branch_execution_obeys_bounded_concurrency() -> None:
    plan = _plan(
        PlanQuestion(
            question_id="q1",
            intent=Intent.AMENDMENT,
            has_resolved_entity=True,
            has_document_target=True,
            version_change=True,
        )
    )
    provider = _RecordingProvider(
        delays={branch: 0.02 for branch in RetrievalBranch}
    )

    asyncio.run(
        execute_selective_retrieval(
            plan,
            query="DSM amendment",
            provider=provider,
            limit=5,
            config=SelectiveRetrievalConfig(max_concurrency=2),
        )
    )

    assert provider.max_active == 2


def test_skipped_outcome_contract_rejects_health_duration_and_failure_drift() -> None:
    with pytest.raises(ValidationError):
        RetrievalBranchOutcome(
            branch=RetrievalBranch.GRAPH,
            status=RetrievalBranchStatus.SKIPPED,
            health=RetrievalBranchHealth.HEALTHY,
            duration_ms=0,
            match_count=0,
        )
    with pytest.raises(ValidationError):
        RetrievalBranchOutcome(
            branch=RetrievalBranch.GRAPH,
            status=RetrievalBranchStatus.SKIPPED,
            health=RetrievalBranchHealth.NOT_RUN,
            duration_ms=1,
            match_count=0,
        )
    with pytest.raises(ValidationError):
        RetrievalBranchOutcome(
            branch=RetrievalBranch.GRAPH,
            status=RetrievalBranchStatus.SKIPPED,
            health=RetrievalBranchHealth.NOT_RUN,
            duration_ms=0,
            match_count=0,
            safe_failure_code="RETRIEVAL_BRANCH_SKIPPED",
        )


def test_selective_executor_rejects_invalid_request_boundaries() -> None:
    plan = _plan(
        PlanQuestion(question_id="q1", intent=Intent.GENERAL_QUESTION)
    )
    provider = _RecordingProvider()

    with pytest.raises(ValueError, match="nonblank"):
        asyncio.run(
            execute_selective_retrieval(
                plan,
                query=" ",
                provider=provider,
                limit=5,
            )
        )
    with pytest.raises(ValueError, match="positive"):
        asyncio.run(
            execute_selective_retrieval(
                plan,
                query="question",
                provider=provider,
                limit=0,
            )
        )


def test_legacy_hybrid_path_still_executes_all_five_branches(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = SupabaseHybridRetrieval()
    calls: list[RetrievalBranch] = []

    def branch_search(
        branch: RetrievalBranch,
        query: str,
        *,
        limit: int,
        event_id: int | None = None,
    ) -> RetrievalBranchExecution:
        del query, limit, event_id
        calls.append(branch)
        return _execution(branch)

    monkeypatch.setattr(provider, "branch_search", branch_search)
    monkeypatch.setattr(
        retrieval_module,
        "rank_hits",
        lambda hits, intent, *, limit: list(hits)[:limit],
    )

    result = provider.hybrid_search("legacy query", limit=10)

    assert set(calls) == set(RetrievalBranch)
    assert len(calls) == len(RetrievalBranch)
    assert {outcome.branch for outcome in result.branch_outcomes} == set(
        RetrievalBranch
    )
