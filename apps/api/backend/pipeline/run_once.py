import asyncio
from datetime import date

from backend.core.logging import configure_logging, log_event
from backend.core.models import DiscoveryAuditRecord
from backend.core.repository import (
    create_crawl_run,
    finalize_crawl_run,
    list_enabled_source_pages,
    load_checkpoint,
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


async def run_once() -> dict:
    return await run_crawl()


async def run_crawl(
    *,
    source_id: int | None = None,
    page_id: int | None = None,
) -> dict:
    configure_logging()
    docs_found = 0
    primary_docs_found = 0
    errors: list[dict] = []
    extracted_docs = []
    successful_page_docs: dict[int, list] = {}
    run_id = create_crawl_run()
    log_event("run_started")

    source_pages = list_enabled_source_pages(source_id=source_id, page_id=page_id)
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
        log_event("run_finished", status="failed", docs_found=0, new_events=0)
        return {
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
            docs = await scrape_source_page(page)
            docs_found += len(docs)
            primary_result = await acquire_primary_documents(docs)
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
                source_code=source_code,
                source_page_id=page["id"],
                error=str(exc),
            )

    new_event_ids = persist_extracted_documents(extracted_docs)
    checkpoints_advanced = 0
    for successful_page_id, docs in successful_page_docs.items():
        mark_source_page_crawled(successful_page_id)
        if docs:
            save_checkpoint(successful_page_id, docs[0], run_id=run_id)
            checkpoints_advanced += 1
    digest = build_digest(date.today(), new_event_ids)
    enqueue_notifications(new_event_ids)
    email_result = send_pending_notifications(digest.events)
    status = "success" if not errors else "partial"
    finalize_crawl_run(
        run_id,
        status=status,
        sources_attempted=len(attempted_source_ids),
        sources_succeeded=len(successful_source_ids),
        docs_found=docs_found,
        new_events=len(new_event_ids),
        errors=errors,
    )
    log_event("run_finished", status=status, docs_found=docs_found, new_events=len(new_event_ids))
    return {
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
