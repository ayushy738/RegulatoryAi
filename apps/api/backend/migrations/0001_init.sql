-- ===== enums =====
create type jurisdiction_t   as enum ('central','state');
create type crawler_t        as enum ('digest','agent','static');
create type event_t          as enum ('NEW','CHANGED','REPLACEMENT','DUPLICATE');
create type date_precision_t as enum ('day','month','year','unknown');
create type run_status_t      as enum ('running','success','partial','failed');
create type notify_channel_t  as enum ('email','slack','whatsapp');
create type notify_status_t   as enum ('pending','sent','failed','skipped');
create type user_role_t       as enum ('user','admin');

-- ===== sources (config, DB-backed so admins edit via UI) =====
create table sources (
  id bigint generated always as identity primary key,
  code text unique not null,
  name text not null,
  jurisdiction jurisdiction_t not null,
  url text not null,
  crawler_type crawler_t not null default 'agent',
  allowed_domains text[] not null default '{}',
  hint text,
  enabled boolean not null default true,
  last_checked_at timestamptz,
  last_status int,
  consecutive_failures int not null default 0,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

-- ===== documents (deduped regulatory docs) =====
create table documents (
  id bigint generated always as identity primary key,
  source_id bigint references sources(id) on delete set null,
  url_hash text unique not null,
  source_url text not null,
  title text not null,
  issuing_body text,
  jurisdiction jurisdiction_t,
  issue_date date,
  issue_date_precision date_precision_t default 'unknown',
  doc_type text,
  first_seen_at timestamptz not null default now(),
  last_seen_at timestamptz not null default now(),
  created_at timestamptz not null default now()
);
create index on documents (source_id);
create index on documents (issue_date desc);

-- ===== document versions (change detection baseline) =====
create table document_versions (
  id bigint generated always as identity primary key,
  document_id bigint not null references documents(id) on delete cascade,
  file_hash text,
  content_hash text,
  raw_file_path text,
  text_path text,
  page_count int,
  needs_ocr boolean default false,
  http_status int,
  etag text,
  last_modified text,
  fetched_at timestamptz not null default now(),
  unique (document_id, file_hash)
);
create index on document_versions (document_id);

-- ===== events (what users see) =====
create table events (
  id bigint generated always as identity primary key,
  document_id bigint not null references documents(id) on delete cascade,
  version_id bigint references document_versions(id) on delete set null,
  event_type event_t not null,
  digest_origin text,
  raw_summary text,
  topic_tags text[] not null default '{}',
  suppressed boolean not null default false,
  detected_at timestamptz not null default now(),
  created_at timestamptz not null default now()
);
create index on events (detected_at desc);
create index on events (suppressed);
create index on events using gin (topic_tags);

-- ===== AI summaries =====
create table summaries (
  id bigint generated always as identity primary key,
  event_id bigint not null references events(id) on delete cascade,
  model text not null,
  summary_json jsonb not null,
  key_points text[],
  tokens_used int,
  created_at timestamptz not null default now(),
  unique (event_id, model)
);

-- ===== daily digests =====
create table digests (
  id bigint generated always as identity primary key,
  digest_date date unique not null,
  event_count int not null default 0,
  created_at timestamptz not null default now()
);
create table digest_events (
  digest_id bigint references digests(id) on delete cascade,
  event_id  bigint references events(id) on delete cascade,
  primary key (digest_id, event_id)
);

-- ===== users / profiles =====
create table profiles (
  id uuid primary key references auth.users(id) on delete cascade,
  email text,
  full_name text,
  role user_role_t not null default 'user',
  created_at timestamptz not null default now()
);

-- ===== subscriptions (notification preferences) =====
create table subscriptions (
  id bigint generated always as identity primary key,
  user_id uuid not null references auth.users(id) on delete cascade,
  jurisdictions jurisdiction_t[] not null default '{}',
  source_ids bigint[] not null default '{}',
  topics text[] not null default '{}',
  email_enabled boolean not null default true,
  frequency text not null default 'daily',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (user_id)
);

-- ===== per-user read/bookmark state =====
create table user_event_state (
  user_id uuid not null references auth.users(id) on delete cascade,
  event_id bigint not null references events(id) on delete cascade,
  is_read boolean not null default false,
  is_bookmarked boolean not null default false,
  read_at timestamptz,
  primary key (user_id, event_id)
);

-- ===== pipeline run log =====
create table crawl_runs (
  id bigint generated always as identity primary key,
  started_at timestamptz not null default now(),
  finished_at timestamptz,
  status run_status_t not null default 'running',
  sources_attempted int default 0,
  sources_succeeded int default 0,
  docs_found int default 0,
  new_events int default 0,
  errors jsonb not null default '[]'
);

-- ===== notification log (dedup: never double-notify) =====
create table notifications_log (
  id bigint generated always as identity primary key,
  user_id uuid not null references auth.users(id) on delete cascade,
  event_id bigint not null references events(id) on delete cascade,
  channel notify_channel_t not null default 'email',
  status notify_status_t not null default 'pending',
  provider_message_id text,
  error text,
  sent_at timestamptz,
  created_at timestamptz not null default now(),
  unique (user_id, event_id, channel)
);

-- ===== insight chat history =====
create table chat_messages (
  id bigint generated always as identity primary key,
  user_id uuid not null references auth.users(id) on delete cascade,
  event_id bigint references events(id) on delete set null,
  role text not null,
  content text not null,
  created_at timestamptz not null default now()
);
create index on chat_messages (user_id, created_at);

-- ===== admin audit =====
create table audit_log (
  id bigint generated always as identity primary key,
  actor_id uuid references auth.users(id) on delete set null,
  action text not null,
  target text,
  detail jsonb,
  created_at timestamptz not null default now()
);
