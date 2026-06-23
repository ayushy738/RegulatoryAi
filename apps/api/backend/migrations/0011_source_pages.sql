create table if not exists source_pages (
  id bigint generated always as identity primary key,
  source_id bigint not null references sources(id) on delete cascade,
  name text not null,
  url text not null,
  page_type text not null,
  priority int not null default 100,
  enabled boolean not null default true,
  last_crawled_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (source_id, url)
);

create index if not exists source_pages_source_idx on source_pages (source_id);
create index if not exists source_pages_enabled_priority_idx
  on source_pages (enabled, priority, id);
create index if not exists source_pages_page_type_idx on source_pages (page_type);

alter table source_pages enable row level security;

drop policy if exists source_pages_read on source_pages;
create policy source_pages_read on source_pages
  for select to authenticated using (true);

insert into sources (code, name, jurisdiction, url, crawler_type, allowed_domains, hint, enabled)
values
  (
    'seci',
    'Solar Energy Corporation of India',
    'central',
    'https://www.seci.co.in',
    'agent',
    array['seci.co.in', 'www.seci.co.in'],
    'Curated tender source. Crawl only configured source_pages entries.',
    true
  )
on conflict (code) do update set
  name = excluded.name,
  jurisdiction = excluded.jurisdiction,
  url = excluded.url,
  crawler_type = excluded.crawler_type,
  allowed_domains = excluded.allowed_domains,
  hint = excluded.hint,
  enabled = excluded.enabled,
  updated_at = now();

with page_seed(code, name, url, page_type, priority, enabled) as (
  values
    (
      'mnre',
      'Current Notices',
      'https://mnre.gov.in/en/notice-category/current-notices/',
      'notice_listing',
      10,
      true
    ),
    (
      'mnre',
      'Monthly Updates',
      'https://mnre.gov.in/en/monthly-updates/',
      'digest_listing',
      20,
      true
    ),
    (
      'cerc',
      'Public Notice',
      'https://cercind.gov.in/public-notice.html',
      'public_notice_listing',
      10,
      true
    ),
    (
      'cerc',
      'Suo Motu Petitions / Staff Papers / Notices',
      'https://cercind.gov.in/SPN.html',
      'spn_listing',
      20,
      true
    ),
    (
      'cerc',
      'Notice / Letter',
      'https://cercind.gov.in/notice-letter.html',
      'notice_letter_listing',
      30,
      true
    ),
    (
      'seci',
      'Tenders',
      'https://www.seci.co.in/tenders',
      'tender_listing',
      10,
      true
    ),
    (
      'mop',
      'What''s New',
      'https://www.powermin.gov.in/whats-new',
      'whats_new_listing',
      10,
      true
    )
)
insert into source_pages (source_id, name, url, page_type, priority, enabled, updated_at)
select s.id, page_seed.name, page_seed.url, page_seed.page_type, page_seed.priority,
       page_seed.enabled, now()
from page_seed
join sources s on s.code = page_seed.code
on conflict (source_id, url) do update set
  name = excluded.name,
  page_type = excluded.page_type,
  priority = excluded.priority,
  enabled = excluded.enabled,
  updated_at = now();
