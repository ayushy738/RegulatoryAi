lock table public.chat_messages in share row exclusive mode;
lock table public.chat_sessions in share row exclusive mode;

do $ask_ai_backfill_preflight$
begin
  if exists (
    select 1
    from public.chat_messages
    where public_id is null
       or session_id is null
  ) then
    raise exception using
      errcode = '23514',
      message = 'ASK_AI_BACKFILL_INCOMPLETE: message identity remains nullable';
  end if;

  if exists (
    select 1
    from public.chat_messages message
    left join public.chat_sessions session on session.id = message.session_id
    where session.id is null
       or session.user_id <> message.user_id
       or session.event_id is distinct from message.event_id
  ) then
    raise exception using
      errcode = '23514',
      message = 'ASK_AI_BACKFILL_INVALID: message ownership or event scope drift';
  end if;

  if exists (
    select 1
    from public.chat_sessions
    where scope_snapshot @> '{"legacy_backfill": true}'::jsonb
    group by user_id, event_id
    having count(*) > 1
  ) then
    raise exception using
      errcode = '23505',
      message = 'ASK_AI_BACKFILL_INVALID: duplicate legacy session scope';
  end if;

  if exists (
    select 1
    from public.chat_sessions
    where scope_snapshot @> '{"legacy_backfill": true}'::jsonb
      and (
        scope_snapshot ->> 'legacy_backfill_version' is distinct from '1'
        or not (scope_snapshot ? 'event_id')
      )
  ) then
    raise exception using
      errcode = '23514',
      message = 'ASK_AI_BACKFILL_INVALID: legacy session metadata drift';
  end if;
end
$ask_ai_backfill_preflight$;

alter table public.chat_messages
  add constraint chat_messages_public_session_pair_chk
    check ((public_id is null) = (session_id is null))
    not valid;

alter table public.chat_messages
  validate constraint chat_messages_public_session_pair_chk;

create unique index chat_sessions_legacy_owner_event_key
  on public.chat_sessions (user_id, coalesce(event_id, 0))
  where scope_snapshot @> '{"legacy_backfill": true}'::jsonb;

create index chat_messages_owner_session_created_cursor_idx
  on public.chat_messages (user_id, session_id, created_at, id)
  where session_id is not null;
