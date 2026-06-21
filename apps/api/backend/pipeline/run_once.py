import asyncio
from datetime import date

from backend.core.logging import configure_logging, log_event
from backend.core.repository import (
    create_crawl_run,
    finalize_crawl_run,
    list_sources,
    persist_extracted_documents,
    record_discovery_audits,
    record_source_check,
)
from backend.pipeline.agent_scraper import scrape_source
from backend.pipeline.digest_builder import build_digest
from backend.pipeline.notifier import enqueue_notifications, send_pending_notifications
from backend.pipeline.primary_document import acquire_primary_documents


async def run_once() -> dict:
    configure_logging()
    docs_found = 0
    primary_docs_found = 0
    errors: list[dict] = []
    extracted_docs = []
    run_id = create_crawl_run()
    log_event("run_started")

    sources = [source for source in list_sources() if source.get("enabled", True)]
    if not sources:
        errors.append({"source": "pipeline", "error": "No enabled sources configured"})
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
            "sources_succeeded": 0,
            "docs_found": 0,
            "new_events": 0,
            "notification_message_id": None,
            "errors": errors,
        }
    for source in sources:
        try:
            docs = await scrape_source(source)
            docs_found += len(docs)
            primary_result = await acquire_primary_documents(docs)
            record_discovery_audits(run_id, primary_result.audits)
            primary_docs_found += len(primary_result.accepted)
            extracted_docs.extend(primary_result.accepted)
            record_source_check(source["code"], status=200, ok=True)
            log_event(
                "source_ok",
                source_code=source["code"],
                docs_found=len(docs),
                primary_docs_found=len(primary_result.accepted),
            )
        except Exception as exc:
            record_source_check(source["code"], status=None, ok=False)
            errors.append({"source": source["code"], "error": str(exc)})
            log_event("source_failed", source_code=source["code"], error=str(exc))

    new_event_ids = persist_extracted_documents(extracted_docs)
    digest = build_digest(date.today(), new_event_ids)
    enqueue_notifications(new_event_ids)
    email_result = send_pending_notifications(digest.events)
    status = "success" if not errors else "partial"
    finalize_crawl_run(
        run_id,
        status=status,
        sources_attempted=len(sources),
        sources_succeeded=len(sources) - len(errors),
        docs_found=docs_found,
        new_events=len(new_event_ids),
        errors=errors,
    )
    log_event("run_finished", status=status, docs_found=docs_found, new_events=len(new_event_ids))
    return {
        "status": status,
        "sources_attempted": len(sources),
        "sources_succeeded": len(sources) - len(errors),
        "docs_found": docs_found,
        "primary_docs_found": primary_docs_found,
        "new_events": len(new_event_ids),
        "notification_message_id": email_result.message_id,
        "errors": errors,
    }


def main() -> None:
    result = asyncio.run(run_once())
    print(result)


if __name__ == "__main__":
    main()
