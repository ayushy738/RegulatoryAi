# B-009 Material Claim Verification Policy

## Executive Summary

This artifact approves the production method for verifying material regulatory claims against admitted evidence. Verification is claim-scoped, provenance-preserving, and fail-closed. A verifier MAY label a claim `Supported`, `Partial Support`, `Contradiction`, or `Unknown` only after evidence identity, scope, status, and semantic support checks pass. One bounded correction pass is allowed. Grounded prose is permitted only when the approved quality gates pass and every material claim has a publishable outcome; otherwise the product MUST use evidence-only mode or explicitly withhold the claim.

This approval resolves blocker B-009 and authorizes E7.3, E7.9, grounded-prose activation, and their dependent work.

## Purpose

The purpose is to define claim granularity, evidence identity, verification outcomes, confidence treatment, correction behavior, evaluation thresholds, and human-review controls.

## Scope

This policy applies to candidate claims derived from official internal evidence and attributed live evidence, including summaries, obligations, deadlines, status, applicability, amendments, comparisons, timelines, and current-event statements. General AI prose without evidence is outside the grounded verifier and MUST follow Mode 2 disclosure and confidence ceilings.

## Background

The frozen architecture requires two-pass verification: identity/admission followed by claim support, with a single bounded correction attempt. Candidate Claim contracts, evidence admission, confidence calculation, and provenance lineage already define strict boundaries. Engineering lacked approved semantic labels, quality thresholds, and prose-release rules.

## Problem Statement

Citation presence is not proof that evidence supports the nearby text. Claims can overstate scope, omit exceptions, misread draft status, combine several propositions, or cite a related but non-supporting passage. A deterministic release policy is required to prevent unsupported regulatory prose.

## Final Approved Decision

Resolven Ask AI SHALL use the definitions and pipeline below. The production verifier MUST meet all acceptance thresholds on the approved evaluation dataset before grounded prose is enabled. Until then, and during any verifier degradation, grounded lanes SHALL use evidence-only mode.

## Policy

### Normative definitions

**Material Claim:** one independently verifiable proposition whose inaccuracy could alter a user's understanding of legal status, applicability, obligation, deadline, scope, actor, amount, exception, procedural step, chronology, source authority, or current event. Headings, pure navigation text, and explicitly labeled uncertainty without a factual proposition are not material claims.

**Evidence:** an admitted, immutable evidence unit with source identity, document identity, locator, excerpt, provenance lane, jurisdiction, status, applicable time, and content hash. A URL, title, retrieval result, model memory, or graph edge without backing evidence is not evidence.

**Support:** the admitted evidence directly entails the complete claim, including entity, action, modality, jurisdiction, status, time, quantity, condition, exception, and scope. The approved output label is `Supported`.

**Partial Support:** evidence entails a material subset of the claim but leaves at least one non-contradicted material qualifier unestablished. Partial support MUST identify the unsupported span or qualifier.

**Contradiction:** admitted evidence directly conflicts with at least one material proposition or establishes an incompatible status, date, actor, quantity, scope, or modality. A contradiction MUST retain both the claim and conflicting evidence for audit.

**Unknown:** the admitted evidence cannot establish support, partial support, or contradiction with the required precision. Missing evidence, ambiguous scope, unresolved source conflict, unverifiable cross-reference, and verifier inability produce `Unknown`.

`Unsupported` MAY be an internal diagnostic for a claim with available evidence that supplies no material support and no direct conflict. At the product boundary it is handled as `Unknown` unless a distinct unsupported display is explicitly present in the frozen response contract.

### Claim granularity

A candidate claim MUST contain one subject, one principal predicate, and its inseparable qualifiers. Coordinated claims joined by `and`, `or`, semicolons, bullets, or relative clauses MUST be split when either proposition could receive a different verification result. Dates, amounts, thresholds, exceptions, jurisdiction, actor, modality (`must`, `may`, `proposes`), and legal status are material qualifiers and MUST remain in the same atomic claim as the proposition they qualify.

Quotations MUST be verified for text identity and attribution. Summaries MUST be verified for semantic entailment. A claim spanning multiple sources MAY be Supported only when the evidence set jointly establishes the whole claim and no source conflicts.

### Evidence identity

Verification inputs MUST reference exact admitted evidence IDs. The verifier SHALL revalidate document, source, chunk or locator, excerpt hash, provenance lane, status-as-of, jurisdiction, and question/section scope. Identity mismatch, stale mutable lookup, forged source reference, wrong owner, invalid lineage, or lane contamination terminates semantic verification for that evidence.

### Verifier pipeline

1. Revalidate the versioned request, Candidate Claim, and evidence contracts.
2. Normalize the claim without changing material meaning.
3. Segment the claim into atomic material propositions.
4. Resolve each evidence reference to the immutable admitted snapshot.
5. Apply identity, authorization, provenance, jurisdiction, time, and status gates.
6. Extract relevant evidence spans without expanding source authority.
7. Evaluate complete support, partial support, and contradiction at proposition level.
8. Aggregate proposition outcomes using the weakest material proposition.
9. Apply deterministic legal-status and provenance constraints.
10. Calculate verification confidence and record reasons.
11. If not publishable, perform at most one bounded correction.
12. Reverify the corrected claim from step 1.
13. Emit the final typed result and complete audit record.

No model judgment may override a failed identity, authorization, status, provenance, or scope gate.

### Verification workflow and correction

Supported claims pass unchanged. Partial Support triggers a correction attempt that removes or narrows only the unsupported qualifier while preserving the answer's intent. Contradiction triggers either a corrected statement faithful to evidence or a visible conflict statement. Unknown triggers withholding or evidence-only presentation.

Only one correction attempt is permitted. A correction MUST reference the same or a strict subset of admitted evidence, MUST NOT introduce a new material proposition, and MUST preserve material exceptions. If re-verification does not produce Supported, the corrected prose MUST NOT be published as grounded prose.

### Confidence calculation

Verification confidence is a calibrated support score, not a probability of legal correctness. It MUST combine semantic entailment, qualifier coverage, evidence agreement, evidence quality, and verifier agreement without replacing the frozen evidence-derived confidence calculation.

Publication thresholds are:

| Outcome | Required verifier confidence | Product treatment |
|---|---:|---|
| Supported, high-risk claim | at least 0.95 | Eligible for grounded prose subject to all other gates |
| Supported, other material claim | at least 0.90 | Eligible for grounded prose subject to all other gates |
| Partial Support | at least 0.80 for the supported subset | Correction or explicit limitation; not publishable as the original claim |
| Contradiction | at least 0.90 | Conflict display or correction; original claim forbidden |
| Unknown | any lower or indeterminate score | Withhold or evidence-only |

The final claim confidence MUST NOT exceed the weakest evidence authority, source-lane ceiling, scope fitness, status fitness, or frozen confidence score.

### Grounded prose and evidence-only mode

Grounded prose is allowed only when:

- the current approved verifier dataset has a `PASS` release record;
- every material claim is Supported after no more than one correction;
- high-risk claims meet the 0.95 verifier threshold;
- citation coverage for material claims is 100%;
- evidence identity and provenance checks pass;
- no unresolved contradiction remains;
- the verifier completes inside its approved budget.

Evidence-only mode is REQUIRED when the verifier is disabled, unavailable, timed out, circuit-open, below an acceptance threshold, operating on an unapproved model/prompt/policy version, or unable to support every high-risk material claim. Evidence-only output MAY show admitted excerpts, source cards, dates, status, and explicit gaps. It MUST NOT present an unverified synthesized conclusion.

## Technical Requirements

- Verifier requests and results MUST be immutable, strictly versioned, schema validated, and deterministically serializable.
- Results MUST include claim ID, atomic proposition IDs, evidence IDs, outcome, confidence, supported/unsupported spans, contradiction references, correction lineage, verifier version, policy version, model version, latency, and terminal reason.
- The same input and pinned verifier version MUST produce equivalent labels within approved nondeterminism bounds; disagreement across repeated evaluation is a test failure.
- Verifier prompts and model output MUST be treated as untrusted and constrained to the typed output schema.
- Evidence excerpts MUST not be broadened, rewritten, or replaced before verification.

## Engineering Rules

- Identity/admission verification MUST precede semantic support verification.
- The verifier MUST NOT retrieve new evidence. Missing evidence returns Unknown and the Orchestrator decides whether a separate retrieval is eligible.
- One claim MUST NOT inherit support from another claim.
- Aggregate section status SHALL be the weakest material-claim status.
- Correction MUST be append-only and retain the original claim.
- New verifier, model, prompt, label, or threshold versions require shadow evaluation and approval.

## Allowed Behavior

- Use several admitted evidence units jointly to support one atomic claim.
- Narrow a partially supported claim to the exact supported proposition once.
- State that official sources conflict and present both verified positions.
- Publish non-material connective prose that introduces or organizes verified claims.
- Display evidence cards when semantic verification is unavailable.

## Forbidden Behavior

- Treat topical relevance, citation proximity, lexical overlap, graph adjacency, or source authority alone as support.
- Publish Partial Support, Contradiction, Unknown, or internally Unsupported claims as settled grounded prose.
- Hide material exceptions, conditions, draft status, jurisdiction, or effective date.
- Reverify against a mutable URL instead of the admitted snapshot.
- Allow a language model to self-approve its claim without calibrated independent verification.
- perform more than one correction pass.

## Rollout Rules

The verifier SHALL run offline first, then in shadow for at least 14 consecutive days and 1,000 eligible claims. Grounded prose activation SHALL progress at 1%, 10%, 25%, 50%, and 100%. Every stage requires all dataset thresholds, zero critical unsupported publications, stable latency under B-007, and Regulatory Reviewer signoff on sampled production-shadow cases. A model, prompt, or rule change resets shadow evaluation for the changed version.

## Rollback Rules

Any release-gate failure, critical false support, provenance defect, cross-tenant defect, or sustained SLO breach SHALL disable grounded prose and activate evidence-only mode immediately. Previously persisted claim and correction records remain immutable. Rollback MUST pin the last approved verifier version or disable semantic verification; it MUST NOT silently use an unapproved version.

## Security Requirements

Verifier inputs MUST remain owner scoped and contain only admitted evidence needed for the claim. Provider retention MUST be disabled where supported. Prompts, evidence, and outputs MUST be protected in transit and at rest. Logs MUST exclude full prompt/evidence text and user secrets. Prompt injection inside evidence MUST be treated as content, never as instruction. Authorization and RLS failures are fail-closed.

## Observability Requirements

Dashboards MUST expose outcome distribution, confidence distribution, correction rate, second-pass outcome, contradiction rate, Unknown rate, evidence-only rate, identity-gate failures, provenance failures, per-intent precision/recall from evaluation, latency percentiles, timeout/circuit state, verifier version, and dataset checksum. Metrics MUST not contain claim text or evidence excerpts. A single critical false-support or provenance failure pages.

## Testing Requirements

### Evaluation dataset

The approved verifier evaluation dataset SHALL contain at least 1,500 independently labeled atomic claims:

| Label | Minimum cases |
|---|---:|
| Supported | 400 |
| Partial Support | 300 |
| Contradiction | 300 |
| Unknown/Unsupported | 300 |
| Multi-source or conflict-specific cases, included above | 200 |

At least 40% SHALL be high-risk obligation, deadline, applicability, legal-status, or amendment claims; at least 20% SHALL contain negation, exceptions, quantities, or temporal qualifiers; all production intents, jurisdictions, provenance lanes, and status classes SHALL be represented.

Two qualified reviewers SHALL label every case independently. Disagreement requires a third Regulatory Reviewer adjudication. Dataset inter-reviewer Cohen's kappa MUST be at least 0.85 before approval.

### Acceptance thresholds

| Metric | Required threshold |
|---|---:|
| Supported precision, high-risk claims | at least 98% |
| Supported precision, all material claims | at least 96% |
| Supported recall, high-risk claims | at least 95% |
| Supported recall, all material claims | at least 92% |
| Contradiction precision | at least 97% |
| Contradiction recall | at least 95% |
| Partial Support macro F1 | at least 90% |
| Unknown/Unsupported macro F1 | at least 90% |
| Evidence identity/provenance gate accuracy | 100% |
| Material claim citation coverage | 100% |
| Critical unsupported grounded publications | 0 |
| p95 verification latency | at most 2,200 ms |

Metrics SHALL be reported overall and per high-risk intent. Every mandatory threshold must pass; averaging cannot mask a failing intent or class.

## Acceptance Criteria

- All terms and outcomes have executable definitions.
- Claim segmentation preserves every material qualifier.
- Evidence identity and admission are revalidated before semantics.
- One bounded correction is enforced and auditable.
- Grounded prose and evidence-only transitions are deterministic.
- The labeled dataset meets size, diversity, dual-review, and agreement requirements.
- Every precision, recall, coverage, safety, and latency threshold passes.
- E7.3 and E7.9 can proceed without another verifier-policy decision.

## Review Checklist

- [x] Material Claim and Evidence defined.
- [x] Support, Partial Support, Contradiction, and Unknown defined.
- [x] Pipeline, granularity, workflow, identity, and correction rules fixed.
- [x] Confidence and prose-release gates fixed.
- [x] Dataset, human review, precision, recall, latency, and acceptance thresholds fixed.
- [x] Security, observability, rollout, and rollback fixed.

## Future Revisions

Revisions require a new semantic version, immutable evaluation results against the current and proposed policies, Regulatory Reviewer approval, Security review for provider/data changes, and SRE approval for latency changes. Previously verified claims remain bound to their recorded policy and verifier versions.

## Version

`1.0.0`

## Approval Metadata

| Field | Approved value |
|---|---|
| Approval ID | `RAA-B009-2026-001` |
| Status | Approved |
| Effective date | 2026-07-29 |
| Approval authority | Resolven Ask AI Governance Authority |
| Accountable roles | Lead Product Architect; Principal AI Engineer; Principal Platform Engineer; SRE; Security Engineer; Regulatory Reviewer |
| Governing blocker | B-009 |
| Authorized work | E7.3, E7.9 and grounded-prose activation |
| Review frequency | Quarterly and on every verifier change |
| Supersedes | No prior approved verifier policy |

## Change History

| Version | Date | Change | Approval |
|---|---|---|---|
| 1.0.0 | 2026-07-29 | Initial material-claim verification, evaluation, and grounded-prose approval. | `RAA-B009-2026-001` |
