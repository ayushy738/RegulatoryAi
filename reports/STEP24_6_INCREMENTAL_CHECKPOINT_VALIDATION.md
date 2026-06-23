# Step 24.6 - Incremental Crawl Checkpoint Validation

Generated: 2026-06-23T00:55:27

## Backup And Reset

- Backup before validation reset: `E:\RegulatoryAi\reports\backups\checkpoint_validation_backup_20260622T191506Z.json`
- Generated intelligence and checkpoint tables were truncated before Run 1 so the first crawl represented a fresh normal crawl.

## Headline Results

| Metric | Run 1 Fresh Crawl | Run 2 No Source Changes |
| --- | --- | --- |
| Run ID | 1 | 2 |
| Status | success | success |
| Runtime seconds | 554.6 | 21.4 |
| Candidates returned by parsers | 45 | 0 |
| Primary documents accepted | 39 | 0 |
| Events created | 19 | 0 |
| Discovery audit rows | 45 | 7 |
| Downloads/text extractions | 45 | 0 |
| Checkpoints advanced | 7 | 0 |

## Avoided Work

| Avoided Work | Value |
| --- | --- |
| Downloads avoided | 45 |
| Documents avoided | 39 |
| Extraction jobs avoided | 45 |
| Download avoidance | 100.0% |
| Runtime reduction | 96.1% |

## Per-Page Run Metrics

### Run 1

| Source | Page | Audit Rows | Downloads/Extractions | Accepted Primary | Rejected Primary | No Primary |
| --- | --- | --- | --- | --- | --- | --- |
| cerc | Notice / Letter | 3 | 3 | 3 | 0 | 0 |
| cerc | Public Notice | 6 | 6 | 5 | 1 | 0 |
| cerc | Suo Motu Petitions / Staff Papers / Notices | 8 | 8 | 7 | 1 | 0 |
| mnre | Current Notices | 4 | 4 | 2 | 2 | 0 |
| mnre | Monthly Updates | 8 | 8 | 8 | 0 | 0 |
| mop | What's New | 8 | 8 | 6 | 2 | 0 |
| seci | Tenders | 8 | 8 | 8 | 0 | 0 |

### Run 2

| Source | Page | Audit Rows | Downloads/Extractions | Accepted Primary | Rejected Primary | No Primary |
| --- | --- | --- | --- | --- | --- | --- |
| cerc | Notice / Letter | 1 | 0 | 0 | 1 | 1 |
| cerc | Public Notice | 1 | 0 | 0 | 1 | 1 |
| cerc | Suo Motu Petitions / Staff Papers / Notices | 1 | 0 | 0 | 1 | 1 |
| mnre | Current Notices | 1 | 0 | 0 | 1 | 1 |
| mnre | Monthly Updates | 1 | 0 | 0 | 1 | 1 |
| mop | What's New | 1 | 0 | 0 | 1 | 1 |
| seci | Tenders | 1 | 0 | 0 | 1 | 1 |

## Checkpoints After Run 2

| Source | Page | Record ID | Title | Last Run | Saved At | URL |
| --- | --- | --- | --- | --- | --- | --- |
| cerc | Public Notice | Notice190526.pdf | Notice: Conducting of Hearings through Video Conferencing/Hybrid Mode | 1 | 2026-06-22T19:24:47.373119+00:00 | https://cercind.gov.in/2026/whatsnew/Notice190526.pdf |
| cerc | Suo Motu Petitions / Staff Papers / Notices | 213/TD/2026 | 213/TD/2026 - Petition under Section 14 of the Electricity Act 2003 read with Regulation 6 of the CERC (Procedure, Terms and Conditions for  | 1 | 2026-06-22T19:24:48.513618+00:00 | https://cercind.gov.in/SPN/213-TD-2026 (Hindu-19.6.2026).pdf |
| cerc | Notice / Letter | Monthly-Trading-Information201123.pdf | Uploading of Monthly Information on the website of Trading Licensees-reg. | 1 | 2026-06-22T19:24:49.411206+00:00 | https://cercind.gov.in/2023/whatsnew/Monthly-Trading-Information201123.pdf |
| mnre | Current Notices | 202605251665091021.pdf | ALMM – No blanket extension of ALMM List-II beyond 01.06.2026 subject to Protection of Investments already made | 1 | 2026-06-22T19:24:45.143073+00:00 | https://cdnbbsr.s3waas.gov.in/s3716e1b8c6cd17b771da77391355749f3/uploads/2026/05/202605251665091021.pdf |
| mnre | Monthly Updates | May 2026 | Renewable Energy Policy and Regulatory update for May 2026 month (546 KB) | 1 | 2026-06-22T19:24:46.303103+00:00 | https://cdnbbsr.s3waas.gov.in/s3716e1b8c6cd17b771da77391355749f3/uploads/2026/06/20260612775650314.pdf |
| mop | What's New | 24609 | Implementation of decriminalisation measures under the Jan Vishwas (Amendment of Provisions) Act, 2026 | 1 | 2026-06-22T19:24:50.841409+00:00 | https://powermin.gov.in/static/uploads/2026/06/1aa18ca95f5e1f477b7a0ca36b8bade5.pdf |
| seci | Tenders | SECI000258 | RfS for assured Peak Supply of 4800 MWh (1200 MW x 4 Hrs.) from ISTS-Connected RE Projects (SECI-FDRE-IX) | 1 | 2026-06-22T19:24:51.793120+00:00 | https://www.seci.co.in/uploads/tenders/RfS_for_4800_MWh_Peak_Supply_(FDRE-IX)-_final_upload.pdf |

## Row Counts After Validation

| Table | Rows |
| --- | --- |
| events | 19 |
| summaries | 19 |
| document_versions | 39 |
| documents | 39 |
| document_texts | 39 |
| discovery_audit | 52 |
| event_intelligence_audit | 39 |
| regulatory_change_audit | 58 |
| document_family_assignments | 39 |
| document_version_registry | 39 |
| document_version_relationships | 0 |
| document_families | 38 |
| deadline_history | 391 |
| regulatory_graph_document_entities | 0 |
| regulatory_graph_edges | 0 |
| regulatory_graph_extractions | 0 |
| regulatory_graph_stakeholders | 0 |
| regulatory_graph_obligations | 0 |
| regulatory_graph_deadlines | 0 |
| regulatory_graph_family_enrichment | 0 |
| regulatory_graph_entities | 0 |
| source_page_checkpoints | 7 |
| crawl_runs | 2 |
| digests | 1 |
| digest_events | 19 |
| notifications_log | 0 |
| chat_messages | 0 |
| user_event_state | 0 |
| sources | 4 |
| source_pages | 7 |
| profiles | 4 |
| subscriptions | 0 |

## Verdict

- Downloads avoided: `45` of `45` (100.0%).
- Runtime reduction: `96.1%`.
- Run 2 created `0` events and accepted `0` primary documents.

Checkpoint validation passed: unchanged second crawls now avoid the expensive primary-document pipeline.

Note: the expected Run 1 event count was about 20. This validation produced 19
events while still matching the expected 45 candidates and 39 primary documents.
The difference came from downstream event intelligence gating, not checkpointing:
one MNRE monthly update was accepted as a primary document but rejected as
`EXPIRED_OPPORTUNITY`.
