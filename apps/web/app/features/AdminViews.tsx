import {
  Activity,
  AlertCircle,
  CheckCircle2,
  ClipboardCheck,
  Database,
  FileSearch,
  FileText,
  Gauge,
  History,
  Layers3,
  Loader2,
  Network,
  Play,
  RefreshCw,
  Settings,
} from "lucide-react";

import type { ReactNode } from "react";

import { AdminRows } from "@/app/components/ui/AdminRows";
import { EmptyState } from "@/app/components/ui/EmptyState";
import { ErrorState } from "@/app/components/ui/ErrorState";
import { LoadingState } from "@/app/components/ui/LoadingState";
import { MetricCard } from "@/app/components/ui/MetricCard";
import { Panel } from "@/app/components/ui/Panel";
import { compactNumber, formatRelativeDate } from "@/app/workspace/format";
import { useWorkspace } from "@/app/workspace/WorkspaceContext";

export function AdminGate({ children }: { children: ReactNode }) {
  const { adminStatus } = useWorkspace();
  if (adminStatus.isLoading) {
    return <LoadingState label="Loading admin data..." />;
  }
  if (adminStatus.isError) {
    return (
      <ErrorState
        title="Unable to load admin data"
        error={adminStatus.error}
        onRetry={adminStatus.refetch}
      />
    );
  }
  return <>{children}</>;
}

export function AdminDashboardView() {
  const { analytics, sources, sourcePages, events, runs } = useWorkspace();
  const activeSources = sources.filter((source) => source.enabled).length;
  const healthySources = sources.filter((source) => (source.consecutive_failures ?? 0) === 0).length;
  const latestRun = runs[0];
  return (
    <div className="stitch-admin-page">
      <header className="stitch-page-header">
        <div>
          <h2>Platform Management</h2>
          <p>
            <span className="stitch-system-health">SYSTEM HEALTH: {healthySources ? "OPTIMAL" : "DEGRADED"}</span>{" "}
            Last updated: {formatRelativeDate(latestRun?.started_at)}
          </p>
        </div>
        <a className="stitch-secondary-action" href="/admin/sources">
          <span className="material-symbols-outlined">add</span>
          Add Source
        </a>
      </header>

      <section className="stitch-admin-kpis">
        <AdminKpi icon="menu_book" meta={`${Math.round((healthySources / Math.max(sources.length, 1)) * 100)}% UP`} value={activeSources || sources.length} label="Active Sources" />
        <AdminKpi icon="layers" meta="+12 today" value={analytics?.pages ?? sourcePages.length} label="Monitored Pages" />
        <AdminKpi icon="autorenew" meta={`${runs.filter((run) => run.status === "running").length} ongoing`} value={runs.length} label="Crawl Runs (24h)" />
        <AdminKpi icon="description" meta="Verified" value={analytics?.documents ?? 0} label="Parsed Documents" />
        <AdminKpi icon="notifications_active" meta="2 High" value={analytics?.events ?? events.length} label="System Events" />
        <AdminKpi icon="hub" meta="Optimized" value={analytics?.families ?? 0} label="Knowledge Nodes" />
        <AdminKpi icon="group" meta="24 online" value={analytics?.sources ?? sources.length} label="Active Users" />
      </section>

      <section className="stitch-admin-grid">
        <div className="stitch-admin-panel">
          <div className="stitch-section-heading stitch-section-heading--panel">
            <h3>Source Management</h3>
            <a href="/admin/sources">View All</a>
          </div>
          <div className="stitch-admin-source-list">
            {sources.slice(0, 3).map((source) => (
              <div key={source.id} className="stitch-admin-source-card">
                <span>{source.code}</span>
                <div>
                  <strong>{source.name}</strong>
                  <p>Code: {source.code}</p>
                </div>
                <div>
                  <strong className={source.consecutive_failures ? "bad" : "good"}>
                    {source.consecutive_failures ? "Degraded" : "Healthy"}
                  </strong>
                  <p>Synced: {formatRelativeDate(source.last_checked_at)}</p>
                </div>
              </div>
            ))}
            {!sources.length ? <EmptyState title="No sources" body="No admin sources are available." /> : null}
          </div>
          <a className="stitch-primary-action as-link" href="/admin/sources">Configure All Sources</a>
        </div>

        <div className="stitch-admin-panel">
          <div className="stitch-section-heading stitch-section-heading--panel">
            <h3>Recent Crawl Runs</h3>
            <span className="stitch-live-feed">LIVE FEED</span>
          </div>
          <div className="stitch-admin-table-toolbar">
            <button type="button"><span className="material-symbols-outlined">filter_list</span></button>
            <button type="button"><span className="material-symbols-outlined">refresh</span></button>
          </div>
          <div className="stitch-admin-run-table">
            <div>
              <strong>Source Code</strong>
              <strong>Status</strong>
              <strong>Duration</strong>
              <strong>Docs (Acc/Rej)</strong>
              <strong>Actions</strong>
            </div>
            {runs.slice(0, 5).map((run) => (
              <div key={run.id}>
                <span>RUN_{run.id}</span>
                <span className={`run-status ${run.status}`}>
                  <span className="material-symbols-outlined">
                    {run.status === "failed" ? "error" : run.status === "running" ? "sync" : "check_circle"}
                  </span>
                  {run.status}
                </span>
                <span>{run.finished_at ? formatRelativeDate(run.finished_at) : "In Progress"}</span>
                <span>{compactNumber(run.docs_found)} / {compactNumber(run.errors.length)}</span>
                <a href="/admin/runs">{run.status === "failed" ? "Retry" : "Logs"}</a>
              </div>
            ))}
          </div>
        </div>
      </section>
    </div>
  );
}

function AdminKpi({ icon, meta, value, label }: { icon: string; meta: string; value: number; label: string }) {
  return (
    <article className="stitch-admin-kpi">
      <span className="material-symbols-outlined">{icon}</span>
      <small>{meta}</small>
      <strong>{compactNumber(value)}</strong>
      <p>{label}</p>
    </article>
  );
}

export function AdminSourcesView() {
  const { sources, busyAction, handleToggleSource, handleSourceCrawl, loadBaseData } = useWorkspace();
  return (
    <Panel
      title="Sources"
      icon={Database}
      action={
        <button type="button" onClick={() => void loadBaseData()}>
          <RefreshCw size={16} /> Refresh
        </button>
      }
    >
      <AdminRows
        rows={sources}
        columns={[
          ["Code", (row) => row.code],
          ["Name", (row) => row.name],
          ["Status", (row) => (row.enabled ? "Enabled" : "Disabled")],
          ["Failures", (row) => compactNumber(row.consecutive_failures)],
          [
            "Actions",
            (row) => (
              <div className="row-actions">
                <button
                  type="button"
                  onClick={() => void handleToggleSource(row)}
                  disabled={busyAction === `source-${row.id}`}
                >
                  {busyAction === `source-${row.id}` ? <Loader2 className="spin" size={15} /> : <Settings size={15} />}
                  {row.enabled ? "Disable" : "Enable"}
                </button>
                <button
                  type="button"
                  onClick={() => void handleSourceCrawl(row)}
                  disabled={busyAction === `crawl-source-${row.id}`}
                >
                  {busyAction === `crawl-source-${row.id}` ? <Loader2 className="spin" size={15} /> : <Play size={15} />}
                  Crawl
                </button>
              </div>
            ),
          ],
        ]}
      />
    </Panel>
  );
}

export function AdminPagesView() {
  const { sourcePages, busyAction, handlePageCrawl } = useWorkspace();
  return (
    <Panel title="Source Pages" icon={Layers3}>
      <AdminRows
        rows={sourcePages}
        columns={[
          ["Source", (row) => row.source_code],
          ["Page", (row) => row.name],
          ["Type", (row) => row.page_type],
          ["Priority", (row) => row.priority],
          ["Last Crawled", (row) => formatRelativeDate(row.last_crawled_at)],
          [
            "Action",
            (row) => (
              <button
                type="button"
                onClick={() => void handlePageCrawl(row)}
                disabled={busyAction === `crawl-page-${row.id}`}
              >
                {busyAction === `crawl-page-${row.id}` ? <Loader2 className="spin" size={15} /> : <Play size={15} />}
                Crawl
              </button>
            ),
          ],
        ]}
      />
    </Panel>
  );
}

export function AdminRunsView() {
  const { runs } = useWorkspace();
  return (
    <Panel title="Crawl Runs" icon={History}>
      <AdminRows
        rows={runs}
        columns={[
          ["Run", (row) => `#${row.id}`],
          ["Started", (row) => formatRelativeDate(row.started_at)],
          ["Status", (row) => row.status],
          ["Sources", (row) => `${row.sources_succeeded}/${row.sources_attempted}`],
          ["Docs", (row) => compactNumber(row.docs_found)],
          ["Events", (row) => compactNumber(row.new_events)],
        ]}
      />
    </Panel>
  );
}

export function AdminEventsView() {
  const { adminEvents } = useWorkspace();
  return (
    <Panel title="Events" icon={ClipboardCheck}>
      <AdminRows
        rows={adminEvents}
        columns={[
          ["ID", (row) => `#${row.id}`],
          ["Source", (row) => row.source_code ?? "unknown"],
          ["Title", (row) => <span className="table-title">{row.title}</span>],
          ["Quality", (row) => row.quality_score ?? "n/a"],
          ["Significance", (row) => row.significance_score ?? "n/a"],
          ["Status", (row) => (row.suppressed ? "Suppressed" : "Visible")],
        ]}
      />
    </Panel>
  );
}

export function AdminDocumentsView() {
  const { adminDocs } = useWorkspace();
  return (
    <Panel title="Documents" icon={FileText}>
      <AdminRows
        rows={adminDocs}
        columns={[
          ["ID", (row) => `#${row.id}`],
          ["Source", (row) => row.source_code ?? "unknown"],
          ["Title", (row) => <span className="table-title">{row.title}</span>],
          ["Type", (row) => row.doc_type ?? "unknown"],
          ["Family", (row) => row.family_title ?? "unassigned"],
          ["Seen", (row) => formatRelativeDate(row.last_seen_at)],
        ]}
      />
    </Panel>
  );
}

export function AdminFamiliesView() {
  const { families } = useWorkspace();
  return (
    <Panel title="Document Families" icon={Network}>
      <AdminRows
        rows={families}
        columns={[
          ["Family", (row) => <span className="table-title">{row.canonical_title}</span>],
          ["Issuer", (row) => row.issuer ?? "unknown"],
          ["Docs", (row) => compactNumber(row.document_count)],
          ["Versions", (row) => compactNumber(row.version_count)],
          ["Deadlines", (row) => compactNumber(row.deadline_count)],
        ]}
      />
    </Panel>
  );
}

export function AdminCheckpointsView() {
  const { checkpoints } = useWorkspace();
  return (
    <Panel title="Incremental Crawl Checkpoints" icon={CheckCircle2}>
      <AdminRows
        rows={checkpoints}
        columns={[
          ["Source", (row) => row.source_code],
          ["Page", (row) => row.source_page],
          ["Checkpoint", (row) => <span className="table-title">{row.checkpoint_title ?? "not set"}</span>],
          ["Lookback", (row) => row.lookback_count ?? 3],
          ["Updated", (row) => formatRelativeDate(row.updated_at)],
        ]}
      />
    </Panel>
  );
}

export function AdminAnalyticsView() {
  const { analytics } = useWorkspace();
  return (
    <div className="page-stack">
      <section className="metric-grid">
        <MetricCard title="Candidates" value={analytics?.candidates ?? 0} Icon={FileSearch} tone="purple" />
        <MetricCard title="Accepted" value={analytics?.accepted_candidates ?? 0} Icon={CheckCircle2} tone="green" />
        <MetricCard title="Rejected" value={analytics?.rejected_candidates ?? 0} Icon={AlertCircle} tone="red" />
        <MetricCard title="Families" value={analytics?.families ?? 0} Icon={Network} tone="amber" />
      </section>
      <Panel title="Top Rejection Reasons" icon={Activity}>
        <div className="reason-list">
          {(analytics?.rejected_reasons ?? []).map((reason) => (
            <div key={reason.reason_code ?? "unknown"}>
              <span>{reason.reason_code ?? "unknown"}</span>
              <strong>{compactNumber(reason.count)}</strong>
            </div>
          ))}
        </div>
      </Panel>
    </div>
  );
}
