create table if not exists regulatory_graph_entities (
  entity_id bigint generated always as identity primary key,
  entity_type text not null,
  name text not null,
  canonical_name text not null,
  issuer text,
  external_ref text,
  confidence numeric(4,3) not null default 0.500,
  evidence text,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create unique index if not exists regulatory_graph_entities_natural_key_idx
  on regulatory_graph_entities (
    entity_type,
    canonical_name,
    coalesce(issuer, ''),
    coalesce(external_ref, '')
  );

create index if not exists regulatory_graph_entities_type_idx
  on regulatory_graph_entities (entity_type);

create table if not exists regulatory_graph_document_entities (
  document_id bigint not null references documents(id) on delete cascade,
  document_version_id bigint references document_versions(id) on delete cascade,
  entity_id bigint not null references regulatory_graph_entities(entity_id)
    on delete cascade,
  role text not null,
  confidence numeric(4,3) not null default 0.500,
  evidence text,
  created_at timestamptz not null default now(),
  primary key (document_id, entity_id, role)
);

create index if not exists regulatory_graph_document_entities_entity_idx
  on regulatory_graph_document_entities (entity_id);

create table if not exists regulatory_graph_edges (
  edge_id bigint generated always as identity primary key,
  from_entity_id bigint not null references regulatory_graph_entities(entity_id)
    on delete cascade,
  to_entity_id bigint not null references regulatory_graph_entities(entity_id)
    on delete cascade,
  relationship_type text not null,
  source_document_id bigint references documents(id) on delete cascade,
  source_document_version_id bigint references document_versions(id) on delete cascade,
  confidence numeric(4,3) not null default 0.500,
  evidence text,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create unique index if not exists regulatory_graph_edges_dedup_idx
  on regulatory_graph_edges (
    from_entity_id,
    to_entity_id,
    relationship_type,
    coalesce(source_document_id, 0)
  );

create index if not exists regulatory_graph_edges_relationship_idx
  on regulatory_graph_edges (relationship_type);

create table if not exists regulatory_graph_extractions (
  document_id bigint primary key references documents(id) on delete cascade,
  document_version_id bigint references document_versions(id) on delete set null,
  provider text not null,
  model text not null,
  status text not null,
  used_ai boolean not null default false,
  extraction_json jsonb not null default '{}'::jsonb,
  error text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists regulatory_graph_stakeholders (
  stakeholder_id bigint generated always as identity primary key,
  document_id bigint not null references documents(id) on delete cascade,
  document_version_id bigint references document_versions(id) on delete cascade,
  stakeholder text not null,
  normalized_stakeholder text not null,
  confidence numeric(4,3) not null default 0.500,
  evidence text,
  created_at timestamptz not null default now()
);

create unique index if not exists regulatory_graph_stakeholders_dedup_idx
  on regulatory_graph_stakeholders (
    document_id,
    normalized_stakeholder
  );

create table if not exists regulatory_graph_obligations (
  obligation_id bigint generated always as identity primary key,
  document_id bigint not null references documents(id) on delete cascade,
  document_version_id bigint references document_versions(id) on delete cascade,
  obligation text not null,
  deadline_date date,
  deadline_type text,
  affected_party text,
  confidence numeric(4,3) not null default 0.500,
  evidence text,
  created_at timestamptz not null default now()
);

create unique index if not exists regulatory_graph_obligations_dedup_idx
  on regulatory_graph_obligations (
    document_id,
    md5(lower(obligation)),
    coalesce(affected_party, '')
  );

create table if not exists regulatory_graph_deadlines (
  graph_deadline_id bigint generated always as identity primary key,
  document_id bigint not null references documents(id) on delete cascade,
  document_version_id bigint references document_versions(id) on delete cascade,
  deadline_type text not null,
  deadline_date date,
  raw_date text,
  confidence numeric(4,3) not null default 0.500,
  evidence text,
  created_at timestamptz not null default now()
);

create unique index if not exists regulatory_graph_deadlines_dedup_idx
  on regulatory_graph_deadlines (
    document_id,
    deadline_type,
    coalesce(deadline_date, date '0001-01-01'),
    coalesce(raw_date, '')
  );

create table if not exists regulatory_graph_family_enrichment (
  document_id bigint primary key references documents(id) on delete cascade,
  document_version_id bigint references document_versions(id) on delete set null,
  before_family_id bigint,
  after_family_id bigint,
  before_assignment_type text,
  after_assignment_type text,
  inferred_family text,
  confidence numeric(4,3) not null default 0.500,
  evidence text,
  applied boolean not null default false,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
