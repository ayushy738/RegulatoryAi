# Resolven Regulatory AI Complete Flow

## Data Ingestion

1. Source configuration lives in Supabase `sources`.
2. The pipeline reads enabled sources.
3. Public regulatory pages are discovered with polite HTTP scraping.
4. Sites with unreliable listing pages can fall back to Parallel Search.
5. Discovered documents are canonicalized and upserted into `documents`.
6. New document content is versioned in `document_versions`.

## Intelligence Layer

1. Change detection creates visible `events` only when content is new or changed.
2. Baseline summaries are stored immediately in `summaries`.
3. LLM enrichment can update the same event/model slot with stronger explanation and evidence.
4. `digests` and `digest_events` group visible events into daily briefings.

## User Product

1. Users sign in with Supabase Auth.
2. The frontend reads cached digest/event data from the FastAPI backend.
3. Per-user read and bookmark state is stored in `user_event_state`.
4. Chat requests are grounded to the selected event or recent digest context.
5. Chat messages are stored in `chat_messages`.
6. Subscription preferences are stored in `subscriptions`.
7. Latest-news exports are returned as JSON, CSV, or Markdown and logged in `exports_log`.

## Operations

1. Admins inspect source health in `/admin/sources`.
2. Admins inspect crawl history in `/admin/runs`.
3. App documentation is stored in `app_documents` and rendered in `/api-docs` and `/flow`.
