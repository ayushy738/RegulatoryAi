"use client";

import { CalendarClock, Network, Search, Users } from "lucide-react";

import { Badge } from "@/app/components/ui/Badge";
import { EmptyState } from "@/app/components/ui/EmptyState";
import { ErrorState } from "@/app/components/ui/ErrorState";
import { Fact, FactList, PageHeader } from "@/app/components/ui/PageHeader";
import { SkeletonCards } from "@/app/components/ui/Skeleton";
import { clampText, formatShortDate } from "@/app/workspace/format";
import type { IntelligenceTab } from "@/app/workspace/types";
import { useWorkspace } from "@/app/workspace/WorkspaceContext";

import { DeadlinesView } from "./DeadlinesView";

/**
 * Obligations are intentionally not a tab. They remain available as supporting
 * evidence inside a stakeholder, which is how people actually ask the question
 * ("what does this mean for DISCOMs?"), and removing the standalone path also
 * removes the navigation loop it created.
 */
const TABS: Array<[IntelligenceTab, string]> = [
  ["deadlines", "Deadlines"],
  ["stakeholders", "Stakeholders"],
  ["readiness", "Readiness"],
  ["timeline", "Timeline"],
];

export function IntelligenceView() {
  const {
    intelligenceTab,
    setIntelligenceTab,
    stakeholderViews,
    readiness,
    activeDeadlines,
    stakeholdersStatus,
    readinessStatus,
    setSelectedEvidence,
  } = useWorkspace();

  return (
    <div className="rv-page">
      <PageHeader
        eyebrow="Regulatory intelligence"
        title="Deadlines, stakeholders and readiness"
        description="Extracted duties, active deadline risk and evidence-backed stakeholder context."
      />

      <div className="rv-tabs" role="tablist" aria-label="Intelligence views">
        {TABS.map(([key, label]) => (
          <button
            key={key}
            type="button"
            role="tab"
            className="rv-tab"
            aria-selected={intelligenceTab === key}
            onClick={() => setIntelligenceTab(key)}
          >
            {label}
          </button>
        ))}
      </div>

      {intelligenceTab === "deadlines" ? <DeadlinesView embedded /> : null}

      {intelligenceTab === "stakeholders" ? (
        stakeholdersStatus.isLoading ? (
          <SkeletonCards count={4} lines={3} label="Loading stakeholder intelligence" />
        ) : stakeholdersStatus.isError ? (
          <ErrorState
            title="Unable to load stakeholder intelligence"
            body="The stakeholder graph could not be retrieved."
            error={stakeholdersStatus.error}
            onRetry={stakeholdersStatus.refetch}
          />
        ) : stakeholderViews.length ? (
          <div className="rv-quick-links">
            {stakeholderViews.map((view) => (
              <article className="rv-card" key={view.stakeholder}>
                <div className="rv-card__header">
                  <h2 className="rv-card-title">
                    <Users size={15} aria-hidden /> {view.stakeholder}
                  </h2>
                  <Badge>{view.counts.deadlines ?? 0} deadlines</Badge>
                </div>
                <p className="rv-page-subtitle">{view.impact_summary}</p>
                <FactList ariaLabel={`${view.stakeholder} exposure`}>
                  <Fact label="Regulations" value={view.counts.regulations ?? 0} />
                  <Fact label="Obligations" value={view.counts.obligations ?? 0} />
                  <Fact label="Tenders" value={view.counts.tenders ?? 0} />
                </FactList>
                <p className="rv-helper">{view.action_summary}</p>
                {view.obligations.length ? (
                  <div className="rv-btn-group">
                    {view.obligations.slice(0, 3).map((item) => (
                      <button
                        className="rv-btn rv-btn--ghost rv-btn--sm"
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
                        <Search size={14} aria-hidden />
                        <span>{clampText(item.obligation, 48)}</span>
                      </button>
                    ))}
                  </div>
                ) : null}
              </article>
            ))}
          </div>
        ) : (
          <EmptyState
            title="No stakeholder intelligence yet"
            body="Once accepted documents pass through graph extraction, the stakeholders they affect appear here."
            Icon={Users}
          />
        )
      ) : null}

      {intelligenceTab === "readiness" ? (
        readinessStatus.isLoading ? (
          <SkeletonCards count={2} lines={3} label="Loading readiness report" />
        ) : readinessStatus.isError ? (
          <ErrorState
            title="Unable to load readiness report"
            body="The readiness summary could not be retrieved."
            error={readinessStatus.error}
            onRetry={readinessStatus.refetch}
          />
        ) : (
          <div className="rv-card">
            <FactList ariaLabel="Readiness summary">
              <Fact
                label="Active deadlines"
                value={readiness?.active_deadlines.length ?? 0}
              />
              <Fact
                label="Stakeholder groups"
                value={readiness?.stakeholder_obligations.length ?? 0}
              />
              <Fact
                label="Regulatory impacts"
                value={readiness?.regulatory_impacts.length ?? 0}
              />
            </FactList>
            {(readiness?.notes ?? []).length ? (
              <ul className="rv-notes">
                {(readiness?.notes ?? []).map((note) => (
                  <li key={note}>{note}</li>
                ))}
              </ul>
            ) : (
              <p className="rv-helper">
                No readiness notes were generated for the current corpus.
              </p>
            )}
          </div>
        )
      ) : null}

      {intelligenceTab === "timeline" ? (
        activeDeadlines.length ? (
          <ol className="rv-timeline">
            {activeDeadlines.map((deadline) => (
              <li
                className="rv-timeline__item rv-timeline__item--done"
                key={`${deadline.document_id}-${deadline.deadline_type}-${deadline.deadline_date}`}
              >
                <span className="rv-timeline__marker" aria-hidden>
                  <CalendarClock size={13} />
                </span>
                <div className="rv-timeline__body">
                  <button
                    className="rv-link-button"
                    type="button"
                    onClick={() =>
                      setSelectedEvidence({
                        title: deadline.title,
                        issuer: deadline.issuer,
                        date: deadline.deadline_date,
                        summary: deadline.deadline_type.replaceAll("_", " "),
                        evidence: deadline.evidence,
                        sourceUrl: deadline.source_url,
                        documentId: deadline.document_id,
                        relationships: deadline.stakeholders_affected.map(
                          (stakeholder) => `Affects ${stakeholder}`,
                        ),
                      })
                    }
                  >
                    {clampText(deadline.title, 110)}
                  </button>
                  <span className="rv-meta">
                    {deadline.deadline_type.replaceAll("_", " ").toLowerCase()} ·{" "}
                    {formatShortDate(deadline.deadline_date) ?? "Date not stated"}
                    {typeof deadline.days_remaining === "number"
                      ? ` · ${deadline.days_remaining} days left`
                      : ""}
                  </span>
                  <span className="rv-meta">
                    {deadline.stakeholders_affected.slice(0, 3).join(", ") ||
                      "Stakeholders not classified"}
                  </span>
                </div>
              </li>
            ))}
          </ol>
        ) : (
          <EmptyState
            title="No dated obligations"
            body="Deadlines extracted from regulatory documents appear here in chronological order."
            Icon={Network}
          />
        )
      ) : null}
    </div>
  );
}
