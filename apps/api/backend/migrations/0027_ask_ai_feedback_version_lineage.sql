alter table public.chat_messages
  add column status text not null default 'completed',
  add column response_version integer,
  add column reply_to_message_id bigint,
  add column parent_message_id bigint,
  add column reply_to_message_role text
    generated always as ('user'::text) stored,
  add column parent_message_role text
    generated always as ('assistant'::text) stored,
  add column parent_response_version integer
    generated always as (
      case
        when response_version > 1 then response_version - 1
        else null
      end
    ) stored;

update public.chat_messages message
set
  status = case
    when run.status in ('pending', 'running') then 'pending'
    when run.status in ('completed', 'partial') then 'completed'
    when run.status = 'failed' then 'failed'
    when run.status = 'cancelled' then 'cancelled'
    else 'completed'
  end,
  response_version = 1,
  reply_to_message_id = run.user_message_id
from public.ask_runs run
where message.id = run.assistant_message_id
  and message.session_id = run.session_id
  and message.user_id = run.user_id;

alter table public.chat_messages
  add constraint chat_messages_id_owner_role_key
    unique (id, session_id, user_id, role),
  add constraint chat_messages_id_owner_role_version_key
    unique (id, session_id, user_id, role, response_version),
  add constraint chat_messages_id_response_owner_role_version_key
    unique (
      id,
      reply_to_message_id,
      session_id,
      user_id,
      role,
      response_version
    ),
  add constraint chat_messages_response_owner_version_key
    unique (reply_to_message_id, session_id, user_id, response_version),
  add constraint chat_messages_status_chk
    check (status in ('pending', 'completed', 'failed', 'cancelled')),
  add constraint chat_messages_version_lineage_chk
    check (
      (
        role = 'user'
        and response_version is null
        and reply_to_message_id is null
        and parent_message_id is null
      )
      or (
        role = 'assistant'
        and (
          (
            response_version is null
            and reply_to_message_id is null
            and parent_message_id is null
          )
          or (
            response_version = 1
            and session_id is not null
            and reply_to_message_id is not null
            and parent_message_id is null
          )
          or (
            response_version > 1
            and session_id is not null
            and reply_to_message_id is not null
            and parent_message_id is not null
          )
        )
      )
    ),
  add constraint chat_messages_lineage_distinct_chk
    check (
      (reply_to_message_id is null or reply_to_message_id <> id)
      and (parent_message_id is null or parent_message_id <> id)
      and (
        parent_message_id is null
        or reply_to_message_id is null
        or parent_message_id <> reply_to_message_id
      )
    ),
  add constraint chat_messages_reply_owner_role_fkey
    foreign key (
      reply_to_message_id,
      session_id,
      user_id,
      reply_to_message_role
    )
    references public.chat_messages(id, session_id, user_id, role)
    on delete cascade,
  add constraint chat_messages_parent_owner_version_fkey
    foreign key (
      parent_message_id,
      reply_to_message_id,
      session_id,
      user_id,
      parent_message_role,
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
    on delete restrict;

create index chat_messages_response_lineage_idx
  on public.chat_messages (
    user_id,
    session_id,
    reply_to_message_id,
    response_version
  )
  where response_version is not null;

alter table public.ask_runs
  add column response_version integer not null default 1,
  add column user_message_role text
    generated always as ('user'::text) stored,
  add column assistant_message_role text
    generated always as ('assistant'::text) stored;

alter table public.ask_runs
  add constraint ask_runs_id_owner_version_key
    unique (id, session_id, user_id, response_version),
  add constraint ask_runs_user_owner_version_key
    unique (user_message_id, session_id, user_id, response_version),
  add constraint ask_runs_response_version_chk
    check (response_version > 0),
  add constraint ask_runs_user_message_role_fkey
    foreign key (
      user_message_id,
      session_id,
      user_id,
      user_message_role
    )
    references public.chat_messages(id, session_id, user_id, role)
    on delete cascade,
  add constraint ask_runs_assistant_response_fkey
    foreign key (
      assistant_message_id,
      user_message_id,
      session_id,
      user_id,
      assistant_message_role,
      response_version
    )
    references public.chat_messages(
      id,
      reply_to_message_id,
      session_id,
      user_id,
      role,
      response_version
    )
    on delete cascade;

alter table public.ask_sections
  add constraint ask_sections_run_owner_version_fkey
    foreign key (run_id, session_id, user_id, response_version)
    references public.ask_runs(id, session_id, user_id, response_version)
    on delete cascade;

create table public.ask_feedback (
  id uuid primary key default gen_random_uuid(),
  run_id uuid not null,
  session_id uuid not null,
  user_id uuid not null,
  response_version integer not null,
  value text not null,
  reason_code text,
  comment text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint ask_feedback_run_owner_version_fkey
    foreign key (run_id, session_id, user_id, response_version)
    references public.ask_runs(id, session_id, user_id, response_version)
    on delete cascade,
  constraint ask_feedback_value_chk
    check (value in ('helpful', 'not_helpful')),
  constraint ask_feedback_reason_code_chk
    check (
      reason_code is null
      or reason_code ~ '^[a-z][a-z0-9_]{0,99}$'
    ),
  constraint ask_feedback_comment_chk
    check (
      comment is null
      or (
        length(comment) between 1 and 2000
        and comment = btrim(comment)
      )
    ),
  constraint ask_feedback_run_version_key
    unique (run_id, response_version)
);

create index ask_feedback_session_updated_idx
  on public.ask_feedback (
    user_id,
    session_id,
    updated_at desc,
    id desc
  );

alter table public.ask_feedback enable row level security;

create policy own_ask_feedback_read
  on public.ask_feedback
  for select
  to authenticated
  using (user_id = auth.uid());

revoke all on table public.ask_feedback from public;
grant select on table public.ask_feedback to authenticated;
