# B-010 Production Migration and Volume Rehearsal Approval

## Executive Summary

This artifact approves the production migration method for the Ask AI durable workspace schema: expand, backfill, validate, and contract. Production execution is authorized only inside the stated maintenance window and resource envelope, with resumable 1,000-row batches, a two-second lock budget, deterministic reconciliation, and tested rollback. The approval is count-independent: actual production volume is captured by preflight and is permitted when the operating limits pass. Exceeding a limit is an operational stop condition, not an unresolved governance decision.

This approval resolves blocker B-010 and authorizes E1.7 and the dependent schema rollout.

## Purpose

The purpose is to approve production-scale rehearsal, database execution, rollback, lock, recovery, and verification rules for Ask AI migrations and legacy backfill.

## Scope

This approval covers additive Ask AI migrations `0023` onward, the legacy session/message/artifact backfill, validation constraints and indexes, and any later contract step that removes compatibility structures. It does not authorize destructive changes outside Ask AI-owned tables or bypass migration ordering.

## Background

The repository contains additive session, message, run, evidence, event, search, retry, and regeneration migrations plus a resumable backfill and constraint-validation path. Empty and populated test upgrades pass, but production-scale timing, lock, count, hash reconciliation, maintenance, and rollback parameters required explicit approval.

## Problem Statement

A technically correct migration can still harm production through long locks, transaction bloat, replica lag, incomplete backfill, dual-write divergence, or an unsafe contract step. Engineering needs fixed execution parameters and unambiguous stop/rollback criteria.

## Final Approved Decision

The production database migration is approved under this document. The required sequence is:

1. **Expand:** add nullable columns, new tables, constraints as not valid where supported, and concurrent or low-lock indexes.
2. **Backfill:** populate new structures in resumable, idempotent batches.
3. **Validate:** reconcile counts and hashes, validate constraints, test reads, and observe dual-read/dual-write behavior.
4. **Contract:** remove obsolete compatibility structures only after the contract hold period and a separate execution change record.

Expand, backfill, and validate MAY proceed in the approved maintenance window after the preflight checklist passes. Contract MUST wait at least 30 calendar days after 100% production cutover and at least 7 consecutive days of 100% reconciliation.

## Policy

### Production envelope

| Control | Approved value |
|---|---:|
| Default backfill batch | 1,000 source rows |
| Reduced batch | 250 source rows |
| Pause between batches | 250 ms |
| Maximum batch transaction | 5 seconds |
| Session `lock_timeout` | 2 seconds |
| Backfill statement timeout | 5 minutes |
| Access-exclusive lock per DDL statement | under 2 seconds |
| Cumulative blocking attributable to a phase | under 30 seconds |
| Database CPU during migration | under 70% for 5 minutes |
| Replica lag | under 30 seconds |
| Longest blocked application transaction | under 2 seconds |
| Deadlocks caused by migration | 0 |
| Data reconciliation | 100% |

At replica lag above 15 seconds or lock wait above 500 ms, the runner SHALL reduce to 250-row batches and a 1-second pause. At replica lag above 30 seconds, CPU above 70% for 5 minutes, any deadlock, lock wait above 2 seconds, transaction above 5 seconds for three batches, or error rate above 1%, it SHALL pause automatically.

### Maintenance window

The approved recurring window is Sunday 01:00–03:00 Asia/Kolkata. A 30-minute application-change freeze begins before execution. Expand DDL with demonstrated sub-two-second lock behavior MAY run at the start of the window. Backfill MAY continue outside the window only when it uses reduced batches, stays below 25% database CPU attributable load, produces replica lag below 10 seconds, and is supervised by the migration owner.

### Expand

Expand steps MUST be backward compatible, additive, ordered, and idempotent. New application code MUST tolerate absent backfilled data until validation completes. Required indexes MUST use the lowest-lock database-supported construction method. New required constraints SHALL be introduced without full-table validation where PostgreSQL supports it, then validated after backfill.

### Backfill

Backfill MUST use a stable primary-key cursor, commit each batch, record checkpoint and counters durably, and support safe restart from the last committed cursor. It MUST use `INSERT ... ON CONFLICT` or an equivalent idempotent operation. It MUST NOT infer tenant ownership or rewrite immutable source rows. Reprocessing a completed batch MUST produce the same target state.

### Validate

Validation MUST compare:

- source and target eligible-row counts;
- per-owner and per-session counts;
- ordering and lineage;
- null, orphan, and duplicate counts;
- deterministic content hashes over canonical business fields;
- RLS and least-privilege behavior;
- query plans and required index use;
- application dual-read parity;
- full restore of representative historical and current turns.

All reconciliation values MUST be 100% or exactly explainable by documented exclusions already encoded in the migration. A manual exception is not permitted.

### Contract

Contract operations that drop, rename, rewrite, make columns non-null, or remove compatibility reads are separate deployable changes. They require confirmed 30-day hold, 7-day perfect reconciliation, no rollback dependency on the old structure, fresh backup verification, and zero active old application versions. Destructive DDL MUST NOT run in the same release as expand or cutover.

## Technical Requirements

- The migration runner MUST acquire an application-scoped advisory lock preventing two runners.
- Preflight MUST record database version, migration head, row counts, table/index sizes, free storage, replica state, longest transaction, connection saturation, and deployment versions.
- Checkpoints MUST include migration version, source range, last key, processed/succeeded/skipped/failed counts, started/completed times, and runner identity.
- Reconciliation hashes MUST use canonical UTF-8 serialization, stable field order, explicit null encoding, and SHA-256.
- Migration logs MUST use correlation IDs and exclude message text, evidence excerpts, credentials, and personal data.
- A production-like rehearsal dataset MUST be at least the larger of the current production eligible-row count or 10 million source messages, with representative ownership skew and artifact fan-out.

## Engineering Rules

- Database schema changes MUST use the repository migration runner; ad hoc production SQL is forbidden.
- Application deploy and migration ordering MUST be documented in the change record.
- Forward and rollback scripts MUST be tested against empty, populated, partially backfilled, and already-complete states.
- Production volume MUST be measured during preflight and bound to the rehearsal report.
- New writes during backfill MUST remain consistent through the approved dual-write or transactional repository path.
- Contract MUST NOT begin while any compatibility reader or rollback path depends on legacy structures.

## Allowed Behavior

- Pause and resume the backfill at committed checkpoints.
- Reduce batch size or increase pause without additional approval.
- Keep additive columns and tables in place during rollback.
- Run read-only reconciliation repeatedly.
- postpone contract indefinitely while compatibility value remains.

## Forbidden Behavior

- Drop, truncate, bulk rewrite, or make required columns blocking in expand.
- Disable RLS, foreign keys, audit recording, or backups to improve speed.
- run unbounded updates or one transaction over the full dataset.
- Continue after a stop threshold, reconciliation mismatch, or unclassified failure.
- Delete legacy data as the rollback mechanism.
- claim completion before count, hash, authorization, and restore checks pass.

## Rollout Rules

1. Rehearse on production-scale data and record timing, locks, CPU, storage, replica lag, and reconciliation.
2. Obtain SRE and Database Approver signatures on the execution record.
3. Confirm point-in-time recovery and a successful restore rehearsal within the preceding 90 days.
4. Execute expand, deploy compatible code, and observe for one peak interval.
5. Execute/resume backfill under the envelope.
6. Validate and run shadow dual-read comparisons.
7. Cut over reads in 1%, 10%, 25%, 50%, and 100% stages.
8. Start the contract hold period only after 100% validation and cutover.

## Rollback Rules

Before cutover, rollback disables new reads/writes and returns the application to legacy structures; additive schema remains. During backfill, rollback stops the runner, preserves checkpoints, and disables dual writes only after in-flight transactions finish. After read cutover but before contract, rollback returns reads to legacy structures and reconciles writes made during the cutover interval. After contract, recovery requires the separately approved contract rollback artifact or point-in-time restore.

Automatic rollback triggers are any data corruption, cross-tenant result, checksum mismatch, deadlock, uncontrolled lock beyond 2 seconds, replica lag beyond 60 seconds, database error rate above 5%, or inability to resume from checkpoint.

## Security Requirements

The runner MUST use a dedicated least-privilege database role, TLS, short-lived credentials, and approved secret storage. RLS MUST remain enabled and tested. Owner identity MUST be derived from existing authoritative keys. Migration artifacts and logs MUST be encrypted and access audited. Production snapshots MUST not be copied to lower environments without the approved masking process.

## Observability Requirements

Dashboards MUST show rows scanned/processed/succeeded/skipped/failed, batches, throughput, checkpoint age, transaction duration, lock waits, blocked sessions, deadlocks, database CPU, I/O, storage growth, WAL rate, replica lag, application latency/error rate, dual-read mismatch, and reconciliation progress. SRE paging follows the stop thresholds and B-007.

## Testing Requirements

Required tests include empty upgrade, populated upgrade, downgrade or application rollback, partial-batch restart, duplicate-run idempotency, concurrent write behavior, killed-runner recovery, RLS/least privilege, constraint validation, index/query plan, hash reconciliation, skewed ownership, storage exhaustion warning, lock contention, replica lag throttling, and full point-in-time restore rehearsal.

## Acceptance Criteria

- Production-scale rehearsal completes inside the approved envelope.
- Expand is backward compatible and contract remains separated.
- Backfill is resumable, idempotent, and bounded.
- Source/target counts, business-field hashes, ownership, ordering, and lineage reconcile at 100%.
- Lock, deadlock, CPU, storage, and replica thresholds pass.
- Rollback and checkpoint recovery complete in rehearsal.
- DB approval and production checklists are signed in the execution record.
- E1.7 and schema rollout can proceed without another migration-policy decision.

## Review Checklist

### Production checklist

- [x] Expand/backfill/validate/contract sequence approved.
- [x] Batch, pause, timeout, and lock budgets approved.
- [x] Maintenance window and freeze approved.
- [x] Backup, PITR, restore, and rollback controls approved.
- [x] Automatic pause and rollback triggers approved.

### Verification checklist

- [x] Counts and hashes require 100% reconciliation.
- [x] Ownership, RLS, order, lineage, and query plans are verified.
- [x] Empty, populated, partial, concurrent, and recovery states are tested.
- [x] Production-scale rehearsal size is fixed.
- [x] Contract hold period is fixed.

### Database approval

- [x] Database method approved by the Principal Platform Engineer role.
- [x] Operational envelope approved by the SRE role.
- [x] Data-integrity and retention controls approved by the Security and Regulatory Reviewer roles.

## Future Revisions

Changes to batch ceilings, lock budget, destructive scope, maintenance window, reconciliation method, or contract hold period require a new semantic version and fresh Platform, SRE, Security, and Regulatory approval. Lower batch sizes and longer pauses remain preapproved safety adjustments.

## Version

`1.0.0`

## Approval Metadata

| Field | Approved value |
|---|---|
| Approval ID | `RAA-B010-2026-001` |
| Status | Approved |
| Effective date | 2026-07-29 |
| Approval authority | Resolven Ask AI Governance Authority |
| Database approver | Principal Platform Engineer role |
| Operational approver | SRE role |
| Data-control approvers | Security Engineer and Regulatory Reviewer roles |
| Governing blocker | B-010 |
| Authorized work | E1.7 and dependent schema rollout |
| Review frequency | Per migration release and annually |
| Supersedes | No prior production migration approval |

## Change History

| Version | Date | Change | Approval |
|---|---|---|---|
| 1.0.0 | 2026-07-29 | Initial production expand/backfill/validate/contract and volume-rehearsal approval. | `RAA-B010-2026-001` |
