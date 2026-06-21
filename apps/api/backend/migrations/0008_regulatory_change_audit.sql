create table if not exists regulatory_change_audit (
  id bigint generated always as identity primary key,
  event_id bigint references events(id) on delete set null,
  document_id bigint references documents(id) on delete set null,
  version_id bigint references document_versions(id) on delete set null,
  prior_document_id bigint references documents(id) on delete set null,
  prior_version_id bigint references document_versions(id) on delete set null,
  source_url text not null,
  content_hash text,
  title text,
  change_type text not null,
  is_material boolean not null default false,
  confidence numeric(5,4) not null default 0,
  similarity_score numeric(6,5),
  evidence text,
  prior_version_reference text,
  previous_state text,
  new_state text,
  deadline_changes jsonb not null default '[]',
  change_json jsonb not null default '{}',
  created_at timestamptz not null default now()
);

create index if not exists regulatory_change_audit_event_id_idx
  on regulatory_change_audit (event_id);
create index if not exists regulatory_change_audit_document_id_idx
  on regulatory_change_audit (document_id);
create index if not exists regulatory_change_audit_version_id_idx
  on regulatory_change_audit (version_id);
create index if not exists regulatory_change_audit_change_type_idx
  on regulatory_change_audit (change_type);
create index if not exists regulatory_change_audit_material_idx
  on regulatory_change_audit (is_material);
