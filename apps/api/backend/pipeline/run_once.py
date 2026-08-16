import asyncio
import logging
import os
import time
from datetime import date

from backend.core.logging import configure_logging, log_event
from backend.core.models import DiscoveryAuditRecord
from backend.core.repository import (
    create_crawl_run,
    finalize_crawl_run,
    list_enabled_source_pages,
    load_checkpoint,
    mark_crawl_run_running,
    mark_source_page_crawled,
    persist_extracted_documents,
    record_discovery_audits,
    record_source_check,
    save_checkpoint,
)
from backend.pipeline.agent_scraper import scrape_source_page
from backend.pipeline.digest_builder import build_digest
from backend.pipeline.notifier import enqueue_notifications, send_pending_notifications
from backend.pipeline.primary_document import acquire_primary_documents
from backend.rag.indexing import drain_rag_jobs_after_crawl

logger = logging.getLogger(__name__)


def _crawl_worker_log(message: str, **fields: object) -> None:
    if os.environ.get("CRAWL_WORKER") != "1":
        return
    parts = " ".join(
        f"{key}={value}" for key, value in fields.items() if value is not None
    )
    line = f"[CRAWL_WORKER] {message}" + (f" {parts}" if parts else "")
    logger.info("%s", line)


def queue_crawl_run(
    *,
    source_id: int | None = None,
    page_id: int | None = None,
) -> dict:
    """Create exactly one queued crawl_run for an admin HTTP trigger.

    Does not execute crawl stages. The caller must dispatch the GitHub crawl
    worker (or another out-of-process executor) with the same scope.
    """

    configure_logging()
    run_id = create_crawl_run()
    if run_id is None:
        raise RuntimeError("Failed to create crawl_run")
    log_event(
        "crawl_triggered",
        run_id=run_id,
        source_id=source_id,
        page_id=page_id,
        mode="queued_dispatch",
        status="queued",
    )
    return _queued_trigger_response(run_id)


async def run_crawl(
    *,
    source_id: int | None = None,
    page_id: int | None = None,
) -> dict:
    """CLI/cron path: create one run and execute it to a terminal state inline."""

    configure_logging()
    run_id = create_crawl_run()
    if run_id is None:
        raise RuntimeError("Failed to create crawl_run")
    log_event(
        "crawl_triggered",
        run_id=run_id,
        source_id=source_id,
        page_id=page_id,
        mode="inline",
        status="queued",
    )
    return await execute_crawl_run(run_id, source_id=source_id, page_id=page_id)


async def execute_crawl_run(
    run_id: int,
    *,
    source_id: int | None = None,
    page_id: int | None = None,
) -> dict:
    """Own the lifecycle for an existing crawl_run.

    Marks the run running, executes existing stages, and always finalizes on
    BaseException (including CancelledError) before re-raising.
    """

    configure_logging()
    started = time.perf_counter()
    log_event(
        "crawl_background_started",
        run_id=run_id,
        source_id=source_id,
        page_id=page_id,
        status="running",
    )
    # No-op when a worker already claimed via claim_queued_crawl_run.
    mark_crawl_run_running(run_id)
    _crawl_worker_log(
        "discovery_started",
        run_id=run_id,
        source_id=source_id,
        page_id=page_id,
    )
    try:
        result = await _run_crawl_stages(run_id, source_id=source_id, page_id=page_id)
        _crawl_worker_log(
            "finalized",
            run_id=run_id,
            status=result.get("status"),
        )
        log_event(
            "crawl_background_finished",
            run_id=run_id,
            source_id=source_id,
            page_id=page_id,
            status=result.get("status"),
            duration_ms=int((time.perf_counter() - started) * 1000),
        )
        return result
    except BaseException as exc:
        # Includes CancelledError: background execution must still finalize the
        # crawl_runs row so it cannot remain stuck in queued/running.
        _finalize_abandoned_run(run_id, exc)
        _crawl_worker_log(
            "failed",
            run_id=run_id,
            error=f"{type(exc).__name__}: {exc}",
        )
        log_event(
            "crawl_background_failed",
            run_id=run_id,
            source_id=source_id,
            page_id=page_id,
            status="failed",
            error=f"{type(exc).__name__}: {exc}",
            duration_ms=int((time.perf_counter() - started) * 1000),
        )
        raise


async def run_once() -> dict:
    return await run_crawl()


def _finalize_abandoned_run(run_id: int | None, exc: BaseException) -> None:
    error = {
        "source": "pipeline",
        "error": f"{type(exc).__name__}: {exc}",
        "error_code": "crawl_run_abandoned_exception",
    }
    docs_found = 0
    new_events = 0
    sources_attempted = 0
    if run_id is not None:
        try:
            from backend.core.db import session_scope
            from sqlalchemy import text

            with session_scope() as session:
                stats = session.execute(
                    text(
                        """
                        select
                          (select count(*)::int from discovery_audit
                           where run_id = :run_id) as docs_found,
                          (select count(distinct source_code)::int from discovery_audit
                           where run_id = :run_id) as sources_attempted,
                          (select count(distinct e.id)::int
                           from discovery_audit da
                           join document_versions dv on dv.content_hash = da.content_hash
                           join events e on e.document_id = dv.document_id
                           where da.run_id = :run_id and da.content_hash is not null
                          ) as new_events
                        """
                    ),
                    {"run_id": run_id},
                ).mappings().first()
                if stats:
                    docs_found = int(stats["docs_found"] or 0)
                    sources_attempted = int(stats["sources_attempted"] or 0)
                    new_events = int(stats["new_events"] or 0)
        except Exception:
            pass
    try:
        finalize_crawl_run(
            run_id,
            status="failed",
            sources_attempted=sources_attempted,
            sources_succeeded=1 if docs_found else 0,
            docs_found=docs_found,
            new_events=new_events,
            errors=[error],
        )
    except Exception as finalize_error:
        log_event(
            "run_finalize_failed",
            run_id=run_id,
            error=f"{type(finalize_error).__name__}: {finalize_error}",
        )
    log_event(
        "run_finished",
        run_id=run_id,
        status="failed",
        abandoned=True,
        error=error["error"],
    )


async def _run_crawl_stages(
    run_id: int | None,
    *,
    source_id: int | None = None,
    page_id: int | None = None,
) -> dict:
    docs_found = 0
    primary_docs_found = 0
    errors: list[dict] = []
    extracted_docs = []
    successful_page_docs: dict[int, list] = {}

    log_event(
        "crawl_stage_started",
        run_id=run_id,
        source_id=source_id,
        page_id=page_id,
        crawl_stage="source_selection",
    )
    source_pages = list_enabled_source_pages(source_id=source_id, page_id=page_id)
    log_event(
        "crawl_stage_finished",
        run_id=run_id,
        source_id=source_id,
        page_id=page_id,
        crawl_stage="source_selection",
        source_pages=len(source_pages),
    )
    log_event(
        "source_pages_loaded",
        run_id=run_id,
        source_pages=len(source_pages),
        source_id=source_id,
        source_page_id=page_id,
    )
    if not source_pages:
        errors.append({"source": "pipeline", "error": "No enabled source pages configured"})
        finalize_crawl_run(
            run_id,
            status="failed",
            sources_attempted=0,
            sources_succeeded=0,
            docs_found=0,
            new_events=0,
            errors=errors,
        )
        log_event(
            "run_finished",
            run_id=run_id,
            status="failed",
            docs_found=0,
            new_events=0,
        )
        return {
            "run_id": run_id,
            "status": "failed",
            "sources_attempted": 0,
            "pages_attempted": 0,
            "sources_succeeded": 0,
            "pages_succeeded": 0,
            "docs_found": 0,
            "primary_docs_found": 0,
            "new_events": 0,
            "checkpoints_advanced": 0,
            "notification_message_id": None,
            "errors": errors,
        }
    successful_pages = 0
    successful_source_ids: set[int] = set()
    attempted_source_ids = {int(page["source_id"]) for page in source_pages}
    for page in source_pages:
        source_code = page["source_code"]
        page_id_int = int(page["id"])
        try:
            page = {**page, "checkpoint": load_checkpoint(page_id_int)}
            log_event(
                "crawl_stage_started",
                run_id=run_id,
                source_id=source_id,
                page_id=page_id_int,
                crawl_stage="discovery",
                source_code=source_code,
            )
            log_event(
                "crawl_discovery_started",
                run_id=run_id,
                source_code=source_code,
                source_page_id=page_id_int,
                source_page=page["name"],
            )
            docs = await scrape_source_page(page)
            log_event(
                "crawl_discovery_finished",
                run_id=run_id,
                source_code=source_code,
                source_page_id=page_id_int,
                docs_found=len(docs),
            )
            log_event(
                "crawl_stage_finished",
                run_id=run_id,
                source_id=source_id,
                page_id=page_id_int,
                crawl_stage="discovery",
                source_code=source_code,
                docs_found=len(docs),
            )
            docs_found += len(docs)
            log_event(
                "crawl_stage_started",
                run_id=run_id,
                source_id=source_id,
                page_id=page_id_int,
                crawl_stage="primary_document_acquisition",
                source_code=source_code,
            )
            log_event(
                "primary_document_acquisition_started",
                run_id=run_id,
                source_code=source_code,
                source_page_id=page_id_int,
                docs_found=len(docs),
            )
            primary_result = await acquire_primary_documents(docs)
            log_event(
                "primary_document_acquisition_finished",
                run_id=run_id,
                source_code=source_code,
                source_page_id=page_id_int,
                primary_docs_found=len(primary_result.accepted),
                audits=len(primary_result.audits),
            )
            log_event(
                "crawl_stage_finished",
                run_id=run_id,
                source_id=source_id,
                page_id=page_id_int,
                crawl_stage="primary_document_acquisition",
                source_code=source_code,
                primary_docs_found=len(primary_result.accepted),
            )
            audits = _with_source_page_metadata(primary_result.audits, page)
            if not docs:
                audits.append(_no_primary_document_audit(page))
            record_discovery_audits(run_id, audits)
            primary_docs_found += len(primary_result.accepted)
            extracted_docs.extend(primary_result.accepted)
            successful_page_docs[page_id_int] = docs
            record_source_check(source_code, status=200, ok=True)
            successful_pages += 1
            successful_source_ids.add(int(page["source_id"]))
            log_event(
                "source_page_ok",
                run_id=run_id,
                source_code=source_code,
                source_page_id=page["id"],
                docs_found=len(docs),
                primary_docs_found=len(primary_result.accepted),
            )
        except Exception as exc:
            record_source_check(source_code, status=None, ok=False)
            errors.append(
                {
                    "source": source_code,
                    "source_page_id": page["id"],
                    "source_page": page["name"],
                    "error": str(exc),
                }
            )
            log_event(
                "source_page_failed",
                run_id=run_id,
                source_code=source_code,
                source_page_id=page["id"],
                error=str(exc),
            )

    log_event(
        "crawl_stage_started",
        run_id=run_id,
        source_id=source_id,
        page_id=page_id,
        crawl_stage="document_persistence",
        extracted_docs=len(extracted_docs),
    )
    log_event(
        "document_persistence_started",
        run_id=run_id,
        extracted_docs=len(extracted_docs),
    )
    _crawl_worker_log(
        "persistence_started",
        run_id=run_id,
        extracted_docs=len(extracted_docs),
    )
    _crawl_worker_log("graph_started", run_id=run_id, extracted_docs=len(extracted_docs))
    new_event_ids = persist_extracted_documents(extracted_docs)
    log_event(
        "document_persistence_finished",
        run_id=run_id,
        extracted_docs=len(extracted_docs),
        new_events=len(new_event_ids),
    )
    _crawl_worker_log(
        "session_a_committed",
        run_id=run_id,
        extracted_docs=len(extracted_docs),
    )
    _crawl_worker_log(
        "graph_completed",
        run_id=run_id,
        new_events=len(new_event_ids),
    )
    _crawl_worker_log("rag_enqueued", run_id=run_id, extracted_docs=len(extracted_docs))
    log_event(
        "crawl_stage_finished",
        run_id=run_id,
        source_id=source_id,
        page_id=page_id,
        crawl_stage="document_persistence",
        new_events=len(new_event_ids),
    )
    # RAG indexing is enqueued during Session B. Draining is owned by the
    # separate GitHub RAG Action unless explicitly re-enabled.
    from backend.core.config import settings as _settings

    log_event(
        "crawl_stage_started",
        run_id=run_id,
        source_id=source_id,
        page_id=page_id,
        crawl_stage="rag_indexing",
        extracted_docs=len(extracted_docs),
    )
    rag_drain = None
    if getattr(_settings, "crawl_drain_rag_after_persist", False):
        rag_drain = drain_rag_jobs_after_crawl(
            extracted_document_count=len(extracted_docs),
            run_id=run_id,
        )
    else:
        log_event(
            "crawl_rag_drain_skipped",
            run_id=run_id,
            extracted_docs=len(extracted_docs),
            reason="independent_rag_worker",
        )
    log_event(
        "crawl_stage_finished",
        run_id=run_id,
        source_id=source_id,
        page_id=page_id,
        crawl_stage="rag_indexing",
        rag_processed=(rag_drain or {}).get("processed", 0),
        rag_ready=(rag_drain or {}).get("ready", 0),
        rag_failed=(rag_drain or {}).get("failed", 0),
        rag_drain_skipped=rag_drain is None,
    )
    checkpoints_advanced = 0
    log_event(
        "crawl_stage_started",
        run_id=run_id,
        source_id=source_id,
        page_id=page_id,
        crawl_stage="checkpoint_update",
        successful_pages=len(successful_page_docs),
    )
    log_event(
        "checkpoint_update_started",
        run_id=run_id,
        successful_pages=len(successful_page_docs),
    )
    for successful_page_id, docs in successful_page_docs.items():
        mark_source_page_crawled(successful_page_id)
        if docs:
            save_checkpoint(successful_page_id, docs[0], run_id=run_id)
            checkpoints_advanced += 1
    log_event(
        "checkpoint_update_finished",
        run_id=run_id,
        checkpoints_advanced=checkpoints_advanced,
    )
    log_event(
        "crawl_stage_finished",
        run_id=run_id,
        source_id=source_id,
        page_id=page_id,
        crawl_stage="checkpoint_update",
        checkpoints_advanced=checkpoints_advanced,
    )
    log_event(
        "crawl_stage_started",
        run_id=run_id,
        source_id=source_id,
        page_id=page_id,
        crawl_stage="notifications",
        new_events=len(new_event_ids),
    )
    log_event("digest_build_started", run_id=run_id, new_events=len(new_event_ids))
    digest = build_digest(date.today(), new_event_ids)
    log_event("digest_build_finished", run_id=run_id, digest_events=len(digest.events))
    log_event("notification_enqueue_started", run_id=run_id, new_events=len(new_event_ids))
    enqueue_notifications(new_event_ids)
    log_event("notification_enqueue_finished", run_id=run_id, new_events=len(new_event_ids))
    log_event(
        "notification_delivery_started",
        run_id=run_id,
        digest_events=len(digest.events),
    )
    email_result = send_pending_notifications(digest.events)
    log_event(
        "notification_delivery_finished",
        run_id=run_id,
        digest_events=len(digest.events),
        notification_message_id=email_result.message_id,
    )
    log_event(
        "crawl_stage_finished",
        run_id=run_id,
        source_id=source_id,
        page_id=page_id,
        crawl_stage="notifications",
        digest_events=len(digest.events),
    )
    status = "success" if not errors else "partial"
    _crawl_worker_log("finalize_started", run_id=run_id, status=status)
    finalize_crawl_run(
        run_id,
        status=status,
        sources_attempted=len(attempted_source_ids),
        sources_succeeded=len(successful_source_ids),
        docs_found=docs_found,
        new_events=len(new_event_ids),
        errors=errors,
    )
    _crawl_worker_log("finalized", run_id=run_id, status=status)
    log_event(
        "run_finished",
        run_id=run_id,
        status=status,
        docs_found=docs_found,
        new_events=len(new_event_ids),
    )
    return {
        "run_id": run_id,
        "status": status,
        "sources_attempted": len(attempted_source_ids),
        "pages_attempted": len(source_pages),
        "sources_succeeded": len(successful_source_ids),
        "pages_succeeded": successful_pages,
        "docs_found": docs_found,
        "primary_docs_found": primary_docs_found,
        "new_events": len(new_event_ids),
        "checkpoints_advanced": checkpoints_advanced,
        "notification_message_id": email_result.message_id,
        "errors": errors,
    }


def _queued_trigger_response(run_id: int) -> dict:
    return {
        "run_id": run_id,
        "status": "queued",
        "sources_attempted": 0,
        "pages_attempted": 0,
        "sources_succeeded": 0,
        "pages_succeeded": 0,
        "docs_found": 0,
        "primary_docs_found": 0,
        "new_events": 0,
        "checkpoints_advanced": 0,
        "notification_message_id": None,
        "errors": [],
    }


def _with_source_page_metadata(
    audits: list[DiscoveryAuditRecord],
    page: dict,
) -> list[DiscoveryAuditRecord]:
    for audit in audits:
        audit.metadata = {
            **(audit.metadata or {}),
            "source_page_id": page["id"],
            "source_page_name": page["name"],
            "source_page_type": page["page_type"],
        }
    return audits


def _no_primary_document_audit(page: dict) -> DiscoveryAuditRecord:
    return DiscoveryAuditRecord(
        source_code=page["source_code"],
        source_url=page["url"],
        title=page["name"],
        classification="LISTING_PAGE",
        is_valid_event_source=False,
        confidence=1.0,
        reason_code="NO_PRIMARY_DOCUMENT",
        metadata={
            "source_page_id": page["id"],
            "source_page_name": page["name"],
            "source_page_type": page["page_type"],
            "explanation": "Curated source page produced no primary PDF or primary HTML notice.",
        },
    )


def main() -> None:
    result = asyncio.run(run_once())
    print(result)


if __name__ == "__main__":
    main()
