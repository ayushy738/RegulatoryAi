# Step 23.5 - Extraction Dry Run

Generated: 2026-06-22T17:49:05.677785+00:00

## Scope

- Implemented nothing in product code.
- Created no documents, events, graph records, or database rows.
- Ran only the proposed Step 23 selectors/API reads against live source pages.
- SECI detail pages and MoP attachment APIs were fetched only to resolve primary document URLs.

## Summary

| Source | Rows Discovered | Accepted | Rejected |
|---|---:|---:|---:|
| MNRE Current Notices | 5 | 4 | 1 |
| MNRE Monthly Updates | 31 | 29 | 2 |
| CERC Public Notice | 9 | 6 | 3 |
| CERC SPN | 186 | 184 | 2 |
| CERC Notice Letter | 3 | 3 | 0 |
| SECI Tenders | 17 | 10 | 7 |
| MoP What's New API | 21 | 9 | 12 |

## Source Results

## MNRE Current Notices

- Rows discovered: 5
- Accepted: 4
- Rejected: 1
- Rejection reasons: ADMIN_RECRUITMENT=1

### First 20 Accepted Candidates

| # | Decision | Classification | Title | Date | Primary Document URL | Reason |
|---|---|---|---|---|---|---|
| 1 | ACCEPT | DEADLINE_CHANGE | ALMM – No blanket extension of ALMM List-II beyond 01.06.2026 subject to Protection of Investments already made | 25/05/2026 | https://cdnbbsr.s3waas.gov.in/s3716e1b8c6cd17b771da77391355749f3/uploads/2026/05/202605251665091021.pdf | SECTOR_NOTICE |
| 2 | ACCEPT | SCHEME_APPROVAL | Administrative approval for implementation of Small Hydro Power (SHP) Development Scheme from 1 MW to 25 MW for the period FY 2026–27 to FY 2030–31 | 15/05/2026 | https://cdnbbsr.s3waas.gov.in/s3716e1b8c6cd17b771da77391355749f3/uploads/2026/05/202605151467413059.pdf | SECTOR_NOTICE |
| 3 | ACCEPT | AMENDMENT | Amendment to ‘Standard Operating Procedure (SOP) for Approved List of Models and Manufacturers – Wind (ALMM-Wind) and Approved List of Models and Manufacturers – Wind Turbine Components (ALMM-WTC)’ | 01/12/2025 | https://cdnbbsr.s3waas.gov.in/s3716e1b8c6cd17b771da77391355749f3/uploads/2025/12/202512011712290244.pdf | SECTOR_NOTICE |
| 4 | ACCEPT | DEADLINE_CHANGE | OM regarding extension in timeline of the Solar Park scheme | 17/09/2025 | https://cdnbbsr.s3waas.gov.in/s3716e1b8c6cd17b771da77391355749f3/uploads/2025/09/2025091984030227.pdf | SECTOR_NOTICE |

### Rejected Candidates Observed

| # | Decision | Classification | Title | Date | Primary Document URL | Reason |
|---|---|---|---|---|---|---|
| 1 | REJECT | OTHER | Filling up the post of Scientists ‘D’ and ‘C’ in the Ministry of New and Renewable Energy (MNRE) on deputation/short-term contract basis | 20/04/2026 | https://cdnbbsr.s3waas.gov.in/s3716e1b8c6cd17b771da77391355749f3/uploads/2026/04/20260420272618978.pdf | ADMIN_RECRUITMENT |

## MNRE Monthly Updates

- Rows discovered: 31
- Accepted: 29
- Rejected: 2
- Rejection reasons: NOT_MONTHLY_DIGEST=2

### First 20 Accepted Candidates

| # | Decision | Classification | Title | Date | Primary Document URL | Reason |
|---|---|---|---|---|---|---|
| 1 | ACCEPT | REGULATORY_DIGEST | Renewable Energy Policy and Regulatory update for May 2026 month (546 KB) | May 2026 | https://cdnbbsr.s3waas.gov.in/s3716e1b8c6cd17b771da77391355749f3/uploads/2026/06/20260612775650314.pdf | MONTHLY_REGULATORY_DIGEST |
| 2 | ACCEPT | REGULATORY_DIGEST | Renewable Energy Policy and Regulatory update for April 2026 month (546 KB) | April 2026 | https://cdnbbsr.s3waas.gov.in/s3716e1b8c6cd17b771da77391355749f3/uploads/2026/05/20260507651808978.pdf | MONTHLY_REGULATORY_DIGEST |
| 3 | ACCEPT | REGULATORY_DIGEST | Renewable Energy Policy and Regulatory update for March 2026 month (546 KB) | March 2026 | https://cdnbbsr.s3waas.gov.in/s3716e1b8c6cd17b771da77391355749f3/uploads/2026/04/20260409820674347.pdf | MONTHLY_REGULATORY_DIGEST |
| 4 | ACCEPT | REGULATORY_DIGEST | Renewable Energy Policy and Regulatory update for February 2026 month (546 KB) | February 2026 | https://cdnbbsr.s3waas.gov.in/s3716e1b8c6cd17b771da77391355749f3/uploads/2026/03/202603131939222810.pdf | MONTHLY_REGULATORY_DIGEST |
| 5 | ACCEPT | REGULATORY_DIGEST | Renewable Energy Policy and Regulatory update for January 2026 month (546 KB) | January 2026 | https://cdnbbsr.s3waas.gov.in/s3716e1b8c6cd17b771da77391355749f3/uploads/2026/02/202602181255090521.pdf | MONTHLY_REGULATORY_DIGEST |
| 6 | ACCEPT | REGULATORY_DIGEST | Renewable Energy Policy and Regulatory update for December 2025 month (546 KB) | December 2025 | https://cdnbbsr.s3waas.gov.in/s3716e1b8c6cd17b771da77391355749f3/uploads/2026/01/202601061326094596.pdf | MONTHLY_REGULATORY_DIGEST |
| 7 | ACCEPT | REGULATORY_DIGEST | Renewable Energy Policy and Regulatory update for November2025 month (546 KB) |  | https://cdnbbsr.s3waas.gov.in/s3716e1b8c6cd17b771da77391355749f3/uploads/2025/12/202512031107884201.pdf | MONTHLY_REGULATORY_DIGEST |
| 8 | ACCEPT | REGULATORY_DIGEST | Renewable Energy Policy and Regulatory update for October 2025 month (546 KB) | October 2025 | https://cdnbbsr.s3waas.gov.in/s3716e1b8c6cd17b771da77391355749f3/uploads/2025/11/202511071193339728.pdf | MONTHLY_REGULATORY_DIGEST |
| 9 | ACCEPT | REGULATORY_DIGEST | Renewable Energy Policy and Regulatory update for September 2025 month (546 KB) | September 2025 | https://cdnbbsr.s3waas.gov.in/s3716e1b8c6cd17b771da77391355749f3/uploads/2025/11/202511061104877744.pdf | MONTHLY_REGULATORY_DIGEST |
| 10 | ACCEPT | REGULATORY_DIGEST | Renewable Energy Policy and Regulatory update for August 2025 month (546 KB) | August 2025 | https://cdnbbsr.s3waas.gov.in/s3716e1b8c6cd17b771da77391355749f3/uploads/2025/09/20250902340779229.pdf | MONTHLY_REGULATORY_DIGEST |
| 11 | ACCEPT | REGULATORY_DIGEST | Renewable Energy Policy and Regulatory update for July 2025 month (515 KB) | July 2025 | https://cdnbbsr.s3waas.gov.in/s3716e1b8c6cd17b771da77391355749f3/uploads/2025/08/202508061405529607.pdf | MONTHLY_REGULATORY_DIGEST |
| 12 | ACCEPT | REGULATORY_DIGEST | Renewable Energy Policy and Regulatory update for June 2025 month (557 KB) | June 2025 | https://cdnbbsr.s3waas.gov.in/s3716e1b8c6cd17b771da77391355749f3/uploads/2025/07/202507111961820654.pdf | MONTHLY_REGULATORY_DIGEST |
| 13 | ACCEPT | REGULATORY_DIGEST | Renewable Energy Policy and Regulatory update for May 2025 month (534 KB) | May 2025 | https://cdnbbsr.s3waas.gov.in/s3716e1b8c6cd17b771da77391355749f3/uploads/2025/06/20250617594926682.pdf | MONTHLY_REGULATORY_DIGEST |
| 14 | ACCEPT | REGULATORY_DIGEST | Renewable Energy Policy and Regulatory update for April 2025 month (452 KB) | April 2025 | https://cdnbbsr.s3waas.gov.in/s3716e1b8c6cd17b771da77391355749f3/uploads/2025/05/202505011789049365.pdf | MONTHLY_REGULATORY_DIGEST |
| 15 | ACCEPT | REGULATORY_DIGEST | Renewable Energy Policy and Regulatory update for March 2025 month (253 KB) | March 2025 | https://cdnbbsr.s3waas.gov.in/s3716e1b8c6cd17b771da77391355749f3/uploads/2025/04/202504031937165735.pdf | MONTHLY_REGULATORY_DIGEST |
| 16 | ACCEPT | REGULATORY_DIGEST | Renewable Energy Policy and Regulatory update for February 2025 month (393 KB) | February 2025 | https://cdnbbsr.s3waas.gov.in/s3716e1b8c6cd17b771da77391355749f3/uploads/2025/03/202503101999174139.pdf | MONTHLY_REGULATORY_DIGEST |
| 17 | ACCEPT | REGULATORY_DIGEST | Renewable Energy Policy and Regulatory update for January 2025 month (166 KB) | January 2025 | https://cdnbbsr.s3waas.gov.in/s3716e1b8c6cd17b771da77391355749f3/uploads/2025/02/202502071358166455.pdf | MONTHLY_REGULATORY_DIGEST |
| 18 | ACCEPT | REGULATORY_DIGEST | Renewable Energy Policy and Regulatory update for December 2024 month (477 KB) | December 2024 | https://cdnbbsr.s3waas.gov.in/s3716e1b8c6cd17b771da77391355749f3/uploads/2025/01/20250103602129384.pdf | MONTHLY_REGULATORY_DIGEST |
| 19 | ACCEPT | REGULATORY_DIGEST | Renewable Energy Policy and Regulatory update for November 2024 month (389 KB) | November 2024 | https://cdnbbsr.s3waas.gov.in/s3716e1b8c6cd17b771da77391355749f3/uploads/2024/12/20241202808263895.pdf | MONTHLY_REGULATORY_DIGEST |
| 20 | ACCEPT | REGULATORY_DIGEST | Renewable Energy Policy and Regulatory update for October 2024 month (455 KB) | October 2024 | https://cdnbbsr.s3waas.gov.in/s3716e1b8c6cd17b771da77391355749f3/uploads/2024/11/20241105827746827.pdf | MONTHLY_REGULATORY_DIGEST |

### Rejected Candidates Observed

| # | Decision | Classification | Title | Date | Primary Document URL | Reason |
|---|---|---|---|---|---|---|
| 1 | REJECT | REGULATORY_DIGEST | Presentations of Webinar dt 09.05.2024 on “URET” and ‘RPO” |  | https://cdnbbsr.s3waas.gov.in/s3716e1b8c6cd17b771da77391355749f3/uploads/2024/05/20240513106542998.pdf | NOT_MONTHLY_DIGEST |
| 2 | REJECT | REGULATORY_DIGEST | Renewable Energy Policy & Regulatory update for December 2023 month (261 KB) | December 2023 | https://cdnbbsr.s3waas.gov.in/s3716e1b8c6cd17b771da77391355749f3/uploads/2024/01/20240112923625035.pdf | NOT_MONTHLY_DIGEST |

## CERC Public Notice

- Rows discovered: 9
- Accepted: 6
- Rejected: 3
- Rejection reasons: ADMIN_OR_PROCUREMENT_NOTICE=3

### First 20 Accepted Candidates

| # | Decision | Classification | Title | Date | Primary Document URL | Reason |
|---|---|---|---|---|---|---|
| 1 | ACCEPT | PUBLIC_NOTICE | Notice: Conducting of Hearings through Video Conferencing/Hybrid Mode | 19.05.2026 | https://cercind.gov.in/2026/whatsnew/Notice190526.pdf | PUBLIC_NOTICE |
| 2 | ACCEPT | PUBLIC_NOTICE | Requested to file note of submissions | 05.04.2023 | https://cercind.gov.in/2023/whatsnew/Notice-050423.pdf | PUBLIC_NOTICE |
| 3 | ACCEPT | OTHER | Commission to extend the implementation of Ancillary Services Regulations (Provisions pertaining to TRAS) from 01.05.2023 at the earliest | 27.03.2023 | https://cercind.gov.in/Regulations/167_8.pdf | PUBLIC_NOTICE |
| 4 | ACCEPT | PUBLIC_NOTICE | Refund of Amounts against submission of Bank Guarantees, as per Hon'ble Supreme Court's Orders dated 09.05.2022 and 17.05.2022 in Civil Appeal No. 4801 of 2018 | 04.07.2022 02.07.2024 | https://cercind.gov.in/2022/whatsnew/Refund_BG_040722.pdf | PUBLIC_NOTICE |
| 5 | ACCEPT | PUBLIC_NOTICE | Submission of details of the Assets pertaining to Generating and Transmission Companies through CERC SAUDAMINI e-Assets Module (Final Version) | 04.10.2021 | https://cercind.gov.in/2021/whatsnew/PN-E-Assets_Secretary_041021.pdf | PUBLIC_NOTICE |
| 6 | ACCEPT | PUBLIC_NOTICE | Public Notice dated 27.05.2021 regarding Payment of Annual fees | 27.05.2021 | https://cercind.gov.in/2021/whatsnew/public_notice_270521.pdf | PUBLIC_NOTICE |

### Rejected Candidates Observed

| # | Decision | Classification | Title | Date | Primary Document URL | Reason |
|---|---|---|---|---|---|---|
| 1 | REJECT | OTHER | Empanelment of consulting firm/institutions for Assisting the Commission in Discharging its various Regulatory functions. | 17.06.2026 | https://cercind.gov.in/2026/whatsnew/PN-180626.pdf | ADMIN_OR_PROCUREMENT_NOTICE |
| 2 | REJECT | SCHEME_APPROVAL | CERC Internship Scheme | 02.01.2024 | https://cercind.gov.in/pdf/Internship_Scheme.pdf | ADMIN_OR_PROCUREMENT_NOTICE |
| 3 | REJECT | OTHER | Empanelment of consultinq firm/institutions for Assisting the Commission in Discharqinq its various Regulatory functions. | 11.09.2023 | https://cercind.gov.in/2023/tenders/Empanelment of consulting firm2023.pdf | ADMIN_OR_PROCUREMENT_NOTICE |

## CERC SPN

- Rows discovered: 186
- Accepted: 184
- Rejected: 2
- Rejection reasons: NAV_OR_STATIC_SITE_DOCUMENT=2

### First 20 Accepted Candidates

| # | Decision | Classification | Title | Date | Primary Document URL | Reason |
|---|---|---|---|---|---|---|
| 1 | ACCEPT | TRADING_LICENSE_NOTICE | Application under Section 14 of the Electricity Act, 2003, read with the Central Electricity Regulatory Commission (Procedure, Terms and Conditions for grant of trading license and other related matters) Regulations, 2020. REMC Limited. | 19.06.2026 | https://cercind.gov.in/SPN/185-TD-2026 (TOI-19.6.2026).pdf | STATUTORY_PUBLIC_NOTICE |
| 2 | ACCEPT | TRADING_LICENSE_NOTICE | Application under Section 14 of the Electricity Act, 2003 read with Central Electricity Regulatory Commission (Procedure, Terms and Conditions for grant of trading licence and other related matters) Regulations, 2020. PRMK Energy | 09.06.2026 | https://cercind.gov.in/SPN/214-TD-2026 (IE-9.6.2026).pdf | STATUTORY_PUBLIC_NOTICE |
| 3 | ACCEPT | AMENDMENT | Application under Sections 14, 15, 79(1)(e) of the Electricity Act, 2003 read with the Central Electricity Regulatory Commission (Procedure, Terms and Conditions for Grant of Transmission License and other Related Matters) Regulation, 2024 and any other amendments thereon issued from time to time by this Commission for grant of Transmission License to TP Gopalpur Transmission Limited (earlier known as ERES-XXXIX Power Transmission Limited. | 23.05.2026 | https://cercind.gov.in/SPN/125-TL-2026 (HT-23.5.2026).pdf | STATUTORY_PUBLIC_NOTICE |
| 4 | ACCEPT | TRANSMISSION_LICENSE_NOTICE | Application under Section 14 & 15 of the Electricity Act, 2003 read with Central Electricity Regulatory Commission (Procedure, Terms and Conditions for Grant of Transmission License and other related matters) Regulations, 2024 with respect to Transmission License to SR and ER Power Transmission Limited. SR and ER Power Transmission Limited | 19.05.2026 | https://cercind.gov.in/SPN/121-TL-2026 (Hindu-19.5.2026).pdf | STATUTORY_PUBLIC_NOTICE |
| 5 | ACCEPT | TRANSMISSION_LICENSE_NOTICE | Petition under Sections 14, 15 and 79(1)(e) of Electricity Act, 2003, read with the Central Electricity Regulatory Commission (Procedure, Terms and Conditions for Grant of Transmission License and other related matters) Regulations, 2009 seeking grant of Transmission License for Morena-I SEZ Transmission Limited. Morena-I SEZ Transmission Limited | 16.05.2026 | https://cercind.gov.in/SPN/131-TL-2026 (IE-16.5.2026).pdf | STATUTORY_PUBLIC_NOTICE |
| 6 | ACCEPT | TRANSMISSION_LICENSE_NOTICE | Application under Sections 14 & 15 of the Electricity Act, 2003 read with Central Electricity Regulatory Commission (Procedure, Terms and Conditions for Grant of Transmission License and other related matters) Regulations, 2024 with respect to Transmission License to Bellary Davanagere Power Transmission Limited. Bellary Davanagere Power Transmission Limited | 13.05.2026 | https://cercind.gov.in/SPN/133-TL-2026 (HT-13.5.2026).pdf | STATUTORY_PUBLIC_NOTICE |
| 7 | ACCEPT | TRANSMISSION_LICENSE_NOTICE | Application under Section-14, 15, 79(1)(e) of the Electricity Act, 2003 read with Central Electricity Regulatory Commission (Procedure, Terms and Conditions for Grant of Transmission License and other related matters) Regulations, 2024 with respect to Grant of Transmission License to KPS III HVDC Transmission Limited. KPS III HVDC Transmission Limited | 13.05.2026 | https://cercind.gov.in/SPN/27-TL-2026 (Hindu-13.5.2026).pdf | STATUTORY_PUBLIC_NOTICE |
| 8 | ACCEPT | TRADING_LICENSE_NOTICE | Application under Section 14 and Section 15(1) of the Electricity Act, 2003 read with Regulation 6 of the Central Electricity Regulatory Commission (Procedure, Terms and Conditions for Grant of Trading Licence and other Related Matters) Regulations, 2020, for grant of an inter-state trading license. EKI Energy Services Limited. | 08.05.2026 | https://cercind.gov.in/SPN/92-TD-2026 (ToI-8.5.2026).pdf | STATUTORY_PUBLIC_NOTICE |
| 9 | ACCEPT | TRADING_LICENSE_NOTICE | Application under Section 14 of the Electricity Act, 2003 read with Regulation 6 of the Central Electricity Regulatory Commission (Procedure, Terms and Conditions for grant of trading license and other related matters) Regulations, 2020 for grant of an inter-state trading license. Neufo Technologies Private Limited | 30.04.2026 | https://cercind.gov.in/SPN/93-TD-2026 (IE-30.4.2026).pdf | STATUTORY_PUBLIC_NOTICE |
| 10 | ACCEPT | TRADING_LICENSE_NOTICE | Application under Section 14 and 15 (1) of the Electricity Act, 2003 read with Regulation 6 of the Central Electricity Regulatory Commission (Procedure, Terms and Conditions for Grant of trading license and other related matters), Regulations, 2020 for grant of an inter-state trading license. Energy Advisory Services Private Limited. | 31.03.2026 | https://cercind.gov.in/SPN/32-TD-2026 (The Hindu-31.3.2026).pdf | STATUTORY_PUBLIC_NOTICE |
| 11 | ACCEPT | TRANSMISSION_LICENSE_NOTICE | Application under Section 14 & 15 of the Electricity Act, 2003 read with Central Electricity Regulatory Commission (Procedure, Terms and Conditions for Grant of Transmission License and other related matters) Regulations, 2024 with respect to Transmission License to SR WR Power Transmission Limited. SR WR Power Transmission Limited | 12.03.2026 | https://cercind.gov.in/SPN/885-TL-2025 (HT-12.3.2026).pdf | STATUTORY_PUBLIC_NOTICE |
| 12 | ACCEPT | TRANSMISSION_LICENSE_NOTICE | Application under Section 14, 15 and 79(1)(e) of the Electricity Act, 2003 read with the Central Electricity Regulatory Commission (Procedure, Terms and Conditions for Grant of Transmission License and other related matters) Regulations, 2024 and its subsequent Clarification and replacement, if any, with respect to grant of Transmission License to Angul Sundargarh Transmission Limited. Angul Sundargarh Transmission Limited | 19.02.2026 | https://cercind.gov.in/SPN/824-TL-2025 (ToI-19.2.2026).pdf | STATUTORY_PUBLIC_NOTICE |
| 13 | ACCEPT | TRADING_LICENSE_NOTICE | Application under Section 14 of the Electricity Act, 2003 read with Regulation 6 of the Central Electricity Regulatory Commission (Procedure, Terms and Conditions for grant of trading license and other related matters), Regulations, 2020 for grant of an inter-state trading license. K.P. Energy Limited | 06.02.2026 | https://cercind.gov.in/SPN/868-TD-2025 (HT-6.2.2026).pdf | STATUTORY_PUBLIC_NOTICE |
| 14 | ACCEPT | TRANSMISSION_LICENSE_NOTICE | Application under Sections 14 & 15 of the Electricity Act, 2003 read with the Central Electricity Regulatory Commission (Procedure, Terms and Conditions for Grant of Transmission Licence and other related matters) Regulations, 2024 with respect to Transmission Licence to Vindhyachal Varanasi Transmission Limited. Vindhyachal Varanasi Transmission Limited | 04.02.2026 | https://cercind.gov.in/SPN/886-TL-2025 (Hindu-4.2.2026).pdf | STATUTORY_PUBLIC_NOTICE |
| 15 | ACCEPT | TRADING_LICENSE_NOTICE | Application under Section 14 of the Electricity Act, 2003, read with Regulation 6 of the Central Electricity Regulatory Commission (Procedure, Terms and Conditions for grant of trading license and other related matters), Regulations, 2020, for grant of an inter-state trading license. KPI Green Energy Limited | 20.01.2026 | https://cercind.gov.in/SPN/871-TD-2025 (ToI-20.1.2026).pdf | STATUTORY_PUBLIC_NOTICE |
| 16 | ACCEPT | TRANSMISSION_LICENSE_NOTICE | Petition under sections 14 and 15 (1) of the electricity act, 2003 read with regulation 5 of the central electricity regulatory commission (procedure, terms and conditions for grant of transmission licence and other related matters), regulations, 2024 for grant of transmission licence to Ananthapuram II Power Transmission Ltd. Ananthapuram II Power Transmission Ltd. | 07.01.2026 | https://cercind.gov.in/SPN/872-TL-2025 (Hindu-7.1.2026).pdf | STATUTORY_PUBLIC_NOTICE |
| 17 | ACCEPT | TRANSMISSION_LICENSE_NOTICE | Petition under Sections 14, 15, 79 (1)(e) of the Electricity Act, 2003 read with the Central Electricity Regulatory Commission (Procedure, Terms and Conditions for Grant of Transmission License and other related matters) Regulations, 2024 seeking Transmission License for Rajgarh Neemuch Power Transmission Limited. Rajgarh Neemuch Power Transmission Limited | 01.01.2026 | https://cercind.gov.in/SPN/860-TL-2025 (HT-1.1.2026).pdf | STATUTORY_PUBLIC_NOTICE |
| 18 | ACCEPT | TRANSMISSION_LICENSE_NOTICE | Application under Section 14 & 15 of the Electricity Act, 2003 read with Central Electricity Regulatory Commission (Procedure, Terms and Conditions for Grant of Transmission License and other related matters) Regulations, 2024 with respect to Transmission License to Davanagere Power Transmission Limited. Transmission License to Davanagere Power Transmission Limited. | 31.12.2025 | https://cercind.gov.in/SPN/857TL2025-Eng.pdf | STATUTORY_PUBLIC_NOTICE |
| 19 | ACCEPT | TRANSMISSION_LICENSE_NOTICE | Application under Section 14, 15 and 79(1)(e) of the Electricity Act, 2003 read with the Central Electricity Regulatory Commission (Procedure, Terms and Conditions for Grant of Transmission License and other related matters) Regulations, 2024 and its subsequent Clarification and replacement, if any, with respect to grant of Transmission License to Paradeep Transmission Limited. Paradeep Transmission Limited | 24.12.2025 | https://cercind.gov.in/SPN/73-TL-2025 (HT-24.12.2025).pdf | STATUTORY_PUBLIC_NOTICE |
| 20 | ACCEPT | TRANSMISSION_LICENSE_NOTICE | Application under Sections 14 & 15 of the Electricity Act, 2003 read with the Central Electricity Regulatory Commission (Procedure, Terms and Conditions for Grant of Transmission License and other related matters) Regulations, 2024 with respect to Transmission License to Mandsaur I RE Transmission Limited. Mandsaur I RE Transmission Limited | 18.12.2025 | https://cercind.gov.in/SPN/869-TL-2025 (TH-18.12.2025).pdf | STATUTORY_PUBLIC_NOTICE |

### Rejected Candidates Observed

| # | Decision | Classification | Title | Date | Primary Document URL | Reason |
|---|---|---|---|---|---|---|
| 1 | REJECT | TRADING_LICENSE_NOTICE | Petition under Section 14 of the Electricity Act 2003 read with Regulation 6 of the CERC (Procedure, Terms and Conditions for grant of trading licence and other related matters) Regulations, 2020 for the grant of Category V inter-State Trading Licence. Oasis Greenway Power Trading Private Limited | 19.06.2026 | https://cercind.gov.in/SPN/213-TD-2026 (Hindu-19.6.2026).pdf | NAV_OR_STATIC_SITE_DOCUMENT |
| 2 | REJECT | TRADING_LICENSE_NOTICE | Petition under Section 14 of Electricity Act 2003 read with Regulation 6 of the CERC (Procedure, Terms and Conditions for grant of trading licence and other related matters) Regulations, 2020 for grant of Category V Inter-state Trading License. Greennsure Trading Private Limited | 19.02.2026 | https://cercind.gov.in/SPN/46-TD-2026 (IE-19.2.2026).pdf | NAV_OR_STATIC_SITE_DOCUMENT |

## CERC Notice Letter

- Rows discovered: 3
- Accepted: 3
- Rejected: 0

### First 20 Accepted Candidates

| # | Decision | Classification | Title | Date | Primary Document URL | Reason |
|---|---|---|---|---|---|---|
| 1 | ACCEPT | OTHER | Uploading of Monthly Information on the website of Trading Licensees-reg. | 20.11.2023 | https://cercind.gov.in/2023/whatsnew/Monthly-Trading-Information201123.pdf | NOTICE_LETTER |
| 2 | ACCEPT | OTHER | Explanation regarding introduction of G-TAM Daily T+1 Contracts - reg. | 05.05.2022 | https://cercind.gov.in/2022/whatsnew/IEX.pdf | NOTICE_LETTER |
| 3 | ACCEPT | DEADLINE_CHANGE | Explanation regarding modifications in the Delivery Timelines for the Anyday Contracts from T+2 to T+1 - reg. | 05.05.2022 | https://cercind.gov.in/2022/whatsnew/PXIL.pdf | NOTICE_LETTER |

### Rejected Candidates Observed

_No rejected candidates from the proposed selector._

## SECI Tenders

- Rows discovered: 17
- Accepted: 10
- Rejected: 7
- Rejection reasons: LOW_RELEVANCE_TENDER=5, NON_ENERGY_OR_ADMIN_TENDER=2

### First 20 Accepted Candidates

| # | Decision | Classification | Title | Date | Primary Document URL | Reason |
|---|---|---|---|---|---|---|
| 1 | ACCEPT | TENDER | RfS for assured Peak Supply of 4800 MWh (1200 MW x 4 Hrs.) from ISTS-Connected RE Projects (SECI-FDRE-IX) | 05/06/2026 | https://www.seci.co.in/uploads/tenders/RfS_for_4800_MWh_Peak_Supply_(FDRE-IX)-_final_upload.pdf | ENERGY_TENDER |
| 2 | ACCEPT | TENDER | BoS Tender for Setting up of grid-connected 88 MW Ground mounted Solar PV plant at Chitradurga, Karnataka | 08/05/2026 | https://www.seci.co.in/uploads/tenders/Contractual_Tender_document_88_MW_SPV_BoS.pdf | ENERGY_TENDER |
| 3 | ACCEPT | TENDER | RfS for setting up of 12250 kW Grid-Connected Rooftop Solar PV Projects on JNV Buildings (Phase-II) under RESCO Mode through Tenure-based Competitive Bidding (RTSPV-Tranche-XI) | 29/05/2026 | https://www.seci.co.in/uploads/tenders/RfS_for_12250_kW_RTSPV_Projects_for_JNV_Phase-II_(RTSPV-Tranche-XI).pdf | ENERGY_TENDER |
| 4 | ACCEPT | TENDER | RfS for Supply of 1000 MW Excess Power from RE Projects having Existing PPA (SECI-FDRE-VIII) | 26/12/2025 | https://www.seci.co.in/uploads/tenders/RfS_for_Supply_of_1000_MW_Excess_Power_from_RE_Projects-final_upload.pdf | ENERGY_TENDER |
| 5 | ACCEPT | TENDER | RfS for setting up 5500 kW Grid-Connected Rooftop Solar PV Project under RESCO mode (RTSPV-Tranche-X) | 21/05/2026 | https://www.seci.co.in/uploads/tenders/RfS_for_5500_kW_RTSPV_Projects_(RTSPV-Tranche-X).pdf | ENERGY_TENDER |
| 6 | ACCEPT | TENDER | RfS for Supply of 1000 MW Round-the-Clock Thermal Mimic (RTC-TM) Power from ISTS-Connected RE Power Projects in India (SECI-RTC-TM-V) | 10/03/2026 | https://www.seci.co.in/uploads/tenders/RfS_for_1000_MW-RTC-V-final_upload.pdf | ENERGY_TENDER |
| 7 | ACCEPT | TENDER | RfS for assured Peak Supply of 1500 MWh (500 MW x 3 Hrs.) under CfD Mechanism from ISTS-Connected RE Projects (SECI-CfD-I) | 19/04/2026 | https://www.seci.co.in/uploads/tenders/RfS_for_1500_MWh_assured_Peak_Supply_under_CfD_Mechanism_(CfD-I)-final_upload.pdf | ENERGY_TENDER |
| 8 | ACCEPT | TENDER | RfS for 2000 MW ISTS-Connected Wind Power Projects in India (SECI-Tranche-XX) | 21/04/2026 | https://www.seci.co.in/uploads/tenders/RfS_for_1200_MW_Wind_Tranche-XX.pdf | ENERGY_TENDER |
| 9 | ACCEPT | TENDER | Expression of Interest for Virtual Power Purchase Agreement (VPPA) Based Renewable Energy Procurement | 17/04/2026 | https://www.seci.co.in/uploads/tenders/VPPA_EoI_Demand_Analysis.pdf | ENERGY_TENDER |
| 10 | ACCEPT | CONSULTATION | Stakeholder consultation on Draft RfS, GMPA, GMSA documents for Production and supply of Green Methanol | 06/05/2026 | https://www.seci.co.in/uploads/tenders/Draft_RfS_for_Supply_of_Green_Methanol.pdf | ENERGY_TENDER |

### Rejected Candidates Observed

| # | Decision | Classification | Title | Date | Primary Document URL | Reason |
|---|---|---|---|---|---|---|
| 1 | REJECT | TENDER | Request for Empanelment of Advocates/Law Firms with SECI for 2 years | 12/06/2026 | https://www.seci.co.in/tender-details/YmR2 | NON_ENERGY_OR_ADMIN_TENDER |
| 2 | REJECT | TENDER | Internet Leased Line Services for 10 MW Solar PV Project at Badi Sid, Bap, Jodhpur, Rajasthan | 08/06/2026 | https://www.seci.co.in/tender-details/YmR3 | NON_ENERGY_OR_ADMIN_TENDER |
| 3 | REJECT | TENDER | The per page basis Printing Contract for the newly purchased and SECI owned MFPs at SECI, New Delhi | 08/06/2026 | https://www.seci.co.in/tender-details/Ymd- | LOW_RELEVANCE_TENDER |
| 4 | REJECT | TENDER | 5 Nos. 160 MVA, 220/33 - 33 KV Power Transformer Procurement | 29/05/2026 | https://www.seci.co.in/tender-details/Ymdy | LOW_RELEVANCE_TENDER |
| 5 | REJECT | TENDER | Forward Auction for Condemnation of IT Items of SECI | 04/06/2026 | https://www.seci.co.in/tender-details/YmZz | LOW_RELEVANCE_TENDER |
| 6 | REJECT | TENDER | Supply and Maintenance of Plants at SECI Office | 22/05/2026 | https://www.seci.co.in/tender-details/Ymdw | LOW_RELEVANCE_TENDER |
| 7 | REJECT | TENDER | Selection of Agency for Development, Enhancement, Deployment and Maintenance of SECI Digital Systems | 19/05/2026 | https://www.seci.co.in/tender-details/Ymd0 | LOW_RELEVANCE_TENDER |

## MoP What's New API

- Rows discovered: 21
- Accepted: 9
- Rejected: 12
- Rejection reasons: ADMIN_APPOINTMENT_OR_RECRUITMENT=8, ATTACHMENT_OK=2, LOW_RELEVANCE_WHATS_NEW=2

### First 20 Accepted Candidates

| # | Decision | Classification | Title | Date | Primary Document URL | Reason |
|---|---|---|---|---|---|---|
| 1 | ACCEPT | AMENDMENT | Implementation of decriminalisation measures under the Jan Vishwas(Amendment of Provisions) Act, 2026 | 01/06/2026 | https://powermin.gov.in/static/uploads/2026/06/1aa18ca95f5e1f477b7a0ca36b8bade5.pdf | REGULATORY_UPDATE |
| 2 | ACCEPT | AMENDMENT | Electricity Amendment Rules 2025 | 19/09/2025 | https://powermin.gov.in/static/uploads/2026/06/f89ac0cd4dec58a497aef0f15c653379.pdf | REGULATORY_UPDATE |
| 3 | ACCEPT | AMENDMENT | Seeking comments on Draft Electricity (Amendment) Bill, 2025 | 09/10/2025 | https://powermin.gov.in/static/uploads/2026/06/d6dd3cd2d63edd4ad58130c5512af4ee.pdf | REGULATORY_UPDATE |
| 4 | ACCEPT | AMENDMENT | Extension of the Timeline for Submission of Comments on the Electricity (Amendment) Bill, 2025 | 07/11/2025 | https://powermin.gov.in/static/uploads/2026/06/c91862e80a1459694dc0046d6543153c.pdf | REGULATORY_UPDATE |
| 5 | ACCEPT | CONSULTATION | Seeking comments on Draft National Electricity Policy, 2026 | 20/06/2026 | https://powermin.gov.in/static/uploads/2026/06/0593dd0f9b721abdb5227d7ddf5ca439.pdf | REGULATORY_UPDATE |
| 6 | ACCEPT | DEADLINE_CHANGE | Extension of the Timeline for Submission of Comments and Suggestions on Draft National Electricity Policy, 2026 | 25/02/2026 | https://powermin.gov.in/static/uploads/2026/06/58716fc6f0fbdc8ee72d2144e24ea5fe.pdf | REGULATORY_UPDATE |
| 7 | ACCEPT | OTHER | Directions to Imported Coal-Based generating company under Section 11 of the Electricity Act, 2003 | 27/03/2026 | https://powermin.gov.in/static/uploads/2026/04/09cb460156ab88447919a0cb1650783c.pdf | REGULATORY_UPDATE |
| 8 | ACCEPT | AMENDMENT | Seeking comments on Draft Electricity (Rights of Consumers) Amendment Rules, 2026 | 12/03/2026 | https://powermin.gov.in/static/uploads/2026/04/7cec279f2d03dd673b6c2185c6cfb8ee.pdf | REGULATORY_UPDATE |
| 9 | ACCEPT | DEADLINE_CHANGE | Extension of timeline for submission of Renewable Consumption Obligation (RCO) Compliance details for FY 2024-25 up to 31.05.2026 | 16/04/2026 | https://powermin.gov.in/static/uploads/2026/05/07f01334c51fc3e842ce805979b606e1.pdf | REGULATORY_UPDATE |

### Rejected Candidates Observed

| # | Decision | Classification | Title | Date | Primary Document URL | Reason |
|---|---|---|---|---|---|---|
| 1 | REJECT | OTHER | Selection to the post of Chairman & Managing Director, SJVN Limited through the (SCSC) | 13/06/2026 | https://powermin.gov.in/static/uploads/2026/06/b2569d19ef4019ba9b0642cd7a75c3ba.pdf | ADMIN_APPOINTMENT_OR_RECRUITMENT |
| 2 | REJECT | OTHER | Selection for the post of Managing Director, NTPC Green Energy Limited (NGEL), a schedule ‘A’ CPSE | 12/06/2026 | https://powermin.gov.in/static/uploads/2026/06/b44f6ed80a47e1c6d404371aef249302.pdf | ADMIN_APPOINTMENT_OR_RECRUITMENT |
| 3 | REJECT | OTHER | Appointment of Shri V. Packirisamy to the post of Director Commercial PFC Ltd. | 02/06/2026 | https://powermin.gov.in/static/uploads/2026/06/8458dce0faa7848c8fbf09f4ce6daa03.pdf | ADMIN_APPOINTMENT_OR_RECRUITMENT |
| 4 | REJECT | CONSULTATION | Inviting comments on draft recruitment rules for the post of Library & Information Assistant, CEA | 05/05/2026 | https://powermin.gov.in/static/uploads/2026/05/90db15330d9041dd0706fb9e1fa89b77.pdf | ADMIN_APPOINTMENT_OR_RECRUITMENT |
| 5 | REJECT | OTHER | Appointment to the posts of Whole Time Members i.e. Member (Irrigation) & Member (Power) in Bhakra Beas Management Board (BBMB) | 06/06/2026 | https://powermin.gov.in/static/uploads/2026/05/5e0b09db2cff6b6ee208ee87505afd16.pdf | ADMIN_APPOINTMENT_OR_RECRUITMENT |
| 6 | REJECT | OTHER | Selection for the post of Director (Projects), NHPC Limited, a schedule ‘A’ CPSE | 12/05/2026 | https://powermin.gov.in/static/uploads/2026/06/9b043589285ef65e693ffc12bb1df119.pdf | ADMIN_APPOINTMENT_OR_RECRUITMENT |
| 7 | REJECT | OTHER | Filling up the post of Director (Projects), NTPC, a schedule 'A' CPSE | 23/10/2019 |  | ADMIN_APPOINTMENT_OR_RECRUITMENT |
| 8 | REJECT | OTHER | Filling up of the post of Executive Director in REC Limited, New Delhi on deputation -reg. | 15/02/2021 |  | ADMIN_APPOINTMENT_OR_RECRUITMENT |
| 9 | REJECT | AMENDMENT | Electricity (Amendment) Rules, 2026 alongwith Explanatory Note | 16/03/2026 |  | ATTACHMENT_OK |
| 10 | REJECT | AMENDMENT | Electricity (Amendment) Rules, 2026 alongwith Explanatory Note | 16/03/2026 |  | ATTACHMENT_OK |
| 11 | REJECT | OTHER | Introduction of Insurance Surety Bonds (ISBS) as an Alternative to Bank Guarantee/Bid Security across all Power Procurement Frameworks | 07/04/2026 | https://powermin.gov.in/static/uploads/2026/04/f514a61c5ac5e33b968537621e62aa4b.pdf | LOW_RELEVANCE_WHATS_NEW |
| 12 | REJECT | OTHER | Public Procurement (Preference to Make in India) to provide for Purchase Preference (linked with local content) in respect of Power Sector- Roadmap for achieving 60% Minimum Local Content (MLC) in HVDC Substation (LCC Type) | 30/04/2026 | https://powermin.gov.in/static/uploads/2026/05/9a51267ee37056d28c8335379f44bea9.pdf | LOW_RELEVANCE_WHATS_NEW |

## Dry-Run Verdict

Selectors produced intended candidates from every source without creating downstream records.
