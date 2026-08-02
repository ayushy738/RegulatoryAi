from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass

from backend.rag.models import (
    RetrievalBranch,
    RetrievalBranchHealth,
    RetrievalBranchOutcome,
    RetrievalBranchStatus,
    RetrievalHit,
)

BRANCH_SOURCE_TYPES = {
    RetrievalBranch.VECTOR: frozenset({"vector"}),
    RetrievalBranch.KEYWORD: frozenset({"keyword"}),
    RetrievalBranch.GRAPH: frozenset({"graph"}),
    RetrievalBranch.FAMILY_VERSION: frozenset({"family", "version"}),
    RetrievalBranch.SUMMARY: frozenset({"summary"}),
}


@dataclass(frozen=True, slots=True)
class RetrievalBranchExecution:
    outcome: RetrievalBranchOutcome
    hits: tuple[RetrievalHit, ...]


@dataclass(frozen=True, slots=True)
class PartialRetrievalBranchResult:
    hits: tuple[RetrievalHit, ...]


class RetrievalBranchPreflightFailure(RuntimeError):
    def __init__(
        self,
        *,
        status: RetrievalBranchStatus,
        health: RetrievalBranchHealth,
        safe_failure_code: str,
    ) -> None:
        super().__init__(safe_failure_code)
        self.status = status
        self.health = health
        self.safe_failure_code = safe_failure_code


def execute_retrieval_branch(
    *,
    branch: RetrievalBranch,
    worker: Callable[[], object],
    clock: Callable[[], float],
) -> RetrievalBranchExecution:
    started = clock()
    try:
        raw_hits = worker()
    except RetrievalBranchPreflightFailure as exc:
        return RetrievalBranchExecution(
            outcome=RetrievalBranchOutcome(
                branch=branch,
                status=exc.status,
                health=exc.health,
                duration_ms=_elapsed_ms(started, clock()),
                match_count=0,
                safe_failure_code=exc.safe_failure_code,
            ),
            hits=(),
        )
    except TimeoutError:
        return _failed_execution(
            branch,
            status=RetrievalBranchStatus.TIMED_OUT,
            safe_failure_code="RETRIEVAL_BRANCH_TIMED_OUT",
            duration_ms=_elapsed_ms(started, clock()),
        )
    except (KeyError, TypeError, ValueError):
        return _failed_execution(
            branch,
            status=RetrievalBranchStatus.INVALID_OUTPUT,
            safe_failure_code="RETRIEVAL_BRANCH_INVALID_OUTPUT",
            duration_ms=_elapsed_ms(started, clock()),
        )
    except Exception:
        return _failed_execution(
            branch,
            status=RetrievalBranchStatus.UNAVAILABLE,
            safe_failure_code="RETRIEVAL_BRANCH_UNAVAILABLE",
            duration_ms=_elapsed_ms(started, clock()),
        )
    duration_ms = _elapsed_ms(started, clock())
    partial = isinstance(raw_hits, PartialRetrievalBranchResult)
    candidate_hits = raw_hits.hits if partial else raw_hits
    if not _valid_hits(branch, candidate_hits):
        return _failed_execution(
            branch,
            status=RetrievalBranchStatus.INVALID_OUTPUT,
            safe_failure_code="RETRIEVAL_BRANCH_INVALID_OUTPUT",
            duration_ms=duration_ms,
        )
    hits = tuple(candidate_hits)
    if partial:
        return RetrievalBranchExecution(
            outcome=RetrievalBranchOutcome(
                branch=branch,
                status=RetrievalBranchStatus.PARTIAL,
                health=RetrievalBranchHealth.DEGRADED,
                duration_ms=duration_ms,
                match_count=len(hits),
                safe_failure_code="RETRIEVAL_BRANCH_PARTIAL",
            ),
            hits=hits,
        )
    status = (
        RetrievalBranchStatus.SATISFIED
        if hits
        else RetrievalBranchStatus.NO_MATCH
    )
    return RetrievalBranchExecution(
        outcome=RetrievalBranchOutcome(
            branch=branch,
            status=status,
            health=RetrievalBranchHealth.HEALTHY,
            duration_ms=duration_ms,
            match_count=len(hits),
        ),
        hits=hits,
    )


def _valid_hits(branch: RetrievalBranch, value: object) -> bool:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return False
    allowed_sources = BRANCH_SOURCE_TYPES[branch]
    return all(
        isinstance(hit, RetrievalHit) and hit.source in allowed_sources
        for hit in value
    )


def _failed_execution(
    branch: RetrievalBranch,
    *,
    status: RetrievalBranchStatus,
    safe_failure_code: str,
    duration_ms: int,
) -> RetrievalBranchExecution:
    return RetrievalBranchExecution(
        outcome=RetrievalBranchOutcome(
            branch=branch,
            status=status,
            health=RetrievalBranchHealth.FAILED,
            duration_ms=duration_ms,
            match_count=0,
            safe_failure_code=safe_failure_code,
        ),
        hits=(),
    )


def _elapsed_ms(started: float, completed: float) -> int:
    return max(0, int((completed - started) * 1000))
