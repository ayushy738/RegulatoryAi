from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Literal

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
