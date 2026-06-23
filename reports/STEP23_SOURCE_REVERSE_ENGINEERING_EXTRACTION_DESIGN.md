# Step 23 - Source Reverse Engineering & Extraction Design

Generated: 2026-06-22

## Scope

This is an extraction-design audit only.

- No product code was modified.
- No UI was modified.
- No graph, family, RAG, Ask, or intelligence logic was modified.
- The audit inspected the live curated source pages and the prior clean-room validation failures.

## Executive Verdict

The crawler is mechanically reaching the curated pages, but the extraction layer is too broad. The current scraper effectively does:

```text
for every a[href] on the page:
  keep it if URL/text contains regulatory keywords
```

That is why it selected:

- MNRE: `Tenders` navigation page instead of current notice PDFs.
- CERC: `Electricity Act 2003` navigation PDF instead of public notice/SPN table rows.
- SECI: `Corporate Brochure` media-menu PDF instead of live tender rows.
- MoP: nothing, because `What's New` is a Next.js shell and the useful data comes from a JSON CMS endpoint.

The fix should not be more keywords. Each source page needs a source-specific row/card/API parser scoped to the real content container.

## Cross-Source Extraction Principles

1. Never scan global anchors from the whole page.
2. Scope to the page body content container first.
3. Extract at row/card/post level, not isolated anchor level.
4. Treat the row as the candidate and the link as the primary document.
5. Preserve listing metadata: source page, row title, publication date, end date/deadline, tender ID, petition number, and alternate documents.
6. Explicitly reject nav/header/footer/share/archive/sidebar/category links before content scoring.
7. For detail-page workflows, first select the listing row, then fetch the detail page and select documents only inside the detail content root.
8. For JS/Next.js pages, prefer the underlying official JSON endpoint over rendered browser scraping when the endpoint is stable and public.

## 1. MNRE Current Notices

URL: `https://mnre.gov.in/en/notice-category/current-notices/`

### HTML Structure

The useful content is server-rendered HTML.

Observed structure:

```text
main
  div#notice-results-area
    div.data-table-container
      table.data-table-1
        tbody
          tr
            td Sr. No.
            td Title
            td Description
            td Start Date
            td End Date
            td File -> span.pdf-downloads a.pdf-download-link
```

The table currently contains real current notice PDFs.

Example rows observed:

| Title | Start Date | End Date | Primary Document |
|---|---:|---:|---|
| ALMM - No blanket extension of ALMM List-II beyond 01.06.2026 subject to Protection of Investments already made | 25/05/2026 | 25/07/2026 | S3WaaS PDF |
| Administrative approval for implementation of Small Hydro Power (SHP) Development Scheme from 1 MW to 25 MW for FY 2026-27 to FY 2030-31 | 15/05/2026 | 31/03/2031 | S3WaaS PDF |
| Filling up the post of Scientists D and C in MNRE | 20/04/2026 | 08/07/2026 | S3WaaS PDF |
| Amendment to SOP for ALMM-Wind and ALMM-WTC | 01/12/2025 | 01/12/2027 | S3WaaS PDF |
| OM regarding extension in timeline of the Solar Park scheme | 17/09/2025 | 31/03/2029 | S3WaaS PDF |

### Exact Extraction Selectors

```text
content_root:
  main div#notice-results-area

row_selector:
  main div#notice-results-area table.data-table-1 tbody tr

primary_document_selector:
  span.pdf-downloads a.pdf-download-link[href]

field_mapping:
  title: td:nth-of-type(2)
  description: td:nth-of-type(3)
  start_date: td:nth-of-type(4)
  end_date: td:nth-of-type(5)
  primary_document_url: td:nth-of-type(6) a.pdf-download-link[href]
```

### Accept Rules

Accept rows when:

- Row is inside `div#notice-results-area`.
- Row has `a.pdf-download-link[href]`.
- Link host is `cdnbbsr.s3waas.gov.in` or `mnre.gov.in`.
- Title/description is not empty.
- Title matches a regulatory or sector-relevant pattern:
  - `ALMM`
  - `scheme`
  - `administrative approval`
  - `SOP`
  - `amendment`
  - `OM`
  - `extension`
  - `guideline`
  - `policy`
  - `standards`
  - `solar`
  - `wind`
  - `hydro`

### Reject Rules

Reject:

- Navigation/menu links:
  - `li#menu-item-*`
  - `ul#accessibilityMenu`
  - `nav#breadcrumb`
  - `.printShare`
  - footer/certification links
- `Archive` button.
- Category pages:
  - `/notice-category/`
  - `/past-notices/`
  - `/en/tender/`
- Generic website PDFs not in the current notices table:
  - `RE-Statistics`
  - `Citizen charter`
  - certification PDFs
- HR/recruitment rows unless the product intentionally tracks government hiring. Example: `Filling up the post of Scientists D and C`.

### What Should Have Been Selected Instead Of `Tenders`

The crawler selected `https://mnre.gov.in/en/tender/` because it scanned the global `Notices` menu.

It should have selected these table PDFs instead:

1. `ALMM - No blanket extension of ALMM List-II...`
2. `Administrative approval for implementation of Small Hydro Power Scheme...`
3. `Amendment to SOP for ALMM-Wind and ALMM-WTC`
4. `OM regarding extension in timeline of the Solar Park scheme`

## 2. MNRE Monthly Updates

URL: `https://mnre.gov.in/en/monthly-updates/`

### HTML Structure

The useful content is a simple content list, not a table.

Observed structure:

```text
main
  .wpb_text_column.wpb_content_element
    .wpb_wrapper
      ul
        li
          a[href$=".pdf"]
```

Example links observed:

| Title | Primary Document |
|---|---|
| Renewable Energy Policy and Regulatory update for May 2026 month | S3WaaS PDF |
| Renewable Energy Policy and Regulatory update for April 2026 month | S3WaaS PDF |
| Renewable Energy Policy and Regulatory update for March 2026 month | S3WaaS PDF |
| Renewable Energy Policy and Regulatory update for February 2026 month | S3WaaS PDF |
| Renewable Energy Policy and Regulatory update for January 2026 month | S3WaaS PDF |

### Exact Extraction Selectors

```text
content_root:
  main .wpb_text_column.wpb_content_element .wpb_wrapper

row_selector:
  main .wpb_text_column.wpb_content_element .wpb_wrapper ul li

primary_document_selector:
  li > a[href*="/uploads/"][href$=".pdf"]

field_mapping:
  title: anchor text
  issue_month: parse from title
  primary_document_url: a[href]
```

### Accept Rules

Accept rows when:

- Anchor is inside `main .wpb_text_column`.
- URL ends with `.pdf`.
- Anchor text contains `Renewable Energy Policy and Regulatory update`.

### Reject Rules

Reject:

- Header/menu links to `Tenders`, `Current Notices`, `Lab Policy`, etc.
- Share links.
- Certification/footer PDFs.
- `RE-Statistics` PDFs from the global menu.

### Product Note

Monthly Updates are not individual regulatory events. They are digest PDFs. The parser should treat them as digest documents and hand them to the digest parser/extractor, not classify the PDF title itself as a final event.

## 3. CERC Public Notice

URL: `https://cercind.gov.in/public-notice.html`

### Fetching Note

The page sometimes resets a plain `httpx` connection with `WinError 10054`. With a browser-like `Accept` header and relaxed certificate verification during inspection, it returned HTTP 200.

Extraction design should include:

- Browser-like user agent.
- Retry.
- Fallback to `http://cercind.gov.in/public-notice.html`.
- If TLS continues to fail, use a browser-render/fetch fallback.

### HTML Structure

The useful content is a single static table.

Observed structure:

```text
section
  div.wrap-md
    div.container.coc-mid
      table.table.table-bordered.table-striped.tbsa
        tbody#myTable
          tr
            td Sl. No.
            td Subject -> a[href]
            td Date of Publication
```

Example rows observed:

| Subject | Date | Primary Document |
|---|---:|---|
| Empanelment of consulting firm/institutions for assisting CERC in regulatory functions | 17.06.2026 | `2026/whatsnew/PN-180626.pdf` |
| Notice: Conducting of Hearings through Video Conferencing/Hybrid Mode | 19.05.2026 | `2026/whatsnew/Notice190526.pdf` |
| CERC Internship Scheme | 02.01.2024 | `pdf/Internship_Scheme.pdf` |
| Requested to file note of submissions | 05.04.2023 | `2023/whatsnew/Notice-050423.pdf` |
| Commission to extend implementation of Ancillary Services Regulations (TRAS) | 27.03.2023 | `Regulations/167_8.pdf` |

### Exact Extraction Selectors

```text
content_root:
  section .wrap-md .container.coc-mid

row_selector:
  section .wrap-md .container.coc-mid table.tbsa tbody#myTable > tr

primary_document_selector:
  td.style13 a[href], td a[href]

field_mapping:
  title: td:nth-of-type(2) anchor text or cell text
  publication_date: td:nth-of-type(3)
  primary_document_url: td:nth-of-type(2) a[href]
```

### Accept Rules

Accept rows inside `tbody#myTable` when title contains:

- `public notice`
- `notice`
- `hearing`
- `regulatory`
- `regulations`
- `annual fees`
- `trading license`
- `assets`
- `submission`
- `ancillary services`
- `implementation`
- `extension`

### Reject Rules

Reject:

- Header/navigation links in `div.wrap-navi`, `ul.nav.navbar-nav`, dropdown menus.
- `Electricity Act 2003`.
- `Organization Chart`.
- `Rules & Regulations` landing pages.
- `Orders/ROPs/TVs` landing pages.
- Internship/recruitment/admin rows unless explicitly needed:
  - `CERC Internship Scheme`
  - pure staffing/consulting empanelment rows can be low-priority or rejected if the product excludes procurement/admin notices.

### What Should Have Been Selected Instead Of `Electricity Act 2003`

The crawler selected the nav PDF `Act-with-amendment.pdf`.

It should have selected row-level public notice PDFs such as:

1. `Notice: Conducting of Hearings through Video Conferencing/Hybrid Mode`
2. `Commission to extend implementation of Ancillary Services Regulations...`
3. `Public Notice dated 27.05.2021 regarding Payment of Annual fees`

## 4. CERC SPN

URL: `https://cercind.gov.in/SPN.html`

### HTML Structure

The useful current section is a static table.

Observed structure:

```text
section
  div.wrap-md
    div.container.coc-mid
      table.table.table-bordered.table-striped.tbsa
        tbody#myTable
          tr
            td Pet. No.
            td Subject
            td Newspapers -> span.label.label-primary a.text[href]
            td Date of Publication
```

There is also a second older/historical `table.tbsa` lower on the page. Current extraction should start with the first table containing `tbody#myTable`.

Example rows observed:

| Petition No. | Subject | Date | Primary Links |
|---|---|---:|---|
| 213/TD/2026 | Petition for grant of Category V inter-State Trading Licence - Oasis Greenway Power Trading Private Limited | 19.06.2026 | The Hindu, Amar Ujala PDFs |
| 185/TD/2026 | Application for grant of trading license - REMC Limited | 19.06.2026 | Times of India, Dainik Jagran PDFs |
| 214/TD/2026 | Application for trading licence - PRMK Energy | 09.06.2026 | Indian Express, Hindustan PDFs |
| 125/TL/2026 | Transmission licence/public notice row | 23.05.2026 | Hindustan Times, Dainik Jagran PDFs |

### Exact Extraction Selectors

```text
content_root:
  section .wrap-md .container.coc-mid

row_selector:
  section .wrap-md .container.coc-mid table.table.table-bordered.table-striped.tbsa tbody#myTable > tr

primary_document_selector:
  td:nth-of-type(3) a.text[href]

field_mapping:
  petition_no: td:nth-of-type(1)
  title: td:nth-of-type(2)
  publication_date: td:nth-of-type(4)
  primary_document_url: first English newspaper PDF in td:nth-of-type(3)
  alternate_document_urls: all other links in td:nth-of-type(3)
```

### Accept Rules

Accept rows when:

- Petition number exists.
- Subject contains electricity/power sector matter.
- At least one newspaper notice PDF/image exists.
- Prefer English PDFs in this order:
  - `The Hindu`
  - `Times of India`
  - `Indian Express`
  - `Hindustan Times`
  - any other English link
  - Hindi link fallback

### Reject Rules

Reject:

- Header/nav/menu links.
- `Electricity Act 2003`.
- `Organization Chart`.
- `Individual Regulation`.
- `Consolidated Regulation`.
- `Draft Regulation / Discussion Paper` landing pages.
- Older second table rows unless historical backfill is explicitly requested.

### Product Note

SPN rows are not amendments by themselves. They are statutory notices for petitions/licences. The event title should be synthesized from the row:

```text
CERC statutory public notice for petition 213/TD/2026 - Oasis Greenway Power Trading Private Limited trading licence
```

The newspaper PDF is evidence; the row metadata carries the real title.

## 5. CERC Notice / Letter

URL: `https://cercind.gov.in/notice-letter.html`

### HTML Structure

The useful content is a static table.

Observed structure:

```text
section
  div.wrap-md
    div.container.coc-mid
      table.table.table-bordered.table-striped.tbsa
        tbody#myTable
          tr
            td Sl. No.
            td Subject -> a[href]
            td Date of Publication
```

Example rows observed:

| Subject | Date | Primary Document |
|---|---:|---|
| Uploading of Monthly Information on the website of Trading Licensees - reg. | 20.11.2023 | `2023/whatsnew/Monthly-Trading-Information201123.pdf` |
| Explanation regarding introduction of G-TAM Daily T+1 Contracts - reg. | 05.05.2022 | `2022/whatsnew/IEX.pdf` |
| Explanation regarding modifications in Delivery Timelines from T+2 to T+1 - reg. | 05.05.2022 | `2022/whatsnew/PXIL.pdf` |

### Exact Extraction Selectors

```text
content_root:
  section .wrap-md .container.coc-mid

row_selector:
  section .wrap-md .container.coc-mid table.tbsa tbody#myTable > tr

primary_document_selector:
  td.style13 a[href], td a[href]

field_mapping:
  title: td:nth-of-type(2) anchor text or cell text
  publication_date: td:nth-of-type(3)
  primary_document_url: td:nth-of-type(2) a[href]
```

### Accept Rules

Accept if title contains:

- `trading licensees`
- `G-TAM`
- `contracts`
- `delivery timelines`
- `power exchange`
- `market`
- `reg.`
- `monthly information`

### Reject Rules

Reject the same CERC navigation/header links as above.

### Product Note

This page currently appears low-frequency and partly stale. It can still provide high-quality market-operation obligations, but should be freshness-gated. Do not allow old rows to dominate Latest.

## 6. SECI Tenders

URL: `https://www.seci.co.in/tenders`

### HTML Structure

The tender list is server-rendered as a real table.

Observed listing structure:

```text
section.tender-section
  table#tender-list.table.table-bordered
    tbody
      tr.tender-row
        td S No.
        td Tender ID
        td TSC on ETS Portal
        td Tender Ref No.
        td Tender Title
        td Publication Date
        td Bid Submission Date
        td Tender Details -> a.view-detail
```

Example listing rows observed:

| Tender ID | Title | Publication Date | Bid Submission Date | Detail |
|---|---|---:|---:|---|
| SECI000258 | RfS for assured Peak Supply of 4800 MWh from ISTS-connected RE Projects (SECI-FDRE-IX) | 05/06/2026 | 20/07/2026 | `/tender-details/Ymd_` |
| SECI000261 | Request for Empanelment of Advocates/Law Firms with SECI for 2 years | 12/06/2026 | 20/07/2026 | `/tender-details/YmR2` |
| SECI000252 | BoS Tender for 88 MW Ground mounted Solar PV plant at Chitradurga | 08/05/2026 | 10/07/2026 | `/tender-details/Ymd1` |
| SECI000256 | RfS for Rooftop Solar PV Projects on JNV Buildings under RESCO Mode | 29/05/2026 | 10/07/2026 | detail page |

### Listing Selectors

```text
content_root:
  section.tender-section

row_selector:
  section.tender-section table#tender-list tbody tr.tender-row

detail_link_selector:
  a.view-detail[href]

field_mapping:
  tender_id: td:nth-of-type(2)
  ets_id: td:nth-of-type(3)
  tender_ref_no: td:nth-of-type(4)
  title: td:nth-of-type(5)
  publication_date: td:nth-of-type(6)
  bid_submission_date: td:nth-of-type(7)
  detail_url: td:nth-of-type(8) a.view-detail[href]
```

### Detail Page Structure

Each listing row points to a detail page.

Observed detail root:

```text
section.tender-detail
  table(s)
    Tender Basic Details
    Financial Instruments
    Bid Details
    Document links
    Corrigendum links
```

Useful detail fields observed:

- `Tender ID`
- `Tender Reference No`
- `Tender ID On CPPP`
- `Tender Title`
- `Tender Type`
- `Tender Description`
- `Tender Publication Date`
- `Pre Bid Meeting Date`
- `Bid Submission End Date (Online)`
- `Bid Submission End Date (Offline)`
- `Bid Open Date`

Useful document links observed:

For `SECI000258`:

- `RfS_for_4800_MWh_Peak_Supply_(FDRE-IX)-_final_upload.pdf`
- `Standard_SECI_PPA_FDRE-IX-_final_upload.pdf`
- `Standard_SECI-PSA-FDRE-IX-_final_upload.pdf`
- `Integrity_Pact15.pdf`
- `Pre-bid_meeting_notification41.pdf`

For `SECI000252`:

- `Contractual_Tender_document_88_MW_SPV_BoS.pdf`
- `Technical_Tender_Document_88_MW_BoS_P-1.pdf`
- `Technical_Tender_Document_88_MW_BoS_P-2.pdf`
- `Pre-bid_meeting_notification37.pdf`
- `Rescheduling of pre-bid meeting...`
- `Site Visit and pre-bid meeting...`

### Detail Selectors

```text
detail_content_root:
  section.tender-detail

basic_detail_tables:
  section.tender-detail table.table.table-hover.table-striped.table-condensed

primary_tender_documents:
  section.tender-detail a[href*="/uploads/tenders/"][href$=".pdf"]

corrigendum_documents:
  section.tender-detail a[href*="/uploads/tenders/corrigendums/"][href$=".pdf"]

supporting_spreadsheets:
  section.tender-detail a[href*="/uploads/tenders/"][href$=".xlsx"]
```

### Accept Rules

Accept listing rows when:

- Row is inside `section.tender-section table#tender-list`.
- Row has a `View Details` URL.
- Title contains one of:
  - `RfS`
  - `RFP`
  - `Tender`
  - `BoS`
  - `Solar`
  - `RE Projects`
  - `ISTS`
  - `Rooftop`
  - `RESCO`
  - `Bidding`
  - `Empanelment` only if energy/project/legal relevance is desired.

On detail page:

- Accept PDF documents under `/uploads/tenders/`.
- Treat `/uploads/tenders/corrigendums/` as tender update/corrigendum events.
- Prefer primary RfS/RFP/NIT/tender PDFs over supporting PPA/PSA/integrity/spreadsheet files for the main event.
- Store supporting documents as attachments/related documents.

### Reject Rules

Reject:

- Header/nav/menu:
  - `#navbarSupportedContent`
  - `.navbar-nav`
  - `.submenu`
- Footer links.
- Media PDFs:
  - `/uploads/media/APPROVED_CORP_BROCHURE-1.pdf`
- Corporate/investor/CSR documents:
  - `Corporate Brochure`
  - `CSR Policy`
  - `Terms of appointment of Independent Director`
  - annual reports
  - credit ratings
  - POSH/QEHS policy
- Page tabs as primary docs:
  - `All`
  - `CPP Portal`
  - `ETS Portal`
  - `Archived Tenders`
  - `GEM Portal`
  - `Results`
- `/payment-modes`

### What Should Have Been Selected Instead Of `Corporate Brochure`

The crawler selected `Corporate Brochure` because it scanned the global media menu.

It should have selected:

1. `SECI000258 - RfS for assured Peak Supply of 4800 MWh...`
   - primary PDF: `RfS_for_4800_MWh_Peak_Supply_(FDRE-IX)-_final_upload.pdf`
   - deadline: bid submission `20/07/2026`
   - update PDF: `Pre-bid_meeting_notification41.pdf`
2. `SECI000252 - BoS Tender for 88 MW Ground mounted Solar PV plant...`
   - primary PDF: `Contractual_Tender_document_88_MW_SPV_BoS.pdf`
   - deadline: bid submission `10/07/2026`
   - update PDFs: pre-bid/site visit notifications
3. `SECI000256 - RfS for Rooftop Solar PV Projects on JNV Buildings...`

## 7. Ministry of Power What's New

URL: `https://www.powermin.gov.in/whats-new`

### HTML Structure

The public HTML is a Next.js shell. It contains no useful notice rows or document anchors before client-side hydration.

Observed:

```text
title: What's New
tables: 0
candidate anchors: 0
__NEXT_DATA__: pageProps only
```

The useful data comes from the public CMS JSON endpoint used by the bundled frontend.

### API Structure

The Next.js bundle defines:

```text
baseURL: /cms/
headers:
  apikey: 4bW5t13453pa
  Content-Type: application/json
```

Primary endpoint:

```text
GET https://www.powermin.gov.in/cms/wp-json/post-page/whats_new
```

Response shape:

```text
posts[]
  ID
  post_date
  post_title
  post_slug
  post_type = whats_new
  acf_data
    type = PDF
    file = [central_document_id]
```

Attachment resolution endpoint:

```text
GET https://www.powermin.gov.in/cms/wp-json/post-page/post?id=<central_document_id>
```

Attachment response shape:

```text
posts
  ID
  post_title
  post_type = central_documents
  acf_data
    title
    file_date
    pdf
      url
      filename
      filesize
      mime_type
```

Example posts observed:

| Post Title | Post Date | Attachment |
|---|---:|---|
| Selection to the post of Chairman and Managing Director, SJVN Limited | 2026-06-13 | PDF attachment ID 24877 |
| Selection for the post of Managing Director, NTPC Green Energy Limited | 2026-06-12 | PDF attachment ID 24851 |
| Implementation of decriminalisation measures under the Jan Vishwas (Amendment of Provisions) Act, 2026 | 2026-06-07 | PDF attachment ID 24604 |
| Inviting comments on draft recruitment rules for Library and Information Assistant, CEA | 2026-06-07 | PDF attachment ID 24341 |
| Electricity Amendment Rules 2025 | 2026-06-09 | PDF attachment ID 24759 |

Example resolved primary PDF:

```text
Attachment ID: 24759
Title: Electricity Amendment Rules 2025
File date: 19/09/2025
PDF URL: https://powermin.gov.in/static/uploads/2026/06/f89ac0cd4dec58a497aef0f15c653379.pdf
```

### Exact Extraction Specification

```text
listing_api:
  GET /cms/wp-json/post-page/whats_new
  headers:
    apikey: 4bW5t13453pa
    Content-Type: application/json

post_selector:
  posts[]

attachment_ids:
  posts[].acf_data.file[]

attachment_api:
  GET /cms/wp-json/post-page/post?id=<attachment_id>

primary_document_url:
  posts.acf_data.pdf.url

field_mapping:
  title: post_title or attachment.posts.acf_data.title
  publication_date: post_date
  issue_date: attachment.posts.acf_data.file_date
  primary_document_url: attachment.posts.acf_data.pdf.url
  document_type: attachment.posts.acf_data.pdf.mime_type
```

### Accept Rules

Accept posts/titles containing:

- `Electricity Amendment Rules`
- `rules`
- `amendment`
- `notification`
- `guidelines`
- `policy`
- `scheme`
- `decriminalisation`
- `Jan Vishwas`
- `draft`
- `inviting comments`
- `public consultation`
- `transmission`
- `tariff`
- `renewable`
- `power market`
- `electricity`

### Reject Rules

Reject:

- Appointments/selections:
  - `Selection to the post`
  - `Appointment of`
  - `Director`
  - `Chairman`
  - `Managing Director`
- Pure recruitment/staffing unless explicitly tracked:
  - `recruitment rules`
  - `vacancy`
  - `internship`
- Generic Next.js HTML shell.
- Search endpoint results unless a targeted search query is intentionally requested.

### What Should Have Been Selected Instead Of Nothing

The current crawler found no anchors because the page is JS/API-backed.

It should have selected:

1. `Electricity Amendment Rules 2025`
2. `Implementation of decriminalisation measures under the Jan Vishwas (Amendment of Provisions) Act, 2026`
3. `Inviting comments on draft recruitment rules...` only if recruitment-rule consultations are in scope; otherwise reject.

## Source-Specific Parser Specs

### MNRE Current Notices Parser

```yaml
source_page: mnre_current_notices
mode: html_table
url: https://mnre.gov.in/en/notice-category/current-notices/
content_root: main div#notice-results-area
row_selector: table.data-table-1 tbody tr
link_selector: span.pdf-downloads a.pdf-download-link[href]
fields:
  title: td[1]
  description: td[2]
  start_date: td[3]
  end_date: td[4]
  primary_url: link.href
reject_scopes:
  - header
  - nav
  - footer
  - ul#accessibilityMenu
  - nav#breadcrumb
  - .printShare
  - .certification-logo
reject_url_patterns:
  - /notice-category/
  - /past-notices/
  - /en/tender/
  - facebook.com
  - x.com/share
  - linkedin.com
```

### MNRE Monthly Updates Parser

```yaml
source_page: mnre_monthly_updates
mode: html_list
url: https://mnre.gov.in/en/monthly-updates/
content_root: main .wpb_text_column.wpb_content_element .wpb_wrapper
row_selector: ul li
link_selector: a[href*="/uploads/"][href$=".pdf"]
fields:
  title: link.text
  issue_month: parse_month_year(link.text)
  primary_url: link.href
accept_title_patterns:
  - Renewable Energy Policy and Regulatory update
reject_scopes:
  - header
  - nav
  - footer
  - share widgets
```

### CERC Public Notice Parser

```yaml
source_page: cerc_public_notice
mode: static_table
url: https://cercind.gov.in/public-notice.html
fetch:
  retry: true
  browser_accept_header: true
  fallback_http: true
  tolerate_tls_failure_with_browser_fallback: true
content_root: section .wrap-md .container.coc-mid
row_selector: table.tbsa tbody#myTable > tr
link_selector: td.style13 a[href], td a[href]
fields:
  title: td[1]
  publication_date: td[2]
  primary_url: first_link.href
reject_scopes:
  - div.wrap-navi
  - ul.nav.navbar-nav
  - footer
reject_titles:
  - Electricity Act 2003
  - Organization Chart
  - CERC Internship Scheme
```

### CERC SPN Parser

```yaml
source_page: cerc_spn
mode: static_table
url: https://cercind.gov.in/SPN.html
content_root: section .wrap-md .container.coc-mid
row_selector: table.table.table-bordered.table-striped.tbsa tbody#myTable > tr
link_selector: td:nth-of-type(3) a.text[href]
fields:
  petition_no: td[0]
  title: td[1]
  publication_date: td[3]
  primary_url: preferred_english_link
  alternate_urls: all_links
primary_link_preference:
  - The Hindu
  - Times of India
  - Indian Express
  - Hindustan Times
  - English
  - first available
reject_scopes:
  - div.wrap-navi
  - ul.nav.navbar-nav
  - footer
reject_titles:
  - Electricity Act 2003
  - Organization Chart
  - Individual Regulation
  - Consolidated Regulation
  - Draft Regulation / Discussion Paper
```

### CERC Notice Letter Parser

```yaml
source_page: cerc_notice_letter
mode: static_table
url: https://cercind.gov.in/notice-letter.html
content_root: section .wrap-md .container.coc-mid
row_selector: table.tbsa tbody#myTable > tr
link_selector: td.style13 a[href], td a[href]
fields:
  title: td[1]
  publication_date: td[2]
  primary_url: first_link.href
freshness_gate:
  required_for_latest: true
accept_title_patterns:
  - Trading Licensees
  - G-TAM
  - Delivery Timelines
  - Power Exchange
  - contracts
  - reg.
```

### SECI Tenders Parser

```yaml
source_page: seci_tenders
mode: listing_plus_detail
url: https://www.seci.co.in/tenders
listing_content_root: section.tender-section
listing_row_selector: table#tender-list tbody tr.tender-row
detail_link_selector: a.view-detail[href]
listing_fields:
  tender_id: td[1]
  ets_id: td[2]
  tender_ref_no: td[3]
  title: td[4]
  publication_date: td[5]
  bid_submission_date: td[6]
  detail_url: detail_link.href
detail_content_root: section.tender-detail
detail_document_selector: a[href*="/uploads/tenders/"][href$=".pdf"]
corrigendum_selector: a[href*="/uploads/tenders/corrigendums/"][href$=".pdf"]
supporting_file_selector: a[href*="/uploads/tenders/"][href$=".xlsx"]
reject_scopes:
  - '#navbarSupportedContent'
  - .navbar-nav
  - .submenu
  - footer
reject_url_patterns:
  - /uploads/media/
  - /assets/uploads/
  - /payment-modes
  - /documentsfaq
reject_titles:
  - Corporate Brochure
  - CSR Policy
  - Terms of appointment of Independent Director
  - Annual Report
  - Credit Ratings
```

### MoP What's New Parser

```yaml
source_page: mop_whats_new
mode: official_json_api
url: https://www.powermin.gov.in/whats-new
listing_api:
  method: GET
  url: https://www.powermin.gov.in/cms/wp-json/post-page/whats_new
  headers:
    apikey: 4bW5t13453pa
    Content-Type: application/json
post_selector: posts[]
attachment_ids: acf_data.file[]
attachment_api:
  method: GET
  url_template: https://www.powermin.gov.in/cms/wp-json/post-page/post?id={attachment_id}
primary_document_url: posts.acf_data.pdf.url
fields:
  title: post_title
  publication_date: post_date
  issue_date: attachment.posts.acf_data.file_date
  primary_url: attachment.posts.acf_data.pdf.url
accept_title_patterns:
  - Electricity Amendment Rules
  - Jan Vishwas
  - Amendment
  - Rules
  - Notification
  - Guideline
  - Policy
  - Scheme
  - Draft
  - Inviting comments
reject_title_patterns:
  - Selection to the post
  - Appointment of
  - Managing Director
  - Chairman
  - Director Commercial
  - vacancy
  - internship
```

## Replacement Map For The Three Known Bad Outputs

| Bad Output | Why It Was Selected | Correct Selector | Correct Outputs |
|---|---|---|---|
| MNRE `Tenders` landing page | Global nav link under `Notices` matched keyword `tender` | `main div#notice-results-area table.data-table-1 tbody tr` | ALMM List-II notice, SHP Scheme approval, ALMM-Wind SOP amendment, Solar Park timeline OM |
| CERC `Electricity Act 2003` | Dropdown nav PDF matched keyword `amendment` | `section .wrap-md .container.coc-mid table.tbsa tbody#myTable > tr` | CERC public notice rows, SPN petition notices, notice-letter PDFs |
| SECI `Corporate Brochure` | Global media menu PDF matched PDF/document heuristic | `section.tender-section table#tender-list tbody tr.tender-row` plus `section.tender-detail` | RfS FDRE-IX tender, BoS 88 MW solar tender, rooftop solar tender, corrigenda/pre-bid notices |

## Priority For Implementation

P0 extraction changes for next implementation step:

1. Add source-page parser dispatch keyed by `source_pages.page_type` or `source_pages.url`.
2. Implement MNRE Current Notices table parser.
3. Implement MNRE Monthly Updates list parser.
4. Implement CERC static table parser with page variants for Public Notice, SPN, Notice Letter.
5. Implement SECI listing-plus-detail parser.
6. Implement MoP CMS JSON parser.
7. Add strict reject scopes before any keyword scoring.
8. Preserve row metadata into `DiscoveredDoc.raw_summary` or structured metadata for downstream extraction.

P1 extraction quality:

1. Add per-source freshness gates.
2. Add primary-vs-supporting document roles.
3. Add alternate document storage for CERC newspaper links and SECI supporting PDFs/XLSX files.
4. Add fetch fallback strategy for CERC TLS resets.

## Readiness To Implement

The extraction design is now specific enough to implement. The main missing piece is not AI or graph logic. It is parser dispatch and source-specific extraction.

Expected result after implementation:

```text
Curated source page
  -> scoped row/card/API parser
  -> real primary document URL
  -> clean title/date/deadline metadata
  -> document extraction
  -> family/graph/intelligence/event gates
```

This should eliminate the known wrong outputs and produce analyst-grade candidates from the curated pages.
