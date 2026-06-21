create table if not exists event_intelligence_audit (
  id bigint generated always as identity primary key,
  event_id bigint references events(id) on delete set null,
  document_id bigint references documents(id) on delete set null,
  version_id bigint references document_versions(id) on delete set null,
  source_url text not null,
  content_hash text,
  title text,
  event_allowed boolean not null default false,
  rejection_reason text,
  freshness text not null,
  significance_score int not null default 0,
  significance_category text not null,
  actionability text not null,
  quality_score int not null default 0,
  quality_category text not null,
  is_index_document boolean not null default false,
  deadlines jsonb not null default '[]',
  intelligence_json jsonb not null default '{}',
  created_at timestamptz not null default now()
);

create index if not exists event_intelligence_audit_event_id_idx
  on event_intelligence_audit (event_id);
create index if not exists event_intelligence_audit_content_hash_idx
  on event_intelligence_audit (content_hash);
create index if not exists event_intelligence_audit_allowed_idx
  on event_intelligence_audit (event_allowed);
create index if not exists event_intelligence_audit_rejection_idx
  on event_intelligence_audit (rejection_reason);
create index if not exists event_intelligence_audit_quality_idx
  on event_intelligence_audit (quality_score desc);
