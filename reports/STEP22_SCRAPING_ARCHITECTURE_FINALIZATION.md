# Step 22 - Scraping Architecture Finalization & Source Page Refactor

Generated after implementing the curated source-page architecture.

## Objective

Freeze the discovery layer around curated crawl pages so the platform stops treating
government homepages, category pages, navigation pages, archives, and search pages as
valid discovery entrypoints.

This step intentionally did not add AI features, did not change the knowledge graph,
did not change the family registry, and did not redesign the frontend UI.

## Implementation Summary

Implemented:

- Added `source_pages` migration.
- Seeded only the approved crawl pages.
- Added SECI as a configured source so its tender page can be represented.
- Refactored scheduled/manual pipeline execution to start from `source_pages`.
- Removed Parallel Search fallback from the active source scraper path.
- Added page-level discovery audit metadata.
- Added `NO_PRIMARY_DOCUMENT` audit rows when a curated page produces no primary
  PDF or primary HTML notice.
- Added admin APIs for source CRUD, source page CRUD, crawl control, run detail,
  and source analytics.
- Updated seeded backend API/flow docs.

Not implemented:

- No frontend UI changes.
- No new AI extraction layers.
- No knowledge graph changes.
- No family registry changes.

## Tables Kept

### Core

- `sources`
- `documents`
- `document_versions`
- `events`
- `summaries`
- `crawl_runs`

### Audit

- `discovery_audit`
- `document_texts`
- `event_intelligence_audit`
- `regulatory_change_audit`

### Lineage

- `document_families`
- `document_family_assignments`
- `document_version_registry`
- `document_version_relationships`
- `deadline_history`

### Knowledge Graph

- `regulatory_graph_entities`
- `regulatory_graph_document_entities`
- `regulatory_graph_edges`
- `regulatory_graph_extractions`
- `regulatory_graph_stakeholders`
- `regulatory_graph_obligations`
- `regulatory_graph_deadlines`
- `regulatory_graph_family_enrichment`

### Product

- `profiles`
- `subscriptions`
- `user_event_state`
- `digests`
- `digest_events`
- `chat_messages`
- `notifications_log`

## New Table

Migration:

- `apps/api/backend/migrations/0011_source_pages.sql`

Table:

- `source_pages`

Fields:

| Column | Type | Purpose |
|---|---|---|
| `id` | `bigint identity primary key` | Source page ID |
| `source_id` | `bigint references sources(id)` | Parent source |
| `name` | `text` | Human-readable page name |
| `url` | `text` | Exact curated discovery URL |
| `page_type` | `text` | Listing type, such as `tender_listing` |
| `priority` | `int` | Crawl order within source |
| `enabled` | `boolean` | Enables/disables this page |
| `last_crawled_at` | `timestamptz` | Last successful crawl timestamp |
| `created_at` | `timestamptz` | Creation timestamp |
| `updated_at` | `timestamptz` | Update timestamp |

Constraints and indexes:

- Primary key: `id`
- Unique: `(source_id, url)`
- Index: `source_id`
- Index: `(enabled, priority, id)`
- Index: `page_type`
- RLS enabled with authenticated read policy.

## Seeded Source Pages

Only these pages are seeded and allowed by the active crawl loader.

| Source | Page Name | URL | Page Type | Priority |
|---|---|---|---|---:|
| MNRE | Current Notices | `https://mnre.gov.in/en/notice-category/current-notices/` | `notice_listing` | 10 |
| MNRE | Monthly Updates | `https://mnre.gov.in/en/monthly-updates/` | `digest_listing` | 20 |
| CERC | Public Notice | `https://cercind.gov.in/public-notice.html` | `public_notice_listing` | 10 |
| CERC | Suo Motu Petitions / Staff Papers / Notices | `https://cercind.gov.in/SPN.html` | `spn_listing` | 20 |
| CERC | Notice / Letter | `https://cercind.gov.in/notice-letter.html` | `notice_letter_listing` | 30 |
| SECI | Tenders | `https://www.seci.co.in/tenders` | `tender_listing` | 10 |
| MoP | What's New | `https://www.powermin.gov.in/whats-new` | `whats_new_listing` | 10 |

Runtime enforcement:

- `list_enabled_source_pages(...)` filters active crawl pages against this URL allowlist.
- Admins may manage page records, but the current production crawl path will not crawl
  pages outside this approved Step 22 list.

## Old Scraping Flow

```text
SOURCE
-> HOMEPAGE / SOURCE URL
-> GENERIC DISCOVERY
-> DOMAIN / SEARCH / NAVIGATION FALLBACKS
-> CANDIDATE URL
-> PRIMARY DOCUMENT CHECK
-> DOCUMENT
-> EVENT
```

Problems:

- Homepages generated junk candidates.
- Category pages generated stale or broad topic pages.
- Navigation links appeared as regulatory candidates.
- Archive and search pages created low-value discovery noise.
- Parallel Search fallback expanded discovery beyond curated source intent.
- Audit repeatedly showed high rejection rates and weak event yield.

## New Scraping Flow

```text
SOURCE
-> SOURCE PAGE
-> DISCOVERY
-> PRIMARY DOCUMENT URL
-> DOWNLOAD PDF / HTML
-> OCR IF REQUIRED
-> TEXT EXTRACTION
-> DOCUMENT
-> DOCUMENT VERSION
-> FAMILY REGISTRY
-> KNOWLEDGE GRAPH
-> INTELLIGENCE GATE
-> EVENT
-> DIGEST / CHAT / DASHBOARD
```

Active discovery starts at `source_pages`, not `sources.url`.

## Removed From Active Flow

The following concepts may remain in old code paths or historical reports, but are no
longer part of scheduled/manual production crawling:

- Homepage discovery
- Domain discovery
- Search page discovery
- Archive discovery
- Navigation discovery
- Category discovery
- Parallel Search fallback

## Discovery Rule

The active scraper only creates candidates when a curated source page links to:

- a primary PDF; or
- a plausible primary HTML notice/document page.

Otherwise:

- no event is created;
- no document is persisted;
- the rejection path is represented in `discovery_audit`;
- when a curated source page produces no primary documents, the audit reason is
  `NO_PRIMARY_DOCUMENT`.

## Affected Code

### Migration

- Added `apps/api/backend/migrations/0011_source_pages.sql`

### Models

- Updated `apps/api/backend/core/models.py`
- Added:
  - `SourcePayload`
  - `SourceUpdatePayload`
  - `SourcePagePayload`
  - `SourcePageUpdatePayload`
  - `CrawlTriggerResponse`
  - `SourceAnalyticsResponse`

### Repository

- Updated `apps/api/backend/core/repository.py`
- Added:
  - `create_source`
  - `update_source`
  - `delete_source`
  - `list_source_pages`
  - `list_enabled_source_pages`
  - `get_source_page`
  - `create_source_page`
  - `update_source_page`
  - `delete_source_page`
  - `mark_source_page_crawled`
  - `get_crawl_run`
  - `get_source_analytics`

### Scraper

- Updated `apps/api/backend/pipeline/agent_scraper.py`
- Added:
  - `scrape_source_page`
- Changed:
  - `scrape_source` is now legacy source-level discovery.
  - Active production crawling should use `scrape_source_page`.
  - Search fallback is no longer used by `scrape_source`.

### Pipeline

- Updated `apps/api/backend/pipeline/run_once.py`
- Added:
  - `run_crawl(source_id=None, page_id=None)`
- Changed:
  - `run_once()` now calls `run_crawl()`.
  - Pipeline reads enabled allowlisted `source_pages`.
  - Page crawl success updates `source_pages.last_crawled_at`.
  - Crawl results include `pages_attempted` and `pages_succeeded`.

### Admin API

- Updated `apps/api/backend/api/routes/admin.py`
- Replaced toggle-only admin source control with CRUD, pages, crawl control, runs,
  and analytics.

### Seeded Docs

- Updated `apps/api/backend/core/system_docs.py`
- Backend API docs now describe `source_pages` and new admin endpoints.
- Product flow docs now describe curated source-page discovery.

## New Admin API Surface

### Sources

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/admin/sources` | List sources |
| `POST` | `/admin/sources` | Create source |
| `PUT` | `/admin/sources/{id}` | Update source |
| `DELETE` | `/admin/sources/{id}` | Delete source |

Removed from backend route surface:

- `POST /admin/sources/{id}/toggle`

### Source Pages

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/admin/sources/{id}/pages` | List source pages |
| `POST` | `/admin/sources/{id}/pages` | Create source page |
| `PUT` | `/admin/pages/{id}` | Update source page |
| `DELETE` | `/admin/pages/{id}` | Delete source page |

### Crawl Control

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/admin/pages/{id}/crawl` | Crawl one enabled allowlisted page |
| `POST` | `/admin/sources/{id}/crawl` | Crawl all enabled allowlisted pages for one source |

### Runs

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/admin/runs` | List recent crawl runs |
| `GET` | `/admin/runs/{id}` | Read one crawl run |

### Analytics

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/admin/sources/{id}/analytics` | Source discovery/event analytics |

Analytics includes:

- source metadata
- total source pages
- enabled source pages
- documents total
- events total
- discovery candidates
- accepted/rejected discovery counts
- rejection reasons
- classifications
- latest related crawl run

## Migration Plan

1. Apply migrations through `0011_source_pages.sql`.
2. Confirm `source_pages` exists.
3. Confirm SECI exists in `sources`.
4. Confirm exactly seven seeded source pages are present.
5. Run `GET /admin/sources/{id}/pages` for MNRE, CERC, SECI, and MoP.
6. Trigger one controlled page crawl with `POST /admin/pages/{id}/crawl`.
7. Confirm `discovery_audit.metadata` includes:
   - `source_page_id`
   - `source_page_name`
   - `source_page_type`
8. Confirm successful page crawl updates `source_pages.last_crawled_at`.
9. Confirm full pipeline run uses `run_once() -> run_crawl() -> source_pages`.

## Sample Scrape Paths

### MNRE

Source:

- Ministry of New & Renewable Energy

Source pages:

- `https://mnre.gov.in/en/notice-category/current-notices/`
- `https://mnre.gov.in/en/monthly-updates/`

Expected path:

```text
MNRE
-> Current Notices or Monthly Updates source_page
-> primary PDF / primary HTML notice
-> download
-> extract text
-> documents
-> document_versions
-> document_families
-> regulatory_graph
-> event_intelligence_audit
-> events if the intelligence gate passes
```

Expected product value:

- renewable energy notices
- solar/wind policy changes
- scheme updates
- deadline-bearing notices

### CERC

Source:

- Central Electricity Regulatory Commission

Source page:

- `https://cercind.gov.in/public-notice.html`

Expected sample:

```text
CERC
-> Public Notice source_page
-> Draft Central Electricity Regulatory Commission (Power Market)
   (Second Amendment) Regulations, 2026
-> primary PDF
-> download
-> extract text
-> documents.title = Power Market (Second Amendment) Regulations, 2026
-> documents.issuing_body = CERC
-> documents.doc_type = AMENDMENT
-> document_families = CERC Power Market Regulations
-> regulatory_graph AFFECTS Power Exchanges
-> regulatory_graph HAS_DEADLINE 2026-06-26
-> event_intelligence_audit PASS
-> events include what changed, why it matters, stakeholders, and deadlines
```

Expected product value:

- consultations
- draft regulations
- power-market changes
- tariff/regulatory proceedings
- deadlines for stakeholder comments

### SECI

Source:

- Solar Energy Corporation of India

Source page:

- `https://www.seci.co.in/tenders`

Expected path:

```text
SECI
-> Tenders source_page
-> tender notice / RfS / bid document PDF
-> download
-> extract text
-> documents.doc_type = TENDER_DOCUMENT
-> regulatory_graph AFFECTS Solar Developers / Generators
-> regulatory_graph HAS_DEADLINE tender submission date
-> event_intelligence_audit PASS if document is current and actionable
-> events expose tender opportunity and deadline
```

Expected product value:

- solar procurement opportunities
- tender submission deadlines
- bid obligations
- developer relevance

### MoP

Source:

- Ministry of Power

Source page:

- `https://www.powermin.gov.in/whats-new`

Expected path:

```text
MoP
-> What's New source_page
-> order / notification / circular / amendment PDF or HTML notice
-> download
-> OCR if required
-> extract text
-> documents
-> document_versions
-> family registry
-> knowledge graph
-> intelligence gate
-> events
```

Expected product value:

- central power-sector policy updates
- obligations for DISCOMs, generators, and transmission entities
- RPO/REC and open-access changes
- compliance deadlines

## Product Impact

This step changes the product from:

```text
Crawler output filtered after the fact
```

to:

```text
Curated regulatory source-page pipeline
```

That improves:

- title quality
- candidate quality
- rejection explainability
- source maintenance
- product trust
- future source-specific extraction

## Known Boundary

Frontend admin UI was intentionally not updated in this step. The backend route
`POST /admin/sources/{id}/toggle` has been removed, but the existing frontend helper/UI
may still reference it until the next admin UI refactor.

