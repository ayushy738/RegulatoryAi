-- Soft-delete / retire support for monitored source pages.
-- Pages remain configuration history; discovered regulatory data is never cascaded away.

alter table source_pages
  add column if not exists deleted_at timestamptz;

alter table source_pages
  add column if not exists deleted_by uuid references auth.users(id) on delete set null;

comment on column source_pages.deleted_at is
  'When set, the page is retired and must not be selected for crawling.';
comment on column source_pages.deleted_by is
  'Admin auth.users id that retired the page; null after restore.';

-- Replace hard unique(source_id, url) with active-only uniqueness so retired
-- historical rows keep their URL while a restore (not a parallel insert) is required.
alter table source_pages
  drop constraint if exists source_pages_source_id_url_key;

create unique index if not exists source_pages_active_source_url_uidx
  on source_pages (source_id, url)
  where deleted_at is null;

create index if not exists source_pages_deleted_at_idx
  on source_pages (deleted_at)
  where deleted_at is not null;
