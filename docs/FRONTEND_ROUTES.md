# Resolven Regulatory AI Frontend Routes

The frontend is a vinext/Next app in `apps/web`. The main client shell is `apps/web/app/resolven-app.tsx`; each route passes an initial route key into that shared shell.

## Routes

- `/`
  - Today briefing, latest digest, export buttons, event selection, and docked insight chat.
- `/browse`
  - Archive search with topic and jurisdiction filters.
- `/saved`
  - Bookmarked regulatory updates.
- `/events/{id}`
  - Event detail, source link, read/bookmark actions, and grounded chat.
- `/notifications`
  - Email digest and topic subscription settings.
- `/account`
  - Current account/session state.
- `/admin/sources`
  - Source health and enable/disable actions for admins.
- `/admin/runs`
  - Crawl run timeline for admins.
- `/api-docs`
  - Backend API documentation loaded from `app_documents`.
- `/flow`
  - End-to-end product flow loaded from `app_documents`.

## Core UI Pieces

- App shell: persistent left navigation on desktop, horizontal rail on mobile.
- Docket Strip: jurisdiction, issuing body, issue date, and event type.
- Event card: title, plain-English summary, tags, read/bookmark/source actions.
- Insight chat: selected-event context, prompt chips, answer panel, and send control.
- Export bar: JSON, CSV, and Markdown downloads for latest news.

## Runtime Configuration

Required browser-safe variables:

```env
NEXT_PUBLIC_SUPABASE_URL=
NEXT_PUBLIC_SUPABASE_ANON_KEY=
NEXT_PUBLIC_API_BASE_URL=http://localhost:8001
```

The app also reads `VITE_SUPABASE_URL`, `VITE_SUPABASE_ANON_KEY`, and `VITE_API_BASE_URL` for vinext compatibility.
