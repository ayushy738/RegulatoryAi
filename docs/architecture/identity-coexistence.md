# Supabase and First-Party Identity Coexistence

## Boundary

Supabase Auth remains the only authentication provider. No application request
reads `identity.users`, roles, or sessions to authenticate or authorize a user.
PR #2B adds one-way database synchronization and operator tooling only.

```text
Supabase Auth
    |
    v
auth.users
    |-- existing compatibility trigger --> public.profiles
    |
    |-- insert/update/delete triggers --> identity.users
                                          |-- identity.user_profiles
                                          |-- identity.user_role_assignments
                                          `-- identity.audit_events

public.profiles -- insert/update triggers --> identity profile and legacy role mirror
```

Existing foreign keys continue to reference `auth.users`. No frontend, API,
middleware, RLS, token, cookie, session-validation, or login behavior changes.

## Ownership

| Data | Authority | Coexistence behavior |
| --- | --- | --- |
| User UUID | `auth.users` | Preserve exactly in `identity.users.id` |
| Email | `auth.users` | Mirror trimmed email and lowercase lookup value |
| Verification | `auth.users.email_confirmed_at` | Mirror to `email_verified_at` |
| Account state | Supabase | Derive pending, active, disabled, or deleted |
| User timestamps | Supabase | Mirror created and updated timestamps |
| Editable name | `public.profiles.full_name` | Mirror to `display_name` |
| Legacy role | `public.profiles.role` | Maintain auditable `user`/`admin` history |
| Password hash | Identity | Never written by coexistence |
| Sessions and auth version | Identity | Never written by coexistence |
| Lockout counters | Identity | Never written by coexistence |
| Audit history | Identity | Append-only |

Email-less Supabase users are rejected by synchronization because
`identity.users` requires a durable unique email. The current product uses email
authentication; introducing phone-only or anonymous accounts requires a separate
identity-schema decision.

## Transactional synchronization

`public.handle_new_user()` remains the function used by the existing
`on_auth_user_created` trigger. Its implementation performs, in the signup
transaction:

1. Upsert the Supabase-owned identity user fields.
2. Create the identity profile.
3. Add the default `user` assignment only when no active role exists.
4. Create the compatibility `public.profiles` row.
5. Append synchronization audit events.

Any error aborts the Supabase user insertion. Exceptions are not swallowed.
Functions are `SECURITY DEFINER`, use `search_path = pg_catalog`, qualify every
application object, make no external calls, and have public execution revoked.

Additional triggers mirror relevant `auth.users` updates, tombstone deletions,
and mirror explicit profile or role changes. Per-user transaction advisory locks
serialize signup, backfill, and profile operations.

Only explicit `public.profiles.role` inserts or changes can replace an existing
legacy `user` or `admin` assignment. Name-only updates cannot downgrade an admin.
An unrelated future active role is preserved and reported as drift rather than
being silently revoked.

## Backfill

Migration `0020_identity_backfill.sql` seeds the approved RBAC definitions and
runs the idempotent `identity.backfill_from_supabase()` function in this order:

1. Roles
2. Permissions and role-permission mappings
3. Supabase users
4. Legacy profiles
5. Legacy roles
6. Audit events generated only for actual changes

All users preserve their UUIDs and source timestamps. `password_hash` remains
`NULL`. UPSERT predicates prevent unchanged rows and audit events from being
duplicated.

The operator may safely rerun backfill:

```powershell
python -m backend.tools.identity_coexistence backfill
```

Each operator execution is recorded in `identity.coexistence_runs`. A failed
transaction is rolled back and a separate failure record is committed.

## Reconciliation

`identity.coexistence_drift` reports:

- missing or orphaned users;
- UUID/email/verification/status mismatches;
- missing public or identity profiles;
- profile-name mismatches;
- missing or mismatched active roles;
- duplicate normalized emails.

Run and record a detailed JSON report:

```powershell
python -m backend.tools.identity_coexistence reconcile --fail-on-drift
```

Exit status `2` means reconciliation completed but drift exists. Other nonzero
statuses mean the reconciliation itself failed.

## Operational metrics

```powershell
python -m backend.tools.identity_coexistence metrics --format prometheus
```

Exports:

- `identity_source_users`
- `identity_users_mirrored`
- `identity_pending_users`
- `identity_drift_count`
- `identity_trigger_failures_total`
- `identity_sync_failures_total`
- `identity_backfill_progress_ratio`
- `identity_last_reconciliation_timestamp_seconds`

PostgreSQL cannot commit a failure counter from a trigger transaction that must
itself roll back. Trigger failures must therefore be alerted from Supabase or
PostgreSQL error logs. Errors intentionally include the synchronization function
context or `IDENTITY_SYNC_FAILURE`. A log processor records the durable metric:

```powershell
python -m backend.tools.identity_coexistence record-trigger-failure `
  --error-code POSTGRES_SQLSTATE `
  --message "Sanitized database log message"
```

Do not include access tokens, passwords, connection strings, or personal data in
the recorded message.

## Rollback

The emergency script is:

`apps/api/backend/migrations/rollback/0019_identity_coexistence_rollback.sql`

Run it as one transaction through an approved operator connection. It:

1. Removes auth-update, auth-delete, and profile synchronization triggers.
2. Restores the pre-coexistence `public.handle_new_user()` implementation.
3. Recreates the original `on_auth_user_created` trigger name.
4. Preserves all identity data, audit events, and migration history.

After rollback:

- Supabase authentication and compatibility profile creation continue normally.
- Identity drift is expected for users changed or created while synchronization
  is disabled.
- Do not delete migration-history rows or edit migrations `0019`/`0020`.
- Recovery requires a reviewed forward migration that reinstalls coexistence,
  followed by backfill and reconciliation.

Partial migration application is detected by the migration ledger. Partial data
backfill is detected by `identity.coexistence_drift` and repaired by rerunning the
idempotent backfill.

## Future authentication migration

PR #3 may begin only after sustained zero-drift reconciliation, tested rollback,
monitoring alerts, and explicit approval. It must separately design credential
establishment, sessions, token rotation, authorization reads, and application
cutover. Coexistence does not authorize any of those changes.
