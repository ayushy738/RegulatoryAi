# E1.7 Ask AI Production Migration Runbook

**Version:** 1.0.0  
**Approval basis:** `RAA-B010-2026-001`  
**Scope:** Ask AI migrations `0023`–`0025` and deterministic legacy history backfill  
**Owner roles:** Principal Platform Engineer, SRE, Security Engineer, Regulatory Reviewer  
**Maintenance window:** Sunday 01:00–03:00 Asia/Kolkata

## 1. Purpose

This runbook controls the production expand, backfill, validate, cutover, and
rollback sequence for the Ask AI durable workspace foundation. It is
deterministic and mandatory. It does not authorize the contract phase.

## 2. Hard operating envelope

| Control | Required value |
|---|---:|
| Default batch size | 1,000 source messages |
| Reduced batch size | 250 source messages |
| Default inter-batch pause | 250 ms |
| Throttled inter-batch pause | 1 second |
| Maximum batch transaction | 5 seconds |
| Session lock timeout | 2 seconds |
| Backfill statement timeout | 5 minutes |
| Maximum access-exclusive DDL lock | under 2 seconds |
| Maximum phase-attributable blocking | under 30 seconds |
| Database CPU | under 70% for every rolling 5-minute window |
| Replica lag | under 30 seconds |
| Longest blocked application transaction | under 2 seconds |
| Migration-caused deadlocks | 0 |
| Reconciliation | 100% |

The runner MUST reduce to 250-row batches and a one-second pause when replica
lag exceeds 15 seconds or lock wait exceeds 500 ms.

The runner MUST pause when any of these occurs:

- replica lag exceeds 30 seconds;
- database CPU exceeds 70% for five minutes;
- any migration-caused deadlock occurs;
- lock wait reaches 2 seconds;
- three batch transactions exceed 5 seconds;
- application database error rate exceeds 1%.

Automatic rollback begins for corruption, cross-owner results, checksum
mismatch, uncontrolled lock above 2 seconds, replica lag above 60 seconds,
database error rate above 5%, or inability to resume the committed checkpoint.

## 3. Preflight

The migration owner MUST complete every item before the application freeze:

- [ ] Confirm the recurring maintenance window and named incident commander.
- [ ] Begin the application-change freeze 30 minutes before execution.
- [ ] Verify point-in-time recovery and a successful restore rehearsal within
      the preceding 90 days.
- [ ] Record PostgreSQL version and current migration head.
- [ ] Record eligible message count, per-owner count distribution, table and
      index sizes, free storage, connection saturation, longest transaction,
      replicas, and deployed application versions.
- [ ] Confirm the rehearsal dataset is at least the larger of production
      eligible messages or 10,000,000 messages.
- [ ] Confirm no prior runner holds the migration advisory lock.
- [ ] Confirm all Ask AI v2 write/read/UI flags remain off.
- [ ] Confirm dashboards expose rows, batches, throughput, transaction
      duration, locks, deadlocks, CPU, I/O, WAL, storage, replica lag,
      application latency/errors, and reconciliation.
- [ ] Confirm the migration role is dedicated, least-privileged, TLS-bound,
      and uses a short-lived credential from approved secret storage.

Any unchecked item blocks execution.

### 3.1 Disposable production-volume rehearsal

The repository rehearsal command is restricted to a loopback database whose
name contains `rehearsal`. It refuses reset unless the exact acknowledgement
below is supplied. The operator MUST point `DATABASE_URL` at a dedicated,
disposable PostgreSQL 16/pgvector database and MUST NOT use production data.

Prepare the 10-million-message legacy source at migration head `0022`:

```powershell
python -m backend.tools.ask_ai_migration_rehearsal prepare `
  --messages 10000000 `
  --owners 1000 `
  --artifact-owners 100 `
  --acknowledge disposable-local-rehearsal-database
```

Start one-second container CPU sampling before the measured run. Retain at
least one complete five-minute window:

```powershell
docker stats --format "{{.CPUPerc}}" <rehearsal-container> `
  > <temporary-cpu-sample-log>
```

Execute the measured expand/backfill/validate/rollback probe:

```powershell
python -m backend.tools.ask_ai_migration_rehearsal run `
  --messages 10000000 `
  --owners 1000 `
  --artifact-owners 100 `
  --docker-stats-log <temporary-cpu-sample-log> `
  --replica-lag-peak-seconds <observed-peak> `
  --lock-wait-peak-ms <observed-peak> `
  --report-json <report.json> `
  --report-markdown <report.md>
```

The command MUST begin at migration head `0022`, apply exactly `0023` and
`0024` as the measured expand phase, seed representative artifact fan-out,
run the bounded backfill under its application-scoped advisory lock, apply
exactly `0025` as validation, execute the flag-off rollback probe, and emit
both reports. Exit status `2` or a Markdown result other than `PASS` blocks
production migration.

## 4. Expand

1. Record migration status:

   ```powershell
   python -m backend.tools.apply_migration status --through 0024
   ```

2. Apply additive migrations through `0024`:

   ```powershell
   python -m backend.tools.apply_migration apply --through 0024
   ```

3. Confirm each DDL statement held access-exclusive locks for less than two
   seconds and cumulative phase-attributable blocking remained below 30
   seconds.
4. Confirm legacy `/chat` and `/chat/history` reads and null/null writes remain
   valid.
5. Observe one peak traffic interval before backfill begins.

Expand rollback disables Ask AI v2 flags and retains additive schema. Dropping
tables, columns, constraints, or indexes is forbidden.

## 5. Backfill

Run a bounded checkpoint first:

```powershell
python -m backend.tools.ask_ai_legacy_backfill dry-run
python -m backend.tools.ask_ai_legacy_backfill run `
  --batch-size 1000 `
  --batch-pause-seconds 0.25 `
  --after-message-id 0 `
  --max-batches 10
python -m backend.tools.ask_ai_legacy_backfill verify
```

If the checkpoint remains inside the hard envelope, resume without
`--max-batches` and pass the prior result's `last_message_id` as
`--after-message-id`. The tool commits every batch, uses stable primary-key
ordering, sets the approved lock and statement timeouts, and converges on
deterministic session and public identities.

The operator MUST record:

- correlation ID and runner identity;
- source range and last committed message ID;
- processed, succeeded, skipped, and failed rows;
- sessions created;
- batch count, maximum and average transaction duration;
- checkpoint age and total duration;
- lock waits, deadlocks, CPU, I/O, WAL, storage growth, and replica lag.

Message text, evidence excerpts, credentials, personal data, and internal
prompts MUST NOT appear in logs or reports.

## 6. Validate

1. Require clean deterministic verification:

   ```powershell
   python -m backend.tools.ask_ai_legacy_backfill verify --fail-on-drift
   python -m backend.tools.ask_ai_legacy_backfill preflight
   ```

2. Apply `0025`:

   ```powershell
   python -m backend.tools.apply_migration apply --through 0025
   ```

3. Verify all of the following equal their expected values:

   - eligible source count equals backfilled target count;
   - per-owner and per-session counts reconcile at 100%;
   - canonical business-field SHA-256 is unchanged;
   - pending, partial-identity, orphan, duplicate-scope, ownership, ordering,
     event-scope, and lineage mismatch counts are zero;
   - required constraints are validated and indexes are valid/ready;
   - owner/non-owner RLS checks pass;
   - representative historical and current turns restore exactly;
   - a flag-off null/null legacy write still succeeds.

Any mismatch blocks cutover. Manual exceptions are forbidden.

## 7. Cutover

Cutover is outside E1.7 execution but uses the validated foundation:

1. deploy compatible dual-read/dual-write code;
2. observe 100% reconciliation;
3. advance reads through 1%, 10%, 25%, 50%, and 100% cohorts;
4. begin the contract clock only after 100% cutover and validation.

Contract operations require at least 30 calendar days after 100% cutover and
seven consecutive days of perfect reconciliation. Contract is a separate
deployable change and MUST NOT be included with expand, backfill, or cutover.

## 8. Rollback

### Before cutover

1. Stop the backfill runner after the current transaction finishes.
2. Preserve the committed checkpoint and all deterministic identities.
3. Disable Ask AI v2 reads, writes, workers, and UI.
4. Continue the legacy path.
5. Re-run read-only reconciliation and classify the trigger.

### During backfill

1. Confirm no runner process retains the advisory lock.
2. Confirm the last committed batch is complete.
3. Do not clear nullable identities or delete generated sessions.
4. Resume only from the stable pending-row selector after the incident is
   resolved.

### After read cutover and before contract

1. Return reads to legacy structures.
2. Drain in-flight v2 writes.
3. Reconcile writes made during the cutover interval.
4. Retain all additive schema and artifacts for investigation and later
   re-enable.

Destructive un-backfill, table deletion, truncation, source-row rewrite, RLS
disablement, and migration-ledger alteration are forbidden rollback methods.

## 9. Failure recovery

- A killed runner is restarted with the same approved command; pending rows
  resume from committed state.
- A failed batch rolls back atomically and does not advance the checkpoint.
- A checksum or ownership mismatch stops execution and opens a P0 incident.
- Storage warning pauses execution before free space enters the reserved
  recovery envelope.
- Restore uses the verified point-in-time recovery procedure only when
  retained additive state cannot provide a safe forward recovery.

## 10. Completion record

E1.7 is complete only when:

- the production-scale report records PASS;
- source/target counts and SHA-256 reconcile at 100%;
- every mismatch count is zero;
- batch, lock, deadlock, CPU, storage, and replica limits pass;
- checkpoint resume and flag-off rollback compatibility pass;
- the generated report contains no source content or sensitive data;
- Principal Platform Engineer, SRE, Security Engineer, and Regulatory Reviewer
  role approvals are recorded under `RAA-B010-2026-001`.

## 11. Change history

| Version | Date | Change | Approval |
|---|---|---|---|
| 1.0.0 | 2026-07-30 | Initial deterministic E1.7 production migration runbook. | `RAA-B010-2026-001` |
