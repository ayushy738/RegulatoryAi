from __future__ import annotations

from typing import Any

from sqlalchemy import text

from backend.core.db import session_scope
from backend.rag.context_builder import build_context
from backend.rag.embeddings import EmbeddingProviderFactory
from backend.rag.models import citation_to_dict, hit_to_dict
from backend.rag.retrieval import RetrievalProviderFactory
from backend.rag.vector_store import VectorStoreFactory


def rag_status() -> dict[str, Any]:
    with session_scope() as session:
        row = session.execute(
            text(
                """
                select
                  (select count(*) from document_chunks) as chunks,
                  (select count(*) from document_chunk_embeddings) as embeddings,
                  (select count(*) from document_rag_status where status = 'RAG_READY') as ready,
                  (select count(*) from document_rag_status where status = 'FAILED') as failed,
                  (select count(*) from rag_index_jobs where status = 'PENDING') as pending_jobs,
                  (select count(*) from rag_index_jobs where status = 'FAILED') as failed_jobs
                """
            )
        ).mappings().first()
    return {
        **{key: int(value or 0) for key, value in dict(row or {}).items()},
        "embedding_provider": EmbeddingProviderFactory.get_provider().health(),
        "vector_store": VectorStoreFactory.get_provider().health(),
    }


def embedding_queue(limit: int = 100) -> list[dict[str, Any]]:
    with session_scope() as session:
        rows = session.execute(
            text(
                """
                select job_id, document_id, version_id, status, attempts, last_error,
                       created_at, updated_at
                from rag_index_jobs
                order by updated_at desc, job_id desc
                limit :limit
                """
            ),
            {"limit": limit},
        ).mappings()
        return [dict(row) for row in rows]


def chunk_count() -> list[dict[str, Any]]:
    with session_scope() as session:
        rows = session.execute(
            text(
                """
                select d.id as document_id, d.title, rs.status, rs.chunk_count,
                       rs.embedded_chunk_count, rs.provider, rs.model, rs.error
                from document_rag_status rs
                join documents d on d.id = rs.document_id
                order by rs.updated_at desc
                limit 200
                """
            )
        ).mappings()
        return [dict(row) for row in rows]


def chunk_inspector(document_id: int) -> list[dict[str, Any]]:
    with session_scope() as session:
        rows = session.execute(
            text(
                """
                select id, document_id, version_id, family_id, chunk_index, token_count,
                       page_number, section_title, left(text, 1200) as preview, created_at
                from document_chunks
                where document_id = :document_id
                order by chunk_index
                """
            ),
            {"document_id": document_id},
        ).mappings()
        return [dict(row) for row in rows]


def retrieval_inspector(query: str, *, limit: int = 15) -> dict[str, Any]:
    result = RetrievalProviderFactory.get_provider().hybrid_search(query, limit=limit)
    return {
        "intent": result.intent.name,
        "retrieval_latency_ms": result.retrieval_latency_ms,
        "hits": [hit_to_dict(hit) for hit in result.hits],
        "citations": [citation_to_dict(citation) for citation in result.citations],
        "related_questions": result.related_questions,
    }


def context_preview(query: str, *, limit: int = 15) -> dict[str, Any]:
    result = RetrievalProviderFactory.get_provider().hybrid_search(query, limit=limit)
    context = build_context(result)
    return {
        "intent": result.intent.name,
        "estimated_tokens": context.estimated_tokens,
        "context": context.prompt_context,
        "citations": [citation_to_dict(citation) for citation in context.citations],
    }


def prompt_preview(query: str, *, limit: int = 15) -> dict[str, Any]:
    preview = context_preview(query, limit=limit)
    return {
        "system_prompt": "Ground answers only in retrieved evidence and citations.",
        "user_prompt": (
            f"Conversation-aware retrieved context:\n{preview['context']}\n\n"
            f"Question:\n{query}\n\n"
            "Answer with grounded analysis and a short citation list."
        ),
        "estimated_tokens": preview["estimated_tokens"],
    }


def vector_search_tester(query: str, *, limit: int = 10) -> list[dict[str, Any]]:
    provider = EmbeddingProviderFactory.get_provider()
    embedding = provider.embed(query)
    hits = VectorStoreFactory.get_provider().similarity_search(embedding, limit=limit)
    return [hit_to_dict(hit) for hit in hits]
