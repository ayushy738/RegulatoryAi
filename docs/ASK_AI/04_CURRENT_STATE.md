# Ask AI Agent OS — Current State

**Snapshot date:** 2026-07-29  
**Repository revision:** `c7e28aee3c091bf52076fb91122a5098fad637f5` (`master`)  
**Working-tree note:** `apps/api/backend/tests/integration/` is approved canonical repository work under B-011; stage or modify it only in the engineering task whose acceptance criteria it verifies.

## Current feature

**Epic E0 guardrails, the locally verifiable E1 foundation, complete owned v2 session/turn/evidence/lifecycle/search APIs, deterministic Decision Engine planning and shadow comparison, isolated legacy compatibility mapping, Orchestrator lifecycle/execution policies, selective typed retrieval, the feature-scoped frontend read/reconciliation boundary, the Research shell/session rail/entity pages/federated and manual document search with isolated boot, and durable run-event execution/recovery/stream contracts are complete; all governance approvals are explicit, the current `/ask` worktree mounts the Research Workspace, and E9.10 is active pending visual acceptance.**

Current behavior:

- authenticated `/ask` page;
- global transient chat state in `WorkspaceProvider`;
- `POST /chat` and `GET /chat/history`;
- five-branch hybrid retrieval;
- one non-streaming Parallel.ai completion when citations exist;
- flat `chat_messages` persistence;
- detached citation buttons and Evidence Drawer;
- passing backend contract fixtures for chat success, citations, no-evidence fallback, model/retrieval failures, history, persistence, and authentication;
- Vitest/React Testing Library coverage for the legacy Ask empty state, prompt submission, grounded citations, insufficient evidence, composer, and loading behavior;
- nine typed backend Ask rollout settings and a strict public UI flag boundary, all defaulting/failing closed to legacy;
- Ask-scoped correlation IDs, safe model/retrieval error codes, correlated internal detail logging, frontend safe copy, and failed-draft restoration;
- correlation-linked auth/persistence/retrieval/model/request stage metrics with safe fixed fields;
- additive migration `0023` with owner-scoped `chat_sessions`, nullable message public/session identity, cursor indexes, composite ownership linkage, and session RLS;
- typed v2 session/message records, owner-filtered repositories, and atomic user/assistant placeholder persistence that is not wired into legacy routes;
- additive migration `0024` with owned runs, ordered/versioned sections, official/live snapshots, claims, citations/live links, follow-ups, sequenced run events, RLS, and enforced provenance lanes;
- deterministic dry-run/resumable legacy backfill with bounded atomic batches, stable UUIDv5 identities, metrics, streamed verification, and no message-content/order mutation;
- migration `0025` with migration-time backfill guards, validated paired identity, unique legacy scope, owner/session cursor indexing, and retained flag-off null/null compatibility.
- additive migration `0026` with a provenance-bearing canonical entity catalogue, jurisdiction-scoped approved aliases/acronyms, glossary terms, optional graph linkage, authenticated read-only RLS, and ambiguity-preserving mappings.
- additive migration `0027` with assistant reply/parent/status/version lineage, exact message/run/section version constraints, version-specific feedback, authenticated read-only RLS, and non-destructive initial-version backfill.
- typed internal feedback upsert and ordered exact-version restoration, with complete-turn reads selecting the latest response and no legacy/public API change.
- additive migration `0028` with owner-scoped saved source/citation/card/entity/document targets, exact artifact run/version constraints, durable snapshots, authenticated read-only RLS, and idempotent uniqueness.
- additive migration `0029` with monotonic execution versions and event allocation, expiring worker leases/heartbeats, durable cancellation requests, populated-event backfill, and retained owner-scoped RLS.
- off-by-default owned exact-message/evidence/source reads plus session saved-item list/create/delete and version-specific feedback mutations, with shared Pydantic/Zod contracts and no UI switch.
- isolated fail-closed persisted-v2-to-legacy response/history mapping with exact grounded/no-evidence goldens, Decision Record intent translation, official citation snapshots, version selection, and no route wiring.
- off-by-default, authenticated `POST /chat/sessions`, `GET /chat/sessions`, and `GET /chat/sessions/{session_id}` contracts with owner filtering, non-disclosing 404 behavior, versioned Pydantic/Zod schemas, and opaque stable session pagination.
- off-by-default `GET /chat/sessions/{session_id}/messages` with chronological complete-turn pagination, nested saved display artifacts, explicit singleton recovery for unpaired rows, and no raw decision/verifier payload exposure.
- isolated version-1 Decision Record domain types, complete frozen taxonomies, deterministic intent precedence over structured signals, confidence-band boundaries, canonical response mappings, and strict immutable serialization with no route integration.
- injected-clock/IANA-zone time normalization for every frozen absolute, relative, current, draft, consultation, breaking, and intent-default semantic, using visible half-open ranges and exact elapsed rolling windows.
- isolated deterministic entity resolution over immutable catalogue entries using the frozen order/confidence ladder, canonical query expansion, jurisdiction/context scoping, one-question ambiguity, and the `0.85` high-risk gate.
- isolated structured context resolution with explicit reset, field-level interaction/current-turn/conversation/default precedence, focused antecedent clarification, and deterministic atomic-question decomposition with inherited/local scope.
- isolated deterministic capability/response planning across all intents, plan classes, stage gates, conditional fallbacks, selected-document clarification, and the frozen 19-query matrix, with no execution or route import.
- isolated immutable Orchestrator phase/capability/section/run state transitions with scoped node-level dependencies, exact activation phases, safe admitted artifacts, and no scheduling or I/O.
- isolated async-safe selected-node execution with deterministic dependency waves, bounded overall/blocking concurrency, worker-thread isolation for temporary synchronous adapters, shared injected lifecycles, and safe adapter failure terminalization, with no serving or persistence integration.
- isolated versioned five-profile latency policy with injected monotonic checkpoints, exact first/core/soft/hard boundaries, protected Citation Verifier reserve, optional/supporting soft stops, executor/limiter deadlines, late-result withholding, and safe hard-cutoff section degradation.
- isolated immutable full capability failure decisions with scoped affected/unaffected sections, declared-descendant propagation, fallback-boundary traversal, exact no-match/failure distinctions, eligible General AI substitution, and bounded verifier revision policy.
- owner-scoped durable run snapshots and ordered events with row-locked sequence allocation, idempotent identities, stale-worker fencing, lease renewal/takeover/release, replay validation, and safe cancellation preservation.
- immutable active-session context selection over structured relevance keys with newest bounded choice, chronological message pairs, explicit reset/immediate-follow-up behavior, and no factual authority.
- typed vector/keyword/graph/family-version/summary branch outcomes with health, timing, match count, safe failure status, deterministic hybrid diagnostics, and unchanged legacy hit-list behavior.
- isolated approved-plan-to-branch selection with explicit Skipped/Not run outcomes, deduplicated question ownership, bounded worker-thread execution, stable aggregation, and no invocation of nonselected branches.
- isolated explicitly gated Research Workspace provider/read hooks with owner-scoped stable session/message/run keys, opaque list/turn pagination, exact access-token use, canonical message/run cache state, strict E2 parsing, and optional exact E8.1 structured-result parsing; the legacy workspace is not mounted to this boundary.
- strict client-generated optimistic message/idempotency identity plus owner/session-scoped saving, unsynced, synced, and cursor-safe resolved overlays in TanStack Query; repeated begin/result delivery, remount, safe retry, incomplete history, and crossed identity are deterministic without legacy route integration.
- versioned owner-neutral durable run-event reads with safe typed lifecycle fields, exact persisted cursor anchors, bounded snapshot-aware pages, strict contiguous replay, and no stream/route integration.
- injected durable run execution with off-loop SQL transactions, lease-expiry takeover, interrupted-capability recovery, bounded steps, strict progress validation, stale-worker fencing, and cancellation precedence without provider/route integration.
- off-by-default owner-only session rename/pin/archive/restore/context-duplicate/export/soft-delete actions with timestamp-stable idempotent transitions, repeatable-read safe exports, and shared Pydantic/Zod contracts.
- additive migration `0030` with non-denormalizing expression GIN indexes over session metadata, message content, and source/document snapshots plus completed-mode, normalized-entity, and lifecycle cursor indexes.
- flag-gated owner-scoped session search with deterministic session/message/source relevance, mode/entity/archived/pinned filters, filter-bound version-2 cursors, version-1 unfiltered cursor compatibility, and normalized frontend request/cache identity.
- post-response flag-gated shadow Decision construction/comparison with content-free agreement/disagreement telemetry, complete legacy-response isolation, and a separate owner/run-locked non-overwriting Decision Record persistence seam.
- default-registered v2 Research Workspace shell behind only the existing UI
  flag, mounted over the E9.1 provider with semantic navigation/canvas/evidence
  regions, desktop columns, tablet/mobile overlays, and an immediately editable
  composer whose submit behavior exists only when an explicit capability is
  injected; flag-off routing remains the legacy Ask view.
- owned Research session navigation with server-backed normalized search,
  entity/mode/archive/pinned filters, opaque pagination, recency grouping,
  controlled stable-ID selection, provenance/entity indicators, and real
  rename/pin/duplicate/JSON-export/archive/restore/confirmed-soft-delete
  actions; mutations revalidate owner-scoped canonical session caches and
  expose only safe errors.
- route-and-flag-scoped legacy boot suppression: flag-on v2 Ask starts no
  digest, subscription, admin-probe, or flat chat-history request and does not
  wait on digest loading, while the global health check, flag-off Ask, saved
  history, and every non-Ask base dependency remain unchanged.
- off-by-default authenticated `GET /chat/runs/{run_id}/events` SSE over the
  owner-authorized E10.1 durable event read model, with exact `Last-Event-ID`
  or query-cursor resume, bounded replay, contiguous duplicate-free delivery,
  schema-validated heartbeat/completion/safe-error controls, terminal closure,
  disconnect handling, and off-loop repeatable-read polling.
- off-by-default owner-scoped `POST /chat/runs/{run_id}/retry` enqueue plus an
  injected durable retry worker for exactly one transiently failed official,
  live, General AI, or verification node, using one client idempotency UUID,
  a maximum 30-second lease/budget, restart takeover, stale/cancellation
  fencing, exact input/artifact preservation, and no mutation of the source
  run journal.
- off-by-default authenticated canonical entity lookup over the E3.3
  owner-neutral catalogue, with strict resolved/ambiguous/no-match contracts,
  deterministic aliases, fixed safe failures, and no new corpus facts.
- flagged Research Workspace canonical entity routing/restoration, expanded
  entity header, and keyboard-operable ambiguity selection that re-resolves
  the selected canonical ID without changing the legacy Ask route.
- strict canonical five-slot Entity Core Page projection over E8.1/E8.2, with
  independent Overview, Definition, Official Regulations, Official Documents,
  and Confidence rendering; visible mode/state/gaps; truthful partial-page
  behavior; cross-entity fail-closed handling; and no duplicate data store.
- authenticated off-by-default federated search over canonical entities,
  official regulations/documents, amendments, consultations, deadlines, and
  owner-filtered prior research, with deterministic fixed relevance/ties,
  visible why-matched/provenance, full structured filters, correction-bound
  keysets, genuine original-query reversal, isolated unavailable groups, and
  safe total failure.
- flagged debounced grouped Research Workspace typeahead with stale-response
  fencing, keyboard-complete focus, canonical entity re-resolution,
  owned-session restoration, safe artifact routes, and explicit
  pending/no-match/degraded states.
- additive migration `0033` with six production-expression-matched GIN indexes
  over existing canonical search stores and no copied source rows.
- authenticated off-by-default manual official-document search with exact
  phrase, lexical, title, issuer, document number/type, family/version,
  current/superseded/draft, issue/effective date, and within-document filters;
  deterministic status-as-of ordering, version-preserving deep links, opaque
  keyset pagination, fixed match reasons, and explicit no-match/unavailable
  outcomes.
- flagged `/browse` manual-search controls with stale-response fencing,
  accessible exact filters, canonical route restoration, official-source
  metadata and excerpts, safe failures, and unchanged flag-off legacy Browse.
- additive migration `0034` with three production-predicate-matched registry
  status/date and within-document chunk indexes over existing source rows.

Migrations end at `0034`. No production-volume rehearsal, approved regulatory Decision calibration, natural-language Decision Engine routing authority, production capability adapters, v2 serving cutover, live provider, or calibrated claim-support verifier exists in the repository.

## Current task

**E9.10 Application-wide UI/UX refinement** (`Active`)

The attached `Design Guidelines.pptx` is the presentation source of truth for
the existing application UI. This enhancement applies its Resolven palette,
display/body typography hierarchy, diagonal brand geometry, spacing, surfaces,
controls, navigation, states, and responsive behavior through reusable visual
tokens and primitives. It MUST preserve interactions, business logic, API and
data contracts, schema, and frozen specifications. After visual verification,
the Planner resumes E9.2.1 and then the normal eligible task graph.

Implementation and automated local validation are complete. B-015 blocks the
required manual major-route review because the mandated Codex in-app Browser
runtime cannot initialize its `node_repl` kernel assets. E9.10 MUST remain
Active and MUST NOT be approved until that browser evidence is collected.

## Completed work

- Current Ask flow, data model, retrieval, AI, latency, errors, dead code, and failure paths audited.
- Product experience frozen as a Regulatory Intelligence Workspace.
- Deterministic Decision Engine frozen.
- Capability Orchestrator frozen.
- Thirteen-epic, 101-PR implementation plan frozen.
- Agent OS initialized with operating loop, product/architecture summaries, tasks, current state, decisions, progress, tests, blockers, and changelog.
- Agent OS compliance is enforced by a central policy, modular validators, collect-all reporting, fixture tests, and a dedicated GitHub Actions workflow.
- `.codex/REVIEW.md` provides the requested reviewer-policy entry point while preserving `.codex/REVIEWER.md` as the canonical detailed guidance.
- E0.1 freezes the existing Ask backend contract in JSON fixtures and eight passing pytest cases without changing runtime code.
- E0.2 replaces the frontend typecheck-only test alias with Vitest, React Testing Library, a jsdom setup, five legacy Ask component smoke tests, and CI/compliance execution.
- E0.3 adds all nine frozen backend flags, strict frontend UI parsing, and a fail-closed `AskRoute`; every flag defaults off and legacy rendering remains the default.
- E0.4 adds one Ask correlation identity, safe structured model/retrieval failures with legacy fields/statuses, correlated internal logging, frontend safe-code mapping, and draft restoration.
- E0.5 adds correlation-linked auth/persistence/retrieval/model/request timing and outcome events with payload-safe fields and no answer change.
- Epic E0 delivery guardrails and compatibility foundation is complete.
- E1.1 adds expand-only migration `0023`, owner-scoped session RLS, nullable/unique message public identity, nullable owner-safe session linkage, cursor indexes, migration-ledger coverage, and a non-destructive rollback note.
- Migration `0023` passes empty-schema and `0022` upgrade execution, owner/non-owner RLS, legacy-row preservation, public-privilege, and linkage/identity constraint tests on disposable PostgreSQL 16 with pgvector.
- E1.2 adds immutable typed session/message/turn records, owner-filtered repositories, and a transaction-owning service that creates stable user/assistant placeholders and updates session activity only after both inserts.
- E1.2 PostgreSQL tests prove exact identities/content/order, session-derived scope, cross-owner non-leakage, owned lookup, and rollback of the user message and activity timestamp when the assistant insert fails.
- E1.3 adds migration `0024` with seven owned artifact tables, message/run/session ownership constraints, ordered/versioned sections, immutable official/live source snapshots, claims, citations/live links, follow-ups, run events, RLS, and least-privilege read grants.
- E1.3 PostgreSQL tests prove empty and `0023` upgrade paths, ledger recording, unchanged turns, every-table owner visibility, cross-owner rejection, General AI source/citation exclusion, official/live lane matching, and event replay rejection.
- E1.4 adds migration `0027` with assistant status/reply/parent/version lineage, exact message/run/section version constraints, durable version-specific feedback, RLS, least-privilege grants, and a non-destructive rollback path.
- E1.4 typed persistence updates one feedback identity per exact version, restores every historical version with its artifacts and feedback, and keeps public/legacy contracts unchanged while complete-turn reads select the latest version.
- E1.5 adds deterministic UUIDv5 legacy session/message identity, one session per owner/global-or-event scope, bounded atomic batches, operator max-batch checkpoints, natural resume, dry-run, duration/count metrics, and streamed verification.
- E1.5 PostgreSQL tests prove global/event/multi-owner/odd/orphan recovery, no-write dry run, idempotency, bounded resume, failure rollback/recovery, exact content/order/timestamp preservation, and drift reporting.
- E1.6 adds an explicit preflight plus migration `0025` refusal for pending/drifted backfill state, validated paired message identity, unique legacy scope, and owner/session cursor indexing while still permitting flag-off null/null writes.
- E1.6 PostgreSQL tests prove empty application, preflight/refusal ledger rollback, post-backfill success, unchanged rows, partial-identity rejection, duplicate legacy-scope rejection, and legacy write compatibility.
- E2.1 adds versioned create/list/detail contracts behind only `ASK_AI_V2_API_ENABLED`, with a deterministic new-session title, owner-only reads, identical missing/cross-owner detail errors, and no legacy route change.
- E2.1 session pagination excludes archived/deleted sessions and uses an opaque descending `(updated_at, id)` cursor that remains stable when newer sessions are inserted; archived detail remains reopenable and deleted detail does not.
- One recorded session JSON fixture is enforced by backend Pydantic and frontend Zod contract tests.
- E2.2 adds chronological complete-turn pagination behind the same v2 API flag and owner/deletion boundary.
- Run-linked turns restore both messages plus ordered sections, sources, claims, citations, and follow-ups; raw decision, orchestration, timing, and verifier-result payloads remain internal.
- Backfilled, interrupted, or otherwise run-less messages serialize as explicit singleton turns instead of inferred pairs, and one shared version-1 JSON fixture is enforced by Pydantic and Zod.
- E2.2 PostgreSQL tests prove exact nested restoration and duplicate-free cursor continuation when a newer complete turn is inserted between pages.
- E2.3 adds flag-gated owner-only `PATCH`, archive, restore, duplicate, export, and recoverable soft-delete actions over the existing session lifecycle columns with identical inaccessible-session responses.
- Rename/pin patches reject null/empty changes and preserve `updated_at` on an identical retry; archive unpins exactly once, archive/restore/delete are timestamp-stable and idempotent, deleted sessions remain stored but disappear from all owned reads/actions, and archived sessions cannot be pinned.
- Duplicate creates a fresh active draft with copied event/entity/topic/scope only; it intentionally resets knowledge-mode/freshness state and copies no grounded prose/artifact, preventing provenance-free duplication while leaving the source unchanged.
- Export uses one repeatable-read transaction and only the existing public session, complete-turn, artifact, and saved-item schemas, so raw decision/orchestration/verifier/provider fields remain excluded.
- Twenty-nine focused backend API/PostgreSQL lifecycle cases, five shared frontend session-contract cases, the 891-test backend regression, and the 57-test frontend suite pass without a migration, search index, frontend rail, or legacy route change.
- E2.4 adds expression GIN indexes over weighted session metadata, message content, and immutable source/document snapshots without adding denormalized columns or rewriting stored content.
- The v2 session list now accepts normalized `q`, knowledge-mode, entity, archived, and pinned filters; maximum lane relevance `500/400/300` plus update-time/UUID ties produce deterministic bounded results.
- Version-2 session cursors bind rank/tie state to normalized filter identity, reject changed-filter continuation, and preserve version-1 cursors only for the original unfiltered list.
- Empty/populated `0030` upgrades, three representative GIN plans, supporting indexes, owner/RLS/least-privilege boundaries, malformed filters, concurrent inserts, shared frontend cache identity, and unchanged flag-off behavior are covered by 40 focused backend and 16 focused frontend cases.
- E2.5 adds migration `0028`, typed saved-item persistence, exact owned message/evidence/source reads, version-specific feedback writes, and session saved-item list/create/delete behind the existing v2 API gate.
- E2.5 tests prove all five saved target kinds, exact artifact version linkage, idempotent mutation identity, populated upgrades, RLS/least privilege, real PostgreSQL cross-owner isolation, non-disclosing API behavior, shared Pydantic/Zod contracts, and unchanged legacy routes.
- E2.6 adds an isolated persisted-v2 compatibility adapter for exact legacy response/history meanings, persisted Decision Record intent translation, official citation snapshots, related questions, event scope, and selected response versions.
- E2.6 golden/refusal tests prove grounded and no-evidence equality, PostgreSQL restoration, descending history, and fail-closed incomplete, mismatched, broken-link, General AI, or live states without route wiring.
- E3.1 adds immutable strict Decision Request/Record, conversation scope, intent, atomic question, entity, time, capability, retrieval-plan, mode, evidence, confidence, degradation, explanation, and terminal-state types.
- E3.1 freezes 15 intents, five subtypes with allowed parents, 11 entity classes, eight time dimensions, three knowledge modes, nine capabilities, seven capability outcomes, 15 response strategies, four confidence labels, and three terminal product states.
- E3.1 deterministic policy applies all 15 precedence steps over structured signals, including context pronouns, multi-part dominance, compliance/deadline/live secondary intents, version comparison, and healthy general fallback.
- Thirty-three focused tests cover all 19 representative query labels, every precedence branch/collision, exact confidence-band boundaries, immutable deterministic round trips, blank/unknown/duplicate rejection, and reversed-range refusal.
- E3.2 normalizes explicit dates/ranges/years, before/after/since, today, ISO local week, local month, rolling recent/breaking, latest/current, draft, consultation, and latest-draft compound status.
- E3.2 intent defaults cover definition, entity, regulation, deadline, compliance, amendment, timeline, news, consultation, summarization, and no-filter behavior with visible assumptions/freshness requirements.
- Fixed-clock tests prove Asia/Kolkata and America/New_York day differences, DST local boundaries, exact elapsed rolling windows across DST, leap-month boundaries, invalid-zone/naive-clock refusal, and unsupported/reversed input rejection.
- E3.3 adds migration `0026` with canonical entity, alias/acronym, and glossary tables because the legacy graph metadata cannot enforce scoped uniqueness and provenance safely.
- E3.3 applies exact canonical, approved alias/acronym, reinforced glossary, interaction, conversation, jurisdiction-context, fuzzy, and clarification policy without any route import.
- Twenty-five resolver tests plus four PostgreSQL migration tests cover all named fixtures, alias-scope mismatch, ambiguity, workspace dominance, query expansion, exact confidence values, the `0.85` high-risk gate, additive upgrade, RLS, and least privilege.
- E3.4 adds immutable scope-layer/current-reset/reference/context and atomic-clause/decomposition contracts without a natural-language parser or route import.
- E3.4 resolves every scope field in frozen precedence order, preserves safe scope during one-question antecedent clarification, and refuses retained entities after an explicit current-turn reset.
- E3.4 produces stable ordered atomic questions with per-part intent sets, shared scope, clause overrides, closest/global time binding, visible conflicting scope, and multi-part coverage signaling.
- Fourteen focused context tests plus the 101-test Decision Engine suite cover the frozen three-part query, all scope fields, resets, pronouns, defaults, clause inheritance/override, time binding, contradictory jurisdictions, subtype validity, and deterministic IDs.
- E3.5 adds complete immutable plan/question/capability/stage/blueprint contracts and a conditional capability role without executing work.
- E3.5 encodes every atomic intent against all nine capabilities, live/lineage/General-AI/document eligibility, five plan classes, five frozen planning stages, evidence gates/fallbacks, and canonical response blueprints.
- The versioned 19-query golden matrix plus 11 focused tests prove exact roles, skipped branches, response surfaces, multi-part deduplication, General AI isolation, missing-document clarification, accepted degraded fallback, stage dependencies, and strict plan shape.
- E3.6 adds a deterministic lexical adapter that constructs the existing immutable Decision Record/time/plan contracts after legacy retrieval has already selected the serving intent.
- Fixed legacy-to-canonical agreement/disagreement/unavailable comparisons run only as enabled post-response background work; their telemetry contains no question, evidence, answer, owner, provider detail, or raw error.
- Evaluator, recorder, and factory failures are suppressed from serving, and exact flag-off/flag-on legacy response goldens remain identical.
- A separate row-locked owned-run repository stores an exact empty-slot Decision Record/policy once, is idempotent for the same record, returns non-disclosing not-found cross-owner, and refuses different nonempty state without a migration.
- Sixty-five focused Decision/shadow/persistence/legacy cases, the 916-test backend regression, and unchanged 59-test frontend suite pass.
- E3.7 adds a strict immutable calibration-artifact contract for labeled
  intent/entity/time/plan expectations, locked intent/high-risk-entity
  thresholds, regulatory rationale, and attributable approval provenance.
- A canonical SHA-256 digest binds the schema and Decision policy versions,
  thresholds, and every reviewed case; placeholder provenance, naive approval
  time, duplicate identity, unknown fields, policy drift, and case/threshold
  tampering fail closed.
- Fourteen synthetic contract tests pass, but no synthetic or pre-existing
  engineering fixture is treated as regulatory approval. B-013 records the
  missing reviewer-approved dataset and keeps Decision routing shadow-only.
- E4.7 adds a versioned selected-fixture shadow harness over the real bounded
  scheduler with exact expected phase, terminal, and ordered node outcomes.
- Only literal `True` opens its early kill switch; every other value performs
  zero validation, timing, execution, or recording. Enabled boundary inputs
  and reports are revalidated without mutating the original state.
- Exact agreement, disagreement, and fixed unavailable comparisons serialize
  deterministically; evaluator/input/recorder failures are isolated while task
  cancellation propagates.
- Default telemetry emits only correlation/policy, phase/terminal, safe code,
  duration, and fixed terminal-state counts. Fixture/node IDs and
  request/evidence/answer content are excluded.
- Twelve focused shadow cases, the 942-test backend regression, and unchanged
  59-test frontend suite pass without route, provider, persistence, migration,
  frontend, or serving integration. Epic E4 is complete.
- E5.4 adds a strict canonical entity/approved expansion graph request and the
  complete frozen relationship taxonomy over an injected provider boundary.
- Distinct edge identities become distinct deterministic Structured Facts;
  exact E5.3 Evidence Units and atomic-question scope remain attached.
- Unbacked and `relates_to` facts are always discovery-only. Relation,
  direction, entity, evidence, duplicate, and question-scope failures are
  isolated without suppressing valid neighbors.
- Eleven focused graph cases, the 133-test affected slice, 953 backend tests,
  and unchanged 59 frontend tests pass. No SQL/provider path means no migration
  or index change is warranted.
- E5.6 adds a pure evidence-cutoff Timeline Builder with exact date semantics,
  provenance lanes, material/scope admission, source ancestry, and
  weakest-critical-source confidence caps.
- Missing dates remain absent/inferred and event relationships resolve to
  output IDs with unresolved-link warnings. Same-key/same-semantic differing
  dates remain stable conflict sets independent of input order.
- Fourteen focused timeline cases, the 115-test affected slice, 967 backend
  tests, and unchanged 59 frontend tests pass without narrative, provider,
  persistence, migration, route, frontend, or serving integration.
- E4.1 adds an isolated immutable Orchestrator contract package for its distinct ten-capability roster, six participation classes, eleven capability terminal states, seven section terminal states, and thirteen semantic artifact kinds.
- Capability requests carry typed admitted artifacts and results enforce exact identity/scope, declared output authority, timing, safe failure codes, and healthy no-match/failure/skip separation without executing work.
- Artifact envelopes enforce producer authority, source-lane identity, timezone-aware live provenance, immutable transformation ancestry, non-escalation, General AI source exclusion, and deterministic typed JSON round trips.
- Frozen capability registries declare all accepted inputs and allowed outputs; Decision, persisted-v2 compatibility, routes, providers, persistence, scheduling, and frontend behavior remain unchanged.
- E4.2 adds ten forward-only phases, queued/active/terminal capability states, documented section work/terminal states, and deterministic complete/degraded/clarification/cancelled run outcomes.
- Approved plans expand into immutable scoped nodes at the `capability × atomic question × section × provenance lane` boundary with unique request identities, acyclic node dependencies, plan/scope/mode admission, and exact phase gates.
- Citation Verifier evidence-integrity and claim-support passes remain separate nodes; grounded material claims cannot become terminal-ready before claim verification is terminal.
- Twenty-one focused lifecycle tests exhaust every phase/capability/section transition pair, activation phase, terminal run outcome, dependency/scope refusal, optional-section nonblocking merge, early clarification, and stable state round trip.
- E4.3 adds immutable scheduler bindings/configuration/report contracts over E4.2 state nodes, with no route, database, provider, or persistence import.
- Only selected queued nodes admitted for the current phase execute; declared terminal dependencies create deterministic waves and same-wave results are applied in stable plan order.
- Independent async work shares a bounded overall semaphore, while temporary synchronous adapters also use a smaller blocking semaphore and `asyncio.to_thread` so provider/database compatibility work does not block the event loop.
- Injected executors are reused across admitted invocations; missing, raising, or malformed adapters become fixed safe unavailable/invalid-output results without raw details.
- Six focused scheduler tests prove selected-only parallel execution, same-phase dependency waves, concurrency caps, shared lifecycle use, event-loop responsiveness, blocking-pool pressure, failure isolation, deterministic reports, and unchanged input state after request-construction failure.
- E4.4 adds five immutable exact latency profiles and a run-scoped injected monotonic budget shared across scheduler phase calls.
- Checkpoints expose first-result, core, soft, reserve, and hard boundaries; the profile contract prevents optional work from borrowing the 15% verification reserve and preserves the frozen seven-step optional stopping order.
- Optional nodes cancel and supporting nodes time out at the soft boundary, while mandatory/conditional/fallback work and Citation Verifier retain protected execution until the hard boundary.
- Scheduler deadlines cover semaphore waits and async or temporary blocking adapter execution; late outputs are discarded and replaced with fixed safe soft/hard terminal results.
- Hard-cutoff section finalization keeps admitted safe artifacts, detaches unverified grounded claims, degrades required/useful partial sections, and omits empty optional sections without inventing readiness.
- Twelve focused latency cases cover every exact profile and boundary, decision-plan mapping, invalid profiles, reserve protection, optional/supporting/mandatory behavior, real deadline interruption, safe late-result withholding, deterministic JSON, and hard-cutoff artifact/claim handling.
- E4.5 adds strict immutable failure rules and transition decisions for all ten capabilities, evidence-integrity rejection, and single/all-claim support rejection.
- Decisions retain original terminal outcomes while distinguishing partial, healthy no-match, ambiguity, timeout, unavailable, invalid output, and verifier rejection through fixed safe notices and scoped dispositions.
- Dependency traversal is node-level and transitive but stops at an eligible fallback boundary; fallback activation requires both a declared edge and fallback/conditional-mandatory role, and hidden capability expansion is refused.
- Optional Timeline/News outcomes omit only their own nonrequired section, while graph/live/general/composer/follow-up failures preserve unrelated lanes and all admitted artifacts.
- One fallback transition and one single-claim correction pass are hard maxima; evidence-integrity and all-claim failures permit no claim revision.
- Twenty-six focused failure-policy cases cover the full matrix, exact refusal paths, fallback role/dependency gates, substitute-boundary traversal, scoped isolation, deterministic JSON, optional dispositions, safe preservation, and both verifier passes.
- E4.6 adds additive migration `0029` over the existing owned run/event aggregate with monotonic execution versions, a row-locked next-sequence allocator, expiring lease/heartbeat fields, and durable cancellation-request identity.
- Durable repository operations atomically acquire/renew/release leases, append state transitions, request/apply cancellation, and update the exact run snapshot while idempotent public event identities make retries stable.
- Expected execution versions fence stale workers; expired leases permit takeover, terminal runs reject new leases, and ordered replay rejects gaps, regression, admitted-artifact removal, terminal-state mutation, and cross-run identity reuse.
- Safe cancellation retains all admitted artifacts and terminal sections, reports unverified grounded claims for withholding, records the final cancellation boundary, and releases the worker lease without changing a production route.
- Twenty-three focused migration/repository cases cover empty/populated upgrades, lease lifecycle, expiry, idempotency, crash/replay, cursors, phase-by-phase preservation, cancellation, owner/RLS isolation, concurrent allocation, and legacy-compatible additive behavior.
- E10.1 adds a strict version-1 owner-neutral run-event read model that retains actual typed orchestration state while excluding owner/session identity, worker lease payloads, and undeclared lifecycle/capability values.
- Opaque resume cursors bind exact run/event/sequence/execution identity to a persisted anchor; bounded pages are read against one captured run boundary and fail closed on crossed owners, stale/tampered anchors, counter drift, or sequence gaps.
- Full replay now requires zero-based contiguous sequence and execution versions, stable run/session/owner/policy identity, unique event identity, matching state/run identity, monotonic orchestration state, and no event of any kind after a terminal boundary.
- Forty focused E10.1/E4.6 cases plus the 862-test backend regression prove safe serialization, cursor refusal, bounded resume without duplicates, deterministic reconstruction, terminal immutability, PostgreSQL ownership, and existing durability compatibility without a migration, API, worker, or frontend change.
- E10.2 adds an injected async durable coordinator whose SQLAlchemy store executes every owner-scoped lease, snapshot, state, and cancellation transaction off the event loop.
- Workers acquire or take over only expired leases, run bounded TTL-scoped driver steps, renew between accepted steps, persist every forward-valid state atomically, return existing terminal runs idempotently, and never accept a late result after ownership/version drift.
- Persisted active capabilities are recovered first as explicit `Unavailable` outcomes with `CAPABILITY_EXECUTION_INTERRUPTED`; driver progress and the repository both refuse plan/run changes, phase regression, artifact loss, terminal mutation, or other invalid replay progress before storage.
- Durable cancellation wins before driver validation and in the final append race; an interrupted process leaves its lease to expire, the next worker resumes the stored state, and the stale worker cannot overwrite the winner.
- Fifty-three focused E10.2/E10.1/E4.6 cases plus the 874-test backend regression cover process interruption, expired takeover, duplicate terminal invocation, active-node recovery, owner non-disclosure, narrow cancellation races, regressive drivers, deterministic replay, and existing durability/migration compatibility without a new migration, provider, route, stream, or frontend change.
- E4.8 adds strict immutable context candidate/request/selection contracts over already structured scope/relevance keys, with no language model or natural-language classification.
- Selection first excludes other owners/sessions, noncompleted turns, and corrected/inheritance-ineligible turns; it then selects the newest relevant candidates under a bounded `1–32` turn budget and emits complete pairs chronologically.
- Explicit reset clears all inherited scope, while a caller-resolved immediate follow-up retains the latest eligible turn even without repeated entity wording.
- Context output declares `fact_authority = none` and `requires_fresh_retrieval = true`, so prior conversation can resolve meaning but cannot make stale claims current.
- Thirteen focused cases cover long-session truncation, cross-session/user isolation, unrelated and nonterminal history, correction exclusion, reset, immediate follow-up, stable ties, exact accounting, strict validation, and deterministic serialization.
- E5.1 adds strict immutable branch outcomes for vector, keyword, graph, family/version, and summary with exact satisfied/no-match/partial/timeout/unavailable/invalid distinctions.
- Each outcome records health, injected-clock duration, match count, and only a fixed safe failure code; raw exception/provider details are excluded.
- `SupabaseHybridRetrieval` now exposes raw internal branch seams and ordered hybrid diagnostics while public branch methods still return legacy hit lists and suppress failures to `[]`.
- Graph's four internal SQL query units preserve healthy hits when one unit fails and report Partial/Degraded; all-unit failure reports Unavailable, and non-SQL malformed output retains the prior whole-branch failure boundary.
- Forty-five focused E5.1 cases plus legacy/affected regression cover every branch state, worker seam, safe-code contract, timing, graph partial behavior, stable aggregation, and unchanged chat responses.
- E5.2 maps only approved question-plan capability roles to the five official retrieval branches: internal document search to vector/keyword, Knowledge Graph to graph, metadata/lineage to family-version, and eligible official summarization to summary.
- Selected ownership is deduplicated across atomic questions in stable branch order; each selected synchronous seam executes off the event loop under a bounded semaphore and is invoked at most once.
- Nonselected branches emit strict Skipped/Not run outcomes with zero duration and no failure code; selected failures, malformed output, or healthy no-match never activate skipped work.
- Ten focused E5.2 cases plus the 72-test affected slice cover the 19-query routing matrix, General-AI-only zero-call behavior, multi-question identity, stable aggregation, concurrency, failure isolation, contract drift, and unchanged all-five-branch legacy hybrid behavior.
- E5.3 requires complete caller-supplied branch relevance floors, admits exact boundaries, maps healthy weak hits to No match, and fails malformed evidence closed without embedding unapproved E5.8 production values.
- Exact vector/keyword document-version-chunk duplicates become one deterministic Evidence Unit with ordered match reasons; every graph row remains distinct until E5.4 supplies durable fact identity.
- Fourteen focused E5.3 cases plus the 97-test affected slice cover policy validation, thresholds, intent overrides, weak/invalid hits, canonical passages, distinct graph facts, stable ordering, and plan mismatch refusal.
- E5.5 adds immutable official version/status/relationship evidence with complete, partial, and unavailable coverage and exact current/historical/draft decision states.
- Effective-dated supersession/repeal preserves prior in-force history; connected active amendment sets remain together, while unknown, conflicting, cross-family, missing-endpoint, invalid-chronology, and cyclic lineage fails closed.
- Twenty-one focused E5.5 cases plus the 130-test affected slice cover current, historical-as-of, terminal status, draft/future effectiveness, coverage failure, active sets, contradictions, strict contracts, and order independence.
- E5.7 adds strict configured identity, grouped index inventory, compatibility decision, and vector preflight contracts across ready, healthy-empty, partial, unavailable, mismatch, and invalid states.
- The real PostgreSQL health probe exposes `vector(N)` column dimension and provider/model/dimension counts; incompatible populated indexes can no longer become healthy vector no-match.
- Typed vector work stops before embedding/search on partial or failed preflight, while ready work executes normally and legacy public vector methods retain empty-list failure compatibility.
- Twenty-six focused E5.7 cases plus the 104-test affected slice cover physical empty/populated inventory, all mismatch classes, startup failure, malformed metadata, no-match trust, actual vector-seam gating, strict contracts, and safe-detail exclusion.
- E5.9 adds strict immutable declared/actual provider identities, validation decisions, and validated v2 provider bundles for the exact supported retrieval/vector/embedding matrix.
- Unsupported retrieval/vector/embedding choices, the legacy memory declaration, the wrong offline model, unsupported dimensions, missing/blank remote credentials, construction failures, class identity drift, health identity drift, and nonhealthy startup compatibility fail explicitly with deterministic safe codes and no secret detail.
- Validated embedding/vector instances are injected into both v2 retrieval execution and health, while legacy no-injection factories and behavior remain available.
- Thirty-four focused E5.9 cases plus the 124-test affected slice cover the full matrix, credentials, drift, startup states, safe construction, dependency wiring, strict contracts, and legacy compatibility.
- E6.1 adds strict immutable official/live outcome, section-mode, provenance, disclosure, citation/source presentation, legal-force, confidence-ceiling, pending-lane, notice, and terminal selection contracts.
- The pure matrix selects Mode 1 for sufficient/partial official evidence, Mode 2 only for explicit general work or eligible no-match/outage/background triggers, and Mode 3 only for attributed live outcomes; one section cannot cross lanes.
- Exact no-documents wording is confined to healthy official no-match, outage copy never claims absence, pending official work cannot trigger fallback, and live no-match/unavailable remain distinct.
- Mode 2 prohibits citation/source identity and legal applicability; Mode 3 requires attribution and cannot establish legal force; Mode 1 legal force requires verified official status evidence.
- Fifty-eight focused E6.1 cases plus the 177-test affected Decision/Orchestrator slice cover the full matrix, ceilings, disclosures, multi-mode/multi-part rules, pending/degraded/empty states, contamination guards, strict contracts, and deterministic serialization.
- E6.2 adds strict immutable General AI execution request/provider payload/unit/result contracts and an isolated async Parallel adapter consuming only E6.1-assigned Mode 2 sections.
- One bounded call covers the ordered assigned section set; noneligible decisions make zero provider calls, while exact healthy-no-match, outage, explicit-general, and multi-part policies retain their own disclosures and Medium/Low/Unknown ceilings.
- Request/policy/provider identity are revalidated at the boundary, Parallel credentials/model must be explicit and nonblank, and the canonical Orchestrator General Knowledge payload now supports the disclosure-less explicit-general case.
- Provider citations, links, official-absence or binding-applicability wording, duplicate policy copy, source identity, malformed/version/section drift, oversized output, timeout, exceptions, and unsafe provider identity fail closed with fixed safe codes and no leaked detail.
- Forty-nine focused E6.2 cases plus the 176-test affected mode/Orchestrator/legacy slice cover eligibility, provider configuration, one-call execution, exact copy/ceilings, multi-part order, contamination, failure/timeout, strictness, nested revalidation, and deterministic serialization.
- E7.1 adds strict immutable official-evidence candidates, admission requests, admitted units, exclusions, and fixed safe rejection codes over the canonical E5.3, E5.5, and Orchestrator contracts.
- Admission requires exact artifact/evidence identity, positive chunk plus locator, inspectable official source identity, exact resolved-scope echo, admitted relevance metadata, direct pending official provenance, usable ancestry, and satisfied/partial retrieval state.
- Current, historical-as-of, and draft evidence must carry the exact E5.5 request/decision pair, which is recomputed at admission; nonselected older/later versions, stale evaluation scope, unverified status text, no-match, unknown, contradiction, and invalid lineage cannot reach composition.
- Per-candidate revalidation isolates malformed nested/model-copy output without suppressing a valid neighboring unit; no provider, semantic claim-support judgment, confidence calculation, route, persistence, migration, or frontend behavior was added.
- Forty-one focused E7.1 cases plus the 104-test affected evidence/status/Orchestrator slice cover identity, inspectability, scope, provenance, relevance, terminal state, current/historical/draft status, stale versions, partial retention, strictness, safe detail exclusion, and deterministic serialization.
- E7.2 adds strict immutable versioned Candidate Claim batch requests, accepted claims, exclusions, and fixed safe rejection codes over canonical Orchestrator claim artifacts and E7.1 admission results.
- Every accepted claim is material, pending verification, assigned to exactly one approved atomic question and section, grounded in the internal-regulatory lane, and linked in exact order to one or more admitted official Evidence Units in that same narrowed scope.
- The final Response Composer transformation must name the exact support references; duplicate, missing, excluded, unknown, crossed-scope, crossed-lane, malformed, conflicting, nonterminal, preverified, duplicate-ID, or evidence-ID-colliding claims are isolated without semantic support judgment.
- Twenty-seven focused E7.2 cases plus the 117-test affected Candidate Claim/evidence/Orchestrator slice cover single/multi-part and multi-source claims, scope/lane/reference/lineage integrity, invalid-neighbor isolation, admission tampering, strictness, and deterministic serialization.
- E7.4 adds strict immutable versioned confidence dimension, claim, section, overall, penalty, hard-Unknown, High-gate, strict-intent, request, and result contracts.
- Claim scores use the exact 25/15/20/15/15/10 weighted sum, all six frozen additive penalties, and 0–100 bounds; raw numeric labels remain distinct from final labels after High gates, E6 mode/scope ceilings, weakest-critical-input caps, and hard Unknown overrides.
- Section scores use the exact 70% coverage-weighted mean plus 30% lowest material claim; overall scores use the exact 70% importance-weighted mean plus 30% lowest critical section, with weakest-critical-section and strict-intent lowest-claim caps.
- Forty-six focused E7.4 cases plus the 192-test affected Decision/E6/E7/Orchestrator slice cover every weight, penalty, 0/35/60/80/100 boundary, High gate, hard Unknown, mode/input ceiling, zero coverage, aggregation, strict intent, multi-mode visibility, strictness, and deterministic serialization.
- E8.1 adds strict versioned Pydantic and Zod structured-response, ordered-section, card, confidence, action, state, rendering, and compatibility-summary contracts.
- The contract freezes all 15 response strategies, all 12 frozen card types, all common/specific action types, three mode/provenance lanes, claim/source references, contiguous order, `Not established`/partial/unavailable states, and honest available/disabled action metadata.
- Known cards require exact rendering identity; unknown future lower-snake-case card types preserve JSON payload behind an explicit fallback title without breaking the response.
- One shared all-card/all-lane JSON fixture round-trips identically through backend and frontend schemas; card-specific payload semantics, components, merge logic, and final legacy rendering remain later E8 tasks.
- Thirty-four backend E8.1 cases, five frontend contract cases, the 202-test affected backend slice, and the forced uncached 35-test frontend suite cover taxonomy, every strategy, order, uniqueness, lane/reference purity, action safety, JSON payloads, unknown fallback, strictness, and compatibility-summary presence.
- E7.8 adds an isolated strict confidence/coverage presentation boundary with
  overall and per-section score, label, coverage, categorized evidence-based
  reasons, gaps, evidence counts, freshness, and improvement guidance.
- The UI cannot elevate an E7.4 policy label above its numeric band, cannot
  label General AI High, cannot exceed the weakest critical section, and
  requires source counts to agree with displayed official/live modes.
- Mixed provenance sections remain separately visible, Unknown and Limited
  states are explicit, confidence is disclosed as not being a probability of
  legal correctness, and the collapsed explanation panel is keyboard and
  screen-reader accessible without default-route integration.
- Thirteen focused E7.8 cases plus the forced 86-test frontend suite, 1005-test
  backend suite, Ruff, compileall, typecheck, production build, and compliance
  cover strict input refusal, inaccessible-ID handling, non-color state,
  keyboard behavior, and route isolation.
- E8.2 adds matching strict version-1 Pydantic/Zod payload contracts for Answer
  Summary, Definition, Official Source, and Confidence/Coverage cards without
  changing the E8.1 envelope.
- Structured text/date fields preserve explicit `Not established` state;
  generic JSON, malformed dates, mode/provenance drift, dishonest source
  counts, elevated confidence, General AI sources/High labels, and
  introspection reasons fail closed.
- Grounded definitions require official definition/source identity. Official
  Source cards retain exactly one official source, complete issuer/type/date/
  status/locator/excerpt/relationship metadata or truthful Partial state, and
  explicit Open/Save/Compare action availability.
- Isolated renderers show visible provenance and state, responsive metadata,
  evidence excerpts, exact coverage meters, non-color missing fields, separate
  mixed-mode confidence cards, accessible disabled actions, and keyboard
  behavior; available actions without an injected real handler remain hidden.
- Nineteen focused backend E8.2 cases plus the 183-test affected backend slice,
  ten focused component cases, 96-test frontend suite, 1024-test backend suite,
  Ruff, compileall, typecheck, production build, and compliance cover strict
  parity, compatibility, accessibility, and default-route isolation.
- E9.1 adds one `ask-ai-v2` TanStack Query hierarchy scoped by authenticated owner and stable session/message/run/version identity, with cursor values retained as page parameters rather than cache fragments.
- The feature-scoped provider carries only auth, explicit feature enablement, and a read client; session/turn/evidence/source/saved-item data remains canonical in the query cache, and message evidence plus its selected run share one cache record.
- Typed read hooks parse the existing E2 contracts and an injected exact E8.1 structured-response projection, use the provider's exact access token, encode resource path segments, and remain unavailable while flag/auth/resource identity is incomplete.
- Nine focused E9.1 cases plus the forced uncached 44-test frontend suite prove stable keys, both opaque cursor paths, enablement, contract refusal, canonical sharing, exact-token use, and cross-owner cache isolation while legacy Ask component tests remain green.
- E9.6 adds strict client-generated optimistic message/idempotency identities and query-cache-only saving/unsynced/synced reconciliation records with fixed safe failure codes.
- Persisted E2 turns update every cached page-size variant exactly once; incomplete oldest-first histories retain their cursor and use one deduplicated resolved overlay until a matching server page arrives.
- Stable ID/content checks reject crossed results and collisions; repeated begin/reconcile, server-first/client-first/refetch races, cold cache, safe retry, owner/session isolation, and provider remount preserve visible work.
- Eleven focused E9.6 cases plus the forced uncached 55-test frontend suite pass without adding a mutation endpoint, local React message store, route integration, or legacy behavior.
- Existing authentication/identity migrations through `0022` and the legacy Ask implementation remain behaviorally unchanged.

## Remaining work

E0, E1.1–E1.6, E2, E3.1–E3.6, E4,
E5.1–E5.7/E5.9, E6.1–E6.2/E6.5, E7.1–E7.2/E7.4–E7.5/E7.8, E8.1–E8.2,
E9.1–E9.3/E9.6/E9.8, E10.1–E10.3/E10.6–E10.7, and
E11.1–E11.2/E11.5–E11.6 are complete. E1.7 is active. E3.7, E5.8, E6.3,
E7.3, and every dependent implementation task remain planned but are no
longer governance blocked. The task graph MUST continue in priority and
dependency order.

`E0 guardrails → E1/E2 persistence and APIs + E3 decisions → E4 orchestration → E5 evidence → E6/E7 modes and trust → E8 composition → E9/E10 workspace and streaming → E11 journeys → E12 rollout`

Detailed task status: [03_TASKS.md](./03_TASKS.md).

## Known issues

- The persisted-v2 legacy adapter exists, but legacy routes do not consume it and no dual-read/cutover is active.
- Decision plans, immutable capability artifacts, deterministic lifecycle transitions, bounded scheduler execution, latency/failure decisions, and durable event/cancellation primitives exist, but no production adapter/serving integration exists.
- Legacy new searches can still disappear because local state and query cache diverge; isolated v2 E9.6 reconciliation is not route-mounted yet.
- Citations and AI metadata do not restore from history.
- Populated legacy history rows contain database datetimes that currently fail the route's declared `str | int | None` response validation and produce HTTP 500.
- Typed v2 retrieval outcomes distinguish failure from healthy no-match, but the unchanged legacy route still collapses both to its existing empty-result behavior.
- Missing citations prevent AI synthesis.
- Citations are not claim-verified.
- Parallel.ai web provenance is discarded.
- No application-controlled live-news retrieval.
- The isolated v2 selector skips ineligible retrieval work, but the unchanged legacy route still runs all five branches for every query.
- The legacy route still selects global/event history; the correct v2 active-session context selector is isolated and not yet wired to serving.
- Blocking database/provider work occurs in an async route.
- Legacy and non-Ask pages still retain their shared base-query boot behavior;
  flag-on v2 Ask is isolated from those legacy data dependencies.
- UI still lacks canvas/evidence integration, feedback, regeneration controls,
  and stream consumption; backend regeneration/refresh and session
  navigation/search/lifecycle actions are real.
- Federated and manual document search are lexical over approved internal
  stores and intentionally admit no live-provider result; the frozen
  live-intelligence journey remains unfinished.
- Production dependency audit reports three pre-existing high-severity advisory groups in Next.js/PostCSS/sharp; remediation is authorized and remains an engineering release gate under the approved B-012 policy.

The blocker register contains zero unresolved blockers:
[08_BLOCKERS.md](./08_BLOCKERS.md).

## Next recommended task

Complete E9.10 through task-level local validation and manual major-route
visual review. Then resume E9.2.1, followed by the highest-priority eligible
task under the continuous Agent OS loop.

## Last successful iteration

GOV-B005-B014 governance approval package. Eight enterprise approval artifacts
now fix Live Intelligence, production SLO, claim verification, production
migration, integration-test ownership, dependency security, Decision
calibration, and retrieval calibration policy. Every blocker is Resolved,
frozen specification hashes remain unchanged, E1.7 is the highest-priority
eligible task, and the full Agent OS compliance gate passes with zero failures
and zero warnings.
