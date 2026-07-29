create index regulatory_entity_catalog_federated_search_idx
  on public.regulatory_entity_catalog using gin ((
    setweight(to_tsvector('simple', coalesce(canonical_name, '')), 'A')
    || setweight(to_tsvector('simple', coalesce(entity_class, '')), 'B')
    || setweight(to_tsvector('simple', coalesce(jurisdiction, '')), 'B')
  ));

create index regulatory_entity_aliases_federated_search_idx
  on public.regulatory_entity_aliases using gin ((
    setweight(to_tsvector('simple', coalesce(alias, '')), 'A')
    || setweight(to_tsvector('simple', coalesce(jurisdiction, '')), 'B')
  ));

create index documents_federated_search_idx
  on public.documents using gin ((
    setweight(to_tsvector('simple', coalesce(title, '')), 'A')
    || setweight(to_tsvector('simple', coalesce(issuing_body, '')), 'B')
    || setweight(to_tsvector('simple', coalesce(doc_type, '')), 'B')
  ));

create index document_families_federated_search_idx
  on public.document_families using gin ((
    setweight(to_tsvector('simple', coalesce(canonical_title, '')), 'A')
    || setweight(to_tsvector('simple', coalesce(issuer, '')), 'B')
    || setweight(to_tsvector('simple', coalesce(document_type, '')), 'B')
  ));

create index document_version_registry_federated_search_idx
  on public.document_version_registry using gin ((
    setweight(to_tsvector('simple', coalesce(version_label, '')), 'A')
    || setweight(to_tsvector('simple', coalesce(amendment_label, '')), 'A')
    || setweight(to_tsvector('simple', coalesce(referenced_instrument, '')), 'B')
    || setweight(to_tsvector('simple', coalesce(referenced_notification, '')), 'B')
  ));

create index deadline_history_federated_search_idx
  on public.deadline_history using gin ((
    setweight(to_tsvector('simple', coalesce(deadline_type, '')), 'A')
    || setweight(to_tsvector('simple', coalesce(raw_date, '')), 'B')
    || setweight(to_tsvector('simple', coalesce(extracted_from, '')), 'C')
  ));

-- Rollback is flag-off with indexes retained. Dropping these indexes requires a
-- separately approved contraction after no deployed federated-search query uses
-- them; canonical entity, document, version, deadline, and session rows remain
-- the only sources of truth.
