from __future__ import annotations

import hashlib
import math
import re
from datetime import date
from enum import StrEnum
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from backend.ask.decision import Intent, SelectedDecisionPlan
from backend.rag.models import (
    RetrievalBranch,
    RetrievalBranchHealth,
    RetrievalBranchOutcome,
    RetrievalBranchStatus,
    RetrievalHit,
    RetrievalSource,
)
from backend.rag.selective import (
    SelectiveRetrievalResult,
    select_retrieval_branches,
)

RETRIEVAL_QUALITY_SCHEMA_VERSION = "1"
RETRIEVAL_QUALITY_POLICY_VERSION = "ask-ai-retrieval-quality-v1"


class RetrievalMatchReason(StrEnum):
    VECTOR_SIMILARITY = "vector_similarity"
    KEYWORD_MATCH = "keyword_match"
    GRAPH_FACT = "graph_fact"
    FAMILY_VERSION = "family_version"
    SUMMARY_MATCH = "summary_match"


class EvidenceExclusionReason(StrEnum):
    BELOW_THRESHOLD = "below_threshold"
    INVALID_SCORE = "invalid_score"
    INVALID_EVIDENCE = "invalid_evidence"


class RelevanceThreshold(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    branch: RetrievalBranch
    minimum_score: float = Field(ge=0, le=1)
    intent: Intent | None = None

    @model_validator(mode="after")
    def reject_non_atomic_intent(self) -> Self:
        if self.intent is Intent.MULTI_PART_QUESTION:
            raise ValueError("Relevance thresholds require atomic intents")
        if not math.isfinite(self.minimum_score):
            raise ValueError("Relevance thresholds must be finite")
        return self


class RetrievalRelevancePolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1"] = RETRIEVAL_QUALITY_SCHEMA_VERSION
    policy_version: str = Field(
        default=RETRIEVAL_QUALITY_POLICY_VERSION,
        min_length=1,
    )
    thresholds: tuple[RelevanceThreshold, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_complete_policy(self) -> Self:
        keys = tuple((item.branch, item.intent) for item in self.thresholds)
        if len(set(keys)) != len(keys):
            raise ValueError("Relevance threshold keys must be unique")
        defaults = {
            item.branch for item in self.thresholds if item.intent is None
        }
        if defaults != set(RetrievalBranch):
            raise ValueError("Relevance policy requires every branch default")
        return self

    def minimum_for(self, branch: RetrievalBranch, intent: Intent) -> float:
        return next(
            (
                item.minimum_score
                for item in self.thresholds
                if item.branch is branch and item.intent is intent
            ),
            next(
                item.minimum_score
                for item in self.thresholds
                if item.branch is branch and item.intent is None
            ),
        )


class EvidenceScoreSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    vector: float = Field(default=0, ge=0, le=1)
    keyword: float = Field(default=0, ge=0, le=1)
    graph: float = Field(default=0, ge=0, le=1)
    admitted_relevance: float = Field(ge=0, le=1)


class CanonicalEvidenceUnit(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1"] = RETRIEVAL_QUALITY_SCHEMA_VERSION
    policy_version: str = Field(min_length=1)
    evidence_unit_id: str = Field(pattern=r"^evidence_[0-9a-f]{32}$")
    document_id: int = Field(ge=1)
    version_id: int | None = None
    family_id: int | None = None
    chunk_id: int | None = None
    title: str = Field(min_length=1)
    source_url: str = Field(min_length=1)
    issuer: str | None = None
    issue_date: date | None = None
    text: str = Field(min_length=1)
    retrieval_sources: tuple[RetrievalSource, ...] = Field(min_length=1)
    match_reasons: tuple[RetrievalMatchReason, ...] = Field(min_length=1)
    question_ids: tuple[str, ...] = Field(min_length=1)
    scores: EvidenceScoreSnapshot

    @model_validator(mode="after")
    def validate_unit(self) -> Self:
        for values, message in (
            (self.retrieval_sources, "Evidence retrieval sources must be unique"),
            (self.match_reasons, "Evidence match reasons must be unique"),
            (self.question_ids, "Evidence question IDs must be unique"),
        ):
            if len(set(values)) != len(values):
                raise ValueError(message)
        return self


class EvidenceExclusion(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    branch: RetrievalBranch
    document_id: int | None = Field(default=None, ge=1)
    chunk_id: int | None = None
    reason: EvidenceExclusionReason
    observed_score: float | None = Field(default=None, ge=0, le=1)
    minimum_score: float = Field(ge=0, le=1)


class EvidenceAdmissionResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1"] = RETRIEVAL_QUALITY_SCHEMA_VERSION
    policy_version: str = Field(min_length=1)
    evidence_units: tuple[CanonicalEvidenceUnit, ...]
    exclusions: tuple[EvidenceExclusion, ...]
    branch_outcomes: tuple[RetrievalBranchOutcome, ...]

    @model_validator(mode="after")
    def validate_branch_order(self) -> Self:
        if tuple(item.branch for item in self.branch_outcomes) != tuple(
            RetrievalBranch
        ):
            raise ValueError("Quality outcomes must retain stable branch order")
        ids = tuple(item.evidence_unit_id for item in self.evidence_units)
        if len(set(ids)) != len(ids):
            raise ValueError("Canonical evidence unit IDs must be unique")
        return self


def admit_retrieval_evidence(
    plan: SelectedDecisionPlan,
    retrieval: SelectiveRetrievalResult,
    *,
    policy: RetrievalRelevancePolicy,
) -> EvidenceAdmissionResult:
    if retrieval.selections != select_retrieval_branches(plan):
        raise ValueError("Retrieval selections do not match the approved plan")

    question_intents = {
        question.question_id: question.intent
        for question in plan.question_plans
    }
    builders: dict[str, _EvidenceBuilder] = {}
    exclusions: list[EvidenceExclusion] = []
    quality_outcomes: list[RetrievalBranchOutcome] = []

    for selection, execution in zip(
        retrieval.selections,
        retrieval.executions,
        strict=True,
    ):
        admitted_count = 0
        invalid_count = 0
        for hit_index, hit in enumerate(execution.hits):
            score = _primary_score(selection.branch, hit)
            thresholds = tuple(
                policy.minimum_for(selection.branch, question_intents[question_id])
                for question_id in selection.question_ids
            )
            minimum = min(thresholds)
            if not math.isfinite(score) or score < 0 or score > 1:
                invalid_count += 1
                exclusions.append(
                    EvidenceExclusion(
                        branch=selection.branch,
                        document_id=(
                            hit.document_id if hit.document_id >= 1 else None
                        ),
                        chunk_id=hit.chunk_id,
                        reason=EvidenceExclusionReason.INVALID_SCORE,
                        minimum_score=minimum,
                    )
                )
                continue
            if not _valid_evidence_hit(hit):
                invalid_count += 1
                exclusions.append(
                    EvidenceExclusion(
                        branch=selection.branch,
                        document_id=(
                            hit.document_id if hit.document_id >= 1 else None
                        ),
                        chunk_id=hit.chunk_id,
                        reason=EvidenceExclusionReason.INVALID_EVIDENCE,
                        minimum_score=minimum,
                    )
                )
                continue
            eligible_questions = tuple(
                question_id
                for question_id, threshold in zip(
                    selection.question_ids,
                    thresholds,
                    strict=True,
                )
                if score >= threshold
            )
            if not eligible_questions:
                exclusions.append(
                    EvidenceExclusion(
                        branch=selection.branch,
                        document_id=hit.document_id,
                        chunk_id=hit.chunk_id,
                        reason=EvidenceExclusionReason.BELOW_THRESHOLD,
                        observed_score=score,
                        minimum_score=minimum,
                    )
                )
                continue
            admitted_count += 1
            key = _canonical_key(hit, hit_index=hit_index)
            builder = builders.get(key)
            if builder is None:
                builders[key] = _EvidenceBuilder.from_hit(
                    key,
                    hit,
                    selection.branch,
                    eligible_questions,
                )
            else:
                builder.merge(hit, selection.branch, eligible_questions)
        quality_outcomes.append(
            _quality_outcome(
                execution.outcome,
                admitted_count=admitted_count,
                invalid_count=invalid_count,
            )
        )

    return EvidenceAdmissionResult(
        policy_version=policy.policy_version,
        evidence_units=tuple(
            builder.build(policy.policy_version)
            for builder in builders.values()
        ),
        exclusions=tuple(exclusions),
        branch_outcomes=tuple(quality_outcomes),
    )


class _EvidenceBuilder:
    def __init__(
        self,
        *,
        key: str,
        hit: RetrievalHit,
        branch: RetrievalBranch,
        question_ids: tuple[str, ...],
    ) -> None:
        self.key = key
        self.document_id = hit.document_id
        self.version_id = hit.version_id
        self.family_id = hit.family_id
        self.chunk_id = hit.chunk_id
        self.title = hit.title
        self.source_url = hit.source_url
        self.issuer = hit.issuer
        self.issue_date = hit.issue_date
        self.text = hit.text
        self.sources: list[RetrievalSource] = [hit.source]
        self.reasons = [_match_reason(branch)]
        self.question_ids = list(question_ids)
        self.vector_score = hit.vector_score
        self.keyword_score = hit.keyword_score
        self.graph_score = hit.graph_score
        self.admitted_relevance = _primary_score(branch, hit)

    @classmethod
    def from_hit(
        cls,
        key: str,
        hit: RetrievalHit,
        branch: RetrievalBranch,
        question_ids: tuple[str, ...],
    ) -> _EvidenceBuilder:
        return cls(
            key=key,
            hit=hit,
            branch=branch,
            question_ids=question_ids,
        )

    def merge(
        self,
        hit: RetrievalHit,
        branch: RetrievalBranch,
        question_ids: tuple[str, ...],
    ) -> None:
        if hit.source not in self.sources:
            self.sources.append(hit.source)
        reason = _match_reason(branch)
        if reason not in self.reasons:
            self.reasons.append(reason)
        for question_id in question_ids:
            if question_id not in self.question_ids:
                self.question_ids.append(question_id)
        self.vector_score = max(self.vector_score, hit.vector_score)
        self.keyword_score = max(self.keyword_score, hit.keyword_score)
        self.graph_score = max(self.graph_score, hit.graph_score)
        self.admitted_relevance = max(
            self.admitted_relevance,
            _primary_score(branch, hit),
        )
        if len(hit.text) > len(self.text):
            self.text = hit.text

    def build(self, policy_version: str) -> CanonicalEvidenceUnit:
        digest = hashlib.sha256(self.key.encode("utf-8")).hexdigest()[:32]
        return CanonicalEvidenceUnit(
            policy_version=policy_version,
            evidence_unit_id=f"evidence_{digest}",
            document_id=self.document_id,
            version_id=self.version_id,
            family_id=self.family_id,
            chunk_id=self.chunk_id,
            title=self.title,
            source_url=self.source_url,
            issuer=self.issuer,
            issue_date=self.issue_date,
            text=self.text,
            retrieval_sources=tuple(self.sources),
            match_reasons=tuple(self.reasons),
            question_ids=tuple(self.question_ids),
            scores=EvidenceScoreSnapshot(
                vector=self.vector_score,
                keyword=self.keyword_score,
                graph=self.graph_score,
                admitted_relevance=self.admitted_relevance,
            ),
        )


def _primary_score(branch: RetrievalBranch, hit: RetrievalHit) -> float:
    if branch is RetrievalBranch.VECTOR:
        return hit.vector_score
    if branch in {RetrievalBranch.KEYWORD, RetrievalBranch.SUMMARY}:
        return hit.keyword_score
    return hit.graph_score


def _valid_evidence_hit(hit: RetrievalHit) -> bool:
    return (
        hit.document_id >= 1
        and bool(hit.title.strip())
        and bool(hit.source_url.strip())
        and bool(hit.text.strip())
        and all(
            math.isfinite(score) and 0 <= score <= 1
            for score in (
                hit.vector_score,
                hit.keyword_score,
                hit.graph_score,
            )
        )
    )


def _match_reason(branch: RetrievalBranch) -> RetrievalMatchReason:
    return {
        RetrievalBranch.VECTOR: RetrievalMatchReason.VECTOR_SIMILARITY,
        RetrievalBranch.KEYWORD: RetrievalMatchReason.KEYWORD_MATCH,
        RetrievalBranch.GRAPH: RetrievalMatchReason.GRAPH_FACT,
        RetrievalBranch.FAMILY_VERSION: RetrievalMatchReason.FAMILY_VERSION,
        RetrievalBranch.SUMMARY: RetrievalMatchReason.SUMMARY_MATCH,
    }[branch]


def _canonical_key(hit: RetrievalHit, *, hit_index: int) -> str:
    version = hit.version_id if hit.version_id is not None else "none"
    if hit.source in {"vector", "keyword"} and hit.chunk_id is not None:
        return f"passage:{hit.document_id}:{version}:{hit.chunk_id}"
    normalized_text = re.sub(r"\s+", " ", hit.text).strip()
    text_digest = hashlib.sha256(normalized_text.encode("utf-8")).hexdigest()
    return (
        f"{hit.source}:{hit.document_id}:{version}:"
        f"{hit.family_id or 'none'}:{hit_index}:{text_digest}"
    )


def _quality_outcome(
    original: RetrievalBranchOutcome,
    *,
    admitted_count: int,
    invalid_count: int,
) -> RetrievalBranchOutcome:
    if original.status not in {
        RetrievalBranchStatus.SATISFIED,
        RetrievalBranchStatus.PARTIAL,
    }:
        return original
    if invalid_count:
        status = (
            RetrievalBranchStatus.PARTIAL
            if admitted_count
            else RetrievalBranchStatus.INVALID_OUTPUT
        )
        return RetrievalBranchOutcome(
            branch=original.branch,
            status=status,
            health=(
                RetrievalBranchHealth.DEGRADED
                if admitted_count
                else RetrievalBranchHealth.FAILED
            ),
            duration_ms=original.duration_ms,
            match_count=admitted_count,
            safe_failure_code=(
                "RETRIEVAL_RELEVANCE_PARTIAL"
                if admitted_count
                else "RETRIEVAL_RELEVANCE_INVALID_SCORE"
            ),
        )
    if original.status is RetrievalBranchStatus.PARTIAL:
        return original.model_copy(update={"match_count": admitted_count})
    return RetrievalBranchOutcome(
        branch=original.branch,
        status=(
            RetrievalBranchStatus.SATISFIED
            if admitted_count
            else RetrievalBranchStatus.NO_MATCH
        ),
        health=RetrievalBranchHealth.HEALTHY,
        duration_ms=original.duration_ms,
        match_count=admitted_count,
    )
