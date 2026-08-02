# B-012 Dependency Security and Release-Gate Policy

## Executive Summary

This artifact approves the dependency security policy for Resolven Ask AI. Critical and High exploitable runtime vulnerabilities are zero-tolerance production release gates. Critical findings require mitigation within 4 hours and a fixed version within 24 hours; High findings require mitigation within 1 business day and a fixed version within 7 calendar days. Patch and compatible minor upgrades are routine; major upgrades are isolated changes. Lockfiles are immutable generated assets and every release carries auditable scan and SBOM evidence.

This approval resolves blocker B-012, authorizes remediation of the identified Next.js, PostCSS, and Sharp advisories, and unblocks E12.3 and E12.6 subject to passing gates.

## Purpose

The purpose is to define dependency upgrade strategy, security SLAs, review cadence, severity response, patch windows, audit evidence, lockfile controls, rollback, exceptions, and release gates.

## Scope

This policy covers direct and transitive production, development, build, test, container, operating-system, GitHub Action, Python, Node.js, and frontend dependencies used by Ask AI and its delivery pipeline.

## Background

Repository audit identified unresolved High-severity advisories in the web dependency graph, including Next.js, PostCSS, and Sharp-related paths. Engineering needed authorization to upgrade and deterministic rules for handling current and future findings.

## Problem Statement

Uncoordinated upgrades can introduce regressions, while delayed security patches leave known exploit paths. A deterministic policy must state how fast findings are contained and patched, what evidence permits release, and how dependency state remains reproducible.

## Final Approved Decision

Engineering SHALL upgrade affected dependencies to the lowest maintained, compatible versions that remove all Critical and High advisories in the production dependency graph. The exact fixed versions SHALL be selected from current authoritative registry and vendor advisory metadata at implementation time and locked by the reviewed package manager. Blind forced upgrades and audit-result suppression are forbidden.

The production release gate is zero known Critical or High vulnerabilities in shipped runtime dependencies. A temporary exception is permitted only under the explicit exception process below and does not mark the vulnerability resolved.

## Policy

### Upgrade strategy

1. Apply a direct dependency patch or compatible minor upgrade when it resolves the transitive advisory.
2. Apply package-manager overrides or resolutions only when the upstream fixed transitive version is compatible, documented, and tested.
3. Isolate major-version upgrades in a dedicated task with migration notes, compatibility tests, and rollback.
4. Remove an unused vulnerable dependency when removal has lower product risk than upgrade.
5. Replace an unmaintained dependency when no supported fixed version exists.

The Next.js, PostCSS, and Sharp advisory set is explicitly approved for remediation under this strategy. Production compatibility and security gates determine completion.

### Security SLA

| Severity | Initial triage | Required mitigation | Fixed release deadline |
|---|---:|---:|---:|
| Critical / CVSS 9.0–10.0 or known exploited | 1 hour | 4 hours | 24 hours |
| High / CVSS 7.0–8.9 | 4 business hours | 1 business day | 7 calendar days |
| Medium / CVSS 4.0–6.9 | 3 business days | 14 calendar days when reachable | 30 calendar days |
| Low / CVSS below 4.0 | 10 business days | Next planned cycle | 90 calendar days |

`Known exploited`, remote code execution, authentication bypass, cross-tenant access, secret disclosure, supply-chain compromise, or reachable SSRF is treated as Critical regardless of published score.

Mitigation can be a feature disable, dependency removal, network isolation, WAF rule, capability circuit, input restriction, or rollback only when Security documents that it blocks the exploit path. Mitigation does not replace the fixed-release deadline.

### Review cadence

- every pull request: lockfile-aware dependency, license, secret, and static scan;
- every default-branch build: full production dependency audit;
- daily: advisory and malware scan of the current deployment graph;
- weekly: Security triage of open findings, stale packages, and exceptions;
- monthly: planned patch/minor upgrade cycle;
- quarterly: SBOM reconciliation, license review, unmaintained-package review, and restore rehearsal;
- immediately: scan after a material vendor advisory or supply-chain event.

### Severity handling and reachability

Security SHALL validate package identity, installed version, affected range, dependency path, shipped artifact, exploit prerequisites, public exploit status, and application reachability. An unreachable finding remains recorded; it MAY receive a lower remediation priority only with reproducible reachability evidence. It MUST NOT be omitted from audit output.

### Patch windows

Critical fixes may deploy at any time through the emergency change path. High fixes deploy in the next safe window within 7 calendar days. Medium and Low fixes use the monthly cycle unless exploit conditions raise severity. Security fixes are not held for unrelated feature scope.

### Lockfile policy

`package-lock.json`, Python requirement locks where present, container digests, and action version pins are canonical generated assets. They MUST be committed with the manifest change, generated by the repository-approved toolchain, and reviewed for unexpected package, registry, integrity, script, license, and transitive changes. Manual lockfile editing, deletion to hide drift, unlocked production install, and permissive floating versions are forbidden. CI MUST use reproducible frozen-lock installation.

### Exception policy

A temporary exception requires a unique risk ID, package/path/version, severity, exploitability evidence, business reason, compensating controls, affected deployments, owner, expiration, and approval by Security, SRE, and Product Architecture. Critical exceptions expire within 72 hours; High exceptions expire within 14 calendar days. Renewal requires new evidence and approval. Regulatory or cross-tenant integrity risks cannot receive an exception.

## Technical Requirements

- Scanners MUST inspect production-pruned and full development graphs separately.
- SBOMs MUST use CycloneDX or SPDX and bind to the release artifact digest.
- Container bases and binary packages MUST be digest pinned.
- Registry integrity metadata and install scripts MUST be validated.
- CI MUST fail on scanner execution failure, malformed output, or unavailable vulnerability database; it MUST not treat those states as clean.
- Scan evidence MUST include tool/version, advisory database time, manifest and lockfile hashes, artifact digest, findings, exceptions, and verdict.

## Engineering Rules

- Use the smallest compatible upgrade set that clears findings and passes regression.
- Do not run blanket `--force` or disable peer-dependency checks as a security fix.
- New direct dependencies require purpose, maintenance, license, size, security history, and alternative analysis.
- Production code MUST NOT depend on development-only packages at runtime.
- Package scripts with network, binary download, or native build behavior require review.
- Dependency changes MUST include affected unit, integration, type, build, compatibility, security, and smoke tests.

## Allowed Behavior

- Use an exact override for a transitive fixed version with compatibility evidence.
- Remove unused packages and regenerate the lockfile.
- Ship a security-only patch outside the normal release train.
- Temporarily disable an affected capability under an approved mitigation.
- Roll back to a still-supported, non-vulnerable release.

## Forbidden Behavior

- Suppress, ignore, downgrade, or reclassify a finding to pass CI without evidence and approval.
- Release a known Critical or High runtime vulnerability without a current exception.
- copy packages from unapproved registries or unverified archives.
- use floating container tags or unpinned production GitHub Actions.
- manually edit integrity hashes or lockfile package records.
- disclose exploit details or credentials in public build logs.

## Rollout Rules

Dependency changes SHALL pass clean install, lockfile diff review, audit, SBOM, backend/frontend tests, typecheck, production build, smoke tests, and affected integration/E2E tests. Canary progression is 10%, 25%, 50%, and 100% for runtime-framework or native-binary upgrades. Each stage requires stable error, latency, memory, CPU, image-processing, and rendering metrics for one normal traffic interval.

## Rollback Rules

Every dependency release MUST retain the previous signed artifact and lockfile. Rollback is triggered by regression, crash, memory leak, output corruption, security-control failure, or SLO breach. Rollback MUST NOT return to a vulnerable version unless Security confirms that an active compensating control blocks exposure and an unexpired exception exists. If no safe prior artifact exists, disable the affected capability.

## Security Requirements

Dependency sources MUST be allowlisted; credentials MUST use scoped tokens and secret storage; provenance attestations and signatures SHALL be verified where available. Build workers MUST be ephemeral and least privileged. Install scripts and native modules require sandboxing or controlled builders. Security retains authority to freeze a release or revoke an artifact on compromise evidence.

## Observability Requirements

Dashboards MUST expose findings by severity, reachability, age, package, dependency path, owner, SLA time remaining, exception expiry, scan freshness, SBOM coverage, outdated/unmaintained count, and release artifact. Alerts fire on any new Critical/High, scanner failure, lockfile drift, expired exception, unknown artifact, or missed SLA.

## Testing Requirements

Tests MUST cover clean reproducible install, lockfile immutability, application build/typecheck, API and UI regression, native-module execution, image processing where Sharp is present, CSS processing where PostCSS is present, framework routing/rendering where Next.js is present, security scanning, SBOM generation, malicious package-name detection, and rollback to the previous safe artifact.

## Acceptance Criteria

- The production graph contains zero unexcepted Critical or High findings.
- Next.js, PostCSS, and Sharp advisory paths resolve to non-affected versions or are removed.
- Lockfile and artifact builds are reproducible.
- Required backend, frontend, integration, security, and smoke tests pass.
- SBOM and scan evidence bind to the released artifact.
- No expired or incomplete exception exists.
- E12.3 and E12.6 can proceed without another dependency-policy decision.

## Review Checklist

- [x] Upgrade strategy approved.
- [x] Security SLA and patch windows approved.
- [x] Severity and reachability handling approved.
- [x] Review and audit cadence approved.
- [x] Lockfile, exception, rollback, and release gates approved.
- [x] Current Next.js, PostCSS, and Sharp remediation authorized.

## Future Revisions

Revisions require a new semantic version and Security approval. Changes to Critical/High SLA, exception eligibility, lockfile integrity, or release gates additionally require Product Architecture and SRE approval. Tighter scanner rules and shorter remediation deadlines MAY be adopted through a minor version.

## Version

`1.0.0`

## Approval Metadata

| Field | Approved value |
|---|---|
| Approval ID | `RAA-B012-2026-001` |
| Status | Approved |
| Effective date | 2026-07-29 |
| Approval authority | Resolven Ask AI Governance Authority |
| Accountable owner | Security Engineering |
| Operational co-owner | SRE |
| Governing blocker | B-012 |
| Authorized work | Dependency remediation; E12.3; E12.6 |
| Review frequency | Weekly finding review; quarterly policy review |
| Supersedes | No prior dependency security approval |

## Change History

| Version | Date | Change | Approval |
|---|---|---|---|
| 1.0.0 | 2026-07-29 | Initial dependency security, SLA, audit, lockfile, exception, and release-gate approval. | `RAA-B012-2026-001` |
