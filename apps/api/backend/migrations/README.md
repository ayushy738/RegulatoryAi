# Database migration runner

All PostgreSQL migrations are ordered by the numeric prefix in their filename
and recorded in `public.schema_migrations`.

The runner:

- takes a PostgreSQL advisory lock so only one deployment can migrate at a time;
- validates the ledger's required columns and constraints after bootstrap;
- verifies filenames and SHA-256 checksums for every applied migration;
- refuses missing, renamed, modified, duplicated, or out-of-order history;
- executes each migration and its history insert in one transaction;
- reads each SQL file as a complete script, preserving PL/pgSQL function bodies;
- records a migration only when the migration transaction commits.

Run commands from `apps/api` with `DATABASE_URL` configured.

## Existing production database: one-time adoption

Migrations `0001` through `0016` predate the migration ledger and were applied
manually. Before baselining, independently verify that the live schema contains
their expected objects. Baselining does not execute SQL and cannot prove that the
database matches those files.

```powershell
python -m backend.tools.apply_migration status
python -m backend.tools.apply_migration baseline `
  --through 0016 `
  --acknowledge existing-schema-verified
python -m backend.tools.apply_migration status
```

The baseline command:

- works only when migration history is empty;
- cannot record anything after `0016`;
- records the current checksums of `0001` through `0016`;
- requires the explicit safety acknowledgement.

Back up the database and retain the baseline verification report before running
the command in production.

## Apply pending migrations

After the one-time legacy baseline:

```powershell
python -m backend.tools.apply_migration apply
```

To stop at an explicitly reviewed version:

```powershell
python -m backend.tools.apply_migration apply --through 0018
```

The identity foundation migrations are:

1. `0017_identity_schema.sql`
2. `0018_identity_seed.sql`

The Supabase coexistence migrations are:

3. `0019_identity_coexistence.sql`
4. `0020_identity_backfill.sql`

The parallel first-party authentication migration is:

5. `0021_identity_authentication.sql`

Migration `0021` adds refresh-token rotation fields to the dormant identity
session table and creates shared authentication rate-limit state. It does not
modify Supabase, existing application foreign keys, RLS, or coexistence triggers.

The dual-authentication migration is:

6. `0022_dual_authentication.sql`

Migration `0022` adds replay-safe Supabase session exchange records and
authentication metrics. It does not remove or modify Supabase Auth.

## Repair manually applied 0021/0022 history

Use this only when migrations `0021` and/or `0022` were executed manually and
their objects exist, but `public.schema_migrations` still ends at the preceding
contiguous version:

```powershell
python -m backend.tools.apply_migration mark-existing `
  --through 0022 `
  --acknowledge manually-applied-schema-verified
```

`mark-existing` never executes migration SQL. Under the migration advisory lock,
it:

1. Validates the migration-ledger schema and all already recorded checksums.
2. Requires the missing records to be a contiguous suffix.
3. Refuses migrations without an explicitly registered schema verifier.
4. Verifies the repository files against pinned SHA-256 checksums.
5. Verifies the expected columns, constraints, indexes, cascading foreign keys,
   security-invoker view, and public privilege revocations.
6. Inserts every verified missing record in one transaction.

Any failed check rolls back all ledger inserts. Do not use this command to hide
a failed or partially applied migration, do not edit a checksum, and do not
manually insert `schema_migrations` rows.

After repair:

```powershell
python -m backend.tools.apply_migration status
```

The expected result is 22 applied migrations and no pending migrations.

After applying coexistence, run:

```powershell
python -m backend.tools.identity_coexistence reconcile --fail-on-drift
python -m backend.tools.identity_coexistence metrics --format prometheus
```

Do not rerun individual SQL files manually. A checksum mismatch or history gap
must be investigated; never update the history table to suppress the error.
