create table if not exists source_page_checkpoints (
  id bigint generated always as identity primary key,
  source_page_id bigint not null references source_pages(id) on delete cascade,
  checkpoint_key text not null,
  checkpoint_url text,
  checkpoint_title text,
  checkpoint_issue_date date,
  checkpoint_published_at timestamptz,
  checkpoint_source_record_id text,
  checkpoint_content_hash text,
  checkpoint_payload jsonb not null default '{}',
  lookback_count int not null default 3,
  last_successful_run_id bigint references crawl_runs(id) on delete set null,
  last_successful_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (source_page_id)
);

create index if not exists source_page_checkpoints_key_idx
  on source_page_checkpoints (source_page_id, checkpoint_key);

create index if not exists source_page_checkpoints_date_idx
  on source_page_checkpoints (source_page_id, checkpoint_issue_date desc);

alter table source_page_checkpoints enable row level security;

drop policy if exists source_page_checkpoints_read on source_page_checkpoints;
create policy source_page_checkpoints_read on source_page_checkpoints
  for select to authenticated using (true);
