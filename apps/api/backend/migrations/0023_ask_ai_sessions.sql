create table public.chat_sessions (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null
    references auth.users(id) on delete cascade,
  event_id bigint
    references public.events(id) on delete set null,
  title text,
  status text not null default 'draft',
  primary_entity text,
  primary_topic text,
  scope_snapshot jsonb not null default '{}'::jsonb,
  knowledge_mode_summary jsonb not null default '{}'::jsonb,
  freshness_state text,
  is_pinned boolean not null default false,
  archived_at timestamptz,
  deleted_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  last_message_at timestamptz,
  constraint chat_sessions_id_user_id_key unique (id, user_id)
);

create index chat_sessions_user_updated_cursor_idx
  on public.chat_sessions (user_id, updated_at desc, id desc);

create index chat_sessions_user_event_updated_cursor_idx
  on public.chat_sessions (user_id, event_id, updated_at desc, id desc)
  where deleted_at is null;

create index chat_sessions_user_pinned_updated_cursor_idx
  on public.chat_sessions (user_id, updated_at desc, id desc)
  where is_pinned and deleted_at is null;

alter table public.chat_sessions enable row level security;

create policy own_chat_sessions
  on public.chat_sessions
  for all
  to authenticated
  using (user_id = auth.uid())
  with check (user_id = auth.uid());

revoke all on table public.chat_sessions from public;
grant select, insert, update, delete
  on table public.chat_sessions
  to authenticated;

alter table public.chat_messages
  add column public_id uuid,
  add column session_id uuid,
  add constraint chat_messages_session_owner_fkey
    foreign key (session_id, user_id)
    references public.chat_sessions(id, user_id)
    on delete set null (session_id);

create unique index chat_messages_public_id_key
  on public.chat_messages (public_id)
  where public_id is not null;

create index chat_messages_session_created_cursor_idx
  on public.chat_messages (session_id, created_at, id)
  where session_id is not null;
