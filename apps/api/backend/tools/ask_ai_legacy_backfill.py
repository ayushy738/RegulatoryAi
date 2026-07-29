from __future__ import annotations

import argparse
import json
from typing import Any

from backend.ask.backfill import (
    DEFAULT_BATCH_SIZE,
    LegacyBackfillDriftError,
    preflight_backfill_validation,
    preview_backfill,
    run_backfill,
    verify_backfill,
)
from backend.core.db import get_engine


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Dry-run, execute, or verify the Ask AI legacy session backfill."
    )
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("dry-run", help="Report expected changes without writing.")

    run = commands.add_parser(
        "run",
        help="Backfill legacy message identities in bounded committed batches.",
    )
    run.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE)
    run.add_argument(
        "--max-batches",
        type=int,
        help="Stop after this many committed batches; rerun to resume.",
    )

    verify = commands.add_parser(
        "verify",
        help="Reconcile identity, session grouping, ownership, and pending counts.",
    )
    verify.add_argument(
        "--fail-on-drift",
        action="store_true",
        help="Exit with status 2 when verification is incomplete or inconsistent.",
    )
    commands.add_parser(
        "preflight",
        help="Require a clean backfill before migration 0025 validation.",
    )
    return parser


def _print_report(report: dict[str, Any]) -> None:
    print(json.dumps(report, sort_keys=True))


def main() -> None:
    args = _parser().parse_args()
    engine = get_engine()
    try:
        if args.command == "dry-run":
            _print_report(preview_backfill(engine).to_dict())
            return
        if args.command == "run":
            result = run_backfill(
                engine,
                batch_size=args.batch_size,
                max_batches=args.max_batches,
            )
            _print_report(result.to_dict())
            if result.status == "failed":
                raise SystemExit(2)
            return
        if args.command == "preflight":
            preflight = preflight_backfill_validation(engine)
            _print_report(preflight.to_dict())
            if not preflight.is_ready:
                raise SystemExit(2)
            return

        verification = verify_backfill(engine)
        _print_report(verification.to_dict())
        if args.fail_on_drift and not verification.is_valid:
            raise SystemExit(2)
    except (LegacyBackfillDriftError, ValueError) as exc:
        raise SystemExit(f"Backfill refused: {exc}") from exc
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
