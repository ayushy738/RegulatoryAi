from __future__ import annotations

import time
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
LEGACY_BACKFILL_ADVISORY_LOCK_KEY = 7_224_027_517_001
DEFAULT_BATCH_SIZE = 1_000
APPROVED_BATCH_PAUSE_SECONDS = 0.25
APPROVED_LOCK_TIMEOUT = "2s"
APPROVED_STATEMENT_TIMEOUT = "5min"
APPROVED_MAX_BATCH_TRANSACTION_SECONDS = 5.0
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
where id > :after_message_id
  and (
    public_id is null
    or session_id is null
  )
order by id
limit :batch_size
for update
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


class LegacyBackfillConcurrentRunError(RuntimeError):
    """Another legacy backfill runner owns the application-scoped lock."""


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
    max_batch_duration_ms: int
    average_batch_duration_ms: int
    batches_over_budget: int
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
            "max_batch_duration_ms": self.max_batch_duration_ms,
            "average_batch_duration_ms": self.average_batch_duration_ms,
            "batches_over_budget": self.batches_over_budget,
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


def _ensure_sessions(
    connection: Connection,
    grouped: dict[tuple[UUID, int | None], list[RowMapping]],
) -> int:
    if not grouped:
        return 0

    session_ids: list[UUID] = []
    user_ids: list[UUID] = []
    event_ids: list[int | None] = []
    first_message_times: list[datetime] = []
    last_message_times: list[datetime] = []
    for (user_id, event_id), messages in grouped.items():
        timestamps = [message["created_at"] for message in messages]
        session_ids.append(legacy_session_id(user_id, event_id))
        user_ids.append(user_id)
        event_ids.append(event_id)
        first_message_times.append(min(timestamps))
        last_message_times.append(max(timestamps))

    inserted_rows = connection.execute(
        text(
            """
            with batch_sessions as (
              select *
              from unnest(
                cast(:session_ids as uuid[]),
                cast(:user_ids as uuid[]),
                cast(:event_ids as bigint[]),
                cast(:first_message_times as timestamptz[]),
                cast(:last_message_times as timestamptz[])
              ) as batch(
                session_id,
                user_id,
                event_id,
                first_message_at,
                last_message_at
              )
            )
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
            select
              session_id,
              user_id,
              event_id,
              case
                when event_id is null then 'Legacy Ask history'
                else 'Legacy Ask history · Event ' || event_id::text
              end,
              'complete',
              jsonb_build_object(
                'legacy_backfill', true,
                'legacy_backfill_version', :backfill_version,
                'event_id', event_id
              ),
              first_message_at,
              last_message_at,
              last_message_at
            from batch_sessions
            on conflict (id) do nothing
            returning id
            """
        ),
        {
            "session_ids": session_ids,
            "user_ids": user_ids,
            "event_ids": event_ids,
            "first_message_times": first_message_times,
            "last_message_times": last_message_times,
            "backfill_version": LEGACY_BACKFILL_VERSION,
        },
    ).all()
    validated = connection.execute(
        text(
            """
            with batch_sessions as (
              select *
              from unnest(
                cast(:session_ids as uuid[]),
                cast(:user_ids as uuid[]),
                cast(:event_ids as bigint[])
              ) as batch(session_id, user_id, event_id)
            )
            select
              count(*) as session_count,
              count(*) filter (
                where session.user_id <> batch.user_id
                   or session.event_id is distinct from batch.event_id
                   or not (
                     session.scope_snapshot
                       @> jsonb_build_object(
                         'legacy_backfill',
                         true,
                         'legacy_backfill_version',
                         :backfill_version
                       )
                   )
              ) as mismatch_count
            from batch_sessions batch
            join public.chat_sessions session
              on session.id = batch.session_id
            """
        ),
        {
            "session_ids": session_ids,
            "user_ids": user_ids,
            "event_ids": event_ids,
            "backfill_version": LEGACY_BACKFILL_VERSION,
        },
    ).one()
    if validated.session_count != len(grouped) or validated.mismatch_count:
        raise LegacyBackfillDriftError(
            "A deterministic legacy session has conflicting ownership or scope"
        )
    return len(inserted_rows)


def _backfill_batch(connection: Connection, rows: list[RowMapping]) -> tuple[int, int]:
    grouped: dict[tuple[UUID, int | None], list[RowMapping]] = {}
    for row in rows:
        grouped.setdefault((row["user_id"], row["event_id"]), []).append(row)

    sessions_created = _ensure_sessions(connection, grouped)
    message_ids = [row["id"] for row in rows]
    user_ids = [row["user_id"] for row in rows]
    public_ids = [legacy_message_public_id(row["id"]) for row in rows]
    session_ids = [
        legacy_session_id(row["user_id"], row["event_id"]) for row in rows
    ]
    updated = connection.execute(
        text(
            """
            with batch_messages as (
              select *
              from unnest(
                cast(:message_ids as bigint[]),
                cast(:user_ids as uuid[]),
                cast(:public_ids as uuid[]),
                cast(:session_ids as uuid[])
              ) as batch(message_id, user_id, public_id, session_id)
            )
            update public.chat_messages as message
            set
              public_id = coalesce(message.public_id, batch.public_id),
              session_id = coalesce(message.session_id, batch.session_id)
            from batch_messages as batch
            where message.id = batch.message_id
              and message.user_id = batch.user_id
              and (message.public_id is null or message.public_id = batch.public_id)
              and (message.session_id is null or message.session_id = batch.session_id)
            """
        ),
        {
            "message_ids": message_ids,
            "user_ids": user_ids,
            "public_ids": public_ids,
            "session_ids": session_ids,
        },
    )
    messages_updated = int(updated.rowcount or 0)
    if messages_updated != len(rows):
        raise LegacyBackfillDriftError(
            "A legacy message has conflicting public/session identity"
        )
    return messages_updated, sessions_created


def _reconcile_session_timestamps(engine: Engine) -> None:
    with engine.begin() as connection:
        connection.exec_driver_sql(
            f"set local lock_timeout = '{APPROVED_LOCK_TIMEOUT}'"
        )
        connection.exec_driver_sql(
            f"set local statement_timeout = '{APPROVED_STATEMENT_TIMEOUT}'"
        )
        connection.execute(
            text(
                """
                with message_bounds as (
                  select
                    message.session_id,
                    min(message.created_at) as first_message_at,
                    max(message.created_at) as last_message_at
                  from public.chat_messages message
                  join public.chat_sessions session
                    on session.id = message.session_id
                  where session.scope_snapshot
                    @> '{"legacy_backfill": true}'::jsonb
                  group by message.session_id
                )
                update public.chat_sessions session
                set
                  created_at = bounds.first_message_at,
                  updated_at = bounds.last_message_at,
                  last_message_at = bounds.last_message_at
                from message_bounds bounds
                where session.id = bounds.session_id
                  and (
                    session.created_at is distinct from bounds.first_message_at
                    or session.updated_at is distinct from bounds.last_message_at
                    or session.last_message_at
                      is distinct from bounds.last_message_at
                  )
                """
            )
        )


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


def _run_backfill(
    engine: Engine,
    *,
    batch_size: int = DEFAULT_BATCH_SIZE,
    max_batches: int | None = None,
    batch_pause_seconds: float = 0.0,
    after_message_id: int = 0,
) -> BackfillResult:
    _validate_limits(batch_size, max_batches)
    if batch_pause_seconds < 0:
        raise ValueError("batch_pause_seconds must be non-negative")
    if after_message_id < 0:
        raise ValueError("after_message_id must be non-negative")
    started_at = perf_counter()
    batches_completed = 0
    messages_updated = 0
    sessions_created = 0
    last_message_id: int | None = None
    batch_durations_ms: list[int] = []

    while max_batches is None or batches_completed < max_batches:
        batch_started_at = perf_counter()
        with engine.begin() as connection:
            connection.exec_driver_sql(
                f"set local lock_timeout = '{APPROVED_LOCK_TIMEOUT}'"
            )
            connection.exec_driver_sql(
                f"set local statement_timeout = '{APPROVED_STATEMENT_TIMEOUT}'"
            )
            rows = list(
                connection.execute(
                    text(SELECT_BATCH_SQL),
                    {
                        "after_message_id": after_message_id,
                        "batch_size": batch_size,
                    },
                ).mappings()
            )
            if not rows:
                break
            batch_messages, batch_sessions = _backfill_batch(connection, rows)
            messages_updated += batch_messages
            sessions_created += batch_sessions
            last_message_id = rows[-1]["id"]
            after_message_id = last_message_id
        batches_completed += 1
        batch_duration_ms = max(
            0,
            round((perf_counter() - batch_started_at) * 1000),
        )
        batch_durations_ms.append(batch_duration_ms)
        if (
            batch_pause_seconds
            and (max_batches is None or batches_completed < max_batches)
        ):
            elapsed = perf_counter() - batch_started_at
            if elapsed < APPROVED_MAX_BATCH_TRANSACTION_SECONDS:
                time.sleep(batch_pause_seconds)

    _reconcile_session_timestamps(engine)
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
        max_batch_duration_ms=max(batch_durations_ms, default=0),
        average_batch_duration_ms=(
            round(sum(batch_durations_ms) / len(batch_durations_ms))
            if batch_durations_ms
            else 0
        ),
        batches_over_budget=sum(
            duration > APPROVED_MAX_BATCH_TRANSACTION_SECONDS * 1000
            for duration in batch_durations_ms
        ),
        verification=verification,
    )


def run_backfill(
    engine: Engine,
    *,
    batch_size: int = DEFAULT_BATCH_SIZE,
    max_batches: int | None = None,
    batch_pause_seconds: float = 0.0,
    after_message_id: int = 0,
) -> BackfillResult:
    with engine.connect() as lock_connection:
        acquired = lock_connection.execute(
            text("select pg_try_advisory_lock(:lock_key)"),
            {"lock_key": LEGACY_BACKFILL_ADVISORY_LOCK_KEY},
        ).scalar_one()
        if not acquired:
            raise LegacyBackfillConcurrentRunError(
                "another Ask AI legacy backfill runner is active"
            )
        try:
            return _run_backfill(
                engine,
                batch_size=batch_size,
                max_batches=max_batches,
                batch_pause_seconds=batch_pause_seconds,
                after_message_id=after_message_id,
            )
        finally:
            lock_connection.execute(
                text("select pg_advisory_unlock(:lock_key)"),
                {"lock_key": LEGACY_BACKFILL_ADVISORY_LOCK_KEY},
            )
