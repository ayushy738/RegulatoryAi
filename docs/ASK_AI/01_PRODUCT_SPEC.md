# Ask AI Agent OS — Product Specification

**Derived from:** [ASK_AI_PRODUCT_SPEC.md](./ASK_AI_PRODUCT_SPEC.md)  
**Decision detail:** [ASK_AI_DECISION_ENGINE.md](./ASK_AI_DECISION_ENGINE.md)  
**Status:** Frozen summary; not a replacement for the source specification.

## Vision

Ask AI becomes a persistent **Regulatory Intelligence Workspace**, not a generic chatbot. A user can begin with an acronym, regulation, document, compliance question, amendment, or current-development query and reach a defensible understanding with explicit provenance, evidence, confidence, continuity, and useful next steps.

Product promise:

> Start anywhere. Understand the regulatory context. Verify the evidence. Continue the research.

## Objectives

- Resolve acronyms and regulatory entities into structured intelligence.
- Support evidence-backed regulatory and compliance research.
- Make timelines, amendments, stakeholders, obligations, and deadlines understandable.
- Preserve exact research continuity across sessions.
- Separate official, general, and live knowledge.
- Remain useful when individual capabilities fail.
- Replace raw errors and fake progress with truthful product states.

## Users

| Persona | Primary need | Trust requirement |
|---|---|---|
| Regulatory/Compliance Manager | Applicability, obligations, deadlines, authority | Very high; official basis required for action |
| Regulatory Research Analyst | Entity discovery, evolution, related instruments | Clear source paths; labeled general orientation acceptable |
| Legal/Policy Specialist | Exact legal basis, scope, versions, provisions | Claim-level citations and current status |
| Strategy/Market Intelligence Lead | Current developments and implications | Fresh live sources separated from official status |
| Operations/Project Member | Plain-language orientation and escalation | Simple explanations; no unsupported compliance conclusions |
| Executive | Significance, risk, urgency, next action | Concise summary with confidence and drill-down evidence |

## Core workflows

1. **Acronym to Intelligence Page:** `DSM` resolves to a canonical entity with definition, official instruments, timeline, stakeholders, obligations, amendments, related regulations, news when present, and follow-ups.
2. **Compliance research:** resolve entity, jurisdiction, and stakeholder; retrieve official evidence; show applicability assumptions, obligations, deadlines, exceptions, and sources.
3. **Latest intelligence:** search internal corpus and approved live sources independently; show separate provenance sections.
4. **Amendment exploration:** resolve regulation family; show chronology, affected provisions, versions, effective dates, and before/after evidence.
5. **Comparison:** resolve both operands; compare equivalent dimensions with independent evidence and `Not established` where missing.
6. **Document explanation:** explain or summarize a selected document/passage without losing its source context.
7. **Continue research:** reopen the workspace exactly, retain historical output, and offer explicit refresh rather than silent mutation.

## Knowledge modes

| Mode | Entry condition | Required behavior |
|---|---|---|
| Grounded Regulatory Knowledge | Relevant official/internal evidence supports the claim | Claim-linked official citations; High only where evidence gates pass |
| General AI Knowledge | Healthy official search finds no evidence, or request is explicitly general | Exact disclosure, no fake citations, Medium ceiling for standard no-match |
| Live Intelligence | Latest/current/news/consultation intent | Separate Internal Regulatory Corpus and Live Web Sources, each with freshness and source identity |

If official retrieval is unavailable, the product must not say that no documents exist. Any general explanation is qualified and capped Low/Unknown according to the Decision Engine.

## Functional requirements

| ID | Requirement |
|---|---|
| FR-01 | Interpret every query into intent, entities, time/status scope, confidence, and query expansion. |
| FR-02 | Clarify only material ambiguity; otherwise show editable assumptions. |
| FR-03 | Route only eligible capabilities and degrade them independently. |
| FR-04 | A bare resolved entity opens an Intelligence Page, not only prose. |
| FR-05 | Material grounded claims expose verified official evidence. |
| FR-06 | Missing official evidence activates the truthful Mode 2 path rather than ending the response. |
| FR-07 | Current queries keep official and live provenance separate. |
| FR-08 | Responses use structured cards for definitions, sources, obligations, deadlines, timelines, amendments, comparisons, stakeholders, related regulations, news, and confidence. |
| FR-09 | Multi-part questions complete independently by section. |
| FR-10 | Conversations preserve messages, sections, citations, sources, news, timelines, related questions, feedback, titles, modes, AI metadata, and visible state. |
| FR-11 | Sessions support create, reopen, rename, search, pin, duplicate, archive/restore, export, recoverable delete, refresh, and continuation. |
| FR-12 | Progress labels reflect actual capability events; stopping preserves completed artifacts. |
| FR-13 | Save, feedback, retry, regenerate, refresh, and stop perform their stated behavior. |
| FR-14 | Manual official-document search remains available during degraded retrieval. |
| FR-15 | Follow-ups advance research, deepen evidence, and avoid duplication. |

## Non-functional requirements

| ID | Requirement |
|---|---|
| NFR-01 Trust | Zero provenance mixing; no fake citations; no raw provider/database/HTTP errors. |
| NFR-02 Determinism | Same query context, policy version, capability health, and evidence yield the same decision outcome. |
| NFR-03 Reliability | Capability failures remain isolated; partial results survive. |
| NFR-04 Continuity | Reopening reproduces the historical result exactly; updates create new versions. |
| NFR-05 Security | Authentication, ownership, RLS, least privilege, and non-leaking authorization failures protect every workspace artifact. |
| NFR-06 Performance | Meet orchestration latency profiles or terminate at defined soft/hard cutoffs with useful output. |
| NFR-07 Accessibility | Keyboard-complete, responsive, readable provenance and confidence, accessible cards and evidence navigation. |
| NFR-08 Observability | Decisions, capability outcomes, timing, fallbacks, verification, and persistence are traceable without exposing chain-of-thought. |
| NFR-09 Compatibility | Rollout remains backward compatible through additive schema, side-by-side APIs, feature flags, and adapters. |

## Success metrics

### Trust

- 0 raw technical errors displayed.
- 100% of retained material Mode 1 claims have inspectable verified evidence.
- 100% of Mode 2 no-match responses show the exact disclosure.
- 100% of mixed live/internal results preserve provenance separation.
- 100% exact restoration in acceptance fixtures.

### Research effectiveness

- Entity/document/actionable-answer resolution rate.
- Time from acronym submission to useful entity overview.
- Official-source open rate.
- Timeline, amendment, and comparison engagement.
- Research-advancing follow-up completion rate.

### Quality and continuity

- Unsupported-claim reports by mode.
- Entity-correction and ambiguity rates.
- Conversation reopen and continuation rates.
- Session-search success.
- Saved/pinned evidence use.
- Healthy no-match rate separated from retrieval failures.

Production percentile SLO thresholds beyond the frozen orchestration cutoffs remain `TODO(Product/SRE)`; see [08_BLOCKERS.md](./08_BLOCKERS.md).

## Non-goals

- Not a substitute for legal advice.
- No automatic compliance decision without human review.
- No presentation of General AI as official interpretation.
- No silent promotion of live sources into the official corpus.
- No confidence claim based on model self-assessment.
