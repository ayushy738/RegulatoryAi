"""CLI for abandoned crawl-run reclaim and incomplete document downstream retry.

Examples (do not run against production without approval)::

  python -m backend.tools.crawl_recovery reclaim-runs
  python -m backend.tools.crawl_recovery reclaim-runs --run-id 58 --force
  python -m backend.tools.crawl_recovery retry-document --document-id 274
  python -m backend.tools.crawl_recovery repair-run --run-id 58 --document-id 274 --force
"""

from __future__ import annotations

import argparse
import json

from backend.pipeline.crawl_recovery import (
    reclaim_stale_crawl_runs,
    retry_incomplete_document_downstream,
    retry_incomplete_documents,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    reclaim = sub.add_parser("reclaim-runs", help="Finalize stale RUNNING crawl_runs as FAILED")
    reclaim.add_argument("--stale-seconds", type=int, default=None)
    reclaim.add_argument("--run-id", type=int, default=None)
    reclaim.add_argument(
        "--force",
        action="store_true",
        help="With --run-id, skip the age gate (explicit operator repair).",
    )

    retry = sub.add_parser(
        "retry-document",
        help="Retry graph/RAG/events for a durable document missing Session B work",
    )
    retry.add_argument("--document-id", type=int, required=True)
    retry.add_argument("--no-ai", action="store_true")

    retry_many = sub.add_parser(
        "retry-incomplete",
        help="Retry a batch of durable documents with incomplete graph downstream",
    )
    retry_many.add_argument("--limit", type=int, default=50)
    retry_many.add_argument("--no-ai", action="store_true")

    repair = sub.add_parser(
        "repair-run",
        help="Reclaim one abandoned run and optionally retry one document",
    )
    repair.add_argument("--run-id", type=int, required=True)
    repair.add_argument("--document-id", type=int, default=None)
    repair.add_argument("--force", action="store_true")
    repair.add_argument("--no-ai", action="store_true")

    args = parser.parse_args()
    if args.command == "reclaim-runs":
        result = reclaim_stale_crawl_runs(
            stale_seconds=args.stale_seconds,
            run_id=args.run_id,
            force=args.force,
        )
    elif args.command == "retry-document":
        result = retry_incomplete_document_downstream(
            args.document_id,
            use_ai=not args.no_ai,
        )
    elif args.command == "retry-incomplete":
        result = retry_incomplete_documents(limit=args.limit, use_ai=not args.no_ai)
    elif args.command == "repair-run":
        result = {
            "reclaim": reclaim_stale_crawl_runs(
                run_id=args.run_id,
                force=args.force,
            ),
        }
        if args.document_id is not None:
            result["document"] = retry_incomplete_document_downstream(
                args.document_id,
                use_ai=not args.no_ai,
            )
    else:
        raise SystemExit(f"Unknown command: {args.command}")

    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
