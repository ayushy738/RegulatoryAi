# Step 18 Document Family & Version Registry

Generated at: 2026-06-21T20:44:51.258351+00:00

## What Was Implemented

- `document_families`: canonical family records for regulatory instruments.
- `document_family_assignments`: document-to-family assignment with confidence.
- `document_version_registry`: version lineage per family.
- `document_version_relationships`: explicit amendment/corrigendum/supersession links.
- `deadline_history`: normalized durable deadline rows.

## Backfill Summary

- Documents processed: 26
- Document families created in this run: 6
- Total document families now: 6
- Documents assigned to families: 6
- Documents not assigned: 20
- Registry versions now: 6
- Version relationships now: 0
- Deadline history rows now: 34
- Deadline rows discovered during assignment pass: 34
- Amendment/corrigendum/addendum signals discovered: 2

## Assignment Mix

- UNKNOWN_FAMILY: 20
- NEW_FAMILY: 6

## Quality Audit

- Documents: 26
- Families: 6
- Average versions per family: 1.00
- Families with multiple versions: 0
- Families with amendment chains: 2
- Families with deadline history: 4

## Assignment Details

| Document | Assignment | Confidence | Family | Evidence |
|---:|---|---:|---|---|
| 1 | UNKNOWN_FAMILY | 0.22 |  | No primary text and no strong family signal in title. |
| 2 | UNKNOWN_FAMILY | 0.22 |  | No primary text and no strong family signal in title. |
| 3 | NEW_FAMILY | 0.56 | Lab Policy, Standards and Quality Control | Lab Policy, Standards and Quality Control |
| 4 | UNKNOWN_FAMILY | 0.18 |  | Generic navigation/listing title without a resolvable instrument. |
| 5 | UNKNOWN_FAMILY | 0.18 |  | Generic navigation/listing title without a resolvable instrument. |
| 6 | UNKNOWN_FAMILY | 0.18 |  | Generic navigation/listing title without a resolvable instrument. |
| 7 | UNKNOWN_FAMILY | 0.18 |  | Generic navigation/listing title without a resolvable instrument. |
| 8 | UNKNOWN_FAMILY | 0.18 |  | Generic navigation/listing title without a resolvable instrument. |
| 9 | UNKNOWN_FAMILY | 0.18 |  | Generic navigation/listing title without a resolvable instrument. |
| 10 | UNKNOWN_FAMILY | 0.18 |  | Generic navigation/listing title without a resolvable instrument. |
| 11 | UNKNOWN_FAMILY | 0.22 |  | No primary text and no strong family signal in title. |
| 12 | UNKNOWN_FAMILY | 0.18 |  | Generic navigation/listing title without a resolvable instrument. |
| 13 | NEW_FAMILY | 0.58 | Renewable Purchase Obligation (RPO) and Energy Storage Obligation Trajectory till 2029-30 | Corrigendum to Renewable Purchase Obligation (RPO) and Energy Storage Obligation Trajectory till 2029-30 order dated 22n... |
| 14 | UNKNOWN_FAMILY | 0.22 |  | No primary text and no strong family signal in title. |
| 15 | UNKNOWN_FAMILY | 0.18 |  | Generic navigation/listing title without a resolvable instrument. |
| 24 | UNKNOWN_FAMILY | 0.18 |  | Generic navigation/listing title without a resolvable instrument. |
| 25 | UNKNOWN_FAMILY | 0.18 |  | Generic navigation/listing title without a resolvable instrument. |
| 26 | UNKNOWN_FAMILY | 0.18 |  | Generic navigation/listing title without a resolvable instrument. |
| 27 | NEW_FAMILY | 0.62 | Annexure ... Central Electricity Regulatory Commission Regulation of Power Supply Regulations | Annexure ... Central Electricity Regulatory Commission (Regulation of Power Supply) (First Amendment) Regulations |
| 28 | UNKNOWN_FAMILY | 0.18 |  | Generic navigation/listing title without a resolvable instrument. |
| 29 | UNKNOWN_FAMILY | 0.18 |  | Generic navigation/listing title without a resolvable instrument. |
| 30 | UNKNOWN_FAMILY | 0.22 |  | No primary text and no strong family signal in title. |
| 31 | NEW_FAMILY | 0.62 | Central Electricity Regulatory Commission Draft Central Electricity Regulatory Commission Deviation Settlement Mechanism and Related Matters Regulations | Central Electricity Regulatory Commission Draft Central Electricity Regulatory Commission (Deviation Settlement Mechanis... |
| 39 | NEW_FAMILY | 0.82 | RFP for Selection of Bidder as Transmission Service Provider | RFP for Selection of Bidder as Transmission Service Provider STANDARD SINGLE STAGE REQUEST FOR PROPOSAL DOCUMENT FOR SEL... |
| 40 | NEW_FAMILY | 0.82 | The Energy Conservation Act, 2001 | SEC. 1 THE GAZETTE OF INDIA EXTRAORDINARY 3 MINISTRY OF LAW, JUSTICE AND COMPANY AFFAIRS (Legislative Department) New De... |
| 41 | UNKNOWN_FAMILY | 0.16 |  | Index/catalog page detected, not a single regulatory instrument. |

## Examples

### Family with amendment chain

- Annexure ... Central Electricity Regulatory Commission Regulation of Power Supply Regulations (issuer: Central Electricity Regulatory Commission; versions: 1)
- Central Electricity Regulatory Commission Draft Central Electricity Regulatory Commission Deviation Settlement Mechanism and Related Matters Regulations (issuer: Central Electricity Regulatory Commission; versions: 1)

### Family with multiple versions

- None found in the current corpus.

### Family with deadline history

- RFP for Selection of Bidder as Transmission Service Provider (issuer: Ministry of Power; deadlines: 30; types: COMPLIANCE_DEADLINE, PUBLICATION_DATE, TENDER_SUBMISSION_DEADLINE, UNKNOWN_DATE)
- The Energy Conservation Act, 2001 (issuer: Maharashtra Electricity Regulatory Commission; deadlines: 2; types: PUBLICATION_DATE, UNKNOWN_DATE)
- Renewable Purchase Obligation (RPO) and Energy Storage Obligation Trajectory till 2029-30 (issuer: Ministry of Power; deadlines: 1; types: PUBLICATION_DATE)
- Central Electricity Regulatory Commission Draft Central Electricity Regulatory Commission Deviation Settlement Mechanism and Related Matters Regulations (issuer: Central Electricity Regulatory Commission; deadlines: 1; types: CONSULTATION_DEADLINE)

### Family that could not be resolved

- Notification (evidence: Index/catalog page detected, not a single regulatory instrument.)
- Solar Thermal (evidence: Generic navigation/listing title without a resolvable instrument.)
- Solar (evidence: Generic navigation/listing title without a resolvable instrument.)
- Wind (evidence: Generic navigation/listing title without a resolvable instrument.)
- Notices (evidence: Generic navigation/listing title without a resolvable instrument.)
- Recruitments (evidence: Generic navigation/listing title without a resolvable instrument.)
- Orders | Government of India | Ministry of Power (evidence: Generic navigation/listing title without a resolvable instrument.)
- Ministry Of Power: Home (evidence: Generic navigation/listing title without a resolvable instrument.)


## Readiness Assessment

Choice: **PARTIALLY**.

The registry now gives the system durable places to store family identity, version lineage, amendment relationships, supersession relationships, and normalized deadline history. That is the missing foundation Step 17 identified.

However, the current corpus still has very little usable lineage: most stored documents are old crawler artifacts or singletons, and only a small number have primary extracted text. Genuine version-aware change detection becomes possible for future crawls once the same family receives multiple clean primary-document versions.