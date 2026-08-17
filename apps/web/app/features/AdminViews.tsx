import Link from "next/link";
import type { ReactNode } from "react";
import { AlertCircle, Database, History, Play, RefreshCw, Users } from "lucide-react";

import { StatusBadge, normalizeRunStatus } from "@/app/components/ui/Badge";
import { Button } from "@/app/components/ui/Button";
import { DataTable } from "@/app/components/ui/DataTable";
import { EmptyState } from "@/app/components/ui/EmptyState";
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
import { compactNumber, formatDateTime, formatDuration } from "@/app/workspace/format";
import { useWorkspace } from "@/app/workspace/WorkspaceContext";

/** Run-card helper: null/undefined means unavailable, not zero. */
export function formatRunMetric(value: number | null | undefined): string {
  if (value === null || value === undefined) return "Not available";
  return compactNumber(value);
}

/**
 * Admin routes share one soft gate: partial dataset failures degrade the page
 * rather than blanking it, because an operator diagnosing an outage needs
 * whatever telemetry did load.
 */
export function AdminGate({ children }: { children: ReactNode }) {
  const { adminStatus } = useWorkspace();
  return (
    <>
      {adminStatus.isError ? (
        <div className="status-banner">
          <AlertCircle size={18} />
          <span>Some admin datasets failed to load. Available panels remain usable.</span>
          <button type="button" onClick={adminStatus.refetch}>
            Retry
          </button>
        </div>
      ) : null}
      {children}
    </>
  );
}

/**
 * Operational overview: system scale, pipeline health and the most recent runs.
 * Deliberately shallow — every number here links to the console that owns it.
 */
export function AdminDashboardView() {
  const {
    analytics,
    sources,
    sourcePages,
    adminDocs,
    adminEvents,
    families,
    runs,
    ragStatus,
    ragQueue,
    adminStatus,
    busyAction,
    loadBaseData,
    handleProcessRagJob,
    handleRequeueRagJobs,
  } = useWorkspace();

  const enabledSources = sources.filter((source) => source.enabled).length;
  const degradedSources = sources.filter(
    (source) => (source.consecutive_failures ?? 0) > 0,
  ).length;
  const latestRun = runs[0];
  const failedRags = ragStatus?.failed_jobs ?? 0;

  return (
    <div className="rv-page">
      <PageHeader
        eyebrow="Operations"
        title="Admin dashboard"
        description={
          latestRun
            ? `Latest crawl #${latestRun.id} started ${formatDateTime(latestRun.started_at)}.`
            : "No crawl has run yet."
        }
        actions={
          <RefreshButton
            onClick={() => void loadBaseData()}
            loading={adminStatus.isFetching}
            label="Refresh admin telemetry"
          />
        }
      />

      {adminStatus.isLoading ? (
        <SkeletonMetrics count={6} />
      ) : (
        <MetricStrip ariaLabel="System scale">
          <Metric
            label="Sources"
            value={enabledSources}
            hint={`${sources.length} registered`}
          />
          <Metric
            label="Degraded sources"
            value={degradedSources}
            tone={degradedSources ? "warning" : "neutral"}
            hint="Consecutive failures"
          />
          <Metric label="Monitored pages" value={analytics?.pages ?? sourcePages.length} />
          <Metric label="Documents" value={analytics?.documents ?? adminDocs.length} />
          <Metric label="Events" value={analytics?.events ?? adminEvents.length} />
          <Metric
            label="RAG failures"
            value={failedRags}
            tone={failedRags ? "danger" : "neutral"}
            hint={`${compactNumber(ragStatus?.ready ?? 0)} indexed`}
          />
        </MetricStrip>
      )}

      <section className="rv-section">
        <SectionHeader
          title="Recent crawl runs"
          actions={
            <Link className="rv-btn rv-btn--secondary rv-btn--sm" href="/admin/runs">
              Open crawl runs
            </Link>
          }
        />
        {adminStatus.isLoading ? (
          <SkeletonCards count={3} lines={1} label="Loading recent runs" />
        ) : runs.length ? (
          <DataTable
            caption="Recent crawl runs"
            rows={runs.slice(0, 8)}
            rowKey={(run) => run.id}
            columns={[
              {
                id: "run",
                header: "Run",
                mobilePrimary: true,
                render: (run) => <span className="rv-cell-primary">#{run.id}</span>,
              },
              {
                id: "started",
                header: "Started",
                render: (run) => (
                  <span className="rv-cell-secondary">
                    {formatDateTime(run.started_at)}
                  </span>
                ),
              },
              {
                id: "duration",
                header: "Duration",
                numeric: true,
                render: (run) => formatDuration(run.started_at, run.finished_at),
              },
              {
                id: "documents",
                header: "Documents",
                numeric: true,
                render: (run) =>
                  compactNumber(run.documents_discovered ?? run.docs_found),
              },
              {
                id: "events",
                header: "Events",
                numeric: true,
                render: (run) => compactNumber(run.events_created ?? run.new_events),
              },
              {
                id: "status",
                header: "Status",
                render: (run) => (
                  <StatusBadge kind="run" status={normalizeRunStatus(run.status)} />
                ),
              },
              {
                id: "actions",
                header: "Actions",
                actions: true,
                render: (run) => (
                  <Link
                    className="rv-btn rv-btn--secondary rv-btn--sm"
                    href={`/admin/runs/${run.id}`}
                  >
                    View
                  </Link>
                ),
              },
            ]}
            mobileActions={(run) => (
              <Link
                className="rv-btn rv-btn--secondary rv-btn--sm rv-btn--block"
                href={`/admin/runs/${run.id}`}
              >
                View run #{run.id}
              </Link>
            )}
          />
        ) : (
          <EmptyState
            compact
            title="No crawl runs yet"
            body="Trigger a crawl from the Sources console to produce the first run."
            Icon={History}
            action={
              <Link className="rv-btn rv-btn--primary rv-btn--sm" href="/admin/sources">
                Open sources
              </Link>
            }
          />
        )}
      </section>

      <section className="rv-section">
        <SectionHeader
          title="Retrieval index"
          actions={
            <div className="rv-btn-group">
              <Button
                variant="secondary"
                size="sm"
                Icon={RefreshCw}
                loading={busyAction === "rag-requeue"}
                onClick={() => void handleRequeueRagJobs()}
              >
                Requeue interrupted
              </Button>
              <Button
                variant="secondary"
                size="sm"
                Icon={Play}
                loading={busyAction === "rag-process"}
                onClick={() => void handleProcessRagJob()}
              >
                Process next job
              </Button>
            </div>
          }
        />
        <div className="rv-card">
          <FactList ariaLabel="Retrieval index state">
            <Fact label="Chunks" value={compactNumber(ragStatus?.chunks ?? 0)} />
            <Fact label="Embeddings" value={compactNumber(ragStatus?.embeddings ?? 0)} />
            <Fact label="Documents ready" value={compactNumber(ragStatus?.ready ?? 0)} />
            <Fact label="Queued jobs" value={compactNumber(ragQueue.length)} />
            <Fact label="Failed jobs" value={compactNumber(failedRags)} />
            <Fact label="Document families" value={compactNumber(families.length)} />
          </FactList>
        </div>
      </section>

      <section className="rv-section">
        <SectionHeader title="Jump to" />
        <div className="rv-quick-links">
          <Link className="rv-quick-link" href="/admin/sources">
            <Database size={16} aria-hidden />
            <span className="rv-cell-primary">Sources</span>
            <span className="rv-cell-secondary">
              Registry, monitored pages and crawl triggers
            </span>
          </Link>
          <Link className="rv-quick-link" href="/admin/runs">
            <History size={16} aria-hidden />
            <span className="rv-cell-primary">Crawl runs</span>
            <span className="rv-cell-secondary">
              Run history, page results and failure diagnostics
            </span>
          </Link>
          <Link className="rv-quick-link" href="/admin/users">
            <Users size={16} aria-hidden />
            <span className="rv-cell-primary">Users</span>
            <span className="rv-cell-secondary">Accounts, roles and alert delivery</span>
          </Link>
        </div>
      </section>
    </div>
  );
}
