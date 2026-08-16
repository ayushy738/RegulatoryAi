"""Crawl run abandonment recovery and incomplete-document downstream retry.

Schema note
-----------
``crawl_runs`` has started_at / finished_at / status only — no heartbeat or lease.
Admin triggers insert ``queued`` rows and dispatch GitHub Actions ``crawl-worker``;
the runner claims the row and executes the pipeline. If the runner dies, a row can
remain ``running`` with ``finished_at`` null until age-gated reclaim.

Safe reclaim without a migration
--------------------------------
Atomic UPDATE of rows that are still ``running``, have ``finished_at`` null, and
whose ``started_at`` is older than ``CRAWL_RUNNING_STALE_SECONDS`` (default 2h).

Risk (documented): a legitimate crawl that runs longer than the threshold while
the process stays alive would be marked failed. Current curated crawls finish in
minutes; tune via settings if needed. Multi-instance hosts remain safe because
only aged rows are touched and the UPDATE is idempotent.

Document downstream retry
-------------------------
Durable Session A commits (document/version/family) can outlive Session B
(graph/RAG/events). Retry rebuilds ExtractedDoc from storage, runs graph with
skip_completed, enqueues RAG idempotently, and creates an event only when none
exist for that document.
"""

from __future__ import annotations

import logging
from dataclasses import replace
from typing import Any

from sqlalchemy import text

from backend.core.config import settings
from backend.core.db import session_scope
from backend.core.logging import log_event
from backend.core.models import DiscoveredDoc, ExtractedDoc, FetchedFile
from backend.core.repository import (
    _DurableDocumentState,
    _process_document_downstream,
    _summary_from_extracted,
    _topic_tags,
)
from backend.pipeline.intelligence_gate import (
    assess_event_intelligence,
    attach_intelligence_to_summary,
)
from backend.pipeline.regulatory_knowledge_graph import (
    GRAPH_STATUS_COMPLETED,
    GRAPH_STATUS_FAILED,
    GRAPH_STATUS_PENDING,
    GRAPH_STATUS_PROCESSING,
    GRAPH_STATUS_SKIPPED,
)

logger = logging.getLogger(__name__)

ABANDONED_ERROR_CODE = "crawl_run_abandoned_process_death"
DEFAULT_STALE_SECONDS = 2 * 60 * 60
INCOMPLETE_GRAPH_STATUSES = {
    GRAPH_STATUS_FAILED,
    GRAPH_STATUS_PENDING,
    GRAPH_STATUS_PROCESSING,
}


def crawl_running_stale_seconds() -> int:
    return int(getattr(settings, "crawl_running_stale_seconds", DEFAULT_STALE_SECONDS))


def reclaim_stale_crawl_runs(
    *,
    stale_seconds: int | None = None,
    run_id: int | None = None,
    force: bool = False,
) -> dict[str, Any]:
    """Mark abandoned RUNNING crawl_runs as FAILED.

    Idempotent and concurrency-safe: a single UPDATE ... WHERE status='running'
    so concurrent reclaimers cannot double-finalize terminal rows.

    ``force=True`` with ``run_id`` skips the age gate for explicit operator repair
    (production Run #58). Without ``run_id``, force is rejected.
    """

    seconds = stale_seconds if stale_seconds is not None else crawl_running_stale_seconds()
    if seconds < 60:
        raise ValueError("stale_seconds must be at least 60")
    if force and run_id is None:
        raise ValueError("force reclaim requires an explicit run_id")

    with session_scope() as session:
        params: dict[str, Any] = {
            "stale_seconds": seconds,
            "error_code": ABANDONED_ERROR_CODE,
        }
        predicates = [
            "status = cast('running' as run_status_t)",
            "finished_at is null",
        ]
        if run_id is not None:
            predicates.append("id = cast(:run_id as bigint)")
            params["run_id"] = run_id
        if not force:
            predicates.append(
                "started_at < (now() - (cast(:stale_seconds as int) * interval '1 second'))"
            )

        where_sql = " and ".join(predicates)
        rows = session.execute(
            text(
                f"""
                update crawl_runs cr
                set
                  status = cast('failed' as run_status_t),
                  finished_at = now(),
                  docs_found = greatest(
                    coalesce(cr.docs_found, 0),
                    coalesce((
                      select count(*)::int from discovery_audit da
                      where da.run_id = cr.id
                    ), 0)
                  ),
                  sources_attempted = greatest(
                    coalesce(cr.sources_attempted, 0),
                    coalesce((
                      select count(distinct da.source_code)::int
                      from discovery_audit da
                      where da.run_id = cr.id
                    ), 0)
                  ),
                  sources_succeeded = case
                    when exists (
                      select 1 from discovery_audit da
                      where da.run_id = cr.id and da.content_hash is not null
                    )
                    then greatest(coalesce(cr.sources_succeeded, 0), 1)
                    else coalesce(cr.sources_succeeded, 0)
                  end,
                  new_events = greatest(
                    coalesce(cr.new_events, 0),
                    coalesce((
                      select count(distinct e.id)::int
                      from discovery_audit da
                      join document_versions dv on dv.content_hash = da.content_hash
                      join events e on e.document_id = dv.document_id
                      where da.run_id = cr.id and da.content_hash is not null
                    ), 0)
                  ),
                  errors = coalesce(cr.errors, '[]'::jsonb) || jsonb_build_array(
                    jsonb_build_object(
                      'source', 'crawl_recovery',
                      -- jsonb_build_object is variadic "any": bound parameters
                      -- must be cast explicitly or PostgreSQL cannot infer them.
                      'error_code', cast(:error_code as text),
                      'error',
                        'Crawl run abandoned: executing API process disappeared '
                        'before finalize_crawl_run (stale running reclaim).',
                      'stale_seconds', cast(:stale_seconds as int)
                    )
                  )
                where cr.id in (
                  select id
                  from crawl_runs
                  where {where_sql}
                  for update skip locked
                )
                returning cr.id, cr.docs_found, cr.new_events, cr.started_at, cr.finished_at
                """
            ),
            params,
        ).mappings()
        reclaimed = [dict(row) for row in rows]

    log_event(
        "crawl_runs_reclaimed",
        reclaimed=len(reclaimed),
        stale_seconds=seconds,
        run_id=run_id,
        force=force,
        run_ids=[row["id"] for row in reclaimed],
    )
    return {
        "stale_seconds": seconds,
        "force": force,
        "reclaimed": len(reclaimed),
        "runs": reclaimed,
    }


def list_incomplete_downstream_document_ids(*, limit: int = 50) -> list[int]:
    """Durable documents whose Session B (graph) did not reach a success terminal."""

    with session_scope() as session:
        rows = session.execute(
            text(
                """
                select d.id as document_id
                from documents d
                join lateral (
                  select id, content_hash, fetched_at
                  from document_versions
                  where document_id = d.id
                  order by fetched_at desc
                  limit 1
                ) dv on true
                left join regulatory_graph_extractions g on g.document_id = d.id
                where g.document_id is null
                   or g.status = any(:incomplete_statuses)
                order by d.id desc
                limit :limit
                """
            ),
            {
                "limit": limit,
                "incomplete_statuses": list(INCOMPLETE_GRAPH_STATUSES),
            },
        ).mappings()
        return [int(row["document_id"]) for row in rows]


def retry_incomplete_document_downstream(
    document_id: int,
    *,
    use_ai: bool = True,
) -> dict[str, Any]:
    """Re-run graph + RAG enqueue + event creation for a durable document.

    Does not insert a second documents/document_versions row. Graph uses
    skip_completed. RAG enqueue is ON CONFLICT idempotent. Events are skipped
    when any event already exists for the document.
    """

    del use_ai  # graph path reads settings; retained for CLI symmetry
    state = _load_durable_state_for_retry(document_id)
    if state is None:
        return {
            "document_id": document_id,
            "status": "FAILED",
            "error": "Document/version/text could not be loaded for downstream retry.",
        }

    existing_events = _event_count_for_document(document_id)
    # Force event creation only when none exist yet (interrupted before event insert).
    if existing_events > 0:
        state = replace(state, create_events=False)

    try:
        event_id = _process_document_downstream(state)
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
        logger.warning(
            "incomplete document downstream retry failed document_id=%s: %s",
            document_id,
            error,
        )
        log_event(
            "document_downstream_retry_failed",
            document_id=document_id,
            error=error,
        )
        return {
            "document_id": document_id,
            "status": "FAILED",
            "error": error,
            "event_id": None,
        }

    graph_status = _graph_status(document_id)
    rag = _rag_snapshot(document_id)
    log_event(
        "document_downstream_retry_finished",
        document_id=document_id,
        graph_status=graph_status,
        event_id=event_id,
        rag_job_status=rag.get("job_status"),
        rag_status=rag.get("rag_status"),
    )
    return {
        "document_id": document_id,
        "document_version_id": state.version_id,
        "status": "COMPLETED" if graph_status in {
            GRAPH_STATUS_COMPLETED,
            GRAPH_STATUS_SKIPPED,
        } else (graph_status or "FAILED"),
        "graph_status": graph_status,
        "event_id": event_id,
        "events_already_present": existing_events,
        "rag_job_status": rag.get("job_status"),
        "rag_status": rag.get("rag_status"),
        "error": None,
    }


def retry_incomplete_documents(
    *,
    limit: int = 50,
    document_id: int | None = None,
    use_ai: bool = True,
) -> dict[str, Any]:
    ids = [document_id] if document_id is not None else list_incomplete_downstream_document_ids(
        limit=limit
    )
    results = [
        retry_incomplete_document_downstream(doc_id, use_ai=use_ai) for doc_id in ids if doc_id
    ]
    return {
        "requested_limit": limit,
        "document_id": document_id,
        "processed": len(results),
        "results": results,
    }


def _load_durable_state_for_retry(document_id: int) -> _DurableDocumentState | None:
    with session_scope() as session:
        row = session.execute(
            text(
                """
                select
                  d.id as document_id,
                  d.source_id,
                  d.title,
                  d.source_url,
                  d.issuing_body,
                  d.issue_date,
                  d.issue_date_precision::text as issue_date_precision,
                  d.doc_type,
                  d.jurisdiction::text as jurisdiction,
                  s.code as source_code,
                  dv.id as version_id,
                  dv.file_hash,
                  dv.content_hash,
                  dv.raw_file_path,
                  dv.text_path,
                  dv.page_count,
                  dv.needs_ocr,
                  dv.http_status,
                  coalesce(dt.text_content, '') as text_content,
                  coalesce(dt.content_length, 0) as content_length,
                  a.family_id,
                  a.assignment_type
                from documents d
                left join sources s on s.id = d.source_id
                join lateral (
                  select *
                  from document_versions
                  where document_id = d.id
                  order by fetched_at desc
                  limit 1
                ) dv on true
                left join document_texts dt on dt.content_hash = dv.content_hash
                left join document_family_assignments a on a.document_id = d.id
                where d.id = :document_id
                """
            ),
            {"document_id": document_id},
        ).mappings().first()
        if not row:
            return None
        text_content = str(row["text_content"] or "")
        if not text_content.strip():
            return None

        discovered = DiscoveredDoc(
            source_code=str(row["source_code"] or "unknown"),
            title=str(row["title"]),
            source_url=str(row["source_url"]),
            issuing_body=row.get("issuing_body"),
            issue_date=row.get("issue_date"),
            issue_date_precision=row.get("issue_date_precision") or "unknown",
            doc_type=row.get("doc_type"),
            jurisdiction=row.get("jurisdiction"),
        )
        fetched = FetchedFile(
            discovered=discovered,
            file_hash=str(row["file_hash"] or row["content_hash"]),
            raw_file_path=str(row["raw_file_path"] or ""),
            http_status=int(row["http_status"] or 200),
        )
        extracted = ExtractedDoc(
            fetched=fetched,
            text=text_content,
            content_hash=str(row["content_hash"]),
            page_count=int(row["page_count"] or 0),
            needs_ocr=bool(row["needs_ocr"]),
            text_path=str(row["text_path"] or ""),
        )
        topics = _topic_tags(f"{discovered.title}\n{text_content}")
        summary = _summary_from_extracted(extracted)
        intelligence = assess_event_intelligence(
            extracted, topics=topics, summary=summary
        )
        summary = attach_intelligence_to_summary(summary, intelligence)
        return _DurableDocumentState(
            extracted=extracted,
            url=str(row["source_url"]),
            content_hash=str(row["content_hash"]),
            document_id=int(row["document_id"]),
            version_id=int(row["version_id"]) if row["version_id"] is not None else None,
            source_id=int(row["source_id"]) if row["source_id"] is not None else None,
            prior_reference=None,
            family_id=int(row["family_id"]) if row["family_id"] is not None else None,
            assignment_type=row.get("assignment_type"),
            had_prior_document=False,
            create_events=True,
            topics=topics,
            summary=summary,
            intelligence=intelligence,
        )


def _event_count_for_document(document_id: int) -> int:
    with session_scope() as session:
        return int(
            session.execute(
                text("select count(*) from events where document_id = :id"),
                {"id": document_id},
            ).scalar()
            or 0
        )


def _graph_status(document_id: int) -> str | None:
    with session_scope() as session:
        row = session.execute(
            text(
                """
                select status from regulatory_graph_extractions
                where document_id = :id
                """
            ),
            {"id": document_id},
        ).mappings().first()
        return str(row["status"]) if row else None


def _rag_snapshot(document_id: int) -> dict[str, Any]:
    with session_scope() as session:
        job = session.execute(
            text(
                """
                select status from rag_index_jobs
                where document_id = :id
                order by job_id desc
                limit 1
                """
            ),
            {"id": document_id},
        ).mappings().first()
        status = session.execute(
            text(
                """
                select status from document_rag_status
                where document_id = :id
                """
            ),
            {"id": document_id},
        ).mappings().first()
        return {
            "job_status": job["status"] if job else None,
            "rag_status": status["status"] if status else None,
        }

