"""Subscription matching for regulatory update emails."""

from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Connection
from sqlalchemy.orm import Session

# Explicit subscription row + email_enabled + instant only.
# source_ids = [] means ALL sources (only when a row exists).
_ELIGIBLE_USERS_SQL = """
select
  s.user_id::text as user_id,
  p.email as email
from subscriptions s
join profiles p on p.id = s.user_id
where s.email_enabled = true
  and lower(s.frequency) = 'instant'
  and p.email is not null
  and length(trim(p.email)) > 0
  and (
    cardinality(s.source_ids) = 0
    or :source_id = any(s.source_ids)
  )
"""


def list_eligible_notification_recipients(
    session: Session | Connection,
    *,
    source_id: int | None,
) -> list[dict[str, Any]]:
    """Return users with an explicit instant email subscription for the source.

    No subscription row → not eligible.
    source_ids empty → all sources.
    Missing source_id on the document → only all-source subscribers match.
    """

    if source_id is None:
        rows = session.execute(
            text(
                """
                select
                  s.user_id::text as user_id,
                  p.email as email
                from subscriptions s
                join profiles p on p.id = s.user_id
                where s.email_enabled = true
                  and lower(s.frequency) = 'instant'
                  and cardinality(s.source_ids) = 0
                  and p.email is not null
                  and length(trim(p.email)) > 0
                """
            )
        ).mappings().all()
        return [dict(row) for row in rows]

    rows = session.execute(
        text(_ELIGIBLE_USERS_SQL),
        {"source_id": int(source_id)},
    ).mappings().all()
    return [dict(row) for row in rows]
