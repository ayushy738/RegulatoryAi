# Website UI Audit

Date: 2026-07-01 IST

## Scope

This is a UI/UX audit only. No frontend, backend, Azure, or WhatsApp code was modified.

Inspected surfaces:

- Landing/auth screen
- Dashboard
- Latest Intelligence
- Intelligence
- Deadlines
- Ask AI
- Notifications/Digests
- Account
- Saved
- Event detail
- Admin dashboard
- Admin sources, pages, runs, events, documents, families, checkpoints, analytics
- API Docs
- Flow
- Desktop viewport
- Mobile viewport around 390px width

Environment used:

- Web dev server: `http://localhost:3000`
- API server launched for audit: `http://127.0.0.1:8001`
- Frontend typecheck: passed with `tsc --noEmit`

## Executive Verdict

The product has strong raw material: real regulatory data, graph intelligence, RAG-capable backend work, and a coherent energy-regulation domain. The current UI, however, reads like a polished prototype layered over incomplete interaction contracts.

The biggest problem is trust. Many controls look production-ready but do nothing. Several surfaces show raw OCR/extraction text. Mobile loses primary navigation. Chat copy still claims structured citations are missing even though the backend has moved forward. The result is a user experience that looks richer than it actually behaves.

Production readiness: **not ready without immediate UX triage**.

## Immediate Fixes

Fix these first before any visual redesign.

| Priority | Issue | Impact | Evidence |
|---|---|---|---|
| P0 | Local preview/session state is not navigation-safe | Clicking sidebar links from preview returns to the auth screen, making route testing and unauthenticated preview brittle | Browser test: Dashboard preview -> Latest link -> auth screen |
| P0 | Mobile has no replacement navigation | At mobile width the sidebar is hidden and no hamburger/bottom nav appears | `apps/web/app/globals.css:3413` hides `.sidebar`; browser mobile audit found no alternate nav |
| P0 | Global topbar search is inert | Users can type and press Enter, but nothing filters or navigates | `apps/web/app/components/layout/TopBar.tsx:24` has input without state/handler |
| P0 | Topbar notification/settings buttons are inert | Alert dot implies urgency but opens nothing | `TopBar.tsx:27-31`; browser click showed no change |
| P0 | Event detail tabs are fake | Obligations, Timeline, Stakeholder Analysis, Source Document never switch content | `EventDetailView.tsx:73-76`; browser click showed active tab stayed Summary |
| P0 | Primary-looking analysis actions are fake | Generate Stakeholder Report and Run Gap Analysis do nothing | `DashboardView.tsx:209`, `EventDetailView.tsx:164` |
| P0 | Latest page action buttons are fake | Filters, Custom View, Share, Load Older do nothing | `LatestView.tsx:97-115`, `153-155`, `190-192`; browser click showed no change |
| P0 | Ask AI feedback/copy/regenerate buttons are fake | Thumb up/down, copy, regenerate look interactive but do not work | `AskView.tsx:111-114` |
| P0 | Chat UI is stale versus backend | UI says `/chat` lacks structured citations; web schema ignores `intent`, `citations`, `related_questions` | `AskView.tsx:98-106`, `apps/web/lib/schemas.ts:80-84` |
| P1 | API dev port mismatch | Web default is 8001; API dev script starts 8000, causing dashboard `Failed to fetch` unless manually corrected | `apps/web/lib/api.ts:64-65`, `apps/api/package.json:6` |
| P1 | Slow/opaque loading states | Deadlines/Intelligence sat on loading for roughly 20-30 seconds before content appeared in audit run | Browser long-wait audit |
| P1 | Raw OCR artifacts leak into product copy | Summaries/deadline evidence include `(cid:)`, duplicated Hindi glyphs, huge copied legal/OCR fragments | Dashboard, Latest, Deadlines, Event detail |
| P1 | Admin data is misleading | Admin dashboard shows sources, but several admin tables show "No rows"; backend logs show admin families query error hidden behind a 200 response | API log: `column dh.id does not exist` in `list_admin_families` |
| P1 | Sign out is not available | Sidebar accepts `onSignOut` but aliases it unused; no visible sign-out control | `Sidebar.tsx:32` |
| P1 | Saved route exists but is absent from active sidebar nav | Users can reach `/saved` only by URL or alternate code path | `workspace/nav.ts:28` defines Saved; `Sidebar.tsx` local nav omits it |

## Broken Buttons And Controls

Confirmed broken or inert in browser:

- Topbar search input: accepts text, no filter, no search results, no route change.
- Topbar Notifications icon: no menu, page, count, or drawer opens.
- Topbar Settings icon: no menu or settings page opens.
- Dashboard "Generate Stakeholder Report": no visible effect.
- Latest "Filters": no drawer/popover.
- Latest "Custom View": no drawer/modal/save behavior.
- Latest Share buttons: 22 buttons found; first clicked with no effect.
- Latest "Load Older Intelligence": no pagination or additional results.
- Event detail tabs: Obligations, Timeline, Stakeholder Analysis, Source Document all no-op.
- Event detail "Run Gap Analysis": no visible effect.
- Ask AI thumb up/down buttons: no visible feedback state.
- Ask AI copy button: no visible confirmation and no implemented handler.
- Ask AI sync/regenerate button: no implemented handler.
- Admin dashboard filter icon: no filter panel.
- Admin dashboard refresh icon: no refresh behavior.
- Admin dashboard "Add Source": only links to Sources; there is no add-source form.

Partially working:

- Latest source tabs work and change the active source.
- Latest feed search filters results after the page is loaded.
- Intelligence tabs work.
- Notifications settings render and have a Save button.
- Event Save button calls bookmark behavior.
- Admin Sources Refresh has a handler.
- Ask prompt suggestions send chat requests, but were not used for destructive/mutating validation beyond safe inspection.

## Route Audit

### Landing/Auth

Works:

- Email/password fields render.
- Sign in, magic link, and local preview buttons render.

Problems:

- Local preview state is not durable across normal anchor navigation.
- The product has no clear "preview mode" banner or limitation notice once inside.

### Dashboard

Works:

- Loads digest data with live API.
- Shows KPIs, recent updates, deadlines column, stakeholder cards.

Problems:

- KPI metadata appears fabricated or hardcoded (`+12%`, "Updated", "3 Open").
- "Upcoming Deadlines" says clear on dashboard even when Deadlines page later returns active deadlines.
- News summaries are not line-clamped enough and contain extraction/OCR noise.
- "Generate Stakeholder Report" is a no-op.
- Dashboard cards link with normal anchors, causing local preview auth loss.

### Latest Intelligence

Works:

- Loads event feed after a delay.
- Source tabs and local search work.
- Export button is wired to backend export URL.

Problems:

- Filters, Custom View, Share, Load Older are no-ops.
- The first content can appear after an extended loading period.
- Cards are visually heavy and repeat large OCR summaries.
- Confidence percentages look absolute and over-precise.
- "No matching updates" can appear after filter/search but Load Older remains clickable and inert.

### Intelligence

Works:

- Tabs render and switch.
- Obligations, Stakeholders, Readiness, and Deadlines data can load.

Problems:

- First load is too slow and gives no progress detail.
- Dense raw obligation text overwhelms scanning.
- Readiness is presented as totals without drill-down paths.
- Deadlines copy includes raw OCR artifacts.

### Deadlines

Works:

- Deadline type and stakeholder filters render.
- Refresh calls the intelligence reload handler.
- Active deadline cards eventually load.

Problems:

- Load time is long and opaque.
- Evidence text is raw and polluted.
- Deadline cards need severity, confidence, source, and "why this matters" hierarchy.

### Ask AI

Works:

- Composer exists.
- Prompt suggestions are wired to ask.
- History rail can populate.

Problems:

- Feedback/copy/regenerate controls are fake.
- Citation panel is hardcoded and stale.
- UI still says structured citations are unavailable, while backend RAG now returns additive citation fields.
- The assistant answer area includes static "Critical Deadline" and "Renewable Priority" cards unrelated to the current answer.
- The page shows only latest user and latest assistant, not a clear conversational thread.

### Event Detail

Works:

- Event data loads.
- Source document link works.
- Bookmark/save is wired.

Problems:

- Detail tabs are fake.
- Run Gap Analysis is fake.
- Sentiment Analysis is explicitly a backend gap but is rendered as if part of the product.
- Risk/readiness bars are formulaic and not clearly tied to evidence.
- Long summary text overwhelms the primary decision path.

### Notifications/Digests

Works:

- Preferences render.
- Save button is wired.

Problems:

- Sidebar label says "Digests" while route/page is notification preferences.
- "Stakeholders and topics" is a comma-separated free text field; this should be a tag selector with validation.
- No preview of what a digest looks like.

### Account

Works:

- Profile and subscription panels render.

Problems:

- No sign out.
- No account management actions.
- Local preview is labeled Admin automatically, which may confuse permission expectations.

### Saved

Works:

- Empty state renders.

Problems:

- Saved route is missing from the sidebar used by the app shell.
- Saved deadlines count currently mirrors all active deadlines, not saved deadlines.

### Admin

Works:

- Admin dashboard renders source summary and metrics.
- Admin Sources/Pages/Runs/Events/Documents/Families/Checkpoints/Analytics routes render.

Problems:

- Admin dashboard filter/refresh controls are fake.
- Add Source does not open an add flow.
- Admin subviews often show "No rows" despite platform data existing elsewhere.
- Backend logs show `list_admin_families` failing on `dh.id`, while the UI presents a quiet empty state.
- Admin dashboard uses marketing-style KPI cards for operational work; operators need dense tables, status, logs, retry, and error context.

### API Docs / Flow

Works:

- Static docs and flow render.

Problems:

- They are not discoverable in the active sidebar.
- Flow is static; it does not show current pipeline health or row counts.

## Accessibility Findings

- Material icon text leaks into accessible names: examples include `dashboard Dashboard`, `filter_list Filters`, `download Export Feed`.
- Icon-only buttons lack meaningful visible labels or tooltips in several places.
- Fake buttons are still keyboard-focusable, creating bad keyboard and screen-reader experiences.
- Tabs are implemented as plain buttons without tablist/tabpanel semantics.
- Loading states are not announced with useful progress or context.
- Mobile nav disappears entirely at the breakpoint.

## Content Quality Findings

The UI currently surfaces backend/OCR output too directly. Examples observed:

- `(cid:)` artifacts in Latest and Deadline evidence.
- Repeated garbled Hindi/OCR text in deadlines and latest summaries.
- Long unstructured snippets in dashboard cards.
- "Tender Submission Deadline shortened from 2026-09-24 to 2026-09-24" reads nonsensical.
- Overconfident labels like "98% Match" lack explanation.

Required content layer:

- Sanitize OCR artifacts before rendering.
- Line-clamp summaries.
- Separate "what changed", "why it matters", "who is affected", "deadline", and "source evidence".
- Use evidence quotes only in citation/evidence sections, not as primary card copy.

## UX Refactor Recommendation

### Product North Star

Refactor the app around the job: "Help regulatory teams know what changed, who is affected, what action is due, and where the evidence is."

Every screen should answer one of these:

- What changed?
- What do I need to do?
- By when?
- Who is affected?
- What source proves it?
- What changed versus previous versions?

### Information Architecture

Replace the current mixed nav with a task-first structure:

- Monitor: dashboard and latest updates
- Obligations: obligations by stakeholder/entity
- Deadlines: timeline/calendar/list
- Documents: source documents, families, versions
- Ask: RAG chat with evidence
- Saved: bookmarked work queue
- Notifications: delivery preferences
- Admin: source and pipeline operations

Unify `workspace/nav.ts` and `Sidebar.tsx` so there is one navigation source of truth.

### Shell Refactor

Immediate shell changes:

- Use client-side navigation or persist preview/auth state.
- Add mobile hamburger or bottom navigation.
- Make topbar search global or remove it.
- Make notifications/settings link to real destinations or disable them with tooltips.
- Add sign out.
- Show route title and contextual actions in the topbar.

### Dashboard Refactor

Dashboard should be a command center, not a marketing bento:

- "Needs attention now" list: urgent deadlines, high-impact changes, unread critical events.
- "What changed" feed with 3-5 concise cards.
- "Deadlines next 7/14/30 days" with source and stakeholder.
- "Stakeholder impact" as drill-down cards.
- Remove fabricated deltas until real trend data exists.
- Every KPI should click through to a filtered view.

### Latest Refactor

Turn Latest into a high-density regulatory feed:

- Left filter rail: source, date, event type, stakeholder, topic, deadline.
- Main list: title, source, date, change type, affected stakeholders, deadline chip, confidence.
- Expandable summary/evidence row.
- Real share/copy actions.
- Real pagination or infinite scroll.
- Saved/bookmark state visible and filterable.

### Intelligence Refactor

Make Intelligence graph-first:

- Stakeholder matrix: stakeholders x obligations/deadlines/documents.
- Obligation detail drawer with evidence and source links.
- Deadline timeline with severity and confidence.
- Readiness score explained by underlying facts.
- "Why this appears here" evidence trail for each graph fact.

### Ask AI Refactor

Ask should become an evidence workspace:

- Full conversation transcript.
- Structured citations rendered from backend `citations`.
- Right-side source panel with document title, issuer, date, chunk excerpt, URL.
- Related questions rendered from backend `related_questions`.
- "Copy answer", "thumbs up/down", and "regenerate" wired or removed.
- No static "Critical Deadline" card unless retrieved context includes one.
- Display insufficient-evidence states clearly.

### Event Detail Refactor

Make tabs real:

- Summary: concise change, impact, action.
- Obligations: extracted obligations from graph/RAG.
- Timeline: dates, deadlines, version history.
- Stakeholders: affected entities and why.
- Source Document: original, citations, extracted text, family/version.

Remove sentiment/readiness claims unless backed by data.

### Admin Refactor

Admin should feel operational:

- Dense tables with search/sort/filter.
- Source detail page with crawl history, failures, parser type, next run.
- Run detail/logs page.
- Retry actions with confirmation.
- Add/edit source forms.
- RAG/graph health panels if those systems are production components.
- Do not hide backend errors behind empty states.

### Design System Refactor

- Pick one icon system. Current UI mixes Material Symbols and Lucide.
- Reduce radius on operational cards and tables; reserve large rounded cards for marketing only.
- Use tighter typography for data-heavy views.
- Standardize button hierarchy:
  - Primary: creates/runs/submits
  - Secondary: navigates/exports
  - Icon button: one clear tool with tooltip
  - Disabled: visible reason
- Add skeleton states that match final layout.
- Use line-clamp and expandable sections for long regulatory text.
- Improve empty states with next action.

## Suggested Refactor Roadmap

### Phase 0: UX Safety Patch

Target: 1-2 days.

- Remove or disable all no-op buttons.
- Wire topbar Notifications to `/notifications`.
- Wire Settings to `/account` or a real settings page.
- Add sign out.
- Persist preview mode or use client-side navigation.
- Add mobile navigation.
- Align API default port with API dev script.
- Update chat schema to include `intent`, `citations`, `related_questions`.

### Phase 1: Navigation And Shell

Target: 3-5 days.

- Single nav config.
- Responsive app shell.
- Route title/action system.
- Global search strategy.
- Consistent loading/error/empty states.

### Phase 2: Core User Workflows

Target: 1-2 weeks.

- Rebuild Dashboard, Latest, Deadlines, Intelligence around tasks.
- Add real filter drawers and pagination.
- Add evidence/citation drawers.
- Normalize summary rendering.

### Phase 3: RAG Chat UX

Target: 1 week.

- Structured answer renderer.
- Source citation panel.
- Related questions.
- Feedback/copy/regenerate actions.
- Conversation list/history.

### Phase 4: Admin Operations

Target: 1-2 weeks.

- Admin tables and detail routes.
- Crawl logs and retry flows.
- Source add/edit.
- Graph/RAG status pages.
- Backend error surfacing.

## Verification Notes

Commands/run checks:

- `npm run typecheck --workspace @regulatory-ai/web`: passed.
- Browser audited desktop app at `http://localhost:3000`.
- API launched at `http://127.0.0.1:8001` to match current frontend default.
- Mobile breakpoint checked at approximately 390px wide.

Dev-server caveat:

- The API package dev script starts port `8000`, while the web default uses `8001`. The audit used `8001` manually so UI routes could load live data.

## Final Recommendation

Do not start by polishing colors. Start by removing false affordances and repairing the shell. The current design creates user doubt because it asks users to trust controls that do not respond.

The best refactor is a task-first regulatory workspace:

1. Stable navigation on every viewport.
2. Real filters and actions only.
3. Evidence-first cards.
4. Structured RAG citations in chat.
5. Dense admin operations instead of dashboard theater.
6. Sanitized, human-readable regulatory summaries.

Once those are in place, the visual design can be simplified into a calmer, more professional operational tool.
