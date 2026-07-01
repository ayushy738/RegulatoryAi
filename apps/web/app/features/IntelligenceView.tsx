import { CalendarClock, History, ListChecks, Network, Search, Target, Users } from "lucide-react";

import { EmptyState } from "@/app/components/ui/EmptyState";
import { ErrorState } from "@/app/components/ui/ErrorState";
import { LoadingState } from "@/app/components/ui/LoadingState";
import { MetricCard } from "@/app/components/ui/MetricCard";
import { Panel } from "@/app/components/ui/Panel";
import { clampText, formatDate } from "@/app/workspace/format";
import type { IntelligenceTab } from "@/app/workspace/types";
import { useWorkspace } from "@/app/workspace/WorkspaceContext";

import { DeadlinesView } from "./DeadlinesView";

const TABS: Array<[IntelligenceTab, string]> = [
  ["deadlines", "Deadlines"],
  ["obligations", "Obligations"],
  ["stakeholders", "Stakeholders"],
  ["readiness", "Readiness"],
  ["timeline", "Timeline"],
];

export function IntelligenceView() {
  const {
    intelligenceTab,
    setIntelligenceTab,
    obligationGroups,
    stakeholderViews,
    readiness,
    activeDeadlines,
    obligationsStatus,
    stakeholdersStatus,
    readinessStatus,
    setSelectedEvidence,
  } = useWorkspace();
  return (
    <div className="page-stack ops-page intelligence-workspace">
      <section className="ops-page-header premium-page-header">
        <div>
          <span>Regulatory Intelligence</span>
          <h1>Obligations, timelines, and stakeholder impact</h1>
          <p>Review extracted duties, active deadline risk, and evidence-backed stakeholder context.</p>
        </div>
      </section>

      <div className="tab-row premium-tab-row">
        {TABS.map(([key, label]) => (
          <button
            key={key}
            type="button"
            className={intelligenceTab === key ? "active" : ""}
            onClick={() => setIntelligenceTab(key)}
          >
            {label}
          </button>
        ))}
      </div>
      {intelligenceTab === "deadlines" ? <DeadlinesView embedded /> : null}
      {intelligenceTab === "obligations" && obligationsStatus.isLoading ? (
        <LoadingState label="Loading obligations..." />
      ) : null}
      {intelligenceTab === "obligations" && obligationsStatus.isError ? (
        <ErrorState
          title="Unable to load obligations"
          error={obligationsStatus.error}
          onRetry={obligationsStatus.refetch}
        />
      ) : null}
      {intelligenceTab === "obligations" && !obligationsStatus.isLoading && !obligationsStatus.isError ? (
        <Panel title="Stakeholder Obligations" icon={ListChecks}>
          <div className="stack-list obligation-group-list">
            {obligationGroups.map((group) => (
              <section className="intelligence-row obligation-group" key={group.stakeholder}>
                <div className="obligation-group-header">
                  <h3>{group.stakeholder}</h3>
                  <span>{group.obligations.length} obligations</span>
                </div>
                {group.obligations.slice(0, 5).map((item, index) => (
                  <button
                    className="plain-row-button obligation-row"
                    type="button"
                    key={`${group.stakeholder}-${index}`}
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
                    <span className="obligation-row-main">
                      <strong>{item.obligation}</strong>
                      <small>{clampText(item.evidence, 180, "Open evidence to inspect the supporting source text.")}</small>
                    </span>
                    <span className="obligation-row-meta">
                      <b>{item.confidence}%</b>
                      {item.deadline_date ? `Due ${formatDate(item.deadline_date)}` : "No deadline"}
                    </span>
                  </button>
                ))}
              </section>
            ))}
            {!obligationGroups.length ? (
              <EmptyState
                title="No obligations extracted"
                body="Graph extraction has not produced obligation rows yet."
              />
            ) : null}
          </div>
        </Panel>
      ) : null}
      {intelligenceTab === "stakeholders" && stakeholdersStatus.isLoading ? (
        <LoadingState label="Loading stakeholder intelligence..." />
      ) : null}
      {intelligenceTab === "stakeholders" && stakeholdersStatus.isError ? (
        <ErrorState
          title="Unable to load stakeholder intelligence"
          error={stakeholdersStatus.error}
          onRetry={stakeholdersStatus.refetch}
        />
      ) : null}
      {intelligenceTab === "stakeholders" && !stakeholdersStatus.isLoading && !stakeholdersStatus.isError ? (
        <section className="stakeholder-grid">
          {stakeholderViews.map((view) => (
            <Panel key={view.stakeholder} title={view.stakeholder} icon={Users}>
              <p className="lead-copy">{view.impact_summary}</p>
              <div className="mini-grid">
                <span>{view.counts.regulations ?? 0} regulations</span>
                <span>{view.counts.obligations ?? 0} obligations</span>
                <span>{view.counts.deadlines ?? 0} deadlines</span>
                <span>{view.counts.tenders ?? 0} tenders</span>
              </div>
              <p>{view.action_summary}</p>
              <div className="row-wrap">
                {view.obligations.slice(0, 3).map((item) => (
                  <button
                    className="tag-button"
                    type="button"
                    key={`${item.document_id}-${item.obligation}`}
                    onClick={() =>
                      setSelectedEvidence({
                        title: item.title,
                        issuer: item.issuer,
                        date: item.deadline_date,
                        summary: item.obligation,
                        evidence: item.evidence,
                        sourceUrl: item.source_url,
                        documentId: item.document_id,
                        relationships: [`Stakeholder: ${item.stakeholder}`],
                      })
                    }
                  >
                    <Search size={13} />
                    obligation
                  </button>
                ))}
              </div>
            </Panel>
          ))}
          {!stakeholderViews.length ? (
            <EmptyState
              title="No stakeholder graph yet"
              body="Run accepted documents through graph extraction to populate this view."
            />
          ) : null}
        </section>
      ) : null}
      {intelligenceTab === "readiness" && readinessStatus.isLoading ? (
        <LoadingState label="Loading readiness report..." />
      ) : null}
      {intelligenceTab === "readiness" && readinessStatus.isError ? (
        <ErrorState
          title="Unable to load readiness report"
          error={readinessStatus.error}
          onRetry={readinessStatus.refetch}
        />
      ) : null}
      {intelligenceTab === "readiness" && !readinessStatus.isLoading && !readinessStatus.isError ? (
        <Panel title="Regulatory Readiness" icon={Target}>
          <div className="readiness-grid">
            <MetricCard title="Active Deadlines" value={readiness?.active_deadlines.length ?? 0} Icon={CalendarClock} tone="green" />
            <MetricCard title="Obligation Groups" value={readiness?.stakeholder_obligations.length ?? 0} Icon={ListChecks} tone="purple" />
            <MetricCard title="Regulatory Impacts" value={readiness?.regulatory_impacts.length ?? 0} Icon={Network} tone="amber" />
          </div>
          {(readiness?.notes ?? []).map((note) => (
            <p className="note-line" key={note}>
              {note}
            </p>
          ))}
        </Panel>
      ) : null}
      {intelligenceTab === "timeline" ? (
        <Panel title="Regulatory Timeline" icon={History}>
          <div className="timeline-list premium-timeline intelligence-timeline">
            {activeDeadlines.map((deadline) => (
              <button
                type="button"
                className="timeline-deadline-row"
                key={`${deadline.document_id}-${deadline.deadline_type}-${deadline.deadline_date}`}
                onClick={() =>
                  setSelectedEvidence({
                    title: deadline.title,
                    issuer: deadline.issuer,
                    date: deadline.deadline_date,
                    summary: deadline.deadline_type.replaceAll("_", " "),
                    evidence: deadline.evidence,
                    sourceUrl: deadline.source_url,
                    documentId: deadline.document_id,
                    relationships: deadline.stakeholders_affected.map((stakeholder) => `Affects ${stakeholder}`),
                  })
                }
              >
                <span />
                <strong>{deadline.deadline_type.replaceAll("_", " ")}</strong>
                <p>
                  {formatDate(deadline.deadline_date)} | {deadline.days_remaining ?? "--"} days |{" "}
                  {clampText(deadline.title, 120)}
                </p>
                <small>{deadline.stakeholders_affected.slice(0, 3).join(", ") || "Stakeholder not classified"}</small>
              </button>
            ))}
            {!activeDeadlines.length ? (
              <EmptyState title="No timeline rows" body="No active deadlines are available for the timeline." />
            ) : null}
          </div>
        </Panel>
      ) : null}
    </div>
  );
}
