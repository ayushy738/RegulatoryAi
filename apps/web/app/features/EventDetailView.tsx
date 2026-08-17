"use client";

import type { ReactNode } from "react";
import Link from "next/link";
import {
  ArrowLeft,
  Bookmark,
  CalendarClock,
  CheckCircle2,
  ExternalLink,
  Search,
  Share2,
  Users,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";

import { sourceCode } from "@/app/components/events/IntelligenceCard";
import { Badge } from "@/app/components/ui/Badge";
import { Button } from "@/app/components/ui/Button";
import { EmptyState } from "@/app/components/ui/EmptyState";
import { ErrorState } from "@/app/components/ui/ErrorState";
import {
  Fact,
  FactList,
  PageHeader,
  SectionHeader,
} from "@/app/components/ui/PageHeader";
import { SkeletonCards } from "@/app/components/ui/Skeleton";
import {
  cleanText,
  eventStakeholders,
  eventSummary,
  formatShortDate,
} from "@/app/workspace/format";
import { useWorkspace } from "@/app/workspace/WorkspaceContext";
import type { DigestEvent } from "@/lib/api";

function eventEvidence(event: DigestEvent) {
  return (
    event.summary?.evidence_quotes
      ?.map((quote) => Object.values(quote).join(" "))
      .filter(Boolean) ?? []
  );
}

/**
 * Full record for one regulatory event. The obligations panel was removed with
 * the rest of the obligation path; stakeholder impact and deadlines carry the
 * same information in language the reader already understands.
 */
export function EventDetailView() {
  const {
    selectedEvent,
    handleBookmark,
    eventStatus,
    activeDeadlines,
    stakeholderViews,
    busyAction,
    setSelectedEvidence,
    setStatusMessage,
  } = useWorkspace();
  const event = selectedEvent;

  if (eventStatus.isLoading) {
    return (
      <div className="rv-page">
        <SkeletonCards count={3} lines={4} label="Loading regulatory event" />
      </div>
    );
  }

  if (eventStatus.isError) {
    return (
      <div className="rv-page">
        <ErrorState
          title="Unable to load this event"
          body="We couldn't retrieve the regulatory event record."
          error={eventStatus.error}
          onRetry={eventStatus.refetch}
        />
      </div>
    );
  }

  if (!event) {
    return (
      <div className="rv-page">
        <EmptyState
          title="Event not found"
          body="This regulatory event is no longer available, or the link is out of date."
          action={
            <Link className="rv-btn rv-btn--primary" href="/latest">
              Back to latest
            </Link>
          }
        />
      </div>
    );
  }

  const currentEvent = event;
  const stakeholders = eventStakeholders(event);
  const importantDates = event.summary?.important_dates ?? [];
  const evidence = eventEvidence(event);
  const matchingDeadlines = activeDeadlines.filter(
    (deadline) =>
      deadline.source_url === event.source_url || deadline.title === event.title,
  );
  const matchingStakeholders = stakeholderViews.filter((view) =>
    stakeholders.some((stakeholder) =>
      view.stakeholder.toLowerCase().includes(stakeholder.toLowerCase()),
    ),
  );

  /** One entry per calendar date, so "issued/detected/deadline" cannot repeat. */
  const timeline = (() => {
    const seen = new Map<string, string>();
    const push = (label: string, value?: string | null) => {
      const formatted = formatShortDate(value);
      if (!formatted || seen.has(formatted)) return;
      seen.set(formatted, label);
    };
    push("Published", event.issue_date);
    matchingDeadlines.forEach((deadline) =>
      push(deadline.deadline_type.replaceAll("_", " "), deadline.deadline_date),
    );
    push("Detected by Resolven", event.detected_at);
    return Array.from(seen, ([value, label]) => ({ label, value }));
  })();

  function shareEvent() {
    const url = `${window.location.origin}/events/${currentEvent.id}`;
    void navigator.clipboard?.writeText(url);
    setStatusMessage("Event link copied.");
  }

  function openEvidence() {
    setSelectedEvidence({
      title: currentEvent.title,
      issuer: currentEvent.issuing_body,
      date: currentEvent.issue_date,
      summary: eventSummary(currentEvent),
      evidence: evidence.join("\n"),
      sourceUrl: currentEvent.source_url,
      documentId: currentEvent.id,
      relationships: [
        ...stakeholders.map((stakeholder) => `Affects ${stakeholder}`),
        ...matchingDeadlines.map((deadline) => `Deadline ${deadline.deadline_type}`),
      ],
    });
  }

  return (
    <div className="rv-page">
      <Link className="rv-link-button" href="/latest">
        <ArrowLeft size={14} aria-hidden />
        Back to latest
      </Link>

      <PageHeader
        eyebrow={`${sourceCode(event)} · ${event.event_type.replaceAll("_", " ").toLowerCase()}`}
        title={cleanText(event.title)}
        description={
          <>
            {event.issuing_body ?? "Government source"}
            {formatShortDate(event.issue_date)
              ? ` · Published ${formatShortDate(event.issue_date)}`
              : ""}
          </>
        }
        actions={
          <>
            <Button
              variant="secondary"
              Icon={Bookmark}
              loading={busyAction === `bookmark-${event.id}`}
              aria-pressed={event.is_bookmarked}
              onClick={() => void handleBookmark(event)}
            >
              {event.is_bookmarked ? "Saved" : "Save"}
            </Button>
            <Button variant="ghost" Icon={Share2} onClick={shareEvent}>
              Share
            </Button>
            <Button variant="ghost" Icon={Search} onClick={openEvidence}>
              Evidence
            </Button>
            <a
              className="rv-btn rv-btn--primary"
              href={event.source_url}
              target="_blank"
              rel="noreferrer"
            >
              <ExternalLink size={16} aria-hidden />
              <span>Open source</span>
            </a>
          </>
        }
      />

      {event.topic_tags.length || stakeholders.length ? (
        <div className="rv-intel-card__tags">
          {stakeholders.map((stakeholder) => (
            <Badge key={stakeholder} tone="brand">
              {stakeholder}
            </Badge>
          ))}
          {event.topic_tags.slice(0, 8).map((tag) => (
            <Badge key={tag}>{tag}</Badge>
          ))}
        </div>
      ) : null}

      <div className="rv-detail-layout">
        <div className="rv-detail-main">
          <Section title="What changed" Icon={CheckCircle2}>
            <p className="rv-prose">{eventSummary(event)}</p>
            <FactList ariaLabel="Event summary">
              <Fact
                label="Why it matters"
                value={cleanText(event.summary?.why_it_matters, "Not stated")}
              />
              <Fact
                label="Action required"
                value={cleanText(event.summary?.action_required, "Monitor")}
              />
              <Fact
                label="Stakeholders"
                value={stakeholders.length ? stakeholders.join(", ") : "Not classified"}
              />
              <Fact
                label="Confidence"
                value={cleanText(event.summary?.confidence, "medium")}
              />
            </FactList>
          </Section>

          {timeline.length ? (
            <Section title="Key dates" Icon={CalendarClock}>
              <ol className="rv-timeline">
                {timeline.map((entry) => (
                  <li className="rv-timeline__item" key={`${entry.label}-${entry.value}`}>
                    <span className="rv-timeline__marker" aria-hidden />
                    <div className="rv-timeline__body">
                      <span className="rv-cell-primary">{entry.value}</span>
                      <span className="rv-meta">{entry.label}</span>
                    </div>
                  </li>
                ))}
                {importantDates.length ? (
                  <li className="rv-timeline__item">
                    <span className="rv-timeline__marker" aria-hidden />
                    <div className="rv-timeline__body">
                      <span className="rv-cell-primary">Dates cited in the document</span>
                      <span className="rv-meta">{importantDates.join(" · ")}</span>
                    </div>
                  </li>
                ) : null}
              </ol>
            </Section>
          ) : null}

          <Section title="Stakeholder impact" Icon={Users}>
            {matchingStakeholders.length ? (
              <div className="rv-card-list">
                {matchingStakeholders.map((view) => (
                  <article className="rv-card" key={view.stakeholder}>
                    <h3 className="rv-card-title">{view.stakeholder}</h3>
                    <p className="rv-prose">{view.impact_summary}</p>
                    <p className="rv-helper">{view.action_summary}</p>
                  </article>
                ))}
              </div>
            ) : (
              <EmptyState
                compact
                title="No detailed stakeholder profile"
                body="This event carries summary-level stakeholder tags only."
              />
            )}
          </Section>

          {evidence.length ? (
            <Section title="Evidence from the source" Icon={Search}>
              <ul className="rv-notes">
                {evidence.slice(0, 6).map((quote, index) => (
                  <li key={`${quote.slice(0, 24)}-${index}`}>{quote}</li>
                ))}
              </ul>
            </Section>
          ) : null}
        </div>

        <aside className="rv-detail-side">
          <section className="rv-card">
            <SectionHeader as="h2" title="What to do next" />
            <p className="rv-prose">
              {cleanText(
                event.summary?.why_it_matters,
                "Review the source document and confirm whether it affects your filings.",
              )}
            </p>
            {matchingDeadlines.length ? (
              <FactList ariaLabel="Deadlines">
                {matchingDeadlines.slice(0, 3).map((deadline) => (
                  <Fact
                    key={`${deadline.document_id}-${deadline.deadline_type}`}
                    label={deadline.deadline_type.replaceAll("_", " ")}
                    value={formatShortDate(deadline.deadline_date) ?? "Date not stated"}
                  />
                ))}
              </FactList>
            ) : (
              <p className="rv-helper">No dated obligation was extracted for this event.</p>
            )}
            <a
              className="rv-btn rv-btn--secondary rv-btn--block"
              href={event.source_url}
              target="_blank"
              rel="noreferrer"
            >
              <ExternalLink size={15} aria-hidden />
              <span>Read the original</span>
            </a>
          </section>
        </aside>
      </div>
    </div>
  );
}

function Section({
  title,
  Icon,
  action,
  children,
}: {
  title: string;
  Icon: LucideIcon;
  action?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section className="rv-section">
      <SectionHeader
        as="h2"
        title={
          <>
            <Icon size={16} aria-hidden /> {title}
          </>
        }
        actions={action}
      />
      {children}
    </section>
  );
}
