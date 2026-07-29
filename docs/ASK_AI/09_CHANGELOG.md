# Ask AI Engineering Changelog

All notable completed Ask AI changes are recorded here. Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Planned work belongs in [03_TASKS.md](./03_TASKS.md), not here.

## [Unreleased]

### Added

- Ask AI governance approval package:
  - approved Live Intelligence providers, domains, licensing, provenance,
    freshness, attribution, separation, caching, rate limits, failure
    behavior, source trust, UI badges, and confidence ceilings under B-005;
  - approved component/profile percentile SLOs, alerts, degradation, circuit
    breakers, error budgets, dashboards, and pager conditions under B-007;
  - approved material-claim definitions, verifier pipeline, correction,
    evidence-only boundary, human dataset, and precision/recall release gates
    under B-009;
  - approved production expand/backfill/validate/contract migration, volume
    rehearsal, batch, lock, maintenance, recovery, reconciliation, and
    rollback envelope under B-010;
  - declared all Ask AI integration tests canonical repository assets with
    deterministic ownership, review, staging, modification, quarantine, and
    deletion rules under B-011;
  - approved dependency security SLAs, upgrade cadence, severity handling,
    lockfile policy, exceptions, rollback, audit evidence, and zero
    Critical/High release gate under B-012;
  - approved Decision and retrieval golden-dataset specifications, exact
    thresholds, checksum provenance, reviewer workflows, shadow gates, and
    release signoffs under B-013 and B-014.
  - resolved every blocker in the Agent OS register and activated E1.7 as the
    highest-priority dependency-eligible engineering task.
  - made the Agent OS root Markdown and nested approval Markdown artifacts
    explicitly versionable under the repository's general `docs/*` ignore
    rule.
- Agent Operating System:
  - permanent execution/resume loop;
  - concise product and architecture summaries;
  - hierarchical live task registry;
  - current-state handoff;
  - architectural decision index;
  - append-only progress journal;
  - measurable test plan;
  - unresolved blocker registry;
  - engineering changelog.
- Frozen Ask AI documentation set:
  - architecture audit;
  - Regulatory Intelligence Workspace product specification;
  - deterministic Decision Engine;
  - AI capability Orchestrator;
  - 13-epic production implementation plan.
- Agent OS compliance framework:
  - central TOML policy and frozen-document hashes;
  - modular document, task, state, dependency, blocker, security, hygiene, branch, and test validators;
  - collect-all console and Markdown reporting;
  - fixture-based compliance regression suite;
  - dedicated GitHub Actions workflow and uploaded compliance report;
  - reviewer-policy compatibility entry point at `.codex/REVIEW.md`.
- Legacy Ask backend contract suite:
  - recorded JSON fixtures for success, citations, no-evidence fallback, model and retrieval failures, history, and authentication;
  - eight pytest cases covering persistence sequencing, conversation-history selection, repository ordering/filtering, HTTP response shape, and current failure behavior;
  - no application runtime or database change.
- Frontend test foundation:
  - Vitest, React Testing Library, jest-dom, user-event, and jsdom development tooling;
  - five legacy Ask component smoke tests for empty, grounded, uncited, composer, and loading states;
  - root Turbo and Agent OS compliance execution alongside typecheck and production build.
- Ask rollout boundary:
  - nine typed backend rollout flags from the frozen implementation plan, all off by default;
  - strict public UI flag parsing and a fail-closed `AskRoute`;
  - backend and frontend default/independence/equivalence tests with no v2 implementation.
- Safe Ask failures and correlation:
  - server-generated correlation headers across the Ask surface;
  - safe structured retrieval/model errors retaining legacy status and `detail`;
  - correlated internal detail logging without exposing upstream text to clients;
  - typed frontend safe messages, legacy fallback preservation, and failed-draft restoration.
- Ask baseline metrics:
  - correlation-linked auth, persistence, retrieval, model, and terminal request stages;
  - typed success/no-match/skipped/suppressed-failure/unavailable outcomes;
  - fixed payload-safe fields and tests proving question/evidence content is excluded.
- Ask AI session schema expansion:
  - additive `0023` migration with durable owner-scoped session identity, workspace metadata, lifecycle timestamps, and cursor indexes;
  - nullable stable public identity and session linkage on legacy chat messages without backfill or row reinterpretation;
  - composite session/message ownership, authenticated-owner RLS, and least-privilege grants;
  - disposable PostgreSQL verification from empty and `0022`, including ledger, legacy-row, ownership, and uniqueness checks;
  - non-destructive flag rollback that retains additive schema and the legacy chat path.
- Ask AI session/message persistence:
  - immutable typed session, message, and turn-placeholder records;
  - isolated owner-filtered session/message repositories with caller-stable public UUIDs;
  - one transaction for the user message, assistant placeholder, and session activity update;
  - propagated persistence errors and full rollback when any placeholder write fails;
  - unchanged legacy chat repository and route behavior while v2 flags remain off.
- Ask AI research-artifact schema:
  - additive `0024` runs, ordered/versioned sections, official/live source snapshots, claims, citations/live links, follow-ups, and run events;
  - composite run/session/user/message ownership and RLS across every artifact;
  - General AI provenance plus required model/policy/disclosure metadata without synthetic source or citation rows;
  - database-enforced official/live provenance-lane matching and replay-safe run-event sequence identity;
  - empty/`0023` migration, unchanged-turn, least-privilege, ownership, provenance, and ordering tests.
- Ask AI legacy history backfill:
  - permanent deterministic UUIDv5 identities for legacy sessions and messages;
  - one recoverable legacy session per owner and global/event scope without turn-pair assumptions;
  - dry-run, bounded batches, max-batch checkpoints, natural resume, idempotent rerun, metrics, and streamed verification;
  - atomic batch rollback and refusal/reporting for conflicting non-null identity;
  - preserved message IDs, owners, event scope, roles, content, timestamps, and ordering.
- Ask AI backfill validation:
  - explicit clean-preflight command before migration `0025`;
  - transaction/ledger refusal for pending identity or ownership/scope/marker drift;
  - validated paired public/session identity and unique legacy owner/event scope;
  - owner/session message cursor index;
  - continued flag-off null/null legacy writes with true non-null contraction deferred.
- Ask AI session API:
  - authenticated, versioned `POST /chat/sessions`, `GET /chat/sessions`, and `GET /chat/sessions/{session_id}` contracts gated only by the off-by-default v2 API flag;
  - deterministic new-session title fallback and bounded create metadata;
  - owner-only active-session listing with an opaque descending `(updated_at, id)` cursor and stable concurrent-insert behavior;
  - identical missing/cross-owner/deleted detail responses, with archived sessions excluded from lists but still reopenable by their owner;
  - one recorded JSON contract enforced by backend Pydantic and frontend Zod tests, with legacy chat routes unchanged.
- Ask AI complete-turn history:
  - authenticated `GET /chat/sessions/{session_id}/messages` behind the same off-by-default v2 API gate;
  - chronological complete-turn page units with an opaque `(created_at, id)` cursor and a maximum page size of 50;
  - exact display restoration for linked user/assistant messages, sections, sources, claims, citations, and follow-ups;
  - explicit singleton turns for run-less legacy or interrupted messages, without inferred pairing;
  - public omission of raw decision, orchestration, timing, and verifier-result payloads;
  - PostgreSQL concurrent-insert stability and a shared backend/frontend version-1 turn fixture.
- Ask AI Decision Record and taxonomy:
  - isolated immutable version-1 domain contracts for every canonical Decision Record area;
  - complete frozen intent, subtype-parent, entity, time, knowledge-mode, capability, outcome, response-strategy, confidence, and terminal-state enums;
  - all 15 ordered intent-precedence rules over already-extracted structured signals, with no natural-language classifier or serving integration;
  - exact intent-confidence bands and deterministic canonical JSON round trips;
  - one recorded taxonomy fixture covering all 19 representative query decisions and strict rejection of unknown, blank, duplicate, or reversed-range input.
- Ask AI time/status understanding:
  - injected aware clock and IANA user-zone normalization with no route integration;
  - half-open explicit date/range/year and local today/ISO-week/month windows;
  - exact elapsed rolling 90-day recent, 30-day News-default, and 72-hour breaking windows across DST;
  - latest/current/draft/consultation status filters, live eligibility, visible source expressions, and freshness requirements;
  - all frozen intent-specific defaults and fail-closed naive-clock, unknown-zone, unsupported-expression, and reversed-range behavior.
- Ask AI entity/glossary resolution:
  - additive `0026` canonical entity, approved alias/acronym, and glossary tables with jurisdiction-scoped normalized keys, provenance, optional graph linkage, authenticated read-only RLS, and ambiguity-preserving mappings;
  - immutable catalogue/request/result contracts and the frozen eight-step resolver order;
  - exact `1.00/0.95/0.85/0.70/0.50/<0.50` resolution confidence, visible expansion/assumptions, and `0.85` obligation/deadline/current/amendment gate;
  - recorded DSM, ABT, REC, RPO, CERC, MNRE, Green Hydrogen, Tariff Policy, Electricity Act, and synthetic ambiguity fixtures;
  - empty/`0025` migration, scoped uniqueness, least-privilege, deterministic resolution, and fail-closed mismatch tests with no route integration.
- Ask AI entity lookup and disambiguation:
  - authenticated, off-by-default `POST /chat/entities/resolve` over the
    existing deterministic E3.3 catalogue/resolver, with strict
    resolved/ambiguous/no-match public contracts and fixed safe failures;
  - canonical identity, public aliases, jurisdiction, entity class, match
    reason, policy confidence, and canonical-ID route without provenance,
    graph, database, or provider internals;
  - flagged Research Workspace entity header with visible acronym expansion,
    keyboard-operable ambiguity selection, server-side candidate
    re-resolution, URL refresh/back restoration, and safe no-match/degraded
    states;
  - unchanged flag-off legacy Ask behavior and no entity content sections,
    new catalogue facts, migration, federated search, or live-source work.
- Ask AI entity core page:
  - matching strict backend/frontend version-1 projection over E8.1/E8.2 with
    canonical entity binding and fixed Overview, Definition, Official
    Regulations, Official Documents, and Confidence slots;
  - exact slot order/title/strategy/card-family validation, honest
    ready/non-content/degraded state rules, live/cross-slot refusal, and no
    duplicate entity-page source of truth;
  - flagged independent section rendering with mode-first labeling, explicit
    state, assumptions, evidence gaps, `Not established` handling, safe
    malformed/mismatched identity refusal, and hidden unavailable actions;
  - complete and partial-page fixtures with no API, cache, corpus fact,
    migration, timeline, stakeholder, federated-search, or live-source work.
- Ask AI federated research search:
  - authenticated off-by-default `POST /chat/search` with strict
    backend/frontend version-1 request, correction, grouped-result, match
    reason, provenance, safe route, degradation, and opaque-pagination
    contracts;
  - deterministic read-through grouping over canonical entities/aliases,
    official regulations/documents, amendments, consultations, deadlines, and
    owner-filtered Previous Research, with fixed relevance tiers, stable ties,
    filter-bound cursors, isolated group failure, and safe total failure;
  - additive migration `0033` with six weighted expression GIN indexes that
    match production search predicates and do not copy or rewrite canonical
    source rows;
  - preserved-original automatic spelling/acronym expansion plus an explicit
    original-query mode whose one-click reversal changes retrieval and cursor
    identity;
  - flagged debounced grouped Workspace typeahead with stale-result fencing,
    visible why-matched/provenance and full frozen filters, keyboard-complete
    focus, canonical entity re-resolution, owned-session restoration, safe
    artifact navigation, and explicit pending/no-match/partial/unavailable
    states;
  - no live-provider retrieval, manual-document engine, new corpus facts,
    natural-language Decision authority, or default/legacy route switch.
- Ask AI multi-part and context policy:
  - immutable scope-layer, current-turn reset, reference-candidate, context-result, atomic-clause, and decomposition contracts;
  - fixed interaction, explicit current-turn, conversation, regulatory-default, and clarification precedence applied independently to every scope field;
  - one focused ambiguous-pronoun question that preserves independently resolved safe scope and refuses retained antecedents after an explicit entity reset;
  - stable ordered atomic questions with per-part intent sets, shared scope, clause-local/global time binding, local overrides, conflict visibility, and Research Report coverage signaling;
  - versioned conversation/decomposition fixtures and parameterized current-turn precedence tests with no route or provider integration.
- Ask AI retrieval/response plan selection:
  - complete nine-capability required/supporting/conditional/skipped routing for every atomic intent;
  - fixed cheap-resolution, intent-evidence, sufficiency, conditional-fallback, and response/verification stage ordering with explicit evidence gates;
  - Fast exact, Focused grounded, Live combined, Deep research, and Composite plan selection;
  - General AI evidence-gate isolation, live/version eligibility, selected-document clarification, accepted degraded fallback, and multi-part capability deduplication;
  - canonical response blueprints plus a versioned 19-query golden matrix, with no capability execution or serving integration.
- Ask AI feedback and response-version lineage:
  - additive `0027` assistant status, owning reply, positive response version, and exact prior-assistant regeneration parent fields;
  - composite constraints rejecting duplicate, skipped, cross-question, cross-session, and cross-owner chains while binding runs and sections to the same response version;
  - one authenticated-owner RLS feedback record per exact run/version with stable-identity update semantics;
  - typed internal feedback persistence and ordered historical-version restoration, with latest-version complete-turn compatibility and no public API change;
  - empty/`0026` migration, unchanged-row, ownership, lineage, feedback, and legacy-regression verification plus a non-destructive rollback note.
- Ask AI evidence, saved-item, and feedback APIs:
  - additive `0028` saved source, citation, card, entity, and document targets with durable label/metadata snapshots;
  - exact artifact run/version and composite owner/session constraints, authenticated-read-only RLS, and idempotent save identity;
  - flag-gated owned message evidence/source reads, version-specific feedback writes, and session saved-item list/create/delete operations;
  - non-disclosing missing/cross-owner behavior with real PostgreSQL authorization tests;
  - shared backend Pydantic/frontend Zod evidence, feedback, source, and saved-item contracts without switching the UI or legacy routes.
- Ask AI persisted-v2 legacy compatibility:
  - isolated completed-response-version mapping to the unchanged legacy `ChatResponse`;
  - exact official citation snapshot, related-question, event, model, answer, and Decision Record intent translation;
  - descending event-scoped persisted-turn mapping to legacy history field meanings;
  - fail-closed incomplete, mismatched-version, missing model/intent/source, General AI, and live-provenance states;
  - grounded/no-evidence golden equality and real PostgreSQL restoration with no route cutover or migration.
- Ask AI capability artifact contracts:
  - isolated immutable request/result contracts for the distinct ten-capability Orchestrator roster;
  - all six participation classes, eleven capability terminal states, seven section terminal states, and thirteen shared semantic artifact kinds;
  - typed admitted inputs, declared outputs, producer authority, exact scope echo, safe failure codes, confidence dimensions, and timezone-aware timing;
  - provenance-pure source lanes, complete live-source identity, General AI source exclusion, immutable transformation ancestry, and provenance non-escalation;
  - deterministic typed JSON round trips and adapter seams with no capability execution, persistence mutation, route wiring, migration, or frontend switch.
- Ask AI deterministic Orchestrator lifecycle:
  - ten immutable forward-only phases plus exhaustive capability, section, and run transition contracts;
  - scoped capability instances at the atomic-question, section, and provenance-lane failure boundary with unique request identity and acyclic node dependencies;
  - phase-specific activation for all capability operations, including separate Citation Verifier evidence-integrity and claim-support passes;
  - plan/scope/mode/input/output admission, safe artifact retention, grounded material-claim verification gates, optional-section nonblocking merge, and deterministic complete/degraded/clarification/cancelled finalization;
  - no scheduler, provider/database I/O, persistence mutation, route wiring, migration, or frontend switch.
- Ask AI async-safe dependency scheduler:
  - selected queued lifecycle nodes execute only after declared dependencies become terminal;
  - independent ready work uses bounded stable waves with a separate cap for temporary blocking adapters;
  - blocking adapters execute off the event loop while injected capability/provider lifecycles are reused;
  - missing, raising, and malformed adapters fail closed with fixed safe terminal results and no raw details;
  - no latency/fallback policy, durable event/cancellation behavior, production provider cutover, persistence mutation, route wiring, migration, or frontend switch.
- Ask AI latency and stopping policy:
  - five immutable versioned latency profiles carry exact first-result, core, soft, hard, and protected-verification boundaries;
  - injected monotonic clocks and deterministic checkpoints enforce optional/supporting soft stops while preserving Citation Verifier reserve;
  - scheduler deadlines cover limiter waits and capability execution, discard late outputs, and emit fixed safe soft/hard outcomes;
  - hard-cutoff section finalization retains safe artifacts, removes unverified grounded claims, degrades required work, and omits empty optional work;
  - no cooperative fallback selection, durable events/cancellation, production adapter cutover, persistence mutation, route wiring, migration, or frontend switch.
- Ask AI partial-failure and fallback policy:
  - immutable decisions cover every capability row plus evidence-integrity and single/all-claim verifier failures;
  - healthy no-match, partial, ambiguity, timeout, unavailable, and invalid output remain distinct with fixed safe notices;
  - propagation follows declared scoped descendants and stops at an eligible fallback boundary;
  - General AI substitution requires both a declared dependency and fallback/conditional participation, with at most one transition;
  - unrelated sections and all safe admitted artifacts remain preserved; optional live/timeline failures omit only their own sections;
  - no retry execution, durable event/cancellation behavior, production provider cutover, persistence mutation, route wiring, migration, or frontend switch.
- Ask AI durable run events and cancellation:
  - additive `0029` execution versions, row-locked event allocation, expiring worker leases/heartbeats, and durable cancellation requests on the existing owned run/event aggregate;
  - atomic idempotent lease, state-transition, cancellation-request, and cancellation-application events with stale-worker version fencing;
  - ordered replay and exact run snapshots that reject duplicate, out-of-order, regressing, artifact-losing, or terminal-mutating histories;
  - safe cancellation plans retain admitted artifacts and completed sections while identifying unverified grounded claims for withholding;
  - populated-upgrade, phase, crash/replay, concurrent allocation, ownership/RLS, legacy-regression, and full build verification with no production adapter, route, stream, retry, regeneration, or frontend switch.
- Ask AI conversation-context selection:
  - immutable versioned candidate, request, selected-message, and selection contracts over structured context keys;
  - active owner/session filtering plus completed/inheritance eligibility before relevance selection;
  - newest relevant bounded turn choice with stable chronological user/assistant serialization and exact exclusion/truncation accounting;
  - explicit reset and immediate-follow-up semantics without treating prior turns as factual evidence;
  - long-session, cross-session/user, unrelated-history, follow-up, ordering, strict-validation, and deterministic round-trip tests with no storage, route, provider, migration, or frontend change.
- Ask AI typed retrieval outcomes:
  - immutable versioned branch status, health, duration, match-count, and fixed safe-failure contracts for vector, keyword, graph, family/version, and summary;
  - satisfied, healthy no-match, partial/degraded, timed-out, unavailable, and invalid-output distinctions;
  - raw internal branch seams with legacy public hit-list methods and fail-closed behavior retained;
  - deterministic hybrid branch diagnostics without changing selection, ranking, citations, or response contracts;
  - graph partial-failure preservation plus all-branch failure/malformed/timing injection tests with no threshold, deduplication, provider, route, migration, or frontend switch.
- Ask AI selective retrieval:
  - deterministic approved-plan mapping from internal search, Knowledge Graph, metadata/lineage, and official-source summarization to the five existing retrieval branches;
  - stable deduplicated capability/question ownership across multi-part plans;
  - bounded worker-thread execution of only selected synchronous branch seams with stable outcome and hit aggregation;
  - explicit Skipped/Not run zero-duration outcomes for every nonselected branch, with no provider invocation after selected failure or healthy no-match;
  - full routing-fixture, no-call, concurrency, failure, malformed-output, order, and legacy all-branch compatibility tests with no threshold, hit deduplication, graph query, provider, route, migration, or frontend switch.
- Ask AI retrieval quality and canonical evidence:
  - versioned caller-supplied complete branch relevance floors with optional atomic-intent overrides and no unreviewed production defaults before E5.8;
  - inclusive threshold admission, healthy below-threshold no-match, and fail-closed malformed/non-finite evidence outcomes;
  - deterministic Evidence Unit identity for exact vector/keyword document-version-chunk duplicates with ordered match reasons, question ownership, and maximum source-native scores;
  - preservation of every graph row until durable fact identity is available, preventing text-based collapse of distinct facts;
  - boundary, weak-hit, invalid-hit, intent-override, duplicate-passage, graph-distinctness, plan-alignment, order, and serialization tests with no legacy ranker/serving change.
- Ask AI version/current-status evidence:
  - immutable official version records, effective-dated lineage relationships, explicit coverage, resolved-status, and decision contracts;
  - current, historical-as-of, draft/consultation, superseded, repealed, unknown, contradictory, and invalid-lineage distinctions;
  - chronological direct-status versus supersession/repeal precedence, prior in-force preservation, connected active amendment sets, and separate publication/effectiveness semantics;
  - fixed safe failure codes for partial/unavailable coverage, newer unknown state, conflicts, family mismatch, missing endpoints, invalid chronology, and cycles;
  - current-claim admission only for validated-current evidence, with strict/order-independent fixtures and no title inference, migration, route, provider, or frontend switch.
- Ask AI embedding compatibility health:
  - strict configured embedding identity, grouped indexed identity, physical column dimension, compatibility decision, and vector preflight contracts;
  - Ready, compatible Healthy empty, Partial index, provider unavailable, provider/model/dimension mismatch, metadata unavailable, and invalid metadata distinctions;
  - real PostgreSQL empty/populated inventory health with deterministic provider/model/dimension counts and `vector(1536)` discovery;
  - typed vector preflight that prevents incompatible filtered indexes from becoming false no-match and stops failed work before embed/search;
  - fixed safe outcomes with unchanged legacy public empty-list behavior and no E5.9 enforcement, reindex, migration, route, or frontend switch.
- Ask AI v2 provider-configuration enforcement:
  - strict versioned declared/actual provider identities, validation decisions, and validated provider bundles;
  - exact Supabase retrieval/vector and existing offline/OpenAI-compatible/Parallel embedding matrix at physical dimension 1536;
  - explicit safe rejection of unsupported declarations, wrong offline model, missing credentials, construction failures, identity drift, and nonhealthy startup compatibility;
  - validated embedding/vector dependency injection into both retrieval execution and health with unchanged legacy factories and no provider, reindex, route, migration, or frontend switch.
- Ask AI knowledge-mode domain policy:
  - immutable versioned official/live outcome, per-section Mode 1/2/3, notice, pending-lane, and terminal selection contracts;
  - exact healthy-no-match versus official-outage disclosures with distinct Medium versus Low/Unknown ceilings;
  - enforced official-citation, no-source General AI, and attributed-live provenance lanes with legal-force and prohibited-claim boundaries;
  - full matrix, mixed-mode/multi-part, pending, contamination, ceiling, strictness, and deterministic serialization coverage without capability execution or serving change.
- Ask AI isolated General AI capability:
  - one bounded Parallel generation call only for E6.1-assigned Mode 2 sections, with zero calls for noneligible or pending official work;
  - strict ordered versioned provider payloads converted to canonical Orchestrator General Knowledge units;
  - policy-owned healthy-no-match/outage disclosure, confidence ceiling, provenance, and prohibited claims rather than provider-authored trust metadata;
  - safe rejection of provider/configuration/timeout/malformed output and citation, source, official-absence, legal-applicability, or disclosure contamination without legacy serving change.
- Ask AI official-evidence integrity admission:
  - strict versioned candidates and results joining canonical E5.3 evidence, Orchestrator artifacts, and exact E5.5 status evidence;
  - inspectable document/chunk/locator/excerpt identity, exact scope/relevance/provenance/terminal-state gates, and fixed safe per-unit exclusions;
  - recomputed current, historical-as-of, and draft status fitness that withholds stale/nonselected, unknown, contradictory, invalid-lineage, forged, or mismatched evidence;
  - partial valid-neighbor retention and nested contract revalidation without semantic claim support, confidence calculation, serving, persistence, migration, provider, or frontend changes.
- Ask AI Candidate Claim contract:
  - strict versioned claim-batch requests/results over canonical Orchestrator Candidate Claim artifacts and E7.1 admission results;
  - one material pending Mode 1 claim per approved atomic-question/section scope with exact ordered admitted-evidence references;
  - matching final Response Composer transformation plus scope, provenance-lane, terminal-state, conflict, duplicate, and identity-collision gates;
  - independent invalid-claim exclusion without semantic support judgment, confidence calculation, serving, persistence, migration, provider/composer execution, or frontend changes.
- Ask AI evidence-derived confidence calculation:
  - strict versioned dimension, penalty, hard-Unknown, High-gate, claim, section, overall, request, and result contracts;
  - exact frozen weighted claim arithmetic, additive penalties, score bounds, label boundaries, E6 mode/scope and weakest-input ceilings;
  - exact coverage-weighted section and importance-weighted overall 70/30 aggregation with weakest critical and strict-intent caps;
  - multi-mode section visibility, nested revalidation, and deterministic serialization without verifier calibration, persistence, migration, serving, provider/composer execution, or frontend changes.
- Ask AI structured response and card transport:
  - strict versioned Pydantic/Zod response, ordered-section, generic card, confidence, action, state, rendering, and compatibility-summary contracts;
  - complete 15-strategy, 12-card, three-lane, claim/source-reference, order, and action-availability taxonomies;
  - explicit JSON-preserving fallback for unknown future card types without known-card impersonation;
  - one shared all-card/all-lane backend/frontend fixture and strict parity tests without card-specific semantics/components, merge, compatibility rendering, persistence, migration, serving, or UI changes.
- Ask AI durable run-event read contract:
  - versioned owner-neutral event records with typed orchestration state and only declared safe lifecycle/capability values;
  - opaque cursors bound to exact persisted run, public event, sequence, and execution-version identity;
  - bounded snapshot-aware repository pages with owner non-disclosure, idle resume, and fail-closed cursor/gap/counter validation;
  - strict full replay requiring contiguous identity/version history and refusing state regression or every post-terminal event, without a migration, endpoint, worker, or frontend change.
- Ask AI durable run execution and recovery:
  - injected async coordinator with off-loop owner-scoped SQL lease, snapshot, event, and cancellation transactions;
  - bounded lease-owned driver steps, expiry-based takeover, duplicate terminal idempotency, and stale-worker fencing;
  - explicit safe terminalization of persisted Active capabilities after interruption plus forward-state validation before durable append;
  - cancellation precedence during execution and the final append race, without a migration, production provider/worker, endpoint, stream, or frontend change.
- Ask AI resumable run-event stream:
  - authenticated owner-only SSE endpoint gated by both off-by-default v2 API
    and streaming flags;
  - exact persisted `Last-Event-ID`/query-cursor resume with conflicting,
    crossed, missing, and stale cursor refusal before stream headers;
  - bounded contiguous duplicate-free replay, off-loop repeatable-read polling,
    strict heartbeat/completion/safe-error controls, terminal closure, and
    disconnect handling;
  - safe public errors and owner non-disclosure without generated answer
    content, raw worker payload, frontend reducer, provider, or migration.
- Ask AI capability-specific retry:
  - additive migration `0031` with one owner-scoped retry execution per exact
    run/node/original request, client UUID idempotency, strict lifecycle
    constraints, expiring worker lease, recovery index, and read-only owner RLS;
  - exact transient-failure eligibility for official retrieval, live retrieval,
    General AI, and citation verification while healthy, partial, no-match,
    cancelled, unsupported, or dependency-failed nodes remain untouched;
  - v2 owner-only enqueue and injected one-node worker with a 30-second hard
    bound, restart takeover, stale/cancellation/version fencing, safe failure,
    and duplicate suppression;
  - immutable original run events, capabilities, sections, evidence, and
    artifacts; retry output remains a separate execution for later append-only
    answer-version handling.
- Ask AI response regeneration and refresh:
  - additive migration `0032` with immutable selected/current-parent/target
    response lineage, exact owner/version/message foreign keys, linear append
    constraints, owner-read RLS, and retained-data rollback;
  - separate strict same-source regeneration and official/live refresh
    contracts with default, concise, beginner, and legal-detail modifiers;
  - one owner-only v2 transaction locks the original turn, allocates a stable
    assistant identity plus valid pending durable run, and suppresses sequential
    or concurrent duplicate client requests;
  - exact historical source snapshot reuse only for same-source work, explicit
    fresh official or official-plus-live retrieval plans, and zero overwrite of
    prior messages, runs, evidence, citations, feedback, or saved state.
- Ask AI session lifecycle actions:
  - flag-gated owner-only rename, pin, archive, restore, context-duplicate, export, and recoverable soft-delete routes;
  - row-locked idempotent transitions, stable no-op timestamps, pin clearing on archive/delete, and safe archived-pin conflict responses;
  - fresh-identity context duplication that resets knowledge/freshness trust and copies no messages, runs, evidence, feedback, or saved items;
  - repeatable-read export through safe public session, complete-turn, and saved-item contracts, with unchanged legacy routes and no migration.
- Ask AI session search and filters:
  - additive `0030` expression GIN indexes for session metadata, message content, and immutable source/document snapshots, plus mode/entity/lifecycle cursor support;
  - owner-scoped lexical search with deterministic session/message/source relevance tiers and exact knowledge-mode, entity, archived, and pinned filters;
  - version-2 opaque cursors bound to normalized filter identity with stable concurrent-insert pagination and version-1 unfiltered-list compatibility;
  - shared frontend query normalization and cache identity, populated/empty migration, query-plan, RLS/least-privilege, malformed-input, and flag-off tests without a session rail or legacy route change.
- Ask AI shadow decision recording:
  - deterministic lexical shadow adapter that constructs the existing versioned Decision Record, time interpretation, capability plan, and response strategy beside legacy intent detection;
  - fixed legacy-to-canonical agreement, disagreement, and unavailable comparison contracts with question/evidence/answer-free telemetry;
  - post-response flag-gated execution plus evaluator, recorder, and factory failure isolation that leaves legacy retrieval, model work, response bodies, and history unchanged;
  - owner/run-locked exact Decision Record persistence with idempotent replay, cross-owner non-disclosure, and non-overwriting conflicts, without a migration, routing cutover, Orchestrator execution, or UI field.
- Ask AI regulatory calibration approval boundary:
  - strict immutable versioned contracts for reviewed Decision thresholds,
    query labels, expected entity/time/plan outcomes, regulatory rationale, and
    attributable approval provenance;
  - one canonical SHA-256 digest covering the complete reviewed policy,
    thresholds, and case payload, with deterministic round-trip and tamper,
    duplicate, placeholder, timestamp, policy-drift, and unknown-field tests;
  - synthetic contract evidence only, with the absent human approval recorded
    as B-013 and no runtime routing, provider, API, migration, or UI change.
- Ask AI shadow Orchestrator harness:
  - versioned selected-fixture expectations and deterministic
    agreement/disagreement/unavailable comparisons over the existing bounded
    async scheduler;
  - literal-True early kill switch, immutable boundary revalidation, evaluator
    and recorder failure isolation, task-cancellation propagation, and exact
    original-state preservation;
  - content-free aggregate telemetry and twelve focused tests without a route,
    production adapter, provider, persistence, migration, frontend, or serving
    change.
- Ask AI entity-aware graph retrieval boundary:
  - canonical resolved-entity, approved expansion, jurisdiction,
    relation-type, question/section, direction, and bounded provider contracts;
  - distinct deterministic Structured Facts with exact E5.3 backing Evidence
    Units and isolated invalid-neighbor/exclusion reasons;
  - mandatory discovery-only treatment for unbacked and `relates_to` edges,
    plus distinct no-match/partial/unavailable/invalid-output results, without
    SQL, migration, legacy graph, route, provider, or frontend changes.
- Ask AI Timeline Builder:
  - pure scoped material official/live/Structured Fact inputs and
    provenance-pure existing Timeline Event outputs with source ancestry and
    weakest-source confidence caps;
  - deterministic chronology retaining distinct date semantics, missing dates,
    inferred order, resolved/unresolved event relationships, and
    discovery-only graph status;
  - stable conflict sets retaining every differing same-semantic date
    independent of input order, without narrative, provider, persistence,
    migration, route, frontend, or serving changes.
- Ask AI retrieval evaluation boundary:
  - strict versioned per-intent labeled cases, expected healthy no-match,
    observed ranked evidence, typed branch observations, regulatory rationale,
    end-to-end latency, and complete threshold contracts;
  - deterministic precision@K, recall@K, case coverage, branch health, and p95
    end-to-end latency reports with full-payload tamper-evident approval;
  - draft results remain unapproved and B-014 records the absent regulatory
    dataset/threshold approval, with no runtime floor, provider, route,
    persistence, migration, frontend, or serving change.
- Ask AI provenance lineage:
  - strict versioned graph-wide traces and concrete admitted-evidence,
    Structured Fact, Timeline Event, Candidate Claim, and Section Draft
    adapters;
  - deterministic acyclic ancestry, scope narrowing, exact transitive source
    unions, immutable source identity, and verification-independent origins;
  - exhaustive authority-pair monotonicity, weakest-lane output, cross-lane
    citation filtering, and discovery-only zero-authority taint without route,
    provider, persistence, migration, frontend, or serving change.
- Ask AI mode UI primitives:
  - isolated typed official, General AI, and live provenance bands with visible
    mode/state metadata and exact E6.1 disclosure copy;
  - attributed live-source cards with publisher/type, timezone-aware
    publication/retrieval identity, safe links, coverage, and non-legal-force
    notice;
  - accessible pending/empty/degraded status regions, mandatory manual search
    fallback, keyboard/non-color tests, and strict invalid-input refusal
    without mounting or changing the default Ask route.
- Ask AI confidence/coverage UI:
  - isolated strict overall and per-section confidence indicators with numeric
    scores, policy labels, coverage, evidence counts, freshness, categorized
    reasons, gaps, and improvement guidance;
  - non-elevating labels, General AI and weakest-critical ceilings, exact
    mode/count agreement, and separately visible mixed provenance sections;
  - explicit Unknown/Limited/non-color identity plus an accessible collapsed
    explanation that confidence is not a probability of legal correctness,
    without mounting or changing the default Ask route.
- Ask AI core response cards:
  - matching strict version-1 backend/frontend payload contracts for Answer
    Summary, Definition, Official Source, and Confidence/Coverage cards;
  - explicit established/`Not established` structured fields, exact
    mode/provenance/reference/count rules, non-elevating confidence, and
    source-free General AI boundaries;
  - accessible isolated renderers with visible provenance/state, complete
    official metadata and excerpts, coverage meters, responsive missing-field
    presentation, keyboard actions, and no cosmetic available actions without
    a real handler;
  - unchanged generic payload ownership for later E8.3/E8.4 cards and no
    default-route, composer, persistence, migration, or serving integration.
- Ask AI manual document search:
  - authenticated off-by-default `POST /chat/documents/search` with strict
    canonical document/registry-version identity, exact phrase and lexical
    query, every frozen metadata/date/lifecycle/within-document filter, and
    fixed safe validation/storage outcomes;
  - canonical read-through over existing document, registry, family/
    assignment, and chunk stores with status-as-of evaluation, historical
    version preservation, deterministic ordering, match reasons, official
    metadata/excerpts, healthy no-match, and filter-bound opaque pagination;
  - additive migration `0034` with three production-matched registry cursor
    and chunk lookup indexes, populated upgrade/row-preservation/plan tests,
    and no copied source rows;
  - accessible flag-gated `/browse` controls, stale-response fencing, exact
    transport, canonical route restoration/cleanup, explicit empty/degraded
    states, and unchanged flag-off legacy Browse.
- Agent OS terminal graph compliance:
  - tested support for no active task only when no dependency-eligible item
    remains, while omission still fails whenever eligible work exists.

### Changed

- The in-progress E9.10 presentation layer now applies the Resolven design
  guideline palette, Verbatim-first typography hierarchy, diagonal brand
  geometry, shared spacing/radius/elevation tokens, unified navigation,
  cards, controls, tables, forms, dialogs, states, Ask AI workspace surfaces,
  and responsive rules across the application. Automated validation passes;
  final manual visual acceptance remains open under B-015.
- Documentation now distinguishes the completed legacy baseline from the unimplemented redesign.
- E0.1 Ask contract characterization is complete.
- E0.2 Frontend test foundation is complete.
- E0.3 Feature-flag boundary is complete.
- E0.4 Safe errors and correlation identity is complete.
- E0.5 Baseline stage metrics and Epic E0 are complete.
- E1.1 `0023` session expansion is complete.
- E1.2 session/message repositories is complete.
- E1.3 `0024` run and section artifacts is complete.
- E1.5 legacy backfill and E1.6 validation are complete.
- E8.1 Section and card contracts is complete.
- E9.1 Feature-scoped data layer adds an isolated, explicitly gated Research Workspace provider/read boundary; owner-scoped stable session/message/run keys; typed E2 session/turn/evidence/source/saved-item hooks; exact-token requests; opaque pagination; canonical message/run caching; and optional exact E8.1 structured-result parsing. It does not mount or alter the legacy workspace.
- E9.2 Research shell registers a semantic left-navigation/center-canvas/right-evidence workspace only behind the existing UI flag, with responsive mutually exclusive overlays, accessible panel controls, an immediately editable stable composer, explicit injected submission, race-safe acknowledgement, safe failures, and honest disabled behavior when submission is unavailable. Flag-off routing remains the legacy Ask view, and no cosmetic session/evidence behavior is added.
- E9.3 Session rail adds owned paginated active/pinned/archived navigation, recency groups, normalized server search/entity/mode filters, stable-ID selection, entity/provenance indicators, and real rename, pin, duplicate, JSON export, archive/restore, and confirmed soft-delete actions. Exact-token mutations validate responses, refresh only the owner's canonical session caches, handle 204 deletion, hide forbidden archived pinning, and expose safe failures without duplicating session server state.
- E9.8 removes flag-on v2 Ask boot coupling to the legacy digest, subscription, sources/runs admin probes, and flat chat history. Query hooks keep stable order but stay disabled, digest no longer blocks shell readiness, and manual base reload cannot bypass isolation; the nonblocking health check, flag-off legacy Ask, saved history, and all non-Ask dependencies remain unchanged.
- E9.6 Optimistic turn reconciliation adds strict client-generated message/idempotency identity, query-cache-only saving/unsynced/synced records, safe failure/retry, stable-ID conflict refusal, exact persisted-turn updates across page sizes, cursor-safe resolved overlays for incomplete long histories, and remount-safe pending visibility without mounting or altering the legacy workspace.
- E10.1 Durable run-event contract is the canonical autonomous resume task because it is the next eligible P0 task.
- The web package `test` command now runs component tests; typecheck remains an independent required gate.
- `docs/ASK_AI/*.md` is explicitly versionable despite the repository's general `docs/*` ignore rule.
- Local compliance reports under `artifacts/` are ignored and uploaded by CI instead of being committed.

## [0.1.0] — Release date not recorded

### Added

- Authenticated `/ask` experience.
- Legacy `POST /chat` and `GET /chat/history`.
- Hybrid vector, keyword, graph, family/version, and summary retrieval.
- Parallel.ai non-streaming answer synthesis when local citations exist.
- Flat chat-message persistence and best-effort retrieval audit.
- Markdown answer rendering, citation buttons, and Evidence Drawer.
- Supabase authentication and identity/security migrations through `0022`.

### Known limitations

- No true conversation sessions or exact structured restoration.
- Retrieval outages and no-match are not distinguishable.
- Citations are not claim-verified.
- No explicit live intelligence capability.
- Client/server state divergence can make searches disappear.

The `0.1.0` entry is an observed repository baseline, not a reconstructed historical release date.
