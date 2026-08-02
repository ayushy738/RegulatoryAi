from __future__ import annotations

import asyncio
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal, Protocol, TypeVar

from pydantic import BaseModel, ConfigDict, Field, model_validator

from backend.ask.decision import (
    CapabilityName,
    Intent,
    QuestionPlan,
    SelectedDecisionPlan,
)
from backend.rag.models import (
    RetrievalBranch,
    RetrievalBranchHealth,
    RetrievalBranchOutcome,
    RetrievalBranchStatus,
    RetrievalHit,
)
from backend.rag.outcomes import BRANCH_SOURCE_TYPES, RetrievalBranchExecution

SELECTIVE_RETRIEVAL_SCHEMA_VERSION = "1"
SELECTIVE_RETRIEVAL_POLICY_VERSION = "ask-ai-selective-retrieval-v1"
T = TypeVar("T")

CAPABILITY_RETRIEVAL_BRANCHES: Mapping[
    CapabilityName,
    tuple[RetrievalBranch, ...],
] = {
    CapabilityName.INTERNAL_DOCUMENT_SEARCH: (
        RetrievalBranch.VECTOR,
        RetrievalBranch.KEYWORD,
    ),
    CapabilityName.DOCUMENT_METADATA: (RetrievalBranch.FAMILY_VERSION,),
    CapabilityName.KNOWLEDGE_GRAPH: (RetrievalBranch.GRAPH,),
    CapabilityName.VERSION_LINEAGE: (RetrievalBranch.FAMILY_VERSION,),
}


class RetrievalBranchSelection(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1"] = SELECTIVE_RETRIEVAL_SCHEMA_VERSION
    policy_version: str = Field(
        default=SELECTIVE_RETRIEVAL_POLICY_VERSION,
        min_length=1,
    )
    branch: RetrievalBranch
    selected: bool
    capabilities: tuple[CapabilityName, ...] = ()
    question_ids: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_selection(self) -> RetrievalBranchSelection:
        if self.selected != bool(self.capabilities):
            raise ValueError("Selected branches require capability ownership")
        if self.selected != bool(self.question_ids):
            raise ValueError("Selected branches require question identity")
        if len(set(self.capabilities)) != len(self.capabilities):
            raise ValueError("Branch capabilities must be unique")
        if len(set(self.question_ids)) != len(self.question_ids):
            raise ValueError("Branch question IDs must be unique")
        return self


class SelectiveRetrievalConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    max_concurrency: int = Field(default=3, ge=1, le=len(RetrievalBranch))


@dataclass(frozen=True, slots=True)
class SelectiveRetrievalResult:
    selections: tuple[RetrievalBranchSelection, ...]
    executions: tuple[RetrievalBranchExecution, ...]
    hits: tuple[RetrievalHit, ...]

    def __post_init__(self) -> None:
        branches = tuple(RetrievalBranch)
        if tuple(item.branch for item in self.selections) != branches:
            raise ValueError("Retrieval selections must retain stable branch order")
        if tuple(item.outcome.branch for item in self.executions) != branches:
            raise ValueError("Retrieval executions must retain stable branch order")
        expected_hits = tuple(
            hit for execution in self.executions for hit in execution.hits
        )
        if self.hits != expected_hits:
            raise ValueError("Retrieval hits must retain stable branch aggregation")

    @property
    def outcomes(self) -> tuple[RetrievalBranchOutcome, ...]:
        return tuple(execution.outcome for execution in self.executions)


class SelectiveRetrievalProvider(Protocol):
    def branch_search(
        self,
        branch: RetrievalBranch,
        query: str,
        *,
        limit: int,
        event_id: int | None = None,
    ) -> RetrievalBranchExecution: ...


def select_retrieval_branches(
    plan: SelectedDecisionPlan,
) -> tuple[RetrievalBranchSelection, ...]:
    capabilities_by_branch: dict[RetrievalBranch, list[CapabilityName]] = {
        branch: [] for branch in RetrievalBranch
    }
    questions_by_branch: dict[RetrievalBranch, list[str]] = {
        branch: [] for branch in RetrievalBranch
    }

    for question_plan in plan.question_plans:
        selected_capabilities = {
            capability.capability for capability in question_plan.capabilities
        }
        for capability in CapabilityName:
            if capability not in selected_capabilities:
                continue
            for branch in CAPABILITY_RETRIEVAL_BRANCHES.get(capability, ()):
                _append_unique(capabilities_by_branch[branch], capability)
                _append_unique(questions_by_branch[branch], question_plan.question_id)
        if _summary_branch_selected(question_plan, selected_capabilities):
            _append_unique(
                capabilities_by_branch[RetrievalBranch.SUMMARY],
                CapabilityName.INTERNAL_DOCUMENT_SEARCH,
            )
            _append_unique(
                questions_by_branch[RetrievalBranch.SUMMARY],
                question_plan.question_id,
            )

    return tuple(
        RetrievalBranchSelection(
            branch=branch,
            selected=bool(capabilities_by_branch[branch]),
            capabilities=tuple(capabilities_by_branch[branch]),
            question_ids=tuple(questions_by_branch[branch]),
        )
        for branch in RetrievalBranch
    )


async def execute_selective_retrieval(
    plan: SelectedDecisionPlan,
    *,
    query: str,
    provider: SelectiveRetrievalProvider,
    limit: int,
    event_id: int | None = None,
    config: SelectiveRetrievalConfig | None = None,
) -> SelectiveRetrievalResult:
    normalized_query = query.strip()
    if not normalized_query:
        raise ValueError("Selective retrieval requires a nonblank query")
    if limit < 1:
        raise ValueError("Selective retrieval limit must be positive")

    selections = select_retrieval_branches(plan)
    selected = tuple(item for item in selections if item.selected)
    concurrency = asyncio.Semaphore(
        (config or SelectiveRetrievalConfig()).max_concurrency
    )
    selected_executions = await asyncio.gather(
        *(
            _execute_selected_branch(
                selection.branch,
                query=normalized_query,
                provider=provider,
                limit=limit,
                event_id=event_id,
                concurrency=concurrency,
            )
            for selection in selected
        )
    )
    executions_by_branch = {
        execution.outcome.branch: execution for execution in selected_executions
    }
    executions = tuple(
        executions_by_branch.get(branch, _skipped_execution(branch))
        for branch in RetrievalBranch
    )
    return SelectiveRetrievalResult(
        selections=selections,
        executions=executions,
        hits=tuple(hit for execution in executions for hit in execution.hits),
    )


def _summary_branch_selected(
    question_plan: QuestionPlan,
    selected_capabilities: set[CapabilityName],
) -> bool:
    return (
        question_plan.intent is Intent.SUMMARIZATION
        and CapabilityName.INTERNAL_DOCUMENT_SEARCH in selected_capabilities
    )


async def _execute_selected_branch(
    branch: RetrievalBranch,
    *,
    query: str,
    provider: SelectiveRetrievalProvider,
    limit: int,
    event_id: int | None,
    concurrency: asyncio.Semaphore,
) -> RetrievalBranchExecution:
    async with concurrency:
        try:
            execution = await asyncio.to_thread(
                provider.branch_search,
                branch,
                query,
                limit=limit,
                event_id=event_id,
            )
        except Exception:
            return _failed_execution(
                branch,
                RetrievalBranchStatus.UNAVAILABLE,
                "RETRIEVAL_BRANCH_UNAVAILABLE",
            )
    if not _valid_execution(branch, execution):
        return _failed_execution(
            branch,
            RetrievalBranchStatus.INVALID_OUTPUT,
            "RETRIEVAL_BRANCH_INVALID_OUTPUT",
        )
    return execution


def _valid_execution(branch: RetrievalBranch, value: object) -> bool:
    if not isinstance(value, RetrievalBranchExecution):
        return False
    if value.outcome.branch is not branch:
        return False
    if value.outcome.status is RetrievalBranchStatus.SKIPPED:
        return False
    if value.outcome.match_count != len(value.hits):
        return False
    allowed_sources = BRANCH_SOURCE_TYPES[branch]
    return all(
        isinstance(hit, RetrievalHit) and hit.source in allowed_sources
        for hit in value.hits
    )


def _skipped_execution(branch: RetrievalBranch) -> RetrievalBranchExecution:
    return RetrievalBranchExecution(
        outcome=RetrievalBranchOutcome(
            branch=branch,
            status=RetrievalBranchStatus.SKIPPED,
            health=RetrievalBranchHealth.NOT_RUN,
            duration_ms=0,
            match_count=0,
        ),
        hits=(),
    )


def _failed_execution(
    branch: RetrievalBranch,
    status: RetrievalBranchStatus,
    safe_failure_code: str,
) -> RetrievalBranchExecution:
    return RetrievalBranchExecution(
        outcome=RetrievalBranchOutcome(
            branch=branch,
            status=status,
            health=RetrievalBranchHealth.FAILED,
            duration_ms=0,
            match_count=0,
            safe_failure_code=safe_failure_code,
        ),
        hits=(),
    )


def _append_unique(values: list[T], value: T) -> None:
    if value not in values:
        values.append(value)
