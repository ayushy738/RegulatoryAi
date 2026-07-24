from __future__ import annotations

import argparse
import json
from datetime import datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError

from backend.core.db import get_engine

START_RUN_SQL = """
insert into identity.coexistence_runs (run_type, status, metadata)
values (:run_type, 'running', cast(:metadata as jsonb))
returning id
"""

COMPLETE_BACKFILL_SQL = """
update identity.coexistence_runs
set
  status = 'succeeded',
  finished_at = clock_timestamp(),
  users_seen = :users_seen,
  users_changed = :users_changed,
  profiles_seen = :profiles_seen,
  profiles_changed = :profiles_changed,
  roles_changed = :roles_changed
where id = :run_id
"""

COMPLETE_RECONCILIATION_SQL = """
update identity.coexistence_runs
set
  status = 'succeeded',
  finished_at = clock_timestamp(),
  drift_count = :drift_count
where id = :run_id
"""

RECORD_FAILURE_SQL = """
insert into identity.coexistence_runs (
  run_type,
  status,
  finished_at,
  error_code,
  error_message,
  metadata
)
values (
  :run_type,
  'failed',
  clock_timestamp(),
  :error_code,
  :error_message,
  cast(:metadata as jsonb)
)
returning id
"""

DRIFT_SQL = """
select drift_type, user_id, source_value, mirror_value
from identity.coexistence_drift
order by drift_type, user_id
"""

METRICS_SQL = "select * from identity.coexistence_metrics"


def _json_default(value: Any) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _error_code(exc: BaseException) -> str:
    if isinstance(exc, SQLAlchemyError) and exc.orig is not None:
        sqlstate = getattr(exc.orig, "sqlstate", None)
        if sqlstate:
            return str(sqlstate)[:100]
    return type(exc).__name__[:100]


def record_failure(
    engine: Engine,
    *,
    run_type: str,
    error_code: str,
    error_message: str,
    metadata: dict[str, Any] | None = None,
) -> str:
    with engine.begin() as connection:
        run_id = connection.execute(
            text(RECORD_FAILURE_SQL),
            {
                "run_type": run_type,
                "error_code": error_code[:100],
                "error_message": error_message[:2000],
                "metadata": json.dumps(metadata or {}),
            },
        ).scalar_one()
    return str(run_id)


def run_backfill(engine: Engine) -> dict[str, Any]:
    try:
        with engine.begin() as connection:
            run_id = connection.execute(
                text(START_RUN_SQL),
                {
                    "run_type": "backfill",
                    "metadata": json.dumps({"source": "operator"}),
                },
            ).scalar_one()
            result = dict(
                connection.execute(text("select * from identity.backfill_from_supabase()"))
                .mappings()
                .one()
            )
            connection.execute(
                text(COMPLETE_BACKFILL_SQL),
                {**result, "run_id": run_id},
            )
        return {"run_id": str(run_id), "status": "succeeded", **result}
    except Exception as exc:
        failure_id = record_failure(
            engine,
            run_type="backfill",
            error_code=_error_code(exc),
            error_message=str(exc),
            metadata={"source": "operator"},
        )
        raise RuntimeError(f"Backfill failed; failure run {failure_id}") from exc


def run_reconciliation(engine: Engine) -> dict[str, Any]:
    try:
        with engine.begin() as connection:
            run_id = connection.execute(
                text(START_RUN_SQL),
                {
                    "run_type": "reconciliation",
                    "metadata": json.dumps({"source": "operator"}),
                },
            ).scalar_one()
            drifts = [dict(row) for row in connection.execute(text(DRIFT_SQL)).mappings()]
            connection.execute(
                text(COMPLETE_RECONCILIATION_SQL),
                {"run_id": run_id, "drift_count": len(drifts)},
            )
        return {
            "run_id": str(run_id),
            "status": "succeeded",
            "drift_count": len(drifts),
            "drifts": drifts,
        }
    except Exception as exc:
        failure_id = record_failure(
            engine,
            run_type="reconciliation",
            error_code=_error_code(exc),
            error_message=str(exc),
            metadata={"source": "operator"},
        )
        raise RuntimeError(f"Reconciliation failed; failure run {failure_id}") from exc


def read_metrics(engine: Engine) -> dict[str, Any]:
    with engine.connect() as connection:
        return dict(connection.execute(text(METRICS_SQL)).mappings().one())


def _prometheus(metrics: dict[str, Any]) -> str:
    metric_names = {
        "source_users": "identity_source_users",
        "users_mirrored": "identity_users_mirrored",
        "pending_users": "identity_pending_users",
        "drift_count": "identity_drift_count",
        "trigger_failures": "identity_trigger_failures_total",
        "sync_failures": "identity_sync_failures_total",
        "backfill_progress": "identity_backfill_progress_ratio",
    }
    lines = [
        f"{metric_name} {metrics[source_name]}" for source_name, metric_name in metric_names.items()
    ]
    last_reconciliation = metrics.get("last_reconciliation")
    timestamp = last_reconciliation.timestamp() if isinstance(last_reconciliation, datetime) else 0
    lines.append(f"identity_last_reconciliation_timestamp_seconds {timestamp}")
    return "\n".join(lines)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Operate and observe Supabase-to-identity coexistence."
    )
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("backfill", help="Run the idempotent identity backfill.")
    reconcile = commands.add_parser(
        "reconcile",
        help="Record and print a detailed identity drift report.",
    )
    reconcile.add_argument(
        "--fail-on-drift",
        action="store_true",
        help="Exit with status 2 when drift is detected.",
    )
    metrics = commands.add_parser(
        "metrics",
        help="Print coexistence operational metrics.",
    )
    metrics.add_argument(
        "--format",
        choices=("json", "prometheus"),
        default="json",
    )
    trigger_failure = commands.add_parser(
        "record-trigger-failure",
        help="Record a PostgreSQL-log-detected trigger failure.",
    )
    trigger_failure.add_argument("--error-code", required=True)
    trigger_failure.add_argument("--message", required=True)
    return parser


def main() -> None:
    args = _parser().parse_args()
    engine = get_engine()

    if args.command == "backfill":
        print(json.dumps(run_backfill(engine), default=_json_default, indent=2))
        return

    if args.command == "reconcile":
        report = run_reconciliation(engine)
        print(json.dumps(report, default=_json_default, indent=2))
        if args.fail_on_drift and report["drift_count"]:
            raise SystemExit(2)
        return

    if args.command == "metrics":
        metrics = read_metrics(engine)
        if args.format == "prometheus":
            print(_prometheus(metrics))
        else:
            print(json.dumps(metrics, default=_json_default, indent=2))
        return

    run_id = record_failure(
        engine,
        run_type="trigger",
        error_code=args.error_code,
        error_message=args.message,
        metadata={"source": "postgresql-log-monitor"},
    )
    print(json.dumps({"run_id": run_id, "status": "recorded"}, indent=2))


if __name__ == "__main__":
    main()
