from __future__ import annotations

import argparse
import json
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Engine

from backend.core.db import get_engine

AUTHENTICATION_METRICS_SQL = """
select
  source,
  outcome,
  reason_code,
  observation_count
from identity.dual_authentication_metrics
order by source, outcome, reason_code nulls first
"""

SESSION_METRICS_SQL = """
select
  count(*) filter (
    where exchanged_at >= now() - interval '24 hours'
  )::bigint as exchanges_last_24_hours,
  count(*)::bigint as exchanges_total
from identity.session_exchanges
"""

SESSION_STATE_SQL = """
select
  count(*) filter (
    where revoked_at is null and expires_at > now()
  )::bigint as active_sessions,
  count(*) filter (
    where revoked_at is not null
  )::bigint as revoked_sessions,
  count(*) filter (
    where revoked_at is null and expires_at <= now()
  )::bigint as expired_sessions
from identity.auth_sessions
"""


def read_metrics(engine: Engine) -> dict[str, Any]:
    with engine.connect() as connection:
        authentication = [
            dict(row)
            for row in connection.execute(text(AUTHENTICATION_METRICS_SQL)).mappings()
        ]
        exchanges = dict(connection.execute(text(SESSION_METRICS_SQL)).mappings().one())
        sessions = dict(connection.execute(text(SESSION_STATE_SQL)).mappings().one())
    return {
        "authentication_last_24_hours": authentication,
        "exchanges": exchanges,
        "sessions": sessions,
    }


def _prometheus(metrics: dict[str, Any]) -> str:
    lines: list[str] = []
    for observation in metrics["authentication_last_24_hours"]:
        source = observation["source"]
        outcome = observation["outcome"]
        reason = observation.get("reason_code") or ""
        lines.append(
            "identity_authentication_observations_24h"
            f'{{source="{source}",outcome="{outcome}",reason="{reason}"}} '
            f'{observation["observation_count"]}'
        )
    lines.extend(
        (
            "identity_session_exchanges_24h "
            f'{metrics["exchanges"]["exchanges_last_24_hours"]}',
            f'identity_session_exchanges_total {metrics["exchanges"]["exchanges_total"]}',
            f'identity_active_sessions {metrics["sessions"]["active_sessions"]}',
            f'identity_revoked_sessions {metrics["sessions"]["revoked_sessions"]}',
            f'identity_expired_sessions {metrics["sessions"]["expired_sessions"]}',
        )
    )
    return "\n".join(lines)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Read dual-authentication operational metrics."
    )
    parser.add_argument(
        "--format",
        choices=("json", "prometheus"),
        default="json",
    )
    return parser


def main() -> None:
    args = _parser().parse_args()
    metrics = read_metrics(get_engine())
    if args.format == "prometheus":
        print(_prometheus(metrics))
        return
    print(json.dumps(metrics, indent=2, default=str))


if __name__ == "__main__":
    main()
