from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any

from sqlalchemy import text

from backend.core.db import session_scope
from backend.rag.chunker import chunk_document_text
from backend.rag.embeddings import EmbeddingProviderFactory
from backend.rag.models import DocumentChunk
from backend.rag.vector_store import VectorStoreFactory

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RagIndexResult:
    document_id: int
    version_id: int | None
    status: str
    chunk_count: int
    embedded_chunk_count: int
    latency_ms: int
    error: str | None = None


def enqueue_rag_index_job(
    session: Any,
    *,
    document_id: int,
    version_id: int | None,
) -> None:
    session.execute(
        text(
            """
            insert into rag_index_jobs (document_id, version_id, status, updated_at)
            values (:document_id, :version_id, 'PENDING', now())
            on conflict (document_id, coalesce(version_id, 0)) do update set
              status = case
                when rag_index_jobs.status = 'COMPLETED' then rag_index_jobs.status
                else 'PENDING'
              end,
              updated_at = now()
            """
        ),
        {"document_id": document_id, "version_id": version_id},
    )
    session.execute(
        text(
            """
            insert into document_rag_status (document_id, version_id, status, updated_at)
            values (:document_id, :version_id, 'PENDING', now())
            on conflict (document_id) do update set
              version_id = excluded.version_id,
              status = case
                when document_rag_status.status = 'RAG_READY' then document_rag_status.status
                else 'PENDING'
              end,
              updated_at = now()
            """
        ),
        {"document_id": document_id, "version_id": version_id},
    )


def process_pending_rag_jobs(
    *,
    limit: int = 25,
    include_processing: bool = False,
) -> dict[str, Any]:
    if include_processing:
        requeue_processing_jobs(limit=limit)
    results = []
    for _ in range(limit):
        jobs = _claim_jobs(limit=1)
        if not jobs:
            break
        job = jobs[0]
        result = index_document(
            document_id=int(job["document_id"]),
            version_id=job.get("version_id"),
            job_id=int(job["job_id"]),
        )
        results.append(result)
    return {
        "processed": len(results),
        "ready": sum(1 for result in results if result.status == "RAG_READY"),
        "failed": sum(1 for result in results if result.status == "FAILED"),
        "results": [result.__dict__ for result in results],
    }


def requeue_processing_jobs(*, limit: int | None = None) -> dict[str, int]:
    limit_sql = "limit :limit" if limit is not None else ""
    with session_scope() as session:
        rows = session.execute(
            text(
                f"""
                select job_id
                from rag_index_jobs
                where status = 'PROCESSING'
                order by updated_at, job_id
                {limit_sql}
                """
            ),
            {"limit": limit},
        ).mappings().all()
        job_ids = [int(row["job_id"]) for row in rows]
        if not job_ids:
            return {"requeued": 0}
        session.execute(
            text(
                """
                update rag_index_jobs
                set status = 'PENDING',
                    last_error = 'Requeued after interrupted processing.',
                    updated_at = now()
                where job_id = any(:job_ids)
                """
            ),
            {"job_ids": job_ids},
        )
        return {"requeued": len(job_ids)}


def enqueue_existing_documents(*, limit: int | None = None) -> dict[str, int]:
    limit_sql = "limit :limit" if limit is not None else ""
    params = {"limit": limit}
    with session_scope() as session:
        rows = session.execute(
            text(
                f"""
                select
                  d.id as document_id,
                  dv.id as version_id
                from documents d
                join lateral (
                  select *
                  from document_versions
                  where document_id = d.id
                  order by fetched_at desc
                  limit 1
                ) dv on true
                join document_texts dt on dt.content_hash = dv.content_hash
                where coalesce(dt.content_length, 0) >= 250
                order by d.id
                {limit_sql}
                """
            ),
            params,
        ).mappings().all()
        for row in rows:
            enqueue_rag_index_job(
                session,
                document_id=int(row["document_id"]),
                version_id=row["version_id"],
            )
        return {"queued": len(rows)}


def index_document(
    *,
    document_id: int,
    version_id: int | None = None,
    job_id: int | None = None,
) -> RagIndexResult:
    started = time.perf_counter()
    try:
        row = _load_document_text(document_id=document_id, version_id=version_id)
        if not row or not str(row.get("text_content") or "").strip():
            result = RagIndexResult(
                document_id=document_id,
                version_id=version_id,
                status="SKIPPED",
                chunk_count=0,
                embedded_chunk_count=0,
                latency_ms=_elapsed_ms(started),
                error="No extracted text available.",
            )
            _record_result(result, job_id=job_id)
            return result

        chunks = chunk_document_text(
            document_id=int(row["document_id"]),
            version_id=row.get("version_id"),
            family_id=row.get("family_id"),
            text=row["text_content"],
            content_hash=row.get("content_hash"),
        )
        chunks = _replace_chunks(chunks)
        _update_status(
            document_id=document_id,
            version_id=row.get("version_id"),
            status="CHUNKED",
            chunk_count=len(chunks),
            embedded_chunk_count=0,
        )
        provider = EmbeddingProviderFactory.get_provider()
        _update_status(
            document_id=document_id,
            version_id=row.get("version_id"),
            status="EMBEDDING",
            chunk_count=len(chunks),
            embedded_chunk_count=0,
            provider=provider.provider_name,
            model=provider.model,
        )
        embeddings = provider.embed_batch([chunk.text for chunk in chunks])
        embedded = VectorStoreFactory.get_provider().upsert_chunks(
            chunks,
            embeddings,
            embedding_provider=provider.provider_name,
            embedding_model=provider.model,
        )
        result = RagIndexResult(
            document_id=document_id,
            version_id=row.get("version_id"),
            status="RAG_READY",
            chunk_count=len(chunks),
            embedded_chunk_count=embedded,
            latency_ms=_elapsed_ms(started),
        )
        _record_result(
            result,
            job_id=job_id,
            provider=provider.provider_name,
            model=provider.model,
        )
        return result
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
        logger.warning("RAG indexing failed for document %s: %s", document_id, error)
        result = RagIndexResult(
            document_id=document_id,
            version_id=version_id,
            status="FAILED",
            chunk_count=0,
            embedded_chunk_count=0,
            latency_ms=_elapsed_ms(started),
            error=error,
        )
        _record_result(result, job_id=job_id)
        return result


def _claim_jobs(*, limit: int) -> list[dict[str, Any]]:
    with session_scope() as session:
        rows = session.execute(
            text(
                """
                select job_id, document_id, version_id
                from rag_index_jobs
                where status in ('PENDING', 'FAILED')
                order by updated_at, job_id
                limit :limit
                """
            ),
            {"limit": limit},
        ).mappings().all()
        job_ids = [int(row["job_id"]) for row in rows]
        if job_ids:
            session.execute(
                text(
                    """
                    update rag_index_jobs
                    set status = 'PROCESSING',
                        attempts = attempts + 1,
                        updated_at = now()
                    where job_id = any(:job_ids)
                    """
                ),
                {"job_ids": job_ids},
            )
        return [dict(row) for row in rows]


def _load_document_text(
    *,
    document_id: int,
    version_id: int | None,
) -> dict[str, Any] | None:
    version_clause = "and id = :version_id" if version_id is not None else ""
    params = {"document_id": document_id, "version_id": version_id}
    with session_scope() as session:
        row = session.execute(
            text(
                f"""
                select
                  d.id as document_id,
                  d.title,
                  d.source_url,
                  dv.id as version_id,
                  dv.content_hash,
                  dt.text_content,
                  a.family_id
                from documents d
                join lateral (
                  select *
                  from document_versions
                  where document_id = d.id
                  {version_clause}
                  order by fetched_at desc
                  limit 1
                ) dv on true
                left join document_texts dt on dt.content_hash = dv.content_hash
                left join document_family_assignments a on a.document_id = d.id
                where d.id = :document_id
                """
            ),
            params,
        ).mappings().first()
        return dict(row) if row else None


def _replace_chunks(chunks: list[DocumentChunk]) -> list[DocumentChunk]:
    if not chunks:
        return []
    document_id = chunks[0].document_id
    version_id = chunks[0].version_id
    with session_scope() as session:
        session.execute(
            text(
                """
                delete from document_chunks
                where document_id = :document_id
                  and (:version_id is null or version_id = :version_id)
                """
            ),
            {"document_id": document_id, "version_id": version_id},
        )
        stored: list[DocumentChunk] = []
        for chunk in chunks:
            chunk_id = session.execute(
                text(
                    """
                    insert into document_chunks (
                      document_id,
                      version_id,
                      family_id,
                      chunk_index,
                      text,
                      token_count,
                      page_number,
                      section_title,
                      content_hash
                    )
                    values (
                      :document_id,
                      :version_id,
                      :family_id,
                      :chunk_index,
                      :text,
                      :token_count,
                      :page_number,
                      :section_title,
                      :content_hash
                    )
                    returning id
                    """
                ),
                {
                    "document_id": chunk.document_id,
                    "version_id": chunk.version_id,
                    "family_id": chunk.family_id,
                    "chunk_index": chunk.chunk_index,
                    "text": chunk.text,
                    "token_count": chunk.token_count,
                    "page_number": chunk.page_number,
                    "section_title": chunk.section_title,
                    "content_hash": chunk.content_hash,
                },
            ).scalar_one()
            stored.append(DocumentChunk(**{**chunk.__dict__, "id": int(chunk_id)}))
        return stored


def _record_result(
    result: RagIndexResult,
    *,
    job_id: int | None,
    provider: str | None = None,
    model: str | None = None,
) -> None:
    _update_status(
        document_id=result.document_id,
        version_id=result.version_id,
        status=result.status,
        chunk_count=result.chunk_count,
        embedded_chunk_count=result.embedded_chunk_count,
        provider=provider,
        model=model,
        error=result.error,
    )
    if job_id is None:
        return
    with session_scope() as session:
        session.execute(
            text(
                """
                update rag_index_jobs
                set status = :status,
                    last_error = :error,
                    updated_at = now()
                where job_id = :job_id
                """
            ),
            {"job_id": job_id, "status": _job_status(result.status), "error": result.error},
        )


def _update_status(
    *,
    document_id: int,
    version_id: int | None,
    status: str,
    chunk_count: int,
    embedded_chunk_count: int,
    provider: str | None = None,
    model: str | None = None,
    error: str | None = None,
) -> None:
    with session_scope() as session:
        session.execute(
            text(
                """
                insert into document_rag_status (
                  document_id,
                  version_id,
                  status,
                  chunk_count,
                  embedded_chunk_count,
                  provider,
                  model,
                  error,
                  updated_at
                )
                values (
                  :document_id,
                  :version_id,
                  :status,
                  :chunk_count,
                  :embedded_chunk_count,
                  :provider,
                  :model,
                  :error,
                  now()
                )
                on conflict (document_id) do update set
                  version_id = excluded.version_id,
                  status = excluded.status,
                  chunk_count = excluded.chunk_count,
                  embedded_chunk_count = excluded.embedded_chunk_count,
                  provider = coalesce(excluded.provider, document_rag_status.provider),
                  model = coalesce(excluded.model, document_rag_status.model),
                  error = excluded.error,
                  updated_at = now()
                """
            ),
            {
                "document_id": document_id,
                "version_id": version_id,
                "status": status,
                "chunk_count": chunk_count,
                "embedded_chunk_count": embedded_chunk_count,
                "provider": provider,
                "model": model,
                "error": error,
            },
        )


def _job_status(status: str) -> str:
    if status == "RAG_READY":
        return "COMPLETED"
    if status == "SKIPPED":
        return "SKIPPED"
    if status == "FAILED":
        return "FAILED"
    return "PROCESSING"


def _elapsed_ms(started: float) -> int:
    return max(0, int((time.perf_counter() - started) * 1000))
