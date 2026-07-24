from __future__ import annotations

import hashlib
import re
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.exc import SQLAlchemyError

MIGRATION_FILENAME_PATTERN = re.compile(r"^(?P<version>[0-9]{4,})_[a-z0-9][a-z0-9_]*\.sql$")
MIGRATION_ADVISORY_LOCK_ID = 7_428_031_821_907_624_011
LEGACY_BASELINE_MAX_VERSION = "0016"

CREATE_MIGRATION_TABLE_SQL = """
create table if not exists public.schema_migrations (
  version varchar(64) not null,
  filename text not null,
  checksum char(64) not null,
  applied_at timestamptz not null default now(),
  constraint schema_migrations_pkey primary key (version),
  constraint schema_migrations_filename_key unique (filename),
  constraint schema_migrations_version_chk
    check (version ~ '^[0-9]{4,}$'),
  constraint schema_migrations_checksum_chk
    check (checksum ~ '^[0-9a-f]{64}$')
)
"""

HARDEN_MIGRATION_TABLE_SQL = """
do $migration_table_permissions$
declare
  database_role text;
begin
  revoke all privileges on table public.schema_migrations from public;

  foreach database_role in array array['anon', 'authenticated', 'service_role']
  loop
    if exists (select 1 from pg_roles where rolname = database_role) then
      execute format(
        'revoke all privileges on table public.schema_migrations from %%I',
        database_role
      );
    end if;
  end loop;
end
$migration_table_permissions$
"""

LOAD_HISTORY_SQL = """
select version, filename, checksum, applied_at
from public.schema_migrations
"""

LOAD_MIGRATION_TABLE_COLUMNS_SQL = """
select
  column_name,
  data_type,
  is_nullable,
  character_maximum_length,
  column_default
from information_schema.columns
where table_schema = 'public'
  and table_name = 'schema_migrations'
"""

LOAD_MIGRATION_TABLE_CONSTRAINTS_SQL = """
select constraint_record.conname, constraint_record.contype
from pg_constraint constraint_record
where constraint_record.conrelid = 'public.schema_migrations'::regclass
"""

INSERT_HISTORY_SQL = """
insert into public.schema_migrations (version, filename, checksum)
values (:version, :filename, :checksum)
"""

VERIFY_0021_AUTH_SESSION_COLUMNS_SQL = """
select count(*) = 2
from information_schema.columns
where table_schema = 'identity'
  and table_name = 'auth_sessions'
  and (
    (
      column_name = 'refresh_token_hash'
      and udt_schema = 'pg_catalog'
      and udt_name = 'bytea'
      and is_nullable = 'YES'
    )
    or (
      column_name = 'refresh_generation'
      and udt_schema = 'pg_catalog'
      and udt_name = 'int8'
      and is_nullable = 'NO'
      and column_default like '0%'
    )
  )
"""

VERIFY_0021_AUTH_SESSION_CONSTRAINTS_SQL = """
select
  count(*) = 2
  and bool_and(
    case constraint_record.conname
      when 'identity_auth_sessions_refresh_token_hash_length_chk'
        then pg_get_constraintdef(constraint_record.oid, true)
          = 'CHECK (refresh_token_hash IS NULL OR octet_length(refresh_token_hash) = 32)'
      when 'identity_auth_sessions_refresh_generation_chk'
        then pg_get_constraintdef(constraint_record.oid, true)
          = 'CHECK (refresh_generation >= 0)'
      else false
    end
  )
from pg_constraint constraint_record
where constraint_record.conrelid = 'identity.auth_sessions'::regclass
  and constraint_record.contype = 'c'
  and constraint_record.convalidated
  and constraint_record.conname in (
    'identity_auth_sessions_refresh_token_hash_length_chk',
    'identity_auth_sessions_refresh_generation_chk'
  )
"""

VERIFY_0021_AUTH_SESSION_INDEX_SQL = """
select exists (
  select 1
  from pg_index index_record
  join pg_class index_relation
    on index_relation.oid = index_record.indexrelid
  where index_record.indrelid = 'identity.auth_sessions'::regclass
    and index_relation.relname = 'identity_auth_sessions_refresh_token_hash_idx'
    and index_record.indisunique
    and index_record.indisvalid
    and index_record.indisready
    and pg_get_indexdef(index_record.indexrelid)
      = 'CREATE UNIQUE INDEX identity_auth_sessions_refresh_token_hash_idx '
        'ON identity.auth_sessions USING btree (refresh_token_hash) '
        'WHERE (refresh_token_hash IS NOT NULL)'
)
"""

VERIFY_0021_RATE_LIMIT_COLUMNS_SQL = """
select
  count(*) = 6
  and count(*) filter (
    where column_name = 'scope'
      and udt_name = 'text'
      and is_nullable = 'NO'
  ) = 1
  and count(*) filter (
    where column_name = 'subject_hash'
      and udt_name = 'bytea'
      and is_nullable = 'NO'
  ) = 1
  and count(*) filter (
    where column_name = 'window_started_at'
      and udt_name = 'timestamptz'
      and is_nullable = 'NO'
  ) = 1
  and count(*) filter (
    where column_name = 'attempts'
      and udt_name = 'int4'
      and is_nullable = 'NO'
      and column_default like '0%'
  ) = 1
  and count(*) filter (
    where column_name = 'blocked_until'
      and udt_name = 'timestamptz'
      and is_nullable = 'YES'
  ) = 1
  and count(*) filter (
    where column_name = 'updated_at'
      and udt_name = 'timestamptz'
      and is_nullable = 'NO'
      and column_default ilike '%now()%'
  ) = 1
from information_schema.columns
where table_schema = 'identity'
  and table_name = 'authentication_rate_limits'
"""

VERIFY_0021_RATE_LIMIT_CONSTRAINTS_SQL = """
select
  count(*) = 5
  and bool_and(
    case constraint_record.conname
      when 'authentication_rate_limits_pkey'
        then pg_get_constraintdef(constraint_record.oid, true)
          = 'PRIMARY KEY (scope, subject_hash)'
      when 'identity_authentication_rate_limits_scope_chk'
        then pg_get_constraintdef(constraint_record.oid, true)
          = 'CHECK (length(scope) >= 3 AND length(scope) <= 100 '
            'AND scope ~ ''^[a-z][a-z0-9_]*\\.[a-z][a-z0-9_]*$''::text)'
      when 'identity_authentication_rate_limits_subject_hash_length_chk'
        then pg_get_constraintdef(constraint_record.oid, true)
          = 'CHECK (octet_length(subject_hash) = 32)'
      when 'identity_authentication_rate_limits_attempts_chk'
        then pg_get_constraintdef(constraint_record.oid, true)
          = 'CHECK (attempts >= 0)'
      when 'identity_authentication_rate_limits_blocked_until_chk'
        then pg_get_constraintdef(constraint_record.oid, true)
          = 'CHECK (blocked_until IS NULL OR blocked_until >= window_started_at)'
      else false
    end
  )
from pg_constraint constraint_record
where constraint_record.conrelid = 'identity.authentication_rate_limits'::regclass
  and constraint_record.convalidated
  and (
    (
      constraint_record.conname = 'authentication_rate_limits_pkey'
      and constraint_record.contype = 'p'
    )
    or (
      constraint_record.conname in (
        'identity_authentication_rate_limits_scope_chk',
        'identity_authentication_rate_limits_subject_hash_length_chk',
        'identity_authentication_rate_limits_attempts_chk',
        'identity_authentication_rate_limits_blocked_until_chk'
      )
      and constraint_record.contype = 'c'
    )
  )
"""

VERIFY_0021_RATE_LIMIT_INDEXES_SQL = """
select
  count(*) = 2
  and bool_and(
    case index_relation.relname
      when 'identity_authentication_rate_limits_blocked_until_idx'
        then pg_get_indexdef(index_record.indexrelid)
          = 'CREATE INDEX identity_authentication_rate_limits_blocked_until_idx '
            'ON identity.authentication_rate_limits USING btree (blocked_until) '
            'WHERE (blocked_until IS NOT NULL)'
      when 'identity_authentication_rate_limits_updated_at_idx'
        then pg_get_indexdef(index_record.indexrelid)
          = 'CREATE INDEX identity_authentication_rate_limits_updated_at_idx '
            'ON identity.authentication_rate_limits USING btree (updated_at)'
      else false
    end
  )
from pg_index index_record
join pg_class index_relation
  on index_relation.oid = index_record.indexrelid
where index_record.indrelid = 'identity.authentication_rate_limits'::regclass
  and index_record.indisvalid
  and index_record.indisready
  and index_relation.relname in (
    'identity_authentication_rate_limits_blocked_until_idx',
    'identity_authentication_rate_limits_updated_at_idx'
  )
"""

VERIFY_0021_PUBLIC_PRIVILEGES_SQL = """
select not exists (
  select 1
  from pg_class relation
  cross join lateral aclexplode(
    coalesce(relation.relacl, '{}'::aclitem[])
  ) privilege
  where relation.oid = 'identity.authentication_rate_limits'::regclass
    and privilege.grantee = 0
)
"""

VERIFY_0022_SESSION_EXCHANGE_COLUMNS_SQL = """
select
  count(*) = 11
  and count(*) filter (
    where column_name = 'id'
      and udt_name = 'uuid'
      and is_nullable = 'NO'
      and column_default ilike '%gen_random_uuid()%'
  ) = 1
  and count(*) filter (
    where column_name = 'source' and udt_name = 'text' and is_nullable = 'NO'
  ) = 1
  and count(*) filter (
    where column_name = 'source_session_hash'
      and udt_name = 'bytea'
      and is_nullable = 'NO'
  ) = 1
  and count(*) filter (
    where column_name = 'user_id' and udt_name = 'uuid' and is_nullable = 'NO'
  ) = 1
  and count(*) filter (
    where column_name = 'identity_session_id'
      and udt_name = 'uuid'
      and is_nullable = 'NO'
  ) = 1
  and count(*) filter (
    where column_name = 'source_authenticated_at'
      and udt_name = 'timestamptz'
      and is_nullable = 'NO'
  ) = 1
  and count(*) filter (
    where column_name = 'source_expires_at'
      and udt_name = 'timestamptz'
      and is_nullable = 'YES'
  ) = 1
  and count(*) filter (
    where column_name = 'exchanged_at'
      and udt_name = 'timestamptz'
      and is_nullable = 'NO'
      and column_default ilike '%now()%'
  ) = 1
  and count(*) filter (
    where column_name = 'request_id' and udt_name = 'text' and is_nullable = 'YES'
  ) = 1
  and count(*) filter (
    where column_name = 'ip_hash' and udt_name = 'bytea' and is_nullable = 'YES'
  ) = 1
  and count(*) filter (
    where column_name = 'user_agent_hash'
      and udt_name = 'bytea'
      and is_nullable = 'YES'
  ) = 1
from information_schema.columns
where table_schema = 'identity'
  and table_name = 'session_exchanges'
"""

VERIFY_0022_SESSION_EXCHANGE_CONSTRAINTS_SQL = """
select
  count(*) = 10
  and count(*) filter (
    where constraint_record.contype = 'f'
      and constraint_record.confdeltype = 'c'
      and constraint_record.conname in (
        'session_exchanges_user_id_fkey',
        'session_exchanges_identity_session_id_fkey'
      )
  ) = 2
  and bool_and(
    case constraint_record.conname
      when 'session_exchanges_pkey'
        then pg_get_constraintdef(constraint_record.oid, true)
          = 'PRIMARY KEY (id)'
      when 'session_exchanges_user_id_fkey'
        then pg_get_constraintdef(constraint_record.oid, true)
          = 'FOREIGN KEY (user_id) REFERENCES identity.users(id) ON DELETE CASCADE'
      when 'session_exchanges_identity_session_id_fkey'
        then pg_get_constraintdef(constraint_record.oid, true)
          = 'FOREIGN KEY (identity_session_id) '
            'REFERENCES identity.auth_sessions(sid) ON DELETE CASCADE'
      when 'identity_session_exchanges_source_chk'
        then pg_get_constraintdef(constraint_record.oid, true)
          = 'CHECK (source = ''supabase''::text)'
      when 'identity_session_exchanges_source_session_hash_length_chk'
        then pg_get_constraintdef(constraint_record.oid, true)
          = 'CHECK (octet_length(source_session_hash) = 32)'
      when 'identity_session_exchanges_source_session_hash_key'
        then pg_get_constraintdef(constraint_record.oid, true)
          = 'UNIQUE (source_session_hash)'
      when 'identity_session_exchanges_source_expiry_chk'
        then pg_get_constraintdef(constraint_record.oid, true)
          = 'CHECK (source_expires_at IS NULL '
            'OR source_expires_at > source_authenticated_at)'
      when 'identity_session_exchanges_request_id_chk'
        then pg_get_constraintdef(constraint_record.oid, true)
          = 'CHECK (request_id IS NULL OR length(request_id) <= 200)'
      when 'identity_session_exchanges_ip_hash_length_chk'
        then pg_get_constraintdef(constraint_record.oid, true)
          = 'CHECK (ip_hash IS NULL OR octet_length(ip_hash) = 32)'
      when 'identity_session_exchanges_user_agent_hash_length_chk'
        then pg_get_constraintdef(constraint_record.oid, true)
          = 'CHECK (user_agent_hash IS NULL OR octet_length(user_agent_hash) = 32)'
      else false
    end
  )
from pg_constraint constraint_record
where constraint_record.conrelid = 'identity.session_exchanges'::regclass
  and constraint_record.convalidated
  and constraint_record.conname in (
    'session_exchanges_pkey',
    'session_exchanges_user_id_fkey',
    'session_exchanges_identity_session_id_fkey',
    'identity_session_exchanges_source_chk',
    'identity_session_exchanges_source_session_hash_length_chk',
    'identity_session_exchanges_source_session_hash_key',
    'identity_session_exchanges_source_expiry_chk',
    'identity_session_exchanges_request_id_chk',
    'identity_session_exchanges_ip_hash_length_chk',
    'identity_session_exchanges_user_agent_hash_length_chk'
  )
"""

VERIFY_0022_SESSION_EXCHANGE_INDEXES_SQL = """
select
  count(*) = 2
  and bool_and(
    case index_relation.relname
      when 'identity_session_exchanges_user_idx'
        then pg_get_indexdef(index_record.indexrelid)
          = 'CREATE INDEX identity_session_exchanges_user_idx '
            'ON identity.session_exchanges USING btree (user_id, exchanged_at DESC)'
      when 'identity_session_exchanges_identity_session_idx'
        then pg_get_indexdef(index_record.indexrelid)
          = 'CREATE INDEX identity_session_exchanges_identity_session_idx '
            'ON identity.session_exchanges USING btree (identity_session_id)'
      else false
    end
  )
from pg_index index_record
join pg_class index_relation
  on index_relation.oid = index_record.indexrelid
where index_record.indrelid = 'identity.session_exchanges'::regclass
  and index_record.indisvalid
  and index_record.indisready
  and index_relation.relname in (
    'identity_session_exchanges_user_idx',
    'identity_session_exchanges_identity_session_idx'
  )
"""

VERIFY_0022_METRIC_COLUMNS_SQL = """
select
  count(*) = 6
  and count(*) filter (
    where column_name = 'bucket_started_at'
      and udt_name = 'timestamptz'
      and is_nullable = 'NO'
  ) = 1
  and count(*) filter (
    where column_name = 'source' and udt_name = 'text' and is_nullable = 'NO'
  ) = 1
  and count(*) filter (
    where column_name = 'outcome' and udt_name = 'text' and is_nullable = 'NO'
  ) = 1
  and count(*) filter (
    where column_name = 'reason_code'
      and udt_name = 'text'
      and is_nullable = 'NO'
      and column_default = $default$''::text$default$
  ) = 1
  and count(*) filter (
    where column_name = 'observation_count'
      and udt_name = 'int8'
      and is_nullable = 'NO'
      and column_default like '0%'
  ) = 1
  and count(*) filter (
    where column_name = 'updated_at'
      and udt_name = 'timestamptz'
      and is_nullable = 'NO'
      and column_default ilike '%now()%'
  ) = 1
from information_schema.columns
where table_schema = 'identity'
  and table_name = 'authentication_metrics_hourly'
"""

VERIFY_0022_METRIC_CONSTRAINTS_SQL = """
select
  count(*) = 5
  and bool_and(
    case constraint_record.conname
      when 'authentication_metrics_hourly_pkey'
        then pg_get_constraintdef(constraint_record.oid, true)
          = 'PRIMARY KEY (bucket_started_at, source, outcome, reason_code)'
      when 'identity_authentication_metrics_source_chk'
        then pg_get_constraintdef(constraint_record.oid, true)
          = 'CHECK (source = ANY '
            '(ARRAY[''supabase''::text, ''identity''::text, ''unknown''::text]))'
      when 'identity_authentication_metrics_outcome_chk'
        then pg_get_constraintdef(constraint_record.oid, true)
          = 'CHECK (outcome = ANY '
            '(ARRAY[''success''::text, ''failure''::text, ''denied''::text]))'
      when 'identity_authentication_metrics_reason_code_chk'
        then pg_get_constraintdef(constraint_record.oid, true)
          = 'CHECK (reason_code = ''''::text '
            'OR reason_code ~ ''^[A-Z][A-Z0-9_]{0,99}$''::text)'
      when 'identity_authentication_metrics_count_chk'
        then pg_get_constraintdef(constraint_record.oid, true)
          = 'CHECK (observation_count > 0)'
      else false
    end
  )
from pg_constraint constraint_record
where constraint_record.conrelid = 'identity.authentication_metrics_hourly'::regclass
  and constraint_record.convalidated
  and constraint_record.conname in (
    'authentication_metrics_hourly_pkey',
    'identity_authentication_metrics_source_chk',
    'identity_authentication_metrics_outcome_chk',
    'identity_authentication_metrics_reason_code_chk',
    'identity_authentication_metrics_count_chk'
  )
"""

VERIFY_0022_METRIC_INDEX_SQL = """
select exists (
  select 1
  from pg_index index_record
  join pg_class index_relation
    on index_relation.oid = index_record.indexrelid
  where index_record.indrelid = 'identity.authentication_metrics_hourly'::regclass
    and index_relation.relname = 'identity_authentication_metrics_updated_at_idx'
    and index_record.indisvalid
    and index_record.indisready
    and pg_get_indexdef(index_record.indexrelid)
      = 'CREATE INDEX identity_authentication_metrics_updated_at_idx '
        'ON identity.authentication_metrics_hourly USING btree (updated_at)'
)
"""

VERIFY_0022_METRIC_VIEW_SQL = """
select
  relation.relkind = 'v'
  and coalesce(relation.reloptions, '{}'::text[]) @> array['security_invoker=true']
  and position(
    'identity.authentication_metrics_hourly' in pg_get_viewdef(relation.oid, true)
  ) > 0
  and position('24:00:00' in pg_get_viewdef(relation.oid, true)) > 0
from pg_class relation
join pg_namespace namespace on namespace.oid = relation.relnamespace
where namespace.nspname = 'identity'
  and relation.relname = 'dual_authentication_metrics'
"""

VERIFY_0022_PUBLIC_PRIVILEGES_SQL = """
select not exists (
  select 1
  from pg_class relation
  cross join lateral aclexplode(
    coalesce(relation.relacl, '{}'::aclitem[])
  ) privilege
  where relation.oid in (
    'identity.session_exchanges'::regclass,
    'identity.authentication_metrics_hourly'::regclass,
    'identity.dual_authentication_metrics'::regclass
  )
    and privilege.grantee = 0
)
"""

EXPECTED_MIGRATION_TABLE_COLUMNS = {
    "version": ("character varying", "NO", 64),
    "filename": ("text", "NO", None),
    "checksum": ("character", "NO", 64),
    "applied_at": ("timestamp with time zone", "NO", None),
}

EXPECTED_MIGRATION_TABLE_CONSTRAINTS = {
    "schema_migrations_pkey": "p",
    "schema_migrations_filename_key": "u",
    "schema_migrations_version_chk": "c",
    "schema_migrations_checksum_chk": "c",
}


class MigrationError(RuntimeError):
    """Base class for migration discovery, history, and execution errors."""


class MigrationPlanError(MigrationError):
    """The local migration set or requested operation is invalid."""


class MigrationDriftError(MigrationError):
    """Applied migration history no longer matches the repository."""


@dataclass(frozen=True, slots=True)
class ExistingObjectCheck:
    description: str
    sql: str


@dataclass(frozen=True, slots=True)
class ExistingMigrationSpec:
    checksum: str
    checks: tuple[ExistingObjectCheck, ...]


EXISTING_MIGRATION_SPECS = {
    "0021": ExistingMigrationSpec(
        checksum="52d3f5c1d45c6448018ee0f6763c0f6849f14459247202e351e340d3de106edd",
        checks=(
            ExistingObjectCheck(
                "identity.auth_sessions refresh-token columns",
                VERIFY_0021_AUTH_SESSION_COLUMNS_SQL,
            ),
            ExistingObjectCheck(
                "identity.auth_sessions refresh-token constraints",
                VERIFY_0021_AUTH_SESSION_CONSTRAINTS_SQL,
            ),
            ExistingObjectCheck(
                "identity.auth_sessions refresh-token unique partial index",
                VERIFY_0021_AUTH_SESSION_INDEX_SQL,
            ),
            ExistingObjectCheck(
                "identity.authentication_rate_limits columns",
                VERIFY_0021_RATE_LIMIT_COLUMNS_SQL,
            ),
            ExistingObjectCheck(
                "identity.authentication_rate_limits constraints",
                VERIFY_0021_RATE_LIMIT_CONSTRAINTS_SQL,
            ),
            ExistingObjectCheck(
                "identity.authentication_rate_limits indexes",
                VERIFY_0021_RATE_LIMIT_INDEXES_SQL,
            ),
            ExistingObjectCheck(
                "identity.authentication_rate_limits public privileges",
                VERIFY_0021_PUBLIC_PRIVILEGES_SQL,
            ),
        ),
    ),
    "0022": ExistingMigrationSpec(
        checksum="4157c14e5f036271fc0a0f3cb4f00574c1e8a80b004f8b8e33c5fbfedbe69e46",
        checks=(
            ExistingObjectCheck(
                "identity.session_exchanges columns",
                VERIFY_0022_SESSION_EXCHANGE_COLUMNS_SQL,
            ),
            ExistingObjectCheck(
                "identity.session_exchanges constraints and cascading foreign keys",
                VERIFY_0022_SESSION_EXCHANGE_CONSTRAINTS_SQL,
            ),
            ExistingObjectCheck(
                "identity.session_exchanges indexes",
                VERIFY_0022_SESSION_EXCHANGE_INDEXES_SQL,
            ),
            ExistingObjectCheck(
                "identity.authentication_metrics_hourly columns",
                VERIFY_0022_METRIC_COLUMNS_SQL,
            ),
            ExistingObjectCheck(
                "identity.authentication_metrics_hourly constraints",
                VERIFY_0022_METRIC_CONSTRAINTS_SQL,
            ),
            ExistingObjectCheck(
                "identity.authentication_metrics_hourly index",
                VERIFY_0022_METRIC_INDEX_SQL,
            ),
            ExistingObjectCheck(
                "identity.dual_authentication_metrics security-invoker view",
                VERIFY_0022_METRIC_VIEW_SQL,
            ),
            ExistingObjectCheck(
                "PR #3 and PR #4 public privilege revocations",
                VERIFY_0022_PUBLIC_PRIVILEGES_SQL,
            ),
        ),
    ),
}


@dataclass(frozen=True, slots=True)
class MigrationFile:
    version: str
    filename: str
    path: Path
    checksum: str

    @classmethod
    def from_path(cls, path: Path) -> MigrationFile:
        match = MIGRATION_FILENAME_PATTERN.fullmatch(path.name)
        if match is None:
            raise MigrationPlanError(
                f"Invalid migration filename {path.name!r}; expected NNNN_descriptive_name.sql"
            )
        return cls(
            version=match.group("version"),
            filename=path.name,
            path=path,
            checksum=hashlib.sha256(path.read_bytes()).hexdigest(),
        )

    def read_sql(self) -> str:
        return self.path.read_text(encoding="utf-8")


@dataclass(frozen=True, slots=True)
class AppliedMigration:
    version: str
    filename: str
    checksum: str
    applied_at: datetime


@dataclass(frozen=True, slots=True)
class MigrationStatus:
    applied: tuple[AppliedMigration, ...]
    pending: tuple[MigrationFile, ...]


def discover_migrations(directory: Path) -> tuple[MigrationFile, ...]:
    if not directory.is_dir():
        raise MigrationPlanError(f"Migration directory does not exist: {directory}")

    migrations = tuple(
        sorted(
            (MigrationFile.from_path(path) for path in directory.glob("*.sql")),
            key=lambda migration: (int(migration.version), migration.filename),
        )
    )
    if not migrations:
        raise MigrationPlanError(f"No SQL migrations found in {directory}")

    versions: set[str] = set()
    for migration in migrations:
        if migration.version in versions:
            raise MigrationPlanError(f"Duplicate migration version {migration.version!r}")
        versions.add(migration.version)

    return migrations


def plan_pending_migrations(
    migrations: Sequence[MigrationFile],
    applied: Sequence[AppliedMigration],
    *,
    through: str | None = None,
) -> tuple[MigrationFile, ...]:
    local_by_version = {migration.version: migration for migration in migrations}
    applied_by_version = {migration.version: migration for migration in applied}

    if len(applied_by_version) != len(applied):
        raise MigrationDriftError("Migration history contains duplicate versions")

    for recorded in applied:
        local = local_by_version.get(recorded.version)
        if local is None:
            raise MigrationDriftError(
                f"Applied migration {recorded.version} is missing from the repository"
            )
        if recorded.filename != local.filename:
            raise MigrationDriftError(
                f"Applied migration {recorded.version} filename changed: "
                f"{recorded.filename!r} != {local.filename!r}"
            )
        if recorded.checksum != local.checksum:
            raise MigrationDriftError(f"Applied migration {recorded.version} checksum changed")

    applied_versions = sorted(applied_by_version, key=int)
    expected_prefix = [migration.version for migration in migrations[: len(applied_versions)]]
    if applied_versions != expected_prefix:
        raise MigrationDriftError(
            "Applied migration history is not a contiguous prefix of local migrations"
        )

    pending = [migration for migration in migrations if migration.version not in applied_by_version]
    if through is not None:
        if through not in local_by_version:
            raise MigrationPlanError(f"Unknown target migration version {through!r}")
        pending = [migration for migration in pending if int(migration.version) <= int(through)]

    return tuple(pending)


def load_applied_migrations(connection: Connection) -> tuple[AppliedMigration, ...]:
    rows = connection.execute(text(LOAD_HISTORY_SQL)).mappings()
    return tuple(
        sorted(
            (
                AppliedMigration(
                    version=row["version"],
                    filename=row["filename"],
                    checksum=row["checksum"].strip(),
                    applied_at=row["applied_at"],
                )
                for row in rows
            ),
            key=lambda migration: int(migration.version),
        )
    )


def ensure_migration_table(connection: Connection) -> None:
    connection.exec_driver_sql(CREATE_MIGRATION_TABLE_SQL)
    connection.exec_driver_sql(HARDEN_MIGRATION_TABLE_SQL)
    validate_migration_table(connection)


def validate_migration_table(connection: Connection) -> None:
    column_rows = list(connection.execute(text(LOAD_MIGRATION_TABLE_COLUMNS_SQL)).mappings())
    columns = {
        row["column_name"]: (
            row["data_type"],
            row["is_nullable"],
            row["character_maximum_length"],
        )
        for row in column_rows
    }
    if columns != EXPECTED_MIGRATION_TABLE_COLUMNS:
        raise MigrationDriftError(
            "public.schema_migrations columns do not match the required ledger schema"
        )

    defaults = {row["column_name"]: row["column_default"] for row in column_rows}
    if not defaults["applied_at"] or "now()" not in defaults["applied_at"].lower():
        raise MigrationDriftError("public.schema_migrations.applied_at must default to now()")

    constraint_rows = connection.execute(text(LOAD_MIGRATION_TABLE_CONSTRAINTS_SQL)).mappings()
    constraints = {row["conname"]: row["contype"] for row in constraint_rows}
    for name, constraint_type in EXPECTED_MIGRATION_TABLE_CONSTRAINTS.items():
        if constraints.get(name) != constraint_type:
            raise MigrationDriftError(
                f"public.schema_migrations constraint {name!r} is missing or modified"
            )


def apply_migration(connection: Connection, migration: MigrationFile) -> None:
    """Execute SQL and record its checksum in the caller's transaction."""

    connection.exec_driver_sql(migration.read_sql())
    record_migration(connection, migration)


def record_migration(connection: Connection, migration: MigrationFile) -> None:
    """Record a migration without executing its SQL."""

    connection.execute(
        text(INSERT_HISTORY_SQL),
        {
            "version": migration.version,
            "filename": migration.filename,
            "checksum": migration.checksum,
        },
    )


def plan_existing_migrations(
    migrations: Sequence[MigrationFile],
    applied: Sequence[AppliedMigration],
    *,
    through: str,
) -> tuple[MigrationFile, ...]:
    pending = plan_pending_migrations(
        migrations,
        applied,
        through=through,
    )
    for migration in pending:
        specification = EXISTING_MIGRATION_SPECS.get(migration.version)
        if specification is None:
            raise MigrationPlanError(
                f"Migration {migration.version} cannot be marked existing because "
                "it has no registered schema verifier"
            )
        if migration.checksum != specification.checksum:
            raise MigrationDriftError(
                f"Migration {migration.version} does not match the checksum approved "
                "for mark-existing"
            )
    return pending


def verify_existing_migration(
    connection: Connection,
    migration: MigrationFile,
) -> None:
    specification = EXISTING_MIGRATION_SPECS.get(migration.version)
    if specification is None:
        raise MigrationPlanError(
            f"Migration {migration.version} has no registered schema verifier"
        )
    if migration.checksum != specification.checksum:
        raise MigrationDriftError(
            f"Migration {migration.version} does not match the checksum approved "
            "for mark-existing"
        )

    for check in specification.checks:
        try:
            verified = connection.execute(text(check.sql)).scalar_one_or_none()
        except SQLAlchemyError as exc:
            raise MigrationDriftError(
                f"Migration {migration.version} existing-schema verification failed: "
                f"{check.description}"
            ) from exc
        if verified is not True:
            raise MigrationDriftError(
                f"Migration {migration.version} existing-schema verification failed: "
                f"{check.description}"
            )


def verify_and_record_existing_migrations(
    connection: Connection,
    migrations: Sequence[MigrationFile],
) -> None:
    """Verify the complete suffix before writing any history record."""

    for migration in migrations:
        verify_existing_migration(connection, migration)
    for migration in migrations:
        record_migration(connection, migration)


@contextmanager
def migration_lock(engine: Engine) -> Iterator[Connection]:
    with engine.connect() as connection:
        connection.execute(
            text("select pg_advisory_lock(:lock_id)"),
            {"lock_id": MIGRATION_ADVISORY_LOCK_ID},
        )
        connection.commit()
        try:
            yield connection
        finally:
            if connection.in_transaction():
                connection.rollback()
            connection.execute(
                text("select pg_advisory_unlock(:lock_id)"),
                {"lock_id": MIGRATION_ADVISORY_LOCK_ID},
            )
            connection.commit()


def get_migration_status(
    engine: Engine,
    directory: Path,
    *,
    through: str | None = None,
) -> MigrationStatus:
    migrations = discover_migrations(directory)
    with migration_lock(engine) as connection:
        with connection.begin():
            ensure_migration_table(connection)
        with connection.begin():
            applied = load_applied_migrations(connection)
            pending = plan_pending_migrations(
                migrations,
                applied,
                through=through,
            )
    return MigrationStatus(applied=applied, pending=pending)


def apply_pending_migrations(
    engine: Engine,
    directory: Path,
    *,
    through: str | None = None,
) -> tuple[MigrationFile, ...]:
    migrations = discover_migrations(directory)
    completed: list[MigrationFile] = []

    with migration_lock(engine) as connection:
        with connection.begin():
            ensure_migration_table(connection)
        with connection.begin():
            applied = load_applied_migrations(connection)
            pending = plan_pending_migrations(
                migrations,
                applied,
                through=through,
            )

        for migration in pending:
            with connection.begin():
                apply_migration(connection, migration)
            completed.append(migration)

    return tuple(completed)


def baseline_legacy_migrations(
    engine: Engine,
    directory: Path,
    *,
    through: str,
) -> tuple[MigrationFile, ...]:
    migrations = discover_migrations(directory)
    local_by_version = {migration.version: migration for migration in migrations}
    if through not in local_by_version:
        raise MigrationPlanError(f"Unknown baseline migration version {through!r}")
    if int(through) > int(LEGACY_BASELINE_MAX_VERSION):
        raise MigrationPlanError(
            f"Baseline cannot pass legacy boundary {LEGACY_BASELINE_MAX_VERSION}"
        )

    baseline = tuple(
        migration for migration in migrations if int(migration.version) <= int(through)
    )
    with migration_lock(engine) as connection:
        with connection.begin():
            ensure_migration_table(connection)
        with connection.begin():
            applied = load_applied_migrations(connection)
            if applied:
                plan_pending_migrations(migrations, applied)
                raise MigrationPlanError(
                    "Legacy baseline is allowed only when migration history is empty"
                )
            for migration in baseline:
                connection.execute(
                    text(INSERT_HISTORY_SQL),
                    {
                        "version": migration.version,
                        "filename": migration.filename,
                        "checksum": migration.checksum,
                    },
                )

    return baseline


def mark_existing_migrations(
    engine: Engine,
    directory: Path,
    *,
    through: str,
) -> tuple[MigrationFile, ...]:
    """Verify manually applied migrations and atomically repair their ledger entries."""

    migrations = discover_migrations(directory)
    with migration_lock(engine) as connection:
        with connection.begin():
            validate_migration_table(connection)
            applied = load_applied_migrations(connection)
            existing = plan_existing_migrations(
                migrations,
                applied,
                through=through,
            )
            verify_and_record_existing_migrations(connection, existing)

    return existing
