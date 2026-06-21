create table if not exists discovery_audit (
  id bigint generated always as identity primary key,
  run_id bigint references crawl_runs(id) on delete set null,
  source_code text not null,
  source_url text not null,
  title text,
  classification text not null,
  is_valid_event_source boolean not null default false,
  confidence numeric(5,4) not null default 0,
  reason_code text not null,
  primary_url text,
  content_length int not null default 0,
  content_hash text,
  metadata jsonb not null default '{}',
  created_at timestamptz not null default now()
);

create index if not exists discovery_audit_run_id_idx on discovery_audit (run_id);
create index if not exists discovery_audit_source_code_idx on discovery_audit (source_code);
create index if not exists discovery_audit_classification_idx on discovery_audit (classification);
create index if not exists discovery_audit_reason_code_idx on discovery_audit (reason_code);

create table if not exists document_texts (
  content_hash text primary key,
  text_content text not null,
  content_length int not null,
  created_at timestamptz not null default now()
);
