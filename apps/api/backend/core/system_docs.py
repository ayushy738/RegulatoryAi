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

## Intelligence
- `GET /intelligence/deadlines` - active graph deadlines.
  Query params: `issuer`, `deadline_type`, `stakeholder`, `status=active|historical|all`,
  `limit`.
- `GET /intelligence/obligations` - obligations grouped by stakeholder.
  Query params: `stakeholder`, `issuer`, `limit`.
- `GET /intelligence/stakeholders` - stakeholder intelligence cards for the supported
  energy-sector stakeholder set.
- `GET /intelligence/stakeholders/{stakeholder}` - one stakeholder view.
- `GET /intelligence/readiness` - product-readiness snapshot over deadlines,
  obligations, impacts, and consultations.

## Subscriptions
- `GET /subscriptions` - current notification preferences.
- `PUT /subscriptions` - update jurisdictions, source ids, topics, email toggle, and frequency.

## Exports
- `GET /exports/latest?format=json|csv|markdown` - download latest digest/news in
  the requested file format and log the export.

## Admin
- Admin endpoints require an admin role in `user_profiles.role`.
- `GET /admin/sources` - source configuration and health.
- `POST /admin/sources` - create a source.
- `PUT /admin/sources/{id}` - update a source.
- `DELETE /admin/sources/{id}` - delete a source.
- `GET /admin/sources/{id}/pages` - list curated crawl pages for a source.
- `POST /admin/sources/{id}/pages` - create a curated crawl page.
- `PUT /admin/pages/{id}` - update a curated crawl page.
- `DELETE /admin/pages/{id}` - delete a curated crawl page.
- `POST /admin/pages/{id}/crawl` - crawl one curated source page.
- `POST /admin/sources/{id}/crawl` - crawl all enabled curated pages for a source.
- `GET /admin/runs` - pipeline run history.
- `GET /admin/runs/{id}` - one pipeline run.
- `GET /admin/sources/{id}/analytics` - source discovery and event-yield analytics.

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
- `/intelligence` - deadlines, obligations, stakeholder impact, and consultation
  tracking powered by the knowledge graph.
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
2. Curated crawl entrypoints live in `source_pages`.
3. The pipeline reads enabled source pages and discovers only primary PDFs or primary
   HTML notices from those curated listing pages.
4. Each accepted primary document is canonicalized and upserted into `documents`.
5. New versions are written to `document_versions`.
6. Change detection creates visible `events` only when content is new or changed.
7. Non-AI summaries are stored immediately in `summaries`; AI enrichment can update
   the same event/model slot later.
8. `digests` and `digest_events` link the day's visible events into one daily briefing.
9. Users sign in with Supabase Auth and read the same cached digest.
10. Per-user state lives in `user_event_state`: read/unread and bookmarks.
11. The knowledge graph stores entities, relationships, stakeholders, obligations, and
    deadlines for accepted primary documents.
12. The intelligence APIs expose active deadlines, obligations, stakeholder impacts,
    and consultation tracking directly from the graph.
13. Chat requests are grounded to selected event context and persisted in `chat_messages`.
14. Subscription preferences live in `subscriptions`.
15. Latest-news export requests are logged in `exports_log` and returned as JSON, CSV, or Markdown.
16. Admins monitor `crawl_runs`, `source_pages`, and source analytics to catch broken
    government pages quickly.
""",
    },
]
