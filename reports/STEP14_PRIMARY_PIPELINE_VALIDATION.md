# Step 14 Primary Document Pipeline Validation

Generated at: 2026-06-21T18:26:41.281944+00:00
Crawl run id: 4

## Sources

- mop: Ministry of Power - https://powermin.gov.in/en (7 candidates)
- cerc: Central Electricity Regulatory Commission - https://cercind.gov.in/ (8 candidates)
- mnre: Ministry of New & Renewable Energy - https://mnre.gov.in/en/monthly-updates/ (8 candidates)
- merc: Maharashtra Electricity Regulatory Commission - https://merc.gov.in/orders/ (8 candidates)

## Metrics

- Sources Attempted: 4
- Candidates Discovered: 31
- Candidates Rejected: 28
- Primary Documents Downloaded: 9
- Pdfs Extracted: 2
- Ocr Performed: 1
- Events Generated: 3
- Accepted Primary Documents: 3
- Duplicates: 0

## Classification Mix

- LISTING_PAGE: 10
- NAVIGATION_PAGE: 4
- AMENDMENT: 3
- HOMEPAGE: 3
- POLICY_UPDATE: 3
- CATEGORY_PAGE: 3
- NOTIFICATION: 2
- CIRCULAR: 1
- TENDER_DOCUMENT: 1
- ORDER: 1

## Failure Analysis

- homepage: 3
- listing page: 10
- category page: 3
- no primary document: 6
- extraction failure: 6
- OCR failure: 0
- duplicate: 0
- other: 0

## Candidate Records

| Source | Classification | Status | OCR | Text | Candidate URL | Primary URL |
|---|---:|---|---|---:|---|---|
| mop | LISTING_PAGE | LISTING_PAGE_DETECTED | not needed | 0 | https://powermin.gov.in/en/content/orders |  |
| mop | CIRCULAR | INSUFFICIENT_CONTENT | not needed | 0 | https://powermin.gov.in/en/circular | https://www.powermin.gov.in/en/circular |
| mop | NAVIGATION_PAGE | NO_PRIMARY_DOCUMENT | not needed | 0 | https://powermin.gov.in/en/announcements |  |
| mop | LISTING_PAGE | LISTING_PAGE_DETECTED | not needed | 0 | https://powermin.gov.in/en/content/important-orders-guidelines-notifications-reports |  |
| mop | AMENDMENT | NO_PRIMARY_DOCUMENT | not needed | 0 | https://powermin.gov.in/en/content/corrigendum-renewable-purchase-obligation-rpo-and-energy-storage-obligation-trajectory-till |  |
| mop | TENDER_DOCUMENT | accepted | not needed | 978522 | https://www.powermin.gov.in/static/uploads/2025/07/594ead76be03f235d20bfb24c0032a4b.pdf | https://www.powermin.gov.in/static/uploads/2025/07/594ead76be03f235d20bfb24c0032a4b.pdf |
| mop | HOMEPAGE | HOMEPAGE_DETECTED | not needed | 0 | https://rdss.powermin.gov.in/ |  |
| cerc | LISTING_PAGE | LISTING_PAGE_DETECTED | not needed | 0 | https://cercind.gov.in/recent_orders.html |  |
| cerc | HOMEPAGE | HOMEPAGE_DETECTED | not needed | 0 | https://cercind.gov.in/index-en.html |  |
| cerc | LISTING_PAGE | LISTING_PAGE_DETECTED | not needed | 0 | https://www.cercind.gov.in/Current_reg.html |  |
| cerc | LISTING_PAGE | LISTING_PAGE_DETECTED | not needed | 0 | http://cercind.gov.in/Regulations.html |  |
| cerc | LISTING_PAGE | LISTING_PAGE_DETECTED | not needed | 0 | https://www.cercind.gov.in/orders.html |  |
| cerc | LISTING_PAGE | LISTING_PAGE_DETECTED | not needed | 0 | http://www.cercind.gov.in/regulations.html |  |
| cerc | HOMEPAGE | HOMEPAGE_DETECTED | not needed | 0 | http://cercind.gov.in |  |
| cerc | ORDER | NO_PRIMARY_DOCUMENT | not needed | 0 | https://cercind.gov.in/2025/orders/2-SM-2025.pdf |  |
| mnre | NAVIGATION_PAGE | NO_PRIMARY_DOCUMENT | not needed | 0 | https://mnre.gov.in/en/ |  |
| mnre | NAVIGATION_PAGE | NO_PRIMARY_DOCUMENT | not needed | 0 | https://mnre.gov.in/association-of-renewable-energy-agencies-of-states-areas/ |  |
| mnre | POLICY_UPDATE | INSUFFICIENT_CONTENT | not needed | 167 | https://mnre.gov.in/en/lab-policy-standards-and-quality-control/ | https://mnre.gov.in/en/lab-policy-standards-and-quality-control/ |
| mnre | CATEGORY_PAGE | CATEGORY_PAGE_DETECTED | not needed | 0 | https://mnre.gov.in/solar-thermal/ |  |
| mnre | CATEGORY_PAGE | CATEGORY_PAGE_DETECTED | not needed | 0 | https://mnre.gov.in/en/solar/ |  |
| mnre | CATEGORY_PAGE | CATEGORY_PAGE_DETECTED | not needed | 0 | https://mnre.gov.in/en/wind/ |  |
| mnre | LISTING_PAGE | LISTING_PAGE_DETECTED | not needed | 0 | https://mnre.gov.in/en/monthly-updates/ |  |
| mnre | LISTING_PAGE | LISTING_PAGE_DETECTED | not needed | 0 | https://mnre.gov.in/en/notice-category/recruitments/ |  |
| merc | LISTING_PAGE | LISTING_PAGE_DETECTED | not needed | 0 | https://merc.gov.in/orders/ |  |
| merc | AMENDMENT | INSUFFICIENT_CONTENT | not needed | 133 | https://merc.gov.in/the-electricity-act-2003/ | https://merc.gov.in/the-electricity-act-2003/ |
| merc | POLICY_UPDATE | INSUFFICIENT_CONTENT | not needed | 87 | https://merc.gov.in/policy_type/tariff-policies/ | https://merc.gov.in/policy_type/tariff-policies/ |
| merc | POLICY_UPDATE | INSUFFICIENT_CONTENT | not needed | 73 | https://merc.gov.in/electricity-policy/ | https://merc.gov.in/electricity-policy/ |
| merc | NOTIFICATION | accepted | not needed | 68576 | https://merc.gov.in/wp-content/uploads/2022/07/Energy-Conservation-Act-2001.pdf | https://merc.gov.in/wp-content/uploads/2022/07/Energy-Conservation-Act-2001.pdf |
| merc | AMENDMENT | INSUFFICIENT_CONTENT | attempted | 0 | https://merc.gov.in/wp-content/uploads/2022/07/The-Energy-Conservation-Amendment-Act-2010.pdf | https://merc.gov.in/wp-content/uploads/2022/07/The-Energy-Conservation-Amendment-Act-2010.pdf |
| merc | NOTIFICATION | accepted | not needed | 2576 | https://merc.gov.in/goi_rule_noti/rules-by-notification/ | https://merc.gov.in/goi_rule_noti/rules-by-notification/ |
| merc | NAVIGATION_PAGE | NO_PRIMARY_DOCUMENT | not needed | 0 | https://merc.gov.in/existing-regulations/ |  |

## Generated Events

### Event 24: RFP for Selection of Bidder as Transmission Service Provider

- Issuer: Ministry of Power
- Classification: TENDER_DOCUMENT
- Issue date: 2018-05-11
- Deadline: 11.07.2023
- Summary: RFP for Selection of Bidder as Transmission Service Provider STANDARD SINGLE STAGE REQUEST FOR PROPOSAL DOCUMENT FOR SELECTION OF BIDDER AS TRANSMISSION SERVICE PROVIDER THROUGH TARIFF BASED COMPETITIVE BIDDING PROCESS TO ESTABLISH INTER-STATE TRANSMISSION SYSTEM FOR TRANSMISSION SYSTEM FOR EVACUATION OF POWER FROM REZ IN RAJASTHAN (20 GW) UNDER PHASE-III PART I ISSUED BY REC Power Development and Consultancy Limited (Formerly REC Power Distribution Company Limited) (A wholly owned subsidiary of REC Limited) Registered Office: Core-4, SCOPE Complex, 7, Lodhi Road, New Delhi – 110 003 Email: pshariharan@recpdcl.in & tbcb@recpdcl.in 11.07.2023 REC Power Development and Consultancy Limited 1 RF
- Why it matters: This may create a procurement or bidding opportunity. Commercial teams should check eligibility, submission requirements, and bid deadlines.
- Evidence excerpt: RFP for Selection of Bidder as Transmission Service Provider STANDARD SINGLE STAGE REQUEST FOR PROPOSAL DOCUMENT FOR SELECTION OF BIDDER AS TRANSMISSION SERVICE PROVIDER THROUGH TARIFF BASED COMPETITIVE BIDDING PROCESS TO ESTABLISH INTER-STATE TRANSMISSION SYSTEM FOR TRANSMISSION SYSTEM FOR EVACUATION OF POWER FROM REZ IN RAJASTHAN (20 GW) UNDER PHASE-III PART I ISSUED BY REC Power Development and Consultancy Limited (Formerly REC Power Distribution Company Limited) (A wholly owned subsidiary of
- Scores: title 8/10, document 9/10, summary 5/10, usefulness 7/10
- Quality note: Strong primary document capture, but extracted issue/deadline dates are noisy and the summary is still too close to the first page text.

### Event 25: The Energy Conservation Act, 2001

- Issuer: Maharashtra Electricity Regulatory Commission
- Classification: NOTIFICATION
- Issue date: 2001-10-19
- Deadline: 19-10-2001
- Summary: SEC. 1 THE GAZETTE OF INDIA EXTRAORDINARY 3 MINISTRY OF LAW, JUSTICE AND COMPANY AFFAIRS (Legislative Department) New Delhi, the 1st October, 2001/ Asvina 9, 1923 (Saka) The following Act of Parliament received the assent of the President on the 29th September, 2001, and is hereby published for general information:-- THE ENERGY CONSERVATION ACT, 2001 No 52 2001 OF [29th September 2001] An Act to provide for efficient use of energy and its conservation and for matters connected therewith or incidental thereto. BE it enacted by Parliament in the Fifty second Year of the Republic of India as follows:— CHAPTER I PRELIMINARY 1. (1) This Act may be called the Energy Conservation Act, 2001. Short t
- Why it matters: This is an official regulatory publication that may affect obligations, permissions, tariffs, or operating procedures.
- Evidence excerpt: SEC. 1 THE GAZETTE OF INDIA EXTRAORDINARY 3 MINISTRY OF LAW, JUSTICE AND COMPANY AFFAIRS (Legislative Department) New Delhi, the 1st October, 2001/ Asvina 9, 1923 (Saka) The following Act of Parliament received the assent of the President on the 29th September, 2001, and is hereby published for general information:-- THE ENERGY CONSERVATION ACT, 2001 No 52 2001 OF [29th September 2001] An Act to provide for efficient use of energy and its conservation and for matters connected therewith or incid
- Scores: title 7/10, document 9/10, summary 5/10, usefulness 4/10
- Quality note: Backed by a real primary PDF, but this is a 2001 foundational Act and should not appear as a fresh Latest item.

### Event 26: Notification

- Issuer: Maharashtra Electricity Regulatory Commission
- Classification: NOTIFICATION
- Issue date: 2023-09-12
- Deadline: 12-09-2023
- Summary: Rules By Notification S.No. Date Description Attachments 1 12-09-2023 Working Group for review of Transmission Planning/Underutilization aspect and pricing framework. Notification 2 13-09-2023 Compliance to order dated: 13.02.2023 in MERC Case No. 199 of 2022 Notification 3 24-06-2003 Payment of arrears against electricity bills for water supply and street lights Notification 4 31-03-2003 Electricity Duty Act, 1958 Notification 5 14-05-2003 Payment of arrears against electricity bills by Municipal Council/Corporation Notification 6 04-12-2003 MERC (Preparation of Annual Reports) Rules, 2003 Notification 7 19-05-2004 Maharashtra Tax on Sale of Electricity Act, 1963 Notification 8 03-07-2004 M
- Why it matters: This is an official regulatory publication that may affect obligations, permissions, tariffs, or operating procedures.
- Evidence excerpt: Rules By Notification S.No. Date Description Attachments 1 12-09-2023 Working Group for review of Transmission Planning/Underutilization aspect and pricing framework. Notification 2 13-09-2023 Compliance to order dated: 13.02.2023 in MERC Case No. 199 of 2022 Notification 3 24-06-2003 Payment of arrears against electricity bills for water supply and street lights Notification 4 31-03-2003 Electricity Duty Act, 1958 Notification 5 14-05-2003 Payment of arrears against electricity bills by Municip
- Scores: title 3/10, document 5/10, summary 4/10, usefulness 3/10
- Quality note: This is an extracted HTML notification index/table, not a clean single regulatory event. It proves extraction works but should be rejected or split before user display.

## Transition Verdict

- Crawler to Primary Document to Event: validated
- Success criterion met: partial / not yet product-ready
- Notes: Three new events were backed by extracted primary text, but only one is close to Latest-page quality. Date freshness, document-vs-index discrimination, and synthesis quality still need tightening before this should be trusted without cleanup.
