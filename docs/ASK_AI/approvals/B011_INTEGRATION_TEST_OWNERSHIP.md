# B-011 Integration Test Ownership and Repository Asset Policy

## Executive Summary

All Ask AI integration tests, including the previously untracked `apps/api/backend/tests/integration/` tree, are approved as canonical repository assets. Ask AI Platform Engineering is the accountable owner. Regulatory Assurance owns the correctness of regulatory expectations; Security Engineering owns security-control expectations; SRE owns resilience and production-operability expectations. No test is ownerless, disposable, or local-only once it verifies an Ask AI contract.

This approval resolves blocker B-011 and permanently defines creation, review, staging, modification, deletion, and exception rules.

## Purpose

The purpose is to establish unambiguous stewardship for integration tests that cross API, database, retrieval, orchestration, provider, authorization, migration, and frontend boundaries.

## Scope

This policy covers integration tests, test fixtures, golden files, provider fakes, database harnesses, test-only migrations, contract snapshots, evaluation harness adapters, and CI configuration used to verify Ask AI. It applies to tracked and currently untracked assets within the repository.

## Background

Integration assets existed in the shared worktree without a formal ownership determination. Autonomous engineering could not safely adopt, modify, delete, or ignore them because the repository treats unknown worktree changes as user-owned.

## Problem Statement

Ownerless tests create two risks: valid safety evidence can be discarded, or unreviewed local artifacts can become release gates. Governance must define who accepts test intent, who approves regulatory/security assertions, and how assets enter or leave the canonical suite.

## Final Approved Decision

`apps/api/backend/tests/integration/` and every Ask AI integration-test asset under repository test directories SHALL be treated as canonical repository work. Ask AI Platform Engineering owns suite health, execution infrastructure, deterministic behavior, and maintenance. Domain-specific assertions require the additional reviewers defined below.

The existing files MUST be inspected, classified, and staged only as part of the engineering task whose acceptance criteria they verify. They MUST NOT be deleted, overwritten wholesale, or excluded solely because they predate this approval.

## Policy

### Ownership matrix

| Asset or assertion | Accountable owner | Mandatory additional reviewer |
|---|---|---|
| API/database/orchestrator integration tests | Ask AI Platform Engineering | Feature code owner |
| Regulatory labels, legal status, applicability, deadlines, evidence support | Regulatory Assurance | Ask AI Platform Engineering |
| Authentication, authorization, RLS, secrets, abuse, SSRF, dependency security | Security Engineering | Ask AI Platform Engineering |
| Load, recovery, timeout, circuit, migration operability, alerts | SRE | Ask AI Platform Engineering |
| Frontend/API contract integration | Ask AI Product Engineering | Ask AI Platform Engineering |
| Shared test infrastructure and CI gates | Ask AI Platform Engineering | SRE when runtime or capacity changes |

Platform Engineering is the tie-breaking accountable owner for repository placement and suite health. It cannot unilaterally change a regulatory or security expected result.

### Canonical asset criteria

An integration asset becomes canonical when it:

- verifies a frozen specification, approved policy, accepted task criterion, compatibility contract, security control, migration property, or production incident regression;
- runs through a documented repository command or is explicitly staged for a named task that adds that command;
- uses synthetic, licensed, or approved masked data;
- has deterministic setup, teardown, ownership, and expected results;
- contains no credentials, production personal data, or unlicensed content.

An asset that fails these criteria MUST be quarantined through an explicit task and issue record; it MUST NOT be silently deleted.

## Technical Requirements

- Tests MUST be hermetic or declare exact external dependencies and approved test endpoints.
- Database integration tests MUST use a dedicated non-production database and fail closed without the explicit safety opt-in.
- Provider tests MUST default to deterministic fakes; live-provider tests require a separate opt-in and MUST NOT be merge-blocking unless the provider test environment is contractually stable.
- Fixtures MUST declare schema/policy versions and deterministic clocks where time affects results.
- Test artifacts MUST use stable identifiers and clean only resources they created.
- Every CI job MUST expose the command, environment contract, timeout, and artifact retention behavior.

## Engineering Rules

- New cross-boundary behavior requires an integration test at the narrowest sufficient boundary.
- A production incident requires a failing regression test before its remediation is considered complete.
- Test code receives the same review, static analysis, secret scanning, and dependency controls as production code.
- Flaky tests MUST be fixed or placed in a time-bounded quarantine within one business day; deletion is not a flake remedy.
- Tests MUST verify user-visible safe errors rather than raw internal exceptions.
- Staging SHALL include only files intentionally reviewed for the current logical task.

## Allowed Behavior

- Refactor fixtures while preserving or strengthening asserted behavior.
- Move a test to a more appropriate canonical directory with history and CI references updated atomically.
- replace a slow test with an equivalent deterministic test after measured equivalence review.
- quarantine a nondeterministic test for no more than 7 calendar days with an owner and repair task.
- use generated synthetic regulatory examples that are unmistakably non-production.

## Forbidden Behavior

- Delete, skip, mute, weaken, broaden tolerances, or change expected results merely to make CI pass.
- Commit production credentials, tokens, personal data, confidential evidence, or unlicensed commercial text.
- Run destructive integration tests against an environment not explicitly marked as disposable.
- Make network-dependent tests silently pass when the dependency is unavailable.
- stage unrelated worktree assets together without review.
- classify canonical tests as personal or temporary after they verify a repository contract.

## Rollout Rules

Existing integration assets SHALL be onboarded incrementally with the highest-priority eligible engineering task they verify. Before enabling a new CI gate, the suite MUST pass 20 consecutive executions or demonstrate deterministic execution under randomized order and parallelism. Runtime impact MUST be measured; suites over 15 minutes SHALL be partitioned without weakening the required merge gate.

## Rollback Rules

If a new test gate destabilizes CI, the owner MAY revert the CI-gate wiring while retaining the test and opening a repair task. A test that detects a genuine safety, authorization, regulatory, migration, or data-integrity failure MUST NOT be rolled back or quarantined to release affected code. The code change SHALL be held or reverted.

## Security Requirements

Secret scanning, dependency scanning, least-privilege test credentials, network egress controls, database safety guards, and log redaction are REQUIRED. Fixtures MUST be synthetic or formally masked. Security tests that demonstrate an exploitable weakness MUST use restricted artifacts and disclosure channels while retaining a non-sensitive regression in the repository.

## Observability Requirements

CI dashboards MUST expose suite duration, pass/fail result, retry count, flake rate, quarantine count and age, test owner, last changed revision, environment, and artifact links. A test retry that passes still counts as a flaky execution. Security and regulatory gate failures MUST be separately visible.

## Testing Requirements

The policy itself is accepted through repository-path discovery, owner mapping, CI command validation, secret scanning, database safety-guard tests, fixture provenance review, and a staging review. CODEOWNERS or the repository's equivalent review enforcement SHALL map integration paths to Ask AI Platform Engineering and applicable domain reviewers.

## Acceptance Criteria

- Every Ask AI integration asset has an accountable owner.
- `apps/api/backend/tests/integration/` is recognized as canonical repository work.
- Review requirements are deterministic by assertion type.
- Staging includes only intentional current-task assets.
- Modification, quarantine, move, and deletion rules preserve coverage and history.
- CI and database safety requirements are enforceable.
- No engineering task remains blocked by uncertainty over integration-test ownership.

## Review Checklist

- [x] Canonical repository status declared.
- [x] Accountable and domain ownership declared.
- [x] Creation and review process declared.
- [x] Staging rules declared.
- [x] Modification, move, quarantine, and deletion rules declared.
- [x] Security, CI, and database safety controls declared.

## Future Revisions

Ownership changes require a semantic-version update, consent from the outgoing and incoming accountable roles, updated repository review enforcement, and no coverage gap. Individual test ownership MAY change through normal CODEOWNERS updates when the accountable Platform role remains unchanged.

## Version

`1.0.0`

## Approval Metadata

| Field | Approved value |
|---|---|
| Approval ID | `RAA-B011-2026-001` |
| Status | Approved |
| Effective date | 2026-07-29 |
| Approval authority | Resolven Ask AI Governance Authority |
| Accountable owner | Ask AI Platform Engineering |
| Domain owners | Regulatory Assurance; Security Engineering; SRE; Ask AI Product Engineering |
| Governing blocker | B-011 |
| Review frequency | Annual and on ownership-model change |
| Supersedes | No prior ownership decision |

## Change History

| Version | Date | Change | Approval |
|---|---|---|---|
| 1.0.0 | 2026-07-29 | Declared all Ask AI integration tests canonical and established complete ownership and lifecycle rules. | `RAA-B011-2026-001` |
