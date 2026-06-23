# Current Route, API, And Database Inventory

Generated: 2026-06-23

Scope:

- Current frontend routes in `apps/web/app`.
- Current backend API endpoints in `apps/api/backend/api`.
- Current database table inventory with live row counts from the configured database.
- No code changes were made for this inventory.

## 1. Frontend Route Inventory

| Route | Page/component | Purpose | Auth requirement | Data source APIs used | Visibility |
| --- | --- | --- | --- | --- | --- |
| `/` | `apps/web/app/page.tsx` -> `ResolvenApp(today)` | Today briefing, latest events, exports, insight chat | Supabase session or local demo mode | `/digests/latest`, `/subscriptions`, `/health`, `/admin/sources`, `/chat`, `/events/{id}/read`, `/events/{id}/bookmark`, `/exports/latest` | User-visible |
| `/browse` | `apps/web/app/browse/page.tsx` -> `ResolvenApp(browse)` | Search/filter event archive | Supabase session or local demo mode | Base APIs plus `/events?q=&topic=&jurisdiction=` | User-visible |
| `/intelligence` | `apps/web/app/intelligence/page.tsx` -> `ResolvenApp(intelligence)` | Deadlines, obligations, stakeholder intelligence | Supabase session or local demo mode | Base APIs plus `/intelligence/deadlines`, `/intelligence/obligations`, `/intelligence/stakeholders`, `/intelligence/readiness` | User-visible |
| `/saved` | `apps/web/app/saved/page.tsx` -> `ResolvenApp(saved)` | Bookmarked updates | Supabase session or local demo mode | Base APIs plus `/events/{id}/bookmark` | User-visible |
| `/events/[eventId]` | `apps/web/app/events/[eventId]/page.tsx` -> `ResolvenApp(event)` | Event detail and grounded chat | Supabase session or local demo mode | Base APIs plus `/events/{id}`, `/chat`, `/events/{id}/read`, `/events/{id}/bookmark` | User-visible |
| `/notifications` | `apps/web/app/notifications/page.tsx` -> `ResolvenApp(notifications)` | Subscription settings | Supabase session or local demo mode | Base APIs plus `GET /subscriptions`, `PUT /subscriptions` | User-visible |
| `/account` | `apps/web/app/account/page.tsx` -> `ResolvenApp(account)` | Account/session info | Supabase session or local demo mode | Base APIs plus Supabase sign-out | User-visible |
| `/admin/sources` | `apps/web/app/admin/sources/page.tsx` -> `ResolvenApp(admin-sources)` | Source health/toggle UI | Admin API required | `/admin/sources`; frontend also calls missing `POST /admin/sources/{id}/toggle` | Admin-only |
| `/admin/runs` | `apps/web/app/admin/runs/page.tsx` -> `ResolvenApp(admin-runs)` | Crawl run monitor | Admin API required | `/admin/runs` | Admin-only |
| `/api-docs` | `apps/web/app/api-docs/page.tsx` -> `ResolvenApp(api-docs)` | Backend API docs from DB | Supabase session or local demo mode in frontend | `/meta/docs/backend-api` | User-visible |
| `/flow` | `apps/web/app/flow/page.tsx` -> `ResolvenApp(flow)` | Product/data-flow docs from DB | Supabase session or local demo mode in frontend | `/meta/docs/complete-flow` | User-visible |

Frontend mismatch:

- `toggleSource()` in `apps/web/lib/api.ts` calls `POST /admin/sources/{sourceId}/toggle`, but that endpoint is not currently exposed by the backend.

## 2. API Endpoint Inventory

### Auth

| Method | Path | Request schema | Response schema | Current frontend usage |
| --- | --- | --- | --- | --- |
| External | Supabase Auth | Bearer token from Supabase | `CurrentUser` dependency internally | All protected frontend calls |
| GET | `/health` | none | health dict | App base load |
| GET | `/subscriptions` | bearer token | `SubscriptionSettings` | Base load, notifications |
| PUT | `/subscriptions` | `SubscriptionSettings` | `SubscriptionSettings` | Notifications save |

### Events

| Method | Path | Request schema | Response schema | Current frontend usage |
| --- | --- | --- | --- | --- |
| GET | `/digests/latest` | bearer token | `DigestResponse` | Base load, Today |
| GET | `/digests/{digest_date}` | path date | `DigestResponse` | Not currently used |
| GET | `/events` | `q`, `jurisdiction`, `source`, `topic`, `date_from`, `date_to`, `bookmarked`, `page` | `list[EventSummary]` | Browse |
| GET | `/events/{event_id}` | path int | `EventSummary` | Event detail |
| POST | `/events/{event_id}/read` | path int | `{event_id, is_read}` | Today/detail actions |
| POST | `/events/{event_id}/bookmark` | path int | `{event_id, is_bookmarked}` | Today/saved/detail |
| GET | `/exports/latest` | `format=json/csv/markdown` | file `Response` | Today export buttons |

### Intelligence

| Method | Path | Request schema | Response schema | Current frontend usage |
| --- | --- | --- | --- | --- |
| GET | `/intelligence/deadlines` | `issuer`, `deadline_type`, `stakeholder`, `status`, `limit` | `list[IntelligenceDeadline]` | Intelligence page |
| GET | `/intelligence/obligations` | `stakeholder`, `issuer`, `limit` | `list[StakeholderObligationGroup]` | Intelligence page |
| GET | `/intelligence/stakeholders` | bearer token | `list[StakeholderIntelligence]` | Intelligence page |
| GET | `/intelligence/stakeholders/{stakeholder_slug}` | path slug | `StakeholderIntelligence` | Not currently used |
| GET | `/intelligence/readiness` | bearer token | `IntelligenceReadinessReport` | Intelligence page |

### Chat

| Method | Path | Request schema | Response schema | Current frontend usage |
| --- | --- | --- | --- | --- |
| POST | `/chat` | `ChatRequest { message, event_id? }` | `ChatResponse { reply, event_id, model }` | Today/detail chat |
| GET | `/chat/history` | `event_id?` | `list[{ role, content, event_id }]` | Not currently used |

### Sources

| Method | Path | Request schema | Response schema | Current frontend usage |
| --- | --- | --- | --- | --- |
| GET | `/admin/sources` | admin token | `list[dict source]` | Admin sources, admin detection |
| POST | `/admin/sources` | `SourcePayload` | source dict | Not currently used |
| PUT | `/admin/sources/{source_id}` | `SourceUpdatePayload` | source dict | Not currently used |
| DELETE | `/admin/sources/{source_id}` | path int | `{source_id, deleted}` | Not currently used |
| GET | `/admin/sources/{source_id}/pages` | path int | `list[dict source_page]` | Not currently used |
| POST | `/admin/sources/{source_id}/pages` | `SourcePagePayload` | source page dict | Not currently used |
| PUT | `/admin/pages/{page_id}` | `SourcePageUpdatePayload` | source page dict | Not currently used |
| DELETE | `/admin/pages/{page_id}` | path int | `{page_id, source_id, deleted}` | Not currently used |

### Crawl

| Method | Path | Request schema | Response schema | Current frontend usage |
| --- | --- | --- | --- | --- |
| POST | `/admin/pages/{page_id}/crawl` | path int | `CrawlTriggerResponse` | Not currently used |
| POST | `/admin/sources/{source_id}/crawl` | path int | `CrawlTriggerResponse` | Not currently used |
| GET | `/admin/runs` | admin token | `list[dict crawl_run]` | Admin runs |
| GET | `/admin/runs/{run_id}` | path int | crawl run dict | Not currently used |

### Admin

| Method | Path | Request schema | Response schema | Current frontend usage |
| --- | --- | --- | --- | --- |
| GET | `/meta/docs` | none | `list[{slug, title, category}]` | Helper exists, not used |
| GET | `/meta/docs/{slug}` | path slug | system document dict | API docs, flow pages |

### Analytics

| Method | Path | Request schema | Response schema | Current frontend usage |
| --- | --- | --- | --- | --- |
| GET | `/admin/sources/{source_id}/analytics` | path int | `SourceAnalyticsResponse` | Not currently used |

## 3. Database Inventory

This is not a full schema. It is a product usage inventory with current row counts.

| Table | Status | Rows | Purpose | Producer service | Consumer service |
| --- | --- | ---: | --- | --- | --- |
| `sources` | ACTIVE | 4 | Source configuration | migrations/admin API | crawler/admin UI |
| `source_pages` | ACTIVE | 7 | Curated crawl pages | migration/admin API | crawler/admin UI |
| `source_page_checkpoints` | ACTIVE | 7 | Incremental crawl checkpoint | `run_crawl` | parsers |
| `documents` | ACTIVE | 39 | Canonical documents | pipeline persistence | events/intelligence |
| `document_versions` | ACTIVE | 39 | File/content versions | pipeline persistence | change/family/graph |
| `document_texts` | ACTIVE | 39 | Extracted text | primary document pipeline | RAG/change/graph |
| `events` | ACTIVE | 19 | User-visible updates | event pipeline | frontend/digests |
| `summaries` | ACTIVE | 19 | Event summaries | event pipeline | event APIs |
| `digests` | ACTIVE | 1 | Daily digest header | digest builder | `/digests` |
| `digest_events` | ACTIVE | 19 | Digest-event join | digest builder | `/digests` |
| `profiles` | ACTIVE | 4 | User role/email | auth trigger/manual | auth/admin checks |
| `subscriptions` | ACTIVE | 0 | User notification prefs | `/subscriptions` | notifier/settings |
| `user_event_state` | ACTIVE | 0 | Read/bookmark state | event actions | event APIs |
| `chat_messages` | ACTIVE | 0 | Chat history | `/chat` | chat context/history |
| `notifications_log` | AUDIT | 0 | Notification delivery log | notifier | notification dedupe |
| `crawl_runs` | AUDIT | 2 | Pipeline run log | crawler | admin runs |
| `discovery_audit` | AUDIT | 52 | Discovery/extraction audit | primary pipeline | reports/admin analytics |
| `event_intelligence_audit` | AUDIT | 39 | Event gate audit | intelligence gate | quality reports |
| `regulatory_change_audit` | AUDIT | 58 | Change detection audit | change detector | reports |
| `exports_log` | AUDIT | 1 | Export usage log | `/exports/latest` | admin/audit only |
| `app_documents` | ACTIVE | 4 | DB-backed docs | seed docs | `/meta/docs` |
| `document_families` | ACTIVE | 38 | Canonical document families | family registry | lineage/change |
| `document_family_assignments` | ACTIVE | 39 | Document-to-family mapping | family registry/graph | reports/graph |
| `document_version_registry` | ACTIVE | 39 | Family version lineage | family registry | change/graph |
| `document_version_relationships` | ACTIVE | 0 | Supersedes/amends links | family/graph logic | change reports |
| `deadline_history` | ACTIVE | 391 | Normalized deadline history | family registry | deadline intelligence |
| `regulatory_graph_entities` | ACTIVE | 0 | Knowledge graph entities | graph extractor | intelligence APIs |
| `regulatory_graph_document_entities` | ACTIVE | 0 | Document-entity links | graph extractor | intelligence APIs |
| `regulatory_graph_edges` | ACTIVE | 0 | Knowledge graph relationships | graph extractor | stakeholder intelligence |
| `regulatory_graph_extractions` | AUDIT | 0 | Graph extraction audit | graph extractor | graph reports |
| `regulatory_graph_stakeholders` | ACTIVE | 0 | Affected stakeholders | graph extractor | intelligence APIs |
| `regulatory_graph_obligations` | ACTIVE | 0 | Obligations | graph extractor | obligations API |
| `regulatory_graph_deadlines` | ACTIVE | 0 | Graph deadlines | graph extractor | deadlines API |
| `regulatory_graph_family_enrichment` | AUDIT | 0 | Family enrichment audit | graph extractor | graph reports |
| `audit_log` | LEGACY | 0 | Generic audit table | no active producer found | no active consumer found |

