# Regulatory AI

Regulatory AI is a Turborepo monorepo for monitoring Indian energy-sector regulators, building daily digests, and letting users inspect each update with a grounded chat workflow.

The project currently runs in offline/demo mode because Supabase, LLM, email, and deployment secrets are not configured yet.

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

## Secrets Still Needed

Copy `.env.example` to `.env` and fill in Supabase, LLM, email, and Sentry values when available. Until then:

- API returns seeded demo digest data.
- LLM chat uses the offline adapter.
- Email notification returns an offline message id.
- Storage and database calls fail fast only when live pipeline functions need them.

## Manual Cloud Steps

1. Create Supabase project and private `regulatory-docs` bucket.
2. Run `0001_init.sql`, `0002_rls.sql`, `0003_profile_trigger.sql`, then `0004_seed_sources.sql`.
3. Add env vars in your hosting platform.
4. Verify current Render and provider pricing/docs before using `render.yaml`.
