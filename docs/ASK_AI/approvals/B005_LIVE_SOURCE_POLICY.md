# B-005 Live Intelligence Source and Provenance Policy

## Executive Summary

This artifact approves the complete production policy for Resolven Ask AI Live Intelligence. Live Intelligence MAY retrieve current public information only from approved official publishers, contracted commercial-news services, and narrowly defined first-party industry publishers. Every item MUST retain source identity, publisher, publication time, retrieval time, license class, trust rank, and the exact live provenance lane. Live evidence MUST remain separate from Resolven's internal regulatory corpus and MUST NOT independently establish legal force, applicability, or a binding obligation.

This approval resolves blocker B-005 and authorizes engineering tasks E6.3, E6.7, and E11.9 subject to the controls below.

## Purpose

The purpose is to establish a deterministic source-admission, licensing, freshness, attribution, caching, failure, and confidence policy for production Live Intelligence.

## Scope

This policy governs:

- live web search, feed, API, and licensed-news retrieval;
- source admission and trust ranking;
- current-news and consultation time windows;
- provenance, duplicate handling, caching, and rate limiting;
- internal/live evidence separation;
- UI labels, attribution, and confidence ceilings;
- live-capability evaluation, rollout, and failure behavior.

It does not change the frozen definition of official internal evidence or authorize live material to become internal corpus evidence.

## Background

The frozen product specification requires an explicit live knowledge mode for current, latest, recent, breaking, news, and consultation questions. It also requires separate internal and live sections, visible dates and provenance, honest degradation, and a prohibition on presenting reporting as law. Engineering could not implement the live capability without an approved provider, license, source, and confidence policy.

## Problem Statement

Uncontrolled web retrieval can mix authoritative instruments with summaries, stale duplicates, unlicensed text, or hostile pages. Without deterministic admission and display rules, the system could misstate legal status, conceal origin, violate access terms, or elevate commercial reporting above official evidence.

## Final Approved Decision

Resolven Ask AI SHALL operate a three-class live-provider model:

1. **Official Direct Retrieval:** HTTPS retrieval from the approved official-domain registry by publisher API, RSS/Atom feed, sitemap, or bounded document/page fetch.
2. **Parallel.ai Source-Retaining Retrieval:** a Parallel.ai capability that returns inspectable source URLs and source-grounded output, including its Basis-capable product where contracted. A source-free chat or synthesis response MUST NOT be admitted as live evidence.
3. **Licensed Commercial News:** contracted Reuters, Dow Jones/Factiva, or another provider added through a policy revision with equivalent provenance and licensing controls.

Direct scraping of paywalled commercial content, bypass of technical access controls, unlicensed full-text retention, and source-free live synthesis are forbidden.

## Policy

### Approved official publishers

The initial official-domain registry SHALL contain exact HTTPS hosts for:

| Publisher class | Approved host roots |
|---|---|
| Gazette of India | `egazette.nic.in` |
| Ministry of Power | `powermin.gov.in` |
| Central Electricity Regulatory Commission | `cercind.gov.in` |
| Central Electricity Authority | `cea.nic.in` |
| Ministry of New and Renewable Energy | `mnre.gov.in` |
| Press Information Bureau | `pib.gov.in` |
| Solar Energy Corporation of India | `seci.co.in` |
| Grid Controller of India | `grid-india.in` |

State commissions and additional government bodies MAY be used only after their exact hosts, publisher identity, jurisdiction, and TLS behavior are entered in the versioned official-domain registry. A `.gov.in` or `.nic.in` suffix alone does not establish admission. The retrieved page MUST have a demonstrable publisher relationship to the issuing body.

### Commercial and industry sources

Commercial-news evidence MUST originate through an active enterprise license. Reuters and Dow Jones/Factiva are approved provider families, but a connector MUST remain disabled until contract entitlement, API credentials, retention rights, and attribution text are recorded in deployment configuration.

First-party industry sources, including regulated-entity announcements, exchange filings, and named company media rooms, MAY establish that the publisher made an announcement. They MUST NOT establish that a regulatory duty is legally operative.

Social posts, anonymous pages, unmoderated forums, content farms, scraped aggregators, AI-generated pages without attributable primary sources, and unattributed snippets are not admissible.

### Licensing assumptions

Official public content MAY be indexed and excerpted only when the publisher's terms, robots policy, and access controls permit the retrieval method. Commercial content MUST be processed only under an active license. Unless a license explicitly permits full-text retention, the system SHALL retain only provider identity, canonical URL, headline, byline when supplied, publication time, retrieval time, source classification, content hash, and a quotation or snippet no longer than 500 Unicode characters. An unclear or expired entitlement requires metadata-only handling when permitted; otherwise the item MUST be excluded.

### Trust ranking

| Rank | Source type | Permitted evidentiary use | Maximum live confidence |
|---|---|---|---|
| L1 | Operative official publication or regulator-issued current notice | Current official fact, subject to status and scope verification | High |
| L2 | Official draft, consultation, speech, press release, or proposal | Proposal, announcement, or consultation fact only | Medium |
| L3 | Licensed wire or licensed commercial reporting | Reported event, quotation, or market context | Medium |
| L4 | Established professional or national press | Corroborated current context | Medium |
| L5 | First-party industry announcement | Fact that the publisher announced or filed the item | Low, or Medium with independent corroboration |

Rank L1 does not bypass the frozen High-confidence gates. L2 through L5 MUST NOT be used as the sole basis for legal applicability, a binding deadline, or operative status.

### Freshness windows

Interpretation and filtering SHALL use the user's effective time zone, defaulting to Asia/Kolkata:

- `today`: publication time within the current local calendar day;
- `breaking`: rolling 72 hours;
- `news`: rolling 30 days unless the user supplies a bounded range;
- `recent`: rolling 90 days;
- `open consultation`: official closing time has not passed;
- `recently closed consultation`: closing time passed within 90 days.

Items outside the requested window MUST be excluded from the primary live result. They MAY appear in a clearly labeled historical-context section only when needed to explain the current event.

### Provenance and separation

Every live item MUST carry a stable evidence identity, canonical URL, original URL, publisher, provider, source type, trust rank, publication time or explicit `publication time unavailable`, retrieval time, requested time window, license class, content hash, and source title. Redirects MUST resolve only to HTTP or HTTPS hosts that pass admission checks.

Live and internal evidence MUST use different provenance lanes, response sections, citation collections, persistence fields, metrics, and UI badges. A live item MUST NOT be copied into the internal corpus lane by an answer request. Cross-lane reconciliation MAY link duplicate events but MUST retain both source identities and both original provenance paths.

### Duplicate handling

Duplicates SHALL be detected by canonical URL, normalized publisher and headline, content hash, and event fingerprint consisting of entity, event type, effective/publication date, and materially equivalent description. Exact duplicates SHALL render once with all provenance references. Near-duplicates MAY be clustered but MUST remain individually inspectable. An official source controls legal status when reporting conflicts with it; conflicting facts MUST remain visible and MUST trigger the frozen contradiction penalty.

### Caching

Fresh-result cache lifetimes are:

- L1 and L2 current official sources: 15 minutes;
- L3 and L4 news sources: 10 minutes;
- L5 announcements: 15 minutes;
- historical context older than 90 days: 24 hours;
- negative healthy no-match result: 5 minutes;
- provider-unavailable result: no shared negative cache beyond 30 seconds.

Cache keys MUST include provider, normalized query, time window, jurisdiction, source registry version, entitlement version, and policy version. Cached content MUST retain its original retrieval time and MUST NOT receive a new publication time. A failed refresh MAY return a previously admitted cached item only with a visible stale-cache label and a Low ceiling; it MUST NOT satisfy `today` or `breaking`.

### Rate limiting and failure handling

Each official host SHALL use a token bucket capped at 5 requests per second and 10 concurrent requests. Each commercial connector SHALL use the lower of its contractual limit or 10 requests per second and 20 concurrent requests. Per-user live searches are capped at 10 per minute with a burst of 3. Global live fan-out is capped at 8 simultaneous source branches per request.

The client SHALL honor `Retry-After`. Automated retries are limited to two attempts for idempotent retrieval, using bounded exponential backoff and jitter. Authentication, entitlement, robots, invalid-output, and permanent 4xx failures MUST NOT be retried within the request.

A completed, healthy search with no admitted items is `No match`. Timeout, entitlement failure, DNS/TLS failure, rate exhaustion, invalid provider output, or circuit-open state is `Unavailable` or `Timed out`. These outcomes MUST never be collapsed.

### Attribution and UI badges

Each live source card MUST display publisher, source type, publication time, retrieval time, safe external link, and one exact badge:

- `Official live source` for L1 or L2;
- `Licensed news` for L3;
- `Live news source` for L4;
- `Industry announcement` for L5;
- `Stale cached live source` when stale fallback is used.

Every live section MUST display: `Live sources provide current context and do not by themselves establish legal force or applicability.`

## Technical Requirements

- Source registry and entitlement configuration MUST be versioned, immutable per run, schema validated, and included in telemetry.
- URL parsing MUST reject credentials, non-HTTP schemes, loopback, link-local, private-network, and disallowed redirect targets.
- Retrieval MUST enforce response-size, content-type, decompression, redirect, connection, and hard-timeout limits.
- Evidence identity MUST survive deduplication, persistence, refresh, verification, and rendering.
- Provider output MUST pass strict schema validation before admission.
- Publication times MUST retain source time zone when available and store a normalized UTC value.
- Live retrieval MUST emit typed `Satisfied`, `Partial`, `No match`, `Timed out`, `Unavailable`, and `Invalid output` outcomes.

## Engineering Rules

- Connectors MUST implement the common live-capability contract and MUST NOT write directly into internal evidence tables.
- Admission MUST occur before synthesis.
- Synthesis MUST cite only admitted evidence identities.
- Policy, registry, provider, and entitlement versions MUST be recorded on every run.
- Secrets MUST be supplied through the approved secret manager and MUST NOT enter logs, fixtures, source cards, or persisted request payloads.
- A connector without deterministic failure mocks and license-state tests MUST remain disabled.

## Allowed Behavior

- Query multiple approved providers in parallel within the bounded fan-out.
- Use an L3 or L4 report to identify a current event and direct the user to official verification.
- Consolidate duplicate event cards while preserving every underlying source.
- Return internal evidence when live retrieval is unavailable, provided the live limitation is explicit.
- Use live-only prose for non-legal current context after claim verification passes.

## Forbidden Behavior

- Present a live report as an operative law, final regulatory status, or binding user obligation.
- Cite an unapproved domain, hidden redirect, source-free provider output, or unattributed snippet.
- Bypass a paywall, CAPTCHA, robots restriction, contractual quota, or technical access control.
- Mix live citations into an internal-source list or assign internal authority to a live item.
- Fabricate or infer publication time, publisher, title, URL, quotation, or license.
- Suppress a material conflict between live and official evidence.
- Raise confidence above the trust-rank ceiling.

## Rollout Rules

1. Connector contract, security, license, and deterministic fixture tests MUST pass.
2. Shadow evaluation under E6.7 MUST run for at least 14 consecutive days and 500 eligible requests.
3. Admission precision MUST be at least 99%; provenance completeness MUST be 100%; prohibited-domain admission MUST be zero.
4. Rollout SHALL proceed at 1%, 10%, 25%, 50%, then 100%, with at least 24 hours at each stage.
5. A new provider, source class, or retention entitlement requires a policy minor-version approval before enablement.

## Rollback Rules

The live feature flag or an individual provider flag MUST disable new calls immediately. Rollback MUST preserve admitted evidence and audit records already shown to users. Provider credentials SHALL be revoked when entitlement or compromise triggers rollback. The product SHALL fall back to internal evidence and the exact unavailable disclosure. Cached commercial text exceeding post-rollback entitlement MUST be deleted or reduced to permitted metadata within 24 hours.

## Security Requirements

- Enforce SSRF defenses, DNS re-resolution controls, TLS certificate validation, content-size limits, MIME validation, and safe HTML/text extraction.
- Treat all retrieved content as untrusted data and prevent prompt, markup, script, and formula injection.
- Encrypt provider credentials and retained licensed metadata in transit and at rest.
- Record access to licensed sources without logging user secrets or full licensed text.
- Apply tenant and user authorization to persisted live evidence.
- Security SHALL review each connector before production and annually thereafter.

## Observability Requirements

Dashboards MUST expose provider requests, admitted items, rejected items by deterministic reason, no-match rate, unavailable rate, timeout rate, latency percentiles, cache hit/stale rates, quota state, circuit state, trust-rank mix, duplicate ratio, provenance completeness, and live/internal lane contamination. Metrics MUST use bounded labels. Alerts MUST fire on any lane contamination, prohibited-domain admission, provenance completeness below 100%, entitlement failure, or sustained error/latency breach under B-007.

## Testing Requirements

Testing MUST include unit, contract, integration, security, license-state, failure-injection, time-window, redirect, SSRF, cache, deduplication, attribution, accessibility, confidence-ceiling, and internal/live separation suites. Golden cases MUST cover each source rank, every time window, identical and conflicting duplicates, missing publication time, expired entitlement, rate limiting, stale cache, malicious content, and all terminal outcomes.

## Acceptance Criteria

- All approved providers and only approved providers can produce admitted live evidence.
- Official-domain registry matching is exact, versioned, and redirect safe.
- Licensing and retention behavior is testable for active, unclear, expired, and revoked entitlements.
- Freshness filtering matches the defined windows under fixed-clock tests.
- Provenance fields and UI attribution are complete for 100% of rendered sources.
- Live/internal lane contamination is zero.
- Healthy no-match and provider failure remain distinct.
- Duplicate consolidation retains all source identities and material conflicts.
- Confidence never exceeds the approved source-rank ceiling.
- E6.3, E6.7, and E11.9 can proceed without another source-policy decision.

## Review Checklist

- [x] Providers and official domains approved.
- [x] Commercial licensing assumptions fixed.
- [x] Freshness and cache windows fixed.
- [x] Trust ranks and confidence ceilings fixed.
- [x] Provenance, duplicate, and lane-separation rules fixed.
- [x] Rate limits and failure outcomes fixed.
- [x] Attribution and UI badges fixed.
- [x] Security, rollout, rollback, testing, and observability gates fixed.

## Future Revisions

Revisions require a new semantic version, documented change rationale, Security review for connector or domain changes, Regulatory review for trust or confidence changes, and Product/SRE review for user disclosure or operating-limit changes. Existing runs remain bound to the policy version recorded when they executed.

## Version

`1.0.0`

## Approval Metadata

| Field | Approved value |
|---|---|
| Approval ID | `RAA-B005-2026-001` |
| Status | Approved |
| Effective date | 2026-07-29 |
| Approval authority | Resolven Ask AI Governance Authority |
| Accountable roles | Lead Product Architect; Principal AI Engineer; Principal Platform Engineer; SRE; Security Engineer; Regulatory Reviewer |
| Governing blocker | B-005 |
| Authorized work | E6.3, E6.7, E11.9 |
| Review frequency | Quarterly and upon any revision trigger |
| Supersedes | No prior approved policy |

## Change History

| Version | Date | Change | Approval |
|---|---|---|---|
| 1.0.0 | 2026-07-29 | Initial production Live Intelligence source, licensing, provenance, and confidence approval. | `RAA-B005-2026-001` |
