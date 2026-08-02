create index chat_sessions_search_vector_idx
  on public.chat_sessions using gin ((
    setweight(to_tsvector('simple', coalesce(title, '')), 'A')
    || setweight(to_tsvector('simple', coalesce(primary_entity, '')), 'B')
    || setweight(to_tsvector('simple', coalesce(primary_topic, '')), 'C')
  ));

create index chat_messages_search_vector_idx
  on public.chat_messages using gin ((
    to_tsvector('simple', coalesce(content, ''))
  ))
  where session_id is not null;

create index ask_sources_search_vector_idx
  on public.ask_sources using gin ((
    setweight(to_tsvector('simple', coalesce(title_snapshot, '')), 'A')
    || setweight(to_tsvector('simple', coalesce(issuer_snapshot, '')), 'B')
    || setweight(to_tsvector('simple', coalesce(publisher_snapshot, '')), 'B')
    || setweight(to_tsvector('simple', coalesce(evidence_snapshot, '')), 'C')
    || setweight(to_tsvector('simple', coalesce(locator_snapshot, '')), 'D')
  ));

create index ask_sections_session_mode_search_idx
  on public.ask_sections (user_id, session_id, knowledge_mode)
  where status = 'completed';

create index chat_sessions_entity_search_idx
  on public.chat_sessions (
    user_id,
    lower(regexp_replace(btrim(primary_entity), '[[:space:]]+', ' ', 'g')),
    updated_at desc,
    id desc
  )
  where deleted_at is null and primary_entity is not null;

create index chat_sessions_active_search_cursor_idx
  on public.chat_sessions (user_id, is_pinned, updated_at desc, id desc)
  where deleted_at is null and archived_at is null;

create index chat_sessions_archived_search_cursor_idx
  on public.chat_sessions (user_id, is_pinned, updated_at desc, id desc)
  where deleted_at is null and archived_at is not null;
