alter table identity.auth_sessions
  add column refresh_token_hash bytea,
  add column refresh_generation bigint not null default 0;

alter table identity.auth_sessions
  add constraint identity_auth_sessions_refresh_token_hash_length_chk
    check (
      refresh_token_hash is null
      or octet_length(refresh_token_hash) = 32
    ),
  add constraint identity_auth_sessions_refresh_generation_chk
    check (refresh_generation >= 0);

create unique index identity_auth_sessions_refresh_token_hash_idx
  on identity.auth_sessions (refresh_token_hash)
  where refresh_token_hash is not null;

create table identity.authentication_rate_limits (
  scope text not null,
  subject_hash bytea not null,
  window_started_at timestamptz not null,
  attempts integer not null default 0,
  blocked_until timestamptz,
  updated_at timestamptz not null default now(),
  primary key (scope, subject_hash),
  constraint identity_authentication_rate_limits_scope_chk
    check (
      length(scope) between 3 and 100
      and scope ~ '^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$'
    ),
  constraint identity_authentication_rate_limits_subject_hash_length_chk
    check (octet_length(subject_hash) = 32),
  constraint identity_authentication_rate_limits_attempts_chk
    check (attempts >= 0),
  constraint identity_authentication_rate_limits_blocked_until_chk
    check (
      blocked_until is null
      or blocked_until >= window_started_at
    )
);

create index identity_authentication_rate_limits_blocked_until_idx
  on identity.authentication_rate_limits (blocked_until)
  where blocked_until is not null;

create index identity_authentication_rate_limits_updated_at_idx
  on identity.authentication_rate_limits (updated_at);

revoke all on table identity.authentication_rate_limits from public;
