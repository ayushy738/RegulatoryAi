# Resolven Regulatory AI Backend API

Base URL comes from `API_BASE_URL` or `NEXT_PUBLIC_API_BASE_URL`.

Authentication uses Supabase Auth access tokens:

```http
Authorization: Bearer <supabase-access-token>
```

Local development may set `AUTH_REQUIRED=false`, which returns a demo user for app testing.

## Health

- `GET /health`
  - Returns runtime readiness, database connectivity, storage, and configured provider status.

## Digests

- `GET /digests/latest`
  - Returns the latest daily digest.
  - Response: `{ digest_date, event_count, events[] }`
- `GET /digests/{YYYY-MM-DD}`
  - Returns a digest for one date.

## Events

- `GET /events`
  - Query params: `q`, `jurisdiction`, `source`, `topic`, `date_from`, `date_to`, `bookmarked`, `page`.
  - Returns archive events with per-user read/bookmark state.
- `GET /events/{id}`
  - Returns one event detail.
- `POST /events/{id}/read`
  - Marks an event as read for the current user.
- `POST /events/{id}/bookmark`
  - Toggles bookmark state for the current user.

## Chat

- `POST /chat`
  - Body: `{ "event_id": number | null, "message": string }`
  - Returns grounded answer, event id, and model id.
- `GET /chat/history?event_id={id}`
  - Returns saved chat messages for the current user.

## Subscriptions

- `GET /subscriptions`
  - Returns current jurisdictions, sources, topics, email toggle, and frequency.
- `PUT /subscriptions`
  - Replaces subscription settings.

## Exports

- `GET /exports/latest?format=json|csv|markdown`
  - Downloads the latest digest/news in the requested format.
  - Writes an `exports_log` row when a real Supabase user is present.

## Admin

Admin endpoints require an admin role in `user_profiles.role`.

- `GET /admin/sources`
  - Returns source configuration and health.
- `POST /admin/sources/{id}/toggle`
  - Enables or disables one source.
- `GET /admin/runs`
  - Returns pipeline run history.

## Documentation

- `GET /meta/docs`
  - Lists database-backed documents in `app_documents`.
- `GET /meta/docs/{slug}`
  - Returns one document by slug.
