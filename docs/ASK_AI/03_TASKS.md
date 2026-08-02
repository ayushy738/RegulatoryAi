# Ask AI Agent OS — Tasks

**Delivery source:** [ASK_AI_IMPLEMENTATION_PLAN.md](./ASK_AI_IMPLEMENTATION_PLAN.md)  
**Snapshot:** 2026-07-30 at repository revision `87b8eec`
**Rule:** Status reflects repository evidence, not documentation completion.

## Status and priority

- `[x]` Complete — code, tests, acceptance, and documentation verified.
- `[-]` Active — current task named in [04_CURRENT_STATE.md](./04_CURRENT_STATE.md).
- `[ ]` Planned — not started or no repository evidence.
- `[!]` Blocked — blocker ID recorded in [08_BLOCKERS.md](./08_BLOCKERS.md).
- **P0** trust/security/foundation; **P1** required product capability; **P2** rollout/cleanup.

## Universal task subtasks

Every task below inherits these reviewable subtasks:

- [ ] Confirm frozen-spec clauses and dependencies.
- [ ] Characterize current behavior and add/identify a failing test.
- [ ] Implement only the task scope behind the required compatibility boundary.
- [ ] Add unit/contract tests and boundary integration tests.
- [ ] Declare `No database migration` or include additive migration, preflight, and rollback notes.
- [ ] Run affected legacy regression, security, and build/type checks.
- [ ] Update Current State, Tasks, Progress, Blockers, Decisions if needed, and Changelog if completed.

The `Definition of Done` column adds task-specific proof. Full epic acceptance remains in the implementation plan.

## Completed foundation

| Task | Status | Priority | Dependencies | Definition of Done |
|---|---|---:|---|---|
| DOC-01 Frozen audit, product, Decision Engine, Orchestrator, and implementation plan | [x] Complete | P0 | None | Five source documents exist and match the documented current/target state. |
| DOC-02 Agent OS bootstrap | [x] Complete | P0 | DOC-01 | Ten Agent OS files exist, cross-reference each other, and identify E0.1 as resume point. |
| DOC-03 Agent OS compliance framework | [x] Complete | P0 | DOC-02 | Central policy, modular validators, aggregate reporting, fixture tests, and CI enforcement pass the repository gate. |
| DOC-04 Governance approval package B-005 through B-014 | [x] Complete | P0 | DOC-03 | Eight explicit enterprise approvals resolve B-005, B-007, and B-009–B-014; the synchronized graph exposes E1.7 as the next eligible task. |
| LEGACY-01 Existing authenticated Ask flow | [x] Complete | — | Existing repository | `/ask`, `POST /chat`, `GET /chat/history`, hybrid retrieval, Parallel.ai synthesis, and citation UI exist; known defects remain open. |

Legacy completion is evidence of the current baseline, not completion of redesign epics.

## User-directed delivery override

The user explicitly required this presentation-only enhancement before the
next normal engineering task. Its temporary P0 priority records that sequencing
instruction; after completion, normal graph priority resumes without changing
any frozen product interaction or engineering dependency.

| Feature | Task | Status | Pri | Dependencies | Definition of Done |
|---|---|---|---:|---|---|
| Visual system | E9.10 Application-wide UI/UX refinement | [!] Blocked | P0 | E0.2,E9.2 | Existing routes use the approved Resolven deck palette, typography, spacing, navigation, surfaces, controls, states, and responsive primitives without business-logic change; major routes pass manual visual review. Blocked by B-016. |

# E0 — Delivery guardrails and compatibility foundation

**Epic status:** `[x] Complete` · **Priority:** P0 · **Dependencies:** none

| Feature | Task | Status | Pri | Dependencies | Definition of Done |
|---|---|---|---:|---|---|
| Characterization | E0.1 Ask contract characterization | [x] Complete | P0 | None | Current chat/history/citation/error contracts are frozen in passing pytest fixtures with no runtime change. |
| Test foundation | E0.2 Frontend test foundation | [x] Complete | P0 | E0.1 | Component runner and legacy Ask smoke tests run in CI alongside existing typecheck. |
| Rollout control | E0.3 Feature-flag boundary | [x] Complete | P0 | E0.1 | Backend/frontend Ask flags default off and flag-off behavior is equivalent. |
| Safe failures | E0.4 Safe errors and correlation identity | [x] Complete | P0 | E0.1,E0.3 | Safe product codes and one correlation ID are tested; legacy detail remains compatible. |
| Observability | E0.5 Baseline stage metrics | [x] Complete | P0 | E0.1,E0.4 | Current auth/retrieval/model/persistence timings and outcomes emit without changing answers. |

# E1 — Durable research-workspace data model

**Epic status:** `[ ] Planned` · **Priority:** P0 · **Dependencies:** E0

| Feature | Task | Status | Pri | Dependencies | Definition of Done |
|---|---|---|---:|---|---|
| Sessions | E1.1 `0023` session expansion | [x] Complete | P0 | E0.3 | Additive session/public identity fields migrate from empty and `0022`; legacy rows untouched. |
| Persistence | E1.2 Session/message repositories | [x] Complete | P0 | E1.1 | Owned session and transactional placeholder creation pass PostgreSQL tests. |
| Artifacts | E1.3 `0024` run and section artifacts | [x] Complete | P0 | E1.1 | Runs, sections, official/live sources, claims, citations, follow-ups, events, and RLS exist. |
| Versions | E1.4 Feedback and version lineage | [x] Complete | P1 | E1.2,E1.3 | Version-specific feedback and regeneration lineage restore correctly. |
| Backfill | E1.5 Legacy backfill tool | [x] Complete | P0 | E1.2,E1.3 | Dry-run/resumable backfill is idempotent and preserves order/ownership. |
| Constraints | E1.6 Constraint validation migration | [x] Complete | P0 | E1.5 | Preflight proves all rows valid before safe constraints/indexes are added. |
| Rehearsal | E1.7 Production-volume migration rehearsal | [!] Blocked | P0 | E1.6 | Timing, lock, count, and hash reconciliation report and rollback runbook are approved. Blocked by B-017. |

# E2 — Session, turn, and evidence APIs

**Epic status:** `[x] Complete` · **Priority:** P0 · **Dependencies:** E1

| Feature | Task | Status | Pri | Dependencies | Definition of Done |
|---|---|---|---:|---|---|
| Session API | E2.1 Session create/list/detail | [x] Complete | P0 | E1.2 | Owned flag-gated contracts pass authorization and compatibility tests. |
| History | E2.2 Cursor message history | [x] Complete | P0 | E2.1,E1.3 | Chronological stable pagination restores complete turns under concurrent inserts. |
| Lifecycle | E2.3 Session lifecycle actions | [x] Complete | P1 | E2.1 | Rename/pin/duplicate/export/archive/restore/soft-delete transitions are authorized and tested. |
| Search | E2.4 Session search | [x] Complete | P1 | E1.6,E2.1 | Additive index and query-plan tests prove title/content/entity/source filtering. |
| Evidence | E2.5 Evidence, saved-item, and feedback I/O | [x] Complete | P0 | E1.3,E1.4,E2.1 | Artifacts restore by exact version without cross-user leakage. |
| Compatibility | E2.6 Legacy compatibility adapter | [x] Complete | P0 | E2.2,E2.5 | Persisted v2 results map to unchanged legacy response/history golden fixtures. |

# E3 — Query understanding and Decision Engine

**Epic status:** `[ ] Planned` · **Priority:** P0 · **Dependencies:** E0

| Feature | Task | Status | Pri | Dependencies | Definition of Done |
|---|---|---|---:|---|---|
| Policy model | E3.1 Decision record and taxonomy | [x] Complete | P0 | E0.1 | Versioned types and precedence pass every frozen intent fixture. |
| Time | E3.2 Time and status understanding | [x] Complete | P0 | E3.1 | Fixed-clock/time-zone tests match all frozen time semantics. |
| Entities | E3.3 Entity/glossary resolution | [x] Complete | P0 | E3.1 | Canonical aliases, confidence, jurisdiction, and ambiguity pass named-entity fixtures. |
| Context | E3.4 Multi-part and context policy | [x] Complete | P0 | E3.2,E3.3 | Atomic decomposition and current-turn precedence pass conversation fixtures. |
| Plans | E3.5 Retrieval/response plan selection | [x] Complete | P0 | E3.4 | Golden matrix selects only eligible capabilities and response blueprints. |
| Shadow | E3.6 Shadow decision recording | [x] Complete | P1 | E1.3,E3.5 | Disagreements are recorded without user-visible routing changes. |
| Calibration | E3.7 Regulatory review calibration | [!] Blocked | P0 | E3.6 | Approved labels/thresholds become immutable regression fixtures. Blocked by B-018. |

# E4 — AI Orchestrator and capability lifecycle

**Epic status:** `[x] Complete` · **Priority:** P0 · **Dependencies:** E2,E3

| Feature | Task | Status | Pri | Dependencies | Definition of Done |
|---|---|---|---:|---|---|
| Contracts | E4.1 Capability artifact contracts | [x] Complete | P0 | E2.6,E3.5 | Typed artifacts/statuses serialize and legacy adapters remain unchanged. |
| State | E4.2 Orchestration state machine | [x] Complete | P0 | E4.1 | Every permitted/forbidden transition and terminal state is tested. |
| Execution | E4.3 Async-safe dependency scheduler | [x] Complete | P0 | E4.2 | Selected branches run with bounded nonblocking execution and pool-pressure tests. |
| Budgets | E4.4 Latency and stopping policy | [x] Complete | P0 | E4.3 | Fake-clock tests enforce soft/hard cutoffs and reserved verification. |
| Failure | E4.5 Partial failure and fallback transitions | [x] Complete | P0 | E4.4 | Full capability failure matrix isolates dependent sections. |
| Durability | E4.6 Durable run events and cancellation | [x] Complete | P0 | E1.3,E4.2 | Resume/cancel tests preserve safe artifacts and monotonic states. |
| Shadow | E4.7 Shadow orchestrator | [x] Complete | P1 | E4.5,E4.6 | Kill switch proves no user-visible effect while comparison data is captured. |
| Context | E4.8 Conversation-context selection | [x] Complete | P0 | E2.2,E4.1 | Newest relevant active-session turns are isolated and serialized chronologically. |

# E5 — Regulatory retrieval, Knowledge Graph, and Timeline evidence

**Epic status:** `[ ] Planned` · **Priority:** P0 · **Dependencies:** E3,E4

| Feature | Task | Status | Pri | Dependencies | Definition of Done |
|---|---|---|---:|---|---|
| Health | E5.1 Typed retrieval outcomes | [x] Complete | P0 | E4.1 | Every legacy branch reports health/timing/status under failure injection. |
| Routing | E5.2 Selective branch execution | [x] Complete | P0 | E3.5,E5.1 | Nonselected branches are demonstrably skipped. |
| Quality | E5.3 Thresholds and canonical deduplication | [x] Complete | P0 | E5.2 | Weak hits are excluded and duplicate methods yield one Evidence Unit. |
| Graph | E5.4 Entity-aware graph retrieval | [x] Complete | P1 | E3.3,E5.1 | Typed entity queries retain distinct facts and backing evidence. |
| Versions | E5.5 Version/current-status evidence | [x] Complete | P0 | E5.3 | Current/historical fixtures resolve supersession and status correctly. |
| Timeline | E5.6 Timeline Builder | [x] Complete | P1 | E5.4,E5.5 | Date type, certainty, conflicts, and provenance survive construction. |
| Embeddings | E5.7 Embedding compatibility health | [x] Complete | P0 | E5.1 | Provider/model/dimension mismatch is explicit, never a false no-match. |
| Evaluation | E5.8 Retrieval evaluation and tuning | [!] Blocked | P0 | E5.3-E5.7 | Reproducible per-intent quality/latency report locks approved thresholds. Blocked by B-018. |
| Configuration | E5.9 Provider-configuration enforcement | [x] Complete | P0 | E5.1,E5.7 | Declared v2 provider is used or health validation fails explicitly. |

# E6 — Knowledge modes, General AI, and Live Intelligence

**Epic status:** `[-] Active` · **Priority:** P0/P1 · **Dependencies:** E4,E5

| Feature | Task | Status | Pri | Dependencies | Definition of Done |
|---|---|---|---:|---|---|
| Modes | E6.1 Knowledge-mode domain contract | [x] Complete | P0 | E3.5,E4.1 | Mode matrix, disclosures, and ceilings pass without serving change. |
| General AI | E6.2 General AI fallback | [x] Complete | P0 | E5.1,E6.1 | Healthy no-match and outage produce distinct tested outcomes; no citations. |
| Live | E6.3 Live-source capability | [x] Complete | P1 | E6.1 | Approved source policy, time filters, attribution, and failure mocks pass. |
| Reconciliation | E6.4 Internal/live event reconciliation | [x] Complete | P1 | E5.6,E6.3 | Duplicate events consolidate visually while retaining both origins. |
| UI modes | E6.5 Mode UI primitives | [x] Complete | P1 | E0.2,E6.1 | Banners/cards/disclosures/empty states pass a11y and visual fixtures. |
| Degradation | E6.6 Capability-specific degradation | [x] Complete | P0 | E6.2,E6.3 | Retry/manual-search actions and safe copy match each terminal state. |
| Evaluation | E6.7 Shadow live/general evaluation | [!] Blocked | P0 | E6.2,E6.3 | Coverage, safety, provenance, and latency meet approved review set. Blocked by B-019. |

# E7 — Citation verification, confidence, and provenance

**Epic status:** `[-] Active` · **Priority:** P0 · **Dependencies:** E5

| Feature | Task | Status | Pri | Dependencies | Definition of Done |
|---|---|---|---:|---|---|
| Admission | E7.1 Evidence identity and admission | [x] Complete | P0 | E5.3,E5.5 | Source/chunk/scope/status integrity and stale-source cases pass. |
| Claims | E7.2 Candidate claim contract | [x] Complete | P0 | E7.1 | Material claims reference admitted evidence in strict fixtures. |
| Verification | E7.3 Claim-support verifier | [x] Complete | P0 | E7.2 | Supported/partial/negative/conflict calibration meets approved threshold. |
| Confidence | E7.4 Confidence calculation | [x] Complete | P0 | E3.1,E7.2 | Exact weights, penalties, gates, ceilings, and aggregation pass boundaries. |
| Provenance | E7.5 Provenance lineage | [x] Complete | P0 | E5.6,E7.1 | Property tests prevent source-authority upgrade or lane contamination. |
| Persistence | E7.6 Citation persistence and API | [x] Complete | P0 | E1.3,E2.5,E7.3 | Exact claim/source snapshots and verifier versions restore. |
| Citation UI | E7.7 Inline citation and evidence UI | [x] Complete | P1 | E7.6,E0.2 | Claim links, drawer, failure states, and keyboard access pass. |
| Confidence UI | E7.8 Confidence/coverage UI | [x] Complete | P1 | E7.4,E7.5 | Mixed-mode section reasons and gaps render correctly. |
| Evaluation | E7.9 Shadow verification evaluation | [!] Blocked | P0 | E7.3 | Regulatory labels establish approved precision/recall and latency. Blocked by B-018. |

# E8 — Response composition, cards, and follow-ups

**Epic status:** `[x] Complete` · **Priority:** P1 · **Dependencies:** E6,E7

| Feature | Task | Status | Pri | Dependencies | Definition of Done |
|---|---|---|---:|---|---|
| Contracts | E8.1 Section and card contracts | [x] Complete | P0 | E6.1,E7.2 | Versioned backend/frontend fixtures and compatibility summary agree. |
| Core cards | E8.2 Summary/Definition/Source/Confidence | [x] Complete | P1 | E8.1 | Strict schema, component, provenance, and a11y tests pass. |
| Compliance | E8.3 Obligation/Deadline/Stakeholder cards | [x] Complete | P1 | E7.6,E8.1 | `Not established`, applicability, and citation behavior pass. |
| Change | E8.4 Timeline/Amendment/Comparison/News/Related cards | [x] Complete | P1 | E5.6,E6.4,E8.1 | Responsive and provenance fixtures pass. |
| Merge | E8.5 Deterministic section merge | [x] Complete | P0 | E8.2-E8.4 | Order/dedup/conflict/multi-part golden tests pass. |
| Follow-ups | E8.6 Follow-up Generator | [x] Complete | P1 | E8.5 | Suggestions are contextual, distinct, safe, and nonblocking. |
| Compatibility | E8.7 Compatibility rendering | [x] Complete | P0 | E8.5 | Legacy reply and flat citations match compatibility fixtures. |

# E9 — Frontend Research Workspace and exact continuity

**Epic status:** `[-] Active` · **Priority:** P1 · **Dependencies:** E2,E8

| Feature | Task | Status | Pri | Dependencies | Definition of Done |
|---|---|---|---:|---|---|
| Data | E9.1 Feature-scoped data layer | [x] Complete | P0 | E2.2,E2.5 | Stable session/message/run hooks pass cache and contract tests. |
| Shell | E9.2 Research shell | [x] Complete | P1 | E9.1 | Flagged three-pane shell and immediate composer pass responsive tests. |
| Integration | E9.2.1 `/ask` workspace route integration | [!] Blocked | P0 | E9.2,E9.8 | `/ask` mounts the implemented Research Workspace without a legacy Ask render or legacy boot traffic, and local browser verification passes. Blocked by B-016. |
| Sessions | E9.3 Session rail | [x] Complete | P1 | E2.3,E2.4,E9.2 | Real search/lifecycle actions pass component tests. |
| Canvas | E9.4 Structured canvas | [-] Active | P1 | E8.2-E8.5,E9.2 | Sections/cards/modes/confidence render accessibly. |
| Evidence | E9.5 Evidence panel | [ ] Planned | P1 | E7.7,E9.4 | Stored/current evidence and source failure preserve canvas context. |
| Reconciliation | E9.6 Optimistic turn reconciliation | [x] Complete | P0 | E2.6,E9.1 | Race/remount/idempotency tests prove messages do not disappear. |
| Restore | E9.7 Exact restoration | [ ] Planned | P0 | E9.3-E9.6 | Reopen restores all persisted artifacts and view state in E2E tests. |
| Boot | E9.8 Remove Ask boot coupling | [x] Complete | P1 | E9.2 | Network assertions show v2 shell does not await unrelated queries. |
| Accessibility | E9.9 Responsive/keyboard hardening | [ ] Planned | P1 | E9.3-E9.5 | Required viewports, focus order, and keyboard journeys pass. |

# E10 — Streaming, cancellation, retry, regeneration, feedback

**Epic status:** `[-] Active` · **Priority:** P1 · **Dependencies:** E4,E8,E9

| Feature | Task | Status | Pri | Dependencies | Definition of Done |
|---|---|---|---:|---|---|
| Events | E10.1 Durable run-event contract | [x] Complete | P0 | E4.6 | Sequence/replay constraints and read model pass. |
| Recovery | E10.2 Run execution and recovery | [x] Complete | P0 | E10.1 | Restart/stale-run integration tests reach terminal states. |
| Stream | E10.3 Resumable event stream | [x] Complete | P1 | E10.1,E10.2 | Cursor/reconnect tests prevent lost or duplicate events. |
| Client merge | E10.4 Frontend stream reducer | [ ] Planned | P1 | E9.4,E10.3 | Stable section merge tolerates duplicate/out-of-order events. |
| Stop | E10.5 Cancellation/background continuation | [ ] Planned | P1 | E10.2,E10.4 | Phase-by-phase stop preserves sources and verified sections. |
| Retry | E10.6 Capability retry | [x] Complete | P1 | E4.5,E10.2 | Only selected degraded capability reruns idempotently. |
| Versions | E10.7 Regeneration and refresh | [x] Complete | P1 | E1.4,E10.2 | Prior answer remains; correct turn/source/refresh lineage is tested. |
| Feedback | E10.8 Feedback UI and save state | [ ] Planned | P1 | E2.5,E9.7 | Feedback/save state attach to exact version and survive reopen. |
| Legacy | E10.9 Legacy synchronous adapter | [x] Complete | P0 | E8.7,E10.2 | Old client can await v2 result and receive legacy shape. |

# E11 — Entity Intelligence, federated search, structured journeys

**Epic status:** `[-] Active` · **Priority:** P1 · **Dependencies:** E8,E9,E10

| Feature | Task | Status | Pri | Dependencies | Definition of Done |
|---|---|---|---:|---|---|
| Entity | E11.1 Entity lookup/disambiguation | [x] Complete | P1 | E3.3,E9.2 | `DSM` routing and ambiguous selector pass resolver/UI tests. |
| Core page | E11.2 Entity core sections | [x] Complete | P1 | E11.1,E8.2 | Overview/definition/regulations/documents/confidence support partial pages. |
| Change | E11.3 Timeline/amendment sections | [ ] Planned | P1 | E5.6,E8.4,E11.2 | Historical/version and interaction tests pass. |
| Impact | E11.4 Stakeholder/obligation sections | [ ] Planned | P1 | E8.3,E11.2 | Evidence coverage and related-regulation tests pass. |
| Search | E11.5 Federated research search | [x] Complete | P1 | E2.4,E11.1 | Grouped results, corrections, keyboard, relevance, and indexes pass. |
| Documents | E11.6 Manual document search | [x] Complete | P0 | E5.3,E11.5 | Exact/filter/within-document search remains usable during degradation. |
| Comparison | E11.7 Comparison journey | [ ] Planned | P1 | E8.4,E11.1 | Missing-side and independent-citation acceptance tests pass. |
| Compliance | E11.8 Compliance/deadline journey | [ ] Planned | P0 | E8.3,E11.4 | High-risk applicability, deadline, and `Not established` suite passes. |
| Live | E11.9 Latest/consultation journey | [ ] Planned | P1 | E6.3,E8.4 | Time/provenance and open/recent acceptance tests pass. |
| Presentation | E11.10 Presentation levels/follow-ups | [ ] Planned | P1 | E8.6,E11.2 | Same evidence survives beginner/analyst/legal/executive transformations. |

# E12 — Production evaluation, rollout, legacy retirement

**Epic status:** `[ ] Planned` · **Priority:** P0/P2 · **Dependencies:** E0-E11

| Feature | Task | Status | Pri | Dependencies | Definition of Done |
|---|---|---|---:|---|---|
| Evaluation | E12.1 Unified evaluation harness | [ ] Planned | P0 | E3-E11 | Frozen dataset scores decision/retrieval/support/confidence/provenance/latency reproducibly. |
| Operations | E12.2 Production observability | [ ] Planned | P0 | E4.6,E12.1 | Dashboards/alerts/reconciliation have automated metric tests. |
| Resilience | E12.3 Load/chaos/security suite | [ ] Planned | P0 | E12.1 | Dependency failure, restart, cancellation, RLS, and abuse gate passes. |
| Internal | E12.4 Internal cohort rollout | [ ] Planned | P0 | E12.1-E12.3 | Kill switches and dual-write reconciliation pass with staff cohort. |
| Beta | E12.5 External beta rollout | [ ] Planned | P1 | E12.4 | Cohort selection, rollback, quality, and policy compliance are approved. |
| GA | E12.6 General availability gate | [ ] Planned | P0 | E12.5 | All frozen acceptance criteria and rollback drill are signed off. |
| Deprecation | E12.7 Legacy deprecation | [ ] Planned | P2 | E12.6 | V2 defaults on; legacy compatibility smoke tests remain green. |
| Cleanup | E12.8 Post-window cleanup | [ ] Planned | P2 | E12.7 + approved window | Dead code is removed in a separate full-regression PR; no premature destructive DB cleanup. |

## Next task

E9.4 Structured canvas is the active task. E1.7 remains blocked by B-017;
E3.7, E5.8, and E7.9 remain blocked by B-018; E9.10 and E9.2.1 remain blocked
by B-016; E6.7 remains blocked by B-019. These blocked tasks do not prevent
independent graph work.

Execute E9.4 by composing the completed E8.2–E8.5 section/card/mode/confidence
primitives into the flagged Research Workspace canvas with deterministic
unknown/degraded/partial rendering and no change to legacy flag-off behavior. See
[04_CURRENT_STATE.md](./04_CURRENT_STATE.md),
[08_BLOCKERS.md](./08_BLOCKERS.md), and
[07_TEST_PLAN.md](./07_TEST_PLAN.md).
