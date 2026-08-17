"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { Bookmark, CalendarClock, MessageSquareText } from "lucide-react";

import { IntelligenceCard } from "@/app/components/events/IntelligenceCard";
import { Badge } from "@/app/components/ui/Badge";
import { EmptyState } from "@/app/components/ui/EmptyState";
import { ErrorState } from "@/app/components/ui/ErrorState";
import { PageHeader, SectionHeader } from "@/app/components/ui/PageHeader";
import { SkeletonCards } from "@/app/components/ui/Skeleton";
import { SearchInput } from "@/app/components/ui/Toolbar";
import {
  clampText,
  eventStakeholders,
  eventSummary,
  formatShortDate,
} from "@/app/workspace/format";
import { useWorkspace } from "@/app/workspace/WorkspaceContext";

/**
 * Saved is a reading list, not a second dashboard: the same intelligence card
 * as the feed, plus the deadlines and questions attached to what was saved.
 */
export function SavedView() {
  const {
    savedEvents,
    activeDeadlines,
    chatMessages,
    busyAction,
    handleBookmark,
    digestStatus,
    setSelectedEvidence,
  } = useWorkspace();

  const [search, setSearch] = useState("");

  const savedUrls = useMemo(
    () => new Set(savedEvents.map((event) => event.source_url)),
    [savedEvents],
  );
  const savedDeadlines = activeDeadlines.filter((deadline) =>
    savedUrls.has(deadline.source_url),
  );
  const recentQuestions = chatMessages
    .filter((message) => message.role === "user")
    .slice(-6)
    .reverse();

  const filtered = useMemo(() => {
    if (!search) return savedEvents;
    const needle = search.toLowerCase();
    return savedEvents.filter((event) =>
      `${event.title} ${event.issuing_body ?? ""} ${event.topic_tags.join(" ")}`
        .toLowerCase()
        .includes(needle),
    );
  }, [savedEvents, search]);

  if (digestStatus.isLoading) {
    return (
      <div className="rv-page">
        <PageHeader eyebrow="Workbench" title="Saved intelligence" />
        <SkeletonCards count={3} lines={3} label="Loading saved items" />
      </div>
    );
  }

  if (digestStatus.isError) {
    return (
      <div className="rv-page">
        <PageHeader eyebrow="Workbench" title="Saved intelligence" />
        <ErrorState
          title="Unable to load saved items"
          body="We couldn't retrieve your bookmarks."
          error={digestStatus.error}
          onRetry={digestStatus.refetch}
        />
      </div>
    );
  }

  return (
    <div className="rv-page">
      <PageHeader
        eyebrow="Workbench"
        title="Saved intelligence"
        description={`${savedEvents.length} bookmarked update${savedEvents.length === 1 ? "" : "s"}.`}
        actions={
          <Link className="rv-btn rv-btn--secondary" href="/latest">
            Browse feed
          </Link>
        }
      />

      {savedEvents.length ? (
        <div className="rv-saved-layout">
          <div className="rv-saved-main">
            {savedEvents.length > 4 ? (
              <SearchInput
                label="Search saved updates"
                placeholder="Search saved updates"
                value={search}
                onChange={setSearch}
              />
            ) : null}
            {filtered.length ? (
              <div className="rv-feed">
                {filtered.map((event) => (
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
            ) : (
              <EmptyState
                compact
                title="No saved item matches that search"
                body="Clear the search to see everything you have bookmarked."
              />
            )}
          </div>

          <aside className="rv-saved-side">
            <section className="rv-card">
              <SectionHeader
                as="h2"
                title={
                  <>
                    <CalendarClock size={16} aria-hidden /> Deadlines
                  </>
                }
                count={savedDeadlines.length}
              />
              {savedDeadlines.length ? (
                <ul className="rv-mini-list">
                  {savedDeadlines.slice(0, 8).map((deadline) => (
                    <li
                      key={`${deadline.document_id}-${deadline.deadline_type}-${deadline.deadline_date}`}
                    >
                      <a href={deadline.source_url} target="_blank" rel="noreferrer">
                        <span className="rv-cell-primary">
                          {clampText(deadline.title, 70)}
                        </span>
                        <span className="rv-notification__meta">
                          <span>
                            Due {formatShortDate(deadline.deadline_date) ?? "unknown"}
                          </span>
                          {typeof deadline.days_remaining === "number" ? (
                            <Badge tone={deadline.days_remaining <= 7 ? "warning" : "neutral"}>
                              {deadline.days_remaining} days left
                            </Badge>
                          ) : null}
                        </span>
                      </a>
                    </li>
                  ))}
                </ul>
              ) : (
                <EmptyState
                  compact
                  title="No deadlines attached"
                  body="Deadlines from your saved sources appear here."
                />
              )}
            </section>

            <section className="rv-card">
              <SectionHeader
                as="h2"
                title={
                  <>
                    <MessageSquareText size={16} aria-hidden /> Recent questions
                  </>
                }
                actions={
                  <Link className="rv-btn rv-btn--ghost rv-btn--sm" href="/ask">
                    Ask AI
                  </Link>
                }
              />
              {recentQuestions.length ? (
                <ul className="rv-notes">
                  {recentQuestions.map((message, index) => (
                    <li key={`${message.content}-${index}`}>
                      {clampText(message.content, 120)}
                    </li>
                  ))}
                </ul>
              ) : (
                <EmptyState
                  compact
                  title="No questions yet"
                  body="Questions you ask the assistant appear here for quick reuse."
                />
              )}
            </section>
          </aside>
        </div>
      ) : (
        <EmptyState
          title="Nothing saved yet"
          body="Use Save on any update in the feed to keep it here with its related deadlines."
          Icon={Bookmark}
          action={
            <Link className="rv-btn rv-btn--primary" href="/latest">
              Browse latest updates
            </Link>
          }
        />
      )}
    </div>
  );
}
