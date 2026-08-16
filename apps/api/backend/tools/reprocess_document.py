"""Operator-only: reprocess one durable document through event generation.

Default is safe: you must pass exactly one of ``--dry-run`` or ``--execute``.

Dry-run evaluates classification, intelligence, and material-change gates with no
event / notification / RAG writes. Execute reuses ``_process_document_downstream``.

Examples::

  python -m backend.tools.reprocess_document --document-id 287 --dry-run
  python -m backend.tools.reprocess_document --document-id 287 --execute
"""

from __future__ import annotations

import argparse
import json
import sys

from backend.pipeline.reprocess_document import reprocess_document


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--document-id",
        type=int,
        required=True,
        help="Durable document ID to reprocess (required).",
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--dry-run",
        action="store_true",
        help=(
            "Read-only gate evaluation: classification, intelligence, material "
            "change. Does not insert events or enqueue notifications."
        ),
    )
    mode.add_argument(
        "--execute",
        action="store_true",
        help=(
            "Production operation for exactly one document: run Session B "
            "downstream (existing gates + event insert + notification enqueue)."
        ),
    )
    args = parser.parse_args(argv)
    result = reprocess_document(args.document_id, dry_run=bool(args.dry_run))
    print(json.dumps(result, indent=2, default=str))
    if result.get("status") == "FAILED":
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
