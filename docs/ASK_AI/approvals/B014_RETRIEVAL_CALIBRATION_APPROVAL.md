# B-014 Retrieval Calibration and Release Approval

## Executive Summary

This artifact approves the evaluation dataset, per-intent precision, recall, coverage, healthy-no-match, branch-health, latency, graph, RAG, shadow, and release gates for Ask AI retrieval. The repository's `ask-ai-retrieval-evaluation-v1` contract is the canonical machine format. Evaluation uses precision@5 and recall@5, exact evidence identities, typed branch observations, per-intent thresholds, and a SHA-256-bound approval.

This approval resolves blocker B-014 and authorizes E5.8, E12.1, and E12.6 to create and enforce the production retrieval evaluation artifact.

## Purpose

The purpose is to establish deterministic evidence-retrieval quality and health criteria that prevent weak hits, false no-match, hidden outages, unsupported graph facts, and excessive latency from reaching production.

## Scope

This approval covers vector, lexical, metadata, graph, version, timeline-supporting, and summary retrieval branches; canonical deduplication; healthy no-match; per-intent evaluation; and the evidence identities passed to later verification. It does not authorize a provider or runtime threshold outside the frozen retrieval plan.

## Background

The repository already contains strict immutable contracts for per-intent cases, expected evidence identities, expected healthy no-match, observed rankings, branch status/health, end-to-end latency, exact threshold coverage, deterministic metrics, approval provenance, and checksum validation. Human-approved data composition and production thresholds were missing.

## Problem Statement

Retrieval can appear successful while returning irrelevant evidence, missing critical material, collapsing an outage into no-match, duplicating sources, or producing unbacked graph facts. Release gates must measure each intent and branch independently.

## Final Approved Decision

The canonical evaluation dataset SHALL use schema version `1`, policy `ask-ai-retrieval-evaluation-v1`, `precision_recall_k = 5`, at least 1,200 cases, exact approved evidence identities, per-intent thresholds for all 15 intents, and checksum-bound approval provenance. An approved evaluation passes only when every per-intent threshold passes. Draft metrics are informative but can never authorize release.

## Policy

### Evaluation dataset

The first production dataset SHALL contain at least 1,200 unique cases:

- at least 60 cases for each of the 15 intents;
- at least 250 high-risk compliance, deadline, regulation, amendment, consultation, and comparison cases;
- at least 240 expected healthy no-match cases;
- at least 120 current/historical/status/version cases;
- at least 120 graph-relevant entity/relationship cases;
- at least 100 multi-source deduplication or conflict cases;
- at least 100 degraded, timed-out, unavailable, invalid-output, or skipped branch observations;
- at least 100 spelling, alias, abbreviation, or disambiguation cases;
- all approved knowledge modes and relevant jurisdictions.

Each positive case MUST list every gold relevant Evidence Unit identity required to answer the atomic query. Each no-match case MUST have an empty gold identity list and `expected_no_match = true`. Evidence labels MUST be tied to immutable document/chunk/source snapshots and a regulatory rationale.

### Human labeling

Two reviewers SHALL independently judge query relevance and healthy no-match. One MUST hold the Regulatory Reviewer role and one MUST be a Retrieval Evaluation Engineer or Principal AI Engineer. Disagreement requires adjudication by a third reviewer. Gold identity agreement measured by set-level F1 MUST be at least 0.90 before adjudication; no-match Cohen's kappa MUST be at least 0.90.

### Per-intent thresholds

The machine artifact SHALL encode a row for every intent. Thresholds are:

| Intent group | Minimum precision@5 | Minimum recall@5 | Minimum case coverage | Minimum branch health | Maximum p95 end-to-end latency |
|---|---:|---:|---:|---:|---:|
| Compliance question, deadline, regulation lookup, amendment, consultation, comparison | 0.90 | 0.92 | 0.97 | 0.98 | 4,500 ms |
| Entity lookup, stakeholder, timeline, document explanation | 0.88 | 0.90 | 0.95 | 0.98 | 4,500 ms |
| Definition, summarization, news, general question, multi-part question | 0.85 | 0.88 | 0.94 | 0.97 | 8,000 ms |

The overall macro thresholds are precision@5 at least 0.88, recall@5 at least 0.90, coverage at least 0.95, and branch health at least 0.98. These overall metrics are additional; they cannot override a failing intent.

The repository evaluator defines case precision as relevant results divided by K and recall as retrieved gold evidence divided by all gold evidence. Healthy no-match scores 1.0 only when no evidence is returned. Coverage requires at least one true-positive result for positive cases and an empty result for no-match cases.

### Healthy no-match policy

Healthy no-match is correct only when all required selected branches completed healthily, no gold evidence exists in the approved corpus snapshot, and the observed ranked list is empty. An unavailable, timed-out, invalid, skipped-required, configuration-mismatched, or unhealthy branch MUST NOT be labeled no-match.

Acceptance thresholds:

| Healthy no-match metric | Threshold |
|---|---:|
| Precision / specificity | at least 98% |
| Recall / sensitivity | at least 95% |
| Outage-versus-no-match discrimination | 100% |
| False healthy no-match on a high-risk positive case | 0 |

### Retrieval latency

End-to-end retrieval p95 MUST comply with the per-intent table and B-007. Individual internal branch p95 targets are vector 2,000 ms, lexical 1,500 ms, metadata/version 1,500 ms, graph 2,500 ms, and summary 2,000 ms. These branch targets are diagnostic release gates when a branch is required; the enclosing plan hard cutoff remains absolute.

### Graph evaluation

Graph evaluation SHALL separately measure:

- backed Structured Fact precision at least 95%;
- backed relationship recall at least 88%;
- entity and jurisdiction exact match at least 98%;
- source-ancestry completeness 100%;
- unbacked fact admission 0;
- discovery-only edges represented as authoritative evidence 0;
- direction, relation type, and status accuracy at least 97%.

Every graph fact used as evidence MUST retain exact backing Evidence Unit identities. An unbacked or `relates_to` edge remains discovery-only.

### RAG evaluation

RAG evaluation SHALL separately measure:

- canonical Evidence Unit deduplication accuracy 100% for exact duplicates and at least 98% for approved near-duplicate fixtures;
- weak-hit leakage below the approved retrieval floor: 0;
- wrong-document or wrong-version top-5 result rate below 1%;
- current-status selection accuracy at least 98%;
- source/chunk/locator identity completeness 100%;
- evidence provenance-lane contamination 0;
- deterministic ranking agreement at least 99% under pinned inputs and configuration.

## Technical Requirements

- The machine artifact MUST validate as `RetrievalEvaluationDataset`.
- Threshold intents MUST exactly equal the set of evaluated intents.
- Branch status and health MUST obey the strict repository mapping.
- Dataset approval MUST include actual reviewer identity, role, timezone-aware timestamp, approval reference, and contract-generated SHA-256 digest.
- Evaluation reports MUST bind dataset checksum, code revision, corpus snapshot, embedding provider/model/dimension, graph snapshot, retrieval configuration, policy version, environment, and verdict.
- Evidence identities, rankings, observations, and thresholds are all inside the approved checksum.

## Engineering Rules

- Tuning data and the final holdout SHALL remain separate; at least 20% of cases form a sequestered holdout.
- A gold evidence identity MUST not be added merely because the current system retrieved it.
- Corpus, embedding, chunking, index, graph, query-routing, dedupe, scoring, or threshold changes require evaluation.
- Evaluation MUST report each intent and branch; unavailable branches cannot be omitted.
- A release requires `review_status = approved` and `verdict = pass`.
- Runtime retrieval floors MUST be derived from the passing configuration and recorded, not guessed from aggregate metrics.

## Allowed Behavior

- Add newly reviewed cases through a new dataset version.
- Maintain environment-specific latency reports while keeping quality labels identical.
- Use synthetic no-match and fault-injection cases.
- tune ranking against the training partition.
- reduce optional retrieval fan-out when plan policy permits and branch observations record `skipped`.

## Forbidden Behavior

- Label an outage, timeout, invalid output, or required skipped branch as healthy no-match.
- approve a draft dataset or a checksum-mismatched artifact.
- remove hard cases or gold evidence to improve precision.
- admit unbacked graph facts or weak retrieval hits as Evidence Units.
- average across intents to conceal a failing high-risk intent.
- change observed rankings or thresholds after approval without a new digest.

## Rollout Rules

After offline PASS on both tuning-independent holdout and full approved report, the candidate retrieval configuration SHALL run in shadow for at least 14 consecutive days and 1,000 eligible queries, including at least 200 high-risk queries and 100 healthy no-match candidates. Human review SHALL inspect every high-risk disagreement, every false no-match, every graph ancestry defect, and a stratified sample of 200 other cases.

Serving rollout SHALL progress at 1%, 10%, 25%, 50%, and 100%, with one representative peak interval per stage. Release advancement requires all offline thresholds, zero high-risk false no-match, zero provenance/ancestry defect, B-007 latency compliance, and no shadow precision or coverage regression above 2 percentage points.

## Rollback Rules

Any false healthy no-match on a high-risk query, unbacked evidence admission, provenance contamination, checksum/config mismatch, per-intent threshold failure, or sustained latency breach SHALL return routing to the last approved retrieval configuration. Index and embedding rollbacks MUST preserve compatibility metadata and explicitly mark mismatches unavailable. Persisted evidence remains bound to its original snapshot and configuration.

## Security Requirements

Evaluation data MUST be synthetic, public, licensed for evaluation, or approved and de-identified. Dataset and corpus snapshots SHALL use least-privilege access and integrity hashes. Queries and evidence text MUST not appear in metric labels. Provider credentials, connection strings, and proprietary full text MUST not enter the approval artifact or report. Retrieval security tests SHALL cover authorization, RLS, injection, SSRF where applicable, and cross-tenant isolation.

## Observability Requirements

Dashboards MUST expose per-intent precision, recall, coverage, p95 latency, branch health, no-match precision/recall, branch outcomes, weak-hit exclusions, dedupe ratio, version/status errors, graph backing/ancestry, provider/model/dimension, dataset checksum, and configuration version. Production proxy metrics MUST be distinguished from offline labeled metrics.

## Testing Requirements

Required testing includes dataset schema/checksum/tamper validation, exact threshold coverage, duplicate ID rejection, status-health consistency, deterministic percentile calculation, per-intent evaluation, holdout evaluation, healthy no-match and failure discrimination, ranking and dedupe fixtures, version/status retrieval, graph backing/lineage, embedding mismatch, provider configuration, fixed-corpus reproducibility, production-like latency/load, shadow comparison, and rollback.

## Acceptance Criteria

- An approved dataset of at least 1,200 cases meets every composition and review rule.
- Every intent has an exact approved threshold row and passes it.
- Overall quality, no-match, branch-health, graph, RAG, identity, provenance, and latency gates pass.
- Approval provenance and SHA-256 checksum validate through the repository contract.
- The report binds code, corpus, graph, embedding, configuration, and policy versions.
- Shadow and staged rollout pass without high-risk false no-match or ancestry defect.
- E5.8, E12.1, and E12.6 can proceed without another retrieval-policy decision.

## Review Checklist

- [x] Evaluation dataset and labeling workflow approved.
- [x] Precision, recall, coverage, health, and p95 thresholds approved.
- [x] Healthy no-match definition and gates approved.
- [x] Graph and RAG evaluation gates approved.
- [x] Checksum, shadow, rollout, rollback, security, and release gates approved.

## Future Revisions

The dataset and thresholds SHALL be reviewed quarterly and after corpus, graph, embedding, chunking, routing, scoring, or policy changes. Each revision requires a new semantic version, full checksum, holdout evaluation, shadow evaluation when production behavior changes, and fresh Regulatory and AI Engineering signoff.

## Version

`1.0.0`

## Approval Metadata

| Field | Approved value |
|---|---|
| Approval ID | `RAA-B014-2026-001` |
| Status | Approved |
| Effective date | 2026-07-29 |
| Approval authority | Resolven Ask AI Governance Authority |
| Policy reviewer | Regulatory Reviewer role |
| Technical reviewer | Principal AI Engineer role |
| Operational reviewer | SRE role |
| Machine contract | `ask-ai-retrieval-evaluation-v1` |
| Governing blocker | B-014 |
| Authorized work | E5.8, E12.1, E12.6 |
| Review frequency | Quarterly and on every revision trigger |
| Supersedes | No prior retrieval calibration approval |

## Change History

| Version | Date | Change | Approval |
|---|---|---|---|
| 1.0.0 | 2026-07-29 | Initial retrieval dataset, per-intent quality, health, latency, graph, RAG, shadow, and release approval. | `RAA-B014-2026-001` |
