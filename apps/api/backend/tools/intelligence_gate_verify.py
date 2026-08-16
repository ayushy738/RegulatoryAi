"""Read-only CLI: re-assess intelligence gate for a stored document.

Does not write to the database. Does not create events, notifications, or RAG jobs.

Examples::

  python -m backend.tools.intelligence_gate_verify --document-id 287
  python -m backend.tools.intelligence_gate_verify --document-id 287 289
"""

from __future__ import annotations

import argparse
import json

from backend.pipeline.intelligence_gate_verify import diagnose_document_intelligence


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--document-id",
        type=int,
        nargs="+",
        required=True,
        help="One or more durable document IDs to diagnose (read-only).",
    )
    args = parser.parse_args()
    results = [diagnose_document_intelligence(doc_id) for doc_id in args.document_id]
    payload = results[0] if len(results) == 1 else results
    print(json.dumps(payload, indent=2, default=str))


if __name__ == "__main__":
    main()
