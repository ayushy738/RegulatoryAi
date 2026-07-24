# Regulatory AI

Regulatory AI is a Turborepo monorepo for monitoring Indian energy-sector regulators, building daily digests, and letting users inspect each update with a grounded chat workflow.

With Supabase env vars configured, the API reads sources, subscriptions, chat history,
and crawl-run logs from Supabase. Digest events fall back to seeded demo data until
the crawler starts writing real `events` rows. Email remains offline until a provider
key is added.

## Workspace

- `apps/web` - hosted vinext/React dashboard for Sites.
- `apps/api` - FastAPI app plus shared Python pipeline package.
- `apps/api/backend/migrations` - Supabase schema, RLS, profile trigger, and Tier-0 source seed.
- `apps/api/backend/pipeline/digest_parser.py` - existing MNRE digest parser copied in unchanged.

## Local Setup

```bash
npm install
python -m venv apps/api/.venv
apps/api/.venv/Scripts/activate
pip install -r apps/api/requirements.txt
```

PowerShell on this machine blocks `npm.ps1`, so use `npm.cmd` if needed:

```bash
npm.cmd install
npm.cmd run build
```

## Run Locally

```bash
npm run web:dev
npm run api:dev
```

API health:

```bash
cd apps/api
python -m uvicorn backend.api.main:app --reload --port 8000
```

Pipeline smoke run:

```bash
cd apps/api
python -m backend.pipeline.run_once
```

## Runtime Secrets

Copy `.env.example` to `.env` and fill in Supabase, LLM, email, and Sentry values.
When event tables are empty:

- API returns seeded demo digest data.
- LLM chat uses Parallel when `PARALLEL_API_KEY` and `LLM_MODEL_CHAT` are set.
- Email notification returns an offline message id.

The app accepts either the Supabase project URL or the Data API URL ending in
`/rest/v1`; runtime code normalizes it to the project root for Auth and Storage.

## Parallel Authentication

The API supports first-party identity authentication alongside the existing
Supabase bearer-token flow. Supabase Auth remains enabled and existing clients
do not need to change.

First-party endpoints:

- `POST /identity/login`
- `POST /identity/refresh`
- `POST /identity/logout`
- `GET /identity/me`
- `GET /identity/sessions`
- `DELETE /identity/sessions/{session_id}`
- `POST /identity/password/setup`
- `POST /identity/password/change`
- `POST /identity/session/exchange`

Access tokens are short-lived HS256 JWTs signed with the configured identity
key. They contain `kid`, issuer, audience, `sub`, `session_id`,
`auth_version`, role, `iat`, `nbf`, and `exp`. The API validates the token,
the server-side session, current account state, reconciliation status, current
role, and `auth_version` on every identity-authenticated request. The JWT role
is not used as a standalone authorization authority; admin authorization still
uses server-side role state.

Login and session exchange create a random 256-bit refresh token. Only a
peppered HMAC-SHA256 digest is stored. Refresh rotates the token and increments
the session generation; presenting the replaced token revokes the session as a
replay attempt. Password changes increment `auth_version`, rotate the current
session, and revoke other sessions.

The access and refresh cookies are `HttpOnly`; all production identity cookies
are `Secure` and use the configured `SameSite` and domain settings. Cookie-based
state-changing requests also require the signed, session-bound CSRF token in
the `X-CSRF-Token` header. Authentication responses are marked `no-store`.
Database-backed weighted sliding-window counters protect login and refresh,
while repeated password failures impose account lockouts. Authentication
outcomes, lockouts, token replay, and session revocation are written to
`identity.audit_events` with hashed request metadata.

First-party password reset is intentionally not exposed in this PR. Its future
endpoint must use the existing password rate-limit configuration before it is
enabled.

### Frontend authentication during coexistence

The web application continues to authenticate exclusively through Supabase
while the backend supports both legacy and first-party identity tokens.

- `/login` uses Supabase email/password authentication.
- The frontend auth provider restores and refreshes the Supabase browser
  session and listens for authentication changes.
- Product and admin pages redirect unauthenticated users to `/login`.
- The shared API client obtains the current Supabase access token for every
  backend request and attaches it as a bearer token.
- Logout signs out through Supabase, clears cached application data, and
  redirects to `/login`.

The frontend does not call `/identity/login` or use first-party JWTs in this
phase. See `apps/web/README.md` for route and environment-variable details.

For Parallel AI:

```bash
LLM_PROVIDER=parallel
PARALLEL_API_KEY=...
PARALLEL_BASE_URL=https://api.parallel.ai/v1
LLM_MODEL_CHAT=<your-chat-model>
LLM_MODEL_SUMMARY=<your-summary-model>
LLM_MODEL_AGENT=<your-agent-model>
```

If `PARALLEL_API_KEY` is present but `LLM_MODEL_CHAT` is empty, chat returns a
configuration message instead of sending a bad model request.

## Manual Cloud Steps

1. Create Supabase project and private `regulatory-docs` bucket.
2. Run `0001_init.sql`, `0002_rls.sql`, `0003_profile_trigger.sql`, then `0004_seed_sources.sql`.
3. Add env vars in your hosting platform.
4. Verify current Render and provider pricing/docs before using `render.yaml`.
