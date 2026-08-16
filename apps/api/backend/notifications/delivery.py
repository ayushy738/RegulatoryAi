"""Async delivery of pending regulatory notification emails."""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from backend.core.config import settings
from backend.core.db import session_scope
from backend.core.email import send_email
from backend.core.logging import log_event
from backend.notifications.service import load_notification_email_context
from backend.notifications.templates import build_notification_email

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 5
DEFAULT_BATCH_LIMIT = 50


def process_pending_notifications(*, limit: int = DEFAULT_BATCH_LIMIT) -> dict[str, int]:
    """Claim and send a bounded batch of pending/failed notification rows."""

    batch_limit = max(1, min(int(limit), 200))
    claimed = _claim_notifications(limit=batch_limit)
    sent = 0
    failed = 0
    skipped = 0

    for row in claimed:
        notification_id = int(row["id"])
        user_id = str(row["user_id"])
        event_id = int(row["event_id"])
        attempts = int(row.get("attempts") or 0)
        try:
            result = _deliver_one(
                notification_id=notification_id,
                user_id=user_id,
                event_id=event_id,
                attempts=attempts,
            )
        except Exception as exc:  # noqa: BLE001 — isolate batch items
            logger.warning(
                "notification delivery crashed notification_id=%s event_id=%s user_id=%s: %s: %s",
                notification_id,
                event_id,
                user_id,
                type(exc).__name__,
                exc,
            )
            _mark_failed(
                notification_id,
                error=f"{type(exc).__name__}: {exc}",
                attempts=attempts,
            )
            failed += 1
            continue

        if result == "sent":
            sent += 1
        elif result == "skipped":
            skipped += 1
        else:
            failed += 1

    summary = {
        "claimed": len(claimed),
        "sent": sent,
        "failed": failed,
        "skipped": skipped,
    }
    log_event("notification_worker_batch_finished", **summary)
    return summary


def _claim_notifications(*, limit: int) -> list[dict[str, Any]]:
    with session_scope() as session:
        rows = session.execute(
            text(
                """
                select id, user_id::text as user_id, event_id, attempts
                from notifications_log
                where channel = 'email'
                  and (
                    status = 'pending'
                    or (
                      status = 'failed'
                      and attempts < :max_attempts
                    )
                  )
                order by
                  case when status = 'pending' then 0 else 1 end,
                  updated_at,
                  id
                limit :limit
                for update skip locked
                """
            ),
            {"limit": limit, "max_attempts": MAX_ATTEMPTS},
        ).mappings().all()
        ids = [int(row["id"]) for row in rows]
        if ids:
            session.execute(
                text(
                    """
                    update notifications_log
                    set attempts = attempts + 1,
                        updated_at = now(),
                        error = case
                          when status = 'failed' then coalesce(error, 'Retrying failed delivery')
                          else error
                        end
                    where id = any(:ids)
                    """
                ),
                {"ids": ids},
            )
        return [dict(row) for row in rows]


def _deliver_one(
    *,
    notification_id: int,
    user_id: str,
    event_id: int,
    attempts: int,
) -> str:
    with session_scope() as session:
        recipient = session.execute(
            text(
                """
                select p.email as email
                from profiles p
                where p.id = cast(:user_id as uuid)
                """
            ),
            {"user_id": user_id},
        ).mappings().first()
        email = (recipient or {}).get("email") if recipient else None
        if not email or not str(email).strip():
            session.execute(
                text(
                    """
                    update notifications_log
                    set status = 'skipped',
                        error = 'Recipient email missing',
                        updated_at = now()
                    where id = :id
                    """
                ),
                {"id": notification_id},
            )
            log_event(
                "notification_delivery_skipped",
                notification_id=notification_id,
                event_id=event_id,
                user_id=user_id,
                reason="missing_email",
            )
            return "skipped"

        context = load_notification_email_context(session, event_id=event_id)
        if not context:
            session.execute(
                text(
                    """
                    update notifications_log
                    set status = 'skipped',
                        error = 'Event context missing',
                        updated_at = now()
                    where id = :id
                    """
                ),
                {"id": notification_id},
            )
            log_event(
                "notification_delivery_skipped",
                notification_id=notification_id,
                event_id=event_id,
                user_id=user_id,
                reason="missing_event",
            )
            return "skipped"

        subject, html_body, text_body = build_notification_email(context)

    try:
        result = send_email(
            to=str(email).strip(),
            subject=subject,
            html=html_body,
            text=text_body,
        )
    except Exception as exc:  # noqa: BLE001
        _mark_failed(
            notification_id,
            error=f"{type(exc).__name__}: {exc}",
            attempts=attempts + 1,
        )
        log_event(
            "notification_delivery_failed",
            notification_id=notification_id,
            event_id=event_id,
            user_id=user_id,
            provider=settings.email_provider,
            error=f"{type(exc).__name__}: {exc}",
        )
        return "failed"

    with session_scope() as session:
        session.execute(
            text(
                """
                update notifications_log
                set status = 'sent',
                    provider_message_id = :message_id,
                    error = null,
                    sent_at = now(),
                    updated_at = now()
                where id = :id
                """
            ),
            {"id": notification_id, "message_id": result.message_id},
        )
    log_event(
        "notification_delivery_sent",
        notification_id=notification_id,
        event_id=event_id,
        user_id=user_id,
        provider=result.provider,
        message_id=result.message_id,
    )
    return "sent"


def _mark_failed(notification_id: int, *, error: str, attempts: int) -> None:
    status = "failed"
    # Keep retryable until max attempts; final state remains failed.
    try:
        with session_scope() as session:
            session.execute(
                text(
                    """
                    update notifications_log
                    set status = cast(:status as notify_status_t),
                        error = :error,
                        updated_at = now()
                    where id = :id
                    """
                ),
                {
                    "id": notification_id,
                    "status": status,
                    "error": error[:2000],
                },
            )
    except SQLAlchemyError as exc:
        logger.warning(
            "failed to mark notification %s as failed: %s",
            notification_id,
            exc,
        )
