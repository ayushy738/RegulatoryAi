from __future__ import annotations

import argparse
import json
import logging
import time

from backend.core.logging import configure_logging, log_event
from backend.rag.indexing import (
    enqueue_existing_documents,
    process_pending_rag_jobs,
    requeue_processing_jobs,
)

logger = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(description="Process pending Hybrid RAG index jobs.")
    parser.add_argument("--limit", type=int, default=25)
    parser.add_argument("--enqueue-existing", action="store_true")
    parser.add_argument("--requeue-processing", action="store_true")
    args = parser.parse_args()

    configure_logging()
    started = time.perf_counter()
    logger.info(
        "[RAG_WORKER] started limit=%s enqueue_existing=%s requeue_processing=%s",
        args.limit,
        args.enqueue_existing,
        args.requeue_processing,
    )
    log_event(
        "rag_worker_started",
        limit=args.limit,
        enqueue_existing=args.enqueue_existing,
        requeue_processing=args.requeue_processing,
    )

    if args.enqueue_existing:
        queued = enqueue_existing_documents(limit=args.limit)
        logger.info("[RAG_WORKER] enqueue_existing queued=%s", queued.get("queued"))
        print(json.dumps(queued, indent=2, default=str))
    if args.requeue_processing:
        requeued = requeue_processing_jobs(limit=args.limit)
        logger.info("[RAG_WORKER] requeue_processing requeued=%s", requeued.get("requeued"))
        print(json.dumps(requeued, indent=2, default=str))

    logger.info("[RAG_WORKER] polling pending/failed jobs limit=%s", args.limit)
    result = process_pending_rag_jobs(limit=args.limit)
    duration_ms = max(0, int((time.perf_counter() - started) * 1000))
    logger.info(
        "[RAG_WORKER] finished processed=%s ready=%s failed=%s skipped=%s duration_ms=%s",
        result.get("processed"),
        result.get("ready"),
        result.get("failed"),
        result.get("skipped"),
        duration_ms,
    )
    log_event(
        "rag_worker_finished",
        processed=result.get("processed"),
        ready=result.get("ready"),
        failed=result.get("failed"),
        skipped=result.get("skipped"),
        duration_ms=duration_ms,
    )
    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
