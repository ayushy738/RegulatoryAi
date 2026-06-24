import { EmptyState } from "@/app/components/ui/EmptyState";
import { ErrorState } from "@/app/components/ui/ErrorState";
import { LoadingState } from "@/app/components/ui/LoadingState";
import {
  deadlineLabel,
  eventStakeholders,
  eventSummary,
  formatDate,
} from "@/app/workspace/format";
import { sourceOptions } from "@/app/workspace/nav";
import { useWorkspace } from "@/app/workspace/WorkspaceContext";
import { useEventsQuery } from "@/lib/queries";
import type { DigestEvent } from "@/lib/api";

function MaterialIcon({ children, filled = false }: { children: string; filled?: boolean }) {
  return (
    <span className="material-symbols-outlined" style={filled ? { fontVariationSettings: "'FILL' 1" } : undefined}>
      {children}
    </span>
  );
}

function sourceCode(event: DigestEvent) {
  return (
    event.issuing_body
      ?.split(/\s+/)
      .find((part) => /^[A-Z]{2,}$/.test(part.replace(/[^A-Z]/g, "")))
      ?.replace(/[^A-Z]/g, "") ||
    event.issuing_body?.split(/\s+/)[0]?.replace(/[^A-Za-z]/g, "").toUpperCase() ||
    "SRC"
  );
}

function documentType(event: DigestEvent) {
  const tag = event.topic_tags.find(Boolean);
  return tag || event.event_type.replaceAll("_", " ");
}

function confidencePercent(event: DigestEvent) {
  const confidence = event.summary?.confidence;
  if (confidence === "high") return 98;
  if (confidence === "medium") return 84;
  if (confidence === "low") return 62;
  return 70;
}

export function LatestView() {
  const {
    query,
    setQuery,
    sourceFilter,
    setSourceFilter,
    token,
    canRead,
    filteredEvents,
    busyAction,
    handleBookmark,
    downloadLatestExport,
    digestStatus,
  } = useWorkspace();
  const eventsQuery = useEventsQuery(token, canRead, {
    query,
    source: sourceFilter === "all" ? undefined : sourceFilter,
  });
  const feedEvents = eventsQuery.data?.length ? eventsQuery.data : filteredEvents;

  if (digestStatus.isLoading || eventsQuery.isLoading) {
    return <LoadingState label="Loading latest updates..." />;
  }
  if (digestStatus.isError || eventsQuery.isError) {
    return (
      <ErrorState
        title="Unable to load updates"
        error={digestStatus.error ?? eventsQuery.error}
        onRetry={() => {
          digestStatus.refetch();
          void eventsQuery.refetch();
        }}
      />
    );
  }

  return (
    <div className="stitch-feed-page">
      <header className="stitch-page-header">
        <div>
          <h2>Latest Intelligence</h2>
          <p>Stay updated with the most recent regulatory filings and legislative shifts.</p>
        </div>
        <button className="stitch-secondary-action" type="button" onClick={() => void downloadLatestExport("csv", token)}>
          <MaterialIcon>download</MaterialIcon>
          Export Feed
        </button>
      </header>

      <section className="stitch-filter-toolbar" aria-label="Feed filters">
        <button className="stitch-filter-button" type="button">
          <MaterialIcon>filter_list</MaterialIcon>
          Filters
        </button>
        <div className="stitch-source-tabs">
          {sourceOptions.map((source) => (
            <button
              key={source}
              className={sourceFilter === source ? "active" : ""}
              type="button"
              onClick={() => setSourceFilter(source)}
            >
              {source === "all" ? "All Sources" : source}
            </button>
          ))}
        </div>
        <button className="stitch-filter-button stitch-filter-button--right" type="button">
          <MaterialIcon>tune</MaterialIcon>
          Custom View
        </button>
        <div className="stitch-feed-search">
          <MaterialIcon>search</MaterialIcon>
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search intelligence feed"
          />
        </div>
      </section>

      <section className="stitch-intelligence-list">
        {feedEvents.map((event) => (
          <article className="stitch-intelligence-card" key={event.id}>
            <aside className="stitch-intelligence-meta">
              <span className="stitch-source-pill">{sourceCode(event)}</span>
              <span>Document Type</span>
              <strong>{documentType(event)}</strong>
            </aside>
            <div className="stitch-intelligence-body">
              <div className="stitch-confidence-row">
                <span className="stitch-confidence-badge">
                  <MaterialIcon>verified</MaterialIcon>
                  {confidencePercent(event)}% Match
                </span>
                <span>Confidence Score</span>
              </div>
              <h3>{event.title}</h3>
              <div className="stitch-card-actions">
                <button
                  type="button"
                  onClick={() => void handleBookmark(event)}
                  disabled={busyAction === `bookmark-${event.id}`}
                  aria-label="Bookmark"
                >
                  <MaterialIcon filled={event.is_bookmarked}>bookmark</MaterialIcon>
                </button>
                <button type="button" aria-label="Share">
                  <MaterialIcon>share</MaterialIcon>
                </button>
              </div>
              <div className="stitch-publication-row">
                <span>
                  <MaterialIcon>calendar_today</MaterialIcon>
                  {formatDate(event.issue_date)}
                </span>
                <span className={deadlineLabel(event) ? "deadline" : ""}>
                  <MaterialIcon>{deadlineLabel(event) ? "event_busy" : "event_available"}</MaterialIcon>
                  {deadlineLabel(event) ? `Deadline: ${deadlineLabel(event)}` : "No Deadline Specified"}
                </span>
              </div>
              <p>
                <strong>AI Summary:</strong> {eventSummary(event)}
              </p>
              <div className="stitch-impact-row">
                {eventStakeholders(event).slice(0, 4).map((stakeholder) => (
                  <span key={stakeholder}>{stakeholder}</span>
                ))}
                {!eventStakeholders(event).length ? <span>No stakeholder impact tagged</span> : null}
              </div>
              <footer>
                <a href={event.source_url} target="_blank" rel="noreferrer">
                  Read Original Intelligence
                </a>
                <a href={`/events/${event.id}`}>
                  View <MaterialIcon>arrow_forward</MaterialIcon>
                </a>
              </footer>
            </div>
          </article>
        ))}
        {!feedEvents.length ? (
          <EmptyState title="No matching updates" body="Try removing filters or run the curated crawl." />
        ) : null}
        <button className="stitch-load-more" type="button">
          Load Older Intelligence <MaterialIcon>expand_more</MaterialIcon>
        </button>
      </section>
    </div>
  );
}
