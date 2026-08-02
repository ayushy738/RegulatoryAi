# Ask AI Agent OS — Decisions

This is the architectural decision index extracted from the frozen specifications. New decisions are appended. A changed decision is marked **Superseded by D-xxx** rather than deleted.

## D-001 — Product is a Regulatory Intelligence Workspace

- **Decision:** Ask AI is entity- and research-first, not an undifferentiated chatbot.
- **Reason:** Users need discovery, evidence, timelines, structured compliance work, and continuity.
- **Alternatives:** Continue message-bubble chat; add isolated chatbot features.
- **Tradeoffs:** More domain objects and UI complexity; substantially better research utility and trust.
- **Affected:** Product IA, sessions, cards, entity pages, search.
- **Future impact:** New capabilities must fit research workflows, not only prose generation.
- **Source:** Product Spec sections 1–6.

## D-002 — Three explicit knowledge modes

- **Decision:** Grounded Regulatory Knowledge, General AI Knowledge, and Live Intelligence are distinct.
- **Reason:** Authority and freshness differ.
- **Alternatives:** One blended answer; refuse when official evidence is absent.
- **Tradeoffs:** More section/label complexity; truthful provenance and graceful fallback.
- **Affected:** Retrieval, composition, UI, confidence, storage.
- **Future impact:** Every new evidence source declares its provenance lane.

## D-003 — Healthy no-match is not retrieval failure

- **Decision:** Only a healthy scoped no-match permits “no official documents found.”
- **Reason:** Current empty lists hide outages and incorrectly stop synthesis.
- **Alternatives:** Treat all empty results equally.
- **Tradeoffs:** Typed branch health is required; failures become explainable.
- **Affected:** Retriever, Orchestrator, errors, Mode 2.
- **Future impact:** Every capability must return a terminal state.

## D-004 — Decision Engine owns routing

- **Decision:** Fixed policy resolves intent/entity/time, capabilities, modes, response strategy, and confidence gates.
- **Reason:** Same inputs must produce explainable decisions.
- **Alternatives:** Let a model or route handler choose tools ad hoc.
- **Tradeoffs:** Policy/version maintenance; deterministic regression testing.
- **Affected:** Query understanding, planning, observability.
- **Future impact:** Capability additions require policy admission.

## D-005 — Orchestrator is below the Decision Engine

- **Decision:** The Orchestrator executes an approved plan; capabilities cannot change policy or publish directly.
- **Reason:** Prevent hidden scope expansion and provenance promotion.
- **Alternatives:** Autonomous all-tools agent; monolithic route.
- **Tradeoffs:** Typed artifacts and state machine required.
- **Affected:** All AI capabilities and run lifecycle.
- **Future impact:** Extensions plug into declared artifact boundaries.

## D-006 — Retrieval is selective and independently parallel

- **Decision:** Run only intent-eligible branches; independent evidence branches may execute in parallel after scope resolution.
- **Reason:** Current all-branch behavior wastes latency and hides branch health.
- **Alternatives:** Always run all retrieval.
- **Tradeoffs:** Better latency; plan quality becomes important.
- **Affected:** Regulatory Retriever, graph, news, timeline.
- **Future impact:** Every capability declares dependencies and stopping rules.

## D-007 — General AI is a knowledge mode, not an official source

- **Decision:** Parallel.ai may provide Mode 2 general knowledge but creates no synthetic source/citation.
- **Reason:** Orientation must not imitate regulatory evidence.
- **Alternatives:** Attach loosely related citations; refuse to answer.
- **Tradeoffs:** Medium/Low confidence and explicit disclosure.
- **Affected:** General AI, storage, composer, UI.
- **Future impact:** Hidden provider web research is inadmissible without retained live provenance.

## D-008 — Live intelligence is explicit and separate

- **Decision:** Live source links, timestamps, and publishers are separate from the internal corpus.
- **Reason:** News does not itself establish legal force.
- **Alternatives:** Blend news and official citations.
- **Tradeoffs:** Duplicate event reconciliation is required.
- **Affected:** News Retriever, sections, timeline, source cards.
- **Future impact:** Source policy/licensing approval is a rollout gate.

## D-009 — Citation verification is claim-scoped

- **Decision:** Every material Mode 1 claim is linked to and supported by official evidence; failure affects the claim, not the turn.
- **Reason:** Current citation presence is not support.
- **Alternatives:** Source list append; block the whole response.
- **Tradeoffs:** Added latency and verifier calibration.
- **Affected:** Composer, verifier, claims, citations, confidence.
- **Future impact:** Evidence-only fallback is preferred over unverified grounded prose.

## D-010 — Confidence is evidence-derived

- **Decision:** Authority 25%, relevance 15%, coverage 20%, agreement 15%, freshness 15%, scope 10%, with frozen penalties/gates/ceilings.
- **Reason:** Model confidence and fluency do not establish truth.
- **Alternatives:** Model self-score; binary cited/not-cited.
- **Tradeoffs:** More metadata and calibration.
- **Affected:** Claims, sections, UI, evaluation.
- **Future impact:** Transformations cannot exceed weakest critical input.

## D-011 — Session is the durable aggregate

- **Decision:** Messages, sections, citations, sources, news, timeline, feedback, versions, title, scope, and view state belong to a persistent research workspace.
- **Reason:** Current flat history loses context and artifacts.
- **Alternatives:** Flat message log; client-only state.
- **Tradeoffs:** Additive schema and migration/backfill complexity.
- **Affected:** Database, APIs, frontend state.
- **Future impact:** Historical output is immutable; refresh creates a new version.

## D-012 — Structured sections/cards replace monolithic prose

- **Decision:** Response blueprint follows intent; sections are provenance-pure and merge deterministically.
- **Reason:** Regulatory tasks require tables, timelines, obligations, deadlines, sources, and coverage.
- **Alternatives:** Markdown-only response.
- **Tradeoffs:** Versioned schemas and more UI components.
- **Affected:** Composer, API, storage, frontend.
- **Future impact:** Unknown future cards must degrade gracefully.

## D-013 — Capability failures degrade independently

- **Decision:** Failure boundary is capability × atomic question × section × provenance lane.
- **Reason:** One outage must not erase useful work.
- **Alternatives:** Request-level failure.
- **Tradeoffs:** More terminal states and section-level notices.
- **Affected:** Orchestrator, streaming, UI, confidence.
- **Future impact:** Retries are capability-specific.

## D-014 — Latency uses bounded product profiles

- **Decision:** Plans have first-result, core, soft, hard, and reserved-verification budgets.
- **Reason:** Useful early certainty is preferable to opaque waiting.
- **Alternatives:** One global provider timeout.
- **Tradeoffs:** Some optional sections complete degraded.
- **Affected:** Orchestrator, streaming, performance tests.
- **Future impact:** Production percentile SLOs require later approval without changing cutoff semantics.

## D-015 — Additive compatibility rollout

- **Decision:** Expand/backfill/validate/contract, dual write/read, side-by-side APIs, off-by-default flags, cohort rollout.
- **Reason:** Preserve current users and rollback without data loss.
- **Alternatives:** Big-bang schema/API replacement.
- **Tradeoffs:** Temporary adapters and duplicate paths.
- **Affected:** Migrations, APIs, frontend, operations.
- **Future impact:** Destructive cleanup waits until the compatibility window ends.

## D-016 — Async-safe v2 execution

- **Decision:** V2 uses nonblocking database/provider access, bounded concurrency, and shared provider clients; legacy sync adapters are isolated.
- **Reason:** Current sync work blocks the async route and limits concurrency.
- **Alternatives:** Continue per-request thread pools and blocking clients.
- **Tradeoffs:** Runtime/repository migration effort.
- **Affected:** Orchestrator, retrieval, provider clients, load tests.
- **Future impact:** New capabilities must declare resource and budget behavior.

## D-017 — Exact history and recent context

- **Decision:** Reopen exact historical state; AI context uses newest relevant active-session turns in chronological order.
- **Reason:** Current cache/history loses searches and selects the wrong messages.
- **Alternatives:** Global fixed window; silent refresh mutation.
- **Tradeoffs:** Versioned persistence and cursoring.
- **Affected:** Sessions, context selection, frontend cache.
- **Future impact:** Cross-session facts are never implicit context.

## D-018 — Frozen specifications require explicit contradiction handling

- **Decision:** Implementation PRs do not edit frozen specs; contradictions are blocked and separately approved.
- **Reason:** Prevent accidental product redesign.
- **Alternatives:** Resolve ad hoc in code.
- **Tradeoffs:** Affected work may pause.
- **Affected:** All epics and Agent OS maintenance.
- **Future impact:** Approved changes create new policy/spec versions and decision entries.

## D-019 — Agent OS compliance is policy-driven and enforced in CI

- **Decision:** Store compliance policy in `.agent-os-compliance.toml`; run independent validators through one collect-all engine locally and in a dedicated required CI workflow.
- **Reason:** Autonomous sessions need deterministic, reviewable enforcement of frozen specifications, task state, documentation synchronization, security hygiene, and repository validation.
- **Alternatives:** Reviewer-only checklists; one monolithic validation script; embedding policy separately in each validator.
- **Tradeoffs:** Policy and parsers require maintenance when document conventions change, and heuristic checks complement rather than replace specialist security tooling.
- **Affected:** `.codex` operating guidance, Agent OS documents, CI workflows, repository scripts, and engineering handoff practice.
- **Future impact:** New compliance rules plug in as validators and configuration entries without changing existing validation contracts; architecture changes must update Decisions in the same iteration.

## D-020 — Normalized time windows are visible and half-open

- **Decision:** Calendar expressions use local IANA-zone boundaries and half-open `[start_at, end_at)` windows; `this week` uses the ISO Monday-start local week. Rolling 90-day, 30-day, and 72-hour windows subtract elapsed time in UTC, then render in the user's zone.
- **Reason:** Reproducible boundaries avoid end-of-day precision loss, duplicate adjacent-window records, and DST-dependent elapsed durations. The frozen specification requires visible, policy-versioned absolute ranges but does not define a week-start convention.
- **Alternatives:** Inclusive `23:59:59` endpoints; server-local time; Sunday-start weeks; wall-clock subtraction across DST.
- **Tradeoffs:** Consumers must honor the exclusive end and ISO-week assumption; the visible normalized range makes correction possible.
- **Affected:** E3 time interpretation, later retrieval filters, interpretation chips, evaluation fixtures.
- **Future impact:** Changing week start, recent duration, breaking duration, or boundary inclusion requires a new decision-policy version.
- **Source:** Decision Engine sections 7.2–7.5 and 24.3.

## D-021 — Entity aliases and glossary terms use an additive curated catalogue

- **Decision:** Add migration `0026` with stable canonical entity records, separately provenance-bearing aliases and glossary terms, normalized jurisdiction-scoped lookup keys, and authenticated read-only access. Preserve optional linkage to the legacy regulatory graph instead of overloading its free-form metadata. Permit the same normalized alias to map to different entities, while rejecting duplicate mappings for one entity and jurisdiction.
- **Reason:** The legacy graph stores canonical names and a metadata object but cannot enforce alias/glossary provenance, normalized scoped uniqueness, or represent reviewed ambiguity as a first-class contract. Migration `0025` is already the immutable E1.6 validation boundary, so the planned entity expansion must use the next append-only version.
- **Alternatives:** Store aliases inside graph JSON metadata; mutate `0025`; force every alias to be globally unique; hard-code production catalogue data in resolver code.
- **Tradeoffs:** Curated data requires an ingestion/review path later, and catalogue-to-graph linkage is optional until graph enrichment work. Multiple matches must be resolved deterministically rather than prevented by the database.
- **Affected:** E3 entity resolution, later entity index/graph retrieval, migrations, evaluation fixtures, and authenticated catalogue readers.
- **Future impact:** Catalogue writes remain privileged and provenance-bearing; resolver policy changes require a new policy version, and destructive graph consolidation remains outside the compatibility window.
- **Source:** Implementation Plan E3 database changes; Decision Engine sections 6.1–6.5.

## D-022 — Selective official retrieval follows approved plan ownership

- **Decision:** Derive v2 official retrieval work only from approved E3.5 atomic-question capability roles. Internal document search selects vector and keyword; Knowledge Graph selects graph; document metadata or version lineage selects family/version; an official-source summarization question additionally selects summary. Deduplicate branch and question ownership in stable enum order, report nonselected branches as Skipped/Not run, and keep General AI outside official retrieval.
- **Reason:** The frozen Decision Engine makes capability eligibility authoritative and requires selected/skipped work to be observable. A second retrieval intent heuristic could silently expand work, race General AI against official evidence, or make multi-part execution nondeterministic.
- **Alternatives:** Re-run legacy intent detection inside retrieval; map every selected capability to all five branches; omit nonselected outcomes; treat General AI as summary retrieval.
- **Tradeoffs:** The adapter remains isolated until production orchestration wiring, and exact glossary/entity-index/live capabilities still require their own later adapters rather than being approximated by current database branches.
- **Affected:** E5 selective retrieval, later Orchestrator adapters, branch diagnostics, multi-part execution, and retrieval tests.
- **Future impact:** New retrieval branches require an explicit capability-owner mapping and policy version; skipped work must never invoke providers, and legacy all-branch behavior remains behind the compatibility path until cutover.
- **Source:** Decision Engine sections 2.4, 8.2, 10.1–10.3, and 15; Implementation Plan E5 backend changes and acceptance criteria.

## D-023 — Retrieval thresholds are explicit inputs and passage dedup is narrow

- **Decision:** E5.3 requires one finite default relevance floor for every retrieval branch plus optional atomic-intent overrides; it embeds no production cutoff values before E5.8 approval. A score equal to its floor is eligible. Only vector and keyword hits sharing an exact document/version/chunk identity merge into one Evidence Unit; other rows, especially graph facts without durable fact identity, remain distinct.
- **Reason:** Frozen specifications require thresholding and one vector/keyword evidence unit but assign measured tuning to E5.8. Guessing defaults would silently change policy, while text-based graph deduplication could erase distinct legal facts.
- **Alternatives:** Hard-code uncalibrated values; accept all positive scores; reuse the legacy composite rank; deduplicate every source by document/text; defer all admission to E5.8.
- **Tradeoffs:** V2 quality admission cannot run without an explicit policy, and non-vector/keyword cleanup waits for stable source identities. It may retain harmless duplicate graph rows.
- **Affected:** E5 retrieval admission, evidence construction, no-match semantics, E5.8 calibration, Orchestrator adapters, and diagnostics.
- **Future impact:** Production floors require a separately versioned approved policy and regression report. New deduplication rules require stable identity and proof that distinct facts survive.
- **Source:** Decision Engine sections 2.1–2.3, 8.2, 15, 17, and 24.3; Implementation Plan E5 acceptance criteria and E5.3/E5.8 review units.

## D-024 — Legal status is resolved from effective-dated official snapshots

- **Decision:** Resolve version/current status only from immutable official records and effective-dated lineage relationships with an explicit coverage state. Separate publication availability from legal effectiveness; apply direct status and supersession/repeal events chronologically; preserve historical state; return connected active amendment sets; and permit current claims only for a complete, noncontradictory Validated current result.
- **Reason:** The existing registry contains useful dates and lineage but no universal trustworthy legal-status column. Inferring status from titles or treating the newest publication as the only current law would create unsupported legal claims.
- **Alternatives:** Add an unpopulated status column; parse titles for draft/repealed terms; equate latest publication with current; collapse partial lineage to no-match; overwrite historical versions.
- **Tradeoffs:** Callers must supply official status snapshots and coverage, and status remains isolated until a production adapter exists. Complete snapshots may return multiple connected in-force instruments rather than one synthetic consolidated version.
- **Affected:** E5 version evidence, current/as-of retrieval, later confidence/admission, Orchestrator adapters, and diagnostics.
- **Future impact:** Database adapters must preserve official source/time identity and coverage. Any status inference or migration requires separate evidence, tests, and policy versioning.
- **Source:** Decision Engine sections 6.1, 7.4–7.5, 9.1, 10.1, 13.3, and 15–17; Implementation Plan E5.5 and current/legal-status acceptance criteria.

## D-025 — Vector no-match requires compatible physical index identity

- **Decision:** Before typed vector retrieval, compare the effective configured embedding provider/model/dimension with grouped indexed identities and the physical PostgreSQL `vector(N)` dimension. Only Ready and compatible Healthy empty states make no-match trustworthy; partial coverage and provider/model/dimension, metadata, or startup failures produce distinct safe non-no-match outcomes.
- **Reason:** Provider/model filters can return zero rows against a populated incompatible index, falsely appearing to be healthy absence. Configuration text alone also cannot prove the physical vector column accepts the query dimension.
- **Alternatives:** Trust settings only; treat every zero-row query as no-match; rely on SQL exceptions; check only dimensions; require destructive reindexing.
- **Tradeoffs:** Typed vector retrieval performs a health inventory query before work, and partial indexes withhold trustworthy no-match. Legacy public methods still collapse failures to empty lists for compatibility.
- **Affected:** E5 vector retrieval, startup/admin health, failure diagnostics, E5.9 configuration enforcement, and later evaluation.
- **Future impact:** New embedding providers/models must expose effective identity and pass physical-index compatibility before v2 admission; reindexing remains a separate explicit operation.
- **Source:** Implementation Plan E5.7/E5.9 and embedding compatibility acceptance criteria; Decision Engine sections 2.3, 15, and 20.

## D-026 — V2 provider declarations are enforced before construction

- **Decision:** Admit v2 provider construction only for the existing Supabase retrieval/vector implementation and existing offline, OpenAI-compatible, or Parallel embedding implementations at physical dimension 1536. Require the declared offline model to equal `deterministic-hash-v1`, require nonblank credentials for remote embeddings, compare both implementation attributes and health-reported embedding identity with the declaration, and require Ready or compatible Healthy empty startup compatibility. Every refusal returns a fixed safe state/code and no bundle.
- **Reason:** Existing settings accepted `vector_provider=memory` even though the factory always returned Supabase, and the default offline model label did not equal the model actually used. Recording either declaration without enforcement would make audit and health data untrustworthy.
- **Alternatives:** Silently fall back to Supabase; rewrite legacy factories; infer the actual model only after execution; accept any dimension; add a memory provider; expose constructor exceptions.
- **Tradeoffs:** The legacy default offline model must be explicitly corrected before a v2 bundle can start, and v2 construction performs compatibility health validation. Legacy paths remain unchanged and can still use their existing factories.
- **Affected:** E5 provider startup/health, v2 retrieval dependency wiring, later capability adapters, audit identity, and deployment configuration.
- **Future impact:** New providers, models, dimensions, or vector stores require an explicit supported-matrix change plus identity, credential, startup-health, and compatibility proof; reindexing remains separate.
- **Source:** Implementation Plan E5.9 and provider-configuration acceptance criteria; Decision D-025.

## D-027 — Knowledge mode is a section-scoped provenance contract

- **Decision:** Select knowledge mode per section from terminal official/live evidence outcomes, not from prose or provider choice. Bind Mode 1 to internal official provenance and claim-linked citations, Mode 2 to General AI provenance with no source identity, and Mode 3 to attributed live provenance. Healthy official no-match alone authorizes the exact no-documents disclosure; outage uses distinct copy and a Low ceiling. Confidence, legal-force rules, prohibited claims, pending lanes, and live failure notices remain explicit and mode-scoped.
- **Reason:** A fluent composer or shared source list could otherwise merge official, General AI, and live claims, silently convert outage into absence, attach unrelated citations, or apply one confidence label to heterogeneous evidence.
- **Alternatives:** Assign one mode per response; infer mode from citations after generation; let providers label their own output; treat no-match and outage alike; forbid multiple same-mode sections.
- **Tradeoffs:** Mode decisions are more explicit and must be made for each section. Multi-part work may contain repeated Mode 1 sections, but every section key is unique and each section remains in one provenance lane.
- **Affected:** E6 General AI/live capabilities, E7 confidence and citation admission, E8 composition/merge contracts, E9 mode UI, audit/restoration, and later rollout.
- **Future impact:** New sources or modes must declare a provenance lane, source/citation treatment, legal-force boundary, disclosures, confidence ceiling, and terminal evidence trigger before serving.
- **Source:** Product Specification section 8; Decision Engine sections 9, 16, and 17.5; Orchestrator sections 7.5–7.9 and 13–15; Implementation Plan E6.1.

## D-028 — General AI output is untrusted data inside a policy-owned Mode 2 lane

- **Decision:** Execute v2 General AI only for E6.1-assigned Mode 2 sections through one bounded Parallel call. Treat the provider response as untrusted, versioned JSON; require exact ordered section identity and empty citation/source/applicability fields; screen citation-shaped, official-absence, and binding-applicability text; and attach disclosure, confidence ceiling, provenance, and prohibitions exclusively from validated policy. Failure returns only a fixed safe state/code and no unit.
- **Reason:** A model can echo prompt injection, invent source-shaped text, misstate retrieval outage as no documents, or label its own confidence. Letting provider prose choose provenance or disclosure would defeat the knowledge-mode boundary.
- **Alternatives:** Reuse legacy grounded chat directly; accept free-form Markdown; let the model emit citations/disclosures; retry until parse succeeds; support every configured LLM provider silently.
- **Tradeoffs:** Strict output can reject otherwise useful prose, and v2 requires explicit Parallel configuration/model. The provider makes only one attempt; malformed content becomes a structured fallback rather than an automatic regeneration.
- **Affected:** E6 Mode 2 capability, Orchestrator General Knowledge artifacts, later composition/degradation, audit/provider identity, and rollout configuration.
- **Future impact:** Any additional General AI provider or richer payload must preserve the same section identity, no-source lane, policy-owned disclosure/ceiling, bounded execution, and contamination tests.
- **Source:** Product Specification sections 8.2 and 9; Decision Engine sections 9, 16.2, and 17.5; Orchestrator sections 7.5, 10.7, 13.2, 14.7, and 17.3; Implementation Plan E6.2.

## D-029 — Official evidence identity is admitted before claim support is judged

- **Decision:** E7.1 admits official evidence only by joining the exact canonical E5.3 Evidence Unit, Orchestrator artifact envelope, and, when legal status/time is requested, the recomputed E5.5 status request/decision. Require one inspectable internal-regulatory source, a positive chunk and locator, exact excerpt/source/scope/relevance identity, direct pending provenance, ancestry, and a satisfied or partial retrieval terminal state. Reject each invalid unit independently with a fixed safe code; do not label semantic claim support at this boundary.
- **Reason:** A valid source URL or high retrieval score does not prove that a passage supports a later claim. Conversely, one malformed candidate must not erase neighboring official evidence that remains inspectable and in scope. Separating evidence integrity from semantic verification preserves useful partial results without allowing stale, crossed-lane, or mismatched evidence into composition.
- **Alternatives:** Let the composer trust retrieval hits directly; treat source identity as claim support; accept displayed status without recomputing lineage; reject the entire evidence set when one unit is malformed; defer source/scope/status checks to the model verifier.
- **Tradeoffs:** Callers must retain the canonical quality unit and exact status evidence alongside the artifact envelope, and official evidence without a positive chunk is withheld. The gate is intentionally strict and isolated until later capability wiring exists.
- **Affected:** E7 evidence admission and Candidate Claim references, later Citation Verifier input, Mode 1 composition, provenance audit, confidence inputs, and restoration.
- **Future impact:** Adapters must preserve the three linked contracts without rewriting identity. E7.2 may reference only admitted artifact IDs, while E7.3 remains solely responsible for supported/partial/unsupported/contradictory/unverifiable claim labels.
- **Source:** Orchestrator sections 5.2, 7.5, 10.2, 11.1, 13.1, 14.1, and 17.2; Implementation Plan E7.1; Decisions D-023, D-024, and D-027.

## D-030 — Candidate Claim references are proposed support, not verification

- **Decision:** E7.2 accepts a composer-produced Candidate Claim only when it is material, pending verification, assigned to one approved atomic question and one section, grounded in the internal-regulatory lane, and references one or more E7.1-admitted official Evidence Units in that exact narrowed scope. The final Response Composer transformation must name those support IDs in the same order. Invalid claims are excluded independently with fixed safe codes, but E7.2 never assigns a semantic support result.
- **Reason:** A composer must identify which evidence it relied on before verification, but allowing that reference to imply support would collapse the required Citation Verifier boundary. Single-question/section scope and admitted-evidence identity also prevent a citation retrieved for one part of a multi-part response from silently supporting another.
- **Alternatives:** Let claims carry arbitrary source IDs; treat artifact ancestry as sufficient support mapping; verify claims inside the composer; accept nonmaterial claims into the verifier queue; reject the entire batch for one malformed claim.
- **Tradeoffs:** Composer adapters must emit explicit materiality, narrowed scope, ordered support references, and a matching transformation step. Semantically unsupported prose can still pass E7.2 and must be rejected or narrowed by E7.3.
- **Affected:** Response Composer output, Citation Verifier input, multi-part claim isolation, evidence/citation lineage, later confidence and persistence, and claim-level degradation.
- **Future impact:** E7.3 consumes only accepted pending claims and owns all supported/partial/unsupported/contradictory/unverifiable labels. E7.5 may strengthen end-to-end source lineage without changing the support-reference boundary.
- **Source:** Orchestrator sections 5.1–5.2, 10.8–10.9, 13.1, 14.6, and 17.1; Implementation Plan E7.2; Decisions D-027 and D-029.

## D-031 — Confidence score and final policy label remain separate

- **Decision:** E7.4 calculates every material claim from the exact six frozen dimensions and weights, applies all relevant additive penalties, and bounds the numeric score to 0–100. It derives a numerical band, then separately applies mandatory High gates, hard-Unknown conditions, the E6 section-policy ceiling, and the weakest critical-input ceiling to produce the final label. Sections and overall results use the exact frozen 70/30 aggregations and cannot exceed their weakest critical labels; strict compliance, deadline, current-status, and version-comparison work also cannot exceed the lowest material-claim label.
- **Reason:** A fluent or numerically strong result may still be legally unsafe because its jurisdiction is unresolved, current status could not be checked, its mode is capped, or a required input is weaker. Collapsing score and label would either hide these gates or falsify the underlying evidence arithmetic.
- **Alternatives:** Let capabilities emit final labels; equate confidence with model self-assessment; convert mode ceilings into arbitrary score reductions; average all claims/sections without lowest-input shares; use one response-wide label for mixed modes.
- **Tradeoffs:** Stored/displayed confidence must retain both score and final label plus applied conditions. A claim can legitimately show a high numeric score but an Unknown or capped final label, which downstream UI must explain rather than simplify away.
- **Affected:** Decision Engine confidence, E6 mode ceilings, claim/section/overall completion metadata, strict-intent behavior, later Confidence UI, persistence, evaluation, and rollout.
- **Future impact:** E7.3 and later capabilities contribute validated dimensions/conditions only. Calibration can change upstream values after approval, but changing weights, penalties, gates, thresholds, or aggregation requires a new confidence policy version and boundary fixtures.
- **Source:** Decision Engine sections 17.1–17.7; Orchestrator sections 14.1–14.8; Implementation Plan E7.4; Decisions D-027 and D-030.

## D-032 — Card transport is versioned before card semantics

- **Decision:** E8.1 freezes one Pydantic/Zod structured-response transport with ordered provenance-pure sections and generic card envelopes covering all twelve product card identities. Shared metadata includes strategy, state, mode/lane, confidence, claim/source references, assumptions, gaps, actions, and JSON payload. Known card types require exact identity; unknown future lower-snake-case types are retained only through explicit fallback rendering. A compatibility-summary string is carried but not derived.
- **Reason:** Implementing every card payload and component in one change would couple schema evolution, merge behavior, rendering, and legacy compatibility. A shared envelope lets backend and frontend agree on identity and safety before later tasks add card-specific fields or components.
- **Alternatives:** Use arbitrary model-shaped JSON; create one endpoint/table per card; reject every future card type; silently render unknown types as known cards; derive the legacy reply during contract definition; let disabled actions carry live targets.
- **Tradeoffs:** Known-card payload remains generic until E8.2–E8.4, so E8.1 alone cannot render product cards. Unknown payload is preserved for safe fallback, and downstream code must still refuse unsupported semantics.
- **Affected:** Response Composer output, E8 card schemas/merge/rendering, E9 structured canvas, exact restoration, saved cards, compatibility rendering, and schema-version migration.
- **Future impact:** E8.2–E8.4 may add discriminated payload validation without changing envelope identity. E8.7 owns deterministic compatibility rendering, and any breaking envelope change requires a new response schema version plus shared fixtures.
- **Source:** Product Specification sections 11.8 and 12.1–12.13; Implementation Plan E8.1 and Epic E8 acceptance criteria; Decisions D-027 and D-031.

## D-033 — Research Workspace cache identity is owner and artifact scoped

- **Decision:** E9.1 uses one `ask-ai-v2` TanStack Query hierarchy scoped first by authenticated owner, then by stable session/message/run identity and response version. Opaque cursors remain infinite-query page parameters rather than cache-key fragments. Message evidence and its selected run share one canonical cache record. The feature provider carries only auth, feature enablement, and a read client; it does not copy server data into local state. E8.1 structured responses use an exact session/message/run/version key and an injected read projection until a concrete backend projection exists.
- **Reason:** Resource IDs alone do not prevent one browser query cache from reusing data across account changes, while cursor-keyed pages fragment one logical list. Duplicating message/run data in provider state would recreate the race E9 exists to remove. Inventing an endpoint for the E8.1 transport would exceed E9.1.
- **Alternatives:** Reuse legacy `chat` keys; key by bearer token; store server responses in React context state; create one query per cursor; duplicate evidence and run queries; add a speculative structured-response endpoint.
- **Tradeoffs:** Owner IDs remain in in-memory query keys and prior-owner records may remain cached but are unreachable through another owner's key. Structured-response reads stay disabled unless an explicit projection is supplied. Later mutations must update these canonical keys rather than a second message store.
- **Affected:** E9 Research Workspace reads/reconciliation/restoration, auth transitions, E2 session/turn/evidence APIs, E8 structured results, and later streaming cache updates.
- **Future impact:** E9.6, E9.7, and E10.4 must preserve the hierarchy and exact identities. A real structured-response endpoint may replace the injected loader without changing consumer keys. Cross-owner invalidation may be added as defense in depth but cannot collapse owner identity.
- **Source:** Implementation Plan E9 goal, frontend changes, E9.1 review unit, and risk register; Architecture frontend target; E2 and E8.1 contracts.

## D-034 — Optimistic turns are typed query-cache overlays until exact persistence

- **Decision:** E9.6 creates one strict user-anchored optimistic turn with client-generated public-message and idempotency UUIDs, then stores saving/unsynced/synced reconciliation metadata only in the owner/session-scoped TanStack Query hierarchy. Repeated begin/reconcile operations are idempotent for the same stable identity and fail closed on crossed content or IDs. Persisted turns replace or append only where the loaded chronological page range can contain them. When an oldest-first page still has a continuation cursor, the exact persisted result remains a temporary typed overlay so cursor order is not falsified; it collapses after the server page contains that turn.
- **Reason:** Appending a newest result to an incomplete oldest-first page would corrupt visible chronology and cursor semantics, while removing the optimistic record before a matching read would recreate disappearing searches. Local React state would also reintroduce the original server-state race.
- **Alternatives:** Copy messages into provider state; key retries by content; append to every last loaded page regardless of cursor; discard failed drafts; add a speculative backend mutation/idempotency column; overwrite the entire infinite query after each response.
- **Tradeoffs:** A resolved overlay may temporarily retain a second in-cache copy of one persisted turn when the corresponding server range is not loaded. Stable-ID deduplication exposes it once, and later server confirmation removes the overlay payload. Durable cross-process idempotency still belongs to the future v2 mutation contract.
- **Affected:** E9 optimistic creation/reconciliation/restoration, long-session pagination, auth remounts, E10 mutation/stream merges, and session-message transport.
- **Future impact:** A concrete v2 message mutation must accept and persist the client identity/idempotency key and return the exact E2 turn. E10 stream updates and E9 exact restoration must call the same reconciliation boundary rather than creating parallel message state.
- **Source:** Implementation Plan E9 frontend changes, E9.6 review unit, and section 5.2; Product Specification failure matrix; Audit sections 7, 11, and 12.2–12.7; Decision D-033.

## D-035 — Durable event cursors bind persisted event identity

- **Decision:** E10.1 exposes a version-1 owner-neutral run-event read model and opaque resume cursor over exact run ID, public event ID, zero-based sequence, and one-based execution version. Repository paging first captures the owned run's execution/sequence boundary, validates any cursor against its persisted event anchor, and returns a bounded contiguous prefix plus a cursor for the last delivered event. Full reconstruction starts at sequence zero/version one, requires stable run/session/owner/policy and unique event identity, and refuses gaps, crossed state identity, regression, or any event after a terminal boundary. Raw owner/session fields, lease payloads, and undeclared capability/lifecycle values do not enter the read model.
- **Reason:** A sequence number alone can be guessed, crossed between runs, or point at changed/corrupt history. Unbounded event reads cannot safely support recovery or later reconnect behavior, and exposing the E4.6 storage payload would leak worker-only details. Binding the cursor to a persisted immutable event makes retries deterministic while owner filtering remains authoritative.
- **Alternatives:** Reuse the raw durability row as the public contract; use sequence-only cursors; replay arbitrary event tails without a trusted prior state; load every event on each poll; add an SSE route or new migration inside E10.1; duplicate E4.6 sequence/terminal constraints.
- **Tradeoffs:** The cursor is opaque and integrity-checked against storage rather than cryptographically signed; a caller can resume only from an event that still exists in the exact owned run. The read model carries the typed orchestration state for truthful progress but intentionally omits raw payload fields. Later stream transport must preserve these identities and cannot reinterpret event ordering.
- **Affected:** E10 recovery, event streaming/reconnect, frontend stream merge, durable cancellation, exact restoration, observability, and owner authorization.
- **Future impact:** E10.2 consumes the bounded replay contract for recovery. E10.3 may wrap it in a transport cursor without weakening anchor validation, and E10.4 must deduplicate by stable run/event/sequence identity. Any breaking cursor or read shape requires a new schema version.
- **Source:** Product Specification sections 11.1–11.8; Orchestrator sections 18.1–18.3 and 24; Implementation Plan E10.1, risk mitigations, and testing strategy; Decisions D-015 and D-023.

## D-036 — Interrupted capability execution becomes an explicit terminal outcome

- **Decision:** E10.2 recovers a persisted Active capability by finishing that exact request as `Unavailable` with fixed code `CAPABILITY_EXECUTION_INTERRUPTED` before any new driver step. A durable coordinator owns one expiring lease, executes bounded TTL-scoped injected steps, renews between accepted steps, validates forward orchestration progress both before and inside repository persistence, and atomically appends each accepted state. A driver exception leaves the lease/event history intact for expiry-based takeover. After every driver step and on append/version conflict, durable cancellation is re-read and wins over the unpersisted result when the same lease still owns the run.
- **Reason:** After a process failure, an in-memory provider call has no trustworthy completion result. Re-queuing it silently could duplicate external effects, while retaining Active forever prevents recovery. Treating it as an explicit safe terminal capability outcome preserves the exact request and lets declared failure/fallback policy decide later behavior. Rechecking storage at the append boundary prevents both stale workers and narrow cancellation races from overwriting newer durable intent.
- **Alternatives:** Reset Active to Queued; assume the provider call failed without recording an outcome; rerun the capability automatically; persist only the final run; release every lease in a broad exception handler; let a late result beat a concurrent cancellation; execute SQLAlchemy sessions on the async event loop.
- **Tradeoffs:** Interrupted capability work is not automatically retried in E10.2; E10.6 owns explicit capability-specific retry. A controlled driver failure waits for lease expiry just like a process crash, favoring fencing correctness over immediate retry. The coordinator is an injected execution boundary, not a production worker or route.
- **Affected:** Durable orchestration execution, capability failure/fallback decisions, cancellation, restart recovery, run-event replay, later retry/streaming, observability, and worker concurrency.
- **Future impact:** Production drivers must advance immutable Orchestration State and remain within the configured lease TTL. E10.3 may stream only committed events; E10.5 uses the same cancellation precedence; E10.6 creates an explicit retry execution rather than mutating the interrupted outcome.
- **Source:** Product Specification sections 11.1–11.8; Orchestrator sections 12.5–12.6, 13, 18, and 24; Implementation Plan E10.2 and risk/rollback/testing strategy; Decisions D-019, D-023, and D-035.

## D-037 — Session duplication copies research context, not unsupported output

- **Decision:** E2.3 treats `POST /chat/sessions/{id}/duplicate` as creation of a fresh active draft with a new session identity and copied event, entity, topic, and scope. It copies no messages, runs, sources, claims, citations, feedback, or saved items, and resets knowledge-mode summary and freshness. Rename/pin/archive/restore/soft-delete mutate the original owned session under row lock with idempotent timestamp semantics. Export, rather than duplicate, is the exact-content operation and uses one repeatable-read snapshot composed only from public session/turn/saved-item contracts.
- **Reason:** Copying grounded prose without its entire immutable evidence/version/provenance graph would create apparently authoritative content with broken lineage. Deep-cloning run/event/artifact identities would also fabricate execution history and regeneration relationships not specified by the frozen lifecycle task. A context duplicate is useful for branching research while requiring fresh retrieval.
- **Alternatives:** Copy only chat text; deep-clone all run/event/artifact rows; share mutable artifact identities between sessions; copy knowledge/freshness summaries without evidence; make duplicate an alias to export/import; omit duplicate until a full branch model exists.
- **Tradeoffs:** The duplicate opens with no prior turns or saved artifacts, so it is a scoped starting point rather than a historical fork. Users retain exact content through the original session and versioned export. A future explicit research-branch feature would require its own lineage contract and migration.
- **Affected:** Session lifecycle API, session rail actions, context selection, exact restoration, export/import planning, provenance, saved items, and later workspace branching.
- **Future impact:** E9.3 may label the action as duplicating research context and must not imply copied answers. Any future content fork must preserve exact run/message/artifact/version identity through a separately approved branch lineage rather than changing E2.3 semantics silently.
- **Source:** Product Specification sections 5.1–5.5; Implementation Plan Epic E2 API/acceptance and E2.3 review unit; Decisions D-005, D-009, D-015, and D-033.

## D-038 — Session search uses indexed evidence lanes and filter-bound rank cursors

- **Decision:** E2.4 searches persisted session metadata, message content, and immutable source/document snapshot lanes with PostgreSQL `simple` full-text expressions. A session-metadata match ranks `500`, a message match `400`, and a source/document match `300`; the maximum lane rank wins, followed by descending session update time and UUID. The opaque version-2 cursor records that rank/tie position and a SHA-256 identity of normalized `q`, knowledge-mode, entity, archived, and pinned filters. Version-1 cursors remain valid only for the original unfiltered active-session list. Exact mode filtering uses completed persisted sections, exact entity filtering uses a whitespace-normalized case-folded primary entity, and deleted sessions never enter results.
- **Reason:** Ranking by a small declared lane hierarchy is deterministic across PostgreSQL versions and avoids exposing unstable floating-point `ts_rank` values in cursors. Binding the cursor to filters prevents accidental continuation into a different result set. Expression indexes avoid a generated-column rewrite or a second mutable search projection while retaining the immutable content/source snapshots already required for restoration.
- **Alternatives:** Floating-point rank cursors; one denormalized session-search table maintained by triggers; stored generated vectors on populated tables; unindexed `ILIKE` joins; semantic/vector search; accepting a cursor under changed filters; replacing the existing list route with a separate endpoint.
- **Tradeoffs:** Full-text matching is lexical rather than fuzzy or semantic, and entity filtering is exact against the session's resolved primary-entity value. Ranking intentionally prefers where a match occurred over term frequency. Index creation still needs production-volume lock/timing rehearsal under E1.7 before rollout. The authenticated role cannot read legacy `chat_messages` directly; the server repository therefore retains an explicit owner predicate in addition to the table's existing RLS/least-privilege posture.
- **Affected:** Session list/search API, PostgreSQL migration `0030`, cursor compatibility, E9 Research Workspace cache keys, E9.3 session rail, E11.5 federated search, migration rehearsal, authorization, and exact restoration.
- **Future impact:** E9.3 must use this filter-bound query contract rather than local cosmetic filtering. E11.5 may federate entity/document results but must not silently change E2.4 relevance/cursor semantics. Fuzzy correction or semantic search requires a separately versioned contract and measured indexes.
- **Source:** Product Specification sections 13.2–13.5; Implementation Plan Epic E2 acceptance/testing and E2.4 review unit; Decisions D-005, D-009, D-015, D-033, and D-037.

## D-039 — Shadow decisions are post-response comparisons and never create run identity

- **Decision:** E3.6 keeps legacy intent/retrieval/model output authoritative. When the existing Decision Engine flag is enabled and legacy retrieval returns its typed intent, the route schedules a deterministic lexical shadow adapter as a post-response background task. It builds the existing immutable Decision Record/time/plan contracts, maps the legacy intent taxonomy to a canonical intent, and records a versioned agreement, disagreement, or fixed unavailable comparison. Default telemetry contains only correlation ID, schema/policy versions, fixed intent/strategy values, duration, outcome, and safe code. Full Decision Records may be persisted only through an explicit row-locked existing-run/owner operation that is idempotent for the exact record and refuses every different nonempty record; the legacy route has no run identity and therefore never persists or fabricates one.
- **Reason:** E3.1–E3.5 intentionally stopped at structured deterministic policies, while legacy retrieval owns the only current raw-query detector and flat legacy messages have no valid v2 run. A shadow adapter is necessary to collect precedence disagreements without serving them, but inventing a session/run or attaching the result to a guessed turn would corrupt lineage. Running after response and catching every evaluator/recorder/factory failure makes shadow observation removable without changing the user path.
- **Alternatives:** Switch routing when the flag is enabled; overwrite legacy intent before retrieval; create a shadow run for every legacy flat message; log the full question/Decision Record; add a new shadow table/migration; execute inline before response; persist over an existing nonempty decision; wait for the complete v2 serving path before measuring any disagreements.
- **Tradeoffs:** The lexical adapter is intentionally a shadow candidate, not an approved calibrated classifier, and currently produces no catalogue-backed entity decision. Background work is process-local and comparison telemetry is not an exact-content store. Full records remain available only when another valid v2 path supplies owned run identity. E3.7 must review labels/thresholds before any routing authority is considered.
- **Affected:** Legacy `/chat` background behavior, Decision Engine rollout flag, metrics/privacy, E3.7 calibration, run Decision Record persistence, later admin evaluation, and serving cutover.
- **Future impact:** E3.7 may approve or reject lexical labels but cannot silently make shadow output authoritative. A later v2 message/run path may call the owned persistence seam with exact identity. Any admin preview must use a separate authorized API and must not expose raw telemetry records.
- **Source:** Decision Engine specification sections 2–7 and 18–23; Implementation Plan Epic E3 backend/risk/rollback/testing/acceptance and E3.6 review unit; Decisions D-004, D-005, D-009, D-015, and D-025.

## D-040 — Regulatory calibration requires attributable immutable approval

- **Decision:** E3.7 accepts Decision calibration evidence only through a strict versioned artifact containing locked intent/high-risk-entity thresholds, labeled query expectations, regulatory rationale, the exact Decision policy version, and attributable approval provenance. One canonical SHA-256 digest binds all reviewed thresholds, policy identities, and cases. Approval requires an identified reviewer and role, a timezone-aware timestamp, and a non-placeholder approval reference. Existing engineering taxonomy/plan fixtures and synthetic contract tests are not approval evidence and cannot make shadow decisions authoritative.
- **Reason:** The repository contains deterministic engineering fixtures but no regulatory reviewer identity, date, reference, or approved threshold record. Inferring approval would fabricate governance and permit reviewed labels or thresholds to drift after sign-off. Hashing only cases would leave thresholds mutable, so the approval digest covers the complete reviewed payload.
- **Alternatives:** Treat existing engineering fixtures as approved; let AI Engineering self-approve labels; record an untraceable `approved: true`; hash cases but not thresholds; change runtime routing while approval is unavailable; omit the contract until a reviewer appears.
- **Tradeoffs:** E3.7 remains blocked on B-013 and the current lexical Decision adapter remains shadow-only. A reviewer must provide the complete artifact rather than an informal label list. In return, later regression evidence is attributable, fail-closed, policy-bound, and tamper-evident without a runtime policy change.
- **Affected:** E3.7, Decision routing authority, calibration fixtures, shadow disagreement review, E12.1 evaluation, E12.6 GA, and regulatory governance.
- **Future impact:** When B-013 is resolved, engineering validates and commits the approved artifact and permanent regression cases. Any approved threshold change that alters runtime policy requires a new Decision policy version rather than editing the v1 artifact.
- **Source:** Implementation Plan E3.7 and Epic E3 acceptance/testing; Decision Engine sections 5.4, 6.5, 22, and 23; Master Loop blocker/frozen-policy rules; Decision D-039.

## D-041 — Shadow orchestration executes injected fixtures, never serving work

- **Decision:** E4.7 is an isolated async shadow harness over the existing bounded scheduler. A versioned fixture expectation declares the initial/final phase, optional run terminal state, and exact ordered safe node outcomes. Only literal `True` opens an early kill switch; enabled execution revalidates the immutable state, expectation, and Scheduler Report, then records deterministic agreement, disagreement, or a fixed unavailable result. Default telemetry exposes only correlation/policy, phase/terminal values, duration, safe code, and terminal-state counts. The full report remains internal to the execution return and is never passed to the logging recorder or serving path.
- **Reason:** Production capability adapters and v2 serving identity do not yet exist, so wiring shadow execution to legacy traffic would either fabricate a run/plan or execute unsupported provider work. Selected fixtures still exercise the real scheduler, concurrency/failure contracts, and exact comparison boundary. An early strict kill switch proves removal without invoking validators, clocks, adapters, or telemetry.
- **Alternatives:** Invoke the Orchestrator from legacy `/chat`; log full fixture/state/report payloads; accept truthy configuration values; swallow cancellation as unavailable; create a second shadow scheduler; persist synthetic fixture runs; defer all shadow execution until production adapters exist.
- **Tradeoffs:** E4.7 validates selected fixture execution rather than live production traffic, and comparisons are held by an injected recorder rather than a new database table. Later traffic shadowing must supply valid owned run/plan identity and production adapters, but can reuse the same safe comparison contract without changing legacy output.
- **Affected:** E4 scheduler/lifecycle/failure/durability validation, shadow rollout, privacy telemetry, later internal cohort evaluation, and Orchestrator kill-switch behavior.
- **Future impact:** A production shadow driver may provide real owned state and adapters, but cannot weaken strict kill-switch admission, input/report revalidation, content-free default logging, cancellation propagation, or non-authoritative serving isolation.
- **Source:** Implementation Plan E4.7 and Epic E4 acceptance/testing; Orchestrator sections 2, 4–5, 8, 12–18, and 24; Decisions D-019, D-023, D-036, and D-039.

## D-042 — Graph relationships retain edge identity and cannot self-ground

- **Decision:** E5.4 consumes one exact E3.3 canonical resolution and only its approved query expansion, then asks an injected provider for declared frozen relationship types within the approved jurisdiction/question/section scope. Each distinct provider edge keeps a deterministic fact identity and becomes an existing Structured Fact payload only after boundary revalidation. Backing support must reference exact E5.3 Canonical Evidence Units in the same atomic-question scope. Facts without backing evidence and all `relates_to` facts are retained only as discovery material and can never establish legal applicability.
- **Reason:** The legacy graph search flattens heterogeneous rows into hit text, which loses durable relation identity and makes an unbacked edge look similar to official evidence. Deduplicating by endpoints/text would also erase independently extracted facts and their source lineage. Binding the typed graph output to admitted evidence preserves discovery value without manufacturing legal proof.
- **Alternatives:** Treat graph hits as citations; deduplicate equal subject/relation/object triples; accept raw question text as entity scope; infer aliases inside the graph provider; discard every unbacked edge; add SQL/index changes before a provider implementation exists; alter the legacy graph branch.
- **Tradeoffs:** E5.4 is an isolated provider contract rather than a production SQL adapter, so no graph index migration is warranted yet. Unbacked edges remain visible only to downstream discovery workflows, and consumers must carry full evidence lineage for grounded use.
- **Affected:** Knowledge Graph capability input/output, E5.6 Timeline Builder, E7 provenance/admission, structured entity/compliance/deadline/stakeholder outputs, and later provider/evaluation work.
- **Future impact:** A production graph adapter must implement this exact canonical/relation scope and preserve edge/evidence identity. Any indexes are added only with its measured query plan. E5.6 may consume Structured Facts but cannot upgrade discovery-only facts.
- **Source:** Decision Engine sections 6.4–6.5 and 9–10; Orchestrator sections 4.2, 5.1–5.2, 8.4, 10.3, and 17; Implementation Plan E5.4; Decisions D-021, D-027, and D-029.

## D-043 — Timeline conflicts remain events, not averaged dates

- **Decision:** E5.6 transforms scoped material dated inputs into provenance-pure Timeline Events only after the evidence-input cutoff. Issue/publication, effective, deadline, consultation, event, validity, version, and retrieval semantics remain distinct. Same-key/same-semantic differing dates become a deterministic conflict set retaining all events; dates are never averaged or selected implicitly. Missing dates remain absent and receive inferred-order warnings. Each event keeps source IDs, input ancestry, discovery-only status, and a date confidence no higher than its weakest critical source.
- **Reason:** Choosing one conflicting date or treating different semantics as comparable would manufacture chronology and legal meaning. Combining official and live provenance would hide authority differences, while dropping undated material could conceal evidence gaps.
- **Alternatives:** Average conflicts; prefer official dates silently; merge equal labels across provenance lanes; invent dates from order; discard undated inputs; let Timeline Builder write narrative; finalize while evidence remains open.
- **Tradeoffs:** Partial timelines may contain parallel conflicting events and undated events at the end, requiring downstream cards/composition to explain gaps. The builder is deliberately a pure transformation rather than a provider or narrative generator.
- **Affected:** E5.6, timeline/amendment/deadline/current-development sections, confidence/conflict penalties, E8.4 cards, E11 entity timelines, and E5.8 evaluation.
- **Future impact:** Downstream composition must retain conflict groups, warnings, semantics, source lanes, and discovery-only status. Resolving a conflict requires new admissible evidence, never presentation preference.
- **Source:** Orchestrator sections 7.5–7.6, 8.4, 10.5, 12, 14, and 17; Decision Engine sections 7 and 15–17; Implementation Plan E5.6; Decisions D-031 and D-042.

## D-044 — Retrieval measurement is not regulatory approval

- **Decision:** E5.8 evaluates a strict versioned, per-intent labeled dataset with standard precision@K, recall@K, case coverage, branch-health rate, and nearest-rank p95 end-to-end latency. Healthy expected no-match cases score only when no evidence is returned, skipped branches do not dilute health, and a complete canonical SHA-256 digest binds policy/schema versions, K, every label and observation, and every threshold. Draft datasets always produce `Unapproved`; only an attributable regulator-approved artifact with identified reviewer/role, timezone-aware timestamp, non-placeholder reference, and matching digest may produce Pass or Fail. No evaluation result silently changes E5.3 runtime floors.
- **Reason:** Existing Step 26 results are lexical proxies over an engineering benchmark and explicitly require manual regulatory review. Treating those proxies or synthetic fixtures as gold labels would fabricate approval and could tune serving against the wrong evidence semantics. Separating measurement from approval preserves reproducibility while failing governance closed.
- **Alternatives:** Promote legacy proxy metrics; let engineering self-label and self-approve; embed guessed production thresholds; report draft threshold success as Pass; measure only branch latency; include skipped branches as healthy; tune E5.3 automatically from a report.
- **Tradeoffs:** E5.8 remains blocked on B-014 even though its deterministic harness is complete. Regulatory reviewers must provide the full attributable artifact. In return, later quality regressions are reproducible, tamper-evident, per-intent, and incapable of covert runtime-policy changes.
- **Affected:** E5.8, E5.3 retrieval floors, retrieval evaluation artifacts, E12.1 unified evaluation, E12.6 GA, and regulatory governance.
- **Future impact:** When B-014 is resolved, engineering validates and commits the approved dataset/report plus permanent threshold tests. Runtime floor changes require an explicit reviewed policy change and cannot be inferred from evaluation output alone.
- **Source:** Implementation Plan E5.8 and Epic E5 acceptance/testing; Decision Engine sections 15, 17, and 22–23; Master Loop blocker/frozen-policy rules; Decisions D-029 and D-043.

## D-045 — Provenance is a transitive DAG invariant

- **Decision:** E7.5 traces only strict versioned factual artifacts in one deterministic acyclic graph. Official roots must enter through exact E7.1-admitted evidence; graph facts and timeline events use concrete E5.4/E5.6 adapters; claims and sections declare one local kind-authorized transformation. Every derived scope must remain within each parent, every declared input lane must match actual parents, and the output lane must equal the weakest contributing lane. The trace retains the complete transitive origin-source union, exposes as citable only sources in the output lane, preserves stronger origins as ancestry, and treats General AI as source-less. Discovery-only ancestry has zero authority, cannot be cleared, and cannot support a claim or section. Verification changes support status, never origin.
- **Reason:** Local artifact validation cannot detect hidden parents, cross-artifact cycles, dropped source identities, scope broadening, or a later merge that upgrades graph discovery or mixed provenance. A graph-wide invariant is required to prove that composition and placement cannot manufacture authority.
- **Alternatives:** Trust each artifact independently; treat ancestry as an unvalidated string list; cite every mixed-origin source; select the strongest lane; discard stronger origins after weakest-lane downgrade; permit embedded multi-step transformation histories; allow graph labels to establish authority.
- **Tradeoffs:** Every traceable derived artifact must name one local transformation and all of its direct inputs, and mixed-origin content loses higher-lane citation treatment while retaining full audit ancestry. This is intentionally stricter than permissive composition and may require claims to be decomposed.
- **Affected:** E5.4, E5.6, E7.1–E7.5, section composition/merge, citation eligibility, confidence provenance inputs, E8 structured responses, and E12.1 provenance evaluation.
- **Future impact:** Persistence and serving must store or reconstruct the exact trace without changing parent/source identities. Future provenance classes require explicit authority and admission rules plus complete pairwise contamination tests.
- **Source:** Orchestrator sections 7.6–7.9, 15.1–15.6, and 16–17; Decision Engine sections 24.3 and 25; Implementation Plan E7.5 and Epic E7 acceptance/testing; Decisions D-027, D-031, D-042, and D-043.

## D-046 — Mode UI is a strict presentation of policy state

- **Decision:** E6.5 exposes isolated typed UI primitives whose mode, trigger, confidence ceiling, source count, timestamps, and state determine fixed visible presentation. Healthy official no-match and official retrieval outage use different exact E6.1 disclosures; both General AI fallback states require a manual official-document search action. Official and live bands require positive source counts. Live source cards require publisher/type identity, timezone-aware publication and retrieval times, a safe HTTP(S) target, and an explicit non-legal-force notice. Pending, empty, and degraded states are semantic status regions, and mode/state text remains present independently of color. The primitives are not imported by the default Ask route.
- **Reason:** A visually plausible banner can still misrepresent an outage as absence, present zero sources as grounded, attach unsafe or unattributed live material, or rely on color that assistive technology cannot interpret. Presentation must fail closed on the same distinctions as backend policy.
- **Alternatives:** Accept arbitrary disclosure strings; infer mode from card color; allow zero-source official/live bands; accept caller-formatted naive timestamps or arbitrary URLs; put fallback actions in later route code; mount primitives immediately in the legacy Ask view.
- **Tradeoffs:** Callers must supply complete truthful metadata and cannot render incomplete official/live bands. The isolated module does not yet compose full cards or activate the v2 workspace, but it is testable without risking legacy behavior.
- **Affected:** E6.5, E6.1 policy parity, E8/E9 structured workspace presentation, accessibility, live attribution, failure states, and rollout isolation.
- **Future impact:** E9 composition may mount these primitives only from validated structured section state. E6.6 owns capability retry behavior; later cards cannot weaken exact copy, attribution, timestamp, safe-target, or non-color guarantees.
- **Source:** Product Specification sections 6.3, 8.1–8.5, 9.1–9.2, and 11.2–11.4; Decision Engine sections 5, 14, and 16; Implementation Plan E6.5; Decisions D-024 and D-027.

## D-047 — Confidence UI may explain policy output but never upgrade it

- **Decision:** E7.8 is an isolated presentation boundary over E7.4/E8.1 snapshots. A supplied policy label may be lower than the numeric score band because of gates, ceilings, or weakest-input caps, but it may never be higher; General AI may never render High, and overall confidence may not exceed the weakest critical section. Official/live evidence counts must agree with the provenance modes displayed. Mixed-mode sections remain separate, Unknown and Limited states are explicit and non-color-dependent, and explanations use categorized evidence/coverage/freshness/scope/capability reasons rather than model introspection. The accessible collapsed panel discloses that confidence is not a probability of legal correctness. No default-route integration occurs.
- **Rationale:** A confidence score without its policy caps, evidence coverage, and provenance boundaries can overstate trust. Keeping the display strict and section-scoped preserves E7.4 arithmetic, E7.5 lineage, and the Product Specification's mixed-mode transparency.
- **Alternatives rejected:** deriving a label only from the numeric score; flattening mixed sections into one badge; allowing source counts detached from displayed modes; exposing free-form model reasoning; using color as the only status signal; mounting incomplete v2 UI.
- **Affected:** E7.8, E7.4, E7.5, E8 structured responses, E9 workspace rendering, accessibility, provenance presentation, and rollout isolation.
- **Source:** Product Specification sections 8.1–8.5, 9.1–9.2, and 11.2–11.4; Decision Engine sections 17 and 24; Implementation Plan E7.8; Decisions D-010, D-027, D-031, D-045, and D-046.

## D-048 — Core cards bind typed payload semantics to the E8.1 envelope

- **Decision:** E8.2 keeps the E8.1 envelope/schema version and adds strict version-1 payload contracts only for Answer Summary, Definition, Official Source, and Confidence/Coverage. Every structured missing text/date uses an explicit `established` or `not_established` state, rendered as `Not established`; generic JSON is rejected for these four types while later E8.3/E8.4 payloads remain unchanged. Each core card independently revalidates mode/provenance, reference counts, confidence non-elevation, and General AI source/High exclusions. Grounded definitions require official definition/source identity. An Official Source card owns exactly one official source and explicit Open, Save, and Compare descriptors; its visible Partial state must match missing date/status metadata. UI actions marked available are hidden unless a real handler is injected, while disabled actions expose a generic accessible unavailability explanation.
- **Rationale:** The transport envelope alone cannot ensure the product-required fields, truthful absence semantics, or action behavior. Adding discriminated payload validation without changing envelope identity preserves stored response compatibility while preventing model-shaped JSON, provenance drift, and cosmetic controls.
- **Alternatives rejected:** adding a new response envelope version for nonbreaking card semantics; leaving core payloads as arbitrary JSON; duplicating source authority outside envelope references; representing missing fields with null or omission alone; navigating directly to unvalidated action targets; enabling actions without behavior.
- **Affected:** E8.2, E8.1 shared fixtures, E7.8 confidence presentation, E9.4 structured canvas, E11 entity/core journeys, response restoration, accessibility, and compatibility rendering.
- **Source:** Product Specification sections 1.4–1.5, 8.1–8.5, 9.1–9.3, 11.4, and 12.1–12.3/12.12–12.13; Implementation Plan E8.1–E8.2 and Epic E8 acceptance/testing; Decisions D-027, D-031, D-032, D-045, and D-047.

## D-049 — The Research shell owns layout and accepts only explicit capabilities

- **Decision:** E9.2 registers the responsive three-pane Research shell as the
  default v2 UI only behind the existing strict UI flag and mounts it inside
  the E9.1 provider. The shell owns semantic navigation/canvas/evidence
  regions, mutually exclusive responsive panels, and local composer
  presentation. It does not own server state or call legacy workspace actions.
  Submission is available only through an injected typed capability; without
  one the composer remains editable, its draft survives rerenders, and the
  action is truthfully disabled. Successful submission clears only the exact
  acknowledged draft, so a newer draft cannot be erased by an older promise.
- **Rationale:** The target workspace needs a stable layout boundary before
  session, canvas, and evidence behavior can be composed. Reusing the legacy
  global submit path would produce invisible legacy results and duplicate the
  E9.1 canonical data boundary. Capability injection preserves a reviewable
  shell while making unavailable behavior explicit.
- **Alternatives rejected:** keep requiring a caller-supplied workspace;
  enable the v2 flag by default; call the legacy global Ask handler; start
  network work directly in the shell; clear the draft optimistically; render
  cosmetic lifecycle/evidence actions.
- **Affected:** E9.2, Ask route rollout, E9.1 provider ownership, E9.3–E9.5
  region composition, E9.8 boot isolation, accessibility, and legacy
  compatibility.
- **Source:** Product Specification sections 7, 10, and 13; Implementation
  Plan Epic E9 and E9.2; Decisions D-001, D-002, D-033, and D-035.

## D-050 — Session lifecycle mutations revalidate canonical owner caches

- **Decision:** E9.3 consumes the existing E2.3 lifecycle and E2.4 search
  contracts through the E9.1 client/provider. Request actions are strictly
  typed and use the provider's exact token. Successful session-returning
  actions seed the exact owner/session detail record and invalidate every
  owner-scoped session projection; confirmed deletion removes the session
  detail subtree before the same invalidation. Export is validated and
  downloaded as JSON without entering query state. The workspace stores only
  the selected session ID locally, never a second session object.
- **Rationale:** Search relevance, archived/pinned membership, and filter-bound
  cursors are server-owned and cannot be updated safely by cosmetic client
  filtering. Owner-root invalidation preserves E2.4 semantics while exact
  detail seeding supports immediate identity continuity. Stable-ID-only view
  state keeps TanStack Query canonical.
- **Alternatives rejected:** maintain a local session array; optimistically
  splice filter/search pages; infer search relevance in the browser; reuse
  legacy chat state; expose raw action errors; treat export as a cache record;
  enable pinning for archived sessions; delete without explicit confirmation.
- **Affected:** E9.1, E9.3, E2.3, E2.4, session-list cache identity,
  exact restoration, lifecycle accessibility, and flag rollback.
- **Source:** Product Specification sections 4.2, 5.1–5.3, and 13;
  Implementation Plan Epic E9 and E9.3; Decisions D-015, D-033, D-038, and
  D-049.

## D-051 — V2 Ask disables legacy boot queries at their shared owner

- **Decision:** E9.8 derives `isolatedV2Ask` inside `WorkspaceProvider` from
  the normalized Ask route and the same strict UI flag used by `AskRoute`.
  Hooks retain stable invocation order, but digest, subscription, sources/runs
  admin probes, and flat chat-history queries receive disabled conditions in
  that state. Digest loading cannot enter global bootstrapping, and manual
  legacy base reload is a no-op. The global health query remains enabled but
  does not gate rendering. Flag-off Ask, saved history, and non-Ask route
  enablement remain unchanged.
- **Rationale:** The shared controller must still serve every legacy route, so
  removing hooks or splitting the entire application provider would create a
  broad regression surface. Query-level enablement at the state owner prevents
  network work and waiting without violating React hook order or duplicating
  route state.
- **Alternatives rejected:** conditionally render hooks; remove the shared
  provider from `/ask`; disable base data on every Ask route; suppress the
  global health check; rely only on cache hits; filter requests inside the
  transport; change legacy view data ownership.
- **Affected:** E9.8, `WorkspaceProvider`, v2 Ask boot latency, legacy Ask
  rollback, saved history, admin probing, authentication transitions, and
  non-Ask route compatibility.
- **Source:** Product Specification sections 3.2, 4.2, and 13; Implementation
  Plan Epic E9 acceptance/testing and E9.8; Decisions D-001, D-002, D-033,
  D-049, and D-050.

## D-052 — Stream transport resumes only from persisted durable anchors

- **Decision:** E10.3 exposes a server-sent event stream only when both v2 API
  and streaming flags are enabled. Authentication resolves the run through its
  non-deleted owner session before any response stream begins. Standard
  `Last-Event-ID` and an optional query cursor are the same opaque E10.1
  persisted-event anchor; conflicting cursors fail. Preparation primes one
  bounded page so ownership, cursor, and initial storage failures return safe
  HTTP responses. Subsequent database reads run off-loop in repeatable-read
  transactions and pair each event page with the terminal snapshot boundary.
  The transport emits exact persisted event records in contiguous sequence,
  detects duplicates or drift across pages, and uses strict versioned control
  frames only for heartbeat, terminal completion, or one fixed safe error.
- **Rationale:** A process-local offset or synthesized progress event could be
  lost at restart, duplicate canonical state after reconnect, or expose a
  stream before authorization is known. Persisted anchors make reconnect
  deterministic, while priming and owner resolution preserve HTTP
  non-disclosure and repeatable-read batches prevent an inconsistent terminal
  close.
- **Alternatives rejected:** in-memory offsets; unbounded replay; accepting
  different header/query cursors; starting the stream before owner/cursor
  validation; emitting raw storage errors; serializing worker payloads;
  blocking SQL on the event loop; deriving completion only from an empty page;
  implementing the frontend reducer in the transport task.
- **Affected:** E10.1, E10.2, E10.3, E10.4, run-event API authorization,
  reconnect/restart semantics, streaming rollout flags, and legacy rollback.
- **Source:** Product Specification sections 11.3–11.8; Implementation Plan
  E10.3 and Epic E10 acceptance/testing; Decisions D-008, D-014, D-016, and
  D-035.

## D-053 — Capability retry is a separate durable execution

- **Decision:** E10.6 never reopens or replaces a terminal E10.1 event history.
  Migration `0031` stores one owner-scoped retry execution for the exact
  run/node/original-request tuple. The client-generated UUID is both the
  mutation idempotency key and new capability request ID. A strict plan freezes
  the E4.5 failure decision, source execution version, original inputs, and
  every preserved artifact identity. Only timed-out, unavailable, or invalid
  official retrieval, live retrieval, General AI, and citation-verification
  nodes are eligible; healthy, partial, no-match, permanent, cancelled, or
  dependency-failed work is not. Enqueue is owner-only behind the v2 API flag.
  An injected executor leases the attempt for at most the frozen 30-second hard
  budget, supports expired-lease takeover with the same request identity, and
  refuses cancellation or run-version drift before invocation and completion.
- **Rationale:** Resetting a terminal node to queued would contradict E10.1
  replay monotonicity and could erase the explicit interrupted outcome required
  by D-036. A separate attempt preserves audit history, enables deterministic
  restart/idempotency, and guarantees that healthy nodes and ready core
  sections are not delayed or rerun.
- **Alternatives rejected:** mutate the original node/result; reopen a terminal
  run; retry the whole run; allow multiple retry UUIDs; use a process-local
  attempt map; reuse the old provider request ID; accept client-selected
  budgets; expose raw adapter errors; automatically repeat General AI; merge
  retry output into an old answer version.
- **Affected:** E4.5, E10.1, E10.2, E10.6, E10.7, migration `0031`, retry API
  authorization, worker recovery, exact restoration, and legacy rollback.
- **Source:** Product Specification sections 5.6, 9.1–9.4, and 11.7–11.8;
  Orchestrator sections 12.6, 13.4, and 18; Implementation Plan E10.6 and Epic
  E10 acceptance/testing; Decisions D-014, D-016, D-035, and D-036.

## D-054 — Response mutations append from the current head while retaining the selected source

- **Decision:** E10.7 stores each regenerate/refresh request as immutable
  owner-scoped lineage among a selected historical answer, the current branch
  head, and one new pending assistant/run version. The client request UUID is
  global mutation idempotency; the client also supplies the stable target
  assistant UUID. A per-turn database lock allocates `head + 1`, so selecting
  an older answer records it as the source while the new assistant's parent is
  still the immediate prior version required by E1.4. Same-source work freezes
  and reuses every ordered source snapshot ID. Official refresh and live
  inclusion reuse none and explicitly request fresh official or
  official-plus-live retrieval. Style is an orthogonal strict modifier. The
  target run starts with a valid new Research Request state and the mutation
  plan remains its source-policy authority.
- **Rationale:** Treating the selected answer as both source and structural
  parent would either branch outside the existing linear restoration contract
  or overwrite/renumber newer versions. Separating semantic source from
  immediate parent preserves the user's exact selection, deterministic reopen,
  concurrent allocation, and all historical evidence/feedback.
- **Alternatives rejected:** overwrite the selected assistant/run; mutate its
  source rows; copy refreshed results into an old version; derive target
  version from the selected version; use process-local idempotency; accept
  server-generated message identity only; silently reuse sources during
  refresh; place source/style policy in unvalidated free text; expose owner or
  internal bigint identities.
- **Affected:** E1.4, E2.2, E2.5, E9.6, E10.2, E10.7, migration `0032`,
  regeneration/refresh APIs, exact restoration, RLS, and legacy rollback.
- **Source:** Product Specification sections 5.2, 5.5–5.7, and 11.7–11.8;
  Implementation Plan E10.7 and Epic E10 acceptance/testing; Decisions D-014,
  D-016, D-033, D-036, and D-053.

## D-055 — Entity navigation is canonical URL state, not client-side authority

- **Decision:** E11.1 exposes entity lookup through the existing
  authenticated, off-by-default v2 API and reuses the E3.3 resolver unchanged.
  A resolved response includes a route derived only from the canonical
  catalogue ID. The flagged Research Workspace stores that identity in the
  `entity` URL parameter and restores it by asking the server to resolve the
  canonical ID again. An ambiguous response remains non-navigable until the
  user chooses a keyboard-operable candidate; that choice also re-resolves the
  canonical ID instead of treating client data as authoritative. The public
  response excludes provenance internals and exposes only the stable identity,
  aliases, jurisdiction, class, reason, and policy confidence needed by the
  header/selector.
- **Rationale:** Canonical URL identity makes refresh, back/forward navigation,
  and shared workspace state deterministic without copying catalogue state
  into the browser. Re-resolution preserves server-side alias/jurisdiction
  policy and prevents the UI from silently converting an ambiguous candidate
  into a higher-confidence result.
- **Alternatives rejected:** route on the raw mention; encode the canonical
  name as identity; navigate directly from a candidate payload; increase
  confidence after a click; keep selection only in component state; expose
  database provenance or graph metadata; add catalogue facts in the client;
  mount entity behavior on the flag-off legacy Ask route.
- **Affected:** E3.3, E9.1, E9.2, E11.1, E11.2, entity lookup API, Research
  Workspace routing/restoration, and legacy rollback.
- **Source:** Product Specification sections 3.1 and 6.1–6.4; Decision Engine
  entity-resolution policy; Implementation Plan E11.1 and Epic E11
  acceptance/testing; Decisions D-002, D-008, D-014, and D-018.

## D-056 — Entity core pages are fixed projections over canonical artifacts

- **Decision:** E11.2 defines one canonical five-slot projection—Overview,
  Definition, Official Regulations, Official Documents, and Confidence—over
  the existing strict E8.1 response and E8.2 core-card artifacts. Each slot
  fixes its key, order, title, strategy, and permitted card type. Ready slots
  require content; empty, omitted, clarification, and cancelled slots require
  no cards; degraded slots may retain verified cards. The projection binds one
  canonical E11.1 entity ID, rejects live provenance in this task, and renders
  every slot independently with mode, state, assumptions, and gaps.
- **Rationale:** Reusing canonical response artifacts preserves provenance and
  confidence rules while preventing a second entity-page truth store.
  Explicit fixed slots make partial pages deterministic and keep one missing
  or degraded capability from hiding healthy evidence.
- **Alternatives rejected:** duplicate page-content tables; synthesize fields
  from the entity catalogue; infer slot identity from card titles; accept
  arbitrary card types; omit unavailable required slots; flatten provenance;
  show enabled actions without handlers; admit live results before E11.9;
  render a mismatched entity projection.
- **Affected:** E8.1, E8.2, E9.2, E11.1, E11.2, E11.3, E11.4, E11.10,
  structured-response restoration, and legacy rollback.
- **Source:** Product Specification sections 4.2, 6.2–6.5, 10, and 12;
  Implementation Plan E11.2 and Epic E11 acceptance/testing; Decisions D-003,
  D-004, D-006, D-008, D-019, and D-055.

## D-057 — Federated search is a read-through with explicit correction and degradation state

- **Decision:** E11.5 reads the existing entity/alias, official
  document/version/deadline, and owner-filtered session/message stores through
  one strict grouped contract; it creates no search projection table.
  Deterministic fixed relevance tiers plus descending persisted time and
  stable identity define ordering and group-bound keysets. Automatic
  spelling/acronym correction adds the preserved original terms to the
  corrected lexical query, reports the applied interpretation, and binds
  cursors to an explicit `auto` or `original` correction mode so one-click
  reversal performs a genuinely different search. Per-group savepoints expose
  an isolated failure as `unavailable`; only all-requested-group failure
  becomes a safe 503. Previous Research always carries an owner predicate and
  its owned provenance, while all other results carry the internal-corpus
  lane. Migration `0033` adds matching expression indexes only.
- **Rationale:** A read-through prevents a second mutable truth store and
  retains E2.4 ownership semantics. Explicit correction mode prevents the UI
  from claiming an interpretation that retrieval did not use. Independent
  failure state preserves useful results without misreporting an outage as a
  defensible no-match.
- **Alternatives rejected:** duplicate denormalized search rows; floating
  relevance cursors; unbound base64 offsets; replace rather than expand the
  original query; cosmetic correction reversal; swallow group failures as
  empty results; expose SQL/provider errors; query unapproved live web data;
  copy another owner's prior research; change legacy Ask defaults.
- **Affected:** E2.4, E3.3, E9.1–E9.3, E11.1, E11.5, E11.6, migration `0033`,
  Research Workspace routing/typeahead, and legacy rollback.
- **Source:** Product Specification sections 7.1–7.5 and 10.3–10.5;
  Implementation Plan E11.5 and Epic E11 acceptance/testing; Decisions D-005,
  D-009, D-038, and D-055.

## D-058 — Manual document search is an exact canonical read-through

- **Decision:** E11.6 reads existing document, registry-version,
  family/assignment, and chunk rows through one strict authenticated contract;
  it creates no manual-search projection or copied status. Exact phrase
  matching is literal, ordinary text uses the established weighted lexical
  predicates, and within-document matches retain exact chunk/page/section
  identity. Current, superseded, draft, and `Not established` status is
  evaluated from canonical lineage and publication/effective dates against
  one aware as-of day carried by the opaque filter-bound keyset cursor.
  Explicit registry-version identity overrides latest-version selection so
  historical deep links remain stable. Storage errors roll back an isolated
  savepoint and become a fixed safe unavailable response; a healthy empty
  result remains no-match. Migration `0034` adds matching indexes only.
- **Rationale:** The degradation fallback must remain usable without vector,
  semantic, orchestrator, or live-provider health and must not become a second
  corpus truth store. Deriving status and preserving exact version identity
  keeps lifecycle and historical results auditable. A cursor-bound as-of day
  prevents pagination from changing status semantics at a date boundary.
- **Alternatives rejected:** copy documents into a dedicated search table;
  depend on vector retrieval; infer lifecycle labels in the browser; always
  replace a historical version with latest; use offset pagination; treat
  storage failure as no-match; expose raw SQL/provider details; admit live
  results; mount the manual surface when the v2 UI flag is off.
- **Affected:** E5.3, E5.5, E9.1, E11.5, E11.6, migration `0034`, `/browse`
  routing/restoration, official-corpus rollback, and later comparison/
  compliance journeys.
- **Source:** Product Specification sections 7.4 and 10.4–10.5;
  Implementation Plan E11.6 and Epic E11 acceptance/testing; Decisions D-005,
  D-009, D-038, D-053, and D-057.

## D-059 — Legacy rendering is a strict projection, not a fourth provenance lane

- **Decision:** E8.7 derives one immutable version-1 compatibility result from
  the E8.5 structured response plus explicit citation snapshots. The reply
  begins with the stored compatibility summary, then deterministically labels
  live intelligence and General AI as non-official, records degraded sections
  and unknown-card fallback limitations, and appends the established legacy
  citation text format. The flat citation list admits only `supported` or
  legacy `verified` official citations referenced by an official section,
  orders sources by structured-response position, and deduplicates only exact
  stable source identity. Cross-lane source reuse, unknown claim/source
  references, conflicting source snapshots, duplicate citation identity, and
  verified citations without inspectable evidence fail closed.
- **Rationale:** Legacy clients cannot represent typed provenance sections or
  claim-scoped support. A deterministic projection preserves compatibility
  without relabeling live/general material as official, silently elevating
  unsupported evidence, or making the compatibility surface a separate truth
  store.
- **Alternatives rejected:** flatten every source as an official citation;
  return only the compatibility summary and hide provenance limitations;
  deduplicate by title or URL; admit partial/unknown verifier states; let
  citation input order determine output; alter the current route in E8.7.
- **Affected:** E8.1, E8.5, E8.7, E9.4, E10.9, legacy rollback, exact response
  restoration, citation persistence, and future response-schema migrations.
- **Source:** Product Specification sections 9 and 12; Implementation Plan
  Epic E8 API, rollback, testing, acceptance, and E8.7; Decisions D-027,
  D-032, and the B-005/B-009 approval policies.

## D-060 — Synchronous legacy waiting is bounded around the durable run

- **Decision:** E10.9 uses an injected asynchronous service that calls the
  E10.2 durable execution coordinator for one exact run/session/owner and then
  loads one identity-bound terminal artifact for E8.7 projection. Only
  Completed and Partial durable statuses are servable. One positive outer
  deadline, capped at the B-007 30-second Composite hard cutoff, covers durable
  execution, artifact loading, validation, and compatibility rendering; the
  worker lease cannot exceed that deadline and execution steps remain bounded.
  Outer expiry, cancellation, failed/nonterminal state, crossed/missing output,
  malformed artifacts, and internal faults expose fixed safe outcomes. Caller
  cancellation propagates, and an internal provider `TimeoutError` is not
  mislabeled as outer-deadline expiry.
- **Rationale:** The old client needs one synchronous response, while v2 owns
  durable execution and exact structured artifacts. Waiting around the durable
  boundary preserves restart/recovery semantics and legacy equivalence without
  adding a second execution path or silently extending an SLO deadline.
- **Alternatives rejected:** run capabilities directly inside `/chat`; poll
  indefinitely; reset the deadline for artifact loading; serve Failed or
  Cancelled runs; return partially validated artifacts; trust a loader's owner
  identity; convert caller cancellation into a product error; cut over the
  legacy route before rollout authority.
- **Affected:** E8.7, E10.1, E10.2, E10.9, B-007 latency enforcement, legacy
  rollback, and later v2 route cutover.
- **Source:** Implementation Plan Epic E10 API/risk/rollback/testing and E10.9;
  Orchestrator durability/terminal-state rules; B-007 Production SLO Approval;
  Decisions D-014, D-035, and D-059.
