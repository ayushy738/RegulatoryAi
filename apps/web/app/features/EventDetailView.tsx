import { EmptyState } from "@/app/components/ui/EmptyState";
import { ErrorState } from "@/app/components/ui/ErrorState";
import { LoadingState } from "@/app/components/ui/LoadingState";
import { eventStakeholders, eventSummary, formatDate } from "@/app/workspace/format";
import { useWorkspace } from "@/app/workspace/WorkspaceContext";
import type { DigestEvent } from "@/lib/api";

function MaterialIcon({ children, filled = false }: { children: string; filled?: boolean }) {
  return (
    <span className="material-symbols-outlined" style={filled ? { fontVariationSettings: "'FILL' 1" } : undefined}>
      {children}
    </span>
  );
}

function sourceName(event: DigestEvent) {
  return event.issuing_body ?? "Government source";
}

function consultationStatus(event: DigestEvent) {
  const haystack = `${event.title} ${eventSummary(event)} ${event.topic_tags.join(" ")}`.toLowerCase();
  if (haystack.includes("consultation") || haystack.includes("comment")) return "In Consultation";
  return event.event_type === "CHANGED" ? "Updated" : "Published";
}

function evidenceText(event: DigestEvent) {
  return (
    event.summary?.evidence_quotes
      ?.map((quote, index) => `${index + 1}. ${Object.values(quote).join(" ")}`)
      .filter(Boolean) ?? []
  );
}

export function EventDetailView() {
  const { selectedEvent, handleBookmark, eventStatus } = useWorkspace();
  const event = selectedEvent;
  if (eventStatus.isLoading) {
    return <LoadingState label="Loading regulatory event..." />;
  }
  if (eventStatus.isError) {
    return (
      <ErrorState
        title="Unable to load event"
        error={eventStatus.error}
        onRetry={eventStatus.refetch}
      />
    );
  }
  if (!event) {
    return <EmptyState title="Event not found" body="The selected regulatory event could not be loaded." />;
  }
  const stakeholders = eventStakeholders(event);
  const importantDates = event.summary?.important_dates ?? [];
  const evidence = evidenceText(event);
  const confidence = event.summary?.confidence ?? "medium";

  return (
    <section className="stitch-detail-page">
      <header className="stitch-detail-hero">
        <div className="stitch-detail-kicker">
          <span>{event.event_type === "CHANGED" ? "High Priority" : "Regulatory Update"}</span>
          <span>{documentType(event)}</span>
        </div>
        <h2>{event.title}</h2>
        <div className="stitch-detail-meta-grid">
          <DetailMeta icon="account_balance" label="Source" value={sourceName(event)} />
          <DetailMeta label="Publication Date" value={formatDate(event.issue_date)} />
          <DetailMeta label="Impacted Stakeholders" value={stakeholders.length ? stakeholders.join(", ") : "Not classified"} />
          <DetailMeta label="Status" value={consultationStatus(event)} />
          <DetailMeta label="Next Deadline" value={importantDates[0] ?? "No deadline specified"} />
        </div>
        <div className="stitch-detail-tabs">
          {["Summary", "Obligations", "Timeline", "Stakeholder Analysis", "Source Document"].map((tab) => (
            <button className={tab === "Summary" ? "active" : ""} type="button" key={tab}>
              {tab}
            </button>
          ))}
        </div>
      </header>

      <div className="stitch-detail-grid">
        <main className="stitch-detail-main">
          <section className="stitch-detail-card stitch-summary-card">
            <div className="stitch-card-title">
              <MaterialIcon filled>auto_awesome</MaterialIcon>
              <h3>AI-Generated Intelligence Summary</h3>
            </div>
            <p>{eventSummary(event)}</p>
            <ul className="stitch-check-list">
              <li>
                <MaterialIcon>check_circle</MaterialIcon>
                <span>
                  <strong>Why it matters:</strong>{" "}
                  {event.summary?.why_it_matters || "No impact explanation has been generated for this update yet."}
                </span>
              </li>
              <li>
                <MaterialIcon>check_circle</MaterialIcon>
                <span>
                  <strong>Recommended action:</strong> {event.summary?.action_required ?? "monitor"}
                </span>
              </li>
              <li>
                <MaterialIcon>check_circle</MaterialIcon>
                <span>
                  <strong>Confidence:</strong> {confidence}
                </span>
              </li>
            </ul>
          </section>

          <div className="stitch-risk-grid">
            <section className="stitch-detail-card">
              <h4>Risk Profile</h4>
              <strong>{event.summary?.action_required === "urgent" ? "High Impact expected" : "Monitor impact"}</strong>
              <p>{event.summary?.why_it_matters ?? "No risk narrative available from existing APIs."}</p>
              <a href="/intelligence">View Impact Matrix <MaterialIcon>arrow_forward</MaterialIcon></a>
            </section>
            <section className="stitch-detail-card">
              <h4>Sentiment Analysis</h4>
              <strong>{confidence === "high" ? "Strong signal" : "Needs review"}</strong>
              <p>Market or public sentiment is not returned by the existing event endpoint.</p>
              <span className="stitch-gap-note">Backend gap: no sentiment field.</span>
            </section>
          </div>

          <section className="stitch-detail-card">
            <h4>Citations & Supporting Content</h4>
            {evidence.length ? (
              <div className="stitch-citation-list">
                {evidence.map((item) => (
                  <p key={item}>{item}</p>
                ))}
              </div>
            ) : (
              <EmptyState title="No citations returned" body="The existing event API did not include evidence quotes for this update." />
            )}
          </section>
        </main>

        <aside className="stitch-detail-rail">
          <section className="stitch-detail-card">
            <h4>Upcoming Deadlines</h4>
            <div className="stitch-detail-deadlines">
              {importantDates.map((date, index) => (
                <div key={date}>
                  <MaterialIcon>{index === 0 ? "priority_high" : "event"}</MaterialIcon>
                  <div>
                    <strong>{date}</strong>
                    <p>{index === 0 ? "Next action date" : "Important regulatory date"}</p>
                  </div>
                </div>
              ))}
              {!importantDates.length ? (
                <EmptyState title="No deadline detected" body="No important date was returned for this event." />
              ) : null}
            </div>
          </section>

          <section className="stitch-detail-card">
            <h4>Obligation Readiness</h4>
            <ReadinessBar label="Model Governance" value={confidence === "high" ? 75 : 45} />
            <ReadinessBar label="Reporting Setup" value={event.summary?.action_required === "urgent" ? 30 : 12} />
            <button className="stitch-primary-action" type="button">Run Gap Analysis</button>
          </section>

          <section className="stitch-detail-card">
            <h4>Source Document</h4>
            <p>{sourceName(event)}</p>
            <a className="stitch-source-link" href={event.source_url} target="_blank" rel="noreferrer">
              Open Source <MaterialIcon>open_in_new</MaterialIcon>
            </a>
            <button className="stitch-secondary-action full" type="button" onClick={() => void handleBookmark(event)}>
              <MaterialIcon filled={event.is_bookmarked}>bookmark</MaterialIcon>
              {event.is_bookmarked ? "Saved" : "Save"}
            </button>
          </section>
        </aside>
      </div>
    </section>
  );
}

function documentType(event: DigestEvent) {
  return event.topic_tags[0] ?? event.event_type.replaceAll("_", " ");
}

function DetailMeta({ icon, label, value }: { icon?: string; label: string; value: string }) {
  return (
    <div className="stitch-detail-meta">
      {icon ? <MaterialIcon>{icon}</MaterialIcon> : null}
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function ReadinessBar({ label, value }: { label: string; value: number }) {
  return (
    <div className="stitch-readiness">
      <div>
        <span>{label}</span>
        <strong>{value}%</strong>
      </div>
      <i>
        <b style={{ width: `${value}%` }} />
      </i>
    </div>
  );
}
