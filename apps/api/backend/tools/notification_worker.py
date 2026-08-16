from __future__ import annotations

import argparse
import json
import logging
import time

from backend.core.logging import configure_logging, log_event
from backend.notifications.delivery import process_pending_notifications

logger = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Process pending regulatory update email notifications."
    )
    parser.add_argument("--limit", type=int, default=50)
    args = parser.parse_args()

    configure_logging()
    started = time.perf_counter()
    logger.info("[NOTIFICATION_WORKER] started limit=%s", args.limit)
    log_event("notification_worker_started", limit=args.limit)

    result = process_pending_notifications(limit=args.limit)
    duration_ms = max(0, int((time.perf_counter() - started) * 1000))
    logger.info(
        "[NOTIFICATION_WORKER] finished claimed=%s sent=%s failed=%s skipped=%s duration_ms=%s",
        result.get("claimed"),
        result.get("sent"),
        result.get("failed"),
        result.get("skipped"),
        duration_ms,
    )
    log_event(
        "notification_worker_finished",
        claimed=result.get("claimed"),
        sent=result.get("sent"),
        failed=result.get("failed"),
        skipped=result.get("skipped"),
        duration_ms=duration_ms,
    )
    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
