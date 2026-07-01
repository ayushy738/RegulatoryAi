create extension if not exists vector;

create table if not exists document_chunks (
  id bigint generated always as identity primary key,
  document_id bigint not null references documents(id) on delete cascade,
  version_id bigint references document_versions(id) on delete cascade,
  family_id bigint references document_families(family_id) on delete set null,
  chunk_index int not null,
  text text not null,
  token_count int not null default 0,
  page_number int,
  section_title text,
  content_hash text,
  search_vector tsvector generated always as (
    setweight(to_tsvector('english', coalesce(section_title, '')), 'A') ||
    setweight(to_tsvector('english', coalesce(text, '')), 'B')
  ) stored,
  created_at timestamptz not null default now(),
  unique (version_id, chunk_index)
);

create index if not exists document_chunks_document_idx
  on document_chunks (document_id);

create index if not exists document_chunks_version_idx
  on document_chunks (version_id);

create index if not exists document_chunks_family_idx
  on document_chunks (family_id);

create index if not exists document_chunks_search_idx
  on document_chunks using gin (search_vector);

create table if not exists document_chunk_embeddings (
  chunk_id bigint not null references document_chunks(id) on delete cascade,
  provider text not null,
  model text not null,
  embedding vector(1536) not null,
  embedding_dimension int not null default 1536,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  primary key (chunk_id, provider, model)
);

create index if not exists document_chunk_embeddings_vector_idx
  on document_chunk_embeddings using ivfflat (embedding vector_cosine_ops)
  with (lists = 100);

create table if not exists document_rag_status (
  document_id bigint primary key references documents(id) on delete cascade,
  version_id bigint references document_versions(id) on delete set null,
  status text not null default 'PENDING',
  chunk_count int not null default 0,
  embedded_chunk_count int not null default 0,
  provider text,
  model text,
  error text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  check (status in ('PENDING', 'CHUNKED', 'EMBEDDING', 'RAG_READY', 'FAILED', 'SKIPPED'))
);

create index if not exists document_rag_status_status_idx
  on document_rag_status (status, updated_at);

create table if not exists rag_index_jobs (
  job_id bigint generated always as identity primary key,
  document_id bigint not null references documents(id) on delete cascade,
  version_id bigint references document_versions(id) on delete cascade,
  status text not null default 'PENDING',
  attempts int not null default 0,
  last_error text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  check (status in ('PENDING', 'PROCESSING', 'COMPLETED', 'FAILED', 'SKIPPED'))
);

create unique index if not exists rag_index_jobs_document_version_idx
  on rag_index_jobs (document_id, coalesce(version_id, 0));

create index if not exists rag_index_jobs_status_idx
  on rag_index_jobs (status, updated_at);

create table if not exists chat_retrieval_audit (
  id bigint generated always as identity primary key,
  user_id uuid,
  event_id bigint references events(id) on delete set null,
  question text not null,
  detected_intent text not null,
  retrieval_provider text not null,
  embedding_provider text,
  vector_provider text,
  retrieved_chunks jsonb not null default '[]'::jsonb,
  graph_entities jsonb not null default '[]'::jsonb,
  citations jsonb not null default '[]'::jsonb,
  related_questions jsonb not null default '[]'::jsonb,
  model text not null,
  response_latency_ms int not null default 0,
  retrieval_latency_ms int not null default 0,
  context_tokens int not null default 0,
  created_at timestamptz not null default now()
);

create index if not exists chat_retrieval_audit_user_created_idx
  on chat_retrieval_audit (user_id, created_at desc);

create index if not exists documents_search_idx
  on documents using gin (
    to_tsvector(
      'english',
      coalesce(title, '') || ' ' || coalesce(issuing_body, '') || ' ' || coalesce(doc_type, '')
    )
  );

create index if not exists summaries_search_idx
  on summaries using gin (to_tsvector('english', summary_json::text));

create index if not exists regulatory_graph_stakeholders_search_idx
  on regulatory_graph_stakeholders using gin (
    to_tsvector('english', coalesce(stakeholder, '') || ' ' || coalesce(evidence, ''))
  );

create index if not exists regulatory_graph_obligations_search_idx
  on regulatory_graph_obligations using gin (
    to_tsvector('english', coalesce(obligation, '') || ' ' || coalesce(evidence, ''))
  );
