"use client";

import { useMemo, useState } from "react";
import { ChevronDown, Download, FileSearch, Share2 } from "lucide-react";

import { IntelligenceCard } from "@/app/components/events/IntelligenceCard";
import { Button } from "@/app/components/ui/Button";
import { EmptyState } from "@/app/components/ui/EmptyState";
import { ErrorState } from "@/app/components/ui/ErrorState";
import { PageHeader } from "@/app/components/ui/PageHeader";
import { SkeletonCards } from "@/app/components/ui/Skeleton";
import {
  ActiveFilters,
  FilterSelect,
  FilterSheet,
  SearchInput,
  Toolbar,
} from "@/app/components/ui/Toolbar";
import {
  deadlineLabel,
  eventStakeholders,
  eventSummary,
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

/** Explicit page size; the feed never fetches more without a user action. */
const PAGE_SIZE = 20;

function toOptions(values: string[], allLabel: string) {
  return values.map((value) => ({
    value,
    label:
      value === "all"
        ? allLabel
        : value.replaceAll("_", " ").replace(/^./, (char) => char.toUpperCase()),
  }));
}

const DATE_OPTIONS = [
  { value: "all", label: "Any date" },
  { value: "week", label: "Last 7 days" },
  { value: "month", label: "Last 30 days" },
];

const SORT_OPTIONS = [
  { value: "newest", label: "Newest first" },
  { value: "deadline", label: "Deadline first" },
];

function matchesDeadline(event: DigestEvent, deadlineFilter: string) {
  if (deadlineFilter === "all") return true;
  const label = deadlineLabel(event);
  if (!label) return false;
  return label
    .toLowerCase()
    .includes(deadlineFilter.replaceAll("_", " ").toLowerCase());
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

  const [topicFilter, setTopicFilter] = useState("all");
  const [deadlineFilter, setDeadlineFilter] = useState("all");
  const [savedFilter, setSavedFilter] = useState("all");
  const [sortMode, setSortMode] = useState("newest");
  const [visibleCount, setVisibleCount] = useState(PAGE_SIZE);

  const eventsQuery = useEventsQuery(token, canRead, {
    query,
    source: sourceFilter === "all" ? undefined : sourceFilter,
  });
  const baseEvents = eventsQuery.data?.length ? eventsQuery.data : events;

  const topicOptions = useMemo(
    () => [
      { value: "all", label: "Any topic" },
      ...Array.from(new Set(baseEvents.flatMap((event) => event.topic_tags)))
        .sort()
        .map((tag) => ({ value: tag, label: tag })),
    ],
    [baseEvents],
  );

  const feedEvents = useMemo(() => {
    const now = new Date();
    return baseEvents.filter((event) => {
      const text =
        `${event.title} ${event.issuing_body ?? ""} ${event.topic_tags.join(" ")} ${eventSummary(event)}`.toLowerCase();
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

  const sortedEvents = useMemo(
    () =>
      [...feedEvents].sort((left, right) => {
        if (sortMode === "deadline") {
          const leftDeadline = deadlineLabel(left) ? 0 : 1;
          const rightDeadline = deadlineLabel(right) ? 0 : 1;
          if (leftDeadline !== rightDeadline) return leftDeadline - rightDeadline;
        }
        return (
          new Date(right.issue_date ?? right.detected_at).getTime() -
          new Date(left.issue_date ?? left.detected_at).getTime()
        );
      }),
    [feedEvents, sortMode],
  );

  const visibleEvents = sortedEvents.slice(0, visibleCount);
  const remaining = sortedEvents.length - visibleEvents.length;

  function resetPaging<T>(setter: (value: T) => void) {
    return (value: T) => {
      setter(value);
      setVisibleCount(PAGE_SIZE);
    };
  }

  function clearFilters() {
    setQuery("");
    setSourceFilter("all");
    setStakeholderFilter("all");
    setEventTypeFilter("all");
    setDateFilter("all");
    setTopicFilter("all");
    setDeadlineFilter("all");
    setSavedFilter("all");
    setVisibleCount(PAGE_SIZE);
  }

  const activeFilters = useMemo(() => {
    const entries: Array<{ key: string; label: string; onRemove: () => void }> = [];
    const add = (key: string, label: string, onRemove: () => void) =>
      entries.push({ key, label, onRemove });
    if (query) add("q", `Search: ${query}`, () => setQuery(""));
    if (sourceFilter !== "all") add("source", sourceFilter, () => setSourceFilter("all"));
    if (stakeholderFilter !== "all")
      add("stakeholder", stakeholderFilter, () => setStakeholderFilter("all"));
    if (eventTypeFilter !== "all")
      add("type", eventTypeFilter, () => setEventTypeFilter("all"));
    if (topicFilter !== "all") add("topic", topicFilter, () => setTopicFilter("all"));
    if (deadlineFilter !== "all")
      add(
        "deadline",
        deadlineFilter.replaceAll("_", " ").toLowerCase(),
        () => setDeadlineFilter("all"),
      );
    if (dateFilter !== "all")
      add(
        "date",
        DATE_OPTIONS.find((option) => option.value === dateFilter)?.label ?? dateFilter,
        () => setDateFilter("all"),
      );
    if (savedFilter !== "all") add("saved", "Saved only", () => setSavedFilter("all"));
    return entries;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    dateFilter,
    deadlineFilter,
    eventTypeFilter,
    query,
    savedFilter,
    sourceFilter,
    stakeholderFilter,
    topicFilter,
  ]);

  function shareFeed() {
    const params = new URLSearchParams();
    if (query) params.set("q", query);
    if (sourceFilter !== "all") params.set("source", sourceFilter);
    const url = `${window.location.origin}/latest${params.toString() ? `?${params.toString()}` : ""}`;
    void navigator.clipboard?.writeText(url);
    setStatusMessage("Share link copied.");
  }

  const filterControls = (
    <>
      <FilterSelect
        label="Source"
        value={sourceFilter}
        options={toOptions(sourceOptions, "Any source")}
        onChange={resetPaging(setSourceFilter)}
      />
      <FilterSelect
        label="Stakeholder"
        value={stakeholderFilter}
        options={toOptions(stakeholderOptions, "Any stakeholder")}
        onChange={resetPaging(setStakeholderFilter)}
      />
      <FilterSelect
        label="Update type"
        value={eventTypeFilter}
        options={toOptions(eventTypeOptions, "Any type")}
        onChange={resetPaging(setEventTypeFilter)}
      />
      <FilterSelect
        label="Deadline"
        value={deadlineFilter}
        options={toOptions(deadlineTypes, "Any deadline")}
        onChange={resetPaging(setDeadlineFilter)}
      />
      <FilterSelect
        label="Topic"
        value={topicFilter}
        options={topicOptions}
        onChange={resetPaging(setTopicFilter)}
      />
      <FilterSelect
        label="Date"
        value={dateFilter}
        options={DATE_OPTIONS}
        onChange={resetPaging(setDateFilter)}
      />
      <FilterSelect
        label="Sort"
        value={sortMode}
        options={SORT_OPTIONS}
        onChange={setSortMode}
      />
      <FilterSelect
        label="Saved"
        value={savedFilter}
        options={[
          { value: "all", label: "All updates" },
          { value: "saved", label: "Saved only" },
        ]}
        onChange={resetPaging(setSavedFilter)}
      />
    </>
  );

  if (digestStatus.isLoading || eventsQuery.isLoading) {
    return (
      <div className="rv-page">
        <PageHeader eyebrow="Analyst feed" title="Latest regulatory updates" />
        <SkeletonCards count={5} lines={3} label="Loading latest updates" />
      </div>
    );
  }

  if (digestStatus.isError || eventsQuery.isError) {
    return (
      <div className="rv-page">
        <PageHeader eyebrow="Analyst feed" title="Latest regulatory updates" />
        <ErrorState
          title="Unable to load updates"
          body="We couldn't retrieve the regulatory feed."
          error={digestStatus.error ?? eventsQuery.error}
          onRetry={() => {
            digestStatus.refetch();
            void eventsQuery.refetch();
          }}
        />
      </div>
    );
  }

  return (
    <div className="rv-page">
      <PageHeader
        eyebrow="Analyst feed"
        title="Latest regulatory updates"
        description={`${sortedEvents.length} update${sortedEvents.length === 1 ? "" : "s"} matching your filters.`}
        actions={
          <>
            <Button variant="ghost" Icon={Share2} onClick={shareFeed}>
              Share
            </Button>
            <Button
              variant="secondary"
              Icon={Download}
              onClick={() => void downloadLatestExport("csv", token)}
            >
              Export CSV
            </Button>
          </>
        }
      />

      <div className="rv-sticky-toolbar">
        <Toolbar
          ariaLabel="Feed filters"
          search={
            <SearchInput
              label="Search regulatory updates"
              placeholder="Search titles, issuers and summaries"
              value={query}
              onChange={resetPaging(setQuery)}
            />
          }
          filters={
            <>
              <span className="rv-toolbar__desktop-filters">{filterControls}</span>
              <span className="rv-toolbar__mobile-filters">
                <FilterSheet
                  title="Filter updates"
                  activeCount={activeFilters.filter((entry) => entry.key !== "q").length}
                  onClear={clearFilters}
                >
                  {filterControls}
                </FilterSheet>
              </span>
            </>
          }
        />
      </div>

      {activeFilters.length ? (
        <ActiveFilters entries={activeFilters} onClearAll={clearFilters} />
      ) : null}

      {visibleEvents.length ? (
        <>
          <div className="rv-feed">
            {visibleEvents.map((event) => (
              <IntelligenceCard
                key={event.id}
                event={event}
                busy={busyAction === `bookmark-${event.id}`}
                onBookmark={() => void handleBookmark(event)}
                onInspect={() =>
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
                    relationships: eventStakeholders(event).map(
                      (stakeholder) => `Affects ${stakeholder}`,
                    ),
                  })
                }
              />
            ))}
          </div>
          {remaining > 0 ? (
            <div className="rv-feed__more">
              <Button
                variant="secondary"
                Icon={ChevronDown}
                onClick={() => setVisibleCount((value) => value + PAGE_SIZE)}
              >
                Show {Math.min(PAGE_SIZE, remaining)} more
              </Button>
              <span className="rv-meta">
                Showing {visibleEvents.length} of {sortedEvents.length}
              </span>
            </div>
          ) : (
            <p className="rv-meta rv-feed__end">
              You have reached the end of the feed.
            </p>
          )}
        </>
      ) : (
        <EmptyState
          title="No updates match your filters"
          body="Try widening the date range, clearing the stakeholder or topic filter, or searching for a different term."
          Icon={FileSearch}
          action={
            activeFilters.length ? (
              <Button variant="secondary" onClick={clearFilters}>
                Clear filters
              </Button>
            ) : undefined
          }
        />
      )}
    </div>
  );
}
