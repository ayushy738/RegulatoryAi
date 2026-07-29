from __future__ import annotations

import json
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime
from time import perf_counter
from typing import Any
from uuid import UUID, uuid5

from sqlalchemy import text
from sqlalchemy.engine import Connection, Engine, RowMapping

LEGACY_BACKFILL_NAMESPACE = UUID("8d7a8d52-34d1-4b4b-a6d0-5c05696d88f5")
LEGACY_BACKFILL_VERSION = 1
DEFAULT_BATCH_SIZE = 500
MAX_BATCH_SIZE = 10_000

SELECT_BATCH_SQL = """
select
  id,
  user_id,
  event_id,
  public_id,
  session_id,
  created_at
from public.chat_messages
where public_id is null
   or session_id is null
order by id
limit :batch_size
for update skip locked
"""

SELECT_MESSAGE_IDENTITIES_SQL = """
select
  message.id,
  message.user_id,
  message.event_id,
  message.public_id,
  message.session_id,
  message.created_at,
  session.user_id as session_user_id,
  session.event_id as session_event_id,
  session.scope_snapshot as session_scope_snapshot
from public.chat_messages message
left join public.chat_sessions session on session.id = message.session_id
order by message.id
"""

SELECT_LEGACY_SESSIONS_SQL = """
select
  id,
  user_id,
  event_id,
  scope_snapshot,
  created_at,
  updated_at,
  last_message_at
from public.chat_sessions
where scope_snapshot @> '{"legacy_backfill": true}'::jsonb
order by id
"""


class LegacyBackfillDriftError(RuntimeError):
    """Existing identities conflict with deterministic legacy backfill identity."""


@dataclass(frozen=True, slots=True)
class BackfillPreview:
    legacy_message_count: int
    pending_message_count: int
    expected_session_count: int
    existing_legacy_session_count: int
    sessions_to_create: int

    def to_dict(self) -> dict[str, Any]:
        return {"mode": "dry-run", **asdict(self)}


@dataclass(frozen=True, slots=True)
class BackfillVerification:
    is_valid: bool
    legacy_message_count: int
    backfilled_message_count: int
    pending_message_count: int
    expected_session_count: int
    legacy_session_count: int
    public_id_mismatch_count: int
    session_id_mismatch_count: int
    ownership_mismatch_count: int
    event_scope_mismatch_count: int
    session_metadata_mismatch_count: int
    duplicate_scope_session_count: int
    orphan_session_count: int
    drift_count: int

    def to_dict(self) -> dict[str, Any]:
        return {"mode": "verify", **asdict(self)}


@dataclass(frozen=True, slots=True)
class BackfillResult:
    status: str
    batch_size: int
    batches_completed: int
    messages_updated: int
    sessions_created: int
    last_message_id: int | None
    duration_ms: int
    verification: BackfillVerification

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": "run",
            "status": self.status,
            "batch_size": self.batch_size,
            "batches_completed": self.batches_completed,
            "messages_updated": self.messages_updated,
            "sessions_created": self.sessions_created,
            "last_message_id": self.last_message_id,
            "duration_ms": self.duration_ms,
            "verification": asdict(self.verification),
        }


@dataclass(frozen=True, slots=True)
class BackfillPreflight:
    is_ready: bool
    required_migration: str
    verification: BackfillVerification

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": "preflight",
            "is_ready": self.is_ready,
            "required_migration": self.required_migration,
            "verification": asdict(self.verification),
        }


def legacy_session_id(user_id: UUID, event_id: int | None) -> UUID:
    event_scope = "global" if event_id is None else f"event:{event_id}"
    return uuid5(
        LEGACY_BACKFILL_NAMESPACE,
        f"session:{user_id}:{event_scope}",
    )


def legacy_message_public_id(message_id: int) -> UUID:
    return uuid5(LEGACY_BACKFILL_NAMESPACE, f"message:{message_id}")


def legacy_session_title(event_id: int | None) -> str:
    if event_id is None:
        return "Legacy Ask history"
    return f"Legacy Ask history · Event {event_id}"


def _scope_snapshot(event_id: int | None) -> dict[str, Any]:
    return {
        "legacy_backfill": True,
        "legacy_backfill_version": LEGACY_BACKFILL_VERSION,
        "event_id": event_id,
    }


def _validate_limits(batch_size: int, max_batches: int | None) -> None:
    if batch_size < 1 or batch_size > MAX_BATCH_SIZE:
        raise ValueError(f"batch_size must be between 1 and {MAX_BATCH_SIZE}")
    if max_batches is not None and max_batches < 1:
        raise ValueError("max_batches must be at least 1")


def _is_legacy_session(row: RowMapping) -> bool:
    snapshot = row["scope_snapshot"] or {}
    return (
        snapshot.get("legacy_backfill") is True
        and snapshot.get("legacy_backfill_version") == LEGACY_BACKFILL_VERSION
    )


def _is_legacy_message(row: RowMapping) -> bool:
    snapshot = row["session_scope_snapshot"] or {}
    return (
        row["public_id"] is None
        or row["session_id"] is None
        or snapshot.get("legacy_backfill") is True
        or row["public_id"] == legacy_message_public_id(row["id"])
    )


def _ensure_session(
    connection: Connection,
    *,
    session_id: UUID,
    user_id: UUID,
    event_id: int | None,
    first_message_at: datetime,
    last_message_at: datetime,
) -> bool:
    result = connection.execute(
        text(
            """
            insert into public.chat_sessions (
              id,
              user_id,
              event_id,
              title,
              status,
              scope_snapshot,
              created_at,
              updated_at,
              last_message_at
            )
            values (
              :session_id,
              :user_id,
              :event_id,
              :title,
              'complete',
              cast(:scope_snapshot as jsonb),
              :first_message_at,
              :last_message_at,
              :last_message_at
            )
            on conflict (id) do nothing
            """
        ),
        {
            "session_id": session_id,
            "user_id": user_id,
            "event_id": event_id,
            "title": legacy_session_title(event_id),
            "scope_snapshot": json.dumps(_scope_snapshot(event_id)),
            "first_message_at": first_message_at,
            "last_message_at": last_message_at,
        },
    )
    created = int(result.rowcount or 0) == 1
    session_row = connection.execute(
        text(
            """
            select id, user_id, event_id, scope_snapshot
            from public.chat_sessions
            where id = :session_id
            for update
            """
        ),
        {"session_id": session_id},
    ).mappings().one()
    if (
        session_row["user_id"] != user_id
        or session_row["event_id"] != event_id
        or not _is_legacy_session(session_row)
    ):
        raise LegacyBackfillDriftError(
            f"Deterministic legacy session {session_id} has conflicting ownership or scope"
        )

    connection.execute(
        text(
            """
            update public.chat_sessions
            set
              created_at = least(created_at, :first_message_at),
              updated_at = greatest(updated_at, :last_message_at),
              last_message_at = greatest(
                coalesce(last_message_at, :last_message_at),
                :last_message_at
              )
            where id = :session_id
              and user_id = :user_id
              and event_id is not distinct from :event_id
            """
        ),
        {
            "session_id": session_id,
            "user_id": user_id,
            "event_id": event_id,
            "first_message_at": first_message_at,
            "last_message_at": last_message_at,
        },
    )
    return created


def _backfill_batch(connection: Connection, rows: list[RowMapping]) -> tuple[int, int]:
    grouped: dict[tuple[UUID, int | None], list[RowMapping]] = {}
    for row in rows:
        grouped.setdefault((row["user_id"], row["event_id"]), []).append(row)

    sessions_created = 0
    for (user_id, event_id), messages in grouped.items():
        timestamps = [message["created_at"] for message in messages]
        sessions_created += int(
            _ensure_session(
                connection,
                session_id=legacy_session_id(user_id, event_id),
                user_id=user_id,
                event_id=event_id,
                first_message_at=min(timestamps),
                last_message_at=max(timestamps),
            )
        )

    messages_updated = 0
    for row in rows:
        expected_session_id = legacy_session_id(row["user_id"], row["event_id"])
        expected_public_id = legacy_message_public_id(row["id"])
        updated = connection.execute(
            text(
                """
                update public.chat_messages
                set
                  public_id = coalesce(public_id, :public_id),
                  session_id = coalesce(session_id, :session_id)
                where id = :message_id
                  and user_id = :user_id
                  and (public_id is null or public_id = :public_id)
                  and (session_id is null or session_id = :session_id)
                """
            ),
            {
                "message_id": row["id"],
                "user_id": row["user_id"],
                "public_id": expected_public_id,
                "session_id": expected_session_id,
            },
        )
        if int(updated.rowcount or 0) != 1:
            raise LegacyBackfillDriftError(
                f"Legacy message {row['id']} has conflicting public/session identity"
            )
        messages_updated += 1
    return messages_updated, sessions_created


def preview_backfill(engine: Engine) -> BackfillPreview:
    legacy_message_count = 0
    pending_message_count = 0
    expected_sessions: set[UUID] = set()
    with engine.connect() as connection:
        message_rows = (
            connection.execution_options(
                stream_results=True,
                max_row_buffer=1000,
            )
            .execute(text(SELECT_MESSAGE_IDENTITIES_SQL))
            .mappings()
        )
        for row in message_rows:
            if not _is_legacy_message(row):
                continue
            legacy_message_count += 1
            pending_message_count += int(
                row["public_id"] is None or row["session_id"] is None
            )
            expected_sessions.add(
                legacy_session_id(row["user_id"], row["event_id"])
            )
        existing_sessions = {
            row["id"]
            for row in connection.execution_options(
                stream_results=True,
                max_row_buffer=1000,
            )
            .execute(text(SELECT_LEGACY_SESSIONS_SQL))
            .mappings()
        }
    return BackfillPreview(
        legacy_message_count=legacy_message_count,
        pending_message_count=pending_message_count,
        expected_session_count=len(expected_sessions),
        existing_legacy_session_count=len(existing_sessions),
        sessions_to_create=len(expected_sessions - existing_sessions),
    )


def verify_backfill(engine: Engine) -> BackfillVerification:
    expected_session_ids: set[UUID] = set()
    legacy_message_count = 0
    backfilled = 0
    pending = 0
    public_mismatch = 0
    session_mismatch = 0
    ownership_mismatch = 0
    event_mismatch = 0
    session_ids: set[UUID] = set()
    legacy_session_count = 0
    session_metadata_mismatch = 0
    scope_counts: Counter[tuple[UUID, int | None]] = Counter()

    with engine.connect() as connection:
        message_rows = (
            connection.execution_options(
                stream_results=True,
                max_row_buffer=1000,
            )
            .execute(text(SELECT_MESSAGE_IDENTITIES_SQL))
            .mappings()
        )
        for row in message_rows:
            if not _is_legacy_message(row):
                continue
            legacy_message_count += 1
            expected_public_id = legacy_message_public_id(row["id"])
            expected_session_id = legacy_session_id(row["user_id"], row["event_id"])
            expected_session_ids.add(expected_session_id)
            if row["public_id"] is None or row["session_id"] is None:
                pending += 1
            if (
                row["public_id"] is not None
                and row["public_id"] != expected_public_id
            ):
                public_mismatch += 1
            if (
                row["session_id"] is not None
                and row["session_id"] != expected_session_id
            ):
                session_mismatch += 1
            if (
                row["session_user_id"] is not None
                and row["session_user_id"] != row["user_id"]
            ):
                ownership_mismatch += 1
            if (
                row["session_id"] is not None
                and row["session_event_id"] != row["event_id"]
            ):
                event_mismatch += 1
            if (
                row["public_id"] == expected_public_id
                and row["session_id"] == expected_session_id
            ):
                backfilled += 1

        session_rows = (
            connection.execution_options(
                stream_results=True,
                max_row_buffer=1000,
            )
            .execute(text(SELECT_LEGACY_SESSIONS_SQL))
            .mappings()
        )
        for row in session_rows:
            legacy_session_count += 1
            session_ids.add(row["id"])
            scope_counts[(row["user_id"], row["event_id"])] += 1
            session_metadata_mismatch += int(
                row["id"] != legacy_session_id(row["user_id"], row["event_id"])
                or not _is_legacy_session(row)
            )

    duplicate_scope_sessions = sum(count - 1 for count in scope_counts.values() if count > 1)
    orphan_sessions = len(session_ids - expected_session_ids)
    drift_count = (
        public_mismatch
        + session_mismatch
        + ownership_mismatch
        + event_mismatch
        + session_metadata_mismatch
        + duplicate_scope_sessions
        + orphan_sessions
    )
    return BackfillVerification(
        is_valid=pending == 0 and drift_count == 0,
        legacy_message_count=legacy_message_count,
        backfilled_message_count=backfilled,
        pending_message_count=pending,
        expected_session_count=len(expected_session_ids),
        legacy_session_count=legacy_session_count,
        public_id_mismatch_count=public_mismatch,
        session_id_mismatch_count=session_mismatch,
        ownership_mismatch_count=ownership_mismatch,
        event_scope_mismatch_count=event_mismatch,
        session_metadata_mismatch_count=session_metadata_mismatch,
        duplicate_scope_session_count=duplicate_scope_sessions,
        orphan_session_count=orphan_sessions,
        drift_count=drift_count,
    )


def preflight_backfill_validation(engine: Engine) -> BackfillPreflight:
    verification = verify_backfill(engine)
    return BackfillPreflight(
        is_ready=verification.is_valid,
        required_migration="0025_ask_ai_backfill_validation.sql",
        verification=verification,
    )


def run_backfill(
    engine: Engine,
    *,
    batch_size: int = DEFAULT_BATCH_SIZE,
    max_batches: int | None = None,
) -> BackfillResult:
    _validate_limits(batch_size, max_batches)
    started_at = perf_counter()
    batches_completed = 0
    messages_updated = 0
    sessions_created = 0
    last_message_id: int | None = None

    while max_batches is None or batches_completed < max_batches:
        with engine.begin() as connection:
            rows = list(
                connection.execute(
                    text(SELECT_BATCH_SQL),
                    {"batch_size": batch_size},
                ).mappings()
            )
            if not rows:
                break
            batch_messages, batch_sessions = _backfill_batch(connection, rows)
            messages_updated += batch_messages
            sessions_created += batch_sessions
            last_message_id = rows[-1]["id"]
        batches_completed += 1

    verification = verify_backfill(engine)
    status = "complete"
    if verification.drift_count:
        status = "failed"
    elif verification.pending_message_count:
        status = "partial"
    return BackfillResult(
        status=status,
        batch_size=batch_size,
        batches_completed=batches_completed,
        messages_updated=messages_updated,
        sessions_created=sessions_created,
        last_message_id=last_message_id,
        duration_ms=max(0, round((perf_counter() - started_at) * 1000)),
        verification=verification,
    )
