from __future__ import annotations

import argparse
import json

from backend.rag.indexing import (
    enqueue_existing_documents,
    process_pending_rag_jobs,
    requeue_processing_jobs,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Process pending Hybrid RAG index jobs.")
    parser.add_argument("--limit", type=int, default=25)
    parser.add_argument("--enqueue-existing", action="store_true")
    parser.add_argument("--requeue-processing", action="store_true")
    args = parser.parse_args()
    if args.enqueue_existing:
        queued = enqueue_existing_documents(limit=args.limit)
        print(json.dumps(queued, indent=2, default=str))
    if args.requeue_processing:
        requeued = requeue_processing_jobs(limit=args.limit)
        print(json.dumps(requeued, indent=2, default=str))
    result = process_pending_rag_jobs(limit=args.limit)
    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
