alter table public.ask_sections
  add constraint ask_sections_id_run_owner_key
    unique (id, run_id, session_id, user_id);

alter table public.ask_sources
  add constraint ask_sources_id_run_owner_key
    unique (id, run_id, session_id, user_id);

alter table public.ask_citations
  add constraint ask_citations_id_run_owner_key
    unique (id, run_id, session_id, user_id);

create table public.ask_saved_items (
  id uuid primary key default gen_random_uuid(),
  session_id uuid not null,
  user_id uuid not null,
  item_type text not null,
  target_key text not null,
  run_id uuid,
  response_version integer,
  source_id uuid,
  citation_id uuid,
  section_id uuid,
  entity_id text,
  document_id bigint,
  label_snapshot text not null,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint ask_saved_items_session_owner_fkey
    foreign key (session_id, user_id)
    references public.chat_sessions(id, user_id)
    on delete cascade,
  constraint ask_saved_items_run_owner_version_fkey
    foreign key (run_id, session_id, user_id, response_version)
    references public.ask_runs(id, session_id, user_id, response_version)
    on delete restrict,
  constraint ask_saved_items_source_owner_fkey
    foreign key (source_id, run_id, session_id, user_id)
    references public.ask_sources(id, run_id, session_id, user_id)
    on delete restrict,
  constraint ask_saved_items_citation_owner_fkey
    foreign key (citation_id, run_id, session_id, user_id)
    references public.ask_citations(id, run_id, session_id, user_id)
    on delete restrict,
  constraint ask_saved_items_section_owner_fkey
    foreign key (section_id, run_id, session_id, user_id)
    references public.ask_sections(id, run_id, session_id, user_id)
    on delete restrict,
  constraint ask_saved_items_entity_fkey
    foreign key (entity_id)
    references public.regulatory_entity_catalog(canonical_id)
    on delete restrict,
  constraint ask_saved_items_document_fkey
    foreign key (document_id)
    references public.documents(id)
    on delete restrict,
  constraint ask_saved_items_item_type_chk
    check (item_type in ('source', 'citation', 'card', 'entity', 'document')),
  constraint ask_saved_items_target_chk
    check (
      (
        item_type = 'source'
        and source_id is not null
        and citation_id is null
        and section_id is null
        and entity_id is null
        and document_id is null
        and run_id is not null
        and response_version is not null
        and target_key = source_id::text
      )
      or (
        item_type = 'citation'
        and source_id is null
        and citation_id is not null
        and section_id is null
        and entity_id is null
        and document_id is null
        and run_id is not null
        and response_version is not null
        and target_key = citation_id::text
      )
      or (
        item_type = 'card'
        and source_id is null
        and citation_id is null
        and section_id is not null
        and entity_id is null
        and document_id is null
        and run_id is not null
        and response_version is not null
        and target_key = section_id::text
      )
      or (
        item_type = 'entity'
        and source_id is null
        and citation_id is null
        and section_id is null
        and entity_id is not null
        and document_id is null
        and run_id is null
        and response_version is null
        and target_key = entity_id
      )
      or (
        item_type = 'document'
        and source_id is null
        and citation_id is null
        and section_id is null
        and entity_id is null
        and document_id is not null
        and run_id is null
        and response_version is null
        and target_key = document_id::text
      )
    ),
  constraint ask_saved_items_version_chk
    check (response_version is null or response_version > 0),
  constraint ask_saved_items_target_key_chk
    check (btrim(target_key) <> '' and target_key = btrim(target_key)),
  constraint ask_saved_items_label_chk
    check (
      length(label_snapshot) between 1 and 500
      and label_snapshot = btrim(label_snapshot)
    ),
  constraint ask_saved_items_metadata_object_chk
    check (jsonb_typeof(metadata) = 'object')
);

create unique index ask_saved_items_owner_target_key
  on public.ask_saved_items (
    user_id,
    session_id,
    item_type,
    target_key,
    coalesce(response_version, 0)
  );

create index ask_saved_items_session_created_idx
  on public.ask_saved_items (
    user_id,
    session_id,
    created_at,
    id
  );

alter table public.ask_saved_items enable row level security;

create policy own_ask_saved_items_read
  on public.ask_saved_items
  for select
  to authenticated
  using (user_id = auth.uid());

revoke all on table public.ask_saved_items from public;
grant select on table public.ask_saved_items to authenticated;
