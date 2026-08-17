"use client";

import { useMemo, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  ChevronDown,
  ChevronRight,
  Database,
  ExternalLink,
  Play,
  Plus,
  Power,
  Trash2,
} from "lucide-react";

import { ActionMenu } from "@/app/components/ui/ActionMenu";
import {
  Badge,
  StatusBadge,
  lastStatusLabel,
  sourceHealth,
} from "@/app/components/ui/Badge";
import { Button } from "@/app/components/ui/Button";
import { EmptyState } from "@/app/components/ui/EmptyState";
import { ErrorState } from "@/app/components/ui/ErrorState";
import { Fact, FactList, PageHeader } from "@/app/components/ui/PageHeader";
import { ConfirmDialog } from "@/app/components/ui/Overlay";
import { Pagination } from "@/app/components/ui/Pagination";
import { SkeletonCards } from "@/app/components/ui/Skeleton";
import {
  ActiveFilters,
  FilterSelect,
  FilterSheet,
  RefreshButton,
  SearchInput,
  Toolbar,
} from "@/app/components/ui/Toolbar";
import { deleteSource } from "@/lib/api";
import type { AdminSource } from "@/lib/api";
import { queryKeys, useAdminSourceListQuery } from "@/lib/queries";
import { formatRelativeDate } from "@/app/workspace/format";
import { useWorkspace } from "@/app/workspace/WorkspaceContext";

import { SourceCreateModal } from "./SourceCreateModal";
import { SourcePageList } from "./SourcePageList";

const PAGE_SIZE = 12;

const JURISDICTION_OPTIONS = [
  { value: "all", label: "Jurisdiction" },
  { value: "central", label: "Central" },
  { value: "state", label: "State" },
];

const STATUS_OPTIONS = [
  { value: "all", label: "Status" },
  { value: "enabled", label: "Enabled" },
  { value: "disabled", label: "Disabled" },
  { value: "error", label: "Error / degraded" },
];

const LAST_RUN_OPTIONS = [
  { value: "all", label: "Last crawl" },
  { value: "never", label: "Never crawled" },
  { value: "24h", label: "Last 24 hours" },
  { value: "7d", label: "Last 7 days" },
  { value: "30d", label: "Last 30 days" },
  { value: "older", label: "Older than 30 days" },
];

type Filters = {
  q: string;
  jurisdiction: string;
  status: string;
  last_run: string;
};

const EMPTY_FILTERS: Filters = {
  q: "",
  jurisdiction: "all",
  status: "all",
  last_run: "all",
};

function label(options: Array<{ value: string; label: string }>, value: string) {
  return options.find((option) => option.value === value)?.label ?? value;
}

export function AdminSourcesView() {
  const { token, busyAction, setStatusMessage, handleToggleSource, handleSourceCrawl, handlePageCrawl } =
    useWorkspace();
  const queryClient = useQueryClient();

  const [filters, setFilters] = useState<Filters>(EMPTY_FILTERS);
  const [page, setPage] = useState(1);
  const [expanded, setExpanded] = useState<number | null>(null);
  const [createOpen, setCreateOpen] = useState(false);
  const [pendingDelete, setPendingDelete] = useState<AdminSource | null>(null);

  const query = useAdminSourceListQuery(token, true, {
    ...filters,
    page,
    page_size: PAGE_SIZE,
  });

  function updateFilter(changes: Partial<Filters>) {
    setFilters((current) => ({ ...current, ...changes }));
    setPage(1);
  }

  function clearFilters() {
    setFilters(EMPTY_FILTERS);
    setPage(1);
  }

  function invalidate() {
    void queryClient.invalidateQueries({ queryKey: queryKeys.admin.sources });
    void queryClient.invalidateQueries({ queryKey: queryKeys.admin.pages });
    void queryClient.invalidateQueries({ queryKey: queryKeys.admin.analytics });
  }

  const deleteMutation = useMutation({
    mutationFn: (sourceId: number) => deleteSource(sourceId, token),
    onSuccess: () => {
      invalidate();
      setStatusMessage(`Deleted ${pendingDelete?.name ?? "source"}.`);
      setPendingDelete(null);
    },
    onError: (error) => {
      setStatusMessage(
        error instanceof Error ? error.message : "Unable to delete source.",
      );
      setPendingDelete(null);
    },
  });

  const activeFilters = useMemo(() => {
    const entries: Array<{ key: string; label: string; onRemove: () => void }> = [];
    if (filters.q) {
      entries.push({
        key: "q",
        label: `Search: ${filters.q}`,
        onRemove: () => updateFilter({ q: "" }),
      });
    }
    if (filters.jurisdiction !== "all") {
      entries.push({
        key: "jurisdiction",
        label: label(JURISDICTION_OPTIONS, filters.jurisdiction),
        onRemove: () => updateFilter({ jurisdiction: "all" }),
      });
    }
    if (filters.status !== "all") {
      entries.push({
        key: "status",
        label: label(STATUS_OPTIONS, filters.status),
        onRemove: () => updateFilter({ status: "all" }),
      });
    }
    if (filters.last_run !== "all") {
      entries.push({
        key: "last_run",
        label: label(LAST_RUN_OPTIONS, filters.last_run),
        onRemove: () => updateFilter({ last_run: "all" }),
      });
    }
    return entries;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filters]);

  const filterControls = (
    <>
      <FilterSelect
        label="Jurisdiction"
        value={filters.jurisdiction}
        options={JURISDICTION_OPTIONS}
        onChange={(value) => updateFilter({ jurisdiction: value })}
      />
      <FilterSelect
        label="Last crawl"
        value={filters.last_run}
        options={LAST_RUN_OPTIONS}
        onChange={(value) => updateFilter({ last_run: value })}
      />
      <FilterSelect
        label="Status"
        value={filters.status}
        options={STATUS_OPTIONS}
        onChange={(value) => updateFilter({ status: value })}
      />
    </>
  );

  const sources = query.data?.items ?? [];
  const total = query.data?.total ?? 0;
  const hasFilters = activeFilters.length > 0;

  return (
    <div className="rv-page">
      <PageHeader
        eyebrow="Operations"
        title="Sources"
        description="Manage monitored regulatory sources and their pages."
        actions={
          <>
            <RefreshButton
              onClick={() => void query.refetch()}
              loading={query.isFetching}
              label="Refresh source registry"
            />
            <Button variant="primary" Icon={Plus} onClick={() => setCreateOpen(true)}>
              Add source
            </Button>
          </>
        }
      />

      <Toolbar
        ariaLabel="Source filters"
        search={
          <SearchInput
            label="Search sources"
            placeholder="Search by name, code or website"
            value={filters.q}
            onChange={(value) => updateFilter({ q: value })}
          />
        }
        filters={
          <>
            <span className="rv-toolbar__desktop-filters">{filterControls}</span>
            <span className="rv-toolbar__mobile-filters">
              <FilterSheet
                title="Filter sources"
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
        <SkeletonCards count={4} lines={2} label="Loading sources" />
      ) : query.isError ? (
        <ErrorState
          title="Unable to load sources"
          body="We couldn't retrieve the source registry."
          error={query.error}
          onRetry={() => void query.refetch()}
          showTechnicalDetails
        />
      ) : sources.length ? (
        <>
          <ul className="rv-card-list">
            {sources.map((source) => (
              <SourceCard
                key={source.id}
                source={source}
                token={token}
                busyAction={busyAction}
                expanded={expanded === source.id}
                onToggleExpanded={() =>
                  setExpanded((current) => (current === source.id ? null : source.id))
                }
                onCrawl={() => handleSourceCrawl(source)}
                onToggleEnabled={() => handleToggleSource(source)}
                onDelete={() => setPendingDelete(source)}
                onTestPage={handlePageCrawl}
                onStatusMessage={setStatusMessage}
              />
            ))}
          </ul>
          <Pagination
            page={query.data?.page ?? 1}
            pageSize={query.data?.page_size ?? PAGE_SIZE}
            total={total}
            totalPages={query.data?.total_pages ?? 1}
            onPageChange={setPage}
            itemLabel="sources"
            busy={query.isFetching}
          />
        </>
      ) : hasFilters ? (
        <EmptyState
          title="No sources match your filters"
          body="Try a different jurisdiction, status or last-crawl window, or clear the filters to see the whole registry."
          Icon={Database}
          action={
            <Button variant="secondary" onClick={clearFilters}>
              Clear filters
            </Button>
          }
        />
      ) : (
        <EmptyState
          title="No sources yet"
          body="Add the first regulatory website you want Resolven to monitor. You can register its monitored pages at the same time."
          Icon={Database}
          action={
            <Button variant="primary" Icon={Plus} onClick={() => setCreateOpen(true)}>
              Add source
            </Button>
          }
        />
      )}

      <SourceCreateModal
        open={createOpen}
        token={token}
        onClose={() => setCreateOpen(false)}
        onCreated={(message) => {
          invalidate();
          void query.refetch();
          setStatusMessage(message);
        }}
      />

      <ConfirmDialog
        open={Boolean(pendingDelete)}
        title="Delete source?"
        body={
          <>
            <p className="rv-page-subtitle">
              {pendingDelete?.name} and its {pendingDelete?.page_count ?? 0} monitored
              page{pendingDelete?.page_count === 1 ? "" : "s"} will be removed from the
              registry and will stop being crawled.
            </p>
            <p className="rv-helper">
              Documents and events already collected from this source are kept.
            </p>
          </>
        }
        confirmLabel="Delete source"
        loading={deleteMutation.isPending}
        onCancel={() => setPendingDelete(null)}
        onConfirm={() => {
          if (pendingDelete) deleteMutation.mutate(pendingDelete.id);
        }}
      />
    </div>
  );
}

/**
 * One scannable source row: identity, health, the four facts an operator triages
 * on, then a single obvious primary action with everything else in a menu.
 * Monitored pages load only when the row is expanded.
 */
function SourceCard({
  source,
  token,
  busyAction,
  expanded,
  onToggleExpanded,
  onCrawl,
  onToggleEnabled,
  onDelete,
  onTestPage,
  onStatusMessage,
}: {
  source: AdminSource;
  token?: string;
  busyAction: string | null;
  expanded: boolean;
  onToggleExpanded: () => void;
  onCrawl: () => void;
  onToggleEnabled: () => void;
  onDelete: () => void;
  onTestPage: Parameters<typeof SourcePageList>[0]["onTestPage"];
  onStatusMessage: (message: string) => void;
}) {
  const health = sourceHealth(source);
  const failures = source.consecutive_failures ?? 0;

  return (
    <li className="rv-card">
      <div className="rv-card__header">
        <div className="rv-card__identity">
          <button
            type="button"
            className="rv-btn rv-btn--ghost rv-btn--icon rv-btn--sm"
            aria-expanded={expanded}
            aria-label={`${expanded ? "Collapse" : "Expand"} ${source.name}`}
            onClick={onToggleExpanded}
          >
            {expanded ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
          </button>
          <div>
            <h2 className="rv-card-title">{source.name}</h2>
            <p className="rv-cell-secondary">
              <Badge mono>{source.code}</Badge> {source.jurisdiction} ·{" "}
              {source.crawler_type} crawler
            </p>
          </div>
        </div>
        <div className="rv-btn-group">
          <StatusBadge kind="source" status={health} />
          <Button
            variant="secondary"
            size="sm"
            Icon={Play}
            loading={busyAction === `crawl-source-${source.id}`}
            onClick={onCrawl}
          >
            Trigger crawl
          </Button>
          <ActionMenu
            label={`More actions for ${source.name}`}
            items={[
              {
                id: "pages",
                label: expanded ? "Hide monitored pages" : "Manage pages",
                Icon: Database,
                onSelect: onToggleExpanded,
              },
              {
                id: "website",
                label: "Open website",
                Icon: ExternalLink,
                onSelect: () => window.open(source.url, "_blank", "noreferrer"),
              },
              {
                id: "toggle",
                label: source.enabled ? "Disable source" : "Enable source",
                Icon: Power,
                disabled: busyAction === `source-${source.id}`,
                onSelect: onToggleEnabled,
              },
              {
                id: "delete",
                label: "Delete source",
                Icon: Trash2,
                destructive: true,
                separated: true,
                onSelect: onDelete,
              },
            ]}
          />
        </div>
      </div>

      <FactList ariaLabel={`${source.name} crawl health`}>
        <Fact label="Last checked" value={formatRelativeDate(source.last_checked_at)} />
        <Fact
          label="Last page crawl"
          value={formatRelativeDate(source.last_page_crawled_at)}
        />
        <Fact label="Last response" value={lastStatusLabel(source.last_status)} />
        <Fact
          label="Pages monitored"
          value={`${source.enabled_page_count} of ${source.page_count} enabled`}
        />
        <Fact
          label="Consecutive failures"
          value={
            failures ? (
              <span className="rv-fact__value--danger">{failures}</span>
            ) : (
              "None"
            )
          }
        />
      </FactList>

      {expanded ? (
        <>
          <hr className="rv-divider" />
          <SourcePageList
            sourceId={source.id}
            sourceName={source.name}
            token={token}
            busyAction={busyAction}
            onTestPage={onTestPage}
            onStatusMessage={onStatusMessage}
          />
        </>
      ) : null}
    </li>
  );
}
