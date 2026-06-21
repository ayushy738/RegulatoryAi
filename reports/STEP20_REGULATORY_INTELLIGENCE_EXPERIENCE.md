# Step 20 Regulatory Intelligence Experience Layer

Generated at: 2026-06-21T22:02:09.028043+00:00

## What Was Implemented

- `GET /intelligence/deadlines`: active/historical/all graph deadline API with issuer, deadline-type, and stakeholder filters.
- `GET /intelligence/obligations`: obligations grouped by stakeholder.
- `GET /intelligence/stakeholders`: stakeholder intelligence cards for the supported power-sector stakeholder set.
- `GET /intelligence/stakeholders/{stakeholder}`: one stakeholder intelligence view.
- `GET /intelligence/readiness`: readiness snapshot over deadlines, obligations, regulatory impacts, and consultation tracking.
- Frontend route `/intelligence`: deadlines center, obligations center, stakeholder intelligence, and readiness notes.

## Current Data Snapshot

- Active future deadlines: 0
- Extracted graph deadline/date rows: 25
- Stakeholder obligation groups: 7
- Obligation rows shown in groups: 29
- Stakeholder intelligence panels: 6
- Consultation tracking items: 0
- Readiness status: ready

## Active Deadlines

- None. The active API is working, but the current graph has no future-dated deadline rows.

## Extracted Deadline Examples

- PUBLICATION_DATE -> 2001-09-29: The Energy Conservation Act, 2001
- UNKNOWN_DATE -> 2001-10-19: The Energy Conservation Act, 2001
- PUBLICATION_DATE -> 2017-01-13: RFP for Selection of Bidder as Transmission Service Provider
- TENDER_SUBMISSION_DEADLINE -> 2018-03-15: RFP for Selection of Bidder as Transmission Service Provider
- PUBLICATION_DATE -> 2018-05-11: RFP for Selection of Bidder as Transmission Service Provider
- PUBLICATION_DATE -> 2019-06-18: RFP for Selection of Bidder as Transmission Service Provider
- PUBLICATION_DATE -> 2020-07-23: RFP for Selection of Bidder as Transmission Service Provider
- TENDER_SUBMISSION_DEADLINE -> 2020-07-24: RFP for Selection of Bidder as Transmission Service Provider

## Stakeholder Obligations

- Renewable Developers: 12 obligation(s); example: (1) The general superintendence, direction and management of the affairs of the Bureau Management of shall vest in the Governing C...
- DISCOMs: 6 obligation(s); example: In the first round the Initial Offer of the responsive bids would be opened and Quoted Transmission Charges of Initial Offer shall...
- Bidders: 5 obligation(s); example: In addition to the online submission, the Bidder with lowest Final Offer will be required to submit original hard copies of Annexu...
- TSP: 3 obligation(s); example: Ensure that design, construction and testing of all equipment, facilities, components and systems of the Project shall be in accor...
- Bidder: 1 obligation(s); example: Commence Transmission Service in accordance with the provisions of the Transmission Service Agreement.
- Transmission Licensees: 1 obligation(s); example: The Transmission Service Provider shall be selected through tariff based competitive bidding process for the Project based on meet...
- Transmission Service Provider (TSP): 1 obligation(s); example: Establish Inter-State Transmission System for evacuation of power from REZ in Rajasthan (20 GW) under Phase-III Part I on build, o...

## Regulatory Impacts

- Solar Developers: 1 regulations, 12 obligations, 2 deadlines, 0 tenders.
- Wind Developers: 1 regulations, 12 obligations, 2 deadlines, 0 tenders.
- DISCOMs: 0 regulations, 17 obligations, 23 deadlines, 1 tenders.
- Transmission Licensees: 0 regulations, 17 obligations, 23 deadlines, 1 tenders.
- Power Exchanges: 0 regulations, 0 obligations, 0 deadlines, 0 tenders.
- Generators: 0 regulations, 0 obligations, 0 deadlines, 0 tenders.

## Consultation Tracking

- None. No accepted primary consultation documents exist in the current graph.

## Can A User Answer The Core Questions?

- What do I need to do? **Partially yes.** The obligations center exposes actionable graph obligations, especially around transmission/tender documents.
- What deadlines matter? **Partially.** The deadline center exposes graph dates, but the current corpus has no future active deadlines.
- What affects my organization? **Partially yes.** Stakeholder panels summarize regulations, obligations, deadlines, and tenders by stakeholder, but coverage depends on more accepted primary documents.

## Readiness Notes

- Deadlines are future-dated only in the active API.
- Stakeholder views also surface historical extracted deadlines for auditability.
- The current graph has no future-dated active deadline rows.
- The current graph has no accepted primary consultation documents.

## Assessment

Choice: **PARTIALLY READY**.

The platform now has a real user-facing intelligence layer over the knowledge graph. It is useful for obligations and stakeholder impact scanning. It is not yet a complete regulatory intelligence product because active consultations and future deadlines are absent from the current graph data.