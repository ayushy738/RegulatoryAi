from __future__ import annotations

import time
from abc import ABC, abstractmethod
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from backend.core.config import settings
from backend.core.db import session_scope
from backend.core.logging import log_event
from backend.rag.embedding_health import (
    inspect_runtime_embedding_compatibility,
    vector_preflight_outcome,
)
from backend.rag.embeddings import EmbeddingProvider, EmbeddingProviderFactory
from backend.rag.intent import detect_intent
from backend.rag.models import (
    Citation,
    HybridRetrievalResult,
    RetrievalBranch,
    RetrievalBranchHealth,
    RetrievalBranchStatus,
    RetrievalHit,
)
from backend.rag.outcomes import (
    PartialRetrievalBranchResult,
    RetrievalBranchExecution,
    RetrievalBranchPreflightFailure,
    execute_retrieval_branch,
)
from backend.rag.ranker import rank_hits
from backend.rag.vector_store import VectorStore, VectorStoreFactory


class RetrievalProvider(ABC):
    provider_name: str

    @abstractmethod
    def keyword_search(
        self,
        query: str,
        *,
        limit: int,
        event_id: int | None = None,
    ) -> list[RetrievalHit]:
        raise NotImplementedError

    @abstractmethod
    def vector_search(
        self,
        query: str,
        *,
        limit: int,
        event_id: int | None = None,
    ) -> list[RetrievalHit]:
        raise NotImplementedError

    @abstractmethod
    def graph_search(
        self,
        query: str,
        *,
        limit: int,
        event_id: int | None = None,
    ) -> list[RetrievalHit]:
        raise NotImplementedError

    @abstractmethod
    def hybrid_search(
        self,
        query: str,
        *,
        limit: int,
        event_id: int | None = None,
    ) -> HybridRetrievalResult:
        raise NotImplementedError

    @abstractmethod
    def health(self) -> dict[str, Any]:
        raise NotImplementedError


class SupabaseHybridRetrieval(RetrievalProvider):
    provider_name = "supabase"

    def __init__(
        self,
        *,
        embedding_provider: EmbeddingProvider | None = None,
        vector_store: VectorStore | None = None,
    ) -> None:
        self._embedding_provider = embedding_provider
        self._vector_store = vector_store

    def keyword_search(
        self,
        query: str,
        *,
        limit: int,
        event_id: int | None = None,
    ) -> list[RetrievalHit]:
        return list(
            self.branch_search(
                RetrievalBranch.KEYWORD,
                query,
                limit=limit,
                event_id=event_id,
            ).hits
        )

    def _keyword_search(
        self,
        query: str,
        *,
        limit: int,
        event_id: int | None = None,
    ) -> list[RetrievalHit]:
        event_join, event_clause, params = _event_filter(event_id)
        params.update({"query": query, "limit": limit})
        sql = text(
            f"""
            select
              c.id as chunk_id,
              c.document_id,
              c.version_id,
              c.family_id,
              c.chunk_index,
              c.page_number,
              c.section_title,
              c.text as chunk_text,
              d.title,
              d.issuing_body,
              d.issue_date,
              d.source_url,
              ts_rank_cd(c.search_vector, websearch_to_tsquery('english', :query))
                as keyword_score,
              (df.latest_version_id = c.version_id) as latest_version
            from document_chunks c
            join documents d on d.id = c.document_id
            left join document_families df on df.family_id = c.family_id
            {event_join}
            where (
              c.search_vector @@ websearch_to_tsquery('english', :query)
              or d.title ilike '%' || :query || '%'
              or d.issuing_body ilike '%' || :query || '%'
              or coalesce(df.canonical_title, '') ilike '%' || :query || '%'
            )
            {event_clause}
            order by keyword_score desc nulls last, d.issue_date desc nulls last
            limit :limit
            """
        )
        with session_scope() as session:
            rows = session.execute(sql, params).mappings()
            return [_chunk_hit(row, source="keyword") for row in rows]

    def vector_search(
        self,
        query: str,
        *,
        limit: int,
        event_id: int | None = None,
    ) -> list[RetrievalHit]:
        return list(
            self.branch_search(
                RetrievalBranch.VECTOR,
                query,
                limit=limit,
                event_id=event_id,
            ).hits
        )

    def _vector_search(
        self,
        query: str,
        *,
        limit: int,
        event_id: int | None = None,
    ) -> list[RetrievalHit]:
        try:
            embedding_provider = (
                self._embedding_provider
                or EmbeddingProviderFactory.get_provider()
            )
            vector_store = self._vector_store or VectorStoreFactory.get_provider()
        except Exception as exc:
            raise RetrievalBranchPreflightFailure(
                status=RetrievalBranchStatus.UNAVAILABLE,
                health=RetrievalBranchHealth.FAILED,
                safe_failure_code="EMBEDDING_PROVIDER_UNAVAILABLE",
            ) from exc
        compatibility = inspect_runtime_embedding_compatibility(
            embedding_provider,
            vector_store,
        )
        preflight = vector_preflight_outcome(compatibility)
        if preflight is not None:
            if preflight.status is RetrievalBranchStatus.NO_MATCH:
                return []
            raise RetrievalBranchPreflightFailure(
                status=preflight.status,
                health=preflight.health,
                safe_failure_code=(
                    preflight.safe_failure_code
                    or "EMBEDDING_HEALTH_INVALID_METADATA"
                ),
            )
        embedding = embedding_provider.embed(query)
        return vector_store.similarity_search(
            embedding,
            limit=limit,
            event_id=event_id,
        )

    def graph_search(
        self,
        query: str,
        *,
        limit: int,
        event_id: int | None = None,
    ) -> list[RetrievalHit]:
        return list(
            self.branch_search(
                RetrievalBranch.GRAPH,
                query,
                limit=limit,
                event_id=event_id,
            ).hits
        )

    def _graph_search(
        self,
        query: str,
        *,
        limit: int,
        event_id: int | None = None,
    ) -> list[RetrievalHit] | PartialRetrievalBranchResult:
        hits = []
        failures = 0
        graph_workers = (
            _deadline_hits,
            _obligation_hits,
            _stakeholder_hits,
            _relationship_hits,
        )
        for worker in graph_workers:
            try:
                hits.extend(worker(query, limit=limit, event_id=event_id))
            except SQLAlchemyError:
                failures += 1
        if failures == len(graph_workers):
            raise RuntimeError("All graph retrieval units are unavailable")
        if failures:
            return PartialRetrievalBranchResult(hits=tuple(hits[:limit]))
        return hits[:limit]

    def family_search(
        self,
        query: str,
        *,
        limit: int,
        event_id: int | None = None,
    ) -> list[RetrievalHit]:
        return list(
            self.branch_search(
                RetrievalBranch.FAMILY_VERSION,
                query,
                limit=limit,
                event_id=event_id,
            ).hits
        )

    def _family_search(
        self,
        query: str,
        *,
        limit: int,
        event_id: int | None = None,
    ) -> list[RetrievalHit]:
        del event_id
        with session_scope() as session:
            rows = session.execute(
                text(
                    """
                        select
                          d.id as document_id,
                          d.title,
                          d.issuing_body,
                          d.issue_date,
                          d.source_url,
                          dvr.document_version_id as version_id,
                          f.family_id,
                          f.canonical_title,
                          dvr.version_label,
                          dvr.amendment_number,
                          dvr.referenced_instrument,
                          dvr.effective_date
                        from document_version_registry dvr
                        join documents d on d.id = dvr.document_id
                        join document_families f on f.family_id = dvr.family_id
                        where d.title ilike '%' || :query || '%'
                           or f.canonical_title ilike '%' || :query || '%'
                           or coalesce(dvr.version_label, '') ilike '%' || :query || '%'
                           or coalesce(dvr.referenced_instrument, '') ilike '%' || :query || '%'
                        order by d.issue_date desc nulls last, dvr.registry_version_id desc
                        limit :limit
                    """
                ),
                {"query": query, "limit": limit},
            ).mappings()
            return [_family_hit(row) for row in rows]

    def summary_search(
        self,
        query: str,
        *,
        limit: int,
        event_id: int | None = None,
    ) -> list[RetrievalHit]:
        return list(
            self.branch_search(
                RetrievalBranch.SUMMARY,
                query,
                limit=limit,
                event_id=event_id,
            ).hits
        )

    def _summary_search(
        self,
        query: str,
        *,
        limit: int,
        event_id: int | None = None,
    ) -> list[RetrievalHit]:
        event_clause = "and e.id = :event_id" if event_id is not None else ""
        params = {"query": query, "limit": limit, "event_id": event_id}
        with session_scope() as session:
            rows = session.execute(
                text(
                    f"""
                        select
                          d.id as document_id,
                          d.title,
                          d.issuing_body,
                          d.issue_date,
                          d.source_url,
                          e.version_id,
                          sm.summary_json::text as summary_text,
                          ts_rank_cd(
                            to_tsvector('english', sm.summary_json::text),
                            websearch_to_tsquery('english', :query)
                          ) as keyword_score
                        from summaries sm
                        join events e on e.id = sm.event_id
                        join documents d on d.id = e.document_id
                        where (
                          to_tsvector('english', sm.summary_json::text)
                            @@ websearch_to_tsquery('english', :query)
                          or sm.summary_json::text ilike '%' || :query || '%'
                        )
                        {event_clause}
                        order by keyword_score desc nulls last, e.detected_at desc
                        limit :limit
                    """
                ),
                params,
            ).mappings()
            return [_summary_hit(row) for row in rows]

    def branch_search(
        self,
        branch: RetrievalBranch,
        query: str,
        *,
        limit: int,
        event_id: int | None = None,
        clock: Callable[[], float] = time.perf_counter,
    ) -> RetrievalBranchExecution:
        workers = {
            RetrievalBranch.VECTOR: self._vector_search,
            RetrievalBranch.KEYWORD: self._keyword_search,
            RetrievalBranch.GRAPH: self._graph_search,
            RetrievalBranch.FAMILY_VERSION: self._family_search,
            RetrievalBranch.SUMMARY: self._summary_search,
        }
        worker = workers[branch]
        return execute_retrieval_branch(
            branch=branch,
            worker=lambda: worker(query, limit=limit, event_id=event_id),
            clock=clock,
        )

    def hybrid_search(
        self,
        query: str,
        *,
        limit: int,
        event_id: int | None = None,
    ) -> HybridRetrievalResult:
        started = time.perf_counter()
        log_event(
            "retrieval_started",
            retrieval_provider=self.provider_name,
            limit=limit,
            event_id=event_id,
        )
        intent = detect_intent(query)
        search_limit = max(limit, settings.rag_top_k)
        tasks = {
            branch: (
                lambda selected=branch: self.branch_search(
                    selected,
                    query,
                    limit=search_limit,
                    event_id=event_id,
                )
            )
            for branch in RetrievalBranch
        }
        hits: list[RetrievalHit] = []
        branch_executions: list[RetrievalBranchExecution] = []
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(task) for task in tasks.values()]
            for future in as_completed(futures):
                execution = future.result()
                hits.extend(execution.hits)
                branch_executions.append(execution)
        ranked = rank_hits(hits, intent, limit=limit)
        citations = _dedupe_citations([hit.citation() for hit in ranked])
        result = HybridRetrievalResult(
            query=query,
            intent=intent,
            hits=ranked,
            citations=citations,
            graph_facts=[hit for hit in ranked if hit.source == "graph"],
            related_questions=_related_questions(intent.name),
            related_documents=citations[:5],
            retrieval_latency_ms=_elapsed_ms(started),
            branch_outcomes=[
                execution.outcome
                for execution in sorted(
                    branch_executions,
                    key=lambda item: list(RetrievalBranch).index(
                        item.outcome.branch
                    ),
                )
            ],
        )
        log_event(
            "retrieval_finished",
            retrieval_provider=self.provider_name,
            intent=result.intent.name,
            hits=len(result.hits),
            citations=len(result.citations),
            graph_facts=len(result.graph_facts),
            retrieval_latency_ms=result.retrieval_latency_ms,
            branch_outcomes=[
                {
                    "branch": outcome.branch.value,
                    "status": outcome.status.value,
                    "health": outcome.health.value,
                    "hits": outcome.match_count,
                    "safe_failure_code": outcome.safe_failure_code,
                }
                for outcome in result.branch_outcomes
            ],
        )
        return result

    def health(self) -> dict[str, Any]:
        vector_store = self._vector_store or VectorStoreFactory.get_provider()
        embedding_provider = (
            self._embedding_provider
            or EmbeddingProviderFactory.get_provider()
        )
        return {
            "provider": self.provider_name,
            "vector_store": vector_store.health(),
            "embedding_provider": embedding_provider.health(),
        }


class RetrievalProviderFactory:
    @staticmethod
    def get_provider() -> RetrievalProvider:
        return SupabaseHybridRetrieval()


def _event_filter(event_id: int | None) -> tuple[str, str, dict[str, Any]]:
    if event_id is None:
        return "", "", {}
    return (
        "join events ev on ev.document_id = d.id",
        "and ev.id = :event_id",
        {"event_id": event_id},
    )


def _deadline_hits(query: str, *, limit: int, event_id: int | None) -> list[RetrievalHit]:
    event_join, event_clause, params = _event_filter(event_id)
    params.update({"query": query, "limit": limit})
    return _graph_rows(
        f"""
        select
          d.id as document_id,
          d.title,
          d.issuing_body,
          d.issue_date,
          d.source_url,
          gd.document_version_id as version_id,
          'Deadline: ' || gd.deadline_type || ' ' ||
            coalesce(gd.deadline_date::text, gd.raw_date, '') || E'\n' ||
            coalesce(gd.evidence, '') as fact_text,
          gd.confidence as graph_score
        from regulatory_graph_deadlines gd
        join documents d on d.id = gd.document_id
        {event_join}
        where (
          gd.deadline_type ilike '%' || :query || '%'
          or coalesce(gd.evidence, '') ilike '%' || :query || '%'
          or d.title ilike '%' || :query || '%'
        )
        {event_clause}
        order by gd.deadline_date asc nulls last, gd.confidence desc
        limit :limit
        """,
        params,
    )


def _obligation_hits(query: str, *, limit: int, event_id: int | None) -> list[RetrievalHit]:
    event_join, event_clause, params = _event_filter(event_id)
    params.update({"query": query, "limit": limit})
    return _graph_rows(
        f"""
        select
          d.id as document_id,
          d.title,
          d.issuing_body,
          d.issue_date,
          d.source_url,
          o.document_version_id as version_id,
          'Obligation: ' || o.obligation || E'\nAffected party: ' ||
            coalesce(o.affected_party, 'Unresolved') || E'\n' ||
            coalesce(o.evidence, '') as fact_text,
          o.confidence as graph_score
        from regulatory_graph_obligations o
        join documents d on d.id = o.document_id
        {event_join}
        where (
          o.obligation ilike '%' || :query || '%'
          or coalesce(o.affected_party, '') ilike '%' || :query || '%'
          or coalesce(o.evidence, '') ilike '%' || :query || '%'
          or d.title ilike '%' || :query || '%'
        )
        {event_clause}
        order by o.confidence desc
        limit :limit
        """,
        params,
    )


def _stakeholder_hits(query: str, *, limit: int, event_id: int | None) -> list[RetrievalHit]:
    event_join, event_clause, params = _event_filter(event_id)
    params.update({"query": query, "limit": limit})
    return _graph_rows(
        f"""
        select
          d.id as document_id,
          d.title,
          d.issuing_body,
          d.issue_date,
          d.source_url,
          s.document_version_id as version_id,
          'Stakeholder: ' || s.stakeholder || E'\n' ||
            coalesce(s.evidence, '') as fact_text,
          s.confidence as graph_score
        from regulatory_graph_stakeholders s
        join documents d on d.id = s.document_id
        {event_join}
        where (
          s.stakeholder ilike '%' || :query || '%'
          or s.normalized_stakeholder ilike '%' || :query || '%'
          or coalesce(s.evidence, '') ilike '%' || :query || '%'
          or d.title ilike '%' || :query || '%'
        )
        {event_clause}
        order by s.confidence desc
        limit :limit
        """,
        params,
    )


def _relationship_hits(query: str, *, limit: int, event_id: int | None) -> list[RetrievalHit]:
    event_join, event_clause, params = _event_filter(event_id)
    params.update({"query": query, "limit": limit})
    return _graph_rows(
        f"""
        select
          d.id as document_id,
          d.title,
          d.issuing_body,
          d.issue_date,
          d.source_url,
          e.source_document_version_id as version_id,
          'Relationship: ' || source.name || ' ' || e.relationship_type ||
            ' ' || target.name || E'\n' || coalesce(e.evidence, '') as fact_text,
          e.confidence as graph_score
        from regulatory_graph_edges e
        join regulatory_graph_entities source on source.entity_id = e.from_entity_id
        join regulatory_graph_entities target on target.entity_id = e.to_entity_id
        join documents d on d.id = e.source_document_id
        {event_join}
        where (
          e.relationship_type ilike '%' || :query || '%'
          or source.name ilike '%' || :query || '%'
          or target.name ilike '%' || :query || '%'
          or coalesce(e.evidence, '') ilike '%' || :query || '%'
          or d.title ilike '%' || :query || '%'
        )
        {event_clause}
        order by e.confidence desc
        limit :limit
        """,
        params,
    )


def _graph_rows(sql: str, params: dict[str, Any]) -> list[RetrievalHit]:
    with session_scope() as session:
        rows = session.execute(text(sql), params).mappings()
        return [_graph_hit(row) for row in rows]


def _chunk_hit(row: Any, *, source: str) -> RetrievalHit:
    return RetrievalHit(
        source=source,  # type: ignore[arg-type]
        document_id=int(row["document_id"]),
        title=row["title"],
        issuer=row["issuing_body"],
        issue_date=row["issue_date"],
        source_url=row["source_url"],
        version_id=row["version_id"],
        family_id=row["family_id"],
        chunk_id=row["chunk_id"],
        chunk_index=row["chunk_index"],
        page_number=row["page_number"],
        section_title=row["section_title"],
        text=row["chunk_text"],
        keyword_score=float(row.get("keyword_score") or 0),
        metadata={"latest_version": bool(row.get("latest_version"))},
    )


def _graph_hit(row: Any) -> RetrievalHit:
    return RetrievalHit(
        source="graph",
        document_id=int(row["document_id"]),
        title=row["title"],
        issuer=row["issuing_body"],
        issue_date=row["issue_date"],
        source_url=row["source_url"],
        version_id=row["version_id"],
        text=row["fact_text"],
        graph_score=float(row["graph_score"] or 0.65),
        metadata={"latest_version": True},
    )


def _family_hit(row: Any) -> RetrievalHit:
    pieces = [
        f"Family: {row['canonical_title']}",
        f"Version: {row['version_label'] or 'Unlabelled'}",
    ]
    if row.get("amendment_number") is not None:
        pieces.append(f"Amendment number: {row['amendment_number']}")
    if row.get("referenced_instrument"):
        pieces.append(f"Referenced instrument: {row['referenced_instrument']}")
    if row.get("effective_date"):
        pieces.append(f"Effective date: {row['effective_date']}")
    return RetrievalHit(
        source="family",
        document_id=int(row["document_id"]),
        title=row["title"],
        issuer=row["issuing_body"],
        issue_date=row["issue_date"],
        source_url=row["source_url"],
        version_id=row["version_id"],
        family_id=row["family_id"],
        text="\n".join(pieces),
        graph_score=0.72,
        metadata={"latest_version": True},
    )


def _summary_hit(row: Any) -> RetrievalHit:
    return RetrievalHit(
        source="summary",
        document_id=int(row["document_id"]),
        title=row["title"],
        issuer=row["issuing_body"],
        issue_date=row["issue_date"],
        source_url=row["source_url"],
        version_id=row["version_id"],
        text=row["summary_text"],
        keyword_score=float(row["keyword_score"] or 0.45),
        metadata={"latest_version": True},
    )


def _dedupe_citations(citations: list[Citation]) -> list[Citation]:
    seen: set[tuple[int, int | None]] = set()
    output: list[Citation] = []
    for citation in citations:
        key = (citation.document_id, citation.chunk_id)
        if key in seen:
            continue
        seen.add(key)
        output.append(citation)
    return output


def _related_questions(intent: str) -> list[str]:
    if intent == "deadline":
        return [
            "Which stakeholders are affected by these deadlines?",
            "Are any deadlines linked to obligations?",
            "Show related consultations.",
        ]
    if intent == "obligation":
        return [
            "Who must comply with these obligations?",
            "Are there deadline dates for these obligations?",
            "Which regulation created this obligation?",
        ]
    if intent in {"amendment", "comparison"}:
        return [
            "What changed from the prior version?",
            "Which document does this amendment reference?",
            "Show the family version history.",
        ]
    return [
        "Show related regulations.",
        "Show related amendments.",
        "Show related consultations or tenders.",
    ]


def _elapsed_ms(started: float) -> int:
    return max(0, int((time.perf_counter() - started) * 1000))
