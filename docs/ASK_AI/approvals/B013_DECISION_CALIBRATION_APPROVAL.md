# B-013 Decision Engine Calibration Approval

## Executive Summary

This artifact approves the golden dataset, thresholds, review workflow, accuracy gates, versioning, and signoff rules for the Ask AI Decision Engine. The existing immutable `ask-ai-decision-calibration-v1` contract is the canonical machine-readable format. Approved thresholds are 0.90 Certain, 0.10 competing-intent gap, 0.75 Strong, 0.55 Bounded, and 0.85 high-risk entity confidence. The first production golden dataset MUST contain at least 600 independently reviewed cases spanning every intent and high-risk boundary.

This approval resolves blocker B-013 and authorizes E3.7, E12.1, and E12.6 to create, review, checksum, and enforce the production calibration artifact.

## Purpose

The purpose is to make Decision Engine routing quality measurable, reproducible, regulator-reviewed, and release blocking.

## Scope

This approval covers intent, secondary intent, response strategy, confidence band, canonical entity identity, entity confidence, time dimension, plan class, clarification decision, and regulatory rationale. It applies to offline evaluation, shadow evaluation, regression fixtures, and production release gates.

## Background

The repository already enforces a strict frozen calibration schema with unique cases, non-placeholder approval provenance, timezone-aware approval time, immutable thresholds, and a SHA-256 digest over the complete thresholds and case payload. Only a human-approved dataset specification and deterministic quality gates were missing.

## Problem Statement

Unit fixtures prove contract mechanics but cannot approve production routing. Without representative labels and acceptance thresholds, high-risk compliance questions can select the wrong intent, entity, time meaning, or response plan without a release-blocking signal.

## Final Approved Decision

The canonical dataset SHALL use:

- schema version `1`;
- calibration policy `ask-ai-decision-calibration-v1`;
- decision policy `ask-ai-decision-v1`;
- the exact threshold values below;
- at least 600 approved cases;
- approval provenance from a named internal reviewer identity associated with the Regulatory Reviewer role;
- the contract-generated SHA-256 digest over thresholds and cases.

No draft, synthetic-only, placeholder-approved, or checksum-mismatched dataset can authorize production routing.

## Policy

### Approved thresholds

| Contract field | Approved value | Deterministic behavior |
|---|---:|---|
| `intent_certain_min` | 0.90 | Certain requires score at least 0.90 and competing gap at least 0.10 |
| `intent_certain_competing_gap_min` | 0.10 | Smaller gap prevents Certain |
| `intent_strong_min` | 0.75 | Strong begins at 0.75 |
| `intent_bounded_min` | 0.55 | Bounded begins at 0.55 |
| `entity_high_risk_min` | 0.85 | Lower entity confidence cannot drive high-risk direct answers |

Scores below 0.55 or cases with material unresolved ambiguity SHALL use the Ambiguous band and require clarification or a safe bounded plan. A threshold change requires a new calibration-policy version and reapproval.

### Golden dataset specification

The dataset SHALL contain at least 600 unique cases:

- at least 30 cases for each of the 15 primary intents;
- at least 120 high-risk cases across compliance questions, deadlines, amendments, consultations, comparisons, and regulation lookup;
- at least 100 ambiguity/clarification cases;
- at least 100 entity cases including aliases, abbreviations, collisions, wrong jurisdiction, and unresolved identity;
- at least 100 temporal/status cases including issue, effective, compliance deadline, consultation, event, validity, document version, and retrieval meanings;
- at least 75 multi-part cases;
- at least 75 conversation-context cases;
- at least 60 current/latest/recent/news/consultation cases;
- at least 10 cases for each declared response strategy and plan class, with overlap permitted.

The dataset SHALL include positive, near-boundary, adversarial, typo, underspecified, conflicting-context, no-entity, multiple-entity, and out-of-domain examples. No single source template may contribute more than 10% of cases.

Every case MUST populate all contract fields applicable to its meaning: case ID, exact query, primary intent, secondary intents, response strategy, confidence band, canonical entity IDs, minimum entity confidence when applicable, time dimension, plan class, clarification flag, and non-placeholder regulatory rationale.

### Labeling and review workflow

1. An AI Evaluation Engineer creates or imports a candidate case without approval fields.
2. Two qualified reviewers independently label the case. One MUST hold the Regulatory Reviewer role; the other MUST be a Product Architect or Principal AI Engineer.
3. Exact agreement is required for primary intent, response strategy, plan class, and clarification.
4. Disagreement on any material field is adjudicated by a second Regulatory Reviewer or the Lead Product Architect who did not create the case.
5. Entity IDs MUST be validated against the versioned entity/glossary registry.
6. Time labels MUST be reviewed under a fixed clock and declared Asia/Kolkata default unless the query provides another zone.
7. The complete dataset is deduplicated, schema validated, evaluated, and checksum generated.
8. The approving Regulatory Reviewer signs the exact checksum and approval reference.

Creator and final approver MUST be different identities. Approval fields MUST use actual organization identities in the implementation artifact; role labels or placeholders alone are invalid.

### Accuracy metrics and thresholds

| Metric | Release threshold |
|---|---:|
| Primary intent exact accuracy, overall | at least 96% |
| Primary intent exact accuracy, high-risk subset | at least 98% |
| High-risk intent precision and recall, each | at least 97% |
| Secondary-intent micro F1 | at least 92% |
| Response-strategy exact accuracy | at least 96% |
| Plan-class exact accuracy | at least 97% |
| Intent confidence-band accuracy | at least 94% |
| Canonical entity exact-set accuracy, overall | at least 98% |
| Canonical entity exact-set accuracy, high-risk | at least 99% |
| Wrong-jurisdiction entity selection in high-risk cases | 0 |
| Entity confidence gate violations | 0 |
| Time-dimension exact accuracy | at least 97% |
| Clarification precision | at least 95% |
| Clarification recall | at least 95% |
| Unsafe direct answer on required-clarification case | 0 |
| Deterministic repeat agreement | 100% |

Every primary intent MUST have at least 90% exact accuracy. Overall performance cannot mask a failing intent or any zero-tolerance safety metric.

### Ambiguity handling

Clarification is REQUIRED when two material intents remain within the approved competing gap, a high-risk entity is below 0.85, jurisdiction changes the answer and is unresolved, the requested document/version is ambiguous, or a multi-part query cannot be safely decomposed. The engine MAY choose a bounded plan without clarification only when the uncertainty is explicitly represented and cannot change a legal-status, applicability, obligation, or deadline result.

## Technical Requirements

- The machine artifact MUST validate as `DecisionCalibrationDataset`.
- Case IDs MUST be stable, unique, lowercase repository-safe identifiers.
- JSON checksum serialization MUST match the repository function: UTF-8, sorted keys, compact separators, and SHA-256.
- Thresholds and cases MUST be inside the signed payload; approval metadata binds the exact digest.
- Evaluation reports MUST record code revision, policy versions, dataset checksum, entity-registry version, model/rule version, fixed clock, environment, metrics, and verdict.
- Approved cases are immutable. A label correction creates a new dataset version and digest.

## Engineering Rules

- Golden cases MUST NOT be altered to accommodate a regression without independent relabeling and a documented rationale.
- Training or rule-tuning data MUST remain separate from the final holdout set.
- At least 20% of cases SHALL remain a sequestered holdout unavailable during tuning.
- Production routing MUST use exactly the policy and thresholds named by the passing report.
- Shadow disagreement telemetry MUST not contain raw regulated query text.
- Any taxonomy, entity registry, time policy, response strategy, plan class, or threshold change triggers recalibration.

## Allowed Behavior

- Add new approved cases through a minor dataset version.
- Correct a demonstrably mislabeled case after independent review and a change record.
- Use synthetic cases when they represent realistic regulatory boundaries and are labeled as synthetic.
- maintain separate language or jurisdiction slices while reporting the combined required metrics.
- use shadow production patterns after approved de-identification.

## Forbidden Behavior

- Self-approve a dataset created by the same identity.
- Use a placeholder reviewer, role, timestamp, reference, rationale, or checksum.
- delete difficult cases, lower thresholds, or alter labels to make a release pass.
- leak holdout labels into tuning.
- permit aggregate accuracy to override a zero-tolerance unsafe routing failure.
- deploy a checksum, policy, or registry version different from the evaluated artifact.

## Rollout Rules

After offline PASS, the Decision Engine SHALL run in shadow for at least 14 consecutive days and 1,000 eligible production requests. Shadow review MUST include all disagreements on high-risk routing and a stratified sample of agreements. Serving rollout SHALL proceed at 1%, 10%, 25%, 50%, and 100%, with at least 24 hours and one representative peak interval per stage. Each stage requires offline gates, zero unsafe direct answers, no unexplained disagreement increase above 2 percentage points, and B-007 latency compliance.

## Rollback Rules

A wrong-jurisdiction high-risk selection, unsafe direct answer on required ambiguity, dataset/checksum mismatch, policy-version mismatch, or significant gate regression SHALL return serving to the last approved Decision Engine or legacy routing flag. Shadow recording MAY continue. Persisted decisions remain bound to their original policy and calibration versions.

## Security Requirements

Queries in the approved dataset MUST be synthetic, public, or formally de-identified. Dataset access SHALL be least privilege. Approval keys and reviewer credentials MUST not appear in the artifact. Hash and code review protect integrity; the artifact and report MUST be retained as release evidence. Prompt-injection strings MAY appear only as inert test data.

## Observability Requirements

Dashboards MUST show intent distribution, confidence bands, clarification rate, entity confidence, time dimension, plan class, legacy-shadow agreement, high-risk disagreement, unsafe-routing count, dataset checksum, policy/model version, and latency. Metrics MUST use bounded taxonomy values and MUST NOT contain query text or entity names as labels.

## Testing Requirements

Testing includes schema and checksum validation, duplicate/tamper/placeholder/naive-time rejection, deterministic serialization, threshold-boundary tests, full golden evaluation, sequestered holdout evaluation, per-intent confusion matrices, entity exact-set and jurisdiction tests, time-zone fixed-clock tests, ambiguity tests, multi-part and conversation tests, shadow comparison, latency measurement, and rollback flag tests.

## Acceptance Criteria

- A 600-case or larger approved dataset meets every composition rule.
- Thresholds exactly match this approval and the versioned contract.
- Dual review, adjudication, separation of creator/approver, and checksum signoff are complete.
- Every overall, per-intent, entity, time, ambiguity, safety, and determinism threshold passes.
- The report binds dataset, code, registry, policy, and model/rule versions.
- Shadow and staged-rollout gates pass before serving activation.
- E3.7, E12.1, and E12.6 can proceed without another calibration-policy decision.

## Review Checklist

- [x] Golden dataset size and composition approved.
- [x] Review, adjudication, and signoff workflow approved.
- [x] Intent, entity, time, plan, and ambiguity thresholds approved.
- [x] Dataset versioning and checksum contract approved.
- [x] Shadow, release, rollback, security, and observability gates approved.

## Future Revisions

The dataset SHALL be reviewed quarterly and after any taxonomy, registry, policy, model, rule, or material production-pattern change. Revisions require a new dataset semantic version, new SHA-256 digest, complete evaluation, and fresh signoff. Prior versions remain immutable and retained for reproducibility.

## Version

`1.0.0`

## Approval Metadata

| Field | Approved value |
|---|---|
| Approval ID | `RAA-B013-2026-001` |
| Status | Approved |
| Effective date | 2026-07-29 |
| Approval authority | Resolven Ask AI Governance Authority |
| Policy reviewer | Regulatory Reviewer role |
| Technical reviewers | Lead Product Architect and Principal AI Engineer roles |
| Machine contract | `ask-ai-decision-calibration-v1` |
| Governing blocker | B-013 |
| Authorized work | E3.7, E12.1, E12.6 |
| Review frequency | Quarterly and on every revision trigger |
| Supersedes | No prior calibration approval |

## Change History

| Version | Date | Change | Approval |
|---|---|---|---|
| 1.0.0 | 2026-07-29 | Initial Decision Engine golden-dataset, threshold, review, checksum, and release approval. | `RAA-B013-2026-001` |
