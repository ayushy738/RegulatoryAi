# Ask AI Agent OS — Blocker Register

**Policy:** This file is the authoritative blocker register. Unresolved blockers
are recorded as detailed blocker sections. Resolved blockers remain in the
register table for auditability and link to their controlling resolution
artifact. A resolved blocker does not constrain task eligibility.

**Delivery state (2026-07-29):** Every previously unresolved governance,
regulatory, operational, security, and repository-ownership blocker has an
explicit approved artifact. One local verification-infrastructure blocker is
open: the Codex browser runtime cannot initialize, so the required manual
major-route visual review cannot be executed or truthfully approved.

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

## Unresolved blockers

## B-015 — Codex browser automation kernel unavailable

- **Description:** The required in-app browser verification cannot start because every `node_repl` JavaScript execution fails before user code runs with `failed to write kernel assets: The system cannot find the path specified. (os error 3)`. Tool discovery succeeds, `js_reset` succeeds, and the same failure recurs on a minimal runtime check. The Browser skill requires this runtime and prohibits substituting a standalone Playwright process. The application itself runs locally and serves both design-system stylesheets through the Vinext development server.
- **Severity:** P1 / High — E9.10 visual acceptance and E9.2.1 local route verification cannot be approved without browser-visible evidence.
- **Possible solutions:** Restore the Codex Desktop `node_repl` kernel-assets path or provide a functioning connected in-app Browser session, then execute the major-route desktop/tablet/mobile review and close this blocker. If the Browser skill policy is changed by its owner to authorize another visual automation mechanism, use that approved mechanism and retain screenshots as review evidence.
- **Dependencies:** E9.10 Application-wide UI/UX refinement; E9.2.1 `/ask` workspace route integration.
- **Owner:** Codex Desktop browser/runtime platform.
- **Status:** Open — reproduced after tool rediscovery and a clean kernel reset on 2026-07-29.

## Description

All eight formerly open governance blockers have controlling approval
artifacts and are retained in the resolved register above for audit history.
B-015 is an execution-infrastructure failure, not a missing governance or
product-policy decision.

## Severity

B-015 is P1 / High because it blocks required visual acceptance evidence but
does not invalidate the passing automated frontend checks.

## Possible solutions

No additional product-policy approval is required. The Codex Desktop
browser/runtime platform MUST restore a usable `node_repl` kernel or authorize
an equivalent visual verification mechanism.

## Dependencies

There are no unresolved external approval dependencies. B-015 blocks the
manual acceptance portion of E9.10 and the local browser proof required by
E9.2.1. Normal engineering task dependencies remain authoritative in
[03_TASKS.md](./03_TASKS.md).
