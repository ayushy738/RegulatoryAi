import asyncio
from datetime import date

from backend.core.logging import configure_logging, log_event
from backend.core.sample_data import SOURCES
from backend.pipeline.agent_scraper import scrape_source
from backend.pipeline.digest_builder import build_digest
from backend.pipeline.notifier import enqueue_notifications, send_pending_notifications


async def run_once() -> dict:
    configure_logging()
    docs_found = 0
    errors: list[dict] = []
    discovered = []
    log_event("run_started")

    for source in SOURCES:
        try:
            docs = await scrape_source(source)
            docs_found += len(docs)
            discovered.extend(docs)
            log_event("source_ok", source_code=source["code"], docs_found=len(docs))
        except Exception as exc:
            errors.append({"source": source["code"], "error": str(exc)})
            log_event("source_failed", source_code=source["code"], error=str(exc))

    digest = build_digest(date.today())
    new_event_ids = [event.id for event in digest.events]
    enqueue_notifications(new_event_ids)
    email_result = send_pending_notifications(digest.events)
    status = "success" if not errors else "partial"
    log_event("run_finished", status=status, docs_found=docs_found, new_events=len(new_event_ids))
    return {
        "status": status,
        "sources_attempted": len(SOURCES),
        "sources_succeeded": len(SOURCES) - len(errors),
        "docs_found": docs_found,
        "new_events": len(new_event_ids),
        "notification_message_id": email_result.message_id,
        "errors": errors,
    }


def main() -> None:
    result = asyncio.run(run_once())
    print(result)


if __name__ == "__main__":
    main()
