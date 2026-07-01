# Step 25 Production Graph Validation

Generated at: 2026-06-30T14:58:03.945308+00:00

## Scope

- RAG was not implemented.
- Embeddings and vector search were not implemented.
- UI, chat, and Azure deployment files were not modified.
- Validation used curated source pages and the production document ingestion path.
- The old knowledge graph backfill was not invoked for validation.

## Pipeline Audit

Observed production flow after this change:

1. `run_crawl` loads enabled curated `source_pages`.
2. `scrape_source_page` crawls each curated page and returns candidates.
3. `acquire_primary_document` fetches each primary PDF/HTML document.
4. Primary extraction stores raw/text objects and OCRs PDF text when needed.
5. `persist_extracted_documents` upserts `documents`.
6. It persists `document_texts` and `document_versions`.
7. It registers the `document_families` / `document_version_registry` family.
8. It runs transactional graph extraction into existing graph tables.
9. It continues regulatory change and event-intelligence gates.
10. It creates `events` and `summaries` only when the event gates allow it.

Graph extraction occurs immediately after version/family registration and before event creation. A graph failure records `FAILED` in `regulatory_graph_extractions` and does not roll back the document/version.

## Summary

- Curated source pages processed: 7
- Documents processed: 40
- Graph extraction status mix: COMPLETED=40
- AI-backed graph extractions: 36
- Heuristic/fallback graph extractions: 4
- Failures/gaps: 4
- Total validation latency: 482823 ms
- Average graph latency: 47907.8 ms

## Graph Table Growth

| Table/Metric | Before | After | Delta |
|---|---:|---:|---:|
| documents | 42 | 42 | 0 |
| events | 22 | 22 | 0 |
| document_texts | 42 | 42 | 0 |
| document_versions | 42 | 42 | 0 |
| families | 41 | 41 | 0 |
| graph_extractions | 33 | 40 | 7 |
| graph_completed | 33 | 40 | 7 |
| graph_failed | 0 | 0 | 0 |
| graph_skipped | 0 | 0 | 0 |
| entities | 758 | 1044 | 286 |
| document_entities | 33 | 40 | 7 |
| edges | 886 | 1210 | 324 |
| deadlines | 237 | 391 | 154 |
| stakeholders | 191 | 244 | 53 |
| obligations | 300 | 397 | 97 |
| family_enrichment | 33 | 40 | 7 |

## Source Results

| Source Page | Candidates | Accepted | Rejected | Events | Latency ms |
|---|---:|---:|---:|---:|---:|
| MNRE - Current Notices | 6 | 3 | 3 | 0 | 10267 |
| MNRE - Monthly Updates | 8 | 8 | 0 | 0 | 8100 |
| CERC - Public Notice | 6 | 5 | 1 | 0 | 7302 |
| CERC - Suo Motu Petitions / Staff Papers / Notices | 8 | 7 | 1 | 0 | 66289 |
| CERC - Notice / Letter | 3 | 3 | 0 | 0 | 3720 |
| MOP - What's New | 8 | 6 | 2 | 0 | 141014 |
| SECI - Tenders | 8 | 8 | 0 | 0 | 242987 |

## Document Graph Results

| Document | Status | Entities | Edges | Deadlines | Stakeholders | Obligations | Graph ms |
|---|---|---:|---:|---:|---:|---:|---:|
| 40 - Uploading of Bid Document on MNRE Website for wider publicity | COMPLETED | 1 | 26 | 5 | 5 | 14 | 46069 |
| 1 - Administrative approval for implementation of Small Hydro Power (SHP) Development Scheme from 1 MW to 25 MW fo... | COMPLETED | 1 | 35 | 7 | 8 | 15 | 44752 |
| 2 - Amendment to ‘Standard Operating Procedure (SOP) for Approved List of Models and Manufacturers – Wind (ALMM-Wi... | COMPLETED (obligations=0) | 1 | 3 | 1 | 1 | 0 | 49337 |
| 3 - Renewable Energy Policy and Regulatory update for May 2026 month (546 KB) | COMPLETED | 1 | 47 | 12 | 13 | 14 | 53094 |
| 4 - Renewable Energy Policy and Regulatory update for April 2026 month (546 KB) | COMPLETED | 1 | 48 | 18 | 8 | 16 | 54079 |
| 5 - Renewable Energy Policy and Regulatory update for March 2026 month (546 KB) | COMPLETED | 1 | 33 | 16 | 7 | 5 | 36224 |
| 6 - Renewable Energy Policy and Regulatory update for February 2026 month (546 KB) | COMPLETED | 1 | 29 | 7 | 10 | 6 | 32299 |
| 7 - Renewable Energy Policy and Regulatory update for January 2026 month (546 KB) | COMPLETED | 1 | 40 | 8 | 8 | 16 | 50204 |
| 8 - Renewable Energy Policy and Regulatory update for December 2025 month (546 KB) | COMPLETED | 1 | 65 | 10 | 16 | 26 | 72805 |
| 9 - Renewable Energy Policy and Regulatory update for November2025 month (546 KB) | COMPLETED | 1 | 36 | 9 | 17 | 5 | 46210 |
| 10 - Renewable Energy Policy and Regulatory update for October 2025 month (546 KB) | COMPLETED | 1 | 42 | 12 | 8 | 18 | 51492 |
| 11 - Requested to file note of submissions | COMPLETED | 1 | 8 | 2 | 1 | 4 | 19627 |
| 12 - Commission to extend the implementation of Ancillary Services Regulations (Provisions pertaining to TRAS) from... | COMPLETED (stakeholders=0) | 1 | 17 | 7 | 0 | 3 | 28443 |
| 13 - Refund of Amounts against submission of Bank Guarantees, as per Hon'ble Supreme Court's Orders dated 09.05.202... | COMPLETED | 1 | 39 | 13 | 6 | 17 | 60028 |
| 14 - Submission of details of the Assets pertaining to Generating and Transmission Companies through CERC SAUDAMINI... | COMPLETED | 1 | 14 | 5 | 4 | 4 | 48334 |
| 15 - Public Notice dated 27.05.2021 regarding Payment of Annual fees | COMPLETED (stakeholders=0, obligations=0) | 1 | 7 | 4 | 0 | 0 | 49768 |
| 16 - 213/TD/2026 - Petition under Section 14 of the Electricity Act 2003 read with Regulation 6 of the CERC (Proced... | COMPLETED | 1 | 11 | 3 | 2 | 2 | 98313 |
| 17 - 185/TD/2026 - Application under Section 14 of the Electricity Act, 2003, read with the Central Electricity Reg... | COMPLETED | 1 | 14 | 6 | 1 | 2 | 29319 |
| 18 - 125/TL/2026 - Application under Sections 14, 15, 79(1)(e) of the Electricity Act, 2003 read with the Central E... | COMPLETED | 1 | 25 | 6 | 4 | 9 | 49238 |
| 19 - 121/TL/2026 - Application under Section 14 & 15 of the Electricity Act, 2003 read with Central Electricity Reg... | COMPLETED | 1 | 24 | 6 | 4 | 9 | 40516 |
| 20 - 131/TL/2026 - Petition under Sections 14, 15 and 79(1)(e) of Electricity Act, 2003, read with the Central Elec... | COMPLETED | 1 | 17 | 5 | 4 | 4 | 30948 |
| 21 - 133/TL/2026 - Application under Sections 14 & 15 of the Electricity Act, 2003 read with Central Electricity Re... | COMPLETED | 1 | 15 | 6 | 3 | 3 | 26204 |
| 22 - 27/TL/2026 - Application under Section-14, 15, 79(1)(e) of the Electricity Act, 2003 read with Central Electri... | COMPLETED | 1 | 29 | 7 | 3 | 14 | 48424 |
| 23 - Uploading of Monthly Information on the website of Trading Licensees-reg. | COMPLETED | 1 | 34 | 22 | 3 | 5 | 63174 |
| 24 - Explanation regarding introduction of G-TAM Daily T+1 Contracts - reg. | COMPLETED | 1 | 17 | 7 | 3 | 2 | 34435 |
| 25 - Explanation regarding modifications in the Delivery Timelines for the Anyday Contracts from T+2 to T+1 - reg. | COMPLETED | 1 | 16 | 7 | 3 | 2 | 26882 |
| 91 - Seeking comments on draft National Electricity Data Sharing Framework, 2026 | COMPLETED | 1 | 40 | 1 | 15 | 20 | 57904 |
| 26 - Implementation of decriminalisation measures under the Jan Vishwas (Amendment of Provisions) Act, 2026 | COMPLETED | 1 | 27 | 7 | 2 | 12 | 45499 |
| 27 - Electricity Amendment Rules 2025 | COMPLETED | 1 | 17 | 3 | 4 | 5 | 28129 |
| 28 - Seeking comments on Draft Electricity (Amendment) Bill, 2025. | COMPLETED | 1 | 43 | 4 | 12 | 20 | 65662 |
| 29 - Seeking comments on Draft National Electricity Policy, 2026 | COMPLETED (deadlines=0) | 1 | 31 | 0 | 10 | 15 | 44414 |
| 30 - Electricity (Amendment) Rules, 2026 alongwith Explanatory Note | COMPLETED | 1 | 22 | 4 | 1 | 12 | 78471 |
| 102 - Tender for Design, Engineering, Supply, Construction, Erection, Testing, Commissioning and Maintenance of 70 M... | COMPLETED | 1 | 15 | 7 | 5 | 1 | 24442 |
| 37 - RfS for Supply of 1000 MW Round-the-Clock Thermal Mimic (RTC-TM) Power from ISTS-Connected RE Power Projects i... | COMPLETED | 1 | 48 | 23 | 9 | 14 | 50971 |
| 32 - RfS for assured Peak Supply of 4800 MWh (1200 MW x 4 Hrs.) from ISTS-Connected RE Projects (SECI-FDRE-IX) | COMPLETED | 1 | 40 | 21 | 5 | 12 | 45639 |
| 38 - RfS for assured Peak Supply of 1500 MWh (500 MW x 3 Hrs.) under CfD Mechanism from ISTS-Connected RE Projects... | COMPLETED | 1 | 51 | 23 | 8 | 15 | 87593 |
| 33 - BoS Tender for Setting up of grid-connected 88 MW Ground mounted Solar PV plant at Chitradurga, Karnataka | COMPLETED | 1 | 43 | 21 | 5 | 13 | 45335 |
| 34 - RfS for setting up of 12250 kW Grid-Connected Rooftop Solar PV Projects on JNV Buildings (Phase-II) under RESC... | COMPLETED | 1 | 48 | 22 | 10 | 15 | 51482 |
| 35 - RfS for Supply of 1000 MW Excess Power from RE Projects having Existing PPA (SECI-FDRE-VIII) | COMPLETED | 1 | 44 | 21 | 7 | 13 | 46235 |
| 36 - RfS for setting up 5500 kW Grid-Connected Rooftop Solar PV Project under RESCO mode (RTSPV-Tranche-X) | COMPLETED | 1 | 50 | 23 | 9 | 15 | 54316 |

## Failures

- 2: obligations=0
- 12: stakeholders=0
- 15: stakeholders=0, obligations=0
- 29: deadlines=0

## Validation Verdict

PARTIALLY VALIDATED: production ingestion now invokes graph extraction, but some accepted documents are missing one or more graph row categories.