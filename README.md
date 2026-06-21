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
