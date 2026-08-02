create table public.ask_response_regenerations (
  request_id uuid primary key,
  session_id uuid not null,
  user_id uuid not null,
  user_message_id bigint not null,
  source_run_id uuid not null,
  source_response_version integer not null,
  source_assistant_message_id bigint not null,
  parent_assistant_message_id bigint not null,
  parent_response_version integer not null,
  target_run_id uuid not null,
  target_response_version integer not null,
  target_assistant_message_id bigint not null,
  operation text not null,
  source_strategy text not null,
  style_variant text not null,
  plan jsonb not null,
  assistant_role text generated always as ('assistant'::text) stored,
  created_at timestamptz not null default now(),
  constraint ask_response_regenerations_target_run_key
    unique (target_run_id),
  constraint ask_response_regenerations_target_message_key
    unique (target_assistant_message_id),
  constraint ask_response_regenerations_source_run_owner_version_fkey
    foreign key (
      source_run_id,
      session_id,
      user_id,
      source_response_version
    )
    references public.ask_runs(id, session_id, user_id, response_version)
    on delete cascade,
  constraint ask_response_regenerations_target_run_owner_version_fkey
    foreign key (
      target_run_id,
      session_id,
      user_id,
      target_response_version
    )
    references public.ask_runs(id, session_id, user_id, response_version)
    on delete cascade,
  constraint ask_response_regenerations_source_message_fkey
    foreign key (
      source_assistant_message_id,
      user_message_id,
      session_id,
      user_id,
      assistant_role,
      source_response_version
    )
    references public.chat_messages(
      id,
      reply_to_message_id,
      session_id,
      user_id,
      role,
      response_version
    )
    on delete cascade,
  constraint ask_response_regenerations_parent_message_fkey
    foreign key (
      parent_assistant_message_id,
      user_message_id,
      session_id,
      user_id,
      assistant_role,
      parent_response_version
    )
    references public.chat_messages(
      id,
      reply_to_message_id,
      session_id,
      user_id,
      role,
      response_version
    )
    on delete restrict,
  constraint ask_response_regenerations_target_message_fkey
    foreign key (
      target_assistant_message_id,
      user_message_id,
      session_id,
      user_id,
      assistant_role,
      target_response_version
    )
    references public.chat_messages(
      id,
      reply_to_message_id,
      session_id,
      user_id,
      role,
      response_version
    )
    on delete cascade,
  constraint ask_response_regenerations_versions_chk
    check (
      source_response_version > 0
      and parent_response_version > 0
      and target_response_version = parent_response_version + 1
      and target_response_version > source_response_version
    ),
  constraint ask_response_regenerations_distinct_targets_chk
    check (
      source_run_id <> target_run_id
      and source_assistant_message_id <> target_assistant_message_id
      and parent_assistant_message_id <> target_assistant_message_id
    ),
  constraint ask_response_regenerations_operation_chk
    check (operation in ('regenerate', 'refresh')),
  constraint ask_response_regenerations_source_strategy_chk
    check (
      (
        operation = 'regenerate'
        and source_strategy = 'same_sources'
      )
      or (
        operation = 'refresh'
        and source_strategy in ('refresh_official', 'include_live')
      )
    ),
  constraint ask_response_regenerations_style_variant_chk
    check (
      style_variant in ('default', 'concise', 'beginner', 'legal_detail')
    ),
  constraint ask_response_regenerations_plan_chk
    check (jsonb_typeof(plan) = 'object')
);

create index ask_response_regenerations_turn_version_idx
  on public.ask_response_regenerations (
    user_id,
    session_id,
    user_message_id,
    target_response_version
  );

alter table public.ask_response_regenerations enable row level security;

create policy own_ask_response_regenerations_read
  on public.ask_response_regenerations
  for select
  to authenticated
  using (user_id = auth.uid());

revoke all on table public.ask_response_regenerations from public;
grant select on table public.ask_response_regenerations to authenticated;
