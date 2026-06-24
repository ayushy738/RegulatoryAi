import { EmptyState } from "@/app/components/ui/EmptyState";
import { ErrorState } from "@/app/components/ui/ErrorState";
import { LoadingState } from "@/app/components/ui/LoadingState";
import {
  compactNumber,
  eventStakeholders,
  eventSummary,
  formatDate,
  isConsultation,
  isHighImpact,
} from "@/app/workspace/format";
import { useWorkspace } from "@/app/workspace/WorkspaceContext";
import type { DigestEvent, IntelligenceDeadline } from "@/lib/api";

function MaterialIcon({ children }: { children: string }) {
  return <span className="material-symbols-outlined">{children}</span>;
}

function sourceLabel(event: DigestEvent) {
  return event.issuing_body?.split(/[,|-]/)[0]?.trim() || "Government Source";
}

function topicLabel(event: DigestEvent) {
  return event.topic_tags[0] ?? event.event_type.replaceAll("_", " ");
}

function relativeEventTime(event: DigestEvent) {
  const detected = new Date(event.detected_at);
  if (Number.isNaN(detected.getTime())) return "Updated recently";
  const diffHours = Math.max(1, Math.round((Date.now() - detected.getTime()) / 3_600_000));
  if (diffHours < 24) return `Updated ${diffHours}h ago`;
  const diffDays = Math.round(diffHours / 24);
  return `Updated ${diffDays}d ago`;
}

function deadlineBucket(deadlines: IntelligenceDeadline[], minDays: number, maxDays: number) {
  return deadlines
    .filter((deadline) => {
      const days = deadline.days_remaining;
      return days !== null && days >= minDays && days <= maxDays;
    })
    .slice(0, 3);
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

  if (digestStatus.isLoading) {
    return <LoadingState label="Loading regulatory intelligence..." />;
  }
  if (digestStatus.isError) {
    return (
      <ErrorState
        title="Unable to load dashboard"
        error={digestStatus.error}
        onRetry={digestStatus.refetch}
      />
    );
  }

  const consultations = events.filter(isConsultation).length;
  const highImpact = events.filter(isHighImpact).length;
  const displayName = userEmail ? userEmail.split("@")[0].split(/[._-]/)[0] : "Alex";
  const urgentEvents = events.filter((event) => event.summary?.action_required === "urgent").length;
  const stakeholderCount =
    stakeholderViews.length ||
    new Set(events.flatMap((event) => eventStakeholders(event))).size ||
    highImpact;
  const feedEvents = events.slice(0, 3);
  const thisWeek = deadlineBucket(activeDeadlines, 0, 7);
  const nextWeek = deadlineBucket(activeDeadlines, 8, 14);
  const thisMonth = deadlineBucket(activeDeadlines, 15, 31);
  const stakeholderCards =
    stakeholderViews.length > 0
      ? stakeholderViews.slice(0, 3).map((view, index) => ({
          id: view.stakeholder,
          name: view.stakeholder,
          obligations: view.counts.obligations ?? view.obligations.length,
          deadlines: view.counts.deadlines ?? view.deadlines.length,
          icon: ["wb_sunny", "ev_station", "factory"][index] ?? "diversity_3",
          tone: ["green", "purple", "tertiary"][index] ?? "green",
        }))
      : ["Solar Developers", "EV Infrastructure", "Heavy Industry"].map((name, index) => ({
          id: name,
          name,
          obligations: events.filter((event) => eventStakeholders(event).includes(name)).length,
          deadlines: activeDeadlines.filter((deadline) =>
            deadline.stakeholders_affected.some((stakeholder) =>
              stakeholder.toLowerCase().includes(name.toLowerCase()),
            ),
          ).length,
          icon: ["wb_sunny", "ev_station", "factory"][index],
          tone: ["green", "purple", "tertiary"][index],
        }));

  return (
    <div className="stitch-dashboard">
      <header className="stitch-dashboard__header">
        <h2>Good morning, {displayName}</h2>
        <p>
          Here is your regulatory intelligence summary for {formatDate(digestDate)}.{" "}
          {urgentEvents || highImpact} key updates require your immediate attention.
        </p>
      </header>

      <section className="stitch-kpi-grid" aria-label="Today's Intelligence">
        <StitchKpiCard icon="update" value={events.length} label="New Updates" meta="+12%" tone="primary" />
        <StitchKpiCard
          icon="event_upcoming"
          value={activeDeadlines.length}
          label="Upcoming Deadlines"
          meta={activeDeadlines.length ? "Critical" : "Clear"}
          tone="error"
        />
        <StitchKpiCard
          icon="campaign"
          value={consultations}
          label="Consultations"
          meta={`${Math.min(consultations, 3)} Open`}
          tone="secondary"
        />
        <StitchKpiCard
          icon="diversity_3"
          value={stakeholderCount}
          label="Stakeholder Alerts"
          meta="Updated"
          tone="tertiary"
        />
      </section>

      <div className="stitch-bento-grid">
        <section className="stitch-feed-column">
          <div className="stitch-section-heading">
            <h3>What Changed Today</h3>
            <a href="/latest">
              View All <MaterialIcon>arrow_forward</MaterialIcon>
            </a>
          </div>

          <div className="stitch-news-stack">
            {feedEvents.map((event, index) => (
              <article
                className={`stitch-news-card ${index === 0 ? "stitch-news-card--featured" : ""}`}
                key={event.id}
              >
                <div className="stitch-chip-row">
                  <span className="stitch-chip stitch-chip--neutral">{sourceLabel(event)}</span>
                  <span className={`stitch-chip ${index === 2 ? "stitch-chip--error" : index === 1 ? "stitch-chip--primary" : "stitch-chip--tertiary"}`}>
                    {topicLabel(event)}
                  </span>
                </div>
                <h4>{event.title}</h4>
                <p>{eventSummary(event)}</p>
                <footer>
                  <span>{relativeEventTime(event)}</span>
                  <a href={`/events/${event.id}`}>READ MORE</a>
                </footer>
              </article>
            ))}
            {!events.length ? (
              <EmptyState
                title="No intelligence yet"
                body="Run curated sources to populate the intelligence feed."
              />
            ) : null}
          </div>
        </section>

        <aside className="stitch-side-column">
          <section className="stitch-panel">
            <h3>Upcoming Deadlines</h3>
            <div className="stitch-timeline">
              <DeadlineGroup title="This Week" deadlines={thisWeek} active />
              <DeadlineGroup title="Next Week" deadlines={nextWeek} />
              <DeadlineGroup title="This Month" deadlines={thisMonth} muted />
            </div>
          </section>

          <section className="stitch-panel">
            <div className="stitch-section-heading stitch-section-heading--panel">
              <h3>Stakeholder Impact</h3>
              <MaterialIcon>info</MaterialIcon>
            </div>
            <div className="stitch-stakeholder-stack">
              {stakeholderCards.map((card) => (
                <div className="stitch-stakeholder-card" key={card.id}>
                  <div className={`stitch-stakeholder-icon ${card.tone}`}>
                    <MaterialIcon>{card.icon}</MaterialIcon>
                  </div>
                  <div>
                    <h5>{card.name}</h5>
                    <p>{compactNumber(card.obligations)} Active Obligations</p>
                  </div>
                  <div className="stitch-stakeholder-count">
                    <strong>{String(card.deadlines).padStart(2, "0")}</strong>
                    <span>Deadlines</span>
                  </div>
                </div>
              ))}
            </div>
            <button className="stitch-primary-action" type="button">
              Generate Stakeholder Report
            </button>
          </section>

          <section className="stitch-ai-card">
            <div>
              <h4>AI Insights Ready</h4>
              <p>Our intelligence model has synthesized today's updates for your portfolio.</p>
              <a href="/ask">VIEW SYNTHESIS</a>
            </div>
            <MaterialIcon>auto_awesome</MaterialIcon>
          </section>
        </aside>
      </div>
    </div>
  );
}

function StitchKpiCard({
  icon,
  value,
  label,
  meta,
  tone,
}: {
  icon: string;
  value: number;
  label: string;
  meta: string;
  tone: "primary" | "secondary" | "tertiary" | "error";
}) {
  return (
    <article className="stitch-kpi-card">
      <div>
        <span className={`stitch-kpi-icon ${tone}`}>
          <MaterialIcon>{icon}</MaterialIcon>
        </span>
        <span className="stitch-kpi-meta">{meta}</span>
      </div>
      <strong>{String(value).padStart(2, "0")}</strong>
      <p>{label}</p>
    </article>
  );
}

function DeadlineGroup({
  title,
  deadlines,
  active = false,
  muted = false,
}: {
  title: string;
  deadlines: IntelligenceDeadline[];
  active?: boolean;
  muted?: boolean;
}) {
  return (
    <div className={`stitch-deadline-group ${muted ? "muted" : ""}`}>
      <h5>
        <span>
          <i className={active ? "active" : ""} />
        </span>
        {title}
      </h5>
      <div>
        {deadlines.map((deadline, index) => (
          <a
            className={`stitch-deadline-item ${active ? "active" : ""} ${index === 1 ? "error" : ""}`}
            href={deadline.source_url}
            key={`${deadline.document_id}-${deadline.deadline_type}-${deadline.deadline_date}`}
            rel="noreferrer"
            target="_blank"
          >
            <span>{formatDate(deadline.deadline_date).replace(/\s\d{4}$/, "")}</span>
            <strong>{deadline.title}</strong>
          </a>
        ))}
        {!deadlines.length ? (
          <div className="stitch-deadline-item empty">
            <span>--</span>
            <strong>No deadlines in this window</strong>
          </div>
        ) : null}
      </div>
    </div>
  );
}
