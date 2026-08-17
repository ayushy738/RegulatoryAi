"use client";

import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { History } from "lucide-react";

import { Badge, StatusBadge, normalizeRunStatus } from "@/app/components/ui/Badge";
import { Button } from "@/app/components/ui/Button";
import { DataTable } from "@/app/components/ui/DataTable";
import { EmptyState } from "@/app/components/ui/EmptyState";
import { ErrorState } from "@/app/components/ui/ErrorState";
import { Metric, MetricStrip, PageHeader } from "@/app/components/ui/PageHeader";
import { Pagination } from "@/app/components/ui/Pagination";
import { SkeletonMetrics, SkeletonTable } from "@/app/components/ui/Skeleton";
import {
  ActiveFilters,
  FilterSelect,
  FilterSheet,
  RefreshButton,
  SearchInput,
  Toolbar,
} from "@/app/components/ui/Toolbar";
import type { AdminCrawlRun } from "@/lib/api";
import { useAdminRunListQuery, useCrawlRunSourcesQuery } from "@/lib/queries";
import { formatDateTime, formatDuration } from "@/app/workspace/format";
import { useWorkspace } from "@/app/workspace/WorkspaceContext";

const PAGE_SIZE = 20;

const STATUS_OPTIONS = [
  { value: "all", label: "Status" },
  { value: "queued", label: "Queued" },
  { value: "running", label: "Running" },
  { value: "success", label: "Successful" },
  { value: "partial", label: "Partial" },
  { value: "failed", label: "Failed" },
];

const DATE_OPTIONS = [
  { value: "all", label: "Date" },
  { value: "today", label: "Today" },
  { value: "24h", label: "Last 24 hours" },
  { value: "7d", label: "Last 7 days" },
  { value: "30d", label: "Last 30 days" },
];

type Filters = {
  q: string;
  source_code: string;
  status: string;
  date_range: string;
};

const EMPTY_FILTERS: Filters = {
  q: "",
  source_code: "all",
  status: "all",
  date_range: "all",
};

function optionLabel(
  options: Array<{ value: string; label: string }>,
  value: string,
) {
  return options.find((option) => option.value === value)?.label ?? value;
}

function runSourceLabel(run: AdminCrawlRun) {
  const codes = run.source_codes ?? [];
  if (!codes.length) return "—";
  if (codes.length === 1) return codes[0];
  return `${codes[0]} +${codes.length - 1}`;
}

/** Operations dashboard for crawl health, progress and failures. */
export function AdminRunsView() {
  const router = useRouter();
  const { token } = useWorkspace();
  const [filters, setFilters] = useState<Filters>(EMPTY_FILTERS);
  const [page, setPage] = useState(1);

  const query = useAdminRunListQuery(token, true, {
    ...filters,
    page,
    page_size: PAGE_SIZE,
  });
  const sourceOptionsQuery = useCrawlRunSourcesQuery(token, true);

  const sourceOptions = useMemo(
    () => [
      { value: "all", label: "Source" },
      ...(sourceOptionsQuery.data ?? []).map((option) => ({
        value: option.code,
        label: option.code,
      })),
    ],
    [sourceOptionsQuery.data],
  );

  function updateFilter(changes: Partial<Filters>) {
    setFilters((current) => ({ ...current, ...changes }));
    setPage(1);
  }

  function clearFilters() {
    setFilters(EMPTY_FILTERS);
    setPage(1);
  }

  const activeFilters = useMemo(() => {
    const entries: Array<{ key: string; label: string; onRemove: () => void }> = [];
    if (filters.q) {
      entries.push({
        key: "q",
        label: `Search: ${filters.q}`,
        onRemove: () => updateFilter({ q: "" }),
      });
    }
    if (filters.source_code !== "all") {
      entries.push({
        key: "source",
        label: `Source: ${filters.source_code}`,
        onRemove: () => updateFilter({ source_code: "all" }),
      });
    }
    if (filters.status !== "all") {
      entries.push({
        key: "status",
        label: optionLabel(STATUS_OPTIONS, filters.status),
        onRemove: () => updateFilter({ status: "all" }),
      });
    }
    if (filters.date_range !== "all") {
      entries.push({
        key: "date",
        label: optionLabel(DATE_OPTIONS, filters.date_range),
        onRemove: () => updateFilter({ date_range: "all" }),
      });
    }
    return entries;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filters]);

  const filterControls = (
    <>
      <FilterSelect
        label="Source"
        value={filters.source_code}
        options={sourceOptions}
        onChange={(value) => updateFilter({ source_code: value })}
      />
      <FilterSelect
        label="Status"
        value={filters.status}
        options={STATUS_OPTIONS}
        onChange={(value) => updateFilter({ status: value })}
      />
      <FilterSelect
        label="Date"
        value={filters.date_range}
        options={DATE_OPTIONS}
        onChange={(value) => updateFilter({ date_range: value })}
      />
    </>
  );

  const runs = query.data?.items ?? [];
  const summary = query.data?.summary;
  const hasFilters = activeFilters.length > 0;

  function openRun(run: AdminCrawlRun) {
    router.push(`/admin/runs/${run.id}`);
  }

  return (
    <div className="rv-page">
      <PageHeader
        eyebrow="Operations"
        title="Crawl runs"
        description="Monitor crawl health, progress and failures."
        actions={
          <RefreshButton
            onClick={() => void query.refetch()}
            loading={query.isFetching}
            label="Refresh crawl runs"
          />
        }
      />

      {query.isLoading ? (
        <SkeletonMetrics count={5} />
      ) : summary ? (
        <MetricStrip ariaLabel="Crawl run summary">
          <Metric label="Runs today" value={summary.runs_today} />
          <Metric
            label="Running"
            value={summary.running + summary.queued}
            hint={summary.queued ? `${summary.queued} queued` : undefined}
          />
          <Metric label="Successful" value={summary.success} tone="success" hint="Last 7 days" />
          <Metric label="Partial" value={summary.partial} tone="warning" hint="Last 7 days" />
          <Metric label="Failed" value={summary.failed} tone="danger" hint="Last 7 days" />
        </MetricStrip>
      ) : null}

      <Toolbar
        ariaLabel="Crawl run filters"
        search={
          <SearchInput
            label="Search crawl runs"
            placeholder="Search by run ID or source"
            value={filters.q}
            onChange={(value) => updateFilter({ q: value })}
          />
        }
        filters={
          <>
            <span className="rv-toolbar__desktop-filters">{filterControls}</span>
            <span className="rv-toolbar__mobile-filters">
              <FilterSheet
                title="Filter crawl runs"
                activeCount={activeFilters.filter((entry) => entry.key !== "q").length}
                onClear={clearFilters}
              >
                {filterControls}
              </FilterSheet>
            </span>
          </>
        }
      />

      {hasFilters ? (
        <ActiveFilters entries={activeFilters} onClearAll={clearFilters} />
      ) : null}

      {query.isLoading ? (
        <SkeletonTable rows={8} columns={6} label="Loading crawl runs" />
      ) : query.isError ? (
        <ErrorState
          title="Unable to load crawl runs"
          body="We couldn't retrieve crawl telemetry."
          error={query.error}
          onRetry={() => void query.refetch()}
          showTechnicalDetails
        />
      ) : runs.length ? (
        <>
          <DataTable
            caption="Crawl runs"
            rows={runs}
            rowKey={(run) => run.id}
            onRowActivate={openRun}
            rowActionLabel={(run) => `Open crawl run ${run.id}`}
            columns={[
              {
                id: "run",
                header: "Run",
                mobilePrimary: true,
                render: (run) => (
                  <>
                    <span className="rv-cell-primary">#{run.id}</span>
                    <span className="rv-cell-secondary">{runSourceLabel(run)}</span>
                  </>
                ),
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
                id: "pages",
                header: "Pages",
                numeric: true,
                render: (run) =>
                  run.pages_attempted === null || run.pages_attempted === undefined
                    ? "—"
                    : `${run.pages_succeeded ?? 0}/${run.pages_attempted}`,
              },
              {
                id: "documents",
                header: "Documents",
                numeric: true,
                render: (run) => run.documents_discovered ?? run.docs_found ?? 0,
              },
              {
                id: "failures",
                header: "Failures",
                numeric: true,
                render: (run) =>
                  run.errors.length ? (
                    <Badge tone="danger">{run.errors.length}</Badge>
                  ) : (
                    <span className="rv-meta">None</span>
                  ),
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
                  <Button variant="secondary" size="sm" onClick={() => openRun(run)}>
                    View
                  </Button>
                ),
              },
            ]}
            mobileActions={(run) => (
              <Button variant="secondary" size="sm" block onClick={() => openRun(run)}>
                View run #{run.id}
              </Button>
            )}
          />
          <Pagination
            page={query.data?.page ?? 1}
            pageSize={query.data?.page_size ?? PAGE_SIZE}
            total={query.data?.total ?? 0}
            totalPages={query.data?.total_pages ?? 1}
            onPageChange={setPage}
            itemLabel="crawl runs"
            busy={query.isFetching}
          />
        </>
      ) : hasFilters ? (
        <EmptyState
          title="No crawl runs match your filters"
          body="Try changing the date, source or status filter."
          Icon={History}
          action={
            <Button variant="secondary" onClick={clearFilters}>
              Clear filters
            </Button>
          }
        />
      ) : (
        <EmptyState
          title="No crawl runs yet"
          body="Trigger a crawl from a source on the Sources page and its run will appear here."
          Icon={History}
        />
      )}
    </div>
  );
}
