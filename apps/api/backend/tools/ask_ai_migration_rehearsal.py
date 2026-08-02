from __future__ import annotations

import argparse
import json
import re
from dataclasses import asdict
from pathlib import Path

from backend.ask.migration_rehearsal import (
    DEFAULT_ARTIFACT_OWNERS,
    DEFAULT_REHEARSAL_OWNERS,
    MINIMUM_REHEARSAL_MESSAGES,
    DatasetProfile,
    render_markdown_report,
    reset_disposable_rehearsal_database,
    run_volume_rehearsal,
    seed_rehearsal_dataset,
)
from backend.core.db import get_engine
from backend.core.migrations import apply_pending_migrations

MIGRATIONS_DIRECTORY = Path(__file__).resolve().parents[1] / "migrations"
RESET_ACKNOWLEDGEMENT = "disposable-local-rehearsal-database"
DOCKER_STATS_SAMPLE_INTERVAL_SECONDS = 1
DATABASE_CPU_WINDOW_SECONDS = 5 * 60


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Prepare and execute the B-010 Ask AI migration rehearsal."
    )
    commands = parser.add_subparsers(dest="command", required=True)

    prepare = commands.add_parser(
        "prepare",
        help="Reset a fenced local database, apply through 0024, and seed volume.",
    )
    prepare.add_argument(
        "--messages",
        type=int,
        default=MINIMUM_REHEARSAL_MESSAGES,
    )
    prepare.add_argument("--owners", type=int, default=DEFAULT_REHEARSAL_OWNERS)
    prepare.add_argument(
        "--artifact-owners",
        type=int,
        default=DEFAULT_ARTIFACT_OWNERS,
    )
    prepare.add_argument("--acknowledge", required=True)

    run = commands.add_parser(
        "run",
        help="Backfill, validate, reconcile, and emit the signed-off report inputs.",
    )
    run.add_argument(
        "--messages",
        type=int,
        default=MINIMUM_REHEARSAL_MESSAGES,
    )
    run.add_argument("--owners", type=int, default=DEFAULT_REHEARSAL_OWNERS)
    run.add_argument(
        "--artifact-owners",
        type=int,
        default=DEFAULT_ARTIFACT_OWNERS,
    )
    cpu_source = run.add_mutually_exclusive_group(required=True)
    cpu_source.add_argument("--database-cpu-peak-percent", type=float)
    cpu_source.add_argument(
        "--docker-stats-log",
        type=Path,
        help="Local-rehearsal Docker CPU samples, one percentage per line.",
    )
    run.add_argument("--replica-lag-peak-seconds", type=float, required=True)
    run.add_argument("--lock-wait-peak-ms", type=int, required=True)
    run.add_argument("--report-json", type=Path, required=True)
    run.add_argument("--report-markdown", type=Path, required=True)
    return parser


def _dataset(args: argparse.Namespace) -> DatasetProfile:
    return DatasetProfile(
        version="e1.7-v1",
        source_messages=args.messages,
        owners=args.owners,
        hot_owner_percent=10,
        hot_message_percent=70,
        artifact_owners=args.artifact_owners,
        sections_per_artifact_run=4,
        claims_per_artifact_run=8,
        events_per_artifact_run=6,
    )


def _docker_observation_provider(
    path: Path,
    *,
    replica_lag_peak_seconds: float,
    lock_wait_peak_ms: int,
):
    def observe() -> tuple[float, float, int]:
        samples = [
            float(match)
            for match in re.findall(
                r"([0-9]+(?:\.[0-9]+)?)%",
                path.read_text(encoding="utf-8"),
            )
        ]
        if not samples:
            raise ValueError("Docker statistics log contains no CPU samples")
        window_size = (
            DATABASE_CPU_WINDOW_SECONDS // DOCKER_STATS_SAMPLE_INTERVAL_SECONDS
        )
        if len(samples) < window_size:
            raise ValueError(
                "Docker statistics log does not contain a five-minute CPU window"
            )
        window_total = sum(samples[:window_size])
        five_minute_peak = window_total / window_size
        for index in range(window_size, len(samples)):
            window_total += samples[index] - samples[index - window_size]
            five_minute_peak = max(
                five_minute_peak,
                window_total / window_size,
            )
        return (
            five_minute_peak,
            replica_lag_peak_seconds,
            lock_wait_peak_ms,
        )

    return observe


def main() -> None:
    args = _parser().parse_args()
    engine = get_engine()
    try:
        if args.command == "prepare":
            if args.acknowledge != RESET_ACKNOWLEDGEMENT:
                raise SystemExit("Rehearsal prepare refused: invalid acknowledgement")
            reset_disposable_rehearsal_database(engine)
            applied = apply_pending_migrations(
                engine,
                MIGRATIONS_DIRECTORY,
                through="0022",
            )
            if not applied or applied[-1].version != "0022":
                raise SystemExit("Rehearsal prepare refused: migration head is not 0022")
            profile = seed_rehearsal_dataset(
                engine,
                message_count=args.messages,
                owner_count=args.owners,
                artifact_owner_count=args.artifact_owners,
            )
            print(json.dumps(asdict(profile), sort_keys=True))
            return

        observation_provider = None
        database_cpu_peak_percent = args.database_cpu_peak_percent or 0.0
        if args.docker_stats_log is not None:
            observation_provider = _docker_observation_provider(
                args.docker_stats_log,
                replica_lag_peak_seconds=args.replica_lag_peak_seconds,
                lock_wait_peak_ms=args.lock_wait_peak_ms,
            )
        report = run_volume_rehearsal(
            engine,
            MIGRATIONS_DIRECTORY,
            dataset=_dataset(args),
            observed_database_cpu_peak_percent=database_cpu_peak_percent,
            observed_replica_lag_peak_seconds=args.replica_lag_peak_seconds,
            observed_lock_wait_peak_ms=args.lock_wait_peak_ms,
            operational_observation_provider=observation_provider,
        )
        args.report_json.parent.mkdir(parents=True, exist_ok=True)
        args.report_markdown.parent.mkdir(parents=True, exist_ok=True)
        args.report_json.write_text(
            json.dumps(report.to_dict(), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        args.report_markdown.write_text(
            render_markdown_report(report),
            encoding="utf-8",
        )
        print(json.dumps(report.to_dict(), sort_keys=True))
        if not report.acceptance_passed:
            raise SystemExit(2)
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
