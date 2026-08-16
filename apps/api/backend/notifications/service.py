"""Enqueue durable pending notification rows for regulatory events."""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Connection
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from backend.core.db import session_scope
from backend.core.logging import log_event
from backend.notifications.targeting import list_eligible_notification_recipients

logger = logging.getLogger(__name__)

_EVENT_CONTEXT_SQL = """
select
  e.id as event_id,
  e.event_type::text as event_type,
  e.version_id,
  e.document_id,
  d.source_id,
  d.title,
  coalesce(s.name, d.issuing_body, 'Regulatory source') as source_name,
  s.code as source_code
from events e
join documents d on d.id = e.document_id
left join sources s on s.id = d.source_id
where e.id = :event_id
  and e.suppressed = false
  and e.event_type::text in ('NEW', 'CHANGED')
"""


def enqueue_notifications(event_ids: list[int]) -> int:
    """Create pending email notifications for NEW/CHANGED events. Idempotent."""

    if not event_ids:
        return 0

    created = 0
    for event_id in event_ids:
        try:
            created += enqueue_notifications_for_event(event_id=int(event_id))
        except Exception as exc:  # noqa: BLE001 — never fail crawl for notify
            logger.warning(
                "enqueue_notifications failed for event_id=%s: %s: %s",
                event_id,
                type(exc).__name__,
                exc,
            )
            log_event(
                "notification_enqueue_failed",
                event_id=event_id,
                error=f"{type(exc).__name__}: {exc}",
            )
    return created


def enqueue_notifications_for_event(
    *,
    event_id: int,
    session: Session | Connection | None = None,
) -> int:
    """Insert pending notifications_log rows for one event. Returns rows created."""

    if session is not None:
        return _enqueue_with_session(session, event_id=event_id)

    try:
        with session_scope() as owned:
            return _enqueue_with_session(owned, event_id=event_id)
    except SQLAlchemyError as exc:
        logger.warning(
            "enqueue_notifications_for_event db error event_id=%s: %s",
            event_id,
            exc,
        )
        log_event(
            "notification_enqueue_failed",
            event_id=event_id,
            error=f"{type(exc).__name__}: {exc}",
        )
        return 0


def _enqueue_with_session(session: Session | Connection, *, event_id: int) -> int:
    context = session.execute(
        text(_EVENT_CONTEXT_SQL),
        {"event_id": event_id},
    ).mappings().first()
    if not context:
        log_event("notification_enqueue_skipped", event_id=event_id, reason="not_notify_worthy")
        return 0

    source_id = context["source_id"]
    recipients = list_eligible_notification_recipients(
        session,
        source_id=int(source_id) if source_id is not None else None,
    )
    if not recipients:
        log_event(
            "notification_enqueue_skipped",
            event_id=event_id,
            source_id=source_id,
            reason="no_eligible_subscribers",
        )
        return 0

    created = 0
    for recipient in recipients:
        user_id = str(recipient["user_id"])
        inserted = session.execute(
            text(
                """
                insert into notifications_log (user_id, event_id, channel, status)
                values (cast(:user_id as uuid), :event_id, 'email', 'pending')
                on conflict (user_id, event_id, channel) do nothing
                returning id
                """
            ),
            {"user_id": user_id, "event_id": event_id},
        ).first()
        if inserted:
            created += 1
            log_event(
                "notification_enqueued",
                notification_id=int(inserted.id),
                event_id=event_id,
                user_id=user_id,
                source_id=source_id,
                event_type=context["event_type"],
            )

    log_event(
        "notification_enqueue_finished",
        event_id=event_id,
        source_id=source_id,
        recipients=len(recipients),
        created=created,
    )
    return created


def load_notification_email_context(
    session: Session | Connection,
    *,
    event_id: int,
) -> dict[str, Any] | None:
    """Load event/document/source/summary fields for email rendering."""

    row = session.execute(
        text(
            """
            select
              e.id as event_id,
              e.event_type::text as event_type,
              e.detected_at,
              e.raw_summary,
              e.version_id,
              d.id as document_id,
              d.title,
              d.doc_type,
              d.issue_date,
              d.source_url,
              d.issuing_body,
              d.source_id,
              coalesce(s.name, d.issuing_body, 'Regulatory source') as source_name,
              s.code as source_code,
              sm.summary_json
            from events e
            join documents d on d.id = e.document_id
            left join sources s on s.id = d.source_id
            left join lateral (
              select summary_json
              from summaries
              where event_id = e.id
              order by created_at desc
              limit 1
            ) sm on true
            where e.id = :event_id
            """
        ),
        {"event_id": event_id},
    ).mappings().first()
    return dict(row) if row else None
