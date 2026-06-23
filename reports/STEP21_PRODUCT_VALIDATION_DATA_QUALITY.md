# Step 21 Product Validation & Data Quality Audit

Generated at: 2026-06-22T08:29:36.770237+00:00

## Run Scope

- Sources: Ministry of Power, CERC, MNRE, SECI, MERC.
- SECI and MERC were run as ad-hoc validation sources because they are not currently configured in the product source table.
- No UI, API, crawler, or AI-layer features were added for this audit.

## Platform Growth During Audit

- documents: 26 -> 26 (+0)
- events: 26 -> 26 (+0)
- families: 6 -> 6 (+0)
- deadline_history: 34 -> 34 (+0)
- graph_entities: 84 -> 129 (+45)
- graph_edges: 82 -> 127 (+45)
- graph_deadlines: 25 -> 26 (+1)
- graph_obligations: 29 -> 33 (+4)
- graph_stakeholders: 14 -> 15 (+1)

## Source Metrics

| Source | Candidates | Accepted | Rejected | Events | Families | Deadlines | Consultations | Obligations | Stakeholders | Graph growth | ROI |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| mop | 8 | 1 | 7 | 0 | 1 | 24 | 0 | 21 | 10 | 90 | 53.7 |
| cerc | 8 | 2 | 6 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 2.5 |
| mnre | 8 | 0 | 8 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | -2.0 |
| seci | 8 | 1 | 7 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0.2 |
| merc | 8 | 0 | 8 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | -5.0 |

## Source Quality

### Ministry of Power (`mop`)

- Source quality: **Mixed - some useful documents but noisy discovery**.
- Intelligence yield: **High**.
- Stakeholder relevance: **High**.
- Maintenance cost: **Medium**.
- Rejection reasons: NO_PRIMARY_DOCUMENT=3, LISTING_PAGE_DETECTED=2, INSUFFICIENT_CONTENT=1, NAVIGATION_PAGE_DETECTED=1
- Candidate classifications: NAVIGATION_PAGE=3, LISTING_PAGE=2, CIRCULAR=1, AMENDMENT=1, TENDER_DOCUMENT=1
- Sample titles: Orders | Government of India | Ministry of Power; Important Orders/ Guidelines/ Notifications/ Reports | Government of India | Ministry of Power; circular | Government of India | Ministry of Power; Corrigendum to Renewable Purchase Obligati...

### Central Electricity Regulatory Commission (`cerc`)

- Source quality: **Mixed - some useful documents but noisy discovery**.
- Intelligence yield: **None**.
- Stakeholder relevance: **None**.
- Maintenance cost: **Medium**.
- Rejection reasons: LISTING_PAGE_DETECTED=5, HOMEPAGE_DETECTED=1
- Candidate classifications: LISTING_PAGE=5, HOMEPAGE=1, AMENDMENT=1, NOTIFICATION=1
- Sample titles: Central Electricity Regulatory Commission; Central Electricity Regulatory Commission; Central Electricity Regulatory Commission;  :::  Central Electricity Regulatory Commission :::;  :::  Central Electricity Regulatory Commission :::

### Ministry of New & Renewable Energy (`mnre`)

- Source quality: **Poor - discovery is not reaching primary documents**.
- Intelligence yield: **None**.
- Stakeholder relevance: **None**.
- Maintenance cost: **Medium**.
- Rejection reasons: CATEGORY_PAGE_DETECTED=3, NO_PRIMARY_DOCUMENT=2, LISTING_PAGE_DETECTED=2, INSUFFICIENT_CONTENT=1
- Candidate classifications: CATEGORY_PAGE=3, NAVIGATION_PAGE=2, LISTING_PAGE=2, POLICY_UPDATE=1
- Sample titles: नवीन एवं नवीकरणीय ऊर्जा मंत्रालय MINISTRY OF NEW AND RENEWABLE ENERGY; Association of Renewable Energy Agencies of States (AREAS); Lab Policy, Standards and Quality Control; Solar Thermal; Solar

### Solar Energy Corporation of India (`seci`)

- Source quality: **Mixed - some useful documents but noisy discovery**.
- Intelligence yield: **None**.
- Stakeholder relevance: **None**.
- Maintenance cost: **Medium**.
- Rejection reasons: NO_PRIMARY_DOCUMENT=4, INSUFFICIENT_CONTENT=2, HOMEPAGE_DETECTED=1
- Candidate classifications: NAVIGATION_PAGE=4, HOMEPAGE=1, TENDER_DOCUMENT=1, REGULATORY_DOCUMENT=1, POLICY_UPDATE=1
- Sample titles: Solar Energy Corporation of India Limited (A Navratna Government of India Enterprise); Back; About Us; Board of Directors and CVO; Terms of appointment of Independent Director

### Maharashtra Electricity Regulatory Commission (`merc`)

- Source quality: **Poor - crawler/runtime error**.
- Intelligence yield: **None**.
- Stakeholder relevance: **None**.
- Maintenance cost: **High**.
- Errors: WriteTimeout: The write operation timed out
- Sample titles: The Electricity Act, 2003 with amendments; Tariff Policies; Electricity Policy; The Energy Conservation Act, 2001; The Energy Conservation (Amendment) Act, 2010


## ROI Ranking

1. Ministry of Power (`mop`): ROI 53.7
2. Central Electricity Regulatory Commission (`cerc`): ROI 2.5
3. Solar Energy Corporation of India (`seci`): ROI 0.2
4. Ministry of New & Renewable Energy (`mnre`): ROI -2.0
5. Maharashtra Electricity Regulatory Commission (`merc`): ROI -5.0

## Product Questions

### Which sources generate the highest-value intelligence?

- Ministry of Power (`mop`)
- Central Electricity Regulatory Commission (`cerc`)
- Solar Energy Corporation of India (`seci`)

### Which sources should be removed?

- None should be removed solely from this run; low-yield sources should first get custom extraction or better listing URLs.

### Which sources need custom extraction logic?

- Ministry of Power (`mop`)
- Central Electricity Regulatory Commission (`cerc`)
- Ministry of New & Renewable Energy (`mnre`)
- Solar Energy Corporation of India (`seci`)
- Maharashtra Electricity Regulatory Commission (`merc`)

### Can the platform support solar developers?

- **Yes, partially pilot-ready** for solar developers, based on current graph yield.

### Can the platform support DISCOMs?

- **Yes, partially pilot-ready** for DISCOMs, based on current graph yield.

### Can the platform support transmission companies?

- **Yes, partially pilot-ready** for transmission companies, based on current graph yield.

## Shortest Path To A Paying Pilot

- Start with the highest-yield source cluster from this audit, not with every government portal.
- Keep active-deadline and consultation promises conservative until current/future documents enter the graph.
- Build the pilot around obligations and stakeholder impact first; those are the strongest signals currently produced.
- Add custom extraction for the highest-maintenance high-value source before adding more portals.
- Best first pilot wedge: Ministry of Power.