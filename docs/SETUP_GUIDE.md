# Resolven Regulatory AI Setup Guide

This guide takes you from a fresh clone to running the app locally.

## 1. Install Required Software


## 2. Clone the Project

```powershell
git clone https://github.com/ayushy738/RegulatoryAi
```


## 3. Install Dependencies

```powershell
npm install
```

This installs the frontend and backend workspace dependencies.

## 4. Create the Environment File

Create .env file

Fill these values:

```env
SUPABASE_URL=your_supabase_project_url
SUPABASE_ANON_KEY=your_supabase_anon_or_publishable_key
SUPABASE_SERVICE_ROLE_KEY=your_supabase_service_role_key
DATABASE_URL=your_supabase_database_connection_string

NEXT_PUBLIC_SUPABASE_URL=your_supabase_project_url
NEXT_PUBLIC_SUPABASE_ANON_KEY=your_supabase_anon_or_publishable_key
NEXT_PUBLIC_API_BASE_URL=http://localhost:8001

VITE_SUPABASE_URL=your_supabase_project_url
VITE_SUPABASE_ANON_KEY=your_supabase_anon_or_publishable_key
VITE_API_BASE_URL=http://localhost:8001

AUTH_REQUIRED=false

LLM_PROVIDER=parallel
PARALLEL_API_KEY=your_parallel_api_key
LLM_MODEL_CHAT=speed
LLM_MODEL_SUMMARY=base
LLM_MODEL_AGENT=base
```

For first local testing, keep:

```env
AUTH_REQUIRED=false
```

For real Supabase login later, change it to:

```env
AUTH_REQUIRED=true
```

## 5. Create Frontend Environment File

Create env file in apps/web/

Do not commit `.env` or `apps\web\.env.local`.


## 7. Start the Backend

Open PowerShell terminal 1:

```powershell
cd \RegulatoryAi\apps\api
node run_python.mjs -m uvicorn backend.api.main:app --host 127.0.0.1 --port 8001
```

Open this in your browser:

```text
http://127.0.0.1:8001/health
```

You should see something like:

```json
{
  "status": "ok",
  "database_connected": true
}
```

## 8. Start the Frontend

Open PowerShell terminal 2:

```powershell
cd \RegulatoryAi
$env:XDG_CONFIG_HOME='E:\RegulatoryAi\.wrangler-config'
npm.cmd run dev --workspace @regulatory-ai/web -- --host localhost --port 3000
```

Open the app:

```text
http://localhost:3000
```

