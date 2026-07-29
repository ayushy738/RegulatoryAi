create table public.regulatory_entity_catalog (
  canonical_id text primary key,
  canonical_name text not null,
  normalized_name text generated always as (
    btrim(lower(regexp_replace(
      btrim(canonical_name),
      '[^[:alnum:]]+',
      ' ',
      'g'
    )))
  ) stored,
  entity_class text not null,
  jurisdiction text not null,
  normalized_jurisdiction text generated always as (
    btrim(lower(regexp_replace(
      btrim(jurisdiction),
      '[^[:alnum:]]+',
      ' ',
      'g'
    )))
  ) stored,
  graph_entity_id bigint
    references public.regulatory_graph_entities(entity_id)
    on delete set null,
  workspace_priority smallint not null default 50,
  provenance_kind text not null,
  provenance_ref text not null,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint regulatory_entity_catalog_canonical_id_chk
    check (canonical_id ~ '^[a-z0-9][a-z0-9._:-]{0,199}$'),
  constraint regulatory_entity_catalog_canonical_name_chk
    check (btrim(canonical_name) <> ''),
  constraint regulatory_entity_catalog_class_chk
    check (entity_class in (
      'regulatory_concept',
      'regulation_family',
      'legal_instrument',
      'regulator',
      'scheme_or_policy',
      'market_or_commodity',
      'stakeholder',
      'obligation',
      'document',
      'jurisdiction',
      'status'
    )),
  constraint regulatory_entity_catalog_jurisdiction_chk
    check (btrim(jurisdiction) <> ''),
  constraint regulatory_entity_catalog_priority_chk
    check (workspace_priority between 0 and 100),
  constraint regulatory_entity_catalog_provenance_kind_chk
    check (provenance_kind in (
      'official_source',
      'curated_catalog',
      'legacy_graph'
    )),
  constraint regulatory_entity_catalog_provenance_ref_chk
    check (btrim(provenance_ref) <> ''),
  constraint regulatory_entity_catalog_metadata_object_chk
    check (jsonb_typeof(metadata) = 'object'),
  constraint regulatory_entity_catalog_name_jurisdiction_key
    unique (normalized_name, normalized_jurisdiction)
);

create index regulatory_entity_catalog_class_jurisdiction_idx
  on public.regulatory_entity_catalog (
    entity_class,
    normalized_jurisdiction,
    canonical_id
  );

create table public.regulatory_entity_aliases (
  alias_id bigint generated always as identity primary key,
  canonical_id text not null
    references public.regulatory_entity_catalog(canonical_id)
    on delete cascade,
  alias text not null,
  normalized_alias text generated always as (
    btrim(lower(regexp_replace(
      btrim(alias),
      '[^[:alnum:]]+',
      ' ',
      'g'
    )))
  ) stored,
  alias_kind text not null,
  jurisdiction text not null,
  normalized_jurisdiction text generated always as (
    btrim(lower(regexp_replace(
      btrim(jurisdiction),
      '[^[:alnum:]]+',
      ' ',
      'g'
    )))
  ) stored,
  provenance_kind text not null,
  provenance_ref text not null,
  created_at timestamptz not null default now(),
  constraint regulatory_entity_aliases_alias_chk
    check (btrim(alias) <> ''),
  constraint regulatory_entity_aliases_kind_chk
    check (alias_kind in (
      'approved_alias',
      'acronym',
      'former_name',
      'regulation_family',
      'regulator_association'
    )),
  constraint regulatory_entity_aliases_jurisdiction_chk
    check (btrim(jurisdiction) <> ''),
  constraint regulatory_entity_aliases_provenance_kind_chk
    check (provenance_kind in (
      'official_source',
      'curated_catalog',
      'legacy_graph'
    )),
  constraint regulatory_entity_aliases_provenance_ref_chk
    check (btrim(provenance_ref) <> ''),
  constraint regulatory_entity_aliases_entity_scope_key
    unique (canonical_id, normalized_alias, normalized_jurisdiction)
);

create index regulatory_entity_aliases_lookup_idx
  on public.regulatory_entity_aliases (
    normalized_alias,
    normalized_jurisdiction,
    canonical_id
  );

create table public.regulatory_glossary_terms (
  glossary_term_id bigint generated always as identity primary key,
  canonical_id text not null
    references public.regulatory_entity_catalog(canonical_id)
    on delete cascade,
  term text not null,
  normalized_term text generated always as (
    btrim(lower(regexp_replace(
      btrim(term),
      '[^[:alnum:]]+',
      ' ',
      'g'
    )))
  ) stored,
  definition text not null,
  jurisdiction text not null,
  normalized_jurisdiction text generated always as (
    btrim(lower(regexp_replace(
      btrim(jurisdiction),
      '[^[:alnum:]]+',
      ' ',
      'g'
    )))
  ) stored,
  provenance_kind text not null,
  provenance_ref text not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint regulatory_glossary_terms_term_chk
    check (btrim(term) <> ''),
  constraint regulatory_glossary_terms_definition_chk
    check (btrim(definition) <> ''),
  constraint regulatory_glossary_terms_jurisdiction_chk
    check (btrim(jurisdiction) <> ''),
  constraint regulatory_glossary_terms_provenance_kind_chk
    check (provenance_kind in (
      'official_source',
      'curated_catalog',
      'legacy_graph'
    )),
  constraint regulatory_glossary_terms_provenance_ref_chk
    check (btrim(provenance_ref) <> ''),
  constraint regulatory_glossary_terms_entity_scope_key
    unique (canonical_id, normalized_term, normalized_jurisdiction)
);

create index regulatory_glossary_terms_lookup_idx
  on public.regulatory_glossary_terms (
    normalized_term,
    normalized_jurisdiction,
    canonical_id
  );

alter table public.regulatory_entity_catalog enable row level security;
alter table public.regulatory_entity_aliases enable row level security;
alter table public.regulatory_glossary_terms enable row level security;

create policy regulatory_entity_catalog_authenticated_read
  on public.regulatory_entity_catalog
  for select
  to authenticated
  using (true);

create policy regulatory_entity_aliases_authenticated_read
  on public.regulatory_entity_aliases
  for select
  to authenticated
  using (true);

create policy regulatory_glossary_terms_authenticated_read
  on public.regulatory_glossary_terms
  for select
  to authenticated
  using (true);

revoke all on table public.regulatory_entity_catalog from public;
revoke all on table public.regulatory_entity_aliases from public;
revoke all on table public.regulatory_glossary_terms from public;

grant select on table public.regulatory_entity_catalog to authenticated;
grant select on table public.regulatory_entity_aliases to authenticated;
grant select on table public.regulatory_glossary_terms to authenticated;
