create table identity.session_exchanges (
  id uuid primary key default gen_random_uuid(),
  source text not null,
  source_session_hash bytea not null,
  user_id uuid not null
    references identity.users(id) on delete cascade,
  identity_session_id uuid not null
    references identity.auth_sessions(sid) on delete cascade,
  source_authenticated_at timestamptz not null,
  source_expires_at timestamptz,
  exchanged_at timestamptz not null default now(),
  request_id text,
  ip_hash bytea,
  user_agent_hash bytea,
  constraint identity_session_exchanges_source_chk
    check (source = 'supabase'),
  constraint identity_session_exchanges_source_session_hash_length_chk
    check (octet_length(source_session_hash) = 32),
  constraint identity_session_exchanges_source_session_hash_key
    unique (source_session_hash),
  constraint identity_session_exchanges_source_expiry_chk
    check (
      source_expires_at is null
      or source_expires_at > source_authenticated_at
    ),
  constraint identity_session_exchanges_request_id_chk
    check (request_id is null or length(request_id) <= 200),
  constraint identity_session_exchanges_ip_hash_length_chk
    check (ip_hash is null or octet_length(ip_hash) = 32),
  constraint identity_session_exchanges_user_agent_hash_length_chk
    check (user_agent_hash is null or octet_length(user_agent_hash) = 32)
);

create index identity_session_exchanges_user_idx
  on identity.session_exchanges (user_id, exchanged_at desc);

create index identity_session_exchanges_identity_session_idx
  on identity.session_exchanges (identity_session_id);

create table identity.authentication_metrics_hourly (
  bucket_started_at timestamptz not null,
  source text not null,
  outcome text not null,
  reason_code text not null default '',
  observation_count bigint not null default 0,
  updated_at timestamptz not null default now(),
  primary key (bucket_started_at, source, outcome, reason_code),
  constraint identity_authentication_metrics_source_chk
    check (source in ('supabase', 'identity', 'unknown')),
  constraint identity_authentication_metrics_outcome_chk
    check (outcome in ('success', 'failure', 'denied')),
  constraint identity_authentication_metrics_reason_code_chk
    check (
      reason_code = ''
      or reason_code ~ '^[A-Z][A-Z0-9_]{0,99}$'
    ),
  constraint identity_authentication_metrics_count_chk
    check (observation_count > 0)
);

create index identity_authentication_metrics_updated_at_idx
  on identity.authentication_metrics_hourly (updated_at);

create or replace view identity.dual_authentication_metrics
with (security_invoker = true)
as
select
  source,
  outcome,
  nullif(reason_code, '') as reason_code,
  sum(observation_count)::bigint as observation_count
from identity.authentication_metrics_hourly
where bucket_started_at >= date_trunc('hour', now()) - interval '24 hours'
group by source, outcome, reason_code;

revoke all on table identity.session_exchanges from public;
revoke all on table identity.authentication_metrics_hourly from public;
revoke all on table identity.dual_authentication_metrics from public;
