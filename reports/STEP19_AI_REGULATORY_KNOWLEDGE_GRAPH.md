# Step 19 AI Regulatory Knowledge Graph & Family Resolution

Generated at: 2026-06-21T21:21:24.596215+00:00

## Knowledge Graph Schema

- `regulatory_graph_entities`: Document, Regulation, Notification, Consultation, Tender, Stakeholder, Obligation, Deadline, Issuer, and related nodes.
- `regulatory_graph_document_entities`: document-to-entity role links.
- `regulatory_graph_edges`: AMENDS, SUPERSEDES, REFERENCES, IMPLEMENTS, REPEALS, EXTENDS, AFFECTS, HAS_DEADLINE, HAS_OBLIGATION, ISSUED_BY, and BELONGS_TO_FAMILY edges.
- `regulatory_graph_extractions`: extraction audit per document with provider, model, status, JSON payload, and errors.
- `regulatory_graph_stakeholders`: normalized affected-entity rows.
- `regulatory_graph_obligations`: actionable obligation rows.
- `regulatory_graph_deadlines`: graph-level deadline rows.
- `regulatory_graph_family_enrichment`: before/after family-resolution audit.

## Extraction Architecture

1. Load accepted primary documents with stored extracted text.
2. Run AI extraction with a strict regulatory graph JSON schema.
3. Merge AI output with deterministic grounded extraction for dates, stakeholders, obligations, and relationship hints.
4. Persist graph entities and edges.
5. Enrich the Step 18 family registry when AI produces a high-confidence family resolution.
6. Produce an auditable report showing counts, examples, and readiness.

## Backfill Summary

- AI requested: yes
- Primary documents processed: 2
- AI successful extractions: 2
- Heuristic/fallback extractions: 0
- Extraction status mix: AI=2
- Extraction errors: 0

## Entity Counts

| entity_type | Count |
|---|---:|
| OBLIGATION | 29 |
| DEADLINE | 25 |
| STAKEHOLDER | 14 |
| ACT | 10 |
| DOCUMENT | 2 |
| ISSUER | 2 |
| REGULATION | 2 |

## Relationship Counts

| relationship_type | Count |
|---|---:|
| HAS_OBLIGATION | 29 |
| HAS_DEADLINE | 25 |
| AFFECTS | 14 |
| REFERENCES | 9 |
| BELONGS_TO_FAMILY | 2 |
| ISSUED_BY | 2 |
| IMPLEMENTS | 1 |

## Family Enrichment Results

- Document families before AI: 6
- Document families after AI: 6
- Assigned documents before AI: 6
- Assigned documents after AI: 6
- Unassigned documents before AI: 20
- Unassigned documents after AI: 20
- Family enrichments applied: 0
- Documents improved in this run: 0

### Family Enrichment Examples

- Document 39 (recorded, confidence 0.80): RFP for Selection of Bidder as Transmission Service Provider -> Electricity Act, 2003
- Document 40 (recorded, confidence 0.70): The Energy Conservation Act, 2001 -> Energy Conservation Act, 2001

## Amendment Chain Results

- Annexure ... Central Electricity Regulatory Commission Regulation of Power Supply Regulations | version=First Amendment | amendment=1 | parent=not linked
- Central Electricity Regulatory Commission Draft Central Electricity Regulatory Commission Deviation Settlement Mechanism... | version=Third Amendment | amendment=3 | parent=not linked

## Relationship Examples

- REFERENCES: RFP for Selection of Bidder as Transmission Service Provider -> Central Electricity Regulatory Commission (Sharing of Inter-State Transmission Charges and Losses) Regulations (confidence 0.80; evidence: The Transmission Charges shall be payable by the Designated ISTS Customers in Indian Rupees through the CTU as per Central Electricity Regulatory Commission (Sh...)
- IMPLEMENTS: The Energy Conservation Act, 2001 -> The Energy Conservation Act, 2001 (confidence 0.64; evidence: (j) formulate and facilitate implementation of pilot projects and demonstration projects for promotion of efficient use of energy and its conservation;)
- REFERENCES: RFP for Selection of Bidder as Transmission Service Provider -> Electricity Act, 2003 (confidence 0.62; evidence: Electricity Act, 2003)
- REFERENCES: The Energy Conservation Act, 2001 -> This Act may be called the Energy Conservation Act, 2001 (confidence 0.62; evidence: This Act may be called the Energy Conservation Act, 2001)
- REFERENCES: The Energy Conservation Act, 2001 -> Societies Registration Act, 1860 (confidence 0.62; evidence: Societies Registration Act, 1860)
- REFERENCES: The Energy Conservation Act, 2001 -> Electricity Regulatory Commissions Act, 1998 (confidence 0.62; evidence: Electricity Regulatory Commissions Act, 1998)
- REFERENCES: The Energy Conservation Act, 2001 -> Electricity Act, 1910 (confidence 0.62; evidence: Electricity Act, 1910)
- REFERENCES: The Energy Conservation Act, 2001 -> Regulatory Commissions Act, 1998 (confidence 0.62; evidence: Regulatory Commissions Act, 1998)
- REFERENCES: The Energy Conservation Act, 2001 -> Institute registered under the Karnataka Societies Karnataka Act Act, 1960 (confidence 0.62; evidence: Institute registered under the Karnataka Societies Karnataka Act Act, 1960)
- REFERENCES: The Energy Conservation Act, 2001 -> Not withstanding anything contained in the Industrial Disputes Act, 1947 (confidence 0.62; evidence: Not withstanding anything contained in the Industrial Disputes Act, 1947)

## Stakeholder Extraction Results

- Ministry of Power, Government of India: 1 document(s), confidence 1.00; evidence: The Ministry of Power, Government of India, vide its Notifcation No. 15/3/2018-Trans- Pt(1) dated 13.01.2023 has appointed REC Power Development and Consultancy...
- REC Power Development and Consultancy Limited: 1 document(s), confidence 1.00; evidence: RFP for Selection of Bidder as Transmission Service Provider REC Power Development and Consultancy Limited (formerly REC Power Distribution Company Limited) (A...
- Bidder: 1 document(s), confidence 0.90; evidence: REC Power Development and Consultancy Limited 2 RFP for Selection of Bidder as Transmission Service Provider REQUEST FOR PROPOSAL NOTIFICATION REC Power Develop...
- Bureau of Energy Efficiency: 1 document(s), confidence 0.90; evidence: Bureau means the Bureau of Energy Efficiency established under subsection (l) of section 3
- Central Government: 1 document(s), confidence 0.90; evidence: It shall come into force on such dates as the Central Government may, by notification in the Official Gazette, appoint
- Parliament: 1 document(s), confidence 0.90; evidence: BE it enacted by Parliament in the Fifty second Year of the Republic of India as follows:
- Rajasthan Part I Power Transmission Limited: 1 document(s), confidence 0.90; evidence: The objective of the bidding process is to select a Successful Bidder pursuant to this RFP, who shall acquire one hundred percent (100%) of the equity shares of...
- Central Transmission Utility (CTU): 1 document(s), confidence 0.80; evidence: The Transmission Charges shall be payable by the Designated ISTS Customers in Indian Rupees through the CTU as per Central Electricity Regulatory Commission (Sh...
- Designated ISTS Customers: 1 document(s), confidence 0.80; evidence: The Transmission Charges shall be payable by the Designated ISTS Customers in Indian Rupees through the CTU as per Central Electricity Regulatory Commission (Sh...
- Bidders: 1 document(s), confidence 0.74; evidence: RFP for Selection of Bidder as Transmission Service Provider RFP for Selection of Bidder as Transmission Service Provider STANDARD SINGLE STAGE REQUEST FOR PROP...
- Consumers: 1 document(s), confidence 0.74; evidence: (g) “designated consumer” means any consumer specified under clause (e) of section 14;
- DISCOMs: 1 document(s), confidence 0.74; evidence: RFP for Selection of Bidder as Transmission Service Provider RFP for Selection of Bidder as Transmission Service Provider STANDARD SINGLE STAGE REQUEST FOR PROP...

## Obligation Extraction Results

- Document 39: Establish Inter-State Transmission System for evacuation of power from REZ in Rajasthan (20 GW) under Phase-III Part I on build, own, operate & transfer basis and provide transmiss... (Transmission Service Provider (TSP); no deadline; confidence 1.00)
- Document 39: Ensure that design, construction and testing of all equipment, facilities, components and systems of the Project shall be in accordance with the provisions of the Transmission Serv... (TSP; no deadline; confidence 1.00)
- Document 39: Obtain the Transmission License from the Commission. (TSP; no deadline; confidence 1.00)
- Document 39: Commence Transmission Service in accordance with the provisions of the Transmission Service Agreement. (Bidder; no deadline; confidence 1.00)
- Document 39: Transfer all project assets along with substation land, right of way and clearances to CTU or its successors or an agency as decided by the Central Government after 35 years from C... (TSP; no deadline; confidence 0.90)
- Document 39: The TSP shall ensure that design, construction and testing of all equipment, facilities, components and systems of the Project shall be in accordance with the provisions of the Tra... (DISCOMs; 2023-07-11; confidence 0.66)
- Document 39: The TSP shall obtain the Transmission License from the Commission. (DISCOMs; 2023-07-11; confidence 0.66)
- Document 39: The Transmission Service Provider shall be selected through tariff based competitive bidding process for the Project based on meeting stipulated Qualification Requirements prescrib... (Transmission Licensees; 2023-07-11; confidence 0.66)
- Document 39: The selection of the TSP shall be subject to it obtaining Transmission License from the Commission, which, after expiry, may be further extended by such period as deemed appropriat... (DISCOMs; 2023-07-11; confidence 0.66)
- Document 39: The entire bidding process shall be conducted on electronic platform created by MSTC Limited. (Bidders; 2023-07-11; confidence 0.66)
- Document 39: The Bid shall be a single stage two envelope bid comprising the Technical Bid and the Financial Bid. (DISCOMs; 2023-07-11; confidence 0.66)
- Document 39: The Bidders shall submit the Bid online through the electronic bidding platform. (Bidders; 2023-07-11; confidence 0.66)

## Deadline Intelligence Results

- Document 40: PUBLICATION_DATE -> 2001-09-29 (confidence 0.68; evidence: er, 2001, and is hereby published for general information:-- THE ENERGY CONSERVATION ACT, 2001 No 52 2001 OF [29th September 2001] An Act to provide f...)
- Document 40: UNKNOWN_DATE -> 2001-10-19 (confidence 0.35; evidence: 15. Commercial buildings or establishments; SUBHASH C.JAIN, Secy. to the Govt. of India. MGIP(PLU)MRND—2995GI—19-10-2001)
- Document 39: PUBLICATION_DATE -> 2017-01-13 (confidence 0.68; evidence: re sector” shall mean such sectors notified by Department of Economic Affairs in its Gazette Notification no. 13/1/2017-INF dated 14th November, 2017...)
- Document 39: TENDER_SUBMISSION_DEADLINE -> 2018-03-15 (confidence 0.84; evidence: x, 7, Lodhi Road, New Delhi – 110 003 1. The Ministry of Power, Government of India, vide its Notifcation No. 15/3/2018-Trans- Pt(1) dated 13.01.2023...)
- Document 39: PUBLICATION_DATE -> 2018-05-11 (confidence 0.68; evidence: isions of Public Procurement (Preference to Make in India) orders issued by Ministry of Power vide orders No. 11/5/2018 - Coord. dated 28.07.2020 for...)
- Document 39: PUBLICATION_DATE -> 2019-06-18 (confidence 0.68; evidence: Besides, Department of Expenditure, Ministry of Finance vide Order (Public Procurement No 1) bearing File No. 6/18/2019-PPD dated 23.07.2020, Order (P...)
- Document 39: PUBLICATION_DATE -> 2020-07-23 (confidence 0.68; evidence: of Expenditure, Ministry of Finance vide Order (Public Procurement No 1) bearing File No. 6/18/2019-PPD dated 23.07.2020, Order (Public Procurement No...)
- Document 39: TENDER_SUBMISSION_DEADLINE -> 2020-07-24 (confidence 0.84; evidence: No. 6/18/2019-PPD dated 23.07.2020 and Order (Public Procurement No. 3) bearing File No. 6/18/2019-PPD, dated 24.07.2020, as amended from time to time...)
- Document 39: PUBLICATION_DATE -> 2020-07-28 (confidence 0.68; evidence: ent (Preference to Make in India) orders issued by Ministry of Power vide orders No. 11/5/2018 - Coord. dated 28.07.2020 for transmission sector, as a...)
- Document 39: UNKNOWN_DATE -> 2021-02-19 (confidence 0.35; evidence: icated by SECI, various transmission alternatives were evolved and deliberated in 3rd NRPC-TP meeting held on 19.02.2021. Based on deliberations in ab...)
- Document 39: UNKNOWN_DATE -> 2021-09-27 (confidence 0.35; evidence: asthan (20 GW) under Phase III was also agreed in 49th Northern Region Power Committee (NRPC) meeting held on 27.09.2021 & 9th National Committee on T...)
- Document 39: PUBLICATION_DATE -> 2022-09-28 (confidence 0.68; evidence: gion Power Committee (NRPC) meeting held on 27.09.2021 & 9th National Committee on Transmission (NCT) held on 28.09.22. Subsequently, Ministry of Powe...)

## Example Graph Outputs

- Graph edge: DOCUMENT --REFERENCES--> Central Electricity Regulatory Commission (Sharing of Inter-State Transmission Charges and Losses) R...
- Stakeholder node: Ministry of Power, Government of India
- Obligation node: Establish Inter-State Transmission System for evacuation of power from REZ in Rajasthan (20 GW) under Phase-III Part I on build, own, operat...

## New User Capabilities

- What amendments affect solar developers? NO
- Show all active consultations: PARTIAL
- Show all obligations for transmission licensees: YES
- Which regulations changed this month? PARTIAL - graph relationships exist, but true month-over-month version comparison still needs repeated clean versions.
- Show amendment history of DSM Regulations: PARTIAL - amendment labels exist, but parent version links are still sparse.
- What deadlines exist this quarter? PARTIAL

## Readiness Assessment

Choice: **PARTIALLY**.

The system now has an AI-assisted regulatory understanding layer and can persist entities, relationships, stakeholders, obligations, deadlines, and family-enrichment evidence. It is still partial because the current corpus does not contain enough clean repeated versions to prove complete amendment lineage.