alter table public.chat_messages
  add constraint chat_messages_id_session_user_key
    unique (id, session_id, user_id);

create table public.ask_runs (
  id uuid primary key default gen_random_uuid(),
  session_id uuid not null,
  user_id uuid not null,
  user_message_id bigint not null,
  assistant_message_id bigint not null,
  status text not null default 'pending',
  decision_record jsonb not null default '{}'::jsonb,
  orchestration_state jsonb not null default '{}'::jsonb,
  branch_statuses jsonb not null default '{}'::jsonb,
  knowledge_mode_summary jsonb not null default '{}'::jsonb,
  timings jsonb not null default '{}'::jsonb,
  model text,
  policy_version text,
  prompt_version text,
  general_ai_disclosure text,
  safe_error_code text,
  safe_error_message text,
  started_at timestamptz,
  completed_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint ask_runs_id_session_user_key
    unique (id, session_id, user_id),
  constraint ask_runs_assistant_message_key
    unique (assistant_message_id),
  constraint ask_runs_session_owner_fkey
    foreign key (session_id, user_id)
    references public.chat_sessions(id, user_id)
    on delete cascade,
  constraint ask_runs_user_message_owner_fkey
    foreign key (user_message_id, session_id, user_id)
    references public.chat_messages(id, session_id, user_id)
    on delete cascade,
  constraint ask_runs_assistant_message_owner_fkey
    foreign key (assistant_message_id, session_id, user_id)
    references public.chat_messages(id, session_id, user_id)
    on delete cascade,
  constraint ask_runs_distinct_messages_chk
    check (user_message_id <> assistant_message_id),
  constraint ask_runs_status_chk
    check (status in (
      'pending',
      'running',
      'completed',
      'partial',
      'failed',
      'cancelled'
    )),
  constraint ask_runs_safe_error_code_chk
    check (
      safe_error_code is null
      or safe_error_code ~ '^[A-Z][A-Z0-9_]{0,99}$'
    ),
  constraint ask_runs_completion_chk
    check (
      completed_at is null
      or started_at is null
      or completed_at >= started_at
    )
);

create index ask_runs_session_created_cursor_idx
  on public.ask_runs (user_id, session_id, created_at desc, id desc);

create table public.ask_sections (
  id uuid primary key default gen_random_uuid(),
  run_id uuid not null,
  session_id uuid not null,
  user_id uuid not null,
  response_version integer not null default 1,
  ordinal integer not null,
  section_type text not null,
  status text not null default 'pending',
  knowledge_mode text not null,
  provenance_label text,
  title text,
  plain_text text,
  content jsonb not null default '{}'::jsonb,
  card_schema_version text not null default '1',
  model text,
  policy_version text,
  prompt_version text,
  required_disclosure text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint ask_sections_id_owner_mode_key
    unique (id, run_id, session_id, user_id, knowledge_mode),
  constraint ask_sections_run_owner_fkey
    foreign key (run_id, session_id, user_id)
    references public.ask_runs(id, session_id, user_id)
    on delete cascade,
  constraint ask_sections_version_chk
    check (response_version > 0),
  constraint ask_sections_ordinal_chk
    check (ordinal >= 0),
  constraint ask_sections_status_chk
    check (status in ('pending', 'completed', 'failed', 'cancelled')),
  constraint ask_sections_knowledge_mode_chk
    check (knowledge_mode in ('official', 'general', 'live', 'system')),
  constraint ask_sections_provenance_chk
    check (
      (
        knowledge_mode = 'official'
        and provenance_label = 'Internal Regulatory Corpus'
      )
      or (
        knowledge_mode = 'general'
        and provenance_label = 'General AI Knowledge'
        and model is not null
        and policy_version is not null
        and required_disclosure is not null
      )
      or (
        knowledge_mode = 'live'
        and provenance_label = 'Live Web Sources'
      )
      or (
        knowledge_mode = 'system'
        and provenance_label is null
      )
    ),
  constraint ask_sections_run_version_ordinal_key
    unique (run_id, response_version, ordinal)
);

create index ask_sections_run_order_idx
  on public.ask_sections (run_id, response_version, ordinal);

create table public.ask_sources (
  id uuid primary key default gen_random_uuid(),
  run_id uuid not null,
  session_id uuid not null,
  user_id uuid not null,
  ordinal integer not null,
  source_key text not null,
  source_class text not null,
  source_type text not null,
  document_id bigint references public.documents(id) on delete restrict,
  document_version_id bigint
    references public.document_versions(id) on delete restrict,
  chunk_id bigint references public.document_chunks(id) on delete restrict,
  graph_reference jsonb,
  title_snapshot text not null,
  url_snapshot text not null,
  issuer_snapshot text,
  publisher_snapshot text,
  jurisdiction_snapshot text,
  published_at timestamptz,
  retrieved_at timestamptz not null,
  evidence_snapshot text not null,
  locator_snapshot text,
  content_hash text,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  constraint ask_sources_id_owner_class_key
    unique (id, run_id, session_id, user_id, source_class),
  constraint ask_sources_run_owner_fkey
    foreign key (run_id, session_id, user_id)
    references public.ask_runs(id, session_id, user_id)
    on delete cascade,
  constraint ask_sources_ordinal_chk
    check (ordinal >= 0),
  constraint ask_sources_class_chk
    check (source_class in ('official', 'live')),
  constraint ask_sources_class_identity_chk
    check (
      (
        source_class = 'official'
        and document_id is not null
      )
      or (
        source_class = 'live'
        and document_id is null
        and document_version_id is null
        and chunk_id is null
        and publisher_snapshot is not null
        and published_at is not null
      )
    ),
  constraint ask_sources_run_source_key
    unique (run_id, source_key),
  constraint ask_sources_run_ordinal_key
    unique (run_id, ordinal)
);

create index ask_sources_run_class_order_idx
  on public.ask_sources (run_id, source_class, ordinal);

create table public.ask_claims (
  id uuid primary key default gen_random_uuid(),
  run_id uuid not null,
  section_id uuid not null,
  session_id uuid not null,
  user_id uuid not null,
  ordinal integer not null,
  knowledge_mode text not null,
  claim_text text not null,
  is_material boolean not null default true,
  support_status text not null default 'pending',
  support_score numeric(6, 5),
  model text,
  policy_version text,
  prompt_version text,
  required_disclosure text,
  verifier_model text,
  verifier_policy_version text,
  verifier_result jsonb,
  created_at timestamptz not null default now(),
  constraint ask_claims_id_owner_mode_key
    unique (id, run_id, session_id, user_id, knowledge_mode),
  constraint ask_claims_section_owner_mode_fkey
    foreign key (
      section_id,
      run_id,
      session_id,
      user_id,
      knowledge_mode
    )
    references public.ask_sections(
      id,
      run_id,
      session_id,
      user_id,
      knowledge_mode
    )
    on delete cascade,
  constraint ask_claims_ordinal_chk
    check (ordinal >= 0),
  constraint ask_claims_knowledge_mode_chk
    check (knowledge_mode in ('official', 'general', 'live')),
  constraint ask_claims_support_status_chk
    check (support_status in (
      'pending',
      'supported',
      'unsupported',
      'qualified',
      'not_applicable'
    )),
  constraint ask_claims_support_score_chk
    check (
      support_score is null
      or (support_score >= 0 and support_score <= 1)
    ),
  constraint ask_claims_general_support_chk
    check (
      knowledge_mode <> 'general'
      or (
        support_status = 'not_applicable'
        and support_score is null
        and model is not null
        and policy_version is not null
        and required_disclosure is not null
      )
    ),
  constraint ask_claims_section_ordinal_key
    unique (section_id, ordinal)
);

create index ask_claims_run_mode_order_idx
  on public.ask_claims (run_id, knowledge_mode, ordinal);

create table public.ask_citations (
  id uuid primary key default gen_random_uuid(),
  run_id uuid not null,
  claim_id uuid not null,
  source_id uuid not null,
  session_id uuid not null,
  user_id uuid not null,
  ordinal integer not null,
  claim_knowledge_mode text not null,
  source_class text not null,
  citation_kind text not null,
  marker text,
  evidence_snapshot text not null,
  locator_snapshot text,
  support_score numeric(6, 5),
  verification_status text not null default 'pending',
  verifier_model text,
  verifier_policy_version text,
  verifier_result jsonb,
  created_at timestamptz not null default now(),
  constraint ask_citations_run_owner_fkey
    foreign key (run_id, session_id, user_id)
    references public.ask_runs(id, session_id, user_id)
    on delete cascade,
  constraint ask_citations_claim_owner_mode_fkey
    foreign key (
      claim_id,
      run_id,
      session_id,
      user_id,
      claim_knowledge_mode
    )
    references public.ask_claims(
      id,
      run_id,
      session_id,
      user_id,
      knowledge_mode
    )
    on delete cascade,
  constraint ask_citations_source_owner_class_fkey
    foreign key (
      source_id,
      run_id,
      session_id,
      user_id,
      source_class
    )
    references public.ask_sources(
      id,
      run_id,
      session_id,
      user_id,
      source_class
    )
    on delete restrict,
  constraint ask_citations_ordinal_chk
    check (ordinal >= 0),
  constraint ask_citations_mode_class_chk
    check (
      claim_knowledge_mode in ('official', 'live')
      and claim_knowledge_mode = source_class
    ),
  constraint ask_citations_kind_chk
    check (
      (
        source_class = 'official'
        and citation_kind = 'official_citation'
      )
      or (
        source_class = 'live'
        and citation_kind = 'live_source_link'
      )
    ),
  constraint ask_citations_support_score_chk
    check (
      support_score is null
      or (support_score >= 0 and support_score <= 1)
    ),
  constraint ask_citations_verification_status_chk
    check (verification_status in (
      'pending',
      'verified',
      'rejected',
      'qualified',
      'not_applicable'
    )),
  constraint ask_citations_claim_ordinal_key
    unique (claim_id, ordinal)
);

create index ask_citations_run_source_idx
  on public.ask_citations (run_id, source_id, ordinal);

create table public.ask_followups (
  id uuid primary key default gen_random_uuid(),
  run_id uuid not null,
  session_id uuid not null,
  user_id uuid not null,
  ordinal integer not null,
  label text not null,
  question text not null,
  action_type text not null default 'ask',
  payload jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  constraint ask_followups_run_owner_fkey
    foreign key (run_id, session_id, user_id)
    references public.ask_runs(id, session_id, user_id)
    on delete cascade,
  constraint ask_followups_ordinal_chk
    check (ordinal >= 0),
  constraint ask_followups_run_ordinal_key
    unique (run_id, ordinal)
);

create index ask_followups_session_created_idx
  on public.ask_followups (user_id, session_id, created_at desc);

create table public.ask_run_events (
  id bigint generated always as identity primary key,
  public_id uuid not null default gen_random_uuid(),
  run_id uuid not null,
  session_id uuid not null,
  user_id uuid not null,
  sequence bigint not null,
  event_type text not null,
  capability text,
  status text,
  payload jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  constraint ask_run_events_public_id_key
    unique (public_id),
  constraint ask_run_events_run_owner_fkey
    foreign key (run_id, session_id, user_id)
    references public.ask_runs(id, session_id, user_id)
    on delete cascade,
  constraint ask_run_events_sequence_chk
    check (sequence >= 0),
  constraint ask_run_events_run_sequence_key
    unique (run_id, sequence)
);

create index ask_run_events_session_created_idx
  on public.ask_run_events (user_id, session_id, created_at, id);

alter table public.ask_runs enable row level security;
alter table public.ask_sections enable row level security;
alter table public.ask_sources enable row level security;
alter table public.ask_claims enable row level security;
alter table public.ask_citations enable row level security;
alter table public.ask_followups enable row level security;
alter table public.ask_run_events enable row level security;

create policy own_ask_runs_read
  on public.ask_runs
  for select
  to authenticated
  using (user_id = auth.uid());

create policy own_ask_sections_read
  on public.ask_sections
  for select
  to authenticated
  using (user_id = auth.uid());

create policy own_ask_sources_read
  on public.ask_sources
  for select
  to authenticated
  using (user_id = auth.uid());

create policy own_ask_claims_read
  on public.ask_claims
  for select
  to authenticated
  using (user_id = auth.uid());

create policy own_ask_citations_read
  on public.ask_citations
  for select
  to authenticated
  using (user_id = auth.uid());

create policy own_ask_followups_read
  on public.ask_followups
  for select
  to authenticated
  using (user_id = auth.uid());

create policy own_ask_run_events_read
  on public.ask_run_events
  for select
  to authenticated
  using (user_id = auth.uid());

revoke all on table public.ask_runs from public;
revoke all on table public.ask_sections from public;
revoke all on table public.ask_sources from public;
revoke all on table public.ask_claims from public;
revoke all on table public.ask_citations from public;
revoke all on table public.ask_followups from public;
revoke all on table public.ask_run_events from public;

grant select on table public.ask_runs to authenticated;
grant select on table public.ask_sections to authenticated;
grant select on table public.ask_sources to authenticated;
grant select on table public.ask_claims to authenticated;
grant select on table public.ask_citations to authenticated;
grant select on table public.ask_followups to authenticated;
grant select on table public.ask_run_events to authenticated;
