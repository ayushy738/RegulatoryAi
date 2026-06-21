create table if not exists document_families (
  family_id bigint generated always as identity primary key,
  canonical_title text not null,
  issuer text,
  document_type text,
  first_seen_at timestamptz not null default now(),
  latest_version_id bigint references document_versions(id) on delete set null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create unique index if not exists document_families_natural_key_idx
  on document_families (
    lower(coalesce(issuer, '')),
    lower(canonical_title),
    lower(coalesce(document_type, ''))
  );
create index if not exists document_families_issuer_idx on document_families (issuer);
create index if not exists document_families_latest_version_idx
  on document_families (latest_version_id);

create table if not exists document_family_assignments (
  document_id bigint primary key references documents(id) on delete cascade,
  family_id bigint references document_families(family_id) on delete set null,
  assignment_type text not null,
  confidence numeric(5,4) not null default 0,
  evidence text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists document_family_assignments_family_idx
  on document_family_assignments (family_id);
create index if not exists document_family_assignments_type_idx
  on document_family_assignments (assignment_type);

create table if not exists document_version_registry (
  registry_version_id bigint generated always as identity primary key,
  family_id bigint not null references document_families(family_id) on delete cascade,
  document_id bigint not null references documents(id) on delete cascade,
  document_version_id bigint not null references document_versions(id) on delete cascade,
  version_number int,
  version_label text,
  publication_date date,
  issue_date date,
  effective_date date,
  content_hash text,
  parent_registry_version_id bigint references document_version_registry(registry_version_id)
    on delete set null,
  supersedes_registry_version_id bigint references document_version_registry(registry_version_id)
    on delete set null,
  superseded_by_registry_version_id bigint references document_version_registry(registry_version_id)
    on delete set null,
  amendment_number int,
  amendment_label text,
  referenced_instrument text,
  referenced_notification text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (document_version_id)
);

create index if not exists document_version_registry_family_idx
  on document_version_registry (family_id);
create index if not exists document_version_registry_document_idx
  on document_version_registry (document_id);
create index if not exists document_version_registry_parent_idx
  on document_version_registry (parent_registry_version_id);
create index if not exists document_version_registry_content_hash_idx
  on document_version_registry (content_hash);

create table if not exists document_version_relationships (
  relationship_id bigint generated always as identity primary key,
  family_id bigint references document_families(family_id) on delete cascade,
  from_registry_version_id bigint references document_version_registry(registry_version_id)
    on delete cascade,
  to_registry_version_id bigint references document_version_registry(registry_version_id)
    on delete cascade,
  relationship_type text not null,
  confidence numeric(5,4) not null default 0,
  evidence text,
  created_at timestamptz not null default now(),
  unique (from_registry_version_id, to_registry_version_id, relationship_type)
);

create index if not exists document_version_relationships_family_idx
  on document_version_relationships (family_id);
create index if not exists document_version_relationships_type_idx
  on document_version_relationships (relationship_type);

create table if not exists deadline_history (
  deadline_id bigint generated always as identity primary key,
  family_id bigint references document_families(family_id) on delete cascade,
  registry_version_id bigint references document_version_registry(registry_version_id)
    on delete cascade,
  document_id bigint references documents(id) on delete cascade,
  document_version_id bigint references document_versions(id) on delete cascade,
  deadline_type text not null,
  deadline_date date,
  raw_date text,
  extracted_from text,
  confidence numeric(5,4) not null default 0,
  created_at timestamptz not null default now()
);

create index if not exists deadline_history_family_idx on deadline_history (family_id);
create index if not exists deadline_history_registry_version_idx
  on deadline_history (registry_version_id);
create index if not exists deadline_history_type_date_idx
  on deadline_history (deadline_type, deadline_date);
create unique index if not exists deadline_history_dedup_idx
  on deadline_history (
    registry_version_id,
    deadline_type,
    coalesce(deadline_date, date '0001-01-01'),
    coalesce(raw_date, ''),
    left(coalesce(extracted_from, ''), 120)
  );
