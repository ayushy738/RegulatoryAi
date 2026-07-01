import Link from "next/link";
import { useMemo, useState } from "react";
import {
  ArrowRight,
  BadgeCheck,
  Bookmark,
  CalendarClock,
  ExternalLink,
  Filter,
  Loader2,
  Search,
  Share2,
  SlidersHorizontal,
} from "lucide-react";

import { EmptyState } from "@/app/components/ui/EmptyState";
import { ErrorState } from "@/app/components/ui/ErrorState";
import { LoadingState } from "@/app/components/ui/LoadingState";
import { Select } from "@/app/components/ui/Select";
import {
  clampText,
  deadlineLabel,
  eventStakeholders,
  eventSummary,
  formatDate,
} from "@/app/workspace/format";
import {
  deadlineTypes,
  eventTypeOptions,
  sourceOptions,
  stakeholderOptions,
} from "@/app/workspace/nav";
import { useWorkspace } from "@/app/workspace/WorkspaceContext";
import type { DigestEvent } from "@/lib/api";
import { useEventsQuery } from "@/lib/queries";

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

function confidencePercent(event: DigestEvent) {
  const confidence = event.summary?.confidence;
  if (confidence === "high") return 98;
  if (confidence === "medium") return 84;
  if (confidence === "low") return 62;
  return 70;
}

function matchesDeadline(event: DigestEvent, deadlineFilter: string) {
  if (deadlineFilter === "all") return true;
  const label = deadlineLabel(event);
  if (!label) return false;
  return label.toLowerCase().includes(deadlineFilter.replaceAll("_", " ").toLowerCase());
}

export function LatestView() {
  const {
    events,
    query,
    setQuery,
    sourceFilter,
    setSourceFilter,
    stakeholderFilter,
    setStakeholderFilter,
    eventTypeFilter,
    setEventTypeFilter,
    dateFilter,
    setDateFilter,
    token,
    canRead,
    busyAction,
    handleBookmark,
    downloadLatestExport,
    digestStatus,
    setStatusMessage,
    setSelectedEvidence,
  } = useWorkspace();
  const [showFilters, setShowFilters] = useState(true);
  const [topicFilter, setTopicFilter] = useState("all");
  const [deadlineFilter, setDeadlineFilter] = useState("all");
  const [savedFilter, setSavedFilter] = useState("all");
  const [sortMode, setSortMode] = useState("newest");
  const [density, setDensity] = useState<"comfortable" | "compact">("comfortable");
  const [visibleCount, setVisibleCount] = useState(20);
  const eventsQuery = useEventsQuery(token, canRead, {
    query,
    source: sourceFilter === "all" ? undefined : sourceFilter,
  });
  const baseEvents = eventsQuery.data?.length ? eventsQuery.data : events;
  const topicOptions = useMemo(
    () => ["all", ...Array.from(new Set(baseEvents.flatMap((event) => event.topic_tags))).sort()],
    [baseEvents],
  );
  const feedEvents = useMemo(() => {
    const now = new Date();
    return baseEvents.filter((event) => {
      const text = `${event.title} ${event.issuing_body ?? ""} ${event.topic_tags.join(" ")} ${eventSummary(event)}`.toLowerCase();
      if (query && !text.includes(query.toLowerCase())) return false;
      if (sourceFilter !== "all" && !text.includes(sourceFilter.toLowerCase())) return false;
      if (stakeholderFilter !== "all") {
        const stakeholders = eventStakeholders(event).join(" ").toLowerCase();
        if (!stakeholders.includes(stakeholderFilter.toLowerCase())) return false;
      }
      if (eventTypeFilter !== "all" && event.event_type !== eventTypeFilter) return false;
      if (topicFilter !== "all" && !event.topic_tags.includes(topicFilter)) return false;
      if (savedFilter === "saved" && !event.is_bookmarked) return false;
      if (!matchesDeadline(event, deadlineFilter)) return false;
      if (dateFilter !== "all" && event.issue_date) {
        const eventDate = new Date(event.issue_date);
        const diffDays = Math.floor((now.getTime() - eventDate.getTime()) / 86_400_000);
        if (dateFilter === "week" && diffDays > 7) return false;
        if (dateFilter === "month" && diffDays > 31) return false;
      }
      return true;
    });
  }, [
    baseEvents,
    dateFilter,
    deadlineFilter,
    eventTypeFilter,
    query,
    savedFilter,
    sourceFilter,
    stakeholderFilter,
    topicFilter,
  ]);
  const sortedEvents = useMemo(() => {
    return [...feedEvents].sort((left, right) => {
      if (sortMode === "confidence") return confidencePercent(right) - confidencePercent(left);
      if (sortMode === "deadline") {
        const leftDeadline = deadlineLabel(left) ? 0 : 1;
        const rightDeadline = deadlineLabel(right) ? 0 : 1;
        if (leftDeadline !== rightDeadline) return leftDeadline - rightDeadline;
      }
      return new Date(right.issue_date ?? right.detected_at).getTime() - new Date(left.issue_date ?? left.detected_at).getTime();
    });
  }, [feedEvents, sortMode]);
  const visibleEvents = sortedEvents.slice(0, visibleCount);

  if (digestStatus.isLoading || eventsQuery.isLoading) return <LoadingState label="Loading latest updates..." />;
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

  function saveCustomView() {
    window.localStorage.setItem(
      "resolven-latest-view",
      JSON.stringify({
        query,
        sourceFilter,
        stakeholderFilter,
        eventTypeFilter,
        dateFilter,
        topicFilter,
        deadlineFilter,
        savedFilter,
        sortMode,
        density,
      }),
    );
    setStatusMessage("Latest view filters saved on this device.");
  }

  function shareFeed() {
    const params = new URLSearchParams();
    if (query) params.set("q", query);
    if (sourceFilter !== "all") params.set("source", sourceFilter);
    const url = `${window.location.origin}/latest${params.toString() ? `?${params.toString()}` : ""}`;
    void navigator.clipboard?.writeText(url);
    setStatusMessage("Share link copied.");
  }

  return (
    <div className={`ops-page latest-workspace density-${density}`}>
      <section className="ops-page-header premium-page-header">
        <div>
          <span>Analyst Feed</span>
          <h1>Latest regulatory updates</h1>
          <p>
            {feedEvents.length} matching updates across source, stakeholder, type, topic, deadline, date, and search
            filters.
          </p>
        </div>
        <div className="ops-action-row">
          <button type="button" onClick={() => setShowFilters((value) => !value)}>
            <Filter size={16} />
            Filters
          </button>
          <button type="button" onClick={saveCustomView}>
            <SlidersHorizontal size={16} />
            Save view
          </button>
          <button type="button" onClick={shareFeed}>
            <Share2 size={16} />
            Share
          </button>
          <button type="button" onClick={() => void downloadLatestExport("csv", token)}>
            <ExternalLink size={16} />
            Export
          </button>
        </div>
      </section>

      {showFilters ? (
        <section className="toolbar-panel latest-toolbar sticky-filter-bar" aria-label="Feed filters">
          <label className="search-box">
            <Search size={17} />
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Search intelligence feed"
            />
          </label>
          <Select label="Source" value={sourceFilter} onChange={setSourceFilter} options={sourceOptions} />
          <Select label="Stakeholder" value={stakeholderFilter} onChange={setStakeholderFilter} options={stakeholderOptions} />
          <Select label="Type" value={eventTypeFilter} onChange={setEventTypeFilter} options={eventTypeOptions} />
          <Select label="Deadline" value={deadlineFilter} onChange={setDeadlineFilter} options={deadlineTypes} />
          <Select label="Topic" value={topicFilter} onChange={setTopicFilter} options={topicOptions} />
          <Select label="Date" value={dateFilter} onChange={setDateFilter} options={["all", "week", "month"]} />
          <Select label="Sort" value={sortMode} onChange={setSortMode} options={["newest", "deadline", "confidence"]} />
          <Select label="Saved" value={savedFilter} onChange={setSavedFilter} options={["all", "saved"]} />
          <div className="density-toggle" aria-label="Feed density">
            <button
              type="button"
              className={density === "comfortable" ? "active" : ""}
              onClick={() => setDensity("comfortable")}
            >
              Comfortable
            </button>
            <button
              type="button"
              className={density === "compact" ? "active" : ""}
              onClick={() => setDensity("compact")}
            >
              Compact
            </button>
          </div>
        </section>
      ) : null}

      <section className="stitch-intelligence-list ops-feed-list">
        {visibleEvents.map((event) => (
          <article className={`stitch-intelligence-card ops-feed-card premium-event-card ${density}`} key={event.id}>
            <aside className="stitch-intelligence-meta">
              <span className="stitch-source-pill">{sourceCode(event)}</span>
              <span>{event.issuing_body ?? "Unknown issuer"}</span>
              <strong>{event.event_type.replaceAll("_", " ")}</strong>
            </aside>
            <div className="stitch-intelligence-body">
              <div className="stitch-confidence-row">
                <span className="stitch-confidence-badge">
                  <BadgeCheck size={15} />
                  {confidencePercent(event)}% confidence
                </span>
                <span>{formatDate(event.issue_date)}</span>
              </div>
              <h3>{event.title}</h3>
              <div className="stitch-card-actions latest-card-icon-actions">
                <button
                  type="button"
                  aria-label="Open evidence"
                  onClick={() =>
                    setSelectedEvidence({
                      title: event.title,
                      issuer: event.issuing_body,
                      date: event.issue_date,
                      summary: eventSummary(event),
                      evidence: event.summary?.evidence_quotes
                        ?.map((quote) => Object.values(quote).join(" "))
                        .join("\n"),
                      sourceUrl: event.source_url,
                      documentId: event.id,
                      relationships: eventStakeholders(event).map((stakeholder) => `Affects ${stakeholder}`),
                    })
                  }
                >
                  <Search size={17} />
                </button>
              </div>
              <div className="stitch-publication-row">
                <span>
                  <CalendarClock size={15} />
                  {deadlineLabel(event) ? `Deadline: ${deadlineLabel(event)}` : "No deadline specified"}
                </span>
              </div>
              <p>
                <strong>What changed:</strong> {clampText(eventSummary(event), 360)}
              </p>
              <div className="stitch-impact-row">
                {eventStakeholders(event).slice(0, 4).map((stakeholder) => (
                  <span key={stakeholder}>{stakeholder}</span>
                ))}
                {!eventStakeholders(event).length ? <span>No stakeholder impact tagged</span> : null}
              </div>
              <footer>
                <a href={event.source_url} target="_blank" rel="noreferrer">
                  Open source
                  <ExternalLink size={15} />
                </a>
                <button
                  type="button"
                  onClick={() => void handleBookmark(event)}
                  disabled={busyAction === `bookmark-${event.id}`}
                >
                  {busyAction === `bookmark-${event.id}` ? (
                    <Loader2 className="spin" size={15} />
                  ) : (
                    <Bookmark size={15} fill={event.is_bookmarked ? "currentColor" : "none"} />
                  )}
                  {event.is_bookmarked ? "Saved" : "Save"}
                </button>
                <Link href={`/events/${event.id}`}>
                  Open
                  <ArrowRight size={15} />
                </Link>
              </footer>
            </div>
          </article>
        ))}
        {!visibleEvents.length ? (
          <EmptyState title="No matching updates" body="Try removing filters or run the curated crawl." />
        ) : null}
        {visibleCount < sortedEvents.length ? (
          <button className="stitch-load-more" type="button" onClick={() => setVisibleCount((value) => value + 20)}>
            Load older intelligence
            <ArrowRight size={16} />
          </button>
        ) : null}
      </section>
    </div>
  );
}
