import { useMemo } from "react";
import type { ReactNode } from "react";
import Link from "next/link";
import {
  ArrowRight,
  Bookmark,
  CalendarClock,
  CheckCircle2,
  ExternalLink,
  FileText,
  ListChecks,
  Search,
  Share2,
  Users,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";

import { EmptyState } from "@/app/components/ui/EmptyState";
import { ErrorState } from "@/app/components/ui/ErrorState";
import { LoadingState } from "@/app/components/ui/LoadingState";
import { clampText, cleanText, eventStakeholders, eventSummary, formatDate } from "@/app/workspace/format";
import { useWorkspace } from "@/app/workspace/WorkspaceContext";
import type { DigestEvent } from "@/lib/api";

function sourceName(event: DigestEvent) {
  return event.issuing_body ?? "Government source";
}

function eventEvidence(event: DigestEvent) {
  return (
    event.summary?.evidence_quotes
      ?.map((quote) => Object.values(quote).join(" "))
      .filter(Boolean) ?? []
  );
}

export function EventDetailView() {
  const {
    selectedEvent,
    handleBookmark,
    eventStatus,
    activeDeadlines,
    obligationGroups,
    stakeholderViews,
    adminDocs,
    setSelectedEvidence,
    setStatusMessage,
  } = useWorkspace();
  const event = selectedEvent;

  const matchedDocs = useMemo(() => {
    if (!event) return [];
    return adminDocs.filter(
      (doc) =>
        doc.source_url === event.source_url ||
        doc.title.toLowerCase() === event.title.toLowerCase() ||
        doc.title.toLowerCase().includes(event.title.toLowerCase().slice(0, 48)),
    );
  }, [adminDocs, event]);

  if (eventStatus.isLoading) return <LoadingState label="Loading regulatory event..." />;
  if (eventStatus.isError) {
    return <ErrorState title="Unable to load event" error={eventStatus.error} onRetry={eventStatus.refetch} />;
  }
  if (!event) {
    return <EmptyState title="Event not found" body="The selected regulatory event could not be loaded." />;
  }

  const currentEvent = event;
  const stakeholders = eventStakeholders(event);
  const importantDates = event.summary?.important_dates ?? [];
  const evidence = eventEvidence(event);
  const confidence = event.summary?.confidence ?? "medium";
  const matchingDeadlines = activeDeadlines.filter(
    (deadline) => deadline.source_url === event.source_url || deadline.title === event.title,
  );
  const matchingObligations = obligationGroups.flatMap((group) =>
    group.obligations.filter(
      (item) =>
        item.source_url === event.source_url ||
        item.title === event.title ||
        stakeholders.some((stakeholder) => item.stakeholder.toLowerCase().includes(stakeholder.toLowerCase())),
    ),
  );
  const matchingStakeholders = stakeholderViews.filter((view) =>
    stakeholders.some((stakeholder) => view.stakeholder.toLowerCase().includes(stakeholder.toLowerCase())),
  );

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
      documentId: matchedDocs[0]?.id ?? currentEvent.id,
      family: matchedDocs[0]?.family_title,
      version: matchedDocs[0]?.latest_version_id,
      relationships: [
        ...stakeholders.map((stakeholder) => `Affects ${stakeholder}`),
        ...matchingDeadlines.map((deadline) => `Deadline ${deadline.deadline_type}`),
      ],
    });
  }

  return (
    <section className="ops-page detail-page premium-detail-page">
      <header className="event-detail-hero">
        <div className="event-detail-kicker">
          <span>{sourceName(event)}</span>
          <span>{event.event_type.replaceAll("_", " ")}</span>
          <span>Issued {formatDate(event.issue_date)}</span>
        </div>
        <h1>{cleanText(event.title)}</h1>
        <p>{clampText(eventSummary(event), 320)}</p>
        <div className="event-detail-tags">
          {event.topic_tags.slice(0, 8).map((tag) => (
            <span key={tag}>{tag}</span>
          ))}
          <span>Confidence {confidence}</span>
          <span>Action {event.summary?.action_required ?? "monitor"}</span>
        </div>
        <div className="event-detail-actions">
          <button type="button" onClick={() => void handleBookmark(event)}>
            <Bookmark size={16} fill={event.is_bookmarked ? "currentColor" : "none"} />
            {event.is_bookmarked ? "Saved" : "Save"}
          </button>
          <a href={event.source_url} target="_blank" rel="noreferrer">
            <ExternalLink size={16} />
            Open Source
          </a>
          <button type="button" onClick={shareEvent}>
            <Share2 size={16} />
            Share
          </button>
          <button type="button" onClick={openEvidence}>
            <Search size={16} />
            Evidence
          </button>
        </div>
      </header>

      <div className="event-detail-layout">
        <main className="event-detail-main">
          <Section title="Summary" icon={CheckCircle2}>
            <p className="lead-copy">{eventSummary(event)}</p>
            <div className="ops-summary-grid compact-facts">
              <Fact label="Why it matters" value={event.summary?.why_it_matters} />
              <Fact label="Next deadline" value={importantDates[0] ?? matchingDeadlines[0]?.raw_date ?? "No deadline specified"} />
              <Fact label="Affected stakeholders" value={stakeholders.length ? stakeholders.join(", ") : "Not classified"} />
              <Fact label="Source" value={sourceName(event)} />
            </div>
          </Section>

          <Section title="Timeline" icon={CalendarClock}>
            <div className="timeline-list premium-timeline">
              <TimelineItem label="Issue date" value={formatDate(event.issue_date)} />
              <TimelineItem label="Detected by Resolven" value={formatDate(event.detected_at)} />
              {importantDates.map((date) => (
                <TimelineItem key={date} label="Important date" value={date} />
              ))}
              {matchingDeadlines.map((deadline) => (
                <TimelineItem
                  key={`${deadline.document_id}-${deadline.deadline_type}`}
                  label={deadline.deadline_type.replaceAll("_", " ")}
                  value={formatDate(deadline.deadline_date)}
                />
              ))}
            </div>
          </Section>

          <Section title="Obligations" icon={ListChecks} action={<Link href="/intelligence">All obligations <ArrowRight size={15} /></Link>}>
            <div className="ops-mini-list obligation-list">
              {matchingObligations.map((item, index) => (
                <button
                  key={`${item.document_id}-${index}`}
                  type="button"
                  onClick={() =>
                    setSelectedEvidence({
                      title: item.title,
                      issuer: item.issuer,
                      date: item.deadline_date,
                      summary: item.obligation,
                      evidence: item.evidence,
                      sourceUrl: item.source_url,
                      documentId: item.document_id,
                      relationships: [`Stakeholder: ${item.stakeholder}`, `Deadline: ${item.deadline_type ?? "none"}`],
                    })
                  }
                >
                  <strong>{item.obligation}</strong>
                  <span>{item.stakeholder} | {item.deadline_date ? formatDate(item.deadline_date) : "No deadline"}</span>
                </button>
              ))}
              {!matchingObligations.length ? (
                <EmptyState title="No matched obligations" body="No obligation row matched this event from current intelligence APIs." />
              ) : null}
            </div>
          </Section>

          <Section title="Stakeholders" icon={Users}>
            <div className="stakeholder-grid premium-stakeholder-grid">
              {matchingStakeholders.map((view) => (
                <article className="intelligence-row" key={view.stakeholder}>
                  <h3>{view.stakeholder}</h3>
                  <p>{clampText(view.impact_summary, 280)}</p>
                  <p>{clampText(view.action_summary, 220)}</p>
                </article>
              ))}
              {!matchingStakeholders.length ? (
                <EmptyState title="No matched stakeholder profile" body="This event has summary-level stakeholder tags only." />
              ) : null}
            </div>
          </Section>

          {matchedDocs.length ? (
            <Section title="Documents" icon={FileText}>
              <div className="ops-mini-list">
                {matchedDocs.map((doc) => (
                  <button
                    type="button"
                    key={doc.id}
                    onClick={() =>
                      setSelectedEvidence({
                        title: doc.title,
                        issuer: doc.issuing_body,
                        date: doc.issue_date,
                        sourceUrl: doc.source_url,
                        family: doc.family_title,
                        version: doc.latest_version_id,
                        documentId: doc.id,
                        evidence: doc.source_url,
                      })
                    }
                  >
                    <strong>{doc.title}</strong>
                    <span>{doc.source_code ?? "unknown"} | {doc.doc_type ?? "unknown"}</span>
                  </button>
                ))}
              </div>
            </Section>
          ) : null}
        </main>

        <aside className="event-detail-side">
          <section className="ops-panel next-action-panel">
            <span>What to do next</span>
            <strong>{importantDates[0] ?? matchingDeadlines[0]?.raw_date ?? "Review source document"}</strong>
            <p>{clampText(event.summary?.why_it_matters, 220, "No action rationale returned for this event.")}</p>
          </section>
        </aside>
      </div>
    </section>
  );
}

function Section({
  title,
  icon: Icon,
  action,
  children,
}: {
  title: string;
  icon: LucideIcon;
  action?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section className="ops-panel event-section">
      <header>
        <h2>
          <Icon size={18} />
          {title}
        </h2>
        {action}
      </header>
      {children}
    </section>
  );
}

function Fact({ label, value }: { label: string; value?: string | null }) {
  return (
    <div className="detail-fact">
      <span>{label}</span>
      <strong>{cleanText(value, "Not available")}</strong>
    </div>
  );
}

function TimelineItem({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <span />
      <strong>{label}</strong>
      <p>{value}</p>
    </div>
  );
}
