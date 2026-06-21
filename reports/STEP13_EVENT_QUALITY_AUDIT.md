# Step 13 Event Quality Audit

Generated at: 2026-06-21T17:31:56.339565+00:00

## Event Survival Analysis

- Total current events: 23
- Events that survive quality gate: 0
- Events rejected by quality gate: 23
- Survival percentage: 0.0%
- Rejection percentage: 100.0%

## Rejection Breakdown

- HOMEPAGE: 3
- LISTING_PAGE: 8
- ARCHIVE_PAGE: 0
- CATEGORY_PAGE: 3
- SEARCH_PAGE: 1
- NAVIGATION_PAGE: 0
- NO_PRIMARY_DOCUMENT: 8
- OTHER: 0

## Classification Breakdown

- LISTING_PAGE: 8
- HOMEPAGE: 3
- NAVIGATION_PAGE: 3
- CATEGORY_PAGE: 3
- NOTIFICATION: 2
- SEARCH_PAGE: 1
- AMENDMENT: 1
- CIRCULAR: 1
- POLICY_UPDATE: 1

## Rejection Reasons

- NO_PRIMARY_DOCUMENT: 8
- LISTING_PAGE_DETECTED: 8
- HOMEPAGE_DETECTED: 3
- CATEGORY_PAGE_DETECTED: 3
- SEARCH_PAGE_DETECTED: 1

## Primary Document Coverage

- Events generated from primary document content: 0
- Events generated without stored primary content: 23
- Likely link/listing-page generated events: 15
- Generic page-content events: 17
- Percentage of events that would disappear if primary-document requirements were enforced: 100.0%

## Surviving Event Examples

- None. No current event has enough stored primary content evidence.

## Rejected Event Examples

- Title: Central Electricity Regulatory Commission
  - Classification: HOMEPAGE
  - Reason: HOMEPAGE_DETECTED
  - Source: https://cercind.gov.in/index-en.html
- Title: 1 Central Electricity Regulatory Commission
  - Classification: NOTIFICATION
  - Reason: NO_PRIMARY_DOCUMENT
  - Source: https://cercind.gov.in/tariiff/notification.pdf
- Title:  :::  Central Electricity Regulatory Commission :::
  - Classification: LISTING_PAGE
  - Reason: LISTING_PAGE_DETECTED
  - Source: https://cercind.gov.in/Regulations.html?show=All
- Title:  :::  Central Electricity Regulatory Commission :::
  - Classification: LISTING_PAGE
  - Reason: LISTING_PAGE_DETECTED
  - Source: https://www.cercind.gov.in/orders.html
- Title: Central Electricity Regulatory Commission
  - Classification: LISTING_PAGE
  - Reason: LISTING_PAGE_DETECTED
  - Source: https://www.cercind.gov.in/Current_reg.html
- Title: Cercind
  - Classification: NOTIFICATION
  - Reason: NO_PRIMARY_DOCUMENT
  - Source: https://www.cercind.gov.in/regulations/175-Notification.pdf
- Title: ::: केन्द्रीय विद्युत विनियामक आयोग :::
  - Classification: HOMEPAGE
  - Reason: HOMEPAGE_DETECTED
  - Source: https://cercind.gov.in/
- Title: Central Electricity Regulatory Commission
  - Classification: LISTING_PAGE
  - Reason: LISTING_PAGE_DETECTED
  - Source: https://cercind.gov.in/recent_orders.html
