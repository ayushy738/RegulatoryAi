alter table public.ask_runs
  add column execution_version bigint not null default 0,
  add column next_event_sequence bigint not null default 0,
  add column lease_id uuid,
  add column lease_expires_at timestamptz,
  add column lease_heartbeat_at timestamptz,
  add column cancellation_request_id uuid,
  add column cancellation_requested_at timestamptz,
  add column cancellation_reason_code text;

alter table public.ask_run_events
  add column execution_version bigint;

with ranked_events as (
  select
    id,
    row_number() over (
      partition by run_id
      order by sequence, id
    ) as execution_version
  from public.ask_run_events
)
update public.ask_run_events event
set execution_version = ranked.execution_version
from ranked_events ranked
where ranked.id = event.id;

with run_event_state as (
  select
    run_id,
    count(*)::bigint as execution_version,
    coalesce(max(sequence) + 1, 0)::bigint as next_event_sequence
  from public.ask_run_events
  group by run_id
)
update public.ask_runs run
set
  execution_version = event_state.execution_version,
  next_event_sequence = event_state.next_event_sequence
from run_event_state event_state
where event_state.run_id = run.id;

alter table public.ask_run_events
  alter column execution_version set not null,
  add constraint ask_run_events_execution_version_chk
    check (execution_version > 0),
  add constraint ask_run_events_run_execution_version_key
    unique (run_id, execution_version);

alter table public.ask_runs
  add constraint ask_runs_execution_version_chk
    check (execution_version >= 0),
  add constraint ask_runs_next_event_sequence_chk
    check (next_event_sequence >= 0),
  add constraint ask_runs_lease_pair_chk
    check (
      (
        lease_id is null
        and lease_expires_at is null
        and lease_heartbeat_at is null
      )
      or (
        lease_id is not null
        and lease_expires_at is not null
        and lease_heartbeat_at is not null
      )
    ),
  add constraint ask_runs_cancellation_pair_chk
    check (
      (
        cancellation_request_id is null
        and cancellation_requested_at is null
        and cancellation_reason_code is null
      )
      or (
        cancellation_request_id is not null
        and cancellation_requested_at is not null
      )
    ),
  add constraint ask_runs_cancellation_reason_code_chk
    check (
      cancellation_reason_code is null
      or cancellation_reason_code ~ '^[A-Z][A-Z0-9_]{0,99}$'
    ),
  add constraint ask_runs_cancellation_request_key
    unique (cancellation_request_id);

create index ask_runs_active_lease_expiry_idx
  on public.ask_runs (lease_expires_at, id)
  where lease_id is not null;

create index ask_runs_pending_cancellation_idx
  on public.ask_runs (cancellation_requested_at, id)
  where cancellation_request_id is not null
    and status in ('pending', 'running', 'partial');
