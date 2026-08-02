from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

from backend.ask.migration_rehearsal import (
    MINIMUM_REHEARSAL_MESSAGES,
    DatabasePreflight,
    DatasetProfile,
    MigrationRehearsalReport,
    ReconciliationReport,
    render_markdown_report,
    reset_disposable_rehearsal_database,
    run_volume_rehearsal,
    seed_rehearsal_dataset,
)
from backend.core.migrations import apply_pending_migrations
from backend.tests.ask_ai_postgres import POSTGRES_MARK
from backend.tools.ask_ai_migration_rehearsal import (
    _docker_observation_provider,
)

MIGRATIONS_DIRECTORY = Path(__file__).parents[1] / "migrations"


def _report() -> MigrationRehearsalReport:
    return MigrationRehearsalReport(
        report_version="1.0.0",
        started_at="2026-07-30T00:00:00+00:00",
        completed_at="2026-07-30T00:10:00+00:00",
        preflight=DatabasePreflight(
            database_version="PostgreSQL 16",
            migration_head="0024",
            message_count=MINIMUM_REHEARSAL_MESSAGES,
            legacy_pending_count=MINIMUM_REHEARSAL_MESSAGES,
            database_size_bytes=1,
            active_connections=1,
            max_connections=100,
            longest_transaction_seconds=0,
            replica_count=0,
            deadlocks=0,
        ),
        dataset=DatasetProfile(
            version="e1.7-v1",
            source_messages=MINIMUM_REHEARSAL_MESSAGES,
            owners=1_000,
            hot_owner_percent=10,
            hot_message_percent=70,
            artifact_owners=100,
            sections_per_artifact_run=4,
            claims_per_artifact_run=8,
            events_per_artifact_run=6,
        ),
        expand_duration_ms=1,
        backfill={
            "duration_ms": 10,
            "max_batch_duration_ms": 2,
        },
        validate_duration_ms=1,
        reconciliation=ReconciliationReport(
            source_business_hash="a" * 64,
            target_business_hash="a" * 64,
            eligible_source_count=MINIMUM_REHEARSAL_MESSAGES,
            backfilled_target_count=MINIMUM_REHEARSAL_MESSAGES,
            pending_count=0,
            ownership_mismatches=0,
            ordering_mismatches=0,
            lineage_mismatches=0,
            duplicate_scope_count=0,
            orphan_session_count=0,
            hash_match=True,
            count_match=True,
        ),
        rollback_compatible=True,
        deadlock_delta=0,
        approved_batch_size=1_000,
        approved_batch_pause_seconds=0.25,
        approved_max_batch_transaction_seconds=5,
        approved_lock_wait_peak_ms=2_000,
        observed_lock_wait_peak_ms=0,
        observed_replica_lag_peak_seconds=0,
        observed_database_cpu_peak_percent=10,
        acceptance_passed=True,
    )


def test_markdown_report_records_required_reconciliation_and_rollback() -> None:
    markdown = render_markdown_report(_report())

    assert "**Result:** PASS" in markdown
    assert "Source messages: 10,000,000" in markdown
    assert "Source SHA-256" in markdown
    assert "Target SHA-256" in markdown
    assert "Flag-off null/null legacy-write compatibility: True" in markdown
    assert "Contract remains a separate change" in markdown


def test_disposable_reset_is_fenced_by_host_and_database_name() -> None:
    remote = create_engine("postgresql+psycopg://user:pass@example.com/ask_rehearsal")
    wrong_name = create_engine("postgresql+psycopg://user:pass@localhost/production")

    with pytest.raises(ValueError, match="loopback"):
        reset_disposable_rehearsal_database(remote)
    with pytest.raises(ValueError, match="database name"):
        reset_disposable_rehearsal_database(wrong_name)


def test_failed_report_is_explicit() -> None:
    report = replace(_report(), acceptance_passed=False)

    assert "**Result:** FAIL" in render_markdown_report(report)
    assert "production migration is blocked" in render_markdown_report(report)


def test_docker_cpu_observation_uses_approved_five_minute_window(
    tmp_path: Path,
) -> None:
    log = tmp_path / "docker-cpu.log"
    log.write_text(
        "\n".join(["10.00%"] * 299 + ["95.00%"] + ["20.00%"] * 300),
        encoding="utf-8",
    )

    observe = _docker_observation_provider(
        log,
        replica_lag_peak_seconds=2.5,
        lock_wait_peak_ms=100,
    )

    cpu, lag, lock_wait = observe()

    assert cpu == pytest.approx((95 + 299 * 20) / 300)
    assert lag == 2.5
    assert lock_wait == 100


def test_docker_cpu_observation_requires_full_five_minute_window(
    tmp_path: Path,
) -> None:
    log = tmp_path / "docker-cpu.log"
    log.write_text("\n".join(["10.00%"] * 299), encoding="utf-8")

    observe = _docker_observation_provider(
        log,
        replica_lag_peak_seconds=0,
        lock_wait_peak_ms=0,
    )

    with pytest.raises(ValueError, match="five-minute"):
        observe()


@POSTGRES_MARK
def test_small_rehearsal_exercises_expand_backfill_validate_and_rollback(
    postgres_engine: Engine,
) -> None:
    assert apply_pending_migrations(
        postgres_engine,
        MIGRATIONS_DIRECTORY,
        through="0022",
    )[-1].version == "0022"
    dataset = seed_rehearsal_dataset(
        postgres_engine,
        message_count=200,
        owner_count=10,
        artifact_owner_count=2,
        enforce_minimum=False,
    )

    report = run_volume_rehearsal(
        postgres_engine,
        MIGRATIONS_DIRECTORY,
        dataset=dataset,
        observed_database_cpu_peak_percent=10,
        observed_replica_lag_peak_seconds=0,
        observed_lock_wait_peak_ms=0,
        batch_size=50,
        batch_pause_seconds=0,
        minimum_messages=200,
    )

    assert report.acceptance_passed is True, report.to_dict()
    assert report.backfill["status"] == "complete"
    assert report.backfill["batches_completed"] == 4
    assert report.expand_duration_ms >= 0
    assert report.reconciliation.eligible_source_count == 200
    assert report.reconciliation.backfilled_target_count == 200
    assert report.reconciliation.hash_match is True
    assert report.rollback_compatible is True
    assert report.deadlock_delta == 0
