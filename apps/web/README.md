# Resolven Web

React 19 and TypeScript frontend for the Resolven Regulatory Intelligence
Platform. The application uses the Next.js App Router API through vinext/Vite.

## Prerequisites

- Node.js `>=22.13.0`

## Quick start

```bash
npm install
npm run dev
npm run build
```

Configure either the `NEXT_PUBLIC_*` or `VITE_*` variants:

```dotenv
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
NEXT_PUBLIC_SUPABASE_URL=https://<project-ref>.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=<publishable-anon-key>
```

## Authentication during coexistence

The browser authenticates only with Supabase Auth during the identity
coexistence phase:

1. `/login` calls `supabase.auth.signInWithPassword()`.
2. `AuthProvider` restores the persisted session on startup and subscribes to
   `onAuthStateChange`.
3. Supabase stores and refreshes the browser session. Its local-storage key is
   managed by the SDK and has the form `sb-<project-ref>-auth-token`.
4. `ProtectedRoute` redirects unauthenticated product and admin routes to
   `/login`.
5. The shared API client reads the current Supabase session immediately before
   every backend request and adds `Authorization: Bearer <access-token>`.
6. Sign out calls `supabase.auth.signOut()`, clears application query state,
   and returns the user to `/login`.

The frontend does not call `/identity/login` and does not store or send
first-party identity JWTs. The backend can continue accepting both token types,
but Supabase remains the browser authentication source until the later cutover.

Public route:

- `/landing`

Authentication route:

- `/login`

All routes rendered through `ResolvenApp`, other than the landing page, require
an active Supabase session. Backend authorization remains authoritative;
frontend route protection is only the user-facing gate.

## Useful commands

- `npm run dev`: start local development
- `npm run build`: verify the vinext build
- `npm run typecheck`: run TypeScript validation
