"use client";

import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  ExternalLink,
  Pencil,
  Play,
  Plus,
  Power,
  RotateCcw,
  Trash2,
} from "lucide-react";

import { ActionMenu } from "@/app/components/ui/ActionMenu";
import { Badge } from "@/app/components/ui/Badge";
import { Button } from "@/app/components/ui/Button";
import { EmptyState } from "@/app/components/ui/EmptyState";
import { ErrorState } from "@/app/components/ui/ErrorState";
import { ConfirmDialog } from "@/app/components/ui/Overlay";
import { SectionHeader } from "@/app/components/ui/PageHeader";
import { Skeleton } from "@/app/components/ui/Skeleton";
import {
  deleteSourcePage,
  permanentlyDeleteSourcePage,
  restoreSourcePage,
  updateSourcePage,
} from "@/lib/api";
import type { SourcePage } from "@/lib/api";
import {
  queryKeys,
  useRetiredSourcePagesQuery,
  useSourceDetailPagesQuery,
} from "@/lib/queries";
import { formatDate, formatRelativeDate } from "@/app/workspace/format";

import { SourcePageModal } from "./SourcePageModal";

/**
 * Monitored pages for one source. Kept compact: one row per page with the
 * primary action (Test) visible and everything else in an overflow menu.
 *
 * Removal stays two-tier, matching the backend: "Remove" retires a page
 * reversibly, and permanent deletion of the configuration is only reachable
 * from the retired list behind its own confirmation.
 */
export function SourcePageList({
  sourceId,
  sourceName,
  token,
  busyAction,
  onTestPage,
  onStatusMessage,
}: {
  sourceId: number;
  sourceName: string;
  token?: string;
  busyAction: string | null;
  onTestPage: (page: SourcePage) => void;
  onStatusMessage: (message: string) => void;
}) {
  const queryClient = useQueryClient();
  const pagesQuery = useSourceDetailPagesQuery(sourceId, token, true);
  const [showRetired, setShowRetired] = useState(false);
  const retiredQuery = useRetiredSourcePagesQuery(sourceId, token, showRetired);
  const [addOpen, setAddOpen] = useState(false);
  const [editing, setEditing] = useState<SourcePage | null>(null);
  const [pendingRemove, setPendingRemove] = useState<SourcePage | null>(null);
  const [pendingPurge, setPendingPurge] = useState<SourcePage | null>(null);

  function invalidate() {
    void queryClient.invalidateQueries({
      queryKey: queryKeys.admin.sourcePages(sourceId),
    });
    void queryClient.invalidateQueries({
      queryKey: queryKeys.admin.retiredSourcePages(sourceId),
    });
    void queryClient.invalidateQueries({ queryKey: queryKeys.admin.sources });
    void queryClient.invalidateQueries({ queryKey: queryKeys.admin.pages });
  }

  function reportError(error: unknown, fallback: string) {
    onStatusMessage(error instanceof Error ? error.message : fallback);
  }

  const toggleMutation = useMutation({
    mutationFn: ({ pageId, enabled }: { pageId: number; enabled: boolean }) =>
      updateSourcePage(pageId, { enabled }, token),
    onSuccess: (page) => {
      invalidate();
      onStatusMessage(`${page.enabled ? "Enabled" : "Disabled"} "${page.name}".`);
    },
    onError: (error) => reportError(error, "Unable to update page."),
  });

  const removeMutation = useMutation({
    mutationFn: (pageId: number) => deleteSourcePage(pageId, token),
    onSuccess: () => {
      setPendingRemove(null);
      invalidate();
      onStatusMessage(
        "Page removed from monitoring. Configuration and history were preserved.",
      );
    },
    onError: (error) => reportError(error, "Unable to remove page."),
  });

  const restoreMutation = useMutation({
    mutationFn: (pageId: number) => restoreSourcePage(pageId, token),
    onSuccess: () => {
      invalidate();
      onStatusMessage(
        "Page restored. It will be crawled again only if the source and page are enabled.",
      );
    },
    onError: (error) => reportError(error, "Unable to restore page."),
  });

  const purgeMutation = useMutation({
    mutationFn: (pageId: number) => permanentlyDeleteSourcePage(pageId, token),
    onSuccess: () => {
      setPendingPurge(null);
      invalidate();
      onStatusMessage(
        "Page configuration permanently deleted. Regulatory data was not removed.",
      );
    },
    onError: (error) => reportError(error, "Unable to permanently delete page."),
  });

  const pages = (pagesQuery.data ?? []).filter((page) => !page.deleted_at);
  const retiredPages = retiredQuery.data ?? [];

  return (
    <div className="rv-section">
      <SectionHeader
        as="h3"
        title="Monitored pages"
        count={pagesQuery.isSuccess ? `${pages.length}` : undefined}
        actions={
          <Button variant="secondary" size="sm" Icon={Plus} onClick={() => setAddOpen(true)}>
            Add page
          </Button>
        }
      />

      {pagesQuery.isLoading ? (
        <div className="rv-stack" aria-busy="true">
          <Skeleton height={44} />
          <Skeleton height={44} />
        </div>
      ) : pagesQuery.isError ? (
        <ErrorState
          compact
          title="Unable to load monitored pages"
          body="The page registry for this source could not be retrieved."
          error={pagesQuery.error}
          onRetry={() => pagesQuery.refetch()}
          showTechnicalDetails
        />
      ) : pages.length ? (
        <ul className="rv-page-rows">
          {pages.map((page) => (
            <li className="rv-page-row" key={page.id}>
              <div className="rv-page-row__main">
                <span className="rv-cell-primary">{page.name}</span>
                <a
                  className="rv-page-row__url"
                  href={page.url}
                  target="_blank"
                  rel="noreferrer"
                >
                  {page.url}
                </a>
                <div className="rv-page-row__facts">
                  <Badge mono>{page.page_type}</Badge>
                  <span className="rv-meta">Priority {page.priority}</span>
                  {page.enabled ? (
                    <Badge tone="success">Enabled</Badge>
                  ) : (
                    <Badge>Disabled</Badge>
                  )}
                  <span className="rv-meta">
                    Last crawl {formatRelativeDate(page.last_crawled_at)}
                  </span>
                </div>
              </div>
              <div className="rv-page-row__actions">
                <Button
                  variant="secondary"
                  size="sm"
                  Icon={Play}
                  loading={busyAction === `crawl-page-${page.id}`}
                  onClick={() => onTestPage(page)}
                >
                  Test
                </Button>
                <ActionMenu
                  label={`More actions for ${page.name}`}
                  items={[
                    {
                      id: "edit",
                      label: "Edit page",
                      Icon: Pencil,
                      onSelect: () => setEditing(page),
                    },
                    {
                      id: "open",
                      label: "Open page",
                      Icon: ExternalLink,
                      onSelect: () => window.open(page.url, "_blank", "noreferrer"),
                    },
                    {
                      id: "toggle",
                      label: page.enabled ? "Disable page" : "Enable page",
                      Icon: Power,
                      disabled: toggleMutation.isPending,
                      onSelect: () =>
                        toggleMutation.mutate({
                          pageId: page.id,
                          enabled: !page.enabled,
                        }),
                    },
                    {
                      id: "remove",
                      label: "Remove",
                      Icon: Trash2,
                      destructive: true,
                      separated: true,
                      onSelect: () => setPendingRemove(page),
                    },
                  ]}
                />
              </div>
            </li>
          ))}
        </ul>
      ) : (
        <EmptyState
          compact
          title="No monitored pages"
          body="This source has no pages yet, so crawls have nothing to visit. Add the listing pages that publish orders, notices or consultations."
          action={
            <Button variant="primary" size="sm" Icon={Plus} onClick={() => setAddOpen(true)}>
              Add page
            </Button>
          }
        />
      )}

      <details
        className="rv-disclosure"
        onToggle={(event) => setShowRetired(event.currentTarget.open)}
      >
        <summary>Show retired pages</summary>
        <div className="rv-disclosure__content">
          {retiredQuery.isLoading ? (
            <Skeleton height={44} />
          ) : retiredQuery.isError ? (
            <ErrorState
              compact
              title="Unable to load retired pages"
              body="Retired page configurations could not be retrieved."
              error={retiredQuery.error}
              onRetry={() => retiredQuery.refetch()}
              showTechnicalDetails
            />
          ) : retiredPages.length ? (
            <ul className="rv-page-rows">
              {retiredPages.map((page) => (
                <li className="rv-page-row rv-page-row--retired" key={`retired-${page.id}`}>
                  <div className="rv-page-row__main">
                    <span className="rv-cell-primary">{page.name}</span>
                    <a
                      className="rv-page-row__url"
                      href={page.url}
                      target="_blank"
                      rel="noreferrer"
                    >
                      {page.url}
                    </a>
                    <div className="rv-page-row__facts">
                      <Badge tone="warning">Retired</Badge>
                      <span className="rv-meta">Retired {formatDate(page.deleted_at)}</span>
                      <span className="rv-meta">
                        Retired by {page.deleted_by ?? "unknown"}
                      </span>
                    </div>
                  </div>
                  <div className="rv-page-row__actions">
                    <Button
                      variant="secondary"
                      size="sm"
                      Icon={RotateCcw}
                      loading={restoreMutation.isPending}
                      onClick={() => restoreMutation.mutate(page.id)}
                    >
                      Restore
                    </Button>
                    <ActionMenu
                      label={`More actions for retired page ${page.name}`}
                      items={[
                        {
                          id: "purge",
                          label: "Permanently delete",
                          Icon: Trash2,
                          destructive: true,
                          onSelect: () => setPendingPurge(page),
                        },
                      ]}
                    />
                  </div>
                </li>
              ))}
            </ul>
          ) : (
            <EmptyState
              compact
              title="No retired pages"
              body="Pages you remove from monitoring will appear here. You can restore them or permanently delete their configuration."
            />
          )}
        </div>
      </details>

      <SourcePageModal
        open={addOpen}
        sourceId={sourceId}
        sourceName={sourceName}
        token={token}
        onClose={() => setAddOpen(false)}
        onSaved={(message) => {
          invalidate();
          onStatusMessage(message);
        }}
      />
      <SourcePageModal
        open={Boolean(editing)}
        sourceId={sourceId}
        sourceName={sourceName}
        page={editing}
        token={token}
        onClose={() => setEditing(null)}
        onSaved={(message) => {
          invalidate();
          onStatusMessage(message);
        }}
      />

      <ConfirmDialog
        open={Boolean(pendingRemove)}
        title="Remove this page from monitoring?"
        body={
          <>
            <p>
              Monitoring will stop, but the page configuration and history will be
              preserved. You can restore it later.
            </p>
            <p>
              &quot;{pendingRemove?.name ?? ""}&quot; will no longer be crawled for this
              source.
            </p>
          </>
        }
        confirmLabel="Remove page"
        destructive
        loading={removeMutation.isPending}
        onCancel={() => {
          if (!removeMutation.isPending) setPendingRemove(null);
        }}
        onConfirm={() => {
          if (pendingRemove) removeMutation.mutate(pendingRemove.id);
        }}
      />

      <ConfirmDialog
        open={Boolean(pendingPurge)}
        title="Permanently delete this source page?"
        body={
          <>
            <p>
              This will permanently remove this page configuration. This action cannot be
              undone.
            </p>
            <p>
              This does not delete regulatory documents, document versions, events, RAG
              data, or crawl history that were already created from this page.
            </p>
          </>
        }
        confirmLabel="Permanently delete"
        destructive
        loading={purgeMutation.isPending}
        onCancel={() => {
          if (!purgeMutation.isPending) setPendingPurge(null);
        }}
        onConfirm={() => {
          if (pendingPurge) purgeMutation.mutate(pendingPurge.id);
        }}
      />
    </div>
  );
}
