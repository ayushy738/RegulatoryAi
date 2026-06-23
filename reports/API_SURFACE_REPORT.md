# API Surface Report

Generated from source inspection of:

- Backend FastAPI app: `apps/api/backend/api`
- Backend models/repositories: `apps/api/backend/core`
- Frontend API client: `apps/web/lib/api.ts`
- Frontend Supabase client: `apps/web/lib/supabase.ts`
- Frontend app routes/screens: `apps/web/app`

## Executive Summary

- Backend HTTP endpoints created: **22**
- Frontend typed API helper functions created: **21**
- Active frontend product API routes: **0**
- Example-only frontend API routes: **2** under `apps/web/examples/d1/app/api/notes/route.ts`
- Backend framework: FastAPI
- Frontend framework: Next/Vinext-style app router using client-side API calls
- Auth provider: Supabase Auth
- Main API base URL env: `NEXT_PUBLIC_API_BASE_URL` or `VITE_API_BASE_URL`
- Frontend auth env: `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY`, `VITE_SUPABASE_URL`, `VITE_SUPABASE_ANON_KEY`

The product API is primarily backend-driven. The frontend does not currently expose its own active product API routes; it provides a typed client layer that calls the backend API and uses Supabase directly for login/session management.

## Backend API Overview

Backend entrypoint:

- `apps/api/backend/api/main.py`

Routers mounted:

- `digests.router`
- `events.router`
- `chat.router`
- `subscriptions.router`
- `admin.router`
- `exports.router`
- `meta.router`
- `intelligence.router`

Cross-cutting behavior:

- CORS is configured from `settings.cors_origin_list`.
- Most product endpoints require `Authorization: Bearer <supabase_access_token>`.
- If `AUTH_REQUIRED` is disabled, the backend falls back to the demo user.
- Admin endpoints require the current user's `profiles.role` to be `admin`.
- `POST /chat` has an in-memory rate limit of 30 requests per 60 seconds per client key.

FastAPI also provides generated documentation endpoints automatically:

- `GET /docs`
- `GET /redoc`
- `GET /openapi.json`

## Backend Endpoint Inventory

| # | Method | Path | Router | Auth | Purpose |
|---:|---|---|---|---|---|
| 1 | `GET` | `/health` | app root | No bearer required by route | Health, DB, storage, and LLM status |
| 2 | `GET` | `/digests/latest` | digests | User | Latest digest with events |
| 3 | `GET` | `/digests/{digest_date}` | digests | User | Digest for a specific date |
| 4 | `GET` | `/events` | events | User | Search/list events |
| 5 | `GET` | `/events/{event_id}` | events | User | Event detail |
| 6 | `POST` | `/events/{event_id}/read` | events | User | Mark event as read |
| 7 | `POST` | `/events/{event_id}/bookmark` | events | User | Toggle bookmark |
| 8 | `POST` | `/chat` | chat | User + rate limit | Ask insight question |
| 9 | `GET` | `/chat/history` | chat | User | Chat history |
| 10 | `GET` | `/subscriptions` | subscriptions | User | Read notification preferences |
| 11 | `PUT` | `/subscriptions` | subscriptions | User | Update notification preferences |
| 12 | `GET` | `/admin/sources` | admin | Admin | List configured sources |
| 13 | `POST` | `/admin/sources/{source_id}/toggle` | admin | Admin | Enable/disable a source |
| 14 | `GET` | `/admin/runs` | admin | Admin | List crawl runs |
| 15 | `GET` | `/exports/latest` | exports | User | Export latest digest |
| 16 | `GET` | `/meta/docs` | meta | Public route in code | List app docs |
| 17 | `GET` | `/meta/docs/{slug}` | meta | Public route in code | Read one app doc |
| 18 | `GET` | `/intelligence/deadlines` | intelligence | User | Active/historical deadline center |
| 19 | `GET` | `/intelligence/obligations` | intelligence | User | Obligation center grouped by stakeholder |
| 20 | `GET` | `/intelligence/stakeholders` | intelligence | User | Stakeholder intelligence list |
| 21 | `GET` | `/intelligence/stakeholders/{stakeholder_slug}` | intelligence | User | Stakeholder detail |
| 22 | `GET` | `/intelligence/readiness` | intelligence | User | Intelligence readiness/demo payload |

## Backend Endpoint Details

### 1. `GET /health`

File:

- `apps/api/backend/api/main.py`

Purpose:

- Reports whether the API is alive and whether key dependencies are configured/connected.

Request:

- No path parameters.
- No query parameters.
- No explicit `UserDep`.

Response:

```json
{
  "status": "ok",
  "database_configured": true,
  "database_connected": true,
  "storage_configured": true,
  "llm_provider": "offline",
  "effective_llm_provider": "parallel"
}
```

Notes:

- Returns `status: "degraded"` if the database is missing or unreachable.
- `effective_llm_provider` becomes `parallel` when `llm_provider` is `offline` but `parallel_api_key` exists.

### 2. `GET /digests/latest`

File:

- `apps/api/backend/api/routes/digests.py`

Purpose:

- Returns the latest digest and all events in that digest.

Auth:

- Requires `UserDep`.

Response model:

- `DigestResponse`

Response shape:

```json
{
  "digest_date": "2026-06-22",
  "event_count": 3,
  "events": []
}
```

Backend data path:

- `latest_digest(user.id)`
- Reads digest/event state from repository and joins per-user read/bookmark state.

Frontend helper:

- `getLatestDigest(token?)`

Frontend usage:

- Main dashboard/today load.
- Base app data load.

### 3. `GET /digests/{digest_date}`

File:

- `apps/api/backend/api/routes/digests.py`

Purpose:

- Returns a digest for a specific date.

Auth:

- Requires `UserDep`.

Path parameters:

- `digest_date`: ISO date, for example `2026-06-22`

Response model:

- `DigestResponse`

Backend data path:

- `digest_by_date(digest_date, user.id)`

Frontend coverage:

- No dedicated frontend helper currently exists for this endpoint.

### 4. `GET /events`

File:

- `apps/api/backend/api/routes/events.py`

Purpose:

- Lists/searches regulatory events.

Auth:

- Requires `UserDep`.

Query parameters:

| Parameter | Type | Meaning |
|---|---|---|
| `q` | `string` | Search title/source/topic text |
| `jurisdiction` | `string` | Filter by `central` or `state` |
| `source` | `string` | Filter by source |
| `topic` | `string` | Filter by topic tag |
| `date_from` | `date` | Start date filter |
| `date_to` | `date` | End date filter |
| `bookmarked` | `boolean` | Show bookmarked/non-bookmarked |
| `page` | `integer >= 1` | Page number |

Response model:

- `list[EventSummary]`

Backend data path:

- `list_events(...)`

Frontend helper:

- `getEvents(token?, filters?)`

Frontend coverage gap:

- Frontend helper supports `query`, `jurisdiction`, `source`, `topic`, `bookmarked`, and `page`.
- Frontend helper does **not** currently expose `date_from` or `date_to`.

### 5. `GET /events/{event_id}`

File:

- `apps/api/backend/api/routes/events.py`

Purpose:

- Reads one event detail.

Auth:

- Requires `UserDep`.

Path parameters:

- `event_id`: numeric event ID

Response model:

- `EventSummary`

Errors:

- `404 Event not found`

Backend data path:

- `get_event(event_id, user.id)`

Frontend helper:

- `getEvent(eventId, token?)`

Frontend usage:

- `/events/[eventId]`

### 6. `POST /events/{event_id}/read`

File:

- `apps/api/backend/api/routes/events.py`

Purpose:

- Marks an event as read for the current user.

Auth:

- Requires `UserDep`.

Path parameters:

- `event_id`: numeric event ID

Request body:

- None

Response:

```json
{
  "event_id": 123,
  "is_read": true
}
```

Backend data path:

- `mark_event_state(user.id, event_id, is_read=True)`

Frontend helper:

- `markRead(eventId, token?)`

### 7. `POST /events/{event_id}/bookmark`

File:

- `apps/api/backend/api/routes/events.py`

Purpose:

- Toggles bookmark state for the current user.

Auth:

- Requires `UserDep`.

Path parameters:

- `event_id`: numeric event ID

Request body:

- None

Response:

```json
{
  "event_id": 123,
  "is_bookmarked": true
}
```

Backend data path:

- Reads current state with `get_event(...)`.
- Updates state with `mark_event_state(...)`.

Frontend helper:

- `toggleBookmark(eventId, token?)`

### 8. `POST /chat`

File:

- `apps/api/backend/api/routes/chat.py`

Purpose:

- Answers a regulatory question using recent events or a selected event as retrieval context.

Auth:

- Requires `UserDep`.

Rate limit:

- 30 requests per 60 seconds per client key.

Request model:

- `ChatRequest`

Request body:

```json
{
  "message": "What changed and who is affected?",
  "event_id": 123
}
```

Request validation:

- `message`: min length `1`, max length `4000`
- `event_id`: optional

Response model:

- `ChatResponse`

Response:

```json
{
  "reply": "Plain-language answer...",
  "event_id": 123,
  "model": "configured-model-name"
}
```

Errors:

- `429 Rate limit exceeded`
- `502` when LLM client raises a runtime error

Backend data path:

- Pulls recent events via `list_events(page_size=5)` or selected event via `get_event(...)`.
- Pulls chat history via `chat_history(...)`.
- Saves user and assistant messages via `save_chat_message(...)`.
- Calls `get_llm_client().complete_text(...)`.

Frontend helper:

- `sendChat(message, eventId, token?)`

### 9. `GET /chat/history`

File:

- `apps/api/backend/api/routes/chat.py`

Purpose:

- Returns stored chat history.

Auth:

- Requires `UserDep`.

Query parameters:

| Parameter | Type | Meaning |
|---|---|---|
| `event_id` | `integer` | Optional event-specific history filter |

Response:

```json
[
  {
    "id": 1,
    "role": "user",
    "content": "Question",
    "event_id": 123,
    "created_at": "2026-06-22T00:00:00Z"
  }
]
```

Backend data path:

- `chat_history(user.id, event_id)`

Frontend coverage:

- No dedicated frontend helper currently exists.

### 10. `GET /subscriptions`

File:

- `apps/api/backend/api/routes/subscriptions.py`

Purpose:

- Reads notification preferences for the current user.

Auth:

- Requires `UserDep`.

Response model:

- `SubscriptionSettings`

Response shape:

```json
{
  "jurisdictions": ["central"],
  "source_ids": [],
  "topics": ["solar", "tariff"],
  "email_enabled": true,
  "frequency": "daily"
}
```

Backend data path:

- `get_subscription(user.id)`

Frontend helper:

- `getSubscriptions(token?)`

### 11. `PUT /subscriptions`

File:

- `apps/api/backend/api/routes/subscriptions.py`

Purpose:

- Updates notification preferences.

Auth:

- Requires `UserDep`.

Request/response model:

- `SubscriptionSettings`

Request body:

```json
{
  "jurisdictions": ["central", "state"],
  "source_ids": [1, 2],
  "topics": ["solar", "open access"],
  "email_enabled": true,
  "frequency": "daily"
}
```

Allowed frequency:

- `daily`
- `instant`

Backend data path:

- `update_subscription(user.id, payload)`

Frontend helper:

- `saveSubscriptions(payload, token?)`

### 12. `GET /admin/sources`

File:

- `apps/api/backend/api/routes/admin.py`

Purpose:

- Lists configured crawl sources and source health.

Auth:

- Requires admin user.

Response:

```json
[
  {
    "id": 1,
    "code": "mop",
    "name": "Ministry of Power",
    "jurisdiction": "central",
    "url": "https://powermin.gov.in/en",
    "crawler_type": "agent",
    "allowed_domains": ["powermin.gov.in"],
    "enabled": true,
    "last_checked_at": null,
    "last_status": null,
    "consecutive_failures": 0
  }
]
```

Backend data path:

- `list_sources()`

Frontend helper:

- `getSources(token?)`

Frontend usage:

- Admin source page.
- Also used during app bootstrap as a lightweight admin-permission check.

### 13. `POST /admin/sources/{source_id}/toggle`

File:

- `apps/api/backend/api/routes/admin.py`

Purpose:

- Toggles whether a source is enabled.

Auth:

- Requires admin user.

Path parameters:

- `source_id`: numeric source ID

Request body:

- None

Response:

```json
{
  "source_id": 1,
  "enabled": false
}
```

Backend data path:

- `toggle_source(source_id)`

Frontend helper:

- `toggleSource(sourceId, token?)`

### 14. `GET /admin/runs`

File:

- `apps/api/backend/api/routes/admin.py`

Purpose:

- Lists recent crawl runs.

Auth:

- Requires admin user.

Response:

```json
[
  {
    "id": 1,
    "started_at": "2026-06-22T00:00:00Z",
    "finished_at": "2026-06-22T00:05:00Z",
    "status": "success",
    "sources_attempted": 3,
    "sources_succeeded": 3,
    "docs_found": 10,
    "new_events": 2,
    "errors": []
  }
]
```

Backend data path:

- `list_crawl_runs()`

Frontend helper:

- `getRuns(token?)`

### 15. `GET /exports/latest`

File:

- `apps/api/backend/api/routes/exports.py`

Purpose:

- Exports the latest digest as a downloadable file.

Auth:

- Requires `UserDep`.

Query parameters:

| Parameter | Type | Allowed Values | Default |
|---|---|---|---|
| `format` | `string` | `json`, `csv`, `markdown` | `json` |

Response:

- `application/json` for `format=json`
- `text/csv; charset=utf-8` for `format=csv`
- `text/markdown; charset=utf-8` for `format=markdown`

Response headers:

- `Content-Disposition: attachment; filename="resolven-regulatory-ai-{digest_date}.{extension}"`

Backend data path:

- `latest_digest(user.id)`
- `record_export(user.id, "latest_digest", format, len(digest.events))`

Frontend helpers:

- `exportLatestUrl(format)`
- `downloadLatestExport(format, token?)`

### 16. `GET /meta/docs`

File:

- `apps/api/backend/api/routes/meta.py`

Purpose:

- Lists in-app documentation documents.

Auth:

- No `UserDep` in the route. It is public at the backend route level.

Response:

```json
[
  {
    "slug": "backend-api",
    "title": "Backend API",
    "category": "documentation"
  }
]
```

Backend data path:

- `list_system_documents()`

Frontend helper:

- `getDocs(token?)`

Frontend coverage:

- Helper exists, but current app screens mostly call `getDoc(...)` directly.

### 17. `GET /meta/docs/{slug}`

File:

- `apps/api/backend/api/routes/meta.py`

Purpose:

- Reads one in-app documentation document.

Auth:

- No `UserDep` in the route. It is public at the backend route level.

Path parameters:

- `slug`: document slug, for example `backend-api` or `complete-flow`

Response:

```json
{
  "slug": "backend-api",
  "title": "Backend API",
  "category": "documentation",
  "content_md": "..."
}
```

Errors:

- `404 Document not found`

Backend data path:

- `get_system_document(slug)`

Frontend helper:

- `getDoc(slug, token?)`

Frontend usage:

- `/api-docs` loads `backend-api`.
- `/flow` loads `complete-flow`.

### 18. `GET /intelligence/deadlines`

File:

- `apps/api/backend/api/routes/intelligence.py`

Purpose:

- Returns active, historical, or all deadlines extracted from the regulatory graph.

Auth:

- Requires `UserDep`.

Query parameters:

| Parameter | Type | Meaning |
|---|---|---|
| `issuer` | `string` | Filter by issuer |
| `deadline_type` | `string` | Filter by deadline type |
| `stakeholder` | `string` | Filter by affected stakeholder |
| `status` | `string` | `active`, `historical`, or `all`; default `active` |
| `limit` | `integer` | Min `1`, max `500`, default `100` |

Response model:

- `list[IntelligenceDeadline]`

Response item shape:

```json
{
  "document_id": 1,
  "title": "Document title",
  "issuer": "Ministry of Power",
  "deadline_type": "COMPLIANCE_DEADLINE",
  "deadline_date": "2026-07-31",
  "raw_date": "31 July 2026",
  "days_remaining": 39,
  "stakeholders_affected": ["DISCOMs"],
  "source_url": "https://...",
  "confidence": 0.8,
  "evidence": "Evidence snippet"
}
```

Backend data path:

- `list_intelligence_deadlines(...)`

Frontend helper:

- `getIntelligenceDeadlines(token?, filters?)`

### 19. `GET /intelligence/obligations`

File:

- `apps/api/backend/api/routes/intelligence.py`

Purpose:

- Returns obligations grouped by stakeholder.

Auth:

- Requires `UserDep`.

Query parameters:

| Parameter | Type | Meaning |
|---|---|---|
| `stakeholder` | `string` | Filter by stakeholder |
| `issuer` | `string` | Filter by issuer |
| `limit` | `integer` | Min `1`, max `500`, default `200` |

Response model:

- `list[StakeholderObligationGroup]`

Response shape:

```json
[
  {
    "stakeholder": "DISCOMs",
    "obligations": [
      {
        "document_id": 1,
        "title": "Document title",
        "issuer": "Ministry of Power",
        "obligation": "Comply with ...",
        "stakeholder": "DISCOMs",
        "deadline_date": "2026-07-31",
        "deadline_type": "COMPLIANCE_DEADLINE",
        "confidence": 0.8,
        "evidence": "Evidence snippet",
        "source_url": "https://..."
      }
    ]
  }
]
```

Backend data path:

- `list_obligation_groups(...)`

Frontend helper:

- `getIntelligenceObligations(token?, filters?)`

### 20. `GET /intelligence/stakeholders`

File:

- `apps/api/backend/api/routes/intelligence.py`

Purpose:

- Returns intelligence summaries for all supported stakeholders.

Auth:

- Requires `UserDep`.

Response model:

- `list[StakeholderIntelligence]`

Response contains:

- `stakeholder`
- `impact_summary`
- `compliance_summary`
- `action_summary`
- `regulations`
- `consultations`
- `obligations`
- `deadlines`
- `tenders`
- `counts`

Backend data path:

- `list_stakeholder_intelligence()`

Frontend helper:

- `getStakeholderIntelligence(token?)`

### 21. `GET /intelligence/stakeholders/{stakeholder_slug}`

File:

- `apps/api/backend/api/routes/intelligence.py`

Purpose:

- Returns intelligence details for a single stakeholder.

Auth:

- Requires `UserDep`.

Path parameters:

- `stakeholder_slug`: stakeholder identifier/name slug

Response model:

- `StakeholderIntelligence`

Backend data path:

- `get_stakeholder_intelligence(stakeholder_slug)`

Frontend coverage:

- No dedicated frontend helper currently exists.

### 22. `GET /intelligence/readiness`

File:

- `apps/api/backend/api/routes/intelligence.py`

Purpose:

- Returns a demonstration/readiness bundle for the intelligence experience.

Auth:

- Requires `UserDep`.

Response model:

- `IntelligenceReadinessReport`

Response contains:

- `active_deadlines`
- `stakeholder_obligations`
- `regulatory_impacts`
- `consultation_tracking`
- `status`
- `notes`

Backend data path:

- `intelligence_readiness_report()`

Frontend helper:

- `getIntelligenceReadiness(token?)`

## Backend Auth and Permissions

Auth file:

- `apps/api/backend/api/auth.py`

User dependency:

- `UserDep = Annotated[CurrentUser, Depends(current_user)]`

Behavior:

1. If no `Authorization` header exists and `settings.auth_required` is false:
   - returns demo user `DEMO_USER_ID`
   - role is `admin`
2. If no `Authorization` header exists and auth is required:
   - returns `401 Missing bearer token`
3. If token exists:
   - validates token through Supabase Auth using `supabase_project_url` and `supabase_anon_key`
   - loads role from `profiles`
   - defaults role to `user`
4. Admin routes call `admin_user(...)`, which requires `role == "admin"`.

Important note:

- `meta` routes do not currently depend on `UserDep`, so they are public at the FastAPI route layer.

## Backend Response Models

Main API response/request models are defined in:

- `apps/api/backend/core/models.py`

### `EventSummary`

Used by:

- `GET /events`
- `GET /events/{event_id}`
- `DigestResponse.events`
- exports

Fields:

- `id`
- `title`
- `issuing_body`
- `jurisdiction`
- `issue_date`
- `event_type`
- `topic_tags`
- `raw_summary`
- `summary`
- `source_url`
- `detected_at`
- `is_read`
- `is_bookmarked`

### `SummaryPayload`

Nested in:

- `EventSummary.summary`

Fields:

- `plain_english_summary`
- `why_it_matters`
- `affected_segments`
- `important_dates`
- `action_required`
- `confidence`
- `evidence_quotes`
- `deadline_details`
- `intelligence`
- `change_details`

### `DigestResponse`

Used by:

- `GET /digests/latest`
- `GET /digests/{digest_date}`

Fields:

- `digest_date`
- `event_count`
- `events`

### `ChatRequest`

Used by:

- `POST /chat`

Fields:

- `message`
- `event_id`

### `ChatResponse`

Used by:

- `POST /chat`

Fields:

- `reply`
- `event_id`
- `model`

### `SubscriptionSettings`

Used by:

- `GET /subscriptions`
- `PUT /subscriptions`

Fields:

- `jurisdictions`
- `source_ids`
- `topics`
- `email_enabled`
- `frequency`

### Intelligence Models

Used by:

- `/intelligence/*`

Models:

- `IntelligenceDeadline`
- `IntelligenceObligation`
- `StakeholderObligationGroup`
- `IntelligenceDocumentRef`
- `StakeholderIntelligence`
- `IntelligenceReadinessReport`

## Frontend API Client Overview

Main frontend API client:

- `apps/web/lib/api.ts`

Supabase client:

- `apps/web/lib/supabase.ts`

The frontend client uses:

```ts
const API_BASE_URL =
  env.NEXT_PUBLIC_API_BASE_URL ?? env.VITE_API_BASE_URL ?? "http://localhost:8001";
```

All typed backend calls go through:

```ts
apiFetch<T>(path, token?, init?)
```

Behavior:

- Adds `Content-Type: application/json`.
- Adds `Authorization: Bearer <token>` when a token is supplied.
- Throws an `Error` if the backend response is not OK.
- Parses JSON responses for normal API calls.
- Uses direct `fetch` for downloads because export responses are blobs/files.

## Frontend API Helper Inventory

| # | Function | Backend Endpoint | Method | Purpose |
|---:|---|---|---|---|
| 1 | `apiFetch<T>` | Any JSON endpoint | Any | Shared backend fetch wrapper |
| 2 | `getLatestDigest` | `/digests/latest` | `GET` | Load latest digest |
| 3 | `getHealth` | `/health` | `GET` | Load API/DB/LLM health |
| 4 | `getIntelligenceDeadlines` | `/intelligence/deadlines` | `GET` | Load deadline center |
| 5 | `getIntelligenceObligations` | `/intelligence/obligations` | `GET` | Load obligations center |
| 6 | `getStakeholderIntelligence` | `/intelligence/stakeholders` | `GET` | Load stakeholder intelligence list |
| 7 | `getIntelligenceReadiness` | `/intelligence/readiness` | `GET` | Load intelligence readiness bundle |
| 8 | `getEvents` | `/events` | `GET` | Search/list events |
| 9 | `getEvent` | `/events/{event_id}` | `GET` | Load event detail |
| 10 | `sendChat` | `/chat` | `POST` | Ask insight question |
| 11 | `markRead` | `/events/{event_id}/read` | `POST` | Mark read |
| 12 | `toggleBookmark` | `/events/{event_id}/bookmark` | `POST` | Toggle bookmark |
| 13 | `getSubscriptions` | `/subscriptions` | `GET` | Load notification settings |
| 14 | `saveSubscriptions` | `/subscriptions` | `PUT` | Save notification settings |
| 15 | `getSources` | `/admin/sources` | `GET` | Load admin source list |
| 16 | `toggleSource` | `/admin/sources/{source_id}/toggle` | `POST` | Toggle source |
| 17 | `getRuns` | `/admin/runs` | `GET` | Load crawl runs |
| 18 | `getDocs` | `/meta/docs` | `GET` | Load documentation index |
| 19 | `getDoc` | `/meta/docs/{slug}` | `GET` | Load one documentation page |
| 20 | `exportLatestUrl` | `/exports/latest` | URL only | Build export URL |
| 21 | `downloadLatestExport` | `/exports/latest` | `GET` | Download latest digest file |

## Frontend API Helper Details

### `getLatestDigest(token?)`

Backend:

- `GET /digests/latest`

Returns:

- `DigestResponse`

Used by:

- Base app load
- Today screen

### `getHealth()`

Backend:

- `GET /health`

Returns:

- `HealthResponse`

Used by:

- Base app load to show pipeline status.

### `getIntelligenceDeadlines(token?, filters?)`

Backend:

- `GET /intelligence/deadlines`

Supported frontend filters:

- `issuer`
- `deadline_type`
- `stakeholder`
- `status`

Returns:

- `IntelligenceDeadline[]`

Used by:

- `/intelligence`

### `getIntelligenceObligations(token?, filters?)`

Backend:

- `GET /intelligence/obligations`

Supported frontend filters:

- `stakeholder`
- `issuer`

Returns:

- `StakeholderObligationGroup[]`

Used by:

- `/intelligence`

### `getStakeholderIntelligence(token?)`

Backend:

- `GET /intelligence/stakeholders`

Returns:

- `StakeholderIntelligence[]`

Used by:

- `/intelligence`

### `getIntelligenceReadiness(token?)`

Backend:

- `GET /intelligence/readiness`

Returns:

- `IntelligenceReadiness`

Used by:

- `/intelligence`

### `getEvents(token?, filters?)`

Backend:

- `GET /events`

Supported frontend filters:

- `query` mapped to `q`
- `jurisdiction`
- `source`
- `topic`
- `bookmarked`
- `page`

Not currently exposed by frontend helper:

- backend `date_from`
- backend `date_to`

Returns:

- `DigestEvent[]`

Used by:

- `/browse`

### `getEvent(eventId, token?)`

Backend:

- `GET /events/{event_id}`

Returns:

- `DigestEvent`

Used by:

- `/events/[eventId]`

### `sendChat(message, eventId, token?)`

Backend:

- `POST /chat`

Body:

```json
{
  "message": "Question",
  "event_id": 123
}
```

Returns:

```json
{
  "reply": "Answer",
  "model": "model",
  "event_id": 123
}
```

Used by:

- Event detail insight chat
- Selected event chat panel

### `markRead(eventId, token?)`

Backend:

- `POST /events/{event_id}/read`

Returns:

```json
{
  "event_id": 123,
  "is_read": true
}
```

Used by:

- Event cards/details.

### `toggleBookmark(eventId, token?)`

Backend:

- `POST /events/{event_id}/bookmark`

Returns:

```json
{
  "event_id": 123,
  "is_bookmarked": true
}
```

Used by:

- Event cards/details.
- Saved workflow.

### `getSubscriptions(token?)`

Backend:

- `GET /subscriptions`

Returns:

- `SubscriptionSettings`

Used by:

- Base app load
- Notifications/settings screen

### `saveSubscriptions(payload, token?)`

Backend:

- `PUT /subscriptions`

Body/returns:

- `SubscriptionSettings`

Used by:

- Notifications/settings screen

### `getSources(token?)`

Backend:

- `GET /admin/sources`

Returns:

- `SourceHealth[]`

Used by:

- Admin source screen
- Admin privilege check during base load

### `toggleSource(sourceId, token?)`

Backend:

- `POST /admin/sources/{source_id}/toggle`

Returns:

```json
{
  "source_id": 1,
  "enabled": true
}
```

Used by:

- Admin source screen

### `getRuns(token?)`

Backend:

- `GET /admin/runs`

Returns:

- `CrawlRun[]`

Used by:

- Admin runs screen

### `getDocs(token?)`

Backend:

- `GET /meta/docs`

Returns:

- `SystemDocument[]`

Used by:

- Helper exists. Not prominently used by current page routing.

### `getDoc(slug, token?)`

Backend:

- `GET /meta/docs/{slug}`

Returns:

- `SystemDocument`

Used by:

- `/api-docs`
- `/flow`

### `exportLatestUrl(format)`

Backend:

- `GET /exports/latest?format=json|csv|markdown`

Purpose:

- Builds a raw download URL for the latest digest.

Used by:

- `downloadLatestExport(...)`

### `downloadLatestExport(format, token?)`

Backend:

- `GET /exports/latest?format=json|csv|markdown`

Purpose:

- Downloads latest news/export file in browser.

Behavior:

- Sends bearer token if available.
- Reads filename from `Content-Disposition`.
- Creates object URL.
- Triggers browser download.

Used by:

- Latest news export controls.

## Frontend Supabase Auth API Usage

File:

- `apps/web/lib/supabase.ts`
- `apps/web/app/resolven-app.tsx`

Supabase client setup:

```ts
export const supabase =
  supabaseProjectUrl && supabaseAnonKey ? createClient(supabaseProjectUrl, supabaseAnonKey) : null;
```

Supported env names:

- `NEXT_PUBLIC_SUPABASE_URL`
- `NEXT_PUBLIC_SUPABASE_ANON_KEY`
- `VITE_SUPABASE_URL`
- `VITE_SUPABASE_ANON_KEY`

Frontend auth calls:

| Supabase Method | Purpose |
|---|---|
| `supabase.auth.getSession()` | Load current session on app boot |
| `supabase.auth.onAuthStateChange(...)` | Keep React session state synchronized |
| `supabase.auth.signInWithPassword({ email, password })` | Password login |
| `supabase.auth.signInWithOtp({ email, options })` | Magic-link login |
| `supabase.auth.signOut()` | Sign out |

Demo behavior:

- If Supabase env/config is missing, the frontend enters demo mode.
- In demo mode API calls may work only if backend auth is not required.

## Frontend App Routes and API Usage

The active frontend pages are thin wrappers around `ResolvenApp` with different `initialRoute` values.

| Frontend Route | Page File | Primary API Calls |
|---|---|---|
| `/` | `apps/web/app/page.tsx` | `getLatestDigest`, `getSubscriptions`, `getHealth`, optional `getSources` |
| `/browse` | `apps/web/app/browse/page.tsx` | `getEvents` |
| `/intelligence` | `apps/web/app/intelligence/page.tsx` | `getIntelligenceDeadlines`, `getIntelligenceObligations`, `getStakeholderIntelligence`, `getIntelligenceReadiness` |
| `/saved` | `apps/web/app/saved/page.tsx` | Uses loaded events plus `toggleBookmark`, `markRead` |
| `/events/[eventId]` | `apps/web/app/events/[eventId]/page.tsx` | `getEvent`, `sendChat`, `markRead`, `toggleBookmark` |
| `/notifications` | `apps/web/app/notifications/page.tsx` | `getSubscriptions`, `saveSubscriptions` |
| `/account` | `apps/web/app/account/page.tsx` | Supabase session/sign-in/sign-out APIs |
| `/admin/sources` | `apps/web/app/admin/sources/page.tsx` | `getSources`, `toggleSource` |
| `/admin/runs` | `apps/web/app/admin/runs/page.tsx` | `getRuns` |
| `/api-docs` | `apps/web/app/api-docs/page.tsx` | `getDoc("backend-api")` |
| `/flow` | `apps/web/app/flow/page.tsx` | `getDoc("complete-flow")` |

## Frontend Product API Routes

The active frontend product app currently defines no active `app/api/*/route.ts` product route handlers.

The frontend is therefore not acting as a backend-for-frontend layer. It calls the FastAPI backend directly from the browser.

## Example-Only Frontend API Routes

File:

- `apps/web/examples/d1/app/api/notes/route.ts`

These routes are part of a D1 example folder, not the active Resolven product flow.

### Example `GET /api/notes`

Purpose:

- Reads up to 20 notes from a D1-backed `notes` table.

Response:

```json
{
  "notes": []
}
```

Errors:

- Returns `500` with friendly migration guidance when the notes table is unavailable.

### Example `POST /api/notes`

Purpose:

- Creates a note in the example D1 table.

Request body:

```json
{
  "title": "Note title",
  "content": "Note body"
}
```

Validation:

- `title` is required.

Response:

```json
{
  "note": {
    "id": 1,
    "title": "Note title",
    "content": "Note body"
  }
}
```

Errors:

- `400` when `title` is missing.
- `500` for database/route errors.

## Backend to Frontend Coverage Matrix

| Backend Endpoint | Frontend Helper Exists | UI Uses It | Notes |
|---|---|---|---|
| `GET /health` | Yes | Yes | Used for pipeline status |
| `GET /digests/latest` | Yes | Yes | Main dashboard data |
| `GET /digests/{digest_date}` | No | No | Backend exists but no frontend helper |
| `GET /events` | Yes | Yes | Date filters not exposed in helper |
| `GET /events/{event_id}` | Yes | Yes | Dynamic event page |
| `POST /events/{event_id}/read` | Yes | Yes | Event state |
| `POST /events/{event_id}/bookmark` | Yes | Yes | Saved/bookmark flow |
| `POST /chat` | Yes | Yes | Insight chat |
| `GET /chat/history` | No | No | Backend exists but no frontend helper |
| `GET /subscriptions` | Yes | Yes | Notifications/settings |
| `PUT /subscriptions` | Yes | Yes | Notifications/settings |
| `GET /admin/sources` | Yes | Yes | Admin source page and admin check |
| `POST /admin/sources/{source_id}/toggle` | Yes | Yes | Admin source page |
| `GET /admin/runs` | Yes | Yes | Admin runs page |
| `GET /exports/latest` | Yes | Yes | Export download |
| `GET /meta/docs` | Yes | Partial | Helper exists; route currently calls specific docs |
| `GET /meta/docs/{slug}` | Yes | Yes | API docs and flow docs |
| `GET /intelligence/deadlines` | Yes | Yes | Intelligence page |
| `GET /intelligence/obligations` | Yes | Yes | Intelligence page |
| `GET /intelligence/stakeholders` | Yes | Yes | Intelligence page |
| `GET /intelligence/stakeholders/{stakeholder_slug}` | No | No | Backend exists but no frontend helper |
| `GET /intelligence/readiness` | Yes | Yes | Intelligence page |

## Main Gaps Found

1. Backend supports `GET /digests/{digest_date}`, but the frontend has no helper or page for date-specific digest retrieval.
2. Backend supports `GET /chat/history`, but the frontend does not expose chat history yet.
3. Backend supports `GET /intelligence/stakeholders/{stakeholder_slug}`, but the frontend only loads the all-stakeholders endpoint.
4. Backend `GET /events` supports `date_from` and `date_to`, but frontend `getEvents(...)` does not expose date range filters.
5. `meta` routes are public in code because they do not use `UserDep`; this is acceptable for docs if intentional, but it is different from most product API routes.
6. The frontend has no active product `app/api` route handlers; all product API traffic goes browser-to-FastAPI.

## Recommended Documentation Labels

Use these API group names in product/admin documentation:

- **Health API**: `/health`
- **Digest API**: `/digests/*`
- **Events API**: `/events/*`
- **Insight Chat API**: `/chat`, `/chat/history`
- **Subscriptions API**: `/subscriptions`
- **Admin Source API**: `/admin/sources`, `/admin/runs`
- **Export API**: `/exports/latest`
- **Documentation API**: `/meta/docs/*`
- **Regulatory Intelligence API**: `/intelligence/*`
- **Frontend Auth API Usage**: Supabase Auth client methods

