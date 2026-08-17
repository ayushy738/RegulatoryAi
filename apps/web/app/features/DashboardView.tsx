"use client";

import Link from "next/link";
import type { ReactNode } from "react";
import {
  AlertTriangle,
  ArrowRight,
  CalendarClock,
  Gauge,
  ListChecks,
  Network,
  SearchCheck,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";

import { Badge } from "@/app/components/ui/Badge";
import { EmptyState } from "@/app/components/ui/EmptyState";
import { ErrorState } from "@/app/components/ui/ErrorState";
import { PageHeader, SectionHeader } from "@/app/components/ui/PageHeader";
import { SkeletonCards, SkeletonMetrics } from "@/app/components/ui/Skeleton";
import {
  clampText,
  eventStakeholders,
  eventSummary,
  formatShortDate,
  isConsultation,
  isHighImpact,
} from "@/app/workspace/format";
import { useWorkspace } from "@/app/workspace/WorkspaceContext";
import type { DigestEvent, IntelligenceDeadline } from "@/lib/api";

function isTender(event: DigestEvent) {
  const text =
    `${event.title} ${event.topic_tags.join(" ")} ${eventSummary(event)}`.toLowerCase();
  return text.includes("tender") || text.includes("bid") || text.includes("rfp");
}

function isAmendment(event: DigestEvent) {
  const text = `${event.title} ${event.topic_tags.join(" ")} ${event.event_type}`.toLowerCase();
  return (
    text.includes("amend") ||
    text.includes("corrigendum") ||
    event.event_type === "CHANGED"
  );
}

export function DashboardView() {
  const { events, activeDeadlines, digestStatus, userEmail, digestDate } =
    useWorkspace();

  if (digestStatus.isLoading) {
    return (
      <div className="rv-page">
        <PageHeader eyebrow="Daily intelligence" title="Your regulatory briefing" />
        <SkeletonMetrics count={4} />
        <SkeletonCards count={4} lines={3} label="Loading briefing" />
      </div>
    );
  }

  if (digestStatus.isError) {
    return (
      <div className="rv-page">
        <PageHeader eyebrow="Daily intelligence" title="Your regulatory briefing" />
        <ErrorState
          title="Unable to load your briefing"
          body="We couldn't retrieve today's regulatory digest."
          error={digestStatus.error}
          onRetry={digestStatus.refetch}
        />
      </div>
    );
  }

  const displayName = userEmail ? userEmail.split("@")[0].split(/[._-]/)[0] : "analyst";
  const needsAttention = events.filter(
    (event) => event.summary?.action_required === "urgent" || isHighImpact(event),
  );
  const consultations = events.filter(isConsultation);
  const tenders = events.filter(isTender);
  const amendments = events.filter(isAmendment);
  const urgentDeadlines = activeDeadlines.filter(
    (deadline) =>
      typeof deadline.days_remaining === "number" && deadline.days_remaining <= 7,
  );

  return (
    <div className="rv-page">
      <PageHeader
        eyebrow="Daily intelligence"
        title={`Good day, ${displayName}`}
        description={`Digest for ${formatShortDate(digestDate) ?? "today"} · ${events.length} updates tracked.`}
        actions={
          <Link className="rv-btn rv-btn--primary" href="/latest">
            <span>Review feed</span>
            <ArrowRight size={16} aria-hidden />
          </Link>
        }
      />

      <div className="rv-priority-strip">
        <PriorityLink
          href="/latest"
          count={needsAttention.length}
          label="Need attention"
          tone={needsAttention.length ? "danger" : "neutral"}
        />
        <PriorityLink
          href="/intelligence"
          count={activeDeadlines.length}
          label="Active deadlines"
          hint={urgentDeadlines.length ? `${urgentDeadlines.length} within 7 days` : undefined}
          tone={urgentDeadlines.length ? "warning" : "neutral"}
        />
        <PriorityLink href="/latest" count={consultations.length} label="Consultations" />
        <PriorityLink href="/latest" count={amendments.length} label="Amendments" />
      </div>

      <div className="rv-dashboard-grid">
        <DashboardPanel title="Needs attention" Icon={AlertTriangle} href="/latest">
          <EventList
            events={needsAttention.slice(0, 5)}
            empty="No urgent or high-impact updates right now."
          />
        </DashboardPanel>

        <DashboardPanel title="Upcoming deadlines" Icon={CalendarClock} href="/intelligence">
          <DeadlineList deadlines={activeDeadlines.slice(0, 6)} />
        </DashboardPanel>

        <DashboardPanel title="Latest changes" Icon={SearchCheck} href="/latest">
          <EventList events={events.slice(0, 5)} empty="No regulatory updates yet." />
        </DashboardPanel>

        <DashboardPanel title="Consultations" Icon={ListChecks} href="/latest">
          <EventList
            events={consultations.slice(0, 4)}
            empty="No open consultations detected."
          />
        </DashboardPanel>

        <DashboardPanel title="Tenders" Icon={Gauge} href="/latest">
          <EventList events={tenders.slice(0, 4)} empty="No tender activity detected." />
        </DashboardPanel>

        <DashboardPanel title="Amendments" Icon={Network} href="/latest">
          <EventList
            events={amendments.slice(0, 4)}
            empty="No amendments detected in this digest."
          />
        </DashboardPanel>
      </div>
    </div>
  );
}

function PriorityLink({
  href,
  count,
  label,
  hint,
  tone = "neutral",
}: {
  href: string;
  count: number;
  label: string;
  hint?: string;
  tone?: "neutral" | "warning" | "danger";
}) {
  return (
    <Link className={`rv-priority rv-priority--${tone}`} href={href}>
      <strong className="rv-priority__count">{count}</strong>
      <span className="rv-priority__label">{label}</span>
      {hint ? <span className="rv-meta">{hint}</span> : null}
    </Link>
  );
}

function DashboardPanel({
  title,
  Icon,
  href,
  children,
}: {
  title: string;
  Icon: LucideIcon;
  href: string;
  children: ReactNode;
}) {
  return (
    <section className="rv-card">
      <SectionHeader
        as="h2"
        title={
          <>
            <Icon size={16} aria-hidden /> {title}
          </>
        }
        actions={
          <Link className="rv-btn rv-btn--ghost rv-btn--sm" href={href}>
            <span>Open</span>
            <ArrowRight size={14} aria-hidden />
          </Link>
        }
      />
      {children}
    </section>
  );
}

function EventList({ events, empty }: { events: DigestEvent[]; empty: string }) {
  if (!events.length) {
    return <EmptyState compact title="Nothing here" body={empty} />;
  }
  return (
    <ul className="rv-mini-list">
      {events.map((event) => (
        <li key={event.id}>
          <Link href={`/events/${event.id}`}>
            <span className="rv-cell-primary">{clampText(event.title, 90)}</span>
            <span className="rv-notification__meta">
              <span>{event.issuing_body ?? "Unknown issuer"}</span>
              {formatShortDate(event.issue_date ?? event.detected_at) ? (
                <span>{formatShortDate(event.issue_date ?? event.detected_at)}</span>
              ) : null}
              {eventStakeholders(event).length ? (
                <Badge>{eventStakeholders(event)[0]}</Badge>
              ) : null}
            </span>
          </Link>
        </li>
      ))}
    </ul>
  );
}

function DeadlineList({ deadlines }: { deadlines: IntelligenceDeadline[] }) {
  if (!deadlines.length) {
    return (
      <EmptyState
        compact
        title="No active deadlines"
        body="Dated obligations appear here as soon as they are extracted."
      />
    );
  }
  return (
    <ul className="rv-mini-list">
      {deadlines.map((deadline) => {
        const days = deadline.days_remaining;
        return (
          <li
            key={`${deadline.document_id}-${deadline.deadline_type}-${deadline.deadline_date}`}
          >
            <a href={deadline.source_url} target="_blank" rel="noreferrer">
              <span className="rv-cell-primary">{clampText(deadline.title, 90)}</span>
              <span className="rv-notification__meta">
                <span>
                  Due {formatShortDate(deadline.deadline_date) ?? "date not stated"}
                </span>
                {typeof days === "number" ? (
                  <Badge tone={days <= 7 ? "warning" : "neutral"}>
                    {days <= 0 ? "Due today" : `${days} days left`}
                  </Badge>
                ) : null}
              </span>
            </a>
          </li>
        );
      })}
    </ul>
  );
}
