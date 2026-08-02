create index document_version_registry_manual_effective_status_idx
  on public.document_version_registry (
    effective_date desc nulls last,
    superseded_by_registry_version_id,
    registry_version_id desc
  );

create index document_version_registry_manual_document_cursor_idx
  on public.document_version_registry (
    document_id,
    publication_date desc nulls last,
    registry_version_id desc
  );

create index document_chunks_manual_document_version_page_idx
  on public.document_chunks (
    document_id,
    version_id,
    page_number nulls last,
    chunk_index,
    id
  );

-- Rollback is flag-off with indexes retained. Dropping these indexes requires a
-- separately approved contraction after no deployed manual-search query uses
-- them; documents, families, versions, and chunks remain canonical.
