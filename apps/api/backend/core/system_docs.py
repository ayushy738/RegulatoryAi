SYSTEM_DOCUMENTS = [
    {
        "slug": "backend-api",
        "title": "Backend API Reference",
        "category": "api",
        "content_md": """# Resolven Regulatory AI Backend API

Base URL comes from `API_BASE_URL` or `NEXT_PUBLIC_API_BASE_URL`.

Authentication uses Supabase Auth access tokens: `Authorization: Bearer <supabase-access-token>`.

Local development may set `AUTH_REQUIRED=false`, which returns a demo user for app testing.

## Health
- `GET /health` - runtime readiness, DB connectivity, storage, and provider status.

## Digests
- `GET /digests/latest` - latest daily digest with events.
- `GET /digests/{YYYY-MM-DD}` - digest for a specific date.

## Events
- `GET /events` - archive search.
  Query params: `q`, `jurisdiction`, `source`, `topic`, `date_from`, `date_to`,
  `bookmarked`, `page`.
- `GET /events/{id}` - event detail.
- `POST /events/{id}/read` - mark event read.
- `POST /events/{id}/bookmark` - toggle bookmark.

## Chat
- `POST /chat` - grounded event/global chat.
  Body: `{ "event_id": number | null, "message": string }`.
- `GET /chat/history?event_id={id}` - saved chat history.

## Subscriptions
- `GET /subscriptions` - current notification preferences.
- `PUT /subscriptions` - update jurisdictions, source ids, topics, email toggle, and frequency.

## Exports
- `GET /exports/latest?format=json|csv|markdown` - download latest digest/news in
  the requested file format and log the export.

## Admin
- Admin endpoints require an admin role in `user_profiles.role`.
- `GET /admin/sources` - source configuration and health.
- `POST /admin/sources/{id}/toggle` - enable/disable a source.
- `GET /admin/runs` - pipeline run history.

## Documentation
- `GET /meta/docs` - list database-backed documents.
- `GET /meta/docs/{slug}` - retrieve one document.
""",
    },
    {
        "slug": "frontend-routes",
        "title": "Frontend Route Map",
        "category": "frontend",
        "content_md": """# Resolven Regulatory AI Frontend Routes

The frontend is a vinext/Next app in `apps/web`.
The main client shell is `apps/web/app/resolven-app.tsx`.

Routes:
- `/` - Today briefing with latest digest and export actions.
- `/browse` - searchable archive over events.
- `/saved` - bookmarked updates.
- `/events/{id}` - event detail with grounded insight chat.
- `/notifications` - subscription and digest email preferences.
- `/account` - account/session/runtime details.
- `/admin/sources` - source health and enable/disable actions.
- `/admin/runs` - crawl-run timeline.
- `/api-docs` - backend API documentation.
- `/flow` - end-to-end product flow documentation.

Core UI primitives:
- App shell: persistent left navigation on desktop, horizontal rail on mobile.
- Docket strip: jurisdiction, source/body, issue date, event type.
- Event card: docket strip, title, summary, topics, read/bookmark/source actions.
- Insight chat: selected event context, suggestions, answer panel.
- Export bar: JSON, CSV, Markdown export for the latest news.

Runtime configuration:
- `NEXT_PUBLIC_SUPABASE_URL`
- `NEXT_PUBLIC_SUPABASE_ANON_KEY`
- `NEXT_PUBLIC_API_BASE_URL`
- `VITE_SUPABASE_URL`, `VITE_SUPABASE_ANON_KEY`, and `VITE_API_BASE_URL`
  are also supported for vinext compatibility.
""",
    },
    {
        "slug": "complete-flow",
        "title": "Complete Product Flow",
        "category": "flow",
        "content_md": """# Complete Product Flow

1. Source configuration lives in Supabase `sources`.
2. The pipeline reads enabled sources, politely discovers public regulatory documents,
   and falls back to Parallel Search when a site listing is unreliable.
3. Each discovered document is canonicalized and upserted into `documents`.
4. New versions are written to `document_versions`.
5. Change detection creates visible `events` only when content is new or changed.
6. Non-AI summaries are stored immediately in `summaries`; AI enrichment can update
   the same event/model slot later.
7. `digests` and `digest_events` link the day's visible events into one daily briefing.
8. Users sign in with Supabase Auth and read the same cached digest.
9. Per-user state lives in `user_event_state`: read/unread and bookmarks.
10. Chat requests are grounded to selected event context and persisted in `chat_messages`.
11. Subscription preferences live in `subscriptions`.
12. Latest-news export requests are logged in `exports_log` and returned as JSON, CSV, or Markdown.
13. Admins monitor `crawl_runs` and source health to catch broken government sites quickly.
""",
    },
]
