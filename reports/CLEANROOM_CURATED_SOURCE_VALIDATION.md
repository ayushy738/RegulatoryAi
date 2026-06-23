# Clean-Room Curated Source Validation

Generated at: 2026-06-22T11:55:12.673313+00:00

## Scope

- No UI was built.
- No AI logic was modified.
- No graph logic was modified.
- No family registry logic was modified.
- Generic homepage/search/archive/category/navigation discovery was not used.
- The run used only Step 22 curated source pages.

## Backup

- Backup file: `E:\RegulatoryAi\reports\backups\cleanroom_backup_20260622T115038Z.json`
- Backup format: JSON snapshot of generated tables, preserved configuration tables, and auxiliary app tables.
- Original pre-reset backup before the first clean-room truncate:
  `E:\RegulatoryAi\reports\backups\cleanroom_backup_20260622T111534Z.json`
- Additional rerun backup after the first failed persistence validation:
  `E:\RegulatoryAi\reports\backups\cleanroom_backup_20260622T112102Z.json`

## Reset Result

| Table | Before | After Truncate | After Run |
|---|---:|---:|---:|
| `events` | 0 | 0 | 0 |
| `summaries` | 0 | 0 | 0 |
| `document_versions` | 0 | 0 | 3 |
| `documents` | 0 | 0 | 3 |
| `document_texts` | 0 | 0 | 3 |
| `discovery_audit` | 41 | 0 | 41 |
| `event_intelligence_audit` | 0 | 0 | 2 |
| `regulatory_change_audit` | 0 | 0 | 5 |
| `document_family_assignments` | 0 | 0 | 3 |
| `document_version_registry` | 0 | 0 | 2 |
| `document_version_relationships` | 0 | 0 | 0 |
| `document_families` | 0 | 0 | 2 |
| `deadline_history` | 0 | 0 | 4 |
| `regulatory_graph_document_entities` | 0 | 0 | 3 |
| `regulatory_graph_edges` | 0 | 0 | 63 |
| `regulatory_graph_extractions` | 0 | 0 | 3 |
| `regulatory_graph_stakeholders` | 0 | 0 | 16 |
| `regulatory_graph_obligations` | 0 | 0 | 28 |
| `regulatory_graph_deadlines` | 0 | 0 | 5 |
| `regulatory_graph_family_enrichment` | 0 | 0 | 3 |
| `regulatory_graph_entities` | 0 | 0 | 63 |
| `crawl_runs` | 1 | 0 | 1 |
| `digests` | 1 | 0 | 1 |
| `digest_events` | 0 | 0 | 0 |
| `notifications_log` | 0 | 0 | 0 |
| `chat_messages` | 0 | 0 | 0 |
| `user_event_state` | 0 | 0 | 0 |
| `sources` | 4 | 4 | 4 |
| `source_pages` | 7 | 7 | 7 |
| `profiles` | 4 | 4 | 4 |
| `subscriptions` | 0 | 0 | 0 |
| `app_documents` | 4 | 4 | 4 |
| `exports_log` | 1 | 1 | 1 |
| `audit_log` | 0 | 0 | 0 |

## Curated Crawl Result

- Crawl run ID: 1
- Crawl status: partial
- Sources attempted: 4
- Pages attempted: 7
- Pages succeeded: 6
- Candidates found: 40
- Primary documents accepted: 5
- Rejected candidates: 36
- Events generated: 0
- Primary docs found by pipeline: 5
- Crawl errors: 1

## Knowledge Graph Growth

- entities: +63
- document_entities: +3
- edges: +63
- extractions: +3
- stakeholders: +16
- obligations: +28
- deadlines: +5
- family_enrichment: +3
- Documents analyzed by graph extractor: 3

## Source Page Metrics

| Source Page | Candidates | Downloaded | Accepted | Rejected | Events | Families | Graph Links | Deadlines | Obligations | Stakeholders |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| MNRE - Current Notices | 8 | 2 | 1 | 7 | 0 | 0 | 1 | 0 | 0 | 2 |
| MNRE - Monthly Updates | 8 | 2 | 1 | 7 | 0 | 0 | 1 | 0 | 0 | 2 |
| CERC - Public Notice | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| CERC - Suo Motu Petitions / Staff Papers / Notices | 8 | 1 | 1 | 7 | 0 | 1 | 1 | 3 | 24 | 11 |
| CERC - Notice / Letter | 8 | 1 | 1 | 7 | 0 | 1 | 1 | 3 | 24 | 11 |
| MOP - What's New | 0 | 0 | 0 | 1 | 0 | 0 | 0 | 0 | 0 | 0 |
| SECI - Tenders | 8 | 2 | 1 | 7 | 0 | 1 | 1 | 2 | 4 | 3 |

## Source Page Details

### MNRE - Current Notices

- URL: `https://mnre.gov.in/en/notice-category/current-notices/`
- Page type: `notice_listing`
- Candidates found: 8
- Primary documents downloaded: 2
- Accepted: 1
- Rejected: 7
- Events generated: 0
- Families created/assigned: 0
- Knowledge graph document links: 1
- Deadlines: 0
- Obligations: 0
- Stakeholders: 2
- Rejection reasons: CATEGORY_PAGE_DETECTED=3, INSUFFICIENT_CONTENT=1, NO_PRIMARY_DOCUMENT=3
- Classifications: CATEGORY_PAGE=3, NAVIGATION_PAGE=3, POLICY_UPDATE=1, TENDER_DOCUMENT=1
- Example documents: Tenders

### MNRE - Monthly Updates

- URL: `https://mnre.gov.in/en/monthly-updates/`
- Page type: `digest_listing`
- Candidates found: 8
- Primary documents downloaded: 2
- Accepted: 1
- Rejected: 7
- Events generated: 0
- Families created/assigned: 0
- Knowledge graph document links: 1
- Deadlines: 0
- Obligations: 0
- Stakeholders: 2
- Rejection reasons: CATEGORY_PAGE_DETECTED=3, INSUFFICIENT_CONTENT=1, NO_PRIMARY_DOCUMENT=3
- Classifications: CATEGORY_PAGE=3, NAVIGATION_PAGE=3, POLICY_UPDATE=1, TENDER_DOCUMENT=1
- Example documents: Tenders

### CERC - Public Notice

- URL: `https://cercind.gov.in/public-notice.html`
- Page type: `public_notice_listing`
- Candidates found: 0
- Primary documents downloaded: 0
- Accepted: 0
- Rejected: 0
- Events generated: 0
- Families created/assigned: 0
- Knowledge graph document links: 0
- Deadlines: 0
- Obligations: 0
- Stakeholders: 0
- Rejection reasons: none
- Classifications: none
- Example documents: none

### CERC - Suo Motu Petitions / Staff Papers / Notices

- URL: `https://cercind.gov.in/SPN.html`
- Page type: `spn_listing`
- Candidates found: 8
- Primary documents downloaded: 1
- Accepted: 1
- Rejected: 7
- Events generated: 0
- Families created/assigned: 1
- Knowledge graph document links: 1
- Deadlines: 3
- Obligations: 24
- Stakeholders: 11
- Rejection reasons: LISTING_PAGE_DETECTED=3, NO_PRIMARY_DOCUMENT=4
- Classifications: AMENDMENT=1, LISTING_PAGE=3, NAVIGATION_PAGE=3, REGULATORY_DOCUMENT=1
- Example documents: Electricity Act 2003

### CERC - Notice / Letter

- URL: `https://cercind.gov.in/notice-letter.html`
- Page type: `notice_letter_listing`
- Candidates found: 8
- Primary documents downloaded: 1
- Accepted: 1
- Rejected: 7
- Events generated: 0
- Families created/assigned: 1
- Knowledge graph document links: 1
- Deadlines: 3
- Obligations: 24
- Stakeholders: 11
- Rejection reasons: LISTING_PAGE_DETECTED=3, NO_PRIMARY_DOCUMENT=4
- Classifications: AMENDMENT=1, LISTING_PAGE=3, NAVIGATION_PAGE=3, REGULATORY_DOCUMENT=1
- Example documents: Electricity Act 2003

### MOP - What's New

- URL: `https://www.powermin.gov.in/whats-new`
- Page type: `whats_new_listing`
- Candidates found: 0
- Primary documents downloaded: 0
- Accepted: 0
- Rejected: 1
- Events generated: 0
- Families created/assigned: 0
- Knowledge graph document links: 0
- Deadlines: 0
- Obligations: 0
- Stakeholders: 0
- Rejection reasons: NO_PRIMARY_DOCUMENT=1
- Classifications: LISTING_PAGE=1
- Example documents: none

### SECI - Tenders

- URL: `https://www.seci.co.in/tenders`
- Page type: `tender_listing`
- Candidates found: 8
- Primary documents downloaded: 2
- Accepted: 1
- Rejected: 7
- Events generated: 0
- Families created/assigned: 1
- Knowledge graph document links: 1
- Deadlines: 2
- Obligations: 4
- Stakeholders: 3
- Rejection reasons: HOMEPAGE_DETECTED=1, INSUFFICIENT_CONTENT=2, NO_PRIMARY_DOCUMENT=4
- Classifications: HOMEPAGE=1, NAVIGATION_PAGE=4, POLICY_UPDATE=1, REGULATORY_DOCUMENT=2
- Example documents: Corporate Brochure

## Accepted Document Walkthroughs

Only 3 accepted document(s) were produced. The requested 5-10 walkthrough target was not met by this run.

### 1. Tenders

- Source page: Current Notices (`https://mnre.gov.in/en/notice-category/current-notices/`)
- Primary URL: `https://mnre.gov.in/en/tender/`
- Issuer: Ministry of New & Renewable Energy
- Document type: `html`
- Family: Unassigned
- Family assignment: UNKNOWN_FAMILY
- Passed intelligence gate: NO
- Created event: NO
- Gate rejection reason: HISTORICAL_DOCUMENT

Stakeholders:
- Renewable Developers
- Solar Developers

Obligations:
- None extracted.

Deadlines:
- None extracted.

### 2. Electricity Act 2003

- Source page: Suo Motu Petitions / Staff Papers / Notices (`https://cercind.gov.in/SPN.html`)
- Primary URL: `https://cercind.gov.in/Act-with-amendment.pdf`
- Issuer: Central Electricity Regulatory Commission
- Document type: `pdf`
- Family: Electricity Act 2003
- Family assignment: AI_CONFIRMED_FAMILY
- Passed intelligence gate: NO
- Created event: NO
- Gate rejection reason: HISTORICAL_DOCUMENT

Stakeholders:
- Central Government
- State Government
- Central Electricity Authority
- Central Electricity Regulatory Commission
- State Electricity Board
- Appellate Tribunal for Electricity
- DISCOMs
- Transmission Licensees

Obligations:
- (2) The Central Government shall publish National Electricity Policy and tariff policy from time to time. [DISCOMs]
- Ensure transparent policies regarding subsidies. [Parliament]
- Promote competition in the electricity industry. [Parliament]
- Promote efficient and environmentally benign policies. [Parliament]
- Appoint commencement date by notification. [Central Government]
- (31) “Government company” shall have the meaning assigned to it in section 617 of the Companies Act, 1956; [DISCOMs]
- (49) “person” shall include any company or body corporate or association or body of individuals, whether incorporated or not, or artificial juridical person; [DISCOMs]
- (71) "trading" means purchase of electricity for resale thereof and the expression "trade" shall be construed accordingly; [DISCOMs]

Deadlines:
- COMMENCEMENT: such date as the Central Government may, by notification, appoint
- UNKNOWN_DATE: 2004-01-27
- UNKNOWN_DATE: 2007-06-15

### 3. Corporate Brochure

- Source page: Tenders (`https://www.seci.co.in/tenders`)
- Primary URL: `https://www.seci.co.in/uploads/media/APPROVED_CORP_BROCHURE-1.pdf`
- Issuer: Solar Energy Corporation of India
- Document type: `pdf`
- Family: Corporate Brochure
- Family assignment: NEW_FAMILY
- Passed intelligence gate: NO
- Created event: NO
- Gate rejection reason: None

Stakeholders:
- AASHI ATTUT, DM(CP)AA, DM(CP)
- Renewable Developers
- Solar Developers

Obligations:
- 7906) Generated from eOffice by AASHI ATTUT, DM(CP)AA, DM(CP), Solar Energy Corporation of India Limited on 20/11/2025 03:00 pm 132748/2025/CP 4 File No. [Renewable Developers]
- 7906) Generated from eOffice by AASHI ATTUT, DM(CP)AA, DM(CP), Solar Energy Corporation of India Limited on 20/11/2025 03:00 pm 132748/2025/CP 2 File No. [Renewable Developers]
- 132748/2025/CP 1 File No. [Renewable Developers]
- 7906) Generated from eOffice by AASHI ATTUT, DM(CP)AA, DM(CP), Solar Energy Corporation of India Limited on 20/11/2025 03:00 pm 132748/2025/CP 3 File No. [Renewable Developers]

Deadlines:
- UNKNOWN_DATE: 2025-09-18
- UNKNOWN_DATE: 2025-11-20

## Rejection Analysis

### LISTING_PAGE_DETECTED

- CERC / Suo Motu Petitions / Staff Papers / Notices: Rules & Regulations (`LISTING_PAGE`) - Listing page.
- CERC / Suo Motu Petitions / Staff Papers / Notices: Orders/ROPs/TVs (`LISTING_PAGE`) - Listing page.
- CERC / Suo Motu Petitions / Staff Papers / Notices: Orders (`LISTING_PAGE`) - Listing page.
- CERC / Notice / Letter: Rules & Regulations (`LISTING_PAGE`) - Listing page.
- CERC / Notice / Letter: Orders/ROPs/TVs (`LISTING_PAGE`) - Listing page.

### NO_PRIMARY_DOCUMENT

- CERC / Suo Motu Petitions / Staff Papers / Notices: Organization Chart (`REGULATORY_DOCUMENT`) - PDF without strong regulatory terms.
- CERC / Suo Motu Petitions / Staff Papers / Notices: Individual Regulation (`NAVIGATION_PAGE`) - No strong regulatory primary-document signal.
- CERC / Suo Motu Petitions / Staff Papers / Notices: Consolidated Regulation (`NAVIGATION_PAGE`) - No strong regulatory primary-document signal.
- CERC / Suo Motu Petitions / Staff Papers / Notices: Draft Regulation / Discussion Paper (`NAVIGATION_PAGE`) - No strong regulatory primary-document signal.
- CERC / Notice / Letter: Organization Chart (`REGULATORY_DOCUMENT`) - PDF without strong regulatory terms.

### CATEGORY_PAGE_DETECTED

- MNRE / Current Notices: Solar Thermal (`CATEGORY_PAGE`) - Category page.
- MNRE / Current Notices: Solar (`CATEGORY_PAGE`) - Category page.
- MNRE / Current Notices: Wind (`CATEGORY_PAGE`) - Category page.
- MNRE / Monthly Updates: Solar Thermal (`CATEGORY_PAGE`) - Category page.
- MNRE / Monthly Updates: Solar (`CATEGORY_PAGE`) - Category page.

### INSUFFICIENT_CONTENT

- MNRE / Current Notices: Lab Policy, Standards and Quality Control (`POLICY_UPDATE`) - Policy terms.
- MNRE / Monthly Updates: Lab Policy, Standards and Quality Control (`POLICY_UPDATE`) - Policy terms.
- SECI / Tenders: Terms of appointment of Independent Director (`REGULATORY_DOCUMENT`) - PDF with regulatory terms.
- SECI / Tenders: CSR Policy (`POLICY_UPDATE`) - Policy terms.

### HOMEPAGE_DETECTED

- SECI / Tenders: Solar Energy Corporation of India Limited (A Navratna Government of India Enterprise) (`HOMEPAGE`) - Root/index page.

## Architecture Verdict

Verdict: **NOT VALIDATED**

The curated pages did not produce enough accepted primary documents and downstream intelligence. The architecture is cleaner, but source-specific extraction or page parsing still needs work before analyst-grade validation.

## Success Criteria Check

- 5-10 accepted walkthroughs available: NO (3 accepted walkthroughs).
- Events created from curated pages: NO (0).
- Families created/assigned: YES (2).
- Graph obligations extracted: YES (28).
- Graph deadlines extracted: YES (5).
- Stakeholders extracted: YES (16).
