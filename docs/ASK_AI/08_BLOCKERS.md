# Ask AI Agent OS — Blocker Register

**Policy:** This file is the authoritative blocker register. Unresolved blockers
are recorded as detailed blocker sections. Resolved blockers remain in the
register table for auditability and link to their controlling resolution
artifact. A resolved blocker does not constrain task eligibility.

**Delivery state (2026-08-01):** Every governance, regulatory, operational,
security, repository-ownership, and browser-runtime policy blocker has been
resolved. Four execution blockers remain: no approved authenticated visual-test
identity, and the available local Windows/Docker storage path cannot keep every
production-volume migration batch below the approved five-second maximum, and
the exact independently reviewed calibration labels/checksums are unavailable,
and the approved 14-day/500-request Live Intelligence shadow run has not occurred.

## Resolved blocker register

| Blocker | Status | Resolution | Work unblocked |
|---|---|---|---|
| B-005 Live-source policy and provider readiness | Resolved | [B005 Live Intelligence Source and Provenance Policy](./approvals/B005_LIVE_SOURCE_POLICY.md), approval `RAA-B005-2026-001`, effective 2026-07-29 | E6.3, E6.7, E11.9, live GA evaluation |
| B-007 Production percentile SLO approval | Resolved | [B007 Production SLO Approval](./approvals/B007_PRODUCTION_SLO_APPROVAL.md), approval `RAA-B007-2026-001`, effective 2026-07-29 | Production observability, load gates, GA performance signoff |
| B-009 Claim-verifier method and approval threshold | Resolved | [B009 Material Claim Verification Policy](./approvals/B009_CLAIM_VERIFIER_POLICY.md), approval `RAA-B009-2026-001`, effective 2026-07-29 | E7.3, E7.9, grounded-prose evaluation, GA |
| B-010 Production migration volume and lock profile | Resolved | [B010 Production Migration and Volume Rehearsal Approval](./approvals/B010_PRODUCTION_MIGRATION_APPROVAL.md), approval `RAA-B010-2026-001`, effective 2026-07-29 | E1.7 and production schema rollout |
| B-011 Ownership of integration-test files | Resolved | [B011 Integration Test Ownership and Repository Asset Policy](./approvals/B011_INTEGRATION_TEST_OWNERSHIP.md), approval `RAA-B011-2026-001`, effective 2026-07-29 | Canonical adoption and review of Ask AI integration tests |
| B-012 Production web dependency advisories | Resolved | [B012 Dependency Security and Release-Gate Policy](./approvals/B012_DEPENDENCY_SECURITY_APPROVAL.md), approval `RAA-B012-2026-001`, effective 2026-07-29 | Dependency remediation, E12.3, E12.6 |
| B-013 Decision-label regulatory review approval | Resolved | [B013 Decision Engine Calibration Approval](./approvals/B013_DECISION_CALIBRATION_APPROVAL.md), approval `RAA-B013-2026-001`, effective 2026-07-29 | E3.7, E12.1, E12.6 |
| B-014 Retrieval-label and threshold regulatory approval | Resolved | [B014 Retrieval Calibration and Release Approval](./approvals/B014_RETRIEVAL_CALIBRATION_APPROVAL.md), approval `RAA-B014-2026-001`, effective 2026-07-29 | E5.8, E12.1, E12.6 |
| B-015 Codex browser automation kernel unavailable | Resolved | Fresh browser initialization, localhost navigation, DOM inspection, responsive viewport control, and screenshots executed successfully on 2026-07-30. The prior failure was isolated to a stale managed kernel asset path and did not recur after runtime regeneration. | Browser-visible verification for E9.10 and E9.2.1 |

## Unresolved blockers

## B-016 — Authenticated visual-review identity unavailable

- **Description:** The in-app browser now runs and verifies public `/landing`
  and `/login` at desktop and mobile breakpoints. Navigating to `/ask`
  correctly redirects to `/login?next=%2Fask`. The repository and approved
  environment expose no seeded browser user, test email/password, persisted
  authenticated tab, supported preview route, or approved authentication
  bypass. Creating an account, fabricating a session, or weakening
  `ProtectedRoute` would change external/security state and is forbidden.
- **Severity:** P1 / High — automated frontend validation passes, but E9.10
  and E9.2.1 require manual browser evidence for authenticated Dashboard,
  Intelligence, Browse, Ask, Saved, entity, session, evidence, response, and
  related product surfaces.
- **Possible solutions:** An authorized Resolven user MUST sign in through the
  visible local `/login?next=%2Fask` page in the in-app browser, or the
  repository owner MUST provide an approved non-production visual-review
  identity through the existing Supabase authentication flow. Credentials
  MUST NOT be committed, logged, copied into Agent OS documents, or shared in
  chat.
- **Dependencies:** E9.10 Application-wide UI/UX refinement; E9.2.1 `/ask`
  workspace route integration.
- **Owner:** Resolven environment/access administrator or an authorized
  Resolven user.
- **Status:** Open — confirmed after successful browser-runtime recovery and
  protected-route navigation on 2026-07-30.

## B-017 — Production-volume rehearsal storage latency exceeds batch budget

- **Description:** The fenced PostgreSQL 16/pgvector rehearsal database was
  loaded with 10,000,000 representative legacy messages and the measured run
  applied migrations `0023` and `0024`, held the application advisory lock,
  and preserved committed restart boundaries. The first full attempt was
  stopped when an observed batch reached 5.48 seconds. Reviewer removed
  repeated per-batch rewrites of the same 1,000 session summary rows, reducing
  typical transaction time materially. On the optimized path, a 20-batch
  1,000-row sample averaged 708.34 ms but reached 8,914.43 ms, and a 100-batch
  approved reduced-size 250-row sample averaged 95.57 ms with p95 56.49 ms but
  still reached 5,957.34 ms. B-010 fixes five seconds as the maximum batch
  transaction; the available Windows-hosted Docker volume therefore cannot
  produce an approvable report without weakening or fabricating the gate.
- **Severity:** P1 / High — E1.7 and E1 epic completion remain blocked, but
  no source data was lost, the flag-off path remains intact, and independent
  P0 task chains remain eligible.
- **Possible solutions:** Execute the unchanged fenced rehearsal on approved
  Linux-hosted PostgreSQL infrastructure with production-equivalent durable
  storage and at least one complete five-minute CPU observation window; or
  provision an approved local PostgreSQL data volume whose measured fsync and
  checkpoint latency keeps every 250-row batch below five seconds. The
  five-second acceptance threshold MUST NOT be relaxed. After infrastructure
  is available, reset only the disposable database, rerun from migration head
  `0022`, and retain the generated JSON/Markdown PASS reports.
- **Dependencies:** E1.7 Production-volume migration rehearsal and E1 epic
  completion.
- **Owner:** Resolven Platform/SRE infrastructure owner.
- **Status:** Open — reproduced after three bounded attempts on 2026-07-30
  and confirmed after runtime recovery on 2026-08-01.

## B-018 — Independently reviewed calibration label artifacts unavailable

- **Description:** B-013 and B-014 approve deterministic dataset schemas,
  composition rules, thresholds, reviewer workflows, checksums, and release
  gates. They do not contain the exact 600 Decision labels or 1,200 retrieval
  gold-evidence labels signed over their final checksums. E3.7 implementation
  now validates production composition, distinct creator/reviewer identities,
  immutable payload hashes, real Decision policy modules, holdout metrics,
  zero-tolerance gates, and bounded reports. A provisional generated fixture
  was rejected and removed during review because labels derived from current
  system output are not independent regulatory labels and the approval
  reference cannot be used to fabricate checksum signoff. B-014 independently
  requires two relevance reviewers and adjudication over immutable corpus
  evidence identities, which are likewise not present in the repository.
- **Severity:** P0 / Critical — E3.7, E5.8, E7.9, their epic completion gates,
  and downstream unified/GA evaluation cannot be truthfully completed without the
  required human-labeled artifacts. Independent implementation tasks remain
  eligible.
- **Possible solutions:** Qualified Resolven reviewers MUST supply the exact
  B-013 Decision dataset and B-014 retrieval dataset through the existing
  machine contracts, including distinct real reviewer identities, immutable
  entity/corpus/evidence snapshot identities, adjudication records where
  applicable, timezone-aware signoff, and SHA-256 over the final payload. The
  labels MUST be created independently of current system predictions. After
  receipt, run the repository evaluators and retain only PASS reports bound to
  the submitted checksums.
- **Dependencies:** E3.7 Regulatory review calibration; E5.8 Retrieval
  evaluation and tuning; E7.9 Shadow verification evaluation; E12.1 unified
  evaluation; E12.6 GA gate.
- **Owner:** Resolven Regulatory Review and AI/Retrieval Evaluation teams.
- **Status:** Open — confirmed by reviewer integrity audit on 2026-08-01.

## B-019 — Live Intelligence production-shadow evidence unavailable

- **Description:** B-005 requires E6.7 to evaluate at least 14 consecutive days
  and 500 eligible production-shadow requests before rollout. Admission
  precision MUST reach 99%, provenance completeness MUST reach 100%, prohibited
  domain admission MUST remain zero, and coverage/safety/latency results MUST
  be bound to the exact provider, registry, entitlement, and policy versions.
  The repository contains deterministic E6.2/E6.3 capability contracts and
  mocks, but no production-shadow request export, elapsed observation window,
  provider telemetry, independently reviewed admissions, or signed checksum.
  Local synthetic traffic cannot truthfully satisfy elapsed production-shadow
  acceptance.
- **Severity:** P0 / High — E6.7 cannot meet its approved Definition of Done or
  authorize live rollout without external production-shadow execution evidence.
  Independent implementation tasks remain eligible.
- **Possible solutions:** Platform/SRE MUST run the disabled-by-default live and
  General AI capabilities in a non-user-visible production shadow for at least
  14 consecutive days and 500 eligible requests. The Evaluation and Regulatory
  Review owners MUST deliver an immutable, privacy-safe export with bounded
  request identities, exact policy/registry/entitlement/provider versions,
  admitted/rejected provenance outcomes, latency, independent labels,
  observation timestamps, final SHA-256, and signoff. Engineering SHALL then
  execute the E6.7 evaluator and retain the checksum-bound PASS report.
- **Dependencies:** E6.7 Shadow live/general evaluation; live rollout and the
  corresponding E12 production evaluation/GA gates.
- **Owner:** Resolven Platform/SRE, Live Intelligence Evaluation, and Regulatory
  Review teams.
- **Status:** Open — confirmed from the B-005 rollout gate and repository
  evidence audit on 2026-08-01.

## Description

All governance blockers and B-015 have been resolved. B-016 is an access
precondition for visual acceptance. B-017 is an execution-environment latency
failure against the already approved B-010 limit. B-018 is missing execution
evidence required by the approved calibration policies, not a missing policy
decision. B-019 is missing elapsed production-shadow evidence required by the
approved B-005 rollout policy, not a missing provider decision.

## Severity

B-016 and B-017 are P1 / High. B-018 is P0 / Critical because fabricated or
system-derived gold labels would invalidate regulatory and release evidence.
B-019 is P0 / High because synthetic local traffic cannot replace the approved
14-day production-shadow observation.
The blockers do not invalidate passing automated checks or independent
implementation work.

## Possible solutions

No additional product-policy approval is required. For B-016, an authorized
user MUST establish a normal Supabase session in the visible in-app browser.
For B-017, Platform/SRE MUST provide durable PostgreSQL infrastructure that
meets the existing B-010 transaction envelope. No credential bypass or
threshold relaxation is permitted. For B-018, qualified independent reviewers
MUST submit checksum-bound labels; system output MUST NOT be relabeled as gold.
For B-019, Platform/SRE MUST supply the immutable production-shadow export and
independent signoff required by B-005; elapsed time MUST NOT be simulated.

## Dependencies

There are no unresolved governance dependencies. B-016 blocks the
authenticated manual acceptance portion of E9.10 and the protected-route
browser proof required by E9.2.1. B-017 blocks E1.7 and E1 epic completion.
B-018 blocks E3.7, E5.8, E7.9, E12.1, and E12.6.
B-019 blocks E6.7 and live production rollout evidence.
Normal engineering task dependencies remain authoritative in
[03_TASKS.md](./03_TASKS.md).
