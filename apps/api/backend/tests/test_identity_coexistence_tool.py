from datetime import UTC, datetime

from backend.tools.identity_coexistence import _prometheus


def test_prometheus_metrics_include_every_required_signal() -> None:
    output = _prometheus(
        {
            "source_users": 5,
            "users_mirrored": 5,
            "pending_users": 0,
            "drift_count": 0,
            "trigger_failures": 0,
            "sync_failures": 0,
            "backfill_progress": 1,
            "last_reconciliation": datetime(2026, 7, 24, tzinfo=UTC),
        }
    )

    assert "identity_source_users 5" in output
    assert "identity_users_mirrored 5" in output
    assert "identity_pending_users 0" in output
    assert "identity_drift_count 0" in output
    assert "identity_trigger_failures_total 0" in output
    assert "identity_sync_failures_total 0" in output
    assert "identity_backfill_progress_ratio 1" in output
    assert "identity_last_reconciliation_timestamp_seconds" in output
