from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

IntentName = Literal[
    "deadline",
    "stakeholder",
    "obligation",
    "consultation",
    "tender",
    "regulation_lookup",
    "amendment",
    "comparison",
    "summary",
    "semantic_search",
    "general",
]

RetrievalSource = Literal["vector", "keyword", "graph", "family", "version", "summary"]

RETRIEVAL_OUTCOME_SCHEMA_VERSION = "1"
RETRIEVAL_OUTCOME_POLICY_VERSION = "ask-ai-retrieval-outcome-v1"


class RetrievalBranch(StrEnum):
    VECTOR = "vector"
    KEYWORD = "keyword"
    GRAPH = "graph"
    FAMILY_VERSION = "family_version"
    SUMMARY = "summary"


class RetrievalBranchStatus(StrEnum):
    SATISFIED = "satisfied"
    PARTIAL = "partial"
    NO_MATCH = "no_match"
    SKIPPED = "skipped"
    TIMED_OUT = "timed_out"
    UNAVAILABLE = "unavailable"
    INVALID_OUTPUT = "invalid_output"


class RetrievalBranchHealth(StrEnum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    FAILED = "failed"
    NOT_RUN = "not_run"


class RetrievalBranchOutcome(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    schema_version: Literal["1"] = RETRIEVAL_OUTCOME_SCHEMA_VERSION
    policy_version: str = Field(
        default=RETRIEVAL_OUTCOME_POLICY_VERSION,
        min_length=1,
    )
    branch: RetrievalBranch
    status: RetrievalBranchStatus
    health: RetrievalBranchHealth
    duration_ms: int = Field(ge=0)
    match_count: int = Field(ge=0)
    safe_failure_code: str | None = Field(
        default=None,
        pattern=r"^[A-Z][A-Z0-9_]{0,99}$",
    )

    @model_validator(mode="after")
    def validate_outcome(self) -> RetrievalBranchOutcome:
        skipped = self.status is RetrievalBranchStatus.SKIPPED
        healthy = self.status in {
            RetrievalBranchStatus.SATISFIED,
            RetrievalBranchStatus.NO_MATCH,
        }
        partial = self.status is RetrievalBranchStatus.PARTIAL
        expected_health = (
            RetrievalBranchHealth.NOT_RUN
            if skipped
            else (
                RetrievalBranchHealth.HEALTHY
                if healthy
                else (
                    RetrievalBranchHealth.DEGRADED
                    if partial
                    else RetrievalBranchHealth.FAILED
                )
            )
        )
        if self.health is not expected_health:
            raise ValueError("Retrieval branch status and health must agree")
        if self.status is RetrievalBranchStatus.SATISFIED:
            if self.match_count == 0:
                raise ValueError("Satisfied retrieval branches require matches")
        elif not partial and self.match_count != 0:
            raise ValueError(
                "Only satisfied or partial retrieval branches may retain matches"
            )
        if skipped:
            if self.duration_ms != 0:
                raise ValueError("Skipped retrieval branches cannot record duration")
            if self.safe_failure_code is not None:
                raise ValueError("Skipped retrieval branches cannot record failures")
        elif healthy != (self.safe_failure_code is None):
            raise ValueError("Only failed or partial branches require a safe code")
        return self


@dataclass(frozen=True)
class DocumentChunk:
    document_id: int
    version_id: int | None
    family_id: int | None
    chunk_index: int
    text: str
    token_count: int
    page_number: int | None = None
    section_title: str | None = None
    content_hash: str | None = None
    id: int | None = None


@dataclass(frozen=True)
class Citation:
    document_id: int
    title: str
    issuer: str | None
    issue_date: date | None
    source_url: str
    chunk_id: int | None = None
    page_number: int | None = None
    section_title: str | None = None
    evidence: str | None = None


@dataclass
class RetrievalHit:
    source: RetrievalSource
    document_id: int
    title: str
    source_url: str
    issuer: str | None = None
    issue_date: date | None = None
    version_id: int | None = None
    family_id: int | None = None
    chunk_id: int | None = None
    chunk_index: int | None = None
    page_number: int | None = None
    section_title: str | None = None
    text: str = ""
    vector_score: float = 0.0
    keyword_score: float = 0.0
    graph_score: float = 0.0
    freshness_score: float = 0.0
    authority_score: float = 0.0
    version_score: float = 0.0
    quality_score: float = 0.0
    final_score: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def citation(self) -> Citation:
        return Citation(
            document_id=self.document_id,
            title=self.title,
            issuer=self.issuer,
            issue_date=self.issue_date,
            source_url=self.source_url,
            chunk_id=self.chunk_id,
            page_number=self.page_number,
            section_title=self.section_title,
            evidence=self.text[:500] if self.text else None,
        )


@dataclass(frozen=True)
class Intent:
    name: IntentName
    query: str
    confidence: float
    dominant_sources: tuple[RetrievalSource, ...]


@dataclass
class HybridRetrievalResult:
    query: str
    intent: Intent
    hits: list[RetrievalHit]
    citations: list[Citation]
    graph_facts: list[RetrievalHit] = field(default_factory=list)
    related_questions: list[str] = field(default_factory=list)
    related_documents: list[Citation] = field(default_factory=list)
    retrieval_latency_ms: int = 0
    branch_outcomes: list[RetrievalBranchOutcome] = field(default_factory=list)


@dataclass(frozen=True)
class BuiltContext:
    prompt_context: str
    citations: list[Citation]
    graph_facts: list[RetrievalHit]
    related_questions: list[str]
    estimated_tokens: int


def citation_to_dict(citation: Citation) -> dict[str, Any]:
    return {
        "document_id": citation.document_id,
        "title": citation.title,
        "issuer": citation.issuer,
        "issue_date": citation.issue_date.isoformat() if citation.issue_date else None,
        "source_url": citation.source_url,
        "chunk_id": citation.chunk_id,
        "page_number": citation.page_number,
        "section_title": citation.section_title,
        "evidence": citation.evidence,
    }


def hit_to_dict(hit: RetrievalHit) -> dict[str, Any]:
    return {
        "source": hit.source,
        "document_id": hit.document_id,
        "version_id": hit.version_id,
        "family_id": hit.family_id,
        "chunk_id": hit.chunk_id,
        "title": hit.title,
        "source_url": hit.source_url,
        "final_score": hit.final_score,
        "vector_score": hit.vector_score,
        "keyword_score": hit.keyword_score,
        "graph_score": hit.graph_score,
        "metadata": hit.metadata,
    }
