# First-Party Identity Schema

## Status and boundary

PR #2A created first-party identity infrastructure. PR #2B introduced one-way
coexistence synchronization from Supabase into that schema. PR #3 activates an
isolated first-party authentication path under `/identity`; Supabase Auth remains
active and authoritative for every existing application route. Existing
application foreign keys, PR #1 authorization guards, frontend behavior, and
Supabase token validation remain unchanged.

The frontend and existing backend routes still do not use `identity` for
authentication. The new endpoints can establish first-party passwords and
sessions in parallel so a future cutover can be measured and rehearsed without
changing current user-visible behavior.

## Schema overview

All new objects are in the private `identity` schema. Access to the schema is
revoked from PostgreSQL's `public` pseudo-role. A later deployment must grant only
the minimum required privileges to the dedicated backend database role before
the runtime begins using these tables.

### `identity.users`

The future first-party security principal.

- `id` is an application-owned UUID and has no foreign key to `auth.users`.
- `email_normalized` is the unique lookup key and must equal the trimmed,
  lowercase `email`.
- `password_hash` is nullable.
- `status`, verification, lockout, password-change, login, and soft-delete fields
  hold security lifecycle state.
- `auth_version` supports future global invalidation of a user's sessions.
- `failed_login_count` and `locked_until` support a future lockout policy.

The table mirrors Supabase users using the same UUID. It remains non-authoritative
throughout coexistence.

### `identity.user_profiles`

Non-security profile data with a one-to-one relationship to `identity.users`.
The primary key is also a foreign key to `identity.users.id`; deleting a future
identity user deletes its profile. Display name, organization, avatar, preferences,
and biography are intentionally separate from credentials, roles, and account
state.

This table mirrors `public.profiles.full_name` while the legacy profile remains
authoritative.

### `identity.roles`

Role definitions identified by stable machine-readable `code` values. The seed
migration adds only `user` and `admin`, the roles required by the current
application. `is_system` distinguishes platform roles from future configurable
roles.

### `identity.permissions`

Atomic permissions in `resource.action` format. The seed migration adds only:

- `application.access`
- `admin.access`

No speculative permissions are seeded.

### `identity.role_permissions`

Many-to-many mapping from roles to permissions. Its composite primary key prevents
duplicate mappings. Deleting a role or permission deletes its mappings.

The initial mappings are:

| Role | Permissions |
| --- | --- |
| `user` | `application.access` |
| `admin` | `application.access`, `admin.access` |

### `identity.user_role_assignments`

Auditable role history for a user. `granted_by` may refer to the identity user who
made the future administrative change. Revocation is represented by
`revoked_at`, rather than deleting history.

A partial unique index permits at most one active role assignment per user. This
models the application's current single-role behavior while preserving role
history. Role-change authorization, last-admin protection, session invalidation,
and the administrative workflow are deliberately deferred.

### `identity.password_reset_tokens`

Future password-reset challenge records. Only a SHA-256-sized token digest is
stored; plaintext reset tokens must never be persisted. Expiry, consumption, and
invalidation are explicit, and active-token lookup is indexed.

### `identity.email_verification_tokens`

Future email-verification challenge records. It stores the normalized email being
verified and a SHA-256-sized token digest, never the plaintext token. It has the
same expiry, consumption, and invalidation lifecycle as password-reset records.

### `identity.auth_sessions`

The server-side first-party session registry. `sid` is the session identifier
and `auth_version` binds a session to the user's current security version.
Expiry, last-seen time, revocation, device description, and privacy-preserving
request hashes support session management and incident response. PR #3 adds the
keyed refresh-token digest and rotation generation. Raw refresh tokens are never
persisted.

### `identity.authentication_rate_limits`

Shared rate-limit state for authentication operations. The composite key is an
operation scope plus a keyed subject hash. Window, attempt, block, and update
timestamps support enforcement across horizontally scaled API instances without
storing a raw email address or IP address.

### `identity.audit_events`

Append-only authentication and authorization audit history. Events can reference
an actor, target user, and session, while preserving the event if any referenced
record is later removed. Request metadata is constrained to a JSON object.

The migration revokes `UPDATE`, `DELETE`, and `TRUNCATE` from `public`. The
repository exposes only append and read operations. Production grants must keep
the eventual runtime role append-only; operators with owner or superuser
privileges remain capable of maintenance by PostgreSQL design.

## Relationships

```text
identity.users 1 ─── 0..1 identity.user_profiles
identity.users 1 ─── 0..* identity.user_role_assignments
identity.roles 1 ─── 0..* identity.user_role_assignments
identity.roles * ─── * identity.permissions
                  via identity.role_permissions
identity.users 1 ─── 0..* identity.password_reset_tokens
identity.users 1 ─── 0..* identity.email_verification_tokens
identity.users 1 ─── 0..* identity.auth_sessions
identity.users 0..1 ─── 0..* identity.audit_events
identity.auth_sessions 0..1 ─── 0..* identity.audit_events
```

Every foreign key created by PR #2A stays inside `identity`. There are no foreign
keys to `auth.users`, `public.profiles`, or existing application tables.

## Why `auth.users` still exists

Removing or weakening the current identity authority before coexistence,
backfill, parity validation, and rollback controls exist would create downtime
and account-integrity risk. Supabase Auth therefore remains authoritative and the
only active authentication provider. Existing UUIDs and foreign-key paths remain
untouched.

The separate `identity.users.id` is application-owned so the first-party model is
not permanently coupled to Supabase's internal schema. The cross-system identity
mapping and identifier-preservation rules belong to the audited migration phase,
not this foundation PR.

## Why `password_hash` is nullable

During coexistence, imported Supabase identities may not have a portable password
verifier. It must also be possible to represent passwordless or future OAuth-only
accounts. A nullable hash prevents fake placeholder credentials and supports a
controlled password-establishment flow later.

The included `PasswordService` is an isolated Argon2id primitive. It is not called
by login, registration, reset, or any other runtime flow in PR #2A.

## Coexistence

The reviewed ownership, triggers, backfill, reconciliation, monitoring, and
rollback procedures are documented in
`docs/architecture/identity-coexistence.md`.

The parallel authentication implementation is documented in
`docs/architecture/identity-authentication.md`. Registration, password reset,
authorization cutover, foreign-key migration, frontend adoption, and removal of
Supabase Auth remain outside PR #3.
