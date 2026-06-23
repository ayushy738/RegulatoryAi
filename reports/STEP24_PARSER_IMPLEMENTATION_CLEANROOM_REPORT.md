# Step 24 Parser Implementation Clean-Room Report

Generated: 2026-06-23T00:10:59

## Scope

Implemented source-specific extraction parsers only. No UI, graph, RAG, Ask, dashboard, or intelligence logic was changed. The existing crawler and downstream event pipeline were preserved.

## Implementation Summary

- MNRE Current Notices now reads the current-notice table rows and S3WaaS PDF links.
- MNRE Monthly Updates now extracts monthly regulatory update PDFs and stores month-level issue precision.
- CERC Public Notice, SPN, and Notice Letter now use table-specific selectors from the validated dry run.
- CERC SPN no longer rejects petition rows just because the subject mentions the Electricity Act; only the standalone `act-with-amendment.pdf` navigation document is rejected.
- SECI Tenders now follows tender detail pages and selects primary tender/RFS/RFP PDFs instead of the tender landing page or corporate brochure.
- MoP What's New now uses the WordPress JSON API, resolves attachment records, and handles `pdf_both` so `Electricity (Amendment) Rules, 2026 alongwith Explanatory Note` receives a real PDF URL.

## Clean-Room Run

- Backup created before truncation: `E:\RegulatoryAi\reports\backups\cleanroom_backup_20260622T180111Z.json`
- Latest crawl run: `1`
- Status: `success`
- Started: `2026-06-22T18:01:53.233134+00:00`
- Finished: `2026-06-22T18:17:26.249658+00:00`
- Candidates discovered by run: `45`
- Events created by run: `20`
- Run errors: `[]`

Note: the clean-room utility completed the crawl/event stage successfully, then stalled in its optional graph-extraction/reporting stage. I stopped the orphaned Python processes after confirming the crawl run was `success`. Graph table counts remained zero, and no graph logic was modified.

## Headline Results

- Source pages crawled: `7`
- Candidates discovered: `45`
- Extracted documents stored: `39`
- Accepted events: `20`
- Event-gate rejections: `19`
- Discovery/extraction rejections: `6`

## Source-Wise Precision

| Source | Source Page | Type | Candidates | Primary Accepted | Primary Rejected | Extracted Docs | Accepted Events | Rejected Events | Extraction Precision | Event Yield |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| cerc | Public Notice | public_notice_listing | 6 | 5 | 1 | 5 | 0 | 5 | 83.3% | 0.0% |
| cerc | Suo Motu Petitions / Staff Papers / Notices | spn_listing | 8 | 7 | 1 | 7 | 3 | 4 | 87.5% | 42.9% |
| cerc | Notice / Letter | notice_letter_listing | 3 | 3 | 0 | 3 | 0 | 3 | 100.0% | 0.0% |
| mnre | Current Notices | notice_listing | 4 | 2 | 2 | 2 | 1 | 1 | 50.0% | 50.0% |
| mnre | Monthly Updates | digest_listing | 8 | 8 | 0 | 8 | 2 | 6 | 100.0% | 25.0% |
| mop | What's New | whats_new_listing | 8 | 6 | 2 | 6 | 6 | 0 | 75.0% | 100.0% |
| seci | Tenders | tender_listing | 8 | 8 | 0 | 8 | 8 | 0 | 100.0% | 100.0% |

## Extracted Documents

| Doc ID | Source | Page | Title | Issue Date | Type | Text Chars | Event? | Event ID | Gate/Rejection | URL |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 11 | cerc | Public Notice | Requested to file note of submissions | 2023-04-05 | pdf | 767 | no |  | HISTORICAL_DOCUMENT | https://cercind.gov.in/2023/whatsnew/Notice-050423.pdf |
| 12 | cerc | Public Notice | Commission to extend the implementation of Ancillary Services Regulations (Provisions pertaining to TRAS) from 01.05.2023 at th... | 2023-03-27 | pdf | 1684 | no |  | HISTORICAL_DOCUMENT | https://cercind.gov.in/Regulations/167_8.pdf |
| 13 | cerc | Public Notice | Refund of Amounts against submission of Bank Guarantees, as per Hon'ble Supreme Court's Orders dated 09.05.2022 and 17.05.2022... | 2022-07-04 | pdf | 198855 | no |  | HISTORICAL_DOCUMENT | https://cercind.gov.in/2022/whatsnew/Refund_BG_040722.pdf |
| 14 | cerc | Public Notice | Submission of details of the Assets pertaining to Generating and Transmission Companies through CERC SAUDAMINI e-Assets Module... | 2021-10-04 | pdf | 1611 | no |  | HISTORICAL_DOCUMENT | https://cercind.gov.in/2021/whatsnew/PN-E-Assets_Secretary_041021.pdf |
| 15 | cerc | Public Notice | Public Notice dated 27.05.2021 regarding Payment of Annual fees | 2021-05-27 | pdf | 1354 | no |  | HISTORICAL_DOCUMENT | https://cercind.gov.in/2021/whatsnew/public_notice_270521.pdf |
| 16 | cerc | Suo Motu Petitions / Staff Papers / Notices | 213/TD/2026 - Petition under Section 14 of the Electricity Act 2003 read with Regulation 6 of the CERC (Procedure, Terms and Co... | 2026-06-19 | pdf | 1074 | yes | 4 | MEDIUM | https://cercind.gov.in/SPN/213-TD-2026%20(Hindu-19.6.2026).pdf |
| 17 | cerc | Suo Motu Petitions / Staff Papers / Notices | 185/TD/2026 - Application under Section 14 of the Electricity Act, 2003, read with the Central Electricity Regulatory Commissio... | 2026-06-19 | pdf | 1690 | yes | 5 | CRITICAL | https://cercind.gov.in/SPN/185-TD-2026%20(TOI-19.6.2026).pdf |
| 18 | cerc | Suo Motu Petitions / Staff Papers / Notices | 125/TL/2026 - Application under Sections 14, 15, 79(1)(e) of the Electricity Act, 2003 read with the Central Electricity Regula... | 2026-05-23 | pdf | 5829 | yes | 6 | CRITICAL | https://cercind.gov.in/SPN/125-TL-2026%20(HT-23.5.2026).pdf |
| 19 | cerc | Suo Motu Petitions / Staff Papers / Notices | 121/TL/2026 - Application under Section 14 & 15 of the Electricity Act, 2003 read with Central Electricity Regulatory Commissio... | 2026-05-19 | pdf | 3326 | no |  | EXPIRED_OPPORTUNITY | https://cercind.gov.in/SPN/121-TL-2026%20(Hindu-19.5.2026).pdf |
| 20 | cerc | Suo Motu Petitions / Staff Papers / Notices | 131/TL/2026 - Petition under Sections 14, 15 and 79(1)(e) of Electricity Act, 2003, read with the Central Electricity Regulator... | 2026-05-16 | pdf | 2924 | no |  | EXPIRED_OPPORTUNITY | https://cercind.gov.in/SPN/131-TL-2026%20(IE-16.5.2026).pdf |
| 21 | cerc | Suo Motu Petitions / Staff Papers / Notices | 133/TL/2026 - Application under Sections 14 & 15 of the Electricity Act, 2003 read with Central Electricity Regulatory Commissi... | 2026-05-13 | pdf | 3120 | no |  | EXPIRED_OPPORTUNITY | https://cercind.gov.in/SPN/133-TL-2026%20(HT-13.5.2026).pdf |
| 22 | cerc | Suo Motu Petitions / Staff Papers / Notices | 27/TL/2026 - Application under Section-14, 15, 79(1)(e) of the Electricity Act, 2003 read with Central Electricity Regulatory C... | 2026-05-13 | pdf | 4695 | no |  | EXPIRED_OPPORTUNITY | https://cercind.gov.in/SPN/27-TL-2026%20(Hindu-13.5.2026).pdf |
| 23 | cerc | Notice / Letter | Uploading of Monthly Information on the website of Trading Licensees-reg. | 2023-11-20 | pdf | 5481 | no |  | HISTORICAL_DOCUMENT | https://cercind.gov.in/2023/whatsnew/Monthly-Trading-Information201123.pdf |
| 24 | cerc | Notice / Letter | Explanation regarding introduction of G-TAM Daily T+1 Contracts - reg. | 2022-05-05 | pdf | 2157 | no |  | HISTORICAL_DOCUMENT | https://cercind.gov.in/2022/whatsnew/IEX.pdf |
| 25 | cerc | Notice / Letter | Explanation regarding modifications in the Delivery Timelines for the Anyday Contracts from T+2 to T+1 - reg. | 2022-05-05 | pdf | 2198 | no |  | HISTORICAL_DOCUMENT | https://cercind.gov.in/2022/whatsnew/PXIL.pdf |
| 1 | mnre | Current Notices | Administrative approval for implementation of Small Hydro Power (SHP) Development Scheme from 1 MW to 25 MW for the period FY 2... | 2026-05-15 | pdf | 54449 | yes | 1 | CRITICAL | https://cdnbbsr.s3waas.gov.in/s3716e1b8c6cd17b771da77391355749f3/uploads/2026/05/202605151467413059.pdf |
| 2 | mnre | Current Notices | Amendment to ‘Standard Operating Procedure (SOP) for Approved List of Models and Manufacturers – Wind (ALMM-Wind) and Approved... | 2025-12-01 | pdf | 2038 | no |  | HISTORICAL_DOCUMENT | https://cdnbbsr.s3waas.gov.in/s3716e1b8c6cd17b771da77391355749f3/uploads/2025/12/202512011712290244.pdf |
| 3 | mnre | Monthly Updates | Renewable Energy Policy and Regulatory update for May 2026 month (546 KB) | 2026-05-01 | pdf | 18127 | yes | 2 | CRITICAL | https://cdnbbsr.s3waas.gov.in/s3716e1b8c6cd17b771da77391355749f3/uploads/2026/06/20260612775650314.pdf |
| 4 | mnre | Monthly Updates | Renewable Energy Policy and Regulatory update for April 2026 month (546 KB) | 2026-04-01 | pdf | 13643 | no |  | EXPIRED_OPPORTUNITY | https://cdnbbsr.s3waas.gov.in/s3716e1b8c6cd17b771da77391355749f3/uploads/2026/05/20260507651808978.pdf |
| 5 | mnre | Monthly Updates | Renewable Energy Policy and Regulatory update for March 2026 month (546 KB) | 2026-03-01 | pdf | 11772 | no |  | EXPIRED_OPPORTUNITY | https://cdnbbsr.s3waas.gov.in/s3716e1b8c6cd17b771da77391355749f3/uploads/2026/04/20260409820674347.pdf |
| 6 | mnre | Monthly Updates | Renewable Energy Policy and Regulatory update for February 2026 month (546 KB) | 2026-02-01 | pdf | 7846 | yes | 3 | CRITICAL | https://cdnbbsr.s3waas.gov.in/s3716e1b8c6cd17b771da77391355749f3/uploads/2026/03/202603131939222810.pdf |
| 7 | mnre | Monthly Updates | Renewable Energy Policy and Regulatory update for January 2026 month (546 KB) | 2026-01-01 | pdf | 16732 | no |  | EXPIRED_OPPORTUNITY | https://cdnbbsr.s3waas.gov.in/s3716e1b8c6cd17b771da77391355749f3/uploads/2026/02/202602181255090521.pdf |
| 8 | mnre | Monthly Updates | Renewable Energy Policy and Regulatory update for December 2025 month (546 KB) | 2025-12-01 | pdf | 29280 | no |  | EXPIRED_OPPORTUNITY | https://cdnbbsr.s3waas.gov.in/s3716e1b8c6cd17b771da77391355749f3/uploads/2026/01/202601061326094596.pdf |
| 9 | mnre | Monthly Updates | Renewable Energy Policy and Regulatory update for November2025 month (546 KB) | 2025-11-20 | pdf | 10399 | no |  | HISTORICAL_DOCUMENT | https://cdnbbsr.s3waas.gov.in/s3716e1b8c6cd17b771da77391355749f3/uploads/2025/12/202512031107884201.pdf |
| 10 | mnre | Monthly Updates | Renewable Energy Policy and Regulatory update for October 2025 month (546 KB) | 2025-10-01 | pdf | 15100 | no |  | HISTORICAL_DOCUMENT | https://cdnbbsr.s3waas.gov.in/s3716e1b8c6cd17b771da77391355749f3/uploads/2025/11/202511071193339728.pdf |
| 26 | mop | What's New | Implementation of decriminalisation measures under the Jan Vishwas (Amendment of Provisions) Act, 2026 | 2026-06-01 | pdf | 388708 | yes | 7 | CRITICAL | https://www.powermin.gov.in/static/uploads/2026/06/1aa18ca95f5e1f477b7a0ca36b8bade5.pdf |
| 27 | mop | What's New | Electricity Amendment Rules 2025 | 2025-09-19 | pdf | 4984 | yes | 8 | CRITICAL | https://www.powermin.gov.in/static/uploads/2026/06/f89ac0cd4dec58a497aef0f15c653379.pdf |
| 28 | mop | What's New | Seeking comments on Draft Electricity (Amendment) Bill, 2025. | 2025-10-09 | pdf | 87926 | yes | 9 | CRITICAL | https://www.powermin.gov.in/static/uploads/2026/06/d6dd3cd2d63edd4ad58130c5512af4ee.pdf |
| 29 | mop | What's New | Seeking comments on Draft National Electricity Policy, 2026 | 2026-06-20 | pdf | 84824 | yes | 10 | CRITICAL | https://www.powermin.gov.in/static/uploads/2026/06/0593dd0f9b721abdb5227d7ddf5ca439.pdf |
| 30 | mop | What's New | Electricity (Amendment) Rules, 2026 alongwith Explanatory Note | 2026-03-16 | pdf | 34331 | yes | 11 | CRITICAL | https://www.powermin.gov.in/static/uploads/2026/04/cbe6e10292387044a4b5ecb684198562.pdf |
| 31 | mop | What's New | Directions to Imported Coal-Based generating company under Section 11 of the Electricity Act, 2003 | 2026-03-27 | pdf | 7274 | yes | 12 | CRITICAL | https://www.powermin.gov.in/static/uploads/2026/04/09cb460156ab88447919a0cb1650783c.pdf |
| 32 | seci | Tenders | RfS for assured Peak Supply of 4800 MWh (1200 MW x 4 Hrs.) from ISTS-Connected RE Projects (SECI-FDRE-IX) | 2026-06-05 | pdf | 328272 | yes | 13 | CRITICAL | https://www.seci.co.in/uploads/tenders/RfS_for_4800_MWh_Peak_Supply_(FDRE-IX)-_final_upload.pdf |
| 33 | seci | Tenders | BoS Tender for Setting up of grid-connected 88 MW Ground mounted Solar PV plant at Chitradurga, Karnataka | 2026-05-08 | pdf | 660991 | yes | 14 | CRITICAL | https://www.seci.co.in/uploads/tenders/Contractual_Tender_document_88_MW_SPV_BoS.pdf |
| 34 | seci | Tenders | RfS for setting up of 12250 kW Grid-Connected Rooftop Solar PV Projects on JNV Buildings (Phase-II) under RESCO Mode through Te... | 2026-05-29 | pdf | 290980 | yes | 15 | CRITICAL | https://www.seci.co.in/uploads/tenders/RfS_for_12250_kW_RTSPV_Projects_for_JNV_Phase-II_(RTSPV-Tranche-XI).pdf |
| 35 | seci | Tenders | RfS for Supply of 1000 MW Excess Power from RE Projects having Existing PPA (SECI-FDRE-VIII) | 2025-12-26 | pdf | 294441 | yes | 16 | CRITICAL | https://www.seci.co.in/uploads/tenders/RfS_for_Supply_of_1000_MW_Excess_Power_from_RE_Projects-final_upload.pdf |
| 36 | seci | Tenders | RfS for setting up 5500 kW Grid-Connected Rooftop Solar PV Project under RESCO mode (RTSPV-Tranche-X) | 2026-05-21 | pdf | 280773 | yes | 17 | CRITICAL | https://www.seci.co.in/uploads/tenders/RfS_for_5500_kW_RTSPV_Projects_(RTSPV-Tranche-X).pdf |
| 37 | seci | Tenders | RfS for Supply of 1000 MW Round-the-Clock Thermal Mimic (RTC-TM) Power from ISTS-Connected RE Power Projects in India (SECI-RTC... | 2026-03-10 | pdf | 324801 | yes | 18 | CRITICAL | https://www.seci.co.in/uploads/tenders/RfS_for_1000_MW-RTC-V-final_upload.pdf |
| 38 | seci | Tenders | RfS for assured Peak Supply of 1500 MWh (500 MW x 3 Hrs.) under CfD Mechanism from ISTS-Connected RE Projects (SECI-CfD-I) | 2026-04-19 | pdf | 316046 | yes | 19 | CRITICAL | https://www.seci.co.in/uploads/tenders/RfS_for_1500_MWh_assured_Peak_Supply_under_CfD_Mechanism_(CfD-I)-final_upload.pdf |
| 39 | seci | Tenders | RfS for 2000 MW ISTS-Connected Wind Power Projects in India (SECI-Tranche-XX) | 2026-04-21 | pdf | 278946 | yes | 20 | CRITICAL | https://www.seci.co.in/uploads/tenders/RfS_for_1200_MW_Wind_Tranche-XX.pdf |

## Accepted Events

| Event ID | Doc ID | Source | Page | Title | Date | Type | Event Type | Quality | Significance | Actionability | Summary |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 1 | mnre | Current Notices | Administrative approval for implementation of Small Hydro Power (SHP) Development Scheme from 1 MW to 25 MW for the period FY 2... | 2026-05-15 | pdf | NEW | 90 | CRITICAL | INFORMATIONAL | What changed: Amendment. acity addition. . Develop and maintain MIS dashboards at scheme level. . Flag delays, bottlenecks, and... |
| 2 | 3 | mnre | Monthly Updates | Renewable Energy Policy and Regulatory update for May 2026 month (546 KB) | 2026-05-01 | pdf | NEW | 100 | CRITICAL | ACTIONABLE | What changed: Amendment. tory Updates, May 2026 3 2. Draft Central Electricity Regulatory Commission 20th May, 2026 (Connectivi... |
| 3 | 6 | mnre | Monthly Updates | Renewable Energy Policy and Regulatory update for February 2026 month (546 KB) | 2026-02-01 | pdf | NEW | 100 | CRITICAL | ACTIONABLE | What changed: Tender Submission Deadline added. Previous: unknown. New: 2027-07-31. |
| 4 | 16 | cerc | Suo Motu Petitions / Staff Papers / Notices | 213/TD/2026 - Petition under Section 14 of the Electricity Act 2003 read with Regulation 6 of the CERC (Procedure, Terms and Co... | 2026-06-19 | pdf | NEW | 69 | MEDIUM | INFORMATIONAL | What changed: New regulatory primary document detected. TH E HINac/ ELECTRICITY i10N 6th, 7th, & 8th Floor, Tower.B, World Trad... |
| 5 | 17 | cerc | Suo Motu Petitions / Staff Papers / Notices | 185/TD/2026 - Application under Section 14 of the Electricity Act, 2003, read with the Central Electricity Regulatory Commissio... | 2026-06-19 | pdf | NEW | 93 | CRITICAL | ACTIONABLE | What changed: Consultation Update. icence to the applicant for irter-State trading in electricity across India ; . 4. Notice is... |
| 6 | 18 | cerc | Suo Motu Petitions / Staff Papers / Notices | 125/TL/2026 - Application under Sections 14, 15, 79(1)(e) of the Electricity Act, 2003 read with the Central Electricity Regula... | 2026-05-23 | pdf | NEW | 89 | CRITICAL | INFORMATIONAL | What changed: Amendment. Central Ele e le rnrnlssion 7th Floor. Tower World Trade Centre Nauro jl Nagar. New Delhi-110029 BERgE... |
| 7 | 26 | mop | What's New | Implementation of decriminalisation measures under the Jan Vishwas (Amendment of Provisions) Act, 2026 | 2026-06-01 | pdf | NEW | 90 | CRITICAL | INFORMATIONAL | What changed: Amendment. II—SEC. 3(ii)] MINISTRY OF POWER NOTIFICATION New Delhi, the 18th May, 2026 S.O. 2552(E).— In exercise... |
| 8 | 27 | mop | What's New | Electricity Amendment Rules 2025 | 2025-09-19 | pdf | NEW | 85 | CRITICAL | INFORMATIONAL | What changed: Amendment. overnment hereby makes the following rules further to amend the Electricity Rules, 2005, namely:- 1. S... |
| 9 | 28 | mop | What's New | Seeking comments on Draft Electricity (Amendment) Bill, 2025. | 2025-10-09 | pdf | NEW | 90 | CRITICAL | INFORMATIONAL | What changed: Amendment. Draft DRAFT ELECTRICITY (AMENDMENT) BILL, 2025 A BILL further to amend the Electricity Act, 2003 BE it... |
| 10 | 29 | mop | What's New | Seeking comments on Draft National Electricity Policy, 2026 | 2026-06-20 | pdf | NEW | 89 | CRITICAL | INFORMATIONAL | What changed: Amendment. a. 1.2. Notwithstanding things done, purported to have been done, or omitted to be done under the prov... |
| 11 | 30 | mop | What's New | Electricity (Amendment) Rules, 2026 alongwith Explanatory Note | 2026-03-16 | pdf | NEW | 82 | CRITICAL | INFORMATIONAL | What changed: Amendment. Government hereby makes the following rules, further to amend the Electricity Rules, 2005 namely:— 1.... |
| 12 | 31 | mop | What's New | Directions to Imported Coal-Based generating company under Section 11 of the Electricity Act, 2003 | 2026-03-27 | pdf | NEW | 82 | CRITICAL | INFORMATIONAL | What changed: Tender Update. mentioned above, is given, the PPA holder shall not be entitled to get power from the ICB plant fo... |
| 13 | 32 | seci | Tenders | RfS for assured Peak Supply of 4800 MWh (1200 MW x 4 Hrs.) from ISTS-Connected RE Projects (SECI-FDRE-IX) | 2026-06-05 | pdf | NEW | 100 | CRITICAL | ACTIONABLE | What changed: Corrigendum. ww.seci.co.in) and submit their Bid complete in all respect as per terms & conditions of RfS Documen... |
| 14 | 33 | seci | Tenders | BoS Tender for Setting up of grid-connected 88 MW Ground mounted Solar PV plant at Chitradurga, Karnataka | 2026-05-08 | pdf | NEW | 100 | CRITICAL | ACTIONABLE | What changed: Addendum. UREMENT POLICY FOR MICRO AND SMALL ENTERPRISES (MSEs) [G] ANNEXURES: 1. ANNEXURE-I: PROCEDURE FOR ACTIO... |
| 15 | 34 | seci | Tenders | RfS for setting up of 12250 kW Grid-Connected Rooftop Solar PV Projects on JNV Buildings (Phase-II) under RESCO Mode through Te... | 2026-05-29 | pdf | NEW | 100 | CRITICAL | ACTIONABLE | What changed: Corrigendum. CI website (www.seci.co.in) and submit their Bid complete in all respect as per terms & conditions o... |
| 16 | 35 | seci | Tenders | RfS for Supply of 1000 MW Excess Power from RE Projects having Existing PPA (SECI-FDRE-VIII) | 2025-12-26 | pdf | NEW | 100 | CRITICAL | ACTIONABLE | What changed: Corrigendum. CI website (www.seci.co.in) and submit their Bid complete in all respect as per terms & conditions o... |
| 17 | 36 | seci | Tenders | RfS for setting up 5500 kW Grid-Connected Rooftop Solar PV Project under RESCO mode (RTSPV-Tranche-X) | 2026-05-21 | pdf | NEW | 100 | CRITICAL | ACTIONABLE | What changed: Corrigendum. ww.seci.co.in) and submit their Bid complete in all respect as per terms & conditions of RfS documen... |
| 18 | 37 | seci | Tenders | RfS for Supply of 1000 MW Round-the-Clock Thermal Mimic (RTC-TM) Power from ISTS-Connected RE Power Projects in India (SECI-RTC... | 2026-03-10 | pdf | NEW | 100 | CRITICAL | ACTIONABLE | What changed: Corrigendum. .seci.co.in) and submit their Bid complete in all respect as per terms & conditions of RfS document... |
| 19 | 38 | seci | Tenders | RfS for assured Peak Supply of 1500 MWh (500 MW x 3 Hrs.) under CfD Mechanism from ISTS-Connected RE Projects (SECI-CfD-I) | 2026-04-19 | pdf | NEW | 100 | CRITICAL | ACTIONABLE | What changed: Tender Submission Deadline shortened from 2026-09-24 to 2026-09-24. Previous: 2026-09-24. New: 2026-09-24. |
| 20 | 39 | seci | Tenders | RfS for 2000 MW ISTS-Connected Wind Power Projects in India (SECI-Tranche-XX) | 2026-04-21 | pdf | NEW | 100 | CRITICAL | ACTIONABLE | What changed: Corrigendum. seci.co.in) and submit their Bid complete in all respect as per terms & conditions of RfS Document o... |

## Rejected Events

| Doc ID | Source | Page | Title | Date | Reason | Freshness | Quality | Significance | Actionability |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 11 | cerc | Public Notice | Requested to file note of submissions | 2023-04-05 | HISTORICAL_DOCUMENT | HISTORICAL | 36 | MEDIUM | REFERENCE_ONLY |
| 12 | cerc | Public Notice | Commission to extend the implementation of Ancillary Services Regulations (Provisions pertaining to TRAS) from 01.05.2023 at th... | 2023-03-27 | HISTORICAL_DOCUMENT | HISTORICAL | 33 | MEDIUM | REFERENCE_ONLY |
| 13 | cerc | Public Notice | Refund of Amounts against submission of Bank Guarantees, as per Hon'ble Supreme Court's Orders dated 09.05.2022 and 17.05.2022... | 2022-07-04 | HISTORICAL_DOCUMENT | HISTORICAL | 46 | HIGH | REFERENCE_ONLY |
| 14 | cerc | Public Notice | Submission of details of the Assets pertaining to Generating and Transmission Companies through CERC SAUDAMINI e-Assets Module... | 2021-10-04 | HISTORICAL_DOCUMENT | HISTORICAL | 38 | HIGH | REFERENCE_ONLY |
| 15 | cerc | Public Notice | Public Notice dated 27.05.2021 regarding Payment of Annual fees | 2021-05-27 | HISTORICAL_DOCUMENT | HISTORICAL | 28 | LOW | REFERENCE_ONLY |
| 19 | cerc | Suo Motu Petitions / Staff Papers / Notices | 121/TL/2026 - Application under Section 14 & 15 of the Electricity Act, 2003 read with Central Electricity Regulatory Commissio... | 2026-05-19 | EXPIRED_OPPORTUNITY | CURRENT | 88 | CRITICAL | INFORMATIONAL |
| 20 | cerc | Suo Motu Petitions / Staff Papers / Notices | 131/TL/2026 - Petition under Sections 14, 15 and 79(1)(e) of Electricity Act, 2003, read with the Central Electricity Regulator... | 2026-05-16 | EXPIRED_OPPORTUNITY | CURRENT | 85 | CRITICAL | INFORMATIONAL |
| 21 | cerc | Suo Motu Petitions / Staff Papers / Notices | 133/TL/2026 - Application under Sections 14 & 15 of the Electricity Act, 2003 read with Central Electricity Regulatory Commissi... | 2026-05-13 | EXPIRED_OPPORTUNITY | CURRENT | 82 | HIGH | INFORMATIONAL |
| 22 | cerc | Suo Motu Petitions / Staff Papers / Notices | 27/TL/2026 - Application under Section-14, 15, 79(1)(e) of the Electricity Act, 2003 read with Central Electricity Regulatory C... | 2026-05-13 | EXPIRED_OPPORTUNITY | CURRENT | 85 | CRITICAL | INFORMATIONAL |
| 23 | cerc | Notice / Letter | Uploading of Monthly Information on the website of Trading Licensees-reg. | 2023-11-20 | HISTORICAL_DOCUMENT | HISTORICAL | 39 | MEDIUM | REFERENCE_ONLY |
| 24 | cerc | Notice / Letter | Explanation regarding introduction of G-TAM Daily T+1 Contracts - reg. | 2022-05-05 | HISTORICAL_DOCUMENT | HISTORICAL | 39 | HIGH | REFERENCE_ONLY |
| 25 | cerc | Notice / Letter | Explanation regarding modifications in the Delivery Timelines for the Anyday Contracts from T+2 to T+1 - reg. | 2022-05-05 | HISTORICAL_DOCUMENT | HISTORICAL | 39 | HIGH | REFERENCE_ONLY |
| 2 | mnre | Current Notices | Amendment to ‘Standard Operating Procedure (SOP) for Approved List of Models and Manufacturers – Wind (ALMM-Wind) and Approved... | 2025-12-01 | HISTORICAL_DOCUMENT | HISTORICAL | 39 | MEDIUM | REFERENCE_ONLY |
| 4 | mnre | Monthly Updates | Renewable Energy Policy and Regulatory update for April 2026 month (546 KB) | 2026-04-01 | EXPIRED_OPPORTUNITY | RECENT | 84 | CRITICAL | INFORMATIONAL |
| 5 | mnre | Monthly Updates | Renewable Energy Policy and Regulatory update for March 2026 month (546 KB) | 2026-03-01 | EXPIRED_OPPORTUNITY | RECENT | 84 | CRITICAL | INFORMATIONAL |
| 7 | mnre | Monthly Updates | Renewable Energy Policy and Regulatory update for January 2026 month (546 KB) | 2026-01-01 | EXPIRED_OPPORTUNITY | RECENT | 84 | CRITICAL | INFORMATIONAL |
| 8 | mnre | Monthly Updates | Renewable Energy Policy and Regulatory update for December 2025 month (546 KB) | 2025-12-01 | EXPIRED_OPPORTUNITY | CURRENT | 92 | CRITICAL | INFORMATIONAL |
| 9 | mnre | Monthly Updates | Renewable Energy Policy and Regulatory update for November2025 month (546 KB) | 2025-11-20 | HISTORICAL_DOCUMENT | HISTORICAL | 52 | CRITICAL | REFERENCE_ONLY |
| 10 | mnre | Monthly Updates | Renewable Energy Policy and Regulatory update for October 2025 month (546 KB) | 2025-10-01 | HISTORICAL_DOCUMENT | HISTORICAL | 52 | CRITICAL | REFERENCE_ONLY |

## Discovery Rejections

| Source | Page | Title | Primary URL | Classification | Reason | Text Chars | OCR Needed |
| --- | --- | --- | --- | --- | --- | --- | --- |
| cerc | Public Notice | Notice: Conducting of Hearings through Video Conferencing/Hybrid Mode | https://cercind.gov.in/2026/whatsnew/Notice190526.pdf | REGULATORY_DOCUMENT | INSUFFICIENT_CONTENT | 0 | true |
| cerc | Suo Motu Petitions / Staff Papers / Notices | 214/TD/2026 - Application under Section 14 of the Electricity Act, 2003 read with Central Electricity Regulatory Commission (Pr... | https://cercind.gov.in/SPN/214-TD-2026%20(IE-9.6.2026).pdf | ORDER | INSUFFICIENT_CONTENT | 0 | true |
| mnre | Current Notices | ALMM – No blanket extension of ALMM List-II beyond 01.06.2026 subject to Protection of Investments already made | https://cdnbbsr.s3waas.gov.in/s3716e1b8c6cd17b771da77391355749f3/uploads/2026/05/202605251665091021.pdf | REGULATORY_DOCUMENT | INSUFFICIENT_CONTENT | 0 | true |
| mnre | Current Notices | OM regarding extension in timeline of the Solar Park scheme | https://cdnbbsr.s3waas.gov.in/s3716e1b8c6cd17b771da77391355749f3/uploads/2025/09/2025091984030227.pdf | POLICY_UPDATE | INSUFFICIENT_CONTENT | 0 | true |
| mop | What's New | Extension of the Timeline for Submission of Comments on the Electricity (Amendment) Bill, 2025 | https://www.powermin.gov.in/static/uploads/2026/06/c91862e80a1459694dc0046d6543153c.pdf | CONSULTATION_DOCUMENT | INSUFFICIENT_CONTENT | 0 | true |
| mop | What's New | Extension of the Timeline for Submission of Comments and Suggestions on Draft National Electricity Policy, 2026 | https://www.powermin.gov.in/static/uploads/2026/06/58716fc6f0fbdc8ee72d2144e24ea5fe.pdf | CONSULTATION_DOCUMENT | INSUFFICIENT_CONTENT | 0 | true |

## Table Row Counts After Run

| Table | Rows |
| --- | --- |
| sources | 4 |
| source_pages | 7 |
| crawl_runs | 1 |
| discovery_audit | 45 |
| documents | 39 |
| document_versions | 39 |
| document_texts | 39 |
| events | 20 |
| event_intelligence_audit | 39 |
| summaries | 20 |
| digests | 1 |
| digest_events | 20 |
| document_families | 38 |
| document_family_assignments | 39 |
| document_version_registry | 39 |
| document_version_relationships | 0 |
| deadline_history | 391 |
| regulatory_change_audit | 59 |
| regulatory_graph_entities | 0 |
| regulatory_graph_document_entities | 0 |
| regulatory_graph_edges | 0 |
| regulatory_graph_extractions | 0 |
| regulatory_graph_stakeholders | 0 |
| regulatory_graph_obligations | 0 |
| regulatory_graph_deadlines | 0 |
| regulatory_graph_family_enrichment | 0 |
| notifications_log | 0 |
| chat_messages | 0 |
| user_event_state | 0 |
| profiles | 4 |
| subscriptions | 0 |

## Verdict

The Step 24 parser replacement is validated at the extraction layer. The curated pages now produce current primary documents instead of the stale failure artifacts called out in Step 23: no Electricity Act navigation PDF was selected as a current CERC SPN, no SECI Corporate Brochure was selected, and MoP amendment attachments now resolve to primary PDFs.

The run produced 39 stored documents and 20 accepted events from 45 discovered candidates. Remaining quality work is downstream of parser selection: some PDFs still fail content sufficiency/OCR checks, and event usefulness depends on the existing intelligence gate/summarization layer, which Step 24 intentionally did not change.
