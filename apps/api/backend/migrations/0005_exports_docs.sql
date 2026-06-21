create table if not exists app_documents (
  slug text primary key,
  title text not null,
  category text not null,
  content_md text not null,
  updated_at timestamptz not null default now()
);

create table if not exists exports_log (
  id bigint generated always as identity primary key,
  user_id uuid references auth.users(id) on delete set null,
  export_type text not null,
  export_format text not null,
  row_count int not null default 0,
  created_at timestamptz not null default now()
);

alter table app_documents enable row level security;
alter table exports_log enable row level security;

drop policy if exists app_documents_read on app_documents;
create policy app_documents_read on app_documents
  for select to authenticated using (true);

drop policy if exists own_exports_read on exports_log;
create policy own_exports_read on exports_log
  for select to authenticated using (auth.uid() = user_id);
