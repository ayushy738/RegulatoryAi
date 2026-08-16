"""GitHub Actions / local crawl worker entrypoint.

Claims a queued crawl_run atomically, then runs the existing
``execute_crawl_run`` pipeline (Session A / Session B / RAG enqueue / finalize).

Does NOT call the Render admin crawl HTTP endpoint.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
from typing import Any

from backend.core.logging import configure_logging, log_event
from backend.core.repository import claim_queued_crawl_run
from backend.pipeline.run_once import execute_crawl_run

logger = logging.getLogger(__name__)


def _worker_log(message: str, **fields: Any) -> None:
    parts = " ".join(f"{key}={value}" for key, value in fields.items() if value is not None)
    line = f"[CRAWL_WORKER] {message}" + (f" {parts}" if parts else "")
    logger.info("%s", line)
    log_event(f"crawl_worker_{message}", **fields)


def _parse_optional_int(raw: str | None) -> int | None:
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None
    return int(text)


def run_claimed_crawl(
    *,
    run_id: int,
    source_id: int | None,
    page_id: int | None,
) -> dict[str, Any]:
    """Claim ``run_id`` then execute the existing crawler with the given scope."""

    os.environ["CRAWL_WORKER"] = "1"
    _worker_log("received", run_id=run_id, source_id=source_id, page_id=page_id)

    if source_id is not None and page_id is not None:
        raise ValueError("Provide at most one of source_id or page_id")
    if source_id is None and page_id is None:
        raise ValueError("Crawl worker requires source_id or page_id scope")

    _worker_log("claim_attempt", run_id=run_id)
    claimed = claim_queued_crawl_run(run_id)
    if not claimed:
        _worker_log(
            "claim_failed",
            run_id=run_id,
            reason="not_queued_or_locked",
        )
        raise RuntimeError(
            f"Failed to claim crawl_run {run_id}: not queued or already claimed"
        )
    _worker_log("claimed", run_id=run_id)

    # execute_crawl_run marks running again (no-op when already running) and
    # owns finalize on BaseException including CancelledError.
    result = asyncio.run(
        execute_crawl_run(run_id, source_id=source_id, page_id=page_id)
    )
    _worker_log(
        "finalized",
        run_id=run_id,
        status=result.get("status"),
        docs_found=result.get("docs_found"),
        new_events=result.get("new_events"),
    )
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Claim and execute one queued crawl_run.")
    parser.add_argument("--run-id", type=int, required=True)
    parser.add_argument("--source-id", type=str, default="")
    parser.add_argument("--page-id", type=str, default="")
    args = parser.parse_args(argv)

    configure_logging()
    source_id = _parse_optional_int(args.source_id)
    page_id = _parse_optional_int(args.page_id)

    try:
        run_claimed_crawl(run_id=args.run_id, source_id=source_id, page_id=page_id)
    except Exception as exc:
        _worker_log(
            "failed",
            run_id=args.run_id,
            source_id=source_id,
            page_id=page_id,
            error=f"{type(exc).__name__}: {exc}",
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
