"use client";

import { useMemo } from "react";
import { CalendarClock, ExternalLink, Search } from "lucide-react";

import { Badge } from "@/app/components/ui/Badge";
import { Button } from "@/app/components/ui/Button";
import { EmptyState } from "@/app/components/ui/EmptyState";
import { ErrorState } from "@/app/components/ui/ErrorState";
import { PageHeader, SectionHeader } from "@/app/components/ui/PageHeader";
import { SkeletonCards } from "@/app/components/ui/Skeleton";
import { FilterSelect, RefreshButton, Toolbar } from "@/app/components/ui/Toolbar";
import { clampText, cleanText, formatShortDate } from "@/app/workspace/format";
import { deadlineTypes, stakeholderOptions } from "@/app/workspace/nav";
import { useWorkspace } from "@/app/workspace/WorkspaceContext";
import type { IntelligenceDeadline } from "@/lib/api";

type Urgency = "critical" | "soon" | "monitor";

const URGENCY_GROUPS: Array<{ id: Urgency; title: string; hint: string }> = [
  { id: "critical", title: "This week", hint: "Due within 7 days" },
  { id: "soon", title: "This month", hint: "Due within 30 days" },
  { id: "monitor", title: "Later", hint: "More than 30 days away" },
];

function urgency(deadline: IntelligenceDeadline): Urgency {
  const days = deadline.days_remaining;
  if (days !== null && days <= 7) return "critical";
  if (days !== null && days <= 30) return "soon";
  return "monitor";
}

function toOptions(values: string[], allLabel: string) {
  return values.map((value) => ({
    value,
    label:
      value === "all"
        ? allLabel
        : value.replaceAll("_", " ").replace(/^./, (char) => char.toUpperCase()),
  }));
}

/**
 * Deadlines grouped by how soon they bite. The previous list/timeline/calendar
 * switcher showed the same rows three ways; urgency grouping answers the actual
 * question ("what needs me this week?") without a mode to choose first.
 */
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

  const grouped = useMemo(() => {
    const buckets: Record<Urgency, IntelligenceDeadline[]> = {
      critical: [],
      soon: [],
      monitor: [],
    };
    for (const deadline of activeDeadlines) buckets[urgency(deadline)].push(deadline);
    for (const list of Object.values(buckets)) {
      list.sort((left, right) => (left.days_remaining ?? 9999) - (right.days_remaining ?? 9999));
    }
    return buckets;
  }, [activeDeadlines]);

  const toolbar = (
    <Toolbar
      ariaLabel="Deadline filters"
      filters={
        <>
          <FilterSelect
            label="Deadline type"
            value={deadlineType}
            options={toOptions(deadlineTypes, "Any deadline type")}
            onChange={setDeadlineType}
          />
          <FilterSelect
            label="Stakeholder"
            value={deadlineStakeholder}
            options={toOptions(stakeholderOptions, "Any stakeholder")}
            onChange={setDeadlineStakeholder}
          />
        </>
      }
      actions={
        <RefreshButton
          onClick={() => void loadIntelligenceData()}
          loading={deadlinesStatus.isFetching}
          label="Refresh deadlines"
        />
      }
    />
  );

  const body = deadlinesStatus.isLoading ? (
    <SkeletonCards count={4} lines={2} label="Loading deadlines" />
  ) : deadlinesStatus.isError ? (
    <ErrorState
      title="Unable to load deadlines"
      body="We couldn't retrieve extracted regulatory deadlines."
      error={deadlinesStatus.error}
      onRetry={deadlinesStatus.refetch}
    />
  ) : activeDeadlines.length ? (
    <>
      {URGENCY_GROUPS.map((group) =>
        grouped[group.id].length ? (
          <section className="rv-section" key={group.id}>
            <SectionHeader
              as="h3"
              title={group.title}
              count={`${grouped[group.id].length} · ${group.hint}`}
            />
            <ul className="rv-card-list">
              {grouped[group.id].map((deadline) => (
                <DeadlineRow
                  key={`${deadline.document_id}-${deadline.deadline_type}-${deadline.deadline_date}`}
                  deadline={deadline}
                  onEvidence={setSelectedEvidence}
                />
              ))}
            </ul>
          </section>
        ) : null,
      )}
    </>
  ) : (
    <EmptyState
      title="No deadlines match these filters"
      body="Try a different deadline type or stakeholder. Deadlines appear here once they are extracted from crawled documents."
      Icon={CalendarClock}
    />
  );

  if (embedded) {
    return (
      <div className="rv-section">
        {toolbar}
        {body}
      </div>
    );
  }

  return (
    <div className="rv-page">
      <PageHeader
        eyebrow="Deadline intelligence"
        title="Deadlines"
        description={`${activeDeadlines.length} dated obligation${activeDeadlines.length === 1 ? "" : "s"} extracted from regulatory documents.`}
      />
      {toolbar}
      {body}
    </div>
  );
}

function DeadlineRow({
  deadline,
  onEvidence,
}: {
  deadline: IntelligenceDeadline;
  onEvidence: ReturnType<typeof useWorkspace>["setSelectedEvidence"];
}) {
  const level = urgency(deadline);
  const days = deadline.days_remaining;

  return (
    <li className={`rv-deadline rv-deadline--${level}`}>
      <div className="rv-deadline__when">
        <strong>{days ?? "--"}</strong>
        <span>{days === 1 ? "day" : "days"}</span>
      </div>
      <div className="rv-deadline__body">
        <div className="rv-intel-card__tags">
          <Badge mono>{deadline.deadline_type.replaceAll("_", " ").toLowerCase()}</Badge>
          <Badge tone={level === "critical" ? "danger" : level === "soon" ? "warning" : "neutral"}>
            Due {formatShortDate(deadline.deadline_date) ?? "date not stated"}
          </Badge>
          {deadline.stakeholders_affected.slice(0, 2).map((stakeholder) => (
            <Badge key={stakeholder} tone="brand">
              {stakeholder}
            </Badge>
          ))}
        </div>
        <h4 className="rv-card-title">{cleanText(deadline.title)}</h4>
        <p className="rv-helper">
          {clampText(
            deadline.evidence,
            220,
            "Deadline detected from regulatory graph extraction.",
          )}
        </p>
        <p className="rv-meta">
          {deadline.issuer ?? "Unknown issuer"} · confidence{" "}
          {Math.round(deadline.confidence * 100)}%
        </p>
      </div>
      <div className="rv-deadline__actions">
        <Button
          variant="ghost"
          size="sm"
          Icon={Search}
          onClick={() =>
            onEvidence({
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
          Evidence
        </Button>
        <a
          className="rv-btn rv-btn--secondary rv-btn--sm"
          href={deadline.source_url}
          target="_blank"
          rel="noreferrer"
        >
          <ExternalLink size={14} aria-hidden />
          <span>Source</span>
        </a>
      </div>
    </li>
  );
}
