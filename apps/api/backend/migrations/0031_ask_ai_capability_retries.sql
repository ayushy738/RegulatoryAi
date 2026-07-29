create table public.ask_capability_retries (
  id uuid primary key,
  run_id uuid not null,
  session_id uuid not null,
  user_id uuid not null,
  node_id text not null,
  capability text not null,
  original_request_id uuid not null,
  original_execution_version bigint not null,
  status text not null default 'pending',
  retry_plan jsonb not null,
  result jsonb,
  safe_error_code text,
  lease_id uuid,
  lease_expires_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  completed_at timestamptz,
  constraint ask_capability_retries_run_owner_fkey
    foreign key (run_id, session_id, user_id)
    references public.ask_runs(id, session_id, user_id)
    on delete cascade,
  constraint ask_capability_retries_original_request_key
    unique (run_id, node_id, original_request_id),
  constraint ask_capability_retries_version_chk
    check (original_execution_version > 0),
  constraint ask_capability_retries_status_chk
    check (status in ('pending', 'running', 'succeeded', 'failed')),
  constraint ask_capability_retries_capability_chk
    check (capability in (
      'regulatory_retriever',
      'news_retriever',
      'general_ai',
      'citation_verifier'
    )),
  constraint ask_capability_retries_safe_error_code_chk
    check (
      safe_error_code is null
      or safe_error_code ~ '^[A-Z][A-Z0-9_]{0,99}$'
    ),
  constraint ask_capability_retries_lease_pair_chk
    check (
      (
        lease_id is null
        and lease_expires_at is null
      )
      or (
        lease_id is not null
        and lease_expires_at is not null
      )
    ),
  constraint ask_capability_retries_state_chk
    check (
      (
        status = 'pending'
        and result is null
        and safe_error_code is null
        and lease_id is null
        and completed_at is null
      )
      or (
        status = 'running'
        and result is null
        and safe_error_code is null
        and lease_id is not null
        and completed_at is null
      )
      or (
        status = 'succeeded'
        and result is not null
        and safe_error_code is null
        and lease_id is null
        and completed_at is not null
      )
      or (
        status = 'failed'
        and lease_id is null
        and completed_at is not null
        and (
          result is not null
          or safe_error_code is not null
        )
      )
    )
);

create index ask_capability_retries_owner_created_idx
  on public.ask_capability_retries (
    user_id,
    session_id,
    created_at desc,
    id desc
  );

create index ask_capability_retries_recovery_idx
  on public.ask_capability_retries (lease_expires_at, id)
  where status = 'running';

alter table public.ask_capability_retries enable row level security;

create policy own_ask_capability_retries_read
  on public.ask_capability_retries
  for select
  to authenticated
  using (user_id = auth.uid());

revoke all on table public.ask_capability_retries from public;
grant select on table public.ask_capability_retries to authenticated;
