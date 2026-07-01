import { useState } from "react";
import { CalendarDays, ExternalLink, List, RefreshCw, Rows3, Search } from "lucide-react";

import { EmptyState } from "@/app/components/ui/EmptyState";
import { ErrorState } from "@/app/components/ui/ErrorState";
import { LoadingState } from "@/app/components/ui/LoadingState";
import { Select } from "@/app/components/ui/Select";
import { clampText, cleanText, formatDate } from "@/app/workspace/format";
import { deadlineTypes, stakeholderOptions } from "@/app/workspace/nav";
import { useWorkspace } from "@/app/workspace/WorkspaceContext";
import type { IntelligenceDeadline } from "@/lib/api";

type DeadlineViewMode = "list" | "timeline" | "calendar";

function severity(deadline: IntelligenceDeadline) {
  const days = deadline.days_remaining;
  if (days !== null && days <= 7) return "critical";
  if (days !== null && days <= 30) return "soon";
  return "monitor";
}

export function DeadlinesView({ embedded = false }: { embedded?: boolean }) {
  const {
    deadlineType,
    setDeadlineType,
    deadlineStakeholder,
    setDeadlineStakeholder,
    activeDeadlines,
    loadIntelligenceData,
    deadlinesStatus,
    setSelectedEvidence,
  } = useWorkspace();
  const [mode, setMode] = useState<DeadlineViewMode>("list");

  return (
    <div className={embedded ? "page-stack embedded" : "page-stack ops-page"}>
      {!embedded ? (
        <section className="ops-page-header">
          <div>
            <span>Deadline Intelligence</span>
            <h1>Deadlines center</h1>
            <p>{activeDeadlines.length} active deadlines with severity, confidence, stakeholders, evidence, and source links.</p>
          </div>
        </section>
      ) : null}

      <section className="toolbar-panel deadline-toolbar">
        <Select label="Deadline Type" value={deadlineType} onChange={setDeadlineType} options={deadlineTypes} />
        <Select label="Stakeholder" value={deadlineStakeholder} onChange={setDeadlineStakeholder} options={stakeholderOptions} />
        <div className="segmented-control" role="group" aria-label="Deadline view mode">
          <button className={mode === "list" ? "active" : ""} type="button" onClick={() => setMode("list")}>
            <List size={15} />
            List
          </button>
          <button className={mode === "timeline" ? "active" : ""} type="button" onClick={() => setMode("timeline")}>
            <Rows3 size={15} />
            Timeline
          </button>
          <button className={mode === "calendar" ? "active" : ""} type="button" onClick={() => setMode("calendar")}>
            <CalendarDays size={15} />
            Calendar
          </button>
        </div>
        <button type="button" onClick={() => void loadIntelligenceData()}>
          <RefreshCw size={16} />
          Refresh
        </button>
      </section>

      {deadlinesStatus.isLoading ? <LoadingState label="Loading deadlines..." /> : null}
      {deadlinesStatus.isError ? (
        <ErrorState title="Unable to load deadlines" error={deadlinesStatus.error} onRetry={deadlinesStatus.refetch} />
      ) : null}
      {!deadlinesStatus.isLoading && !deadlinesStatus.isError ? (
        <>
          {mode === "list" ? <DeadlineList deadlines={activeDeadlines} onEvidence={setSelectedEvidence} /> : null}
          {mode === "timeline" ? <DeadlineTimeline deadlines={activeDeadlines} onEvidence={setSelectedEvidence} /> : null}
          {mode === "calendar" ? <DeadlineCalendar deadlines={activeDeadlines} onEvidence={setSelectedEvidence} /> : null}
        </>
      ) : null}
    </div>
  );
}

function DeadlineList({
  deadlines,
  onEvidence,
}: {
  deadlines: IntelligenceDeadline[];
  onEvidence: ReturnType<typeof useWorkspace>["setSelectedEvidence"];
}) {
  return (
    <section className="deadline-list">
      {deadlines.map((deadline) => (
        <DeadlineCard key={`${deadline.document_id}-${deadline.deadline_type}-${deadline.deadline_date}`} deadline={deadline} onEvidence={onEvidence} />
      ))}
      {!deadlines.length ? <EmptyState title="No active deadlines" body="No future deadlines match the current filters." /> : null}
    </section>
  );
}

function DeadlineTimeline({
  deadlines,
  onEvidence,
}: {
  deadlines: IntelligenceDeadline[];
  onEvidence: ReturnType<typeof useWorkspace>["setSelectedEvidence"];
}) {
  return (
    <section className="ops-panel">
      <div className="timeline-list">
        {deadlines.map((deadline) => (
          <button
            key={`${deadline.document_id}-${deadline.deadline_type}-${deadline.deadline_date}`}
            type="button"
            onClick={() => openDeadlineEvidence(deadline, onEvidence)}
          >
            <span className={severity(deadline)} />
            <strong>{deadline.deadline_type.replaceAll("_", " ")}</strong>
            <p>
              {formatDate(deadline.deadline_date)} | {deadline.days_remaining ?? "--"} days | {deadline.title}
            </p>
          </button>
        ))}
        {!deadlines.length ? <EmptyState title="No timeline entries" body="No active deadlines match the current filters." /> : null}
      </div>
    </section>
  );
}

function DeadlineCalendar({
  deadlines,
  onEvidence,
}: {
  deadlines: IntelligenceDeadline[];
  onEvidence: ReturnType<typeof useWorkspace>["setSelectedEvidence"];
}) {
  return (
    <section className="calendar-grid">
      {deadlines.map((deadline) => (
        <button
          key={`${deadline.document_id}-${deadline.deadline_type}-${deadline.deadline_date}`}
          className={severity(deadline)}
          type="button"
          onClick={() => openDeadlineEvidence(deadline, onEvidence)}
        >
          <span>{formatDate(deadline.deadline_date).replace(/\s\d{4}$/, "")}</span>
          <strong>{deadline.days_remaining ?? "--"} days</strong>
          <p>{deadline.title}</p>
        </button>
      ))}
      {!deadlines.length ? <EmptyState title="No calendar entries" body="No active deadlines match the current filters." /> : null}
    </section>
  );
}

function DeadlineCard({
  deadline,
  onEvidence,
}: {
  deadline: IntelligenceDeadline;
  onEvidence: ReturnType<typeof useWorkspace>["setSelectedEvidence"];
}) {
  return (
    <article className={`deadline-card ${severity(deadline)}`}>
      <div className="deadline-days">
        <strong>{deadline.days_remaining ?? "--"}</strong>
        <span>days</span>
      </div>
      <div>
        <div className="row-wrap">
          <span className="mini-badge">{deadline.issuer ?? "Unknown issuer"}</span>
          <span className="mini-badge green">{deadline.deadline_type.replaceAll("_", " ")}</span>
          <span className={`tag ${severity(deadline)}`}>{severity(deadline)}</span>
          <span className="tag">confidence {Math.round(deadline.confidence * 100)}%</span>
        </div>
        <h3>{cleanText(deadline.title)}</h3>
        <p>{clampText(deadline.evidence, 260, "Deadline detected from regulatory graph extraction.")}</p>
        <div className="row-wrap">
          <strong>{formatDate(deadline.deadline_date)}</strong>
          {deadline.stakeholders_affected.map((item) => (
            <span className="tag" key={item}>
              {item}
            </span>
          ))}
        </div>
      </div>
      <div className="deadline-actions">
        <button type="button" onClick={() => openDeadlineEvidence(deadline, onEvidence)}>
          <Search size={17} />
        </button>
        <a className="icon-link" href={deadline.source_url} target="_blank" rel="noreferrer" aria-label="Open source">
          <ExternalLink size={18} />
        </a>
      </div>
    </article>
  );
}

function openDeadlineEvidence(
  deadline: IntelligenceDeadline,
  onEvidence: ReturnType<typeof useWorkspace>["setSelectedEvidence"],
) {
  onEvidence({
    title: deadline.title,
    issuer: deadline.issuer,
    date: deadline.deadline_date,
    summary: deadline.deadline_type.replaceAll("_", " "),
    evidence: deadline.evidence,
    sourceUrl: deadline.source_url,
    documentId: deadline.document_id,
    relationships: deadline.stakeholders_affected.map((stakeholder) => `Affects ${stakeholder}`),
  });
}
