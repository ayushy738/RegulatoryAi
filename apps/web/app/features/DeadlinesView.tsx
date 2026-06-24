import { ExternalLink, RefreshCw } from "lucide-react";

import { EmptyState } from "@/app/components/ui/EmptyState";
import { ErrorState } from "@/app/components/ui/ErrorState";
import { LoadingState } from "@/app/components/ui/LoadingState";
import { Select } from "@/app/components/ui/Select";
import { formatDate } from "@/app/workspace/format";
import { deadlineTypes, stakeholderOptions } from "@/app/workspace/nav";
import { useWorkspace } from "@/app/workspace/WorkspaceContext";

export function DeadlinesView({ embedded = false }: { embedded?: boolean }) {
  const {
    deadlineType,
    setDeadlineType,
    deadlineStakeholder,
    setDeadlineStakeholder,
    activeDeadlines,
    loadIntelligenceData,
    deadlinesStatus,
  } = useWorkspace();
  return (
    <div className={embedded ? "page-stack embedded" : "page-stack"}>
      <section className="toolbar-panel">
        <Select label="Deadline Type" value={deadlineType} onChange={setDeadlineType} options={deadlineTypes} />
        <Select label="Stakeholder" value={deadlineStakeholder} onChange={setDeadlineStakeholder} options={stakeholderOptions} />
        <button type="button" onClick={() => void loadIntelligenceData()}>
          <RefreshCw size={16} /> Refresh
        </button>
      </section>
      {deadlinesStatus.isLoading ? <LoadingState label="Loading deadlines..." /> : null}
      {deadlinesStatus.isError ? (
        <ErrorState
          title="Unable to load deadlines"
          error={deadlinesStatus.error}
          onRetry={deadlinesStatus.refetch}
        />
      ) : null}
      {!deadlinesStatus.isLoading && !deadlinesStatus.isError ? (
      <section className="deadline-list">
        {activeDeadlines.map((deadline) => (
          <div
            className="deadline-card"
            key={`${deadline.document_id}-${deadline.deadline_type}-${deadline.deadline_date}`}
          >
            <div className="deadline-days">
              <strong>{deadline.days_remaining ?? "--"}</strong>
              <span>days</span>
            </div>
            <div>
              <div className="row-wrap">
                <span className="mini-badge">{deadline.issuer ?? "Unknown issuer"}</span>
                <span className="mini-badge green">{deadline.deadline_type.replaceAll("_", " ")}</span>
              </div>
              <h3>{deadline.title}</h3>
              <p>{deadline.evidence ?? "Deadline detected from regulatory graph extraction."}</p>
              <div className="row-wrap">
                <strong>{formatDate(deadline.deadline_date)}</strong>
                {deadline.stakeholders_affected.map((item) => (
                  <span className="tag" key={item}>
                    {item}
                  </span>
                ))}
              </div>
            </div>
            <a className="icon-link" href={deadline.source_url} target="_blank" rel="noreferrer">
              <ExternalLink size={18} />
            </a>
          </div>
        ))}
        {!activeDeadlines.length ? (
          <EmptyState title="No active deadlines" body="No future deadlines match the current filters." />
        ) : null}
      </section>
      ) : null}
    </div>
  );
}
