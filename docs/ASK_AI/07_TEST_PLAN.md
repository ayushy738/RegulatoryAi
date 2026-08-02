# Ask AI Agent OS — Test Plan

**Source:** Frozen acceptance criteria plus [ASK_AI_IMPLEMENTATION_PLAN.md](./ASK_AI_IMPLEMENTATION_PLAN.md).
**Task mapping:** [03_TASKS.md](./03_TASKS.md).
**Rule:** A feature is incomplete until its required tests pass in CI and its failure behavior is tested.

## 1. Current test baseline

- Backend uses pytest under `apps/api/backend/tests`.
- Backend Ask contract coverage now freezes success/citations, no-evidence fallback, model and retrieval errors, history ordering/shape and its populated-row validation failure, persistence sequencing, and auth rejection.
- Frontend `test` runs Vitest with React Testing Library and jsdom; five legacy Ask component smoke tests cover current rendering and interaction behavior.
- Backend/frontend feature-flag tests prove all frozen rollout controls default off, parse deterministically, and keep `/ask` on the legacy view when UI v2 is unavailable.
- Ask error contracts prove correlation propagation, safe code/detail bodies, internal-only upstream detail, legacy status compatibility, frontend safe mapping/fallback, and draft restoration.
- Ask baseline metric contracts cover success, no-match, retrieval/model unavailability, skipped model work, suppressed persistence failure, nonnegative durations, correlation, and payload contamination.
- E1.1 migration coverage executes all migrations through `0023` from an empty application schema and from `0022`, proves the ledger record, exact additive columns, nullable untouched legacy rows, owner/non-owner RLS, least-privilege access, composite ownership linkage, and unique public message identity.
- E1.2 repository coverage proves typed ordered placeholders, stable caller UUIDs, session-derived scope, owner-filtered lookup, identical missing/cross-owner errors, session locking/activity, and rollback of the user insert when the assistant insert fails.
- E1.3 migration coverage executes through `0024` from empty and `0023`, proves all seven artifact tables, ledger/RLS/read-only grants, unchanged existing turns, composite ownership FKs, official/live source constraints, General AI source/citation exclusion, provenance-lane matching, and unique run-event sequencing.
- E1.5 backfill coverage proves deterministic global/event/multi-owner grouping, odd/orphan preservation, dry-run no-write behavior, bounded batches, resume, idempotency, atomic failure rollback, streamed verification, stable UUIDs, unchanged content/order/timestamps, and divergent-identity reporting.
- E1.6 validation coverage proves empty-schema application, pre-backfill refusal with ledger/schema rollback, clean preflight success, validated paired identity, unique legacy scope, owner/session cursor index, unchanged rows, partial-identity rejection, and flag-off null/null compatibility.
- E1.4 migration/repository coverage executes through `0027` from empty and `0026`, proves unchanged existing message identity/content/order, deterministic initial-version backfill, message/run/section version agreement, skipped/duplicate/cross-question/cross-session/cross-owner lineage refusal, version-specific feedback update semantics, authenticated-read-only RLS, exact ordered restoration, non-owner isolation, and latest-version complete-turn compatibility.
- E2.1 API/PostgreSQL coverage proves the sole v2 API gate, authentication, deterministic create defaults, owner propagation, identical inaccessible detail responses, archived/deleted list/detail rules, opaque bounded keyset cursors, and stable pagination when a newer session is inserted.
- E2.1 backend Pydantic and frontend Zod schemas parse the same recorded version-1 session fixture.
- E2.2 API/PostgreSQL coverage proves authentication, non-leaking session ownership, chronological bounded complete-turn pagination, invalid cursor rejection, exact nested run artifact restoration, explicit unpaired-message recovery, and duplicate-free continuation when a newer turn is inserted.
- E2.2 backend Pydantic and frontend Zod schemas parse the same recorded version-1 complete-turn fixture; internal decision/orchestration/verifier payloads are absent from the public contract.
- E2.3 API/PostgreSQL coverage proves the sole v2 API gate, authentication, owner non-disclosure, normalized rename/pin requests, idempotent archive/restore/soft-delete transitions, stable no-op timestamps, archived-session pin refusal, and recoverable deleted-row retention.
- E2.3 duplication coverage proves a fresh active identity with copied research scope but no turns or artifacts and reset knowledge/freshness trust state; repeatable-read export coverage proves one exact safe public session/turn/saved-item snapshot. Backend Pydantic and frontend Zod contracts reject malformed lifecycle/export payloads without changing legacy routes or adding a migration.
- E2.4 migration coverage executes expression-index migration `0030` from empty and populated `0029`, proves stored title/message/source content is unchanged, verifies all three representative GIN query plans plus supporting mode/entity/lifecycle indexes, and documents non-destructive flag-off rollback.
- E2.4 API/PostgreSQL/frontend coverage proves lexical title/entity/topic, message, and source/document matches; deterministic `500/400/300` relevance; mode/entity/archived/pinned filters; stable concurrent-insert continuation; filter-bound cursor refusal; version-1 unfiltered cursor compatibility; malformed input rejection; owner non-disclosure; authenticated RLS/least privilege; normalized client requests/cache identity; and unchanged flag-off legacy behavior.
- E2.5 migration/repository/API coverage executes through `0028` from empty and populated `0027`, proves unchanged artifacts, exact source/citation/card run-version ownership, entity/document targets, idempotent save/feedback identity, real PostgreSQL owner/non-owner isolation, every evidence/saved-item/feedback flag/auth/not-found contract, and authenticated-read-only RLS.
- E2.5 backend Pydantic and frontend Zod schemas parse the same recorded version-1 evidence, sources, feedback, and saved-item fixtures without switching the UI.
- E2.6 compatibility coverage proves grounded and no-evidence `ChatResponse` golden equality, event-scoped descending history equality, explicit response-version selection, persisted Decision Record restoration from PostgreSQL, intent translation, citation snapshot mapping, and fail-closed incomplete/missing-model/missing-intent/mismatched-version/General-AI/live/broken-citation states with no route wiring or migration.
- E4.1 contract coverage freezes all ten Orchestrator capabilities, six participation classes, eleven capability terminal states, seven section terminal states, thirteen shared artifacts, three current provenance lanes, derivation types, and verification outcomes. It proves typed admitted inputs/declared outputs, stable immutable JSON round trips for every artifact, producer/scope authority, General AI source exclusion, complete live-source identity, provenance non-escalation/ancestry, safe failure-state separation, timezone-aware timings, follow-up cardinality, unknown/extra-state refusal, adapter seams, and unchanged Decision/legacy compatibility behavior without execution or migration.
- E4.2 lifecycle coverage freezes all ten forward-only phases, queued/active/terminal capability transitions, internal/public section transitions, capability operation activation phases, and four run terminal outcomes. It exhausts every allowed/forbidden phase/capability/section pair; proves complete plan/node coverage, scoped multi-instance isolation, acyclic node dependencies, unique request identity, two Citation Verifier passes, narrowed question/section/lane scope, admitted input/output retention, verified-grounded readiness, optional-section nonblocking merge, early clarification, terminal monotonicity, deterministic serialization, and unchanged legacy behavior without execution, I/O, or migration.
- E4.3 scheduler coverage proves selected-only stable execution waves, same-phase dependency ordering, allowed evidence fan-out, overall and blocking concurrency limits, shared injected executor lifecycles, event-loop responsiveness while temporary synchronous adapters run in worker threads, safe missing/raising/malformed adapter terminalization, deterministic report serialization, and unchanged input state on request-construction failure. It adds no migration, latency/fallback policy, durable resume/cancellation, production adapter, persistence, route, or UI behavior.
- E4.4 latency coverage freezes all five exact profile boundaries, the 15% protected verification shares, plan-class/profile mapping, and the seven-step optional stopping order. Injected-clock and real-deadline tests prove first/core/soft/reserve/hard boundaries, optional cancellation, supporting timeout/degradation, mandatory continuation, Citation Verifier reserve protection, semaphore/executor deadline coverage, late-result withholding, safe cutoff codes, retained artifacts, unverified-grounded-claim removal, and deterministic serialization without fallback, persistence, route, migration, or UI behavior.
- E4.5 failure-policy coverage freezes every ten-capability matrix row plus evidence-integrity, single-claim, and all-claim verifier cases. It proves partial/no-match/ambiguity/timed-out/unavailable/invalid distinctions, declared-descendant-only propagation, fallback-boundary traversal, dependency-plus-role fallback admission, no hidden capability expansion, optional live/timeline omission, scoped lane isolation, safe artifact preservation, fixed notice codes, one fallback/revision bounds, deterministic serialization, and refusal of nonfailures/ineligible signals without executing retries or changing persistence/serving.
- E4.6 durability coverage executes additive migration `0029` from empty and populated `0028`, preserves prior events, backfills monotonic execution versions/sequence allocation, and enforces complete lease/cancellation identities. Repository integration tests prove acquire/renew/release/expiry takeover, stale-worker fencing, idempotent event identity, atomic state append, crash/replay reconstruction, cursor reads, cancellation request/application, terminal lease refusal, phase-by-phase artifact preservation, owner filtering, authenticated RLS, and concurrent sequence allocation without changing legacy routes or serving.
- E4.8 context-selection coverage proves newest-first bounded choice with chronological message-pair output, active owner/session isolation, noncompleted/inheritance exclusion, normalized explicit relevance, unrelated-turn removal, immediate-follow-up retention, reset semantics, stable timestamp/anchor tie-breaking, exact candidate accounting, deterministic immutable serialization, and explicit meaning-only/no-factual-authority output without storage, model, route, migration, or frontend changes.
- E5.1 retrieval-outcome coverage executes every vector, keyword, graph, family/version, and summary branch through satisfied, healthy no-match, unavailable, timeout, malformed/wrong-lane invalid output, provider-seam failure, and unchanged legacy fail-closed behavior. It also proves injected timing, strict deterministic contracts, fixed safe codes without raw details, stable hybrid outcome order, unchanged ranked hits, graph partial SQL-unit preservation, and no routing/threshold/dedup/provider/route/migration/frontend change.
- E5.2 selective-retrieval coverage maps the complete 19-query Decision plan fixture to exact vector/keyword/graph/family-version/summary ownership, deduplicates branch/question identity across atomic questions, proves General-AI-only plans make zero official retrieval calls, and retains stable all-branch outcomes/hit aggregation under out-of-order completion. It also proves bounded worker-thread concurrency, selected failure/no-match/malformed isolation, strict Skipped/Not run contracts, request-boundary validation, and unchanged all-five-branch legacy hybrid behavior without thresholds, hit deduplication, graph query, provider, route, migration, or frontend changes.
- E5.3 retrieval-quality coverage requires unique complete finite branch defaults with optional atomic-intent overrides; proves inclusive exact thresholds, weak-hit exclusion as healthy no-match, non-finite/malformed hit failure as Invalid output or Partial, and approved-plan alignment. It canonicalizes only exact vector/keyword document-version-chunk passages with ordered match reasons and maximum method scores, retains all graph rows without guessing fact identity, and proves stable branch/unit order, deterministic serialization, and no production threshold default or legacy serving change.
- E5.5 version-status coverage proves complete official snapshots across current, historical-as-of, draft/consultation, superseded, repealed, unknown, partial, unavailable, contradictory, and invalid-lineage states. It covers effective-dated direct/relationship precedence, prior in-force history, publication before future effectiveness, connected active amendment sets, healthy absence, newer unknown blocking, same-date conflict, missing endpoints, family mismatch, invalid chronology, cycles, strict claim-support gates, future/naive evidence refusal, and input-order-independent serialization without title inference, migration, route, or frontend change.
- E5.7 embedding-health coverage proves Ready, compatible Healthy empty, Partial index, provider unavailable, provider/model/dimension mismatch, metadata unavailable, and invalid metadata states. It exercises real PostgreSQL empty/populated grouped inventory and physical `vector(1536)` discovery; startup/factory/malformed failures; strict count/identity contracts; no-match trust; typed vector preflight stopping before embed/search; ready execution; fixed safe codes; and unchanged legacy empty-list behavior without E5.9 enforcement, reindex, migration, route, or frontend change.
- E5.9 provider-configuration coverage proves the exact Supabase retrieval/vector plus offline/OpenAI-compatible/Parallel embedding matrix at dimension 1536; rejects memory/unknown providers, wrong offline model, unsupported dimensions, and missing/blank remote credentials; catches constructor, class-identity, health-identity, partial/mismatched/invalid startup states; injects validated instances into retrieval execution and health; emits deterministic safe detail-free decisions; and retains legacy factories without provider, reindex, route, migration, or frontend change.
- E6.1 knowledge-mode coverage proves sufficient/partial/no-match/unavailable/not-required/pending official outcomes crossed with official/reporting/unverified/no-match/unavailable/pending live outcomes; exact healthy-no-match and outage copy; Mode 1/2/3 provenance, citation/source, legal-force, prohibited-claim, and confidence ceilings; scope hard caps; selected-document refusal; live failure isolation; repeated same-mode multi-part sections; pending/degraded/empty invariants; strict validation; and deterministic serialization without capability execution, route, persistence, migration, provider, flag, or frontend change.
- E6.2 General AI coverage proves explicit-general, healthy official no-match, qualified outage, scope-Unknown, noneligible/pending, and ordered multi-part execution; exact policy-owned disclosure/ceiling/provenance; one Parallel call; canonical General Knowledge payloads; explicit nonblank credentials/model; strict section/version identity; citation/link/source/absence/applicability/disclosure contamination refusal; oversized/malformed/reordered/duplicate output; timeout/factory/identity/execution failures; safe detail exclusion; nested request/policy revalidation; deterministic serialization; and unchanged legacy chat without live, route, persistence, migration, flag, or frontend change.
- E6.3 Live Intelligence coverage freezes every B-005 approved official host and provider family, disabled-by-default connectors, versioned registry/entitlement snapshots, active-license and retention gates, exact-host HTTPS/credential/SSRF refusal, declared TLS/DNS/robots/text-extraction limits, publisher/type/license/content-hash identity, all fixed-clock freshness and consultation windows, L1–L5 confidence ceilings/badges, live-only Orchestrator provenance, non-legal-force disclosure, exact duplicate provenance retention, user/fan-out/provider limits, bounded/nonretryable failure behavior, healthy no-match distinction, partial provider preservation, deterministic cache keys/TTLs, stale-cache Low ceiling, strict malformed/tampered refusal, deterministic serialization, and no production connector/network/persistence/route/flag/UI/legacy change.
- E6.4 event-reconciliation coverage proves exact internal/live consolidation into one stable visual identity with separate provenance subsections; complete source, ancestry, publication, retrieval, and reported-status retention; official-only established legal status; input-order independence; readable material identity/date/type/description/status conflicts; unresolved official-status behavior; mandatory contradiction penalty and High prohibition; distinct inspectable near-duplicate clusters; chronological standalone events; cutoff and lane enforcement; strict duplicate-ID refusal; truthful no-events output; deterministic serialization; and no route, provider, persistence, migration, frontend, flag, or legacy change.
- E6.5 mode-UI coverage freezes exact E6.1 no-document, official-outage,
  no-live-update, and live-refresh copy; proves distinct official, General AI,
  live, and mixed-mode landmarks; disclosure-before-prose order; manual search
  fallback; positive source counts; outage confidence ceiling; attributed
  publisher/source type/publication/retrieval time; safe external links;
  live non-legal-force notice; pending polite announcement; empty/degraded
  status copy; keyboard focus; non-color mode/state identity; unsafe URL,
  blank/naive timestamp, missing action, and dishonest count refusal; and
  unchanged default-route isolation.
- E6.6 capability-degradation coverage projects every canonical failure class into strict visibility, severity, confidence effect, exact safe copy, affected/unaffected sections, preserved artifacts, and unique executable actions. It proves official/live healthy no-match never shares outage wording; optional live/timeline/follow-up chrome can be omitted; only E10.6 transient official/live/General-AI/verifier states expose scoped retry; only relevant evidence paths expose safe local manual search; ambiguity requests input; unsupported synthesis is withheld while evidence survives; backend/frontend JSON is exact; command rendering requires a real handler; keyboard interaction works; raw errors/safe codes are not displayed; and no route/API/persistence/legacy behavior changes.
- E7.1 evidence-admission coverage proves exact canonical/artifact identity, positive chunk plus locator, inspectable official source identity, excerpt/source metadata, approved-scope echo, atomic-question membership, E5.3 match/relevance identity, direct pending official provenance, ancestry, terminal state, conflict refusal, and partial valid-neighbor retention. Current, historical-as-of, and draft fixtures recompute the E5.5 decision and reject stale/nonselected versions, evaluation/mode/family/status drift, no-match, unknown, contradiction, invalid lineage, forged decisions, malformed nested/model-copy output, and unsafe detail while preserving deterministic immutable serialization and adding no claim-support, confidence, route, persistence, migration, provider, or frontend behavior.
- E7.2 Candidate Claim coverage proves one material pending Mode 1 claim per approved atomic-question/section scope; exact ordered references and final composer transformation over E7.1-admitted official evidence; multiple evidence references; separated multi-part claims; and explicit nonjudgment of semantic support. It rejects nonmaterial/supportless, duplicate/unknown/excluded, crossed-scope/lane, preverified, nonterminal, conflicting, wrong-lineage, duplicate/colliding identity, tampered admission, malformed neighbor, extra-field, and model-copy cases while preserving valid neighboring claims, deterministic serialization, and no verifier, confidence, route, persistence, migration, provider, composer execution, or frontend behavior.
- E7.3 claim-verifier coverage proves E7.1/E7.2 identity revalidation before semantics; exact atomic claim/evidence spans and qualifier coverage; executable B-009 publication and evaluation thresholds; weakest-proposition Supported/Partial Support/Contradiction/Unknown aggregation; high-risk confidence demotion; one subset-only correction and re-verification; checksum/version/provider/prompt-bound grounded-prose release; 2,200 ms budget; evidence-only timeout/unavailable/malformed/drift behavior; immutable evidence identity hashes; deterministic serialization; and safe provider-detail exclusion without a production provider, serving route, persistence, migration, or frontend change.
- E7.6 citation-persistence coverage executes additive migration `0035` from a populated `0034`, preserves and deterministically backfills existing claim/evidence identities, and proves one atomic owner/run/version write of exact claim text, admitted source snapshots, citation order, provenance, confidence output, correction/verifier artifact, and complete provider/verifier/model/prompt/policy/latency identity. Repository/API/frontend contract cases prove idempotent replay, stable-identity conflict refusal, full rollback on a missing owned source, owner isolation, current/superseded source status, feature-flag concealment, authentication, non-disclosing 404s, strict safe restoration, and unchanged legacy routes.
- E7.7 citation-UI coverage proves exact message/version/citation/claim/source joining, grounded-official lane enforcement, snapshot/locator identity, verified-only native controls, explicit pending/unavailable/support states, immediate saved metadata/excerpt/action presentation, progressive current-detail restoration, current and superseded status, safe failure retention, malformed/crossed-detail refusal, stale-load fencing, HTTPS-only source actions, optional real save handling, close-button focus, Escape, unique ARIA relationships, mobile layout, and no route, workspace-state, API, persistence, migration, or legacy-drawer change.
- E7.4 confidence coverage proves the exact 25/15/20/15/15/10 dimension weights, all six additive penalties, 0–100 bounding, continuous 35/60/80 label boundaries, every mandatory High gate, every hard-Unknown override, E6 mode/scope ceilings, weakest-critical-input caps, and stale/freshness consistency. It proves exact 70/30 coverage-weighted section and importance-weighted overall aggregation, zero-coverage handling, weakest material/critical label propagation, all four strict-intent reasons, multi-mode section visibility, graph/condition/nonfinite/extra-field/model-copy refusal, deterministic serialization, and no verifier calibration, provenance propagation, persistence, migration, route, provider, composer execution, or frontend behavior.
- E7.5 provenance-lineage coverage proves exact E7.1 admission, E5.4 graph
  backing, E5.6 timeline ancestry, claim support, section claim/input lineage,
  full transitive source union, same-document multi-chunk parent retention,
  every official/live/General-AI authority pair, weakest-lane monotonicity,
  cross-lane citation filtering, immutable source identity, verification-
  independent origin, scope narrowing, capability/kind matching, one local
  transformation, discovery-only taint/zero authority, cycle/missing/duplicate
  refusal, deterministic order/JSON, strictness, and immutability without
  route, provider, persistence, migration, frontend, or serving behavior.
- E7.8 confidence/coverage UI coverage proves collapsed accessible
  explanation, keyboard toggling, exact numeric meter values, explicit
  High/Medium/Low/Unknown and mixed/limited identities, independent
  per-section modes, weakest-critical and General-AI ceilings, label
  non-elevation, evidence-count/mode agreement, required categorized reasons,
  gaps/improvements/freshness, safe generated DOM identity, non-color
  critical visibility, introspection-text refusal, strict malformed-input
  rejection, and unchanged default-route isolation.
- E8.1 response-contract coverage freezes all 15 response strategies, 12 known card types, common/specific action types, section/card states, three mode/provenance lanes, confidence snapshots, claim/source references, assumptions/gaps, zero-based order, JSON payload, compatibility-summary, and unknown-card fallback. One shared all-card/all-lane fixture round-trips exactly through strict Pydantic and Zod schemas; backend/frontend tests reject known/fallback drift, cross-lane/reference cards, duplicate/gapped identity, dishonest action state, non-JSON/empty payload, future schema, extra fields, and mutation while adding no card-specific semantics/components, merge, follow-ups, compatibility renderer, persistence, migration, route, provider, composer execution, or UI switch.
- E8.2 core-card coverage proves matching strict version-1 Answer Summary,
  Definition, Official Source, and Confidence/Coverage payloads over the shared
  E8.1 fixture; explicit established/`Not established` text/date states;
  summary source counts; grounded/general definition boundaries; exact
  official lane/source/action identity and Partial metadata state; confidence
  reason/category/count/mode/numeric/General-AI constraints; generic payload,
  introspection, provenance crossing, malformed date, and later-card scope
  boundaries. Component tests prove visible mode/state, all frozen fields,
  evidence excerpts, exact coverage meter semantics, non-color missing state,
  separate mixed-mode cards, keyboard action execution, hidden unhandled
  available actions, accessible disabled actions, and default-route isolation.
- E8.3 compliance-card coverage proves matching strict version-1 Obligation,
  Deadline, and Stakeholder payloads over the shared E8.1 fixture; official-
  corpus-only grounding; exact claim/source/citation sets including multiple
  sources for one claim; complete versus Partial versus `Not established`
  invariants; confidence requirements and High prohibition for partial cards;
  responsible party/action/timing/trigger/jurisdiction/official basis;
  deadline date/type/stakeholder/status/source with disabled future tracking;
  stakeholder role/impact/obligations/regulations/entity/coverage; exact
  inspect/applicability/entity targets; unknown-field and crossed-provenance
  refusal; responsive metadata; non-color missing state; coverage meter
  semantics; keyboard-native real actions; hidden unhandled available actions;
  accessible disabled actions; legacy-route compatibility; and no route, API,
  persistence, migration, provider, flag, or legacy-serving change.
- E8.4 change/intelligence-card coverage proves matching strict version-1
  Timeline Event, Amendment, Comparison, Live News, and Related Regulation
  payloads; whole-card official/live lane switching; exact envelope claim/
  source identity; official timeline citations and live timeline publisher/
  type/publication/retrieval/badge/attribution/HTTPS identity; mandatory live
  non-legal-force disclosure; prior/next timeline relationships; amendment
  instrument/version/date/provision/stakeholder/summary/compare identity;
  independent comparison-side values and citations with visible
  `Not established` and cross-side citation-reuse refusal; live news relevance,
  safe source link, and official-basis target; related regulation provenance,
  explanation, evidence, and canonical entity target; Ready/Partial and High-
  ceiling invariants; crossed lane/envelope, unsafe URL, unknown-field, and
  unsafe-action refusal; responsive metadata and scroll-safe comparison table;
  keyboard-native real actions; hidden unhandled actions; and no route, API,
  persistence, migration, provider, flag, or legacy-serving change.
- E8.5 merge coverage proves strict terminal contribution identity; contiguous
  atomic-question ordering; deterministic question/blueprint/lane assembly;
  input-order-independent serialization; exact content deduplication with
  local section/card action-target normalization; collision-safe stable output
  identities; retention of same-ID/different-content card variants; explicit
  title/strategy/card conflict gaps; weakest confidence; provenance-pure same-
  key cross-mode sections; independently recoverable same-key multi-part
  sections; ready-content preservation as Degraded when a supporting
  contribution is cancelled; unaffected ready sibling sections; exact claim/
  source unions; section-action target rebinding; unknown future-card fallback;
  duplicate contribution and unstable question-order refusal; and a recorded
  golden projection, with no frontend, route, API, persistence, migration,
  provider, flag, or legacy-serving change.
- E8.6 follow-up coverage proves strict resolved entity/document/jurisdiction/
  stakeholder/comparison/related scope; frozen gap/evidence/compliance/change/
  explore/live ordering; fixed gap priority independent of input order;
  below-High official-provision or manual-search evidence deepening; retrieval-
  failure manual search without false absence; completed-intent and normalized
  prior-question/suggestion exclusion; plausible comparison operand and
  resolved-entity live gates; capability eligibility and degraded-capability
  refusal; safe control-character-free question construction; typed response-
  strategy previews; fresh-retrieval flags; stable suggestion identity;
  category/question diversity; exact Orchestrator FollowUpCandidates parity;
  deterministic serialization; three-to-five output; zero on budget exhaustion
  or insufficient safe diversity; required-for-completion false; strict invalid
  scope/prior/degradation refusal; and no route, provider, persistence,
  migration, frontend, flag, or current-turn content change.
- E8.7 compatibility-rendering coverage proves exact legacy Markdown and flat
  citation golden equivalence; structured section/source order; stable
  source-identity deduplication; verified official citation admission only;
  live and General AI separation; degraded and unknown-card disclosure;
  no-evidence behavior; provenance-crossing, unknown-reference, duplicate-ID,
  conflicting-source, missing-evidence, and control-character refusal; input
  order independence; and structured-response immutability without route,
  persistence, or legacy-adapter integration.
- E9.1 data-layer coverage proves stable owner-scoped session/message/run/structured-response keys, distinct page-size identities, session and complete-turn opaque cursor continuation, flag/auth/token/resource enablement, exact request-token use, E2 session/turn/evidence/source/saved-item parsing, E8.1 structured-result parsing through an injected projection, shared canonical message/run caching, invalid-contract rejection, and cross-owner cache isolation. The legacy provider and route smoke tests remain unchanged and pass.
- E9.2 shell coverage proves flag-off legacy equivalence and flag-on default
  registration over E9.1; semantic navigation/canvas/evidence regions;
  desktop-to-overlay responsive state; one open panel at a time; close-button,
  Escape, and New Research focus behavior; an immediately editable stable
  draft; Enter versus Shift+Enter; trimmed explicit-capability submission;
  pending acknowledgement; safe failure preservation; and protection against
  an older completion clearing a newer draft. Slot coverage proves E9.3–E9.5
  can compose real content without the shell inventing lifecycle/evidence
  behavior.
- E9.3 session-rail coverage proves strict lifecycle action/session/export
  identities; exact PATCH/POST/GET/DELETE routes, methods, normalized bodies,
  access tokens, and 204 handling; owner-scoped detail seeding, list
  invalidation, deletion subtree removal, malformed-response refusal, and
  signed-out zero calls. Component coverage proves pinned/active/archived and
  recency groups, entity/mode indicators, controlled current selection,
  submitted normalized server search/entity/mode filters, opaque pagination,
  real rename/pin/duplicate/JSON-export/archive/restore/confirmed-delete
  behavior, archived pin exclusion, generated DOM identity, safe failures,
  truthful unavailable state, and flag-off route compatibility.
- E9.8 boot-isolation coverage records actual request paths and proves flag-on
  v2 Ask is immediately render-ready while starting only the nonblocking
  global health check: no digest, subscription, sources/runs admin probe, or
  flat chat-history request occurs. Flag-off Ask still starts all five legacy
  dependencies; non-Ask base queries and saved-route history remain enabled;
  auth-loading to authenticated transitions and provider remounts cannot
  reactivate suppressed requests.
- E9.6 reconciliation coverage proves strict client-generated message/idempotency identity; honest saving/unsynced/synced states; idempotent begin and duplicate persisted delivery; server-first/client-first/refetch races; exact E2 persisted-turn identity; update across cached page-size variants; incomplete oldest-first cursor preservation with a deduplicated resolved overlay; cold-cache insertion; safe recoverable failure/retry; owner/session/feature isolation; crossed-result refusal; and pending visibility across provider remount. Legacy Ask component tests remain unchanged and pass.
- E10.1 run-event coverage proves a strict owner-neutral version-1 read model, safe declared lifecycle/capability values, exact run/event/sequence/execution cursor identity, persisted-anchor validation, bounded snapshot-aware pages, idle resume, owner non-disclosure, and gap/counter refusal. Full replay tests require zero-based contiguous sequence/version pairs, stable run/session/owner/policy identity, unique event IDs, matching state/run identity, monotonic state, deterministic reconstruction, and no post-terminal event while retaining E4.6 migration/lease/cancellation compatibility.
- E10.2 execution/recovery coverage proves off-loop owner-scoped persistence, lease acquisition and expired takeover, bounded driver steps, between-step renewal, duplicate terminal invocation, explicit persisted-Active interruption outcomes, strict forward-state validation before storage, process interruption recovery to terminal, stale-worker result fencing, owner non-disclosure, and durable cancellation precedence both during a driver call and in the final append race. E4.6 migration/event/replay behavior remains covered without a new migration or production adapter.
- E10.3 stream coverage proves dual-flag and authentication gating, owner-only
  run resolution through non-deleted sessions, pre-header cursor/storage
  refusal, exact `Last-Event-ID` and query-cursor resume, bounded multi-page
  replay across service restart, contiguous event/version identity,
  cross-page duplicate refusal, schema-valid heartbeat/completion/safe-error
  controls, terminal closure, disconnect termination, off-loop polling, and
  PostgreSQL exact-anchor/soft-delete behavior. No raw storage detail, worker
  payload, generated content, frontend reducer, provider, migration, or legacy
  route change is admitted.
- E10.6 capability-retry coverage proves exact official/live/General-AI/
  verification eligibility, transient terminal-state and healthy-dependency
  gates, cancellation refusal, one client-idempotent attempt, exact original
  request/input/failure-decision/artifact preservation, owner-only v2 enqueue,
  a maximum 30-second hard budget, one selected executor call, malformed and
  raised adapter safety, expired-lease takeover, stale-worker/run-version
  fencing, and unchanged source run state. Migration `0031` is exercised from
  empty and populated `0030`, with constraints, indexes, RLS/owner isolation,
  retained rollback, exact PostgreSQL replay, and no frontend, provider,
  answer-version, or legacy-route switch.
- E10.7 regeneration/refresh coverage proves strict same-source,
  fresh-official, official-plus-live, default/concise/beginner/legal-detail
  contracts; exact selected historical answer and original-turn identity;
  immediate current-head parenting; append-only pending assistant and valid
  durable-run allocation; ordered source-snapshot reuse only for same-source
  work; client request/message identities; sequential and concurrent duplicate
  suppression; concurrent linear version allocation; fixed API errors; v2 flag
  and authentication gates; owner non-disclosure and authenticated RLS.
  Migration `0032` is exercised from empty and populated `0031`; source
  message, run, orchestration state, evidence snapshot, metadata, and
  version-specific feedback remain unchanged.
- E10.9 legacy-synchronous coverage proves Completed and Partial durable run
  admission; exact run/session/owner handoff to E10.2 and the terminal artifact
  loader; E8.7 Markdown/flat-citation equivalence; unchanged model/intent/event/
  follow-up fields; positive bounded lease/step inputs; the approved 30-second
  outer maximum; deadline cancellation; internal-timeout distinction; caller-
  cancellation propagation; and fixed safe cancellation, failed/nonterminal,
  missing/crossed artifact, executor, and loader outcomes. It adds no route,
  persistence, migration, provider, frontend, flag, or serving cutover.
- E11.1 entity lookup/disambiguation coverage proves exact canonical,
  approved-alias, jurisdiction-scoped, dominant, ambiguous, and no-match
  outcomes over the existing E3.3 policy; deterministic alias ordering;
  minimized strict public contracts; fixed safe API failures; authenticated
  owner-neutral catalogue access; v2 flag isolation; canonical-ID URL routing
  and refresh/popstate restoration; visible acronym expansion; explicit
  keyboard selection; candidate re-resolution; safe no-match/degraded UI; and
  unchanged flag-off legacy Ask behavior. No entity sections, new corpus
  facts, search indexes, natural-language Decision authority, or live-source
  work are admitted.
- E11.2 entity-core-page coverage proves a matching strict backend/frontend
  version-1 projection; exact canonical entity binding; fixed Overview,
  Definition, Official Regulations, Official Documents, and Confidence order,
  titles, strategies, and card families; ready/non-content/degraded state
  truth; independent partial-page preservation; live/cross-slot/malformed
  refusal; visible knowledge modes, confidence, assumptions, and gaps;
  explicit `Not established` copy; safe identity mismatch; honest action
  availability; responsive layout; flagged E11.1 page integration; and
  unchanged legacy Ask. No API, database cache, provider, corpus fact,
  migration, timeline, stakeholder, search, or live-source behavior is added.
- E11.5 federated-search coverage proves strict backend/frontend request and
  fixed-group parity; original/applied query identity; real automatic
  spelling/acronym expansion and explicit original-query reversal;
  deterministic relevance/tie ordering; visible why-matched and minimized
  provenance; query/correction/filter-bound group cursors; canonical route
  validation; structured provenance, jurisdiction, regulator, document/entity
  type, status, stakeholder, topic, lifecycle, and date filters; entity,
  regulation, document, amendment, consultation, deadline, and previous
  research grouping; authenticated flag-off isolation; owner predicates/RLS;
  partial unavailable groups versus total safe 503; and no raw storage detail.
  PostgreSQL coverage exercises populated `0032` to `0033`, unchanged source
  rows, all six expression indexes and representative plans, production/index
  expression parity, canonical-source grouping, structured filters,
  cross-owner prior-research exclusion, and stable pagination across ties.
  Frontend coverage proves exact-token transport, stale-response refusal,
  correction reversal, all filter controls, safe pending/no-match/degraded
  states, complete ArrowUp/ArrowDown/Escape/Enter focus, canonical entity
  re-resolution, owned-session route restoration, responsive rendering, and
  unchanged flag-off legacy Ask. No live provider, manual-document engine,
  natural-language Decision authority, or default-route switch is admitted.
- E11.6 manual-document-search coverage proves matching strict backend/frontend
  contracts; canonical document and explicit registry-version identity;
  literal exact phrase and weighted lexical query behavior; title, issuer,
  document number/type, family/version, lifecycle/status, issue/effective
  ranges, and within-document filters; deterministic relevance/date/stable-ID
  order; fixed match reasons; official metadata/provenance; page/section/
  excerpt retention; safe same-origin artifact routes; and filter/as-of-bound
  opaque keysets. PostgreSQL coverage exercises populated `0033` to `0034`,
  unchanged source rows, all three indexes and representative plans, exact
  production/index predicate parity, latest and historical registry selection,
  current/superseded/draft derivation, stable pagination, and healthy no-match
  versus rolled-back storage failure. Frontend coverage proves exact-token
  transport, every accessible filter, exact phrase, stale-response refusal,
  canonical document-plus-version and version-only restoration, custom-search
  route cleanup, opaque page append, official links/excerpts, explicit
  pending/no-match/unavailable/disabled states, responsive layout, and
  unchanged flag-off legacy Browse. No live provider, semantic dependency,
  generated answer, copied corpus, natural-language Decision authority, or
  default-route switch is admitted.
- E3.1 contract coverage proves all frozen intent/subtype/entity/time/mode/capability/outcome/response/confidence/terminal taxonomies, all 15 intent precedence steps, 19 representative query labels, confidence-band boundaries, deterministic serialization, immutability, and fail-closed unknown/blank/duplicate/range validation.
- E3.2 fixed-clock coverage proves explicit date/range/year bounds, today/ISO-week/month calendar windows, rolling recent/breaking windows, latest/current/draft/consultation statuses, every frozen intent default, IANA-zone day differences, DST transitions, leap months, exact elapsed durations, and fail-closed clock/zone/expression/range validation.
- E3.6 shadow coverage proves deterministic raw-query construction of the existing Decision Record/time/plan contracts, legacy-to-canonical agreement and precedence disagreement, fixed unavailable outcomes, content-free telemetry, recorder/factory failure isolation, flag-off zero work, background flag-on execution, and exact legacy response equality. PostgreSQL coverage proves owned-run exact storage, idempotency, cross-owner non-disclosure, and non-overwriting conflict behavior without a migration.
- E3.7 calibration-contract coverage uses synthetic data only to prove exact
  schema/Decision-policy binding, immutable intent/entity/time/plan labels,
  strictly ordered thresholds, attributable non-placeholder approval,
  timezone-aware approval time, unique case/entity identities, canonical
  full-payload checksums, tamper refusal for both labels and thresholds, strict
  unknown-field rejection, deterministic file round trips, and a nonempty case
  set. No engineering fixture is treated as regulator-approved; B-013 blocks
  the permanent approved regression dataset and routing authority.
- E4.7 shadow-orchestrator coverage runs a selected three-branch fixture through
  the real bounded scheduler and proves exact ordered agreement/disagreement,
  immutable input state, deterministic serialization, literal-True
  kill-switch admission with zero validation/timing/execution/recording,
  evaluator/malformed-output/input-copy failure isolation, recorder isolation,
  task-cancellation propagation, strict/immutable contracts, and content-free
  aggregate logging. The harness adds no route, provider, persistence,
  migration, frontend, or serving behavior.
- E5.4 entity-graph coverage proves exact canonical resolution and
  resolver-approved alias expansion, the complete frozen relation taxonomy,
  declared relation/entity/direction/question scope, distinct stable edge/fact
  identity, deterministic ordering/serialization, exact E5.3 Evidence Unit
  lineage, inbound/outbound semantics, and mandatory discovery-only handling
  for unbacked and `relates_to` facts. It isolates invalid neighbors, duplicate
  edges, unknown/cross-question evidence, provider failure, malformed output,
  malformed admitted evidence, strictness, and mutation without SQL,
  migration, legacy graph, route, provider, or frontend changes.
- E5.6 Timeline Builder coverage proves timezone-aware chronological ordering,
  exact date-semantic separation, official/live provenance purity, weakest
  critical-source confidence caps, material/entity/question/section scope,
  output event-ID relationships, unresolved-link warnings, missing-date
  preservation/inferred order, discovery-only retention, evidence-cutoff
  finalization, deterministic conflict identity independent of input order,
  complete/partial/no-events states, strictness, immutability, and
  serialization without narrative, provider, persistence, migration, route,
  frontend, or serving behavior.
- E5.8 retrieval-evaluation coverage proves exact expected evidence/no-match
  labeling, standard precision@K and recall@K, per-intent case coverage,
  status-consistent non-skipped branch health, nearest-rank p95 end-to-end
  latency, deterministic reports, full-payload checksum tamper detection,
  attributable timezone-aware non-placeholder approval, exact intent-threshold
  coverage, immutable strict contracts, and draft `Unapproved` behavior.
  Synthetic tests do not constitute regulatory approval; B-014 blocks approved
  thresholds and runtime tuning.
- Pre-existing untracked identity integration tests are not evidence of Ask coverage.

Current commands:

```text
From apps/api: python -m pytest
From apps/api: python -m pytest -q backend/tests/test_chat_contract.py
From apps/api with ASK_AI_TEST_DATABASE_URL and ALLOW_ASK_AI_POSTGRES_TESTS=dedicated-test-database: python -m pytest -q backend/tests/test_ask_ai_session_migration.py
From apps/api with the same disposable PostgreSQL variables: python -m pytest -q backend/tests/test_ask_ai_repositories.py
From apps/api with the same disposable PostgreSQL variables: python -m pytest -q backend/tests/test_ask_ai_artifact_migration.py
From apps/api with the same disposable PostgreSQL variables: python -m pytest -q backend/tests/test_ask_ai_legacy_backfill.py
From apps/api with the same disposable PostgreSQL variables: python -m pytest -q backend/tests/test_ask_ai_backfill_validation.py
From apps/api with the same disposable PostgreSQL variables: python -m pytest -q backend/tests/test_ask_ai_feedback_version_lineage.py
From apps/api with the same disposable PostgreSQL variables: python -m pytest -q backend/tests/test_ask_ai_saved_items.py
From apps/api: python -m pytest -q backend/tests/test_ask_ai_evidence_api.py
From apps/api with the disposable PostgreSQL variables: python -m pytest -q backend/tests/test_ask_ai_legacy_compatibility.py
From apps/api with the same disposable PostgreSQL variables: python -m pytest -q backend/tests/test_ask_ai_session_api.py backend/tests/test_ask_ai_session_api_postgres.py
From apps/api with the same disposable PostgreSQL variables: python -m pytest -q backend/tests/test_ask_ai_message_history_api.py backend/tests/test_ask_ai_message_history_postgres.py
From apps/api with the same disposable PostgreSQL variables: python -m pytest -q backend/tests/test_ask_ai_session_api.py backend/tests/test_ask_ai_session_lifecycle_postgres.py backend/tests/test_ask_ai_session_api_postgres.py backend/tests/test_ask_ai_message_history_postgres.py
From apps/api with the same disposable PostgreSQL variables: python -m pytest -q backend/tests/test_ask_ai_session_api.py backend/tests/test_ask_ai_session_search_migration.py backend/tests/test_ask_ai_session_search_postgres.py backend/tests/test_ask_ai_session_api_postgres.py backend/tests/test_ask_ai_run_durability_migration.py
From apps/api: python -m pytest -q backend/tests/test_ask_ai_decision_contract.py
From apps/api: python -m pytest -q backend/tests/test_ask_ai_time_policy.py
From apps/api with the disposable PostgreSQL variables: python -m pytest -q backend/tests/test_ask_ai_decision_shadow.py backend/tests/test_ask_ai_decision_shadow_persistence.py backend/tests/test_chat_contract.py backend/tests/test_ask_ai_decision_contract.py backend/tests/test_ask_ai_plan_policy.py
From apps/api: python -m pytest -q backend/tests/test_ask_ai_selective_retrieval.py
From apps/api: python -m pytest -q backend/tests/test_ask_ai_retrieval_quality.py
From apps/api: python -m pytest -q backend/tests/test_ask_ai_retrieval_evaluation.py
From apps/api: python -m pytest -q backend/tests/test_ask_ai_provenance_lineage.py
From apps/api: python -m pytest -q backend/tests/test_ask_ai_claim_verification.py backend/tests/test_ask_ai_candidate_claims.py backend/tests/test_ask_ai_evidence_admission.py backend/tests/test_ask_ai_orchestration_contracts.py
From apps/api: python -m pytest -q backend/tests/test_ask_ai_version_status.py
From apps/api with disposable PostgreSQL variables: python -m pytest -q backend/tests/test_ask_ai_embedding_health.py
From apps/api: python -m pytest -q backend/tests/test_ask_ai_orchestration_contracts.py backend/tests/test_ask_ai_orchestration_state_machine.py backend/tests/test_ask_ai_orchestration_scheduler.py
From apps/api: python -m pytest -q backend/tests/test_ask_ai_orchestration_contracts.py backend/tests/test_ask_ai_orchestration_state_machine.py backend/tests/test_ask_ai_orchestration_scheduler.py backend/tests/test_ask_ai_orchestration_latency.py
From apps/api: python -m pytest -q backend/tests/test_ask_ai_orchestration_contracts.py backend/tests/test_ask_ai_orchestration_state_machine.py backend/tests/test_ask_ai_orchestration_scheduler.py backend/tests/test_ask_ai_orchestration_latency.py backend/tests/test_ask_ai_orchestration_failure_policy.py
From apps/api with the disposable PostgreSQL variables: python -m pytest -q backend/tests/test_ask_ai_run_event_contract.py backend/tests/test_ask_ai_orchestration_durability.py backend/tests/test_ask_ai_run_durability_migration.py
From apps/api with the disposable PostgreSQL variables: python -m pytest -q backend/tests/test_ask_ai_run_execution.py backend/tests/test_ask_ai_run_execution_recovery.py backend/tests/test_ask_ai_run_event_contract.py backend/tests/test_ask_ai_orchestration_durability.py backend/tests/test_ask_ai_run_durability_migration.py
From repository root: npm run test --workspace @regulatory-ai/web
From repository root: npm run test --workspace @regulatory-ai/web -- app/features/ask-ai/ModePrimitives.test.tsx
From repository root: npm run test -- --force
From repository root: npm run test
From repository root: npm run typecheck
From repository root: npm run build
```

Frontend watch mode is `npm run test:watch --workspace @regulatory-ai/web`. Full browser E2E journeys remain planned with their owning workspace/journey tasks; E0.2 provides the component DOM foundation only.

Agent OS compliance commands:

```text
python -m pytest -q tests/agent_os_compliance
python scripts/check_agent_os.py
python scripts/check_agent_os.py --run-tests --report artifacts/agent-os-compliance-report.md
```

The compliance fixture suite must cover a valid repository plus missing required documents, broken task dependencies, inconsistent current/progress state, frozen-document modification, malformed blockers, and committed-secret detection. The full command must aggregate validator findings and execute every configured repository gate before merge.

## 2. Test levels

### Unit tests

- Intent precedence; atomic decomposition with shared/local/contradictory scope; interaction/current-turn/conversation precedence and reset; time normalization; and entity resolution with exact confidence, scoped aliases, ambiguity, and high-risk gates.
- Decision-plan selection across every intent/capability role, stage/evidence gate, plan class, conditional activation, multi-part deduplication, and response blueprint.
- Orchestration transitions, dependencies, budgets, stop rules, merge.
- Retrieval thresholding, deduplication, graph identity, version status.
- Timeline date semantics.
- Knowledge-mode selection and disclosure.
- Claim support and confidence formula.
- Provenance propagation and contamination prevention.
- Card validation and follow-up selection.

### Integration tests

- PostgreSQL migrations from empty and the owning upgrade boundary, including `0025` to entity/glossary `0026`, `0026` to feedback/version-lineage `0027`, and populated `0027` to saved-item `0028`.
- RLS owner/non-owner and non-leaking authorization.
- Transaction boundaries, idempotency, pagination, backfill/resume.
- Provider adapters with deterministic mocks, timeout, rejection, malformed output.
- Run event ordering, recovery, cancellation, and replay.
- Retrieval against representative corpus/graph fixtures.

### API tests

- Legacy `/chat` and `/chat/history` compatibility.
- Session lifecycle, paginated messages, evidence, saved items, feedback.
- Structured response schema and unknown-card fallback.
- Safe error codes and correlation identity.
- Run/event/cancel/retry/regenerate/refresh contracts.
- Cursor and idempotency behavior under duplicates/concurrency.

### UI tests

- Research shell, session rail, canvas, cards, evidence panel.
- Cache reconciliation and message persistence across remount.
- Exact reopen and historical-version behavior.
- Mode banners, disclosure, confidence, degraded/empty states.
- Streaming reducer, duplicate/out-of-order events, stop/retry/refresh.
- Keyboard, focus, screen-reader labels, responsive layouts.
- No cosmetic action appears enabled without implemented behavior.

### Performance tests

- Event-loop responsiveness and database-pool pressure.
- Retrieval latency per selected branch.
- First trustworthy result, core target, soft cutoff, hard cutoff.
- Long history/session rendering and pagination.
- Run-event replay and reconnect.
- Migration/backfill lock profile and duration.

Frozen orchestration cutoffs:

| Profile            | First result |  Core | Soft | Hard |
| ------------------ | -----------: | ----: | ---: | ---: |
| Fast exact         |        1.0 s | 3.5 s |  5 s |  7 s |
| Focused grounded   |        1.5 s |   7 s | 10 s | 14 s |
| Live combined      |        1.5 s |   8 s | 12 s | 16 s |
| Deep structured    |          2 s |  12 s | 18 s | 25 s |
| Composite research |          2 s |  15 s | 22 s | 30 s |

Production percentile SLOs are blocked on B-007; hard-cutoff behavior is testable now.

### Security tests

- Authentication required.
- RLS and API ownership for every artifact.
- Session-ID enumeration does not leak existence.
- CSRF/credential behavior remains compatible with active auth mode.
- Rate limits and idempotency prevent duplicate/abusive work.
- Stored evidence and exports cannot cross tenants.
- Provider/SQL/stack/secret details never reach clients.
- Live source URL handling and allowlist policy.
- Prompt/evidence content cannot change policy, provenance, or capability authorization.



# Validation Levels

## Level 1 – Task Validation

Run only:

- lint
- typecheck
- affected unit tests
- affected contract tests
- affected integration tests

Use the narrowest possible scope.

---

## Level 2 – Epic Validation

Run:

- full backend tests
- full frontend tests
- regression
- build
- compliance framework
- reviewer

Epic validation is mandatory before an Epic may be marked complete.

---

## Level 3 – Release Validation

Run:

- complete repository validation
- production migration rehearsal
- security scan
- dependency audit
- release acceptance suite

This level executes only before production release.

## 3. Epic traceability

| Epic | Required proof                                                                                |
| ---- | --------------------------------------------------------------------------------------------- |
| E0   | Legacy contract fixtures, safe errors, flags-off equivalence, correlation and metric tests    |
| E1   | Migration, RLS, transaction, backfill, volume, exact artifact repository tests                |
| E2   | Authorization, cursors, search, lifecycle, restoration, Pydantic/Zod, legacy adapter          |
| E3   | Frozen query matrix, ambiguity, entity/time, context, deterministic plan snapshots            |
| E4   | State-machine, dependency, forbidden parallelism, fake-clock, failure, cancellation, load     |
| E5   | Relevance/dedup, branch health, graph/version/timeline, provider compatibility, evaluation    |
| E6   | Mode matrix, exact disclosure, no-match/outage, live time/source, provenance UI               |
| E7   | Evidence identity, support labels, confidence boundaries, lineage, restoration, calibration   |
| E8   | Every card schema/component, merge conflicts, partial multi-part, fallback, follow-ups        |
| E9   | Cache/remount, exact reopen, auth expiry, sessions, long history, responsive/a11y             |
| E10  | Event order/replay/resume, restart, cancel, retry, regeneration lineage, feedback             |
| E11  | Every product journey, disambiguation, search, comparison, compliance, partial entity page    |
| E12  | Unified evaluation, load/chaos/security, migration reconciliation, cohort and rollback drills |

## 4. Measurable feature acceptance

| Feature             | Acceptance measure                                                                                                                                                                                            |
| ------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Query understanding | 100% of frozen examples produce approved intent/entity/time/plan fixtures.                                                                                                                                    |
| Entity resolution   | All named fixtures resolve deterministically; material obligation/deadline/current/amendment queries do not proceed below`0.85`, and unresolved ambiguity emits exactly one focused clarification.          |
| Multi-part/context  | Every independent clause retains its own intent/scope; current-turn values beat retained conversation values for every field, closest-clause time remains local, and contradictory scopes are never averaged. |
| Decision planning   | Every frozen representative query selects the exact eligible capability roles, plan class, staged gates/fallbacks, and canonical response blueprint; General AI never races unresolved official evidence.     |
| Sessions            | 100% sampled turns reopen with identical messages, sections, sources, citations, versions, and feedback.                                                                                                      |
| Persistence         | No successful terminal turn lacks its durable linked artifacts; idempotent replay creates no duplicate.                                                                                                       |
| Retrieval health    | Every selected branch reports one typed terminal state and timing; failures never count as no-match.                                                                                                          |
| Retrieval quality   | Approved per-intent evaluation thresholds pass; values remain TODO until E5.8 regulatory review.                                                                                                              |
| Mode 1              | 100% retained material claims have verified official support.                                                                                                                                                 |
| Mode 2              | 100% healthy no-match answers use exact disclosure; 0 citation cards.                                                                                                                                         |
| Mode 3              | 100% live items have publisher/publication/retrieval identity and remain separate from official claims.                                                                                                       |
| Citation failure    | A failed claim is removed/qualified; unrelated verified sections remain.                                                                                                                                      |
| Confidence          | Exact numeric boundary fixtures match frozen weights, penalties, gates, and ceilings.                                                                                                                         |
| Streaming           | Reconnect/replay yields no duplicate or missing terminal section.                                                                                                                                             |
| Stop                | Completed sources/verified sections survive cancellation at every phase.                                                                                                                                      |
| UI actions          | 100% enabled actions perform the named persistent behavior.                                                                                                                                                   |
| Errors              | 0 raw provider, HTTP, SQL, JSON, stack, or secret details shown.                                                                                                                                              |
| Authorization       | 0 cross-user artifact reads/writes across the automated matrix.                                                                                                                                               |
| `DSM` journey     | Opens Entity Intelligence Page, not only a paragraph.                                                                                                                                                         |

## 5. Mandatory end-to-end scenarios

1. `DSM`.
2. `What is DSM?`.
3. `Latest DSM`.
4. `DSM amendment`.
5. `DSM consultation`.
6. `Compare DSM and ABT`.
7. `Who regulates DSM?`.
8. `DSM timeline`.
9. Beginner explanation.
10. Compliance question with resolved jurisdiction.
11. Compliance question with unresolved jurisdiction.
12. Healthy official no-match.
13. Official retrieval unavailable.
14. News no-match and news unavailable.
15. Parallel.ai unavailable.
16. Knowledge Graph unavailable.
17. One citation fails and all citations fail.
18. Multi-part partial success.
19. Cancellation during each orchestration phase.
20. Disconnect/resume.
21. Exact session reopen.
22. Legacy history backfill without loss.

## 6. PR test gate

Before marking a task complete:

1. narrow new tests pass;
2. affected package suite passes;
3. legacy compatibility suite passes;
4. migration/provider integration tests pass when applicable;
5. typecheck/build passes;
6. security checks pass for changed ownership/input boundaries;
7. results are appended to [06_PROGRESS.md](./06_PROGRESS.md).

Skipped or unavailable required checks create a blocker; they do not become an implicit pass.
