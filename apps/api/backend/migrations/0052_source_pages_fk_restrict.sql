-- Prevent source deletion from cascading into hard-deletes of source_pages.
-- Active and retired page configuration must go through the explicit page lifecycle:
-- Remove (soft) → Permanently Delete (hard), never via Delete Source cascade.

alter table source_pages
  drop constraint if exists source_pages_source_id_fkey;

alter table source_pages
  add constraint source_pages_source_id_fkey
  foreign key (source_id) references sources(id) on delete restrict;

comment on constraint source_pages_source_id_fkey on source_pages is
  'Sources cannot cascade-delete pages; remove/permanently delete pages first.';
