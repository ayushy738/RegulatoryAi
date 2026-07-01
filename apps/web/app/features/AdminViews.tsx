import Link from "next/link";
import { useState } from "react";
import type { ReactNode } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Activity,
  AlertCircle,
  Bell,
  CheckCircle2,
  ClipboardCheck,
  Database,
  ExternalLink,
  FileSearch,
  FileText,
  Gauge,
  History,
  Layers3,
  Loader2,
  Network,
  Play,
  Plus,
  RefreshCw,
  Settings,
  TableProperties,
  Trash2,
  Users,
} from "lucide-react";

import {
  createSource,
  createSourcePage,
  deleteSource,
  deleteSourcePage,
  updateAdminUserRole,
  updateSourcePage,
} from "@/lib/api";
import type { SourceCreatePayload, SourcePageCreatePayload } from "@/lib/api";
import { queryKeys } from "@/lib/queries";
import { AdminRows } from "@/app/components/ui/AdminRows";
import { EmptyState } from "@/app/components/ui/EmptyState";
import { ErrorState } from "@/app/components/ui/ErrorState";
import { LoadingState } from "@/app/components/ui/LoadingState";
import { MetricCard } from "@/app/components/ui/MetricCard";
import { Panel } from "@/app/components/ui/Panel";
import { compactNumber, formatDate, formatRelativeDate } from "@/app/workspace/format";
import { useWorkspace } from "@/app/workspace/WorkspaceContext";

export function AdminGate({ children }: { children: ReactNode }) {
  const { adminStatus } = useWorkspace();
  if (adminStatus.isLoading) return <LoadingState label="Loading admin data..." />;
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

export function AdminDashboardView() {
  const { analytics, sources, sourcePages, adminDocs, adminEvents, families, runs, ragStatus, loadBaseData } =
    useWorkspace();
  const activeSources = sources.filter((source) => source.enabled).length;
  const healthySources = sources.filter((source) => (source.consecutive_failures ?? 0) === 0).length;
  const latestRun = runs[0];
  return (
    <div className="page-stack ops-page admin-dashboard-console">
      <section className="ops-page-header premium-page-header">
        <div>
          <span>Operations Console</span>
          <h1>Admin dashboard</h1>
          <p>
            {healthySources}/{sources.length || 0} sources healthy | latest run{" "}
            {formatRelativeDate(latestRun?.started_at)}
          </p>
        </div>
        <button type="button" onClick={() => void loadBaseData()}>
          <RefreshCw size={16} />
          Refresh
        </button>
      </section>

      <section className="metric-grid">
        <MetricCard title="Sources" value={activeSources || sources.length} Icon={Database} tone="green" />
        <MetricCard title="Pages" value={analytics?.pages ?? sourcePages.length} Icon={Layers3} tone="purple" />
        <MetricCard title="Documents" value={analytics?.documents ?? adminDocs.length} Icon={FileText} tone="amber" />
        <MetricCard title="Events" value={analytics?.events ?? adminEvents.length} Icon={ClipboardCheck} tone="red" />
        <MetricCard title="Families" value={analytics?.families ?? families.length} Icon={Network} tone="purple" />
        <MetricCard title="RAG Ready" value={ragStatus?.ready ?? 0} Icon={TableProperties} tone="green" />
        <MetricCard title="RAG Failed Jobs" value={ragStatus?.failed_jobs ?? 0} Icon={AlertCircle} tone="red" />
        <MetricCard title="Runs" value={runs.length} Icon={History} tone="amber" />
      </section>

      <section className="admin-console-grid">
        <Panel title="Recent Runs" icon={History} action={<Link href="/admin/runs">Open</Link>}>
          <AdminRows
            rows={runs.slice(0, 10)}
            columns={[
              ["Run", (row) => `#${row.id}`],
              ["Status", (row) => row.status],
              ["Started", (row) => formatRelativeDate(row.started_at)],
              ["Docs", (row) => compactNumber(row.docs_found)],
              ["Events", (row) => compactNumber(row.new_events)],
            ]}
          />
        </Panel>
        <Panel title="RAG Queue" icon={TableProperties} action={<Link href="/admin/runs">Open</Link>}>
          <div className="ops-health-grid">
            <span>
              <strong>{compactNumber(ragStatus?.chunks ?? 0)}</strong>
              chunks
            </span>
            <span>
              <strong>{compactNumber(ragStatus?.embeddings ?? 0)}</strong>
              embeddings
            </span>
            <span>
              <strong>{compactNumber(ragStatus?.pending_jobs ?? 0)}</strong>
              pending
            </span>
            <span>
              <strong>{compactNumber(ragStatus?.failed_jobs ?? 0)}</strong>
              failed
            </span>
          </div>
        </Panel>
      </section>
    </div>
  );
}

type SourcePageDraft = SourcePageCreatePayload;

type SourceCreateForm = {
  code: string;
  name: string;
  url: string;
  jurisdiction: SourceCreatePayload["jurisdiction"];
  crawler_type: SourceCreatePayload["crawler_type"];
  allowed_domains: string;
  hint: string;
  enabled: boolean;
  pages: SourcePageDraft[];
};

const emptyPageDraft: SourcePageDraft = {
  name: "",
  url: "",
  page_type: "listing",
  priority: 100,
  enabled: true,
};

const emptySourceForm: SourceCreateForm = {
  code: "",
  name: "",
  url: "",
  jurisdiction: "central",
  crawler_type: "agent",
  allowed_domains: "",
  hint: "",
  enabled: true,
  pages: [{ ...emptyPageDraft }],
};

function parseDomains(value: string) {
  return value
    .split(/[\n,]/)
    .map((item) => item.trim())
    .filter(Boolean);
}

export function AdminSourcesView() {
  const {
    sources,
    sourcePages,
    busyAction,
    token,
    setStatusMessage,
    handleToggleSource,
    handleSourceCrawl,
    handlePageCrawl,
    loadBaseData,
  } =
    useWorkspace();
  const queryClient = useQueryClient();
  const [formOpen, setFormOpen] = useState(false);
  const [form, setForm] = useState<SourceCreateForm>(emptySourceForm);

  const invalidateSources = () => {
    void queryClient.invalidateQueries({ queryKey: queryKeys.admin.sources });
    void queryClient.invalidateQueries({ queryKey: queryKeys.admin.pages });
    void queryClient.invalidateQueries({ queryKey: queryKeys.admin.analytics });
  };

  const createMutation = useMutation({
    mutationFn: async () => {
      const source = await createSource(
        {
          code: form.code.trim().toUpperCase(),
          name: form.name.trim(),
          url: form.url.trim(),
          jurisdiction: form.jurisdiction,
          crawler_type: form.crawler_type,
          allowed_domains: parseDomains(form.allowed_domains),
          hint: form.hint.trim() || null,
          enabled: form.enabled,
        },
        token,
      );
      const pages = form.pages.filter((page) => page.name.trim() && page.url.trim());
      await Promise.all(
        pages.map((page) =>
          createSourcePage(
            source.id,
            {
              name: page.name.trim(),
              url: page.url.trim(),
              page_type: page.page_type.trim() || "listing",
              priority: Number(page.priority) || 100,
              enabled: page.enabled,
            },
            token,
          ),
        ),
      );
      return { source, pageCount: pages.length };
    },
    onSuccess: ({ source, pageCount }) => {
      invalidateSources();
      setForm(emptySourceForm);
      setFormOpen(false);
      setStatusMessage(`Created ${source.name} with ${pageCount} monitored page(s).`);
    },
    onError: (error) => setStatusMessage(error instanceof Error ? error.message : "Unable to create source."),
  });

  const pageMutation = useMutation({
    mutationFn: ({ pageId, enabled }: { pageId: number; enabled: boolean }) =>
      updateSourcePage(pageId, { enabled }, token),
    onSuccess: invalidateSources,
    onError: (error) => setStatusMessage(error instanceof Error ? error.message : "Unable to update page."),
  });

  const pageDeleteMutation = useMutation({
    mutationFn: (pageId: number) => deleteSourcePage(pageId, token),
    onSuccess: invalidateSources,
    onError: (error) => setStatusMessage(error instanceof Error ? error.message : "Unable to delete page."),
  });

  const sourceDeleteMutation = useMutation({
    mutationFn: (sourceId: number) => deleteSource(sourceId, token),
    onSuccess: invalidateSources,
    onError: (error) => setStatusMessage(error instanceof Error ? error.message : "Unable to delete source."),
  });

  function updatePageDraft(index: number, patch: Partial<SourcePageDraft>) {
    setForm((current) => ({
      ...current,
      pages: current.pages.map((page, pageIndex) => (pageIndex === index ? { ...page, ...patch } : page)),
    }));
  }

  function removePageDraft(index: number) {
    setForm((current) => ({
      ...current,
      pages: current.pages.length === 1 ? [{ ...emptyPageDraft }] : current.pages.filter((_, pageIndex) => pageIndex !== index),
    }));
  }

  return (
    <div className="page-stack ops-page admin-sources-console">
      <section className="ops-page-header premium-page-header">
        <div>
          <span>Operations Console</span>
          <h1>Sources</h1>
          <p>Manage monitored websites and their crawled pages from one place.</p>
        </div>
        <button type="button" onClick={() => void loadBaseData()}>
          <RefreshCw size={16} />
          Refresh
        </button>
      </section>

      <section className="admin-create-source-panel">
        <div>
          <strong>Create Source</strong>
          <p>Enter a website, add monitored pages, then save it into the production source registry.</p>
        </div>
        <button type="button" onClick={() => setFormOpen((open) => !open)}>
          <Plus size={16} />
          {formOpen ? "Close" : "Create Source"}
        </button>
      </section>

      {formOpen ? (
        <form
          className="admin-source-create-form"
          onSubmit={(event) => {
            event.preventDefault();
            createMutation.mutate();
          }}
        >
          <div className="admin-form-grid">
            <label>
              Website
              <input
                required
                value={form.url}
                onChange={(event) => setForm({ ...form, url: event.target.value })}
                placeholder="https://example.gov.in"
              />
            </label>
            <label>
              Source name
              <input
                required
                value={form.name}
                onChange={(event) => setForm({ ...form, name: event.target.value })}
                placeholder="Central Electricity Regulatory Commission"
              />
            </label>
            <label>
              Code
              <input
                required
                value={form.code}
                onChange={(event) => setForm({ ...form, code: event.target.value })}
                placeholder="CERC"
              />
            </label>
            <label>
              Jurisdiction
              <select
                value={form.jurisdiction}
                onChange={(event) => setForm({ ...form, jurisdiction: event.target.value as SourceCreateForm["jurisdiction"] })}
              >
                <option value="central">central</option>
                <option value="state">state</option>
              </select>
            </label>
            <label>
              Crawler
              <select
                value={form.crawler_type}
                onChange={(event) => setForm({ ...form, crawler_type: event.target.value as SourceCreateForm["crawler_type"] })}
              >
                <option value="agent">agent</option>
                <option value="digest">digest</option>
                <option value="static">static</option>
              </select>
            </label>
            <label>
              Allowed domains
              <input
                value={form.allowed_domains}
                onChange={(event) => setForm({ ...form, allowed_domains: event.target.value })}
                placeholder="example.gov.in, cdn.example.gov.in"
              />
            </label>
          </div>
          <label className="admin-form-wide">
            Crawl hint
            <textarea
              value={form.hint}
              onChange={(event) => setForm({ ...form, hint: event.target.value })}
              placeholder="Prioritize current notices, tenders, public consultations, and amendment pages."
              rows={2}
            />
          </label>
          <label className="admin-checkbox-row">
            <input
              type="checkbox"
              checked={form.enabled}
              onChange={(event) => setForm({ ...form, enabled: event.target.checked })}
            />
            Enable immediately
          </label>

          <div className="admin-form-section-title">
            <strong>Monitored pages</strong>
            <button
              type="button"
              onClick={() => setForm((current) => ({ ...current, pages: [...current.pages, { ...emptyPageDraft }] }))}
            >
              <Plus size={15} />
              Add page
            </button>
          </div>

          <div className="admin-page-draft-list">
            {form.pages.map((page, index) => (
              <div className="admin-page-draft" key={`draft-${index}`}>
                <label>
                  Page name
                  <input value={page.name} onChange={(event) => updatePageDraft(index, { name: event.target.value })} placeholder="Current Notices" />
                </label>
                <label>
                  Page URL
                  <input value={page.url} onChange={(event) => updatePageDraft(index, { url: event.target.value })} placeholder="https://example.gov.in/notices" />
                </label>
                <label>
                  Type
                  <input value={page.page_type} onChange={(event) => updatePageDraft(index, { page_type: event.target.value })} placeholder="notice_listing" />
                </label>
                <label>
                  Priority
                  <input
                    type="number"
                    value={page.priority}
                    onChange={(event) => updatePageDraft(index, { priority: Number(event.target.value) })}
                  />
                </label>
                <label className="admin-checkbox-row">
                  <input
                    type="checkbox"
                    checked={page.enabled}
                    onChange={(event) => updatePageDraft(index, { enabled: event.target.checked })}
                  />
                  Enabled
                </label>
                <button type="button" aria-label="Remove page draft" onClick={() => removePageDraft(index)}>
                  <Trash2 size={15} />
                </button>
              </div>
            ))}
          </div>

          <div className="admin-form-actions">
            <button type="button" onClick={() => setForm(emptySourceForm)}>
              Reset
            </button>
            <button className="primary-button" type="submit" disabled={createMutation.isPending}>
              {createMutation.isPending ? <Loader2 className="spin" size={16} /> : <Plus size={16} />}
              Create Source
            </button>
          </div>
        </form>
      ) : null}

      <div className="admin-source-card-list">
        {sources.map((source) => {
          const pages = sourcePages.filter((page) => page.source_id === source.id || page.source_code === source.code);
          return (
            <details className="admin-source-card" key={source.id} open>
              <summary>
                <div>
                  <strong>{source.name}</strong>
                  <span>{source.code} | {source.jurisdiction} | {source.crawler_type}</span>
                </div>
                <div className="admin-source-status">
                  <span className={source.enabled ? "enabled" : "disabled"}>{source.enabled ? "Enabled" : "Disabled"}</span>
                  <span>{pages.length} pages</span>
                  <span>{compactNumber(source.consecutive_failures)} failures</span>
                </div>
              </summary>
              <div className="admin-source-body">
                <div className="admin-source-meta">
                  <a href={source.url} target="_blank" rel="noreferrer">
                    <ExternalLink size={15} />
                    Website
                  </a>
                  <span>Last checked {formatRelativeDate(source.last_checked_at)}</span>
                  <span>Status {source.last_status ?? "unknown"}</span>
                </div>
                <div className="row-actions">
                  <button type="button" onClick={() => void handleToggleSource(source)} disabled={busyAction === `source-${source.id}`}>
                    {busyAction === `source-${source.id}` ? <Loader2 className="spin" size={15} /> : <Settings size={15} />}
                    {source.enabled ? "Disable" : "Enable"}
                  </button>
                  <button
                    type="button"
                    onClick={() => void handleSourceCrawl(source)}
                    disabled={busyAction === `crawl-source-${source.id}`}
                  >
                    {busyAction === `crawl-source-${source.id}` ? <Loader2 className="spin" size={15} /> : <Play size={15} />}
                    Trigger Crawl
                  </button>
                  <button
                    type="button"
                    onClick={() => sourceDeleteMutation.mutate(source.id)}
                    disabled={sourceDeleteMutation.isPending}
                  >
                    <Trash2 size={15} />
                    Delete
                  </button>
                </div>
                <div className="admin-page-list">
                  {pages.map((page) => (
                    <div className="admin-page-row" key={page.id}>
                      <div>
                        <strong>{page.name}</strong>
                        <span>{page.page_type} | priority {page.priority} | last crawl {formatRelativeDate(page.last_crawled_at)}</span>
                        <a href={page.url} target="_blank" rel="noreferrer">{page.url}</a>
                      </div>
                      <div className="row-actions">
                        <button
                          type="button"
                          onClick={() => pageMutation.mutate({ pageId: page.id, enabled: !page.enabled })}
                          disabled={pageMutation.isPending}
                        >
                          <Settings size={15} />
                          {page.enabled ? "Disable" : "Enable"}
                        </button>
                        <button type="button" onClick={() => void handlePageCrawl(page)} disabled={busyAction === `crawl-page-${page.id}`}>
                          {busyAction === `crawl-page-${page.id}` ? <Loader2 className="spin" size={15} /> : <Play size={15} />}
                          Test Page
                        </button>
                        <button
                          type="button"
                          onClick={() => pageDeleteMutation.mutate(page.id)}
                          disabled={pageDeleteMutation.isPending}
                        >
                          <Trash2 size={15} />
                          Delete
                        </button>
                      </div>
                    </div>
                  ))}
                  {!pages.length ? (
                    <EmptyState title="No monitored pages" body="No source page rows are returned for this website." />
                  ) : null}
                </div>
              </div>
            </details>
          );
        })}
        {!sources.length ? <EmptyState title="No sources" body="The sources API returned no configured websites." /> : null}
      </div>
    </div>
  );
}

export function AdminPagesView() {
  return <AdminSourcesView />;
}

export function AdminRunsView() {
  const {
    runs,
    sourcePages,
    adminDocs,
    adminEvents,
    families,
    stakeholderViews,
    obligationGroups,
    activeDeadlines,
    ragStatus,
    ragQueue,
    busyAction,
    handleProcessRagJob,
    handleRequeueRagJobs,
    loadBaseData,
    loadRagData,
  } = useWorkspace();
  const versions = adminDocs.filter((doc) => doc.latest_version_id).length;
  const graphObjects = stakeholderViews.length + obligationGroups.reduce((sum, group) => sum + group.obligations.length, 0) + activeDeadlines.length;
  const latestRun = runs[0];
  return (
    <div className="page-stack ops-page admin-runs-console">
      <section className="ops-page-header premium-page-header">
        <div>
          <span>Operations Console</span>
          <h1>Crawl Runs</h1>
          <p>
            Latest run {latestRun ? `#${latestRun.id}` : "not available"} | documents {compactNumber(adminDocs.length)} |
            events {compactNumber(adminEvents.length)} | RAG ready {compactNumber(ragStatus?.ready ?? 0)}.
          </p>
        </div>
        <div className="ops-action-row">
          <button type="button" onClick={() => void loadBaseData()}>
            <RefreshCw size={16} />
            Refresh
          </button>
          <button type="button" onClick={() => void loadRagData()}>
            <TableProperties size={16} />
            RAG status
          </button>
        </div>
      </section>

      <section className="admin-run-health-grid">
        <span><strong>{compactNumber(sourcePages.length)}</strong> monitored pages</span>
        <span><strong>{compactNumber(adminDocs.length)}</strong> documents</span>
        <span><strong>{compactNumber(adminEvents.length)}</strong> events</span>
        <span><strong>{compactNumber(families.length)}</strong> families</span>
        <span><strong>{compactNumber(versions)}</strong> versions</span>
        <span><strong>{compactNumber(graphObjects)}</strong> graph objects</span>
        <span><strong>{compactNumber(ragStatus?.ready ?? 0)}</strong> RAG indexed</span>
        <span><strong>{compactNumber(ragQueue.length)}</strong> queued jobs</span>
      </section>

      <section className="admin-rag-inline-actions">
        <div>
          <strong>Hybrid RAG worker</strong>
          <p>Process one queued job at a time and requeue interrupted jobs without leaving this operational view.</p>
        </div>
        <div className="row-actions">
          <button type="button" onClick={() => void handleRequeueRagJobs()} disabled={busyAction === "rag-requeue"}>
            {busyAction === "rag-requeue" ? <Loader2 className="spin" size={15} /> : <RefreshCw size={15} />}
            Requeue interrupted
          </button>
          <button type="button" onClick={() => void handleProcessRagJob()} disabled={busyAction === "rag-process"}>
            {busyAction === "rag-process" ? <Loader2 className="spin" size={15} /> : <Play size={15} />}
            Process next job
          </button>
        </div>
      </section>

      <div className="admin-run-list">
        {runs.map((run) => {
          const started = new Date(run.started_at).getTime();
          const finished = run.finished_at ? new Date(run.finished_at).getTime() : Date.now();
          const duration = Number.isFinite(started) && Number.isFinite(finished)
            ? `${Math.max(1, Math.round((finished - started) / 1000))}s`
            : "n/a";
          const successRate = run.sources_attempted
            ? Math.round((run.sources_succeeded / run.sources_attempted) * 100)
            : 0;
          return (
            <details className="admin-run-card" key={run.id} open={run.id === latestRun?.id}>
              <summary>
                <div>
                  <strong>Run #{run.id}</strong>
                  <span>{formatRelativeDate(run.started_at)} | duration {duration}</span>
                </div>
                <div className="admin-run-status">
                  <span className={run.status.toLowerCase()}>{run.status}</span>
                  <span>{successRate}% success</span>
                  <span>{compactNumber(run.errors.length)} failures</span>
                </div>
              </summary>
              <div className="admin-run-body">
                <div className="admin-run-progress" aria-label={`Run ${run.id} success ${successRate}%`}>
                  <span style={{ width: `${successRate}%` }} />
                </div>
                <div className="admin-run-detail-grid">
                  <span><strong>Website</strong> Curated source set</span>
                  <span><strong>Pages crawled</strong> {compactNumber(sourcePages.length)}</span>
                  <span><strong>Sources</strong> {run.sources_succeeded}/{run.sources_attempted}</span>
                  <span><strong>Documents</strong> {compactNumber(run.docs_found)}</span>
                  <span><strong>Events</strong> {compactNumber(run.new_events)}</span>
                  <span><strong>Families</strong> {compactNumber(families.length)}</span>
                  <span><strong>Versions</strong> {compactNumber(versions)}</span>
                  <span><strong>Graph Objects</strong> {compactNumber(graphObjects)}</span>
                  <span><strong>RAG Indexed</strong> {compactNumber(ragStatus?.ready ?? 0)}</span>
                </div>
                <div className="admin-run-timeline">
                  <span>Started {formatRelativeDate(run.started_at)}</span>
                  <span>Finished {formatRelativeDate(run.finished_at)}</span>
                  <span>Status {run.status}</span>
                </div>
                {run.errors.length ? (
                  <div className="admin-run-errors">
                    {run.errors.slice(0, 4).map((error, index) => (
                      <code key={`${run.id}-error-${index}`}>{JSON.stringify(error)}</code>
                    ))}
                  </div>
                ) : (
                  <p className="muted">No errors returned for this run.</p>
                )}
              </div>
            </details>
          );
        })}
        {!runs.length ? <EmptyState title="No crawl runs" body="No crawl run rows are available yet." /> : null}
      </div>
    </div>
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
          ["Actionability", (row) => row.actionability ?? "n/a"],
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
          ["Version", (row) => row.latest_version_id ?? "n/a"],
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
          ["Type", (row) => row.document_type ?? "unknown"],
          ["Docs", (row) => compactNumber(row.document_count)],
          ["Versions", (row) => compactNumber(row.version_count)],
          ["Deadlines", (row) => compactNumber(row.deadline_count)],
        ]}
      />
    </Panel>
  );
}

export function AdminVersionsView() {
  const { adminDocs, families } = useWorkspace();
  return (
    <Panel title="Document Versions" icon={Layers3}>
      <AdminRows
        rows={adminDocs.filter((doc) => doc.latest_version_id)}
        columns={[
          ["Document", (row) => `#${row.id}`],
          ["Latest Version", (row) => row.latest_version_id ?? "n/a"],
          ["Family", (row) => row.family_title ?? "unassigned"],
          ["Family Docs", (row) => families.find((family) => String(family.family_id) === String(row.family_id))?.document_count ?? "n/a"],
          ["Hash", (row) => row.content_hash?.slice(0, 12) ?? row.file_hash?.slice(0, 12) ?? "n/a"],
          ["Fetched", (row) => formatRelativeDate(row.fetched_at)],
        ]}
      />
    </Panel>
  );
}

export function AdminGraphView() {
  const { stakeholderViews, obligationGroups, activeDeadlines, readinessStatus } = useWorkspace();
  if (readinessStatus.isLoading) return <LoadingState label="Loading graph intelligence..." />;
  if (readinessStatus.isError) {
    return <ErrorState title="Unable to load graph intelligence" error={readinessStatus.error} onRetry={readinessStatus.refetch} />;
  }
  const graphRows = [
    ...stakeholderViews.map((view) => ({
      type: "Stakeholder",
      name: view.stakeholder,
      count: view.counts.obligations ?? view.obligations.length,
      status: view.counts.deadlines ? "Deadline linked" : "No active deadlines",
    })),
    ...obligationGroups.map((group) => ({
      type: "Obligation Group",
      name: group.stakeholder,
      count: group.obligations.length,
      status: "Obligations extracted",
    })),
    ...activeDeadlines.map((deadline) => ({
      type: "Deadline",
      name: deadline.title,
      count: deadline.days_remaining ?? 0,
      status: deadline.deadline_type,
    })),
  ];
  return (
    <Panel title="Knowledge Graph" icon={Network}>
      <AdminRows
        rows={graphRows}
        columns={[
          ["Type", (row) => row.type],
          ["Name", (row) => <span className="table-title">{row.name}</span>],
          ["Count", (row) => compactNumber(Number(row.count))],
          ["Status", (row) => row.status],
        ]}
      />
    </Panel>
  );
}

export function AdminRagView() {
  const {
    ragStatus,
    ragChunks,
    ragSystemStatus,
    busyAction,
    loadRagData,
    handleProcessRagJob,
    handleRequeueRagJobs,
    handleEnqueueRagDocuments,
  } = useWorkspace();
  if (ragSystemStatus.isLoading) return <LoadingState label="Loading RAG status..." />;
  return (
    <div className="page-stack ops-page">
      {ragSystemStatus.isError ? (
        <ErrorState title="Unable to load RAG status" error={ragSystemStatus.error} onRetry={ragSystemStatus.refetch} />
      ) : null}
      <section className="ops-action-row">
        <button type="button" onClick={() => void loadRagData()}>
          <RefreshCw size={16} />
          Refresh
        </button>
        <button type="button" onClick={() => void handleRequeueRagJobs()} disabled={busyAction === "rag-requeue"}>
          {busyAction === "rag-requeue" ? <Loader2 className="spin" size={16} /> : <History size={16} />}
          Requeue processing
        </button>
        <button type="button" onClick={() => void handleProcessRagJob()} disabled={busyAction === "rag-process"}>
          {busyAction === "rag-process" ? <Loader2 className="spin" size={16} /> : <Play size={16} />}
          Process one
        </button>
        <button type="button" onClick={() => void handleEnqueueRagDocuments()} disabled={busyAction === "rag-enqueue"}>
          {busyAction === "rag-enqueue" ? <Loader2 className="spin" size={16} /> : <FileSearch size={16} />}
          Enqueue existing
        </button>
      </section>
      <section className="metric-grid">
        <MetricCard title="Chunks" value={ragStatus?.chunks ?? 0} Icon={TableProperties} tone="purple" />
        <MetricCard title="Embeddings" value={ragStatus?.embeddings ?? 0} Icon={CheckCircle2} tone="green" />
        <MetricCard title="Ready" value={ragStatus?.ready ?? 0} Icon={Gauge} tone="green" />
        <MetricCard title="Failed" value={ragStatus?.failed ?? 0} Icon={AlertCircle} tone="red" />
      </section>
      <Panel title="Document RAG Readiness" icon={TableProperties}>
        <AdminRows
          rows={ragChunks}
          columns={[
            ["Document", (row) => `#${row.document_id}`],
            ["Title", (row) => <span className="table-title">{row.title}</span>],
            ["Status", (row) => row.status],
            ["Chunks", (row) => `${row.embedded_chunk_count}/${row.chunk_count}`],
            ["Provider", (row) => row.provider ?? "n/a"],
            ["Model", (row) => row.model ?? "n/a"],
            ["Error", (row) => row.error ?? ""],
          ]}
        />
      </Panel>
    </div>
  );
}

export function AdminQueuesView() {
  const { ragQueue, ragSystemStatus, handleRequeueRagJobs, busyAction } = useWorkspace();
  if (ragSystemStatus.isLoading) return <LoadingState label="Loading queues..." />;
  return (
    <Panel
      title="Queues"
      icon={History}
      action={
        <button type="button" onClick={() => void handleRequeueRagJobs()} disabled={busyAction === "rag-requeue"}>
          {busyAction === "rag-requeue" ? <Loader2 className="spin" size={16} /> : <RefreshCw size={16} />}
          Requeue
        </button>
      }
    >
      <AdminRows
        rows={ragQueue}
        columns={[
          ["Job", (row) => `#${row.job_id}`],
          ["Document", (row) => `#${row.document_id}`],
          ["Version", (row) => row.version_id ?? "n/a"],
          ["Status", (row) => row.status],
          ["Attempts", (row) => row.attempts],
          ["Updated", (row) => formatRelativeDate(row.updated_at)],
          ["Last Error", (row) => row.last_error ?? ""],
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
          ["Issue Date", (row) => formatDate(row.checkpoint_issue_date)],
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
    <div className="page-stack ops-page">
      <section className="metric-grid">
        <MetricCard title="Candidates" value={analytics?.candidates ?? 0} Icon={FileSearch} tone="purple" />
        <MetricCard title="Accepted" value={analytics?.accepted_candidates ?? 0} Icon={CheckCircle2} tone="green" />
        <MetricCard title="Rejected" value={analytics?.rejected_candidates ?? 0} Icon={AlertCircle} tone="red" />
        <MetricCard title="Families" value={analytics?.families ?? 0} Icon={Network} tone="amber" />
      </section>
      <Panel title="Top Rejection Reasons" icon={Activity}>
        <AdminRows
          rows={analytics?.rejected_reasons ?? []}
          columns={[
            ["Reason", (row) => row.reason_code ?? "unknown"],
            ["Count", (row) => compactNumber(row.count)],
          ]}
        />
      </Panel>
    </div>
  );
}

export function AdminUsersView() {
  const { adminUsers, token, userEmail, setStatusMessage } = useWorkspace();
  const queryClient = useQueryClient();
  const roleMutation = useMutation({
    mutationFn: ({ userId, role }: { userId: string; role: "user" | "admin" }) =>
      updateAdminUserRole(userId, role, token),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.admin.users });
      setStatusMessage("User role updated.");
    },
    onError: (error) => setStatusMessage(error instanceof Error ? error.message : "Unable to update user role."),
  });
  const admins = adminUsers.filter((user) => user.role === "admin").length;
  return (
    <div className="page-stack ops-page admin-users-console">
      <section className="ops-page-header premium-page-header">
        <div>
          <span>Operations Console</span>
          <h1>Users</h1>
          <p>{adminUsers.length} profiles | {admins} admins | role changes are applied through the admin API.</p>
        </div>
      </section>
      <Panel title="User Management" icon={Users}>
        <AdminRows
          rows={adminUsers}
          columns={[
            ["Email", (row) => <span className="table-title">{row.email ?? "No email"}</span>],
            ["Name", (row) => row.full_name ?? "Not set"],
            ["Role", (row) => <span className={`admin-role-pill ${row.role}`}>{row.role}</span>],
            ["Alerts", (row) => (row.email_enabled ? `${row.frequency ?? "daily"} email` : "in-app only")],
            ["Topics", (row) => row.topics?.slice(0, 3).join(", ") || "All"],
            ["Created", (row) => formatRelativeDate(row.created_at)],
            [
              "Action",
              (row) => (
                <div className="row-actions">
                  <select
                    aria-label={`Role for ${row.email ?? row.id}`}
                    value={row.role}
                    onChange={(event) =>
                      roleMutation.mutate({
                        userId: row.id,
                        role: event.target.value as "user" | "admin",
                      })
                    }
                    disabled={roleMutation.isPending || row.email === userEmail}
                  >
                    <option value="user">user</option>
                    <option value="admin">admin</option>
                  </select>
                  {row.email === userEmail ? <span className="muted">Current user</span> : null}
                </div>
              ),
            ],
          ]}
        />
        {!adminUsers.length ? (
          <EmptyState title="No users" body="No profiles were returned by the admin users endpoint." />
        ) : null}
      </Panel>
    </div>
  );
}

export function AdminSubscriptionsView() {
  const { settings } = useWorkspace();
  return (
    <Panel title="Subscriptions" icon={Bell}>
      <div className="ops-summary-grid">
        <div className="detail-fact">
          <span>Email</span>
          <strong>{settings.email_enabled ? "Enabled" : "Disabled"}</strong>
        </div>
        <div className="detail-fact">
          <span>Frequency</span>
          <strong>{settings.frequency}</strong>
        </div>
        <div className="detail-fact">
          <span>Topics</span>
          <strong>{settings.topics.length}</strong>
        </div>
        <div className="detail-fact">
          <span>Sources</span>
          <strong>{settings.source_ids.length || "All"}</strong>
        </div>
      </div>
    </Panel>
  );
}
