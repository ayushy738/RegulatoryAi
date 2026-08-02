# B-007 Production Service-Level Objective Approval

## Executive Summary

This artifact approves production latency, availability, error-budget, alerting, degradation, and circuit-breaker objectives for Resolven Ask AI. It binds every request to both component SLOs and the frozen execution-profile cutoffs. SLOs measure service health; the hard profile cutoff remains a per-request correctness boundary. Breaching an SLO consumes error budget and triggers controlled remediation; breaching a hard cutoff terminates or degrades the affected capability.

This approval resolves blocker B-007 and authorizes production observability, load testing, rollout gates, and general availability evaluation.

## Purpose

The purpose is to define measurable production reliability targets and deterministic operational responses for the Decision Engine, retrieval, Orchestrator, verification, and end-to-end request path.

## Scope

This approval applies to v2 Ask AI API requests, synchronous compatibility requests backed by v2, live and internal retrieval capabilities, verification, durable orchestration, and the user-visible terminal result. Offline backfills and administrative exports are excluded.

## Background

The frozen Orchestrator specifies Fast Exact, Focused Grounded, Live Grounded, Deep Regulatory Analysis, and Composite execution profiles with first-result, core-result, soft-cutoff, and hard-cutoff budgets. Production engineering additionally requires percentile objectives, availability objectives, alerts, paging, error budgets, and circuit behavior.

## Problem Statement

Without approved percentile and failure objectives, engineering cannot distinguish a local regression from acceptable tail behavior, implement enforceable dashboards, tune load gates, or decide when to degrade, pause rollout, or page an operator.

## Final Approved Decision

Resolven Ask AI SHALL use the following monthly production SLOs. Latency is measured from accepted authenticated request to the named component's terminal artifact, excluding client network time. Percentiles use successful and safely degraded requests; timeouts remain availability failures and are also represented at their cutoff latency.

### Component latency SLOs

| Component | p50 | p90 | p95 | p99 |
|---|---:|---:|---:|---:|
| Decision Engine | 100 ms | 200 ms | 350 ms | 700 ms |
| Retrieval aggregate | 1,200 ms | 3,000 ms | 4,500 ms | 8,000 ms |
| Orchestrator control overhead, excluding capability execution | 200 ms | 500 ms | 800 ms | 1,500 ms |
| Claim verification | 600 ms | 1,500 ms | 2,200 ms | 3,500 ms |
| End-to-end, all production profiles combined | 3,000 ms | 7,500 ms | 12,000 ms | 25,000 ms |

### Execution-profile latency SLOs

The frozen first/core/soft/hard boundaries are approved as p50/p90/p95/p99 limits for each selected profile:

| Profile | p50 / first useful | p90 / core | p95 / soft cutoff | p99 / hard cutoff |
|---|---:|---:|---:|---:|
| Fast Exact | 1.0 s | 3.5 s | 5.0 s | 7.0 s |
| Focused Grounded | 1.5 s | 7.0 s | 10.0 s | 14.0 s |
| Live Grounded | 1.5 s | 8.0 s | 12.0 s | 16.0 s |
| Deep Regulatory Analysis | 2.0 s | 12.0 s | 18.0 s | 25.0 s |
| Composite | 2.0 s | 15.0 s | 22.0 s | 30.0 s |

No aggregate target grants permission to exceed the selected profile's hard cutoff.

### Availability objectives

| Service indicator | Monthly SLO | Error budget in a 30-day month |
|---|---:|---:|
| Authenticated API accepts or safely rejects a valid request | 99.90% | 43.2 minutes |
| Request reaches a truthful terminal product state | 99.50% | 216 minutes |
| Internal retrieval produces a healthy terminal outcome | 99.50% | 216 minutes |
| Live retrieval produces a healthy terminal outcome when selected | 99.00% | 432 minutes |
| Persisted run/event history can be restored by its owner | 99.90% | 43.2 minutes |

`No match`, `Partial`, and policy-permitted degradation count as available when their health classification is correct and the disclosure is complete. `Unavailable`, invalid output, incorrect healthy-no-match, provenance loss, or failure to persist a required durable terminal state count as unavailable.

## Policy

### Error-budget consumption

Error budget SHALL be calculated per rolling 30-day window and calendar month. A correctness, security, authorization, or provenance incident consumes error budget regardless of response time. Planned maintenance consumes budget unless traffic is fully drained and the public endpoint remains within SLO.

Budget response:

- below 50% consumed at midpoint: normal release cadence;
- 50% consumed before midpoint or 75% consumed at any time: SRE review and no latency-risk expansion;
- 100% consumed: freeze non-remediation Ask AI releases until the trailing seven-day burn rate is below 1.0 and the incident action is verified;
- any P0 security, cross-tenant, or false-provenance event: immediate release freeze independent of remaining budget.

### Alert thresholds

| Severity | Deterministic condition | Response |
|---|---|---|
| Ticket | p95 component or profile objective breached in 2 of 3 consecutive 15-minute windows | Owner investigates within one business day |
| Warning | 2x budget burn over 1 hour, error rate above 2% for 15 minutes, or p99 above objective for 15 minutes | On-call acknowledges within 15 minutes |
| Pager | 14.4x budget burn over 5 minutes and 6x over 1 hour; terminal-state availability below 99.0% for 10 minutes; error rate above 5% for 5 minutes | Immediate page |
| P0 pager | cross-tenant access, fabricated or lost provenance, uncontrolled retry storm, durable-event corruption, or unauthorized provider access | Immediate incident declaration |

Low-volume alerts SHALL also use absolute counts: five consecutive component failures, three provenance failures, or one cross-tenant/security failure.

### Degradation policy

At the soft cutoff, the Orchestrator SHALL stop optional work and preserve the reserved verification budget. Degradation order is:

1. stop follow-up generation and nonessential enrichment;
2. stop low-priority graph expansion and summary retrieval;
3. reduce live-provider fan-out while preserving already admitted sources;
4. return verified completed sections with explicit missing/degraded sections;
5. fall back from grounded prose to evidence-only output if verification cannot complete;
6. return a safe typed unavailable outcome when no truthful section can be completed.

Decision interpretation, authorization, evidence identity, provenance admission, critical official retrieval, and required verification MUST NOT be skipped to meet latency.

### Circuit breakers

Each external provider, retrieval branch, verifier backend, and persistence dependency SHALL have an independent circuit breaker. It opens after 5 consecutive failures or at least 50% failures across the latest 20 eligible calls. The initial open interval is 60 seconds, doubling to a maximum of 10 minutes after repeated failed half-open probes. Half-open permits exactly 3 probes. All 3 MUST succeed before close.

Timeout, connection, rate-limit exhaustion without a usable retry time, malformed output, and 5xx count as failures. Healthy no-match and policy rejection do not. Authentication, entitlement, cross-tenant, or provenance-integrity failure opens the affected circuit immediately and pages.

## Technical Requirements

- Histograms MUST use consistent monotonic-clock measurements and preserve profile, stage, outcome, health, and deployment version as bounded dimensions.
- Queue time, execution time, persistence time, time to first useful artifact, time to core result, verification reserve, and total latency MUST be separately measured.
- SLO calculation MUST exclude synthetic health probes but include production canaries.
- Cancelled client requests SHALL be tracked separately; server-caused cancellation counts as unavailable.
- Metrics and traces MUST share correlation, run, and capability identities without including regulated content.
- Burn-rate recording MUST survive application restart and use the centralized telemetry backend.

## Engineering Rules

- Every new capability MUST declare a timeout below its enclosing hard cutoff.
- Retries MUST fit inside the original request budget and MUST NOT reset the hard deadline.
- Stage timing tests MUST use fake clocks where deterministic behavior is required.
- A release MUST NOT relax an SLO or reclassify failures without a new approval version.
- Tail latency MUST be tested at production-like concurrency and data volume.
- High-cardinality user, session, query, evidence, and URL values MUST NOT be metric labels.

## Allowed Behavior

- Return partial verified sections before optional branches finish.
- Use cached admitted evidence within its approved freshness window.
- Shed optional work or live-provider fan-out when capacity thresholds are reached.
- Open a single provider circuit while other independent capabilities continue.
- Pause rollout automatically when burn thresholds are crossed.

## Forbidden Behavior

- Count a timeout, malformed output, false no-match, provenance loss, or hidden degradation as success.
- Extend a hard cutoff because a retry started late.
- Drop verification reserve to improve headline latency.
- suppress errors or redefine percentile populations during an incident.
- combine healthy no-match with dependency unavailability.
- expose raw provider, database, security, or orchestration errors to users.

## Rollout Rules

Every release affecting the request path MUST pass component benchmark, integration, and profile-cutoff suites. Production rollout SHALL use 1%, 10%, 25%, 50%, and 100% stages with at least one peak traffic interval at 10% and above. Advancement requires p95 and p99 within objective, burn below 2x, no P0/P1 incident, and no unexplained result-quality regression. SRE MAY hold or reverse a stage whenever a gate fails.

## Rollback Rules

Rollback SHALL use capability flags, provider isolation, or the last known good deployment. Rollback triggers are a P0 incident, 14.4x five-minute burn, persistent p99 hard-cutoff breach for 10 minutes, error rate above 5% for 5 minutes, or irreversible durable-state divergence. In-flight runs SHALL reach a safe terminal state or be recovered by the durable-run mechanism. Evidence and audit history already presented MUST remain immutable.

## Security Requirements

Security and authorization failures are never acceptable error-budget tradeoffs. Telemetry MUST redact prompts, answer text, evidence excerpts, credentials, tokens, personal data, and licensed full text. Dashboard access MUST follow least privilege. Alert delivery MUST avoid content payloads. Security event clocks and correlation IDs MUST be tamper resistant and retained under the approved audit schedule.

## Observability Requirements

The production dashboard MUST show request rate, active runs, queue depth, first/core/total latency percentiles by profile, component latency percentiles, outcomes, health states, timeout and invalid-output rates, retry count, circuit state, cache behavior, verification reserve, persistence/event lag, saturation, availability, error-budget remaining, and 1-hour/6-hour/3-day burn. A release annotation and policy/version annotation are REQUIRED.

## Testing Requirements

Required verification includes deterministic timeout tests, profile-budget tests, concurrent load tests, production-volume data tests, provider latency/failure injection, retry-storm tests, circuit state tests, partial-result tests, persistence restart tests, cancellation tests, telemetry-label tests, alert-rule unit tests, and dashboard query tests. Load testing SHALL validate p50, p90, p95, and p99 at expected peak plus 50% headroom.

## Acceptance Criteria

- All component and profile percentiles are emitted and evaluated against the approved numbers.
- Hard cutoffs and verification reserve remain enforced under overload and retries.
- Availability classifies every typed terminal outcome correctly.
- Alerts and pages fire under deterministic synthetic breaches.
- Circuit breakers isolate failing dependencies without hiding healthy no-match.
- Error-budget gates automatically prevent unsafe rollout advancement.
- Dashboards expose all required metrics without sensitive or unbounded labels.
- Production observability and load/release tasks can proceed without another SLO decision.

## Review Checklist

- [x] Component p50, p90, p95, and p99 approved.
- [x] Profile p50, p90, p95, and p99 approved.
- [x] Availability and error budgets approved.
- [x] Alert, pager, and burn thresholds approved.
- [x] Degradation and circuit-breaker behavior approved.
- [x] Dashboard, security, test, rollout, and rollback rules approved.

## Future Revisions

An SLO revision requires 30 days of production evidence or a documented safety incident, workload characterization, capacity analysis, and approval by Product Architecture, Platform Engineering, SRE, Security when relevant, and Regulatory Review when result integrity changes. A revision MUST NOT retroactively reclassify prior measurements.

## Version

`1.0.0`

## Approval Metadata

| Field | Approved value |
|---|---|
| Approval ID | `RAA-B007-2026-001` |
| Status | Approved |
| Effective date | 2026-07-29 |
| Approval authority | Resolven Ask AI Governance Authority |
| Accountable roles | Lead Product Architect; Principal AI Engineer; Principal Platform Engineer; SRE; Security Engineer; Regulatory Reviewer |
| Governing blocker | B-007 |
| Review frequency | Monthly operational review; quarterly policy review |
| Supersedes | No prior approved SLO |

## Change History

| Version | Date | Change | Approval |
|---|---|---|---|
| 1.0.0 | 2026-07-29 | Initial production latency, availability, error-budget, alerting, degradation, and circuit-breaker approval. | `RAA-B007-2026-001` |
