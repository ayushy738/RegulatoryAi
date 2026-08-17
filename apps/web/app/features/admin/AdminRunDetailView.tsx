"use client";

import { useState } from "react";
import Link from "next/link";
import {
  AlertTriangle,
  ArrowLeft,
  Check,
  ChevronDown,
  ChevronRight,
  CircleDashed,
  Loader2,
  Minus,
  X,
} from "lucide-react";

import { Badge, StatusBadge, normalizeRunStatus } from "@/app/components/ui/Badge";
import { Button } from "@/app/components/ui/Button";
import { EmptyState } from "@/app/components/ui/EmptyState";
import { ErrorState } from "@/app/components/ui/ErrorState";
import {
  Fact,
  FactList,
  Metric,
  MetricStrip,
  PageHeader,
  SectionHeader,
} from "@/app/components/ui/PageHeader";
import { SkeletonCards, SkeletonMetrics } from "@/app/components/ui/Skeleton";
import { RefreshButton } from "@/app/components/ui/Toolbar";
import type { CrawlRun, CrawlRunPageResult } from "@/lib/api";
import {
  CATEGORY_LABEL,
  classifyCrawlErrors,
  groupCrawlErrors,
  retryabilityLabel,
} from "@/lib/crawl-errors";
import type { ClassifiedCrawlError } from "@/lib/crawl-errors";
import { useAdminRunPagesQuery, useAdminRunQuery } from "@/lib/queries";
import { formatDateTime, formatDuration } from "@/app/workspace/format";
import { useWorkspace } from "@/app/workspace/WorkspaceContext";

import { pipelineStages } from "./crawl-stages";
import type { StageStatus } from "./crawl-stages";

function metricValue(value: number | null | undefined) {
  return typeof value === "number" ? value : "—";
}

/**
 * One crawl run, structured as an operator reads it: what happened, which pages
 * were affected, where in the pipeline it got to, and what failed. Raw payloads
 * are always demoted behind a disclosure.
 */
export function AdminRunDetailView({ runId }: { runId: number }) {
  const { token } = useWorkspace();
  const runQuery = useAdminRunQuery(runId, token, true);
  const pagesQuery = useAdminRunPagesQuery(runId, token, true);

  function refreshAll() {
    void runQuery.refetch();
    void pagesQuery.refetch();
  }

  if (runQuery.isLoading) {
    return (
      <div className="rv-page">
        <PageHeader eyebrow="Operations" title={`Crawl #${runId}`} />
        <SkeletonMetrics count={4} />
        <SkeletonCards count={3} lines={2} label="Loading crawl run" />
      </div>
    );
  }

  if (runQuery.isError || !runQuery.data) {
    return (
      <div className="rv-page">
        <PageHeader
          eyebrow="Operations"
          title={`Crawl #${runId}`}
          actions={
            <Button variant="secondary" Icon={ArrowLeft} onClick={() => history.back()}>
              Back to runs
            </Button>
          }
        />
        <ErrorState
          title="Unable to load this crawl run"
          body="The run telemetry could not be retrieved. It may have been removed, or the operations API is unavailable."
          error={runQuery.error}
          onRetry={refreshAll}
          showTechnicalDetails
          action={
            <Link className="rv-btn rv-btn--primary" href="/admin/runs">
              Back to runs
            </Link>
          }
        />
      </div>
    );
  }

  const run = runQuery.data;
  const status = normalizeRunStatus(run.status);
  const errors = classifyCrawlErrors(run.errors);
  const pages = pagesQuery.data ?? [];

  return (
    <div className="rv-page">
      <PageHeader
        eyebrow="Operations"
        title={`Crawl #${run.id}`}
        description={
          <>
            Started {formatDateTime(run.started_at)} · ran for{" "}
            {formatDuration(run.started_at, run.finished_at)}
            {run.finished_at ? "" : " (still in progress)"}
          </>
        }
        actions={
          <>
            <Link className="rv-btn rv-btn--ghost" href="/admin/runs">
              <ArrowLeft size={16} aria-hidden />
              <span>Back to runs</span>
            </Link>
            <RefreshButton
              onClick={refreshAll}
              loading={runQuery.isFetching || pagesQuery.isFetching}
              label="Refresh this crawl run"
            />
          </>
        }
      />

      <div className="rv-active-filters">
        <StatusBadge kind="run" status={status} />
        {errors.length ? (
          <Badge tone="danger" Icon={AlertTriangle}>
            {errors.length} failure{errors.length === 1 ? "" : "s"}
          </Badge>
        ) : (
          <Badge tone="success">No failures</Badge>
        )}
        {run.finished_at ? null : <Badge tone="info">In progress</Badge>}
      </div>

      <ExecutionSummary run={run} />

      <PageResults
        pages={pages}
        loading={pagesQuery.isLoading}
        error={pagesQuery.isError ? pagesQuery.error : null}
        onRetry={() => void pagesQuery.refetch()}
      />

      <PipelineProgress run={run} />

      <Errors errors={errors} />
    </div>
  );
}

function ExecutionSummary({ run }: { run: CrawlRun }) {
  return (
    <section className="rv-section">
      <SectionHeader title="Execution summary" />
      <MetricStrip ariaLabel="Execution summary">
        <Metric
          label="Pages"
          value={metricValue(run.pages_attempted)}
          hint={`${metricValue(run.pages_succeeded)} succeeded`}
        />
        <Metric
          label="Documents"
          value={run.documents_discovered ?? run.docs_found ?? 0}
          hint={`${metricValue(run.documents_persisted)} persisted`}
        />
        <Metric
          label="Events"
          value={run.events_created ?? run.new_events ?? 0}
          hint="Created this run"
        />
        <Metric
          label="RAG"
          value={metricValue(run.rag_jobs_enqueued)}
          hint={`${metricValue(run.rag_indexed)} indexed`}
          tone={run.rag_jobs_failed ? "danger" : "neutral"}
        />
      </MetricStrip>
      <details className="rv-disclosure">
        <summary>All run metrics</summary>
        <div className="rv-disclosure__content">
          <FactList ariaLabel="Complete run telemetry">
            <Fact label="Sources attempted" value={run.sources_attempted} />
            <Fact label="Sources succeeded" value={run.sources_succeeded} />
            <Fact
              label="Documents with content"
              value={metricValue(run.documents_with_content)}
            />
            <Fact label="Versions created" value={metricValue(run.versions_created)} />
            <Fact label="Families touched" value={metricValue(run.families_touched)} />
            <Fact
              label="Graph extractions"
              value={metricValue(run.graph_extractions)}
            />
            <Fact label="Entities" value={metricValue(run.entities_extracted)} />
            <Fact label="Stakeholders" value={metricValue(run.stakeholders_extracted)} />
            <Fact label="RAG completed" value={metricValue(run.rag_jobs_completed)} />
            <Fact label="RAG failed" value={metricValue(run.rag_jobs_failed)} />
            <Fact label="Chunks indexed" value={metricValue(run.chunks_indexed)} />
            <Fact label="Finished" value={formatDateTime(run.finished_at)} />
          </FactList>
        </div>
      </details>
    </section>
  );
}

function PageResults({
  pages,
  loading,
  error,
  onRetry,
}: {
  pages: CrawlRunPageResult[];
  loading: boolean;
  error: unknown;
  onRetry: () => void;
}) {
  const [expanded, setExpanded] = useState<string | null>(null);

  return (
    <section className="rv-section">
      <SectionHeader
        title="Page results"
        count={loading ? undefined : `${pages.length}`}
      />
      {loading ? (
        <SkeletonCards count={2} lines={1} label="Loading page results" />
      ) : error ? (
        <ErrorState
          compact
          title="Unable to load page results"
          body="Per-page crawl results could not be retrieved for this run."
          error={error}
          onRetry={onRetry}
          showTechnicalDetails
        />
      ) : pages.length ? (
        <ul className="rv-card-list">
          {pages.map((page, index) => {
            const key = `${page.page_id ?? "unknown"}-${index}`;
            const open = expanded === key;
            const pageErrors = classifyCrawlErrors(page.errors);
            return (
              <li className="rv-card" key={key}>
                <div className="rv-card__header">
                  <div className="rv-card__identity">
                    <button
                      type="button"
                      className="rv-btn rv-btn--ghost rv-btn--icon rv-btn--sm"
                      aria-expanded={open}
                      aria-label={`${open ? "Hide" : "Show"} diagnostics for ${page.page_name}`}
                      onClick={() => setExpanded(open ? null : key)}
                    >
                      {open ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
                    </button>
                    <div>
                      <span className="rv-cell-primary">{page.page_name}</span>
                      <span className="rv-cell-secondary">
                        {page.source_code ? `${page.source_code} · ` : ""}
                        {page.page_type ?? "page"}
                      </span>
                    </div>
                  </div>
                  <div className="rv-btn-group">
                    <StatusBadge kind="run" status={page.status} />
                  </div>
                </div>

                <FactList ariaLabel={`${page.page_name} results`}>
                  <Fact label="Documents found" value={page.documents_discovered} />
                  <Fact label="Accepted" value={page.documents_accepted} />
                  <Fact label="With content" value={page.documents_with_content} />
                  <Fact
                    label="Duration"
                    value={formatDuration(page.first_seen_at, page.last_seen_at)}
                  />
                </FactList>

                {pageErrors.length ? (
                  <p className="rv-field__error">
                    <AlertTriangle size={13} aria-hidden />
                    {pageErrors[0].title}
                  </p>
                ) : null}

                {open ? (
                  <>
                    <hr className="rv-divider" />
                    {page.page_url ? (
                      <a
                        className="rv-cell-secondary"
                        href={page.page_url}
                        target="_blank"
                        rel="noreferrer"
                      >
                        {page.page_url}
                      </a>
                    ) : null}
                    {pageErrors.length ? (
                      <div className="rv-stack">
                        {pageErrors.map((pageError, errorIndex) => (
                          <ErrorDetail
                            key={`${key}-error-${errorIndex}`}
                            error={pageError}
                          />
                        ))}
                      </div>
                    ) : (
                      <p className="rv-helper">
                        No failures were recorded for this page.
                      </p>
                    )}
                  </>
                ) : null}
              </li>
            );
          })}
        </ul>
      ) : (
        <EmptyState
          compact
          title="No page results recorded"
          body="This run did not record per-page activity. That normally means it failed before page selection, or it was triggered at source level and stopped early."
          Icon={CircleDashed}
        />
      )}
    </section>
  );
}

const STAGE_ICON: Record<StageStatus, typeof Check> = {
  done: Check,
  active: Loader2,
  failed: X,
  skipped: Minus,
  pending: CircleDashed,
};

const STAGE_CLASS: Record<StageStatus, string> = {
  done: "rv-timeline__item--done",
  active: "rv-timeline__item--active",
  failed: "rv-timeline__item--failed",
  skipped: "",
  pending: "",
};

const STAGE_LABEL: Record<StageStatus, string> = {
  done: "Completed",
  active: "In progress",
  failed: "Did not complete",
  skipped: "Skipped",
  pending: "Not recorded",
};

function PipelineProgress({ run }: { run: CrawlRun }) {
  const stages = pipelineStages(run);

  return (
    <section className="rv-section">
      <SectionHeader title="Pipeline progress" />
      <div className="rv-card">
        <ol className="rv-timeline">
          {stages.map((stage) => {
            const Icon = STAGE_ICON[stage.status];
            return (
              <li
                className={`rv-timeline__item ${STAGE_CLASS[stage.status]}`}
                key={stage.id}
              >
                <span className="rv-timeline__marker" aria-hidden>
                  <Icon
                    size={13}
                    className={stage.status === "active" ? "rv-btn__spinner" : undefined}
                  />
                </span>
                <div className="rv-timeline__body">
                  <span className="rv-timeline__title">
                    {stage.name}
                    <span className="rv-meta">{STAGE_LABEL[stage.status]}</span>
                  </span>
                  <span className="rv-meta">{stage.result}</span>
                </div>
              </li>
            );
          })}
        </ol>
      </div>
    </section>
  );
}

function Errors({ errors }: { errors: ClassifiedCrawlError[] }) {
  if (!errors.length) {
    return (
      <section className="rv-section">
        <SectionHeader title="Errors" />
        <EmptyState
          compact
          title="No errors recorded"
          body="Every page this run attempted completed without reporting a failure."
          Icon={Check}
        />
      </section>
    );
  }

  const groups = groupCrawlErrors(errors);

  return (
    <section className="rv-section">
      <SectionHeader title="Errors" count={`${errors.length}`} />
      <div className="rv-card-list">
        {groups.map((group, index) => (
          <div className="rv-card" key={`${group.category}-${index}`}>
            <div className="rv-card__header">
              <div className="rv-card__identity">
                <div>
                  <h3 className="rv-card-title">{group.title}</h3>
                  <p className="rv-cell-secondary">
                    {CATEGORY_LABEL[group.category]}
                    {group.items.length > 1
                      ? ` · affected ${group.items.length} pages`
                      : ""}
                  </p>
                </div>
              </div>
              <Badge
                tone={
                  group.items[0].retryability === "retryable"
                    ? "info"
                    : group.items[0].retryability === "needs_configuration"
                      ? "warning"
                      : "danger"
                }
              >
                {retryabilityLabel(group.items[0].retryability)}
              </Badge>
            </div>
            <p className="rv-page-subtitle">{group.items[0].explanation}</p>
            {group.items.map((error, errorIndex) => (
              <ErrorDetail key={`${group.category}-${index}-${errorIndex}`} error={error} />
            ))}
          </div>
        ))}
      </div>
    </section>
  );
}

/** Labelled facts first; the raw serialised payload only behind a disclosure. */
function ErrorDetail({ error }: { error: ClassifiedCrawlError }) {
  return (
    <div className="rv-stack">
      {error.facts.length ? (
        <FactList ariaLabel="Failure details">
          {error.facts.map((fact) => (
            <Fact key={fact.label} label={fact.label} value={fact.value} />
          ))}
        </FactList>
      ) : null}
      <details className="rv-disclosure">
        <summary>Technical details</summary>
        <div className="rv-disclosure__content">
          <code className="rv-code">{JSON.stringify(error.raw, null, 2)}</code>
        </div>
      </details>
    </div>
  );
}
