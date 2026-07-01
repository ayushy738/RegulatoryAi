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

import { EmptyState } from "@/app/components/ui/EmptyState";
import { ErrorState } from "@/app/components/ui/ErrorState";
import { LoadingState } from "@/app/components/ui/LoadingState";
import {
  clampText,
  eventStakeholders,
  eventSummary,
  formatDate,
  isConsultation,
  isHighImpact,
} from "@/app/workspace/format";
import { useWorkspace } from "@/app/workspace/WorkspaceContext";
import type { DigestEvent, IntelligenceDeadline } from "@/lib/api";

function eventHref(event: DigestEvent) {
  return `/events/${event.id}`;
}

function isTender(event: DigestEvent) {
  const text = `${event.title} ${event.topic_tags.join(" ")} ${eventSummary(event)}`.toLowerCase();
  return text.includes("tender") || text.includes("bid") || text.includes("rfp");
}

function isAmendment(event: DigestEvent) {
  const text = `${event.title} ${event.topic_tags.join(" ")} ${event.event_type}`.toLowerCase();
  return text.includes("amend") || text.includes("corrigendum") || event.event_type === "CHANGED";
}

export function DashboardView() {
  const {
    events,
    activeDeadlines,
    stakeholderViews,
    digestStatus,
    userEmail,
    digestDate,
  } = useWorkspace();

  if (digestStatus.isLoading) return <LoadingState label="Loading regulatory intelligence..." />;
  if (digestStatus.isError) {
    return <ErrorState title="Unable to load dashboard" error={digestStatus.error} onRetry={digestStatus.refetch} />;
  }

  const displayName = userEmail ? userEmail.split("@")[0].split(/[._-]/)[0] : "analyst";
  const needsAttention = events.filter(
    (event) => event.summary?.action_required === "urgent" || isHighImpact(event),
  );
  const consultations = events.filter(isConsultation);
  const tenders = events.filter(isTender);
  const amendments = events.filter(isAmendment);
  const stakeholderCount =
    stakeholderViews.length || new Set(events.flatMap((event) => eventStakeholders(event))).size;

  return (
    <div className="ops-dashboard ops-page premium-dashboard">
      <section className="ops-page-header premium-page-header">
        <div>
          <span>Daily Intelligence</span>
          <h1>Good morning, {displayName}</h1>
          <p>
            Digest {formatDate(digestDate)} | {events.length} regulatory updates | {activeDeadlines.length} active
            deadlines | {stakeholderCount} stakeholder groups.
          </p>
        </div>
        <Link className="stitch-secondary-action" href="/latest">
          Review feed
          <ArrowRight size={16} />
        </Link>
      </section>

      <section className="dashboard-priority-strip" aria-label="Dashboard priorities">
        <Link href="/latest">
          <strong>{needsAttention.length}</strong>
          <span>Need attention</span>
        </Link>
        <Link href="/intelligence">
          <strong>{activeDeadlines.length}</strong>
          <span>Upcoming deadlines</span>
        </Link>
        <Link href="/latest">
          <strong>{consultations.length}</strong>
          <span>Consultations</span>
        </Link>
        <Link href="/latest">
          <strong>{amendments.length}</strong>
          <span>Amendments</span>
        </Link>
      </section>

      <div className="ops-dashboard-grid premium-dashboard-grid">
        <DashboardPanel title="Needs Attention" icon={AlertTriangle} href="/latest">
          <EventList events={needsAttention.slice(0, 5)} empty="No urgent or high-impact updates." />
        </DashboardPanel>

        <DashboardPanel title="Latest Regulatory Changes" icon={SearchCheck} href="/latest">
          <EventList events={events.slice(0, 5)} empty="No regulatory updates returned." />
        </DashboardPanel>

        <DashboardPanel title="Upcoming Deadlines" icon={CalendarClock} href="/intelligence">
          <DeadlineList deadlines={activeDeadlines.slice(0, 6)} />
        </DashboardPanel>

        <DashboardPanel title="Recent Consultations" icon={ListChecks} href="/latest">
          <EventList events={consultations.slice(0, 4)} empty="No consultations detected in the current digest." />
        </DashboardPanel>

        <DashboardPanel title="Recent Tenders" icon={Gauge} href="/latest">
          <EventList events={tenders.slice(0, 4)} empty="No tender updates detected in the current digest." />
        </DashboardPanel>

        <DashboardPanel title="Recent Amendments" icon={Network} href="/latest">
          <EventList events={amendments.slice(0, 4)} empty="No amendments detected in the current digest." />
        </DashboardPanel>
      </div>
    </div>
  );
}

function DashboardPanel({
  title,
  icon: Icon,
  href,
  children,
}: {
  title: string;
  icon: LucideIcon;
  href: string;
  children: ReactNode;
}) {
  return (
    <section className="ops-panel">
      <header>
        <h2>
          <Icon size={18} />
          {title}
        </h2>
        <Link href={href}>
          Open
          <ArrowRight size={15} />
        </Link>
      </header>
      {children}
    </section>
  );
}

function EventList({ events, empty }: { events: DigestEvent[]; empty: string }) {
  if (!events.length) return <EmptyState title="Clear" body={empty} />;
  return (
    <div className="ops-mini-list">
      {events.map((event) => (
        <Link key={event.id} href={eventHref(event)}>
          <strong>{event.title}</strong>
          <span>{event.issuing_body ?? "Unknown issuer"} | {formatDate(event.issue_date)}</span>
          <p>{clampText(eventSummary(event), 150)}</p>
        </Link>
      ))}
    </div>
  );
}

function DeadlineList({ deadlines }: { deadlines: IntelligenceDeadline[] }) {
  if (!deadlines.length) {
    return <EmptyState title="No active deadlines" body="No future deadlines are returned for the current filters." />;
  }
  return (
    <div className="ops-mini-list">
      {deadlines.map((deadline) => (
        <a
          key={`${deadline.document_id}-${deadline.deadline_type}-${deadline.deadline_date}`}
          href={deadline.source_url}
          target="_blank"
          rel="noreferrer"
        >
          <strong>{deadline.title}</strong>
          <span>
            {deadline.days_remaining ?? "--"} days | {formatDate(deadline.deadline_date)}
          </span>
          <p>{clampText(deadline.evidence, 140, "Deadline extracted from intelligence APIs.")}</p>
        </a>
      ))}
    </div>
  );
}
