# Step 16 Regulatory Change Detection Backtest

Generated at: 2026-06-21T20:10:49.590880+00:00

## Engine Logic

- Change types: NEW_DOCUMENT, UPDATED_DOCUMENT, AMENDMENT, CORRIGENDUM, ADDENDUM, DEADLINE_CHANGE, TENDER_UPDATE, CONSULTATION_UPDATE, POLICY_UPDATE, WITHDRAWAL, REISSUED_DOCUMENT, NO_MATERIAL_CHANGE.
- Version comparison uses same-document prior versions first, then related-document title similarity within the same source or issuer.
- Material change detection ignores exact content-hash matches and near-identical text unless deadline, amendment, tender, consultation, tariff, compliance, withdrawal, or supersession signals are present.
- Deadline intelligence compares typed deadlines and classifies ADDED, REMOVED, EXTENDED, or SHORTENED changes.
- Event generation requires primary text, a material change, and Step 15 intelligence approval.

## Metrics

- Total documents analyzed: 26
- Total version comparisons: 0
- Documents with no material change: 11
- Documents classified as historical/archival: 21
- Meaningful changes detected before quality gates: 15
- Meaningful change events surviving all gates: 0
- False positives identified by later gates: 15
- Event survival rate after change detection: 0.0%

## Change Type Mix

- NO_MATERIAL_CHANGE: 11
- NEW_DOCUMENT: 4
- CORRIGENDUM: 4
- POLICY_UPDATE: 3
- AMENDMENT: 3
- TENDER_UPDATE: 1

## Freshness Mix

- HISTORICAL: 20
- CURRENT: 5
- ARCHIVAL: 1

## Meaningful Events That Would Be Generated

- None. Current stored documents do not survive the Step 15 intelligence gate.

## Requested Examples

### NEW_DOCUMENT

- Document 11: circular | Government of India | Ministry of Power
  - Issuer: Ministry of Power
  - Change type: NEW_DOCUMENT
  - Material: True
  - Confidence: 0.76
  - Prior reference: none
  - Previous state: No prior version or related document found.
  - New state: New primary document classified as CIRCULAR.
  - Why it matters: A new primary regulatory document was detected and passed material-change checks.
  - Affected: unknown
  - Deadlines: none
  - Evidence: भारत सरकार, विद्युत मंत्रालय की आधिकारिक वेबसाइट
  - Would generate event: False

- Document 26: Cercind
  - Issuer: Central Electricity Regulatory Commission
  - Change type: NEW_DOCUMENT
  - Material: True
  - Confidence: 0.76
  - Prior reference: none
  - Previous state: No prior version or related document found.
  - New state: New primary document classified as NOTIFICATION.
  - Why it matters: A new primary regulatory document was detected and passed material-change checks.
  - Affected: unknown
  - Deadlines: none
  - Evidence: notification of these regulations, as (i) GNA within the region and (ii)
  - Would generate event: False

### AMENDMENT

- Document 27: Central Electricity Regulatory Commission
  - Issuer: Central Electricity Regulatory Commission
  - Change type: AMENDMENT
  - Material: True
  - Confidence: 0.84
  - Prior reference: none
  - Previous state: 
  - New state: rojects based on renewable sources to inter-state transmission system&quot;. 1. Order 2. Annexure ... Central Electricity Regulatory Commission (Regulation of Power Supply) (First Amendment) Regulations, 2021.
  - Why it matters: This changes or clarifies an existing regulatory instrument and may affect compliance interpretation.
  - Affected: renewable developers
  - Deadlines: none
  - Evidence: rojects based on renewable sources to inter-state transmission system&quot;. 1. Order 2. Annexure ... Central Electricity Regulatory Commission (Regulation of Power Supply) (First Amendment) Regulations, 2021.
  - Would generate event: False

- Document 31: Central Electricity Regulatory Commission
  - Issuer: Central Electricity Regulatory Commission
  - Change type: AMENDMENT
  - Material: True
  - Confidence: 0.84
  - Prior reference: none
  - Previous state: 
  - New state: Central Electricity Regulatory Commission Draft Central Electricity Regulatory Commission (Deviation Settlement Mechanism and Related Matters) (Third Amendment) Regulations, 2026 (Last date of submission of comments and suggestions:- 26.06.2026) Read More .. Draft Central Electricity Regulatory Commission (Power Market) (Second Amendment) Regulations, 2026- reg.
  - Why it matters: This changes or clarifies an existing regulatory instrument and may affect compliance interpretation.
  - Affected: unknown
  - Deadlines: none
  - Evidence: Central Electricity Regulatory Commission Draft Central Electricity Regulatory Commission (Deviation Settlement Mechanism and Related Matters) (Third Amendment) Regulations, 2026 (Last date of submission of comments and suggestions:- 26.06.2026) Read More .. Draft Central Electricity Regulatory Commission (Power Market) (Second Amendment) Regulations, 2026- reg.
  - Would generate event: False

### DEADLINE_CHANGE

- No DEADLINE_CHANGE example exists in the current stored corpus.

### CORRIGENDUM

- Document 13: Corrigendum to Renewable Purchase Obligation (RPO) and Energy Storage Obligation Trajectory till 2029-30 order dated 22nd July 2022 | Government of India | Ministry of Power
  - Issuer: Ministry of Power
  - Change type: CORRIGENDUM
  - Material: True
  - Confidence: 0.86
  - Prior reference: none
  - Previous state: 
  - New state: pdf "View STQC Certification") This website belongs to Ministry of Power Govt. of India, Shram Shakti Bhawan, Rafi Marg, New Delhi-1 Hosted by [National Informatics Centre (NIC)](https://www.nic.in/) Last Updated on: 20 May 2026
  - Why it matters: This changes or clarifies an existing regulatory instrument and may affect compliance interpretation.
  - Affected: unknown
  - Deadlines: none
  - Evidence: pdf "View STQC Certification") This website belongs to Ministry of Power Govt. of India, Shram Shakti Bhawan, Rafi Marg, New Delhi-1 Hosted by [National Informatics Centre (NIC)](https://www.nic.in/) Last Updated on: 20 May 2026
  - Would generate event: False

- Document 24: Central Electricity Regulatory Commission
  - Issuer: Central Electricity Regulatory Commission
  - Change type: CORRIGENDUM
  - Material: True
  - Confidence: 0.86
  - Prior reference: none
  - Previous state: 
  - New state: ss to any person for the result of any action taken on the basis of this information. However, CERC shall be obliged if errors/omissions are brought to its notice for carrying out corrections in the next update. CERC does not have any account on any Social Media Platform **Best Viewed in Chrome. Best Resolution to view 1280\*768 px**
  - Why it matters: This changes or clarifies an existing regulatory instrument and may affect compliance interpretation.
  - Affected: unknown
  - Deadlines: none
  - Evidence: ss to any person for the result of any action taken on the basis of this information. However, CERC shall be obliged if errors/omissions are brought to its notice for carrying out corrections in the next update. CERC does not have any account on any Social Media Platform **Best Viewed in Chrome. Best Resolution to view 1280\*768 px**
  - Would generate event: False

### REISSUED_DOCUMENT

- No REISSUED_DOCUMENT example exists in the current stored corpus.

### NO_MATERIAL_CHANGE

- Document 1: नवीन एवं नवीकरणीय ऊर्जा मंत्रालय MINISTRY OF NEW AND RENEWABLE ENERGY
  - Issuer: Ministry of New & Renewable Energy
  - Change type: NO_MATERIAL_CHANGE
  - Material: False
  - Confidence: 0.55
  - Prior reference: none
  - Previous state: No prior version or related document found.
  - New state: Document does not contain enough material-change evidence.
  - Why it matters: This document is classified as NAVIGATION_PAGE and should be reviewed for material impact.
  - Affected: renewable developers
  - Deadlines: none
  - Evidence: No prior version and no material regulatory-change signal detected.
  - Would generate event: False

- Document 2: Association of Renewable Energy Agencies of States (AREAS)
  - Issuer: Ministry of New & Renewable Energy
  - Change type: NO_MATERIAL_CHANGE
  - Material: False
  - Confidence: 0.55
  - Prior reference: none
  - Previous state: No prior version or related document found.
  - New state: Document does not contain enough material-change evidence.
  - Why it matters: This document is classified as NAVIGATION_PAGE and should be reviewed for material impact.
  - Affected: renewable developers
  - Deadlines: none
  - Evidence: No prior version and no material regulatory-change signal detected.
  - Would generate event: False


## False Positives Blocked

- Document 3: Lab Policy, Standards and Quality Control (POLICY_UPDATE, freshness HISTORICAL, primary_text=False)
- Document 7: Notices (TENDER_UPDATE, freshness HISTORICAL, primary_text=False)
- Document 11: circular | Government of India | Ministry of Power (NEW_DOCUMENT, freshness HISTORICAL, primary_text=False)
- Document 12: Important Orders/ Guidelines/ Notifications/ Reports | Government of India | Ministry of Power (POLICY_UPDATE, freshness CURRENT, primary_text=False)
- Document 13: Corrigendum to Renewable Purchase Obligation (RPO) and Energy Storage Obligation Trajectory till 2029-30 order dated 22nd July 2022 | Government of India | Ministry of Power (CORRIGENDUM, freshness CURRENT, primary_text=False)
- Document 24: Central Electricity Regulatory Commission (CORRIGENDUM, freshness HISTORICAL, primary_text=False)
- Document 26: Cercind (NEW_DOCUMENT, freshness HISTORICAL, primary_text=False)
- Document 27: Central Electricity Regulatory Commission (AMENDMENT, freshness HISTORICAL, primary_text=False)
- Document 28:  :::  Central Electricity Regulatory Commission ::: (CORRIGENDUM, freshness HISTORICAL, primary_text=False)
- Document 29:  :::  Central Electricity Regulatory Commission ::: (CORRIGENDUM, freshness HISTORICAL, primary_text=False)
- Document 30: 1 Central Electricity Regulatory Commission (NEW_DOCUMENT, freshness HISTORICAL, primary_text=False)
- Document 31: Central Electricity Regulatory Commission (AMENDMENT, freshness CURRENT, primary_text=False)