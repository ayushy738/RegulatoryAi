from __future__ import annotations

import argparse
import json

from backend.pipeline.graph_extraction_worker import retry_failed_graph_extractions


def main() -> None:
    parser = argparse.ArgumentParser(description="Retry failed regulatory graph extractions.")
    parser.add_argument("--limit", type=int, default=50, help="Maximum failed documents to retry.")
    parser.add_argument("--no-ai", action="store_true", help="Use deterministic extraction only.")
    args = parser.parse_args()

    result = retry_failed_graph_extractions(limit=args.limit, use_ai=not args.no_ai)
    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
