# Step 24.5 - Crawl Checkpoint Audit

Generated: 2026-06-23

## Executive Verdict

The platform does **not** currently have a true crawl checkpoint per source page.

It stores `source_pages.last_crawled_at`, but that is only a telemetry timestamp saying
"this page completed a crawl recently." It is not a source checkpoint because it does
not store the last seen candidate URL, post ID, tender ID, publication date, row
fingerprint, ETag, or content marker.

Current behavior is:

- Listing pages are fetched every run.
- Candidate rows are parsed every run.
- Up to `SOURCE_PAGE_LIMIT = 8` candidates per page are returned to the pipeline.
- Every returned candidate is downloaded and text-extracted every run.
- Duplicate events are suppressed only after download/extraction, using
  `documents.url_hash` and `document_versions(document_id, file_hash)`.

So the crawler is **not incremental**. It is a capped repeated scan.

## Code Evidence

| Area | Evidence |
| --- | --- |
| Source pages include timestamp only | `apps/api/backend/migrations/0011_source_pages.sql:1`, `last_crawled_at` at line 9 |
| Enabled pages loaded with timestamp | `apps/api/backend/core/repository.py:374`, `sp.last_crawled_at` selected at line 400 |
| Timestamp update only | `apps/api/backend/core/repository.py:486`, `last_crawled_at = now()` at line 493 |
| Crawl loads pages then scrapes each page | `apps/api/backend/pipeline/run_once.py:38`, `scrape_source_page(page)` at line 69 |
| Primary docs acquired after discovery | `apps/api/backend/pipeline/run_once.py:71` |
| Page marked crawled before persistence | `apps/api/backend/pipeline/run_once.py:78`, persistence happens later at line 106 |
| Parser cap | `apps/api/backend/pipeline/agent_scraper.py:79`, returned cap at line 105 |
| Candidate download always happens after pre-quality | `apps/api/backend/pipeline/primary_document.py:74`, `_fetch_bytes` |
| Document URL dedupe | `apps/api/backend/core/repository.py:894`, `on conflict (url_hash)` at line 938 |
| Version/file dedupe | `apps/api/backend/core/repository.py:986`, schema unique key in `0001_init.sql:62` |
| Crawl run is run telemetry only | `apps/api/backend/migrations/0001_init.sql:142` |

## Configured Source Page Checkpoint Status

All configured source pages have a `last_crawled_at` value after the latest clean-room
run. None has a reliable source checkpoint.

| Source | Source Page | Stored? | Where Stored | Field Acting As Checkpoint | Reliable? | Stops Early? | Current Classification |
| --- | --- | --- | --- | --- | --- | --- | --- |
| CERC | Public Notice | Partially | `source_pages` | `last_crawled_at` | No | No | Capped repeated scan |
| CERC | Suo Motu Petitions / Staff Papers / Notices | Partially | `source_pages` | `last_crawled_at` | No | No | Capped repeated scan |
| CERC | Notice / Letter | Partially | `source_pages` | `last_crawled_at` | No | No | Capped repeated scan |
| MNRE | Current Notices | Partially | `source_pages` | `last_crawled_at` | No | No | Capped repeated scan |
| MNRE | Monthly Updates | Partially | `source_pages` | `last_crawled_at` | No | No | Capped repeated scan |
| MoP | What's New | Partially | `source_pages` | `last_crawled_at` | No | No | Capped repeated scan |
| SECI | Tenders | Partially | `source_pages` | `last_crawled_at` | No | No | Capped repeated scan |

Why `last_crawled_at` is not reliable:

- It records crawler completion time, not source publication state.
- It cannot answer "which row was last seen?"
- It cannot handle a source backdating a notice.
- It cannot handle edits to an existing notice above or below the latest row.
- It cannot prevent repeated downloads.
- It is updated before `persist_extracted_documents`, so a later persistence failure
  can still leave the page looking successfully crawled.

## Latest Run Metrics

Latest run:

- `crawl_runs.id`: 1
- Status: `success`
- Started: `2026-06-22T18:01:53Z`
- Finished: `2026-06-22T18:17:26Z`
- Runtime: about 15.5 minutes
- Source pages attempted: 7
- Candidates discovered: 45
- Candidates downloaded/text-extracted: 45
- Accepted primary documents: 39
- Primary rejections: 6
- Events created: 20

Per source page:

| Source | Source Page | Candidates | Downloaded/Text Extracted | Accepted Primary | Rejected Primary |
| --- | --- | --- | --- | --- | --- |
| CERC | Public Notice | 6 | 6 | 5 | 1 |
| CERC | Suo Motu Petitions / Staff Papers / Notices | 8 | 8 | 7 | 1 |
| CERC | Notice / Letter | 3 | 3 | 3 | 0 |
| MNRE | Current Notices | 4 | 4 | 2 | 2 |
| MNRE | Monthly Updates | 8 | 8 | 8 | 0 |
| MoP | What's New | 8 | 8 | 6 | 2 |
| SECI | Tenders | 8 | 8 | 8 | 0 |

## Current Crawl Behavior

### Full Scan

No, not a full archive scan. The crawler does not paginate every archive page.

### Partial Scan

Yes. It scans the configured current/listing/API page and caps returned candidates
to 8 per page. Some parsers may inspect more rows internally before the final cap,
but the pipeline receives at most 8 candidates per page.

### Incremental Scan

No. No parser receives or checks a durable checkpoint. No parser stops when it
reaches a prior candidate. No source page stores the top row, last row, source
record ID, high-watermark publication date, or row fingerprint.

Best description: **capped repeated scan with downstream duplicate suppression**.

## Reprocessing Estimate

If the same source pages are run again with no upstream changes:

- Listing/API requests still happen for all 7 source pages.
- Parser selection still happens for the same 45 candidate URLs.
- Primary document downloads still happen for all 45 candidate URLs.
- Text extraction still happens for all 45 candidate URLs.
- The 39 accepted documents still flow into persistence and intelligence checks.
- The 6 rejected low-content documents are also repeatedly downloaded because there
  is no durable rejected-candidate checkpoint.
- New events should likely be 0 for unchanged files because
  `document_versions(document_id, file_hash)` prevents duplicate versions/events.

So the current system avoids duplicate **events**, but it does not avoid duplicate
**work**.

## Downloads That Could Be Avoided

On an unchanged run, a proper checkpoint could avoid approximately:

- 45 primary document downloads.
- 45 text extraction attempts.
- 39 repeated accepted-document persistence/intelligence passes.
- 6 repeated insufficient-content downloads.
- SECI detail-page fetches for old tender rows.
- MoP attachment API calls for old posts.

The listing/API page itself should still be fetched, because it is the cheap way
to discover whether anything new appeared.

Expected no-change runtime reduction:

- Current latest runtime: about 15.5 minutes.
- Estimated checkpointed no-change runtime: about 1-3 minutes.
- Expected reduction: roughly 80-90%.

Most savings would come from SECI and MoP because they contribute large PDFs and
the longest page processing time.

## Why Existing Deduplication Is Not Enough

Existing dedupe is useful but late:

- `documents.url_hash` dedupes by canonical document URL.
- `document_versions(document_id, file_hash)` prevents duplicate versions.
- `document_texts.content_hash` dedupes extracted text storage.

But these checks happen after the system has already:

1. Downloaded the primary document.
2. Extracted text or attempted OCR.
3. Computed hashes.
4. Built candidate quality/intelligence state.

That protects database correctness, not crawler efficiency.

## Minimal Recommended Schema

Create a single table:

```sql
create table source_page_checkpoints (
  id bigint generated always as identity primary key,
  source_page_id bigint not null references source_pages(id) on delete cascade,
  checkpoint_key text not null,
  checkpoint_url text,
  checkpoint_title text,
  checkpoint_issue_date date,
  checkpoint_published_at timestamptz,
  checkpoint_source_record_id text,
  checkpoint_content_hash text,
  checkpoint_payload jsonb not null default '{}',
  lookback_count int not null default 3,
  last_successful_run_id bigint references crawl_runs(id) on delete set null,
  last_successful_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (source_page_id)
);

create index source_page_checkpoints_key_idx
  on source_page_checkpoints (source_page_id, checkpoint_key);

create index source_page_checkpoints_date_idx
  on source_page_checkpoints (source_page_id, checkpoint_issue_date desc);
```

Field meanings:

| Field | Purpose |
| --- | --- |
| `source_page_id` | One durable checkpoint per configured source page. |
| `checkpoint_key` | Stable hash of source-page row identity. Prefer canonical primary URL; fallback to source record ID plus title/date. |
| `checkpoint_url` | Last top accepted/seen primary document URL. |
| `checkpoint_title` | Human-readable debug value. |
| `checkpoint_issue_date` | Date shown by the source page, if available. |
| `checkpoint_published_at` | Timestamp when the source exposes one, especially API sources. |
| `checkpoint_source_record_id` | Source-native ID such as MoP post ID, SECI tender ID, CERC petition number. |
| `checkpoint_content_hash` | Optional last known text/content hash for top candidate. |
| `checkpoint_payload` | Source-specific extras: tender reference, attachment ID, row number, raw date text, API cursor. |
| `lookback_count` | Safety window to re-check a few already-seen rows. |
| `last_successful_run_id` | Crawl run that advanced this checkpoint. |
| `last_successful_at` | Time the checkpoint was advanced. |

## Update Logic

Recommended flow:

1. Load `source_page_checkpoints` with `source_pages`.
2. Parser emits ordered candidates with a stable `candidate_key`.
3. Process candidates from newest to oldest.
4. Continue until:
   - checkpoint key is reached, and
   - at least `lookback_count` old candidates have been inspected, or
   - candidate date is older than checkpoint date and URL/key is already known.
5. Download only candidates above the stop point or inside the safety lookback.
6. Persist documents/events.
7. Advance the checkpoint only after the page-level pipeline and persistence succeed.
8. Store the newest successfully observed candidate as the checkpoint, not merely the
   newest successfully accepted event. This matters because some valid source rows
   may be rejected later for insufficient text or low product significance.

## Rollback Behavior

Do not advance the checkpoint when:

- Listing fetch fails.
- Parser fails.
- Primary acquisition fails for the page in a way that prevents reliable ordering.
- Database persistence fails.
- The run is cancelled mid-page.

If a source page partially succeeds:

- Keep the old checkpoint.
- Record page failure in `crawl_runs.errors`.
- Keep discovery audit rows for debugging.
- Retry from the old checkpoint next run.

This is stricter than current behavior, where `last_crawled_at` is updated before
`persist_extracted_documents`.

## Duplicate Protection

Use layered protection:

1. Parser-level checkpoint prevents repeated old candidate processing.
2. Existing `documents.url_hash` prevents duplicate document rows.
3. Existing `document_versions(document_id, file_hash)` prevents duplicate versions.
4. Existing `document_texts.content_hash` prevents duplicate text blobs.
5. Discovery audit remains append-only for observability.

Do not rely only on dates. Several government portals backdate notices, edit old
rows, or reorder links. The safest minimal checkpoint key is:

```text
sha256(source_page_id + canonical_primary_url)
```

Fallback when primary URL is unavailable before detail resolution:

```text
sha256(source_page_id + source_record_id + normalized_title + issue_date)
```

## Source-Specific Checkpoint Keys

| Source Page | Preferred Checkpoint Key | Safety Notes |
| --- | --- | --- |
| MNRE Current Notices | Canonical PDF URL | Re-check 2-3 rows because old notices can be edited. |
| MNRE Monthly Updates | Canonical monthly PDF URL plus month | Low volatility; easy checkpoint. |
| CERC Public Notice | Canonical PDF URL | Historical page; checkpoint mostly avoids repeated stale downloads. |
| CERC SPN | Petition number plus selected newspaper PDF URL | Do not key only on Electricity Act text; many valid rows mention it. |
| CERC Notice / Letter | Canonical PDF URL | Mostly historical; checkpoint high value for avoiding stale rows. |
| SECI Tenders | Tender ID/reference plus detail URL, then primary PDF URL | Stop before following detail pages for known tender rows. |
| MoP What's New | WordPress post ID plus attachment ID/PDF URL | Stop before resolving attachments for old posts. |

## Recommendation

Implement `source_page_checkpoints` before expanding sources further.

Priority:

1. Add the table.
2. Extend `DiscoveredDoc` or introduce an internal `CandidateCheckpoint` value with
   `candidate_key`, `source_record_id`, `source_page_id`, and `published_at`.
3. Update parsers to emit ordered candidates and stop at checkpoint plus lookback.
4. Move checkpoint advancement to after document/event persistence succeeds.
5. Keep `source_pages.last_crawled_at` as monitoring telemetry only.

Expected result:

- No-change crawls become cheap listing checks.
- Old PDFs are not repeatedly downloaded.
- Rejected insufficient-content files are not repeatedly downloaded.
- Event dedupe remains intact.
- Runtime should drop from about 15.5 minutes to roughly 1-3 minutes on unchanged
  curated pages.

## Final Answer

The foundation for checkpointing is **missing**. The current system has run telemetry
and downstream duplicate protection, but not source-page incremental crawling.

Classification:

```text
Current crawl behavior: capped repeated scan
Incremental checkpointing: no
Reliable source-page checkpoint: no
Repeated primary downloads per unchanged run: about 45
Avoidable primary downloads with checkpointing: about 45
Expected runtime reduction: about 80-90% on unchanged runs
```
