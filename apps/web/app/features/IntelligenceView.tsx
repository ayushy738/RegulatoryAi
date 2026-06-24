import { CalendarClock, ListChecks, Network, Target, Users } from "lucide-react";

import { EmptyState } from "@/app/components/ui/EmptyState";
import { ErrorState } from "@/app/components/ui/ErrorState";
import { LoadingState } from "@/app/components/ui/LoadingState";
import { MetricCard } from "@/app/components/ui/MetricCard";
import { Panel } from "@/app/components/ui/Panel";
import { formatDate } from "@/app/workspace/format";
import type { IntelligenceTab } from "@/app/workspace/types";
import { useWorkspace } from "@/app/workspace/WorkspaceContext";

import { DeadlinesView } from "./DeadlinesView";

const TABS: Array<[IntelligenceTab, string]> = [
  ["deadlines", "Deadlines"],
  ["obligations", "Obligations"],
  ["stakeholders", "Stakeholders"],
  ["readiness", "Readiness"],
];

export function IntelligenceView() {
  const {
    intelligenceTab,
    setIntelligenceTab,
    obligationGroups,
    stakeholderViews,
    readiness,
    obligationsStatus,
    stakeholdersStatus,
    readinessStatus,
  } = useWorkspace();
  return (
    <div className="page-stack">
      <div className="tab-row">
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
          <div className="stack-list">
            {obligationGroups.map((group) => (
              <div className="intelligence-row" key={group.stakeholder}>
                <h3>{group.stakeholder}</h3>
                {group.obligations.slice(0, 5).map((item, index) => (
                  <p key={`${group.stakeholder}-${index}`}>
                    {item.obligation}{" "}
                    <span>{item.deadline_date ? `Due ${formatDate(item.deadline_date)}` : "No deadline found"}</span>
                  </p>
                ))}
              </div>
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
    </div>
  );
}
