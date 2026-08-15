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

The Ask AI session expansion is:

7. `0023_ask_ai_sessions.sql`

Migration `0023` creates the owner-scoped `public.chat_sessions` table and adds
nullable `public_id` and `session_id` columns to `public.chat_messages`. It does
not backfill or reinterpret existing chat rows. New message linkage is protected
by a composite session/user foreign key, and session access is restricted by RLS
to the authenticated owner.

Rollback is non-destructive: turn off all Ask AI v2 write/read/UI flags and keep
using the legacy `chat_messages` path. Leave the new table, nullable columns,
constraints, indexes, and migration-ledger entry in place. If migration execution
fails, the runner rolls back that migration transaction. Dropping `0023` objects
is not an operational rollback and requires a later approved cleanup migration
after v2 data is proven unused.

The Ask AI research-artifact expansion is:

8. `0024_ask_ai_artifacts.sql`

Migration `0024` creates durable runs, ordered/versioned sections, immutable
official/live source snapshots, claims, citations/live-source links, follow-ups,
and resumable run events. Every artifact carries session/user ownership, uses
composite foreign keys to prevent cross-owner linkage, enables RLS, and exposes
authenticated read access only. `ask_sources.source_class` permits only
`official` and `live`; General AI provenance is stored on runs, sections, and
claims and cannot receive a source or citation row.

Rollback remains non-destructive: keep all v2 flags off and continue the legacy
chat path. Leave `0024` tables, constraints, indexes, and ledger history in
place. A failed migration transaction rolls back automatically. Destructive
artifact-table removal requires a later approved cleanup migration after the
data is proven unused.

## Backfill legacy Ask history

After `0024` is applied, preview the deterministic legacy grouping:

```powershell
python -m backend.tools.ask_ai_legacy_backfill dry-run
```

Run bounded committed batches; `--max-batches` provides an operator-controlled
checkpoint and the same command safely resumes remaining nullable rows:

```powershell
python -m backend.tools.ask_ai_legacy_backfill run `
  --batch-size 1000 `
  --batch-pause-seconds 0.25 `
  --after-message-id 0 `
  --max-batches 10
```

Then require a clean reconciliation report:

```powershell
python -m backend.tools.ask_ai_legacy_backfill verify --fail-on-drift
```

Before applying migration `0025`, require the explicit preflight:

```powershell
python -m backend.tools.ask_ai_legacy_backfill preflight
python -m backend.tools.apply_migration apply --through 0025
```

The B-010 production-volume rehearsal is implemented by
`backend.tools.ask_ai_migration_rehearsal`. It prepares a fenced disposable
loopback database at `0022`, measures the real `0023`/`0024` expand, processes
at least 10,000,000 representative legacy messages under the approved
application-scoped advisory lock and batch envelope, validates with `0025`,
checks flag-off rollback compatibility, and emits count/hash/timing/operational
reports. Follow
`docs/ASK_AI/runbooks/E1_7_PRODUCTION_MIGRATION_RUNBOOK.md`; never point the
rehearsal reset command at a shared or production database.

Migration `0025_ask_ai_backfill_validation.sql` refuses pending identities,
ownership/event drift, duplicate legacy scopes, or invalid legacy marker
metadata. It validates paired message identity, makes each legacy owner/event
scope unique, and adds the owner/session message cursor index.

`0025` deliberately does not set `public_id` or `session_id` `NOT NULL`.
Flag-off legacy `/chat` writes still omit both fields, so the validated paired
identity check permits null/null while rejecting partial identity. True
non-null contraction is deferred until dual-write/read cutover and the rollback
window make it safe.

Rollback for `0025` is still flag-off: leave the validated paired-identity
constraint and additive indexes in place. They permit the unchanged legacy
null/null write shape, so no destructive schema reversal is required.

Migration `0026_ask_ai_entity_glossary.sql` adds the curated entity catalogue,
approved aliases, and glossary terms required by the Decision Engine. The
existing regulatory graph remains unchanged and can be linked by optional
`graph_entity_id`; aliases and glossary terms retain explicit provenance and
normalized jurisdiction-scoped lookup keys. Multiple entities may intentionally
share an alias so material ambiguity remains representable, while duplicate
mappings for one entity and jurisdiction are rejected.

The catalogue is authenticated-read-only. Application roles receive no write
grant, and all three tables enforce row-level security. Rollback is flag-off
plus retained additive data; no existing graph or Ask data needs reversal.

Migration `0027_ask_ai_feedback_version_lineage.sql` adds feedback and
response-version lineage without changing the legacy API. Assistant messages
point to their owning user message, regenerated assistants point to the exact
prior assistant version, and each run and section is constrained to the same
positive response version. Existing run-backed assistants are backfilled as
version 1; legacy messages without a run retain their prior content and public
meaning.

`ask_feedback` stores one owner-scoped feedback record per exact run/version.
Repeated feedback updates that durable record rather than creating duplicates,
while the original identity and creation timestamp remain stable. The table is
RLS-protected and authenticated-read-only; application-role writes are not
granted.

Rollback for `0027` is non-destructive: disable versioned Ask writes and
feedback reads, continue the legacy path, and leave the additive columns,
constraints, and feedback rows in place. A failed migration transaction rolls
back automatically. Removing lineage or feedback data requires a separately
approved cleanup migration after the data is proven unused.

Migration `0028_ask_ai_saved_items.sql` adds saved items for exact sources,
citations, response cards, catalogue entities, and documents within an owned
research session. Artifact targets retain their exact run and response version;
composite foreign keys reject cross-owner/session targets, and one expression
index makes repeated saves idempotent. Labels and compact metadata are durable
snapshots so later source or catalogue display changes do not silently rewrite
the saved workspace.

Saved items are authenticated-read-only at the database grant boundary and use
owner RLS. Backend repository writes resolve the target and ownership in the
same statement. Rollback is non-destructive: disable the v2 API, continue
legacy routes, and retain additive saved-item rows and constraints. Destructive
removal requires a later approved cleanup migration.

Migration `0029_ask_ai_run_durability.sql` extends the existing owned
`ask_runs`/`ask_run_events` journal for resumable Orchestrator execution. Each
run has an atomic execution version and next-event sequence, an expiring worker
lease, and a durable cancellation request that remains distinct from terminal
`cancelled` status. Events receive a per-run execution version in addition to
their existing stable public idempotency identity and sequence.

Populated upgrades rank existing events in sequence order, preserve their
payloads and public identities, and initialize each run's version/allocator
from the retained journal. Lease and cancellation fields are additive and null
for existing runs. Existing owner RLS and authenticated read-only grants remain
in force because no table or policy boundary changes.

Rollback is flag-off and lease release: stop durable Orchestrator workers,
continue the legacy path, and retain the additive execution journal. Do not
delete events or reset versions/sequences. Removing durability columns requires
a separately approved contraction only after no deployed worker can read or
write them.

Migration `0030_ask_ai_session_search.sql` adds expression GIN indexes over
owned session metadata, message content, and persisted source snapshots.
Supporting partial indexes cover completed knowledge modes, normalized
primary-entity filters, and active/archived cursor scans. The migration builds
indexes over existing rows without adding a denormalized search column or
rewriting user content and artifact identity.

Rollback is flag-off: stop issuing v2 session search/filter parameters and keep
the expression and supporting indexes for a later re-enable. Do not drop search
indexes while a deployed v2 API can query them. Physical removal requires a
separately approved contraction after the compatibility window.

Migration `0031_ask_ai_capability_retries.sql` adds one owner-scoped durable
retry execution per original failed capability request. A client-generated
UUID is both the mutation idempotency identity and retry request identity.
Retry plans preserve the original run version, selected node, request inputs,
failure decision, and admitted-artifact identities. Pending/running/terminal
state, an expiring worker lease, safe result or fixed error, and exact owner
foreign keys make duplicate requests and restart takeover deterministic
without mutating the original run-event journal.

Rollback is flag-off and worker stop: disable v2 retry requests, stop retry
workers, and retain retry rows and their source run history. Do not drop retry
records or reuse their client identities. Physical removal requires a
separately approved contraction after no deployed API or worker references the
table.

Migration `0032_ask_ai_response_regenerations.sql` adds immutable owner-scoped
lineage for regenerate and refresh mutations. Each client-generated request UUID
selects one historical assistant response, records the immediate prior branch
head, and points to exactly one newly allocated assistant message and durable run
version. The frozen plan distinguishes exact source-snapshot reuse from fresh
official/live retrieval and preserves the selected style variant. Existing
messages, runs, evidence, citations, feedback, and saved items are never updated.

Rollback is flag-off and worker stop: disable v2 regenerate/refresh requests,
stop consuming pending regeneration runs, and retain the lineage rows and every
response version. Do not delete or renumber versions or reuse request identities.
Physical removal requires a separately approved contraction after no deployed
API, worker, or client references this lineage.

Migration `0033_ask_ai_federated_search.sql` adds expression GIN indexes over
the existing canonical entity names/aliases, official document and family
metadata, version/amendment labels, and extracted deadline text. E2.4's
owner-scoped session/message/source indexes remain the previous-research search
path. No denormalized search row, entity-page cache, or duplicate
source-of-truth table is added.

Rollback is flag-off with the indexes retained. Physical index removal requires
a separately approved contraction after no deployed federated-search query
uses them; all canonical entity, document, version, deadline, and session data
remains unchanged.

Migration `0034_ask_ai_manual_document_search.sql` adds only B-tree access
paths for effective-status filtering, stable per-document version selection,
and within-document page ordering. Manual lexical search reuses the `0033`
document/family/version expressions and the existing `0014` chunk search
vector; it adds no search projection, generated content, or source-of-truth
column.

Rollback is flag-off with the three indexes retained. Physical removal
requires a separately approved contraction after no deployed manual-search
query uses them; document, family, version, and chunk rows remain canonical.

The tool creates one deterministic legacy session per user/event scope and one
deterministic public UUID per legacy bigint message ID. It updates only nullable
`session_id`/`public_id` fields, never message content, role, owner, event, ID, or
timestamp. Each batch is atomic; rerunning resumes incomplete rows and converges.
Conflicting non-null identity is reported or refused, never overwritten. Rollback
is flag-off plus retained additive data, not destructive un-backfill.

`backend.ask.backfill.LEGACY_BACKFILL_NAMESPACE` is a permanent persisted-identity
contract. Never change that UUID after any backfill execution; a new mapping
version requires a separately reviewed migration and reconciliation plan.

Migration `0035_ask_ai_citation_verification.sql` finalizes durable claim and
citation restoration without rewriting source content. It adds stable external
claim/evidence keys, exact verifier provider/version/model/prompt/policy and
latency identity, and provenance/confidence snapshots. Existing claim keys are
backfilled from their immutable UUIDs and citation evidence keys from the
already linked immutable source key. New structured verifier JSON is checked
against the duplicated indexed identity columns; pre-E7.6 opaque historical
verifier JSON remains readable. Rollback disables the v2 API/writer and retains
all additive columns and audit records. Destructive removal requires a later
approved contract migration after the compatibility window.

Migration `0049_ask_chat_answer_provenance.sql` makes Ask conversation
restoration exact. `chat_retrieval_audit` gains a nullable
`assistant_message_id` foreign key to `public.chat_messages`, so each retrieval
audit is bound to the one answer it explains instead of being matched by user
question text. `chat_messages` gains a checked nullable `knowledge_basis`
(`official`, `general`, `none`) so a refreshed conversation reproduces the
original answer semantics rather than inferring them from citation counts.

Both columns are additive and nullable. Historical audits keep
`assistant_message_id` null and historical answers keep `knowledge_basis` null;
the pre-`0049` schema never recorded which answer an audit belonged to, so those
rows cannot always be associated exactly after the fact. Restoration therefore
uses the question-text fallback only for answers that predate this migration,
and the fallback query excludes message-bound audit rows so a bound answer can
never inherit another answer's citations.

Rollback is non-destructive: stop writing the new columns and keep them in
place. A failed migration transaction rolls back automatically. Physical removal
requires a separately approved contraction after no deployed API reads the
message binding or persisted knowledge basis.

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

The expected result is 22 applied migrations and
`0023`/`0024`/`0025`/`0026`/`0027`/`0028` pending.
Apply `0023` and `0024`, run the backfill/preflight sequence above, then apply
`0025`, `0026`, `0027`, and `0028`; final status reports 28 applied migrations
and no pending migrations.

After applying coexistence, run:

```powershell
python -m backend.tools.identity_coexistence reconcile --fail-on-drift
python -m backend.tools.identity_coexistence metrics --format prometheus
```

Do not rerun individual SQL files manually. A checksum mismatch or history gap
must be investigated; never update the history table to suppress the error.
