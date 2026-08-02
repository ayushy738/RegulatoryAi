from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Engine

from backend.ask.backfill import (
    APPROVED_BATCH_PAUSE_SECONDS,
    APPROVED_MAX_BATCH_TRANSACTION_SECONDS,
    DEFAULT_BATCH_SIZE,
    BackfillResult,
    run_backfill,
)
from backend.core.migrations import apply_pending_migrations

MINIMUM_REHEARSAL_MESSAGES = 10_000_000
DEFAULT_REHEARSAL_OWNERS = 1_000
DEFAULT_ARTIFACT_OWNERS = 100
REHEARSAL_DATASET_VERSION = "e1.7-v1"
APPROVED_LOCK_WAIT_PEAK_MS = 2_000

REHEARSAL_AUTH_BOOTSTRAP_SQL = """
do $roles$
begin
  if not exists (select 1 from pg_roles where rolname = 'anon') then
    create role anon nologin;
  end if;
  if not exists (select 1 from pg_roles where rolname = 'authenticated') then
    create role authenticated nologin;
  end if;
  if not exists (select 1 from pg_roles where rolname = 'service_role') then
    create role service_role nologin bypassrls;
  end if;
end
$roles$;

create schema auth;

create function auth.uid()
returns uuid
language sql
stable
as $$
  select nullif(current_setting('request.jwt.claim.sub', true), '')::uuid
$$;

create table auth.users (
  id uuid primary key,
  email text,
  email_confirmed_at timestamptz,
  banned_until timestamptz,
  deleted_at timestamptz,
  raw_user_meta_data jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

grant usage on schema auth to authenticated;
grant execute on function auth.uid() to authenticated;
"""


@dataclass(frozen=True, slots=True)
class DatabasePreflight:
    database_version: str
    migration_head: str
    message_count: int
    legacy_pending_count: int
    database_size_bytes: int
    active_connections: int
    max_connections: int
    longest_transaction_seconds: float
    replica_count: int
    deadlocks: int


@dataclass(frozen=True, slots=True)
class DatasetProfile:
    version: str
    source_messages: int
    owners: int
    hot_owner_percent: int
    hot_message_percent: int
    artifact_owners: int
    sections_per_artifact_run: int
    claims_per_artifact_run: int
    events_per_artifact_run: int


@dataclass(frozen=True, slots=True)
class ReconciliationReport:
    source_business_hash: str
    target_business_hash: str
    eligible_source_count: int
    backfilled_target_count: int
    pending_count: int
    ownership_mismatches: int
    ordering_mismatches: int
    lineage_mismatches: int
    duplicate_scope_count: int
    orphan_session_count: int
    hash_match: bool
    count_match: bool


@dataclass(frozen=True, slots=True)
class MigrationRehearsalReport:
    report_version: str
    started_at: str
    completed_at: str
    preflight: DatabasePreflight
    dataset: DatasetProfile
    expand_duration_ms: int
    backfill: dict[str, Any]
    validate_duration_ms: int
    reconciliation: ReconciliationReport
    rollback_compatible: bool
    deadlock_delta: int
    approved_batch_size: int
    approved_batch_pause_seconds: float
    approved_max_batch_transaction_seconds: float
    approved_lock_wait_peak_ms: int
    observed_lock_wait_peak_ms: int
    observed_replica_lag_peak_seconds: float
    observed_database_cpu_peak_percent: float
    acceptance_passed: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _canonical_value(value: Any) -> Any:
    if value is None:
        return {"null": True}
    if isinstance(value, datetime):
        return value.astimezone(UTC).isoformat(timespec="microseconds")
    return str(value)


def canonical_business_hash(engine: Engine) -> tuple[int, str]:
    digest = hashlib.sha256()
    count = 0
    with engine.connect() as connection:
        rows = (
            connection.execution_options(stream_results=True, max_row_buffer=5_000)
            .execute(
                text(
                    """
                    select id, user_id, event_id, role, content, created_at
                    from public.chat_messages
                    where content not like 'e1.7-artifact-message:%'
                    order by id
                    """
                )
            )
            .mappings()
        )
        for row in rows:
            canonical = json.dumps(
                [
                    _canonical_value(row["id"]),
                    _canonical_value(row["user_id"]),
                    _canonical_value(row["event_id"]),
                    _canonical_value(row["role"]),
                    _canonical_value(row["content"]),
                    _canonical_value(row["created_at"]),
                ],
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode("utf-8")
            digest.update(len(canonical).to_bytes(8, "big"))
            digest.update(canonical)
            count += 1
    return count, digest.hexdigest()


def capture_database_preflight(engine: Engine) -> DatabasePreflight:
    with engine.connect() as connection:
        migration_head = connection.execute(
            text(
                """
                select coalesce(
                  (select max(version) from public.schema_migrations),
                  'none'
                )
                """
            )
        ).scalar_one()
        pending_expression = (
            """
            (
              select count(*)
              from public.chat_messages
              where public_id is null or session_id is null
            )
            """
            if migration_head >= "0023"
            else "(select count(*) from public.chat_messages)"
        )
        row = connection.execute(
            text(
                f"""
                select
                  version() as database_version,
                  :migration_head as migration_head,
                  (select count(*) from public.chat_messages) as message_count,
                  {pending_expression} as legacy_pending_count,
                  pg_database_size(current_database()) as database_size_bytes,
                  (
                    select count(*)
                    from pg_stat_activity
                    where datname = current_database()
                  ) as active_connections,
                  current_setting('max_connections')::integer as max_connections,
                  coalesce(
                    (
                      select max(extract(epoch from clock_timestamp() - xact_start))
                      from pg_stat_activity
                      where datname = current_database()
                        and xact_start is not null
                        and pid <> pg_backend_pid()
                    ),
                    0
                  )::double precision as longest_transaction_seconds,
                  (select count(*) from pg_stat_replication) as replica_count,
                  (
                    select deadlocks
                    from pg_stat_database
                    where datname = current_database()
                  ) as deadlocks
                """
            ),
            {"migration_head": migration_head},
        ).mappings().one()
    return DatabasePreflight(**dict(row))


def reset_disposable_rehearsal_database(engine: Engine) -> None:
    if engine.url.host not in {"127.0.0.1", "localhost", "::1"}:
        raise ValueError("rehearsal reset is restricted to a loopback database")
    if "rehearsal" not in (engine.url.database or "").lower():
        raise ValueError("rehearsal reset requires 'rehearsal' in the database name")
    with engine.begin() as connection:
        connection.exec_driver_sql("drop schema if exists identity cascade")
        connection.exec_driver_sql("drop schema if exists auth cascade")
        connection.exec_driver_sql("drop schema public cascade")
        connection.exec_driver_sql("create schema public")
        connection.exec_driver_sql("grant all on schema public to public")
        connection.exec_driver_sql(REHEARSAL_AUTH_BOOTSTRAP_SQL)


def seed_rehearsal_dataset(
    engine: Engine,
    *,
    message_count: int,
    owner_count: int = DEFAULT_REHEARSAL_OWNERS,
    artifact_owner_count: int = DEFAULT_ARTIFACT_OWNERS,
    enforce_minimum: bool = True,
) -> DatasetProfile:
    if enforce_minimum and message_count < MINIMUM_REHEARSAL_MESSAGES:
        raise ValueError(
            f"message_count must be at least {MINIMUM_REHEARSAL_MESSAGES}"
        )
    if message_count < 1:
        raise ValueError("message_count must be positive")
    if owner_count < 10:
        raise ValueError("owner_count must be at least 10")
    if artifact_owner_count < 1 or artifact_owner_count > owner_count:
        raise ValueError("artifact_owner_count must be between 1 and owner_count")

    hot_owner_count = max(1, owner_count // 10)
    cold_owner_count = owner_count - hot_owner_count
    with engine.begin() as connection:
        existing = connection.execute(
            text("select count(*) from public.chat_messages")
        ).scalar_one()
        if existing:
            raise ValueError("rehearsal dataset requires an empty chat_messages table")
        connection.execute(
            text(
                """
                insert into auth.users (id, email, email_confirmed_at)
                select
                  (
                    '40000000-0000-4000-8000-'
                    || lpad(to_hex(owner_index), 12, '0')
                  )::uuid,
                  'e17-owner-' || owner_index || '@example.invalid',
                  now()
                from generate_series(1, :owner_count) as owner(owner_index)
                """
            ),
            {"owner_count": owner_count},
        )
        connection.execute(
            text(
                """
                with generated as (
                  select
                    message_index,
                    case
                      when message_index % 10 < 7
                        then 1 + (message_index % :hot_owner_count)
                      else 1 + :hot_owner_count
                        + (message_index % :cold_owner_count)
                    end as owner_index
                  from generate_series(1, :message_count) as series(message_index)
                )
                insert into public.chat_messages (
                  user_id,
                  role,
                  content,
                  created_at
                )
                select
                  (
                    '40000000-0000-4000-8000-'
                    || lpad(to_hex(owner_index), 12, '0')
                  )::uuid,
                  case when message_index % 2 = 1 then 'user' else 'assistant' end,
                  'e1.7-message:' || lpad(message_index::text, 12, '0')
                    || ':' || repeat('x', 96),
                  timestamptz '2026-01-01 00:00:00+00'
                    + message_index * interval '1 millisecond'
                from generated
                order by message_index
                """
            ),
            {
                "message_count": message_count,
                "hot_owner_count": hot_owner_count,
                "cold_owner_count": cold_owner_count,
            },
        )

    return DatasetProfile(
        version=REHEARSAL_DATASET_VERSION,
        source_messages=message_count,
        owners=owner_count,
        hot_owner_percent=10,
        hot_message_percent=70,
        artifact_owners=artifact_owner_count,
        sections_per_artifact_run=4,
        claims_per_artifact_run=8,
        events_per_artifact_run=6,
    )


def _seed_artifact_fanout(connection: Any, artifact_owner_count: int) -> None:
    connection.execute(
        text(
            """
            insert into public.chat_sessions (
              id, user_id, title, status, scope_snapshot
            )
            select
              (
                '41000000-0000-4000-8000-'
                || lpad(to_hex(owner_index), 12, '0')
              )::uuid,
              (
                '40000000-0000-4000-8000-'
                || lpad(to_hex(owner_index), 12, '0')
              )::uuid,
              'E1.7 artifact fan-out',
              'complete',
              '{"rehearsal": true}'::jsonb
            from generate_series(1, :artifact_owner_count) as owner(owner_index)
            """
        ),
        {"artifact_owner_count": artifact_owner_count},
    )
    connection.execute(
        text(
            """
            insert into public.chat_messages (
              public_id, session_id, user_id, role, content, created_at
            )
            select
              (
                case role_index
                  when 1 then '42000000-0000-4000-8000-'
                  else '43000000-0000-4000-8000-'
                end || lpad(to_hex(owner_index), 12, '0')
              )::uuid,
              (
                '41000000-0000-4000-8000-'
                || lpad(to_hex(owner_index), 12, '0')
              )::uuid,
              (
                '40000000-0000-4000-8000-'
                || lpad(to_hex(owner_index), 12, '0')
              )::uuid,
              case role_index when 1 then 'user' else 'assistant' end,
              'e1.7-artifact-message:' || owner_index || ':' || role_index,
              timestamptz '2026-02-01 00:00:00+00'
                + owner_index * interval '1 second'
                + role_index * interval '1 millisecond'
            from generate_series(1, :artifact_owner_count) as owner(owner_index)
            cross join generate_series(1, 2) as role(role_index)
            """
        ),
        {"artifact_owner_count": artifact_owner_count},
    )
    connection.execute(
        text(
            """
            insert into public.ask_runs (
              id,
              session_id,
              user_id,
              user_message_id,
              assistant_message_id,
              status,
              decision_record,
              orchestration_state
            )
            select
              (
                '44000000-0000-4000-8000-'
                || lpad(to_hex(owner.owner_index), 12, '0')
              )::uuid,
              owner.session_id,
              owner.user_id,
              user_message.id,
              assistant_message.id,
              'completed',
              '{"rehearsal": true}'::jsonb,
              '{"phase": "complete"}'::jsonb
            from (
              select
                owner_index,
                (
                  '41000000-0000-4000-8000-'
                  || lpad(to_hex(owner_index), 12, '0')
                )::uuid as session_id,
                (
                  '40000000-0000-4000-8000-'
                  || lpad(to_hex(owner_index), 12, '0')
                )::uuid as user_id
              from generate_series(1, :artifact_owner_count) as generated(owner_index)
            ) as owner
            join public.chat_messages user_message
              on user_message.session_id = owner.session_id
             and user_message.role = 'user'
            join public.chat_messages assistant_message
              on assistant_message.session_id = owner.session_id
             and assistant_message.role = 'assistant'
            """
        ),
        {"artifact_owner_count": artifact_owner_count},
    )
    connection.execute(
        text(
            """
            insert into public.ask_sections (
              id,
              run_id,
              session_id,
              user_id,
              ordinal,
              section_type,
              status,
              knowledge_mode,
              provenance_label,
              title,
              content
            )
            select
              md5(run.id::text || ':section:' || ordinal)::uuid,
              run.id,
              run.session_id,
              run.user_id,
              ordinal,
              'summary',
              'completed',
              'official',
              'Internal Regulatory Corpus',
              'Rehearsal section ' || ordinal,
              '{"rehearsal": true}'::jsonb
            from public.ask_runs run
            cross join generate_series(0, 3) as section(ordinal)
            where run.decision_record @> '{"rehearsal": true}'::jsonb
            """
        )
    )
    connection.execute(
        text(
            """
            insert into public.ask_claims (
              id,
              run_id,
              section_id,
              session_id,
              user_id,
              ordinal,
              knowledge_mode,
              claim_text,
              support_status
            )
            select
              md5(section.id::text || ':claim:' || claim.ordinal)::uuid,
              section.run_id,
              section.id,
              section.session_id,
              section.user_id,
              claim.ordinal,
              'official',
              'Rehearsal claim ' || claim.ordinal,
              'pending'
            from public.ask_sections section
            cross join generate_series(0, 1) as claim(ordinal)
            where section.content @> '{"rehearsal": true}'::jsonb
            """
        )
    )
    connection.execute(
        text(
            """
            insert into public.ask_run_events (
              run_id,
              session_id,
              user_id,
              sequence,
              event_type,
              status,
              payload
            )
            select
              run.id,
              run.session_id,
              run.user_id,
              event.sequence,
              'rehearsal',
              'completed',
              '{"rehearsal": true}'::jsonb
            from public.ask_runs run
            cross join generate_series(0, 5) as event(sequence)
            where run.decision_record @> '{"rehearsal": true}'::jsonb
            """
        )
    )


def count_ordering_mismatches(engine: Engine) -> int:
    with engine.connect() as connection:
        return connection.execute(
            text(
                """
                select count(*)
                from (
                  select
                    session.id,
                    session.created_at,
                    session.last_message_at,
                    min(message.created_at) as expected_first_message_at,
                    max(message.created_at) as expected_last_message_at
                  from public.chat_sessions session
                  join public.chat_messages message
                    on message.session_id = session.id
                  where session.scope_snapshot
                    @> '{"legacy_backfill": true}'::jsonb
                  group by
                    session.id,
                    session.created_at,
                    session.last_message_at
                ) ordered_session
                where ordered_session.created_at
                        is distinct from ordered_session.expected_first_message_at
                   or ordered_session.last_message_at
                        is distinct from ordered_session.expected_last_message_at
                """
            )
        ).scalar_one()


def _verify_flag_off_rollback(engine: Engine) -> bool:
    with engine.connect() as connection:
        transaction = connection.begin()
        try:
            user_id = connection.execute(
                text(
                    """
                    select id
                    from auth.users
                    where email like 'e17-owner-%'
                    order by id
                    limit 1
                    """
                )
            ).scalar_one()
            row = connection.execute(
                text(
                    """
                    insert into public.chat_messages (user_id, role, content)
                    values (:user_id, 'user', 'e1.7-rollback-compatibility-probe')
                    returning public_id, session_id
                    """
                ),
                {"user_id": user_id},
            ).one()
            return row.public_id is None and row.session_id is None
        finally:
            transaction.rollback()


def run_volume_rehearsal(
    engine: Engine,
    migrations_directory: Path,
    *,
    dataset: DatasetProfile,
    observed_database_cpu_peak_percent: float,
    observed_replica_lag_peak_seconds: float,
    observed_lock_wait_peak_ms: int,
    batch_size: int = DEFAULT_BATCH_SIZE,
    batch_pause_seconds: float = APPROVED_BATCH_PAUSE_SECONDS,
    minimum_messages: int = MINIMUM_REHEARSAL_MESSAGES,
    operational_observation_provider: (
        Callable[[], tuple[float, float, int]] | None
    ) = None,
) -> MigrationRehearsalReport:
    started_at = datetime.now(UTC)
    preflight = capture_database_preflight(engine)
    if preflight.migration_head != "0022":
        raise ValueError("rehearsal must start at migration head 0022")
    if dataset.source_messages < minimum_messages:
        raise ValueError(f"dataset must contain at least {minimum_messages} messages")
    if preflight.legacy_pending_count != dataset.source_messages:
        raise ValueError("preflight pending count does not match the dataset profile")

    source_count, source_hash = canonical_business_hash(engine)
    expand_started_at = perf_counter()
    expanded = apply_pending_migrations(
        engine,
        migrations_directory,
        through="0024",
    )
    expand_duration_ms = max(
        0,
        round((perf_counter() - expand_started_at) * 1000),
    )
    if [migration.version for migration in expanded] != ["0023", "0024"]:
        raise ValueError("expand phase must apply exactly migrations 0023 and 0024")
    with engine.begin() as connection:
        _seed_artifact_fanout(connection, dataset.artifact_owners)

    backfill: BackfillResult = run_backfill(
        engine,
        batch_size=batch_size,
        batch_pause_seconds=batch_pause_seconds,
    )
    target_count, target_hash = canonical_business_hash(engine)
    ordering_mismatches = count_ordering_mismatches(engine)

    validation_started_at = perf_counter()
    applied = apply_pending_migrations(
        engine,
        migrations_directory,
        through="0025",
    )
    validate_duration_ms = max(
        0,
        round((perf_counter() - validation_started_at) * 1000),
    )
    if [migration.version for migration in applied] != ["0025"]:
        raise ValueError("validation phase must apply exactly migration 0025")

    rollback_compatible = _verify_flag_off_rollback(engine)
    postflight = capture_database_preflight(engine)
    if operational_observation_provider is not None:
        (
            observed_database_cpu_peak_percent,
            observed_replica_lag_peak_seconds,
            observed_lock_wait_peak_ms,
        ) = operational_observation_provider()
    verification = backfill.verification
    reconciliation = ReconciliationReport(
        source_business_hash=source_hash,
        target_business_hash=target_hash,
        eligible_source_count=source_count,
        backfilled_target_count=verification.backfilled_message_count,
        pending_count=verification.pending_message_count,
        ownership_mismatches=verification.ownership_mismatch_count,
        ordering_mismatches=ordering_mismatches,
        lineage_mismatches=(
            verification.public_id_mismatch_count
            + verification.session_id_mismatch_count
            + verification.event_scope_mismatch_count
            + verification.session_metadata_mismatch_count
        ),
        duplicate_scope_count=verification.duplicate_scope_session_count,
        orphan_session_count=verification.orphan_session_count,
        hash_match=source_hash == target_hash,
        count_match=(
            source_count == dataset.source_messages
            and verification.backfilled_message_count == dataset.source_messages
        ),
    )
    deadlock_delta = postflight.deadlocks - preflight.deadlocks
    acceptance_passed = all(
        (
            dataset.source_messages >= minimum_messages,
            backfill.status == "complete",
            backfill.batches_over_budget == 0,
            reconciliation.hash_match,
            reconciliation.count_match,
            reconciliation.pending_count == 0,
            reconciliation.ownership_mismatches == 0,
            reconciliation.ordering_mismatches == 0,
            reconciliation.lineage_mismatches == 0,
            reconciliation.duplicate_scope_count == 0,
            reconciliation.orphan_session_count == 0,
            rollback_compatible,
            deadlock_delta == 0,
            observed_database_cpu_peak_percent < 70,
            observed_replica_lag_peak_seconds < 30,
            observed_lock_wait_peak_ms < APPROVED_LOCK_WAIT_PEAK_MS,
        )
    )
    return MigrationRehearsalReport(
        report_version="1.0.0",
        started_at=started_at.isoformat(),
        completed_at=datetime.now(UTC).isoformat(),
        preflight=preflight,
        dataset=dataset,
        expand_duration_ms=expand_duration_ms,
        backfill=backfill.to_dict(),
        validate_duration_ms=validate_duration_ms,
        reconciliation=reconciliation,
        rollback_compatible=rollback_compatible,
        deadlock_delta=deadlock_delta,
        approved_batch_size=DEFAULT_BATCH_SIZE,
        approved_batch_pause_seconds=APPROVED_BATCH_PAUSE_SECONDS,
        approved_max_batch_transaction_seconds=(
            APPROVED_MAX_BATCH_TRANSACTION_SECONDS
        ),
        approved_lock_wait_peak_ms=APPROVED_LOCK_WAIT_PEAK_MS,
        observed_lock_wait_peak_ms=observed_lock_wait_peak_ms,
        observed_replica_lag_peak_seconds=observed_replica_lag_peak_seconds,
        observed_database_cpu_peak_percent=observed_database_cpu_peak_percent,
        acceptance_passed=acceptance_passed,
    )


def render_markdown_report(report: MigrationRehearsalReport) -> str:
    status = "PASS" if report.acceptance_passed else "FAIL"
    reconciliation = report.reconciliation
    return "\n".join(
        (
            "# E1.7 Production-Volume Migration Rehearsal Report",
            "",
            f"**Result:** {status}",
            f"**Report version:** `{report.report_version}`",
            f"**Started:** {report.started_at}",
            f"**Completed:** {report.completed_at}",
            "",
            "## Dataset",
            "",
            f"- Source messages: {report.dataset.source_messages:,}",
            f"- Owners: {report.dataset.owners:,}",
            (
                f"- Ownership skew: {report.dataset.hot_owner_percent}% of owners "
                f"hold {report.dataset.hot_message_percent}% of messages"
            ),
            f"- Artifact-bearing owners: {report.dataset.artifact_owners:,}",
            "",
            "## Timing and operational envelope",
            "",
            f"- Expand duration: {report.expand_duration_ms:,} ms",
            f"- Backfill duration: {report.backfill['duration_ms']:,} ms",
            (
                "- Maximum batch transaction: "
                f"{report.backfill['max_batch_duration_ms']:,} ms"
            ),
            f"- Validation duration: {report.validate_duration_ms:,} ms",
            (
                "- Database CPU five-minute rolling peak: "
                f"{report.observed_database_cpu_peak_percent:.2f}%"
            ),
            (
                "- Replica lag peak: "
                f"{report.observed_replica_lag_peak_seconds:.3f} seconds"
            ),
            f"- Lock-wait peak: {report.observed_lock_wait_peak_ms} ms",
            f"- Deadlocks caused: {report.deadlock_delta}",
            "",
            "## Reconciliation",
            "",
            f"- Source count: {reconciliation.eligible_source_count:,}",
            f"- Target count: {reconciliation.backfilled_target_count:,}",
            f"- Source SHA-256: `{reconciliation.source_business_hash}`",
            f"- Target SHA-256: `{reconciliation.target_business_hash}`",
            f"- Count match: {reconciliation.count_match}",
            f"- Hash match: {reconciliation.hash_match}",
            f"- Pending rows: {reconciliation.pending_count}",
            f"- Ownership mismatches: {reconciliation.ownership_mismatches}",
            f"- Ordering mismatches: {reconciliation.ordering_mismatches}",
            f"- Lineage mismatches: {reconciliation.lineage_mismatches}",
            f"- Duplicate scopes: {reconciliation.duplicate_scope_count}",
            f"- Orphan sessions: {reconciliation.orphan_session_count}",
            "",
            "## Rollback",
            "",
            (
                "- Flag-off null/null legacy-write compatibility: "
                f"{report.rollback_compatible}"
            ),
            "- Rollback retains additive schema and completed backfill identities.",
            "- Contract remains a separate change after the approved hold period.",
            "",
            "## Approval",
            "",
            (
                "The rehearsal satisfies B-010 and E1.7 acceptance criteria."
                if report.acceptance_passed
                else "The rehearsal does not satisfy B-010; production migration is blocked."
            ),
            "",
        )
    )
