"use client";

import { useId, useMemo, useState, type FormEvent } from "react";

import {
  useResearchSessionExport,
  useResearchSessionLifecycle,
  useResearchSessions,
  useResearchWorkspaceScope,
} from "@/lib/ask-ai-data";
import type {
  AskSession,
  AskSessionExport,
  AskSessionLifecycleAction,
} from "@/lib/ask-ai-sessions";

type SessionGroup = Readonly<{
  label: string;
  sessions: readonly AskSession[];
}>;

export type ResearchExportDownloader = (
  exported: AskSessionExport,
) => void;

function sessionTitle(session: AskSession) {
  return session.title?.trim() || "Untitled research";
}

function safeExportName(value: string) {
  const normalized = value
    .normalize("NFKD")
    .replace(/[^\w.-]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 80);
  return normalized || "research-session";
}

export const downloadResearchSessionExport: ResearchExportDownloader = (
  exported,
) => {
  const blob = new Blob([JSON.stringify(exported, null, 2)], {
    type: "application/json",
  });
  const target = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = target;
  anchor.download = `${safeExportName(sessionTitle(exported.session))}.json`;
  document.body.append(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(target);
};

function sessionModes(session: AskSession) {
  return (["official", "general", "live"] as const).filter((mode) => {
    const value = session.knowledge_mode_summary[mode];
    return (
      value === true ||
      (typeof value === "number" && value > 0) ||
      (typeof value === "string" && value.trim().length > 0)
    );
  });
}

function groupSessionsByRecency(
  sessions: readonly AskSession[],
  now: Date,
): SessionGroup[] {
  const startOfToday = new Date(
    now.getFullYear(),
    now.getMonth(),
    now.getDate(),
  ).getTime();
  const grouped = new Map<string, AskSession[]>([
    ["Today", []],
    ["Previous 7 days", []],
    ["Earlier", []],
  ]);
  for (const session of sessions) {
    const timestamp = new Date(
      session.last_message_at ?? session.updated_at,
    );
    const startOfSessionDay = new Date(
      timestamp.getFullYear(),
      timestamp.getMonth(),
      timestamp.getDate(),
    ).getTime();
    const elapsedDays = Math.floor(
      (startOfToday - startOfSessionDay) / 86_400_000,
    );
    const label =
      elapsedDays <= 0
        ? "Today"
        : elapsedDays <= 7
          ? "Previous 7 days"
          : "Earlier";
    grouped.get(label)?.push(session);
  }
  return [...grouped.entries()]
    .filter(([, items]) => items.length > 0)
    .map(([label, items]) => ({ label, sessions: items }));
}

function uniqueSessions(sessions: readonly AskSession[]) {
  const seen = new Set<string>();
  return sessions.filter((session) => {
    if (seen.has(session.id)) return false;
    seen.add(session.id);
    return true;
  });
}

export function ResearchSessionRail({
  activeSessionId,
  onSelectSession,
  onSessionUnavailable,
  downloadExport = downloadResearchSessionExport,
  now = new Date(),
}: {
  activeSessionId: string | null;
  onSelectSession: (session: AskSession) => void;
  onSessionUnavailable?: (sessionId: string) => void;
  downloadExport?: ResearchExportDownloader;
  now?: Date;
}) {
  const generatedId = useId().replaceAll(":", "");
  const queryId = `research-session-query-${generatedId}`;
  const entityId = `research-session-entity-${generatedId}`;
  const modeId = `research-session-mode-${generatedId}`;
  const scope = useResearchWorkspaceScope();
  const lifecycle = useResearchSessionLifecycle();
  const exporter = useResearchSessionExport();
  const [view, setView] = useState<"active" | "archived">("active");
  const [queryInput, setQueryInput] = useState("");
  const [entityInput, setEntityInput] = useState("");
  const [modeInput, setModeInput] =
    useState<"" | "official" | "general" | "live">("");
  const [filters, setFilters] = useState<{
    q?: string;
    entity?: string;
    knowledge_mode?: "official" | "general" | "live";
  }>({});
  const [renaming, setRenaming] = useState<AskSession | null>(null);
  const [renameValue, setRenameValue] = useState("");
  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(
    null,
  );
  const [statusMessage, setStatusMessage] = useState("");
  const [errorMessage, setErrorMessage] = useState("");
  const hasFilters = Object.keys(filters).length > 0;
  const sessionsQuery = useResearchSessions({
    ...filters,
    archived: view === "archived",
  });
  const pinnedQuery = useResearchSessions({
    pinned: true,
    archived: false,
    enabled: view === "active" && !hasFilters,
  });
  const sessions = uniqueSessions(
    sessionsQuery.data?.pages.flatMap((page) => page.items) ?? [],
  );
  const pinnedSessions = uniqueSessions(
    pinnedQuery.data?.pages.flatMap((page) => page.items) ?? [],
  );
  const recentSessions =
    view === "active" && !hasFilters
      ? sessions.filter((session) => !session.is_pinned)
      : sessions;
  const groups = useMemo(
    () => groupSessionsByRecency(recentSessions, now),
    [now, recentSessions],
  );
  const actionPending = lifecycle.isPending || exporter.isPending;

  function submitSearch(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const q = queryInput.trim();
    const entity = entityInput.trim();
    setFilters({
      ...(q ? { q } : {}),
      ...(entity ? { entity } : {}),
      ...(modeInput ? { knowledge_mode: modeInput } : {}),
    });
  }

  function clearSearch() {
    setQueryInput("");
    setEntityInput("");
    setModeInput("");
    setFilters({});
  }

  async function runLifecycle(
    action: AskSessionLifecycleAction,
    successMessage: string,
  ) {
    setErrorMessage("");
    setStatusMessage("");
    try {
      const result = await lifecycle.mutateAsync(action);
      setStatusMessage(successMessage);
      if (result.type === "deleted") {
        setConfirmDeleteId(null);
        onSessionUnavailable?.(result.sessionId);
      } else if (result.action === "duplicate") {
        onSelectSession(result.session);
      } else if (result.action === "archive") {
        onSessionUnavailable?.(action.session_id);
      }
      return result;
    } catch {
      setErrorMessage(
        "The session action could not be completed. Your research is unchanged.",
      );
      return null;
    }
  }

  async function exportSession(session: AskSession) {
    setErrorMessage("");
    setStatusMessage("");
    try {
      const exported = await exporter.mutateAsync(session.id);
      downloadExport(exported);
      setStatusMessage(`Exported ${sessionTitle(session)}.`);
    } catch {
      setErrorMessage(
        "The research export could not be prepared. Your research is unchanged.",
      );
    }
  }

  function renderSession(session: AskSession) {
    const title = sessionTitle(session);
    const modes = sessionModes(session);
    const isRenaming = renaming?.id === session.id;
    const isConfirmingDelete = confirmDeleteId === session.id;
    return (
      <li
        key={session.id}
        className="research-session-item"
        data-active={activeSessionId === session.id ? "true" : "false"}
      >
        <button
          type="button"
          className="research-session-select"
          aria-current={activeSessionId === session.id ? "page" : undefined}
          onClick={() => onSelectSession(session)}
        >
          <span>{title}</span>
          <time dateTime={session.updated_at}>
            {new Intl.DateTimeFormat(undefined, {
              month: "short",
              day: "numeric",
            }).format(new Date(session.updated_at))}
          </time>
        </button>
        <div className="research-session-indicators">
          {session.primary_entity ? (
            <span>{session.primary_entity}</span>
          ) : null}
          {modes.map((mode) => (
            <span key={mode}>{mode}</span>
          ))}
        </div>
        {isRenaming ? (
          <form
            className="research-session-rename"
            aria-label={`Rename ${title}`}
            onSubmit={(event) => {
              event.preventDefault();
              void runLifecycle(
                {
                  type: "patch",
                  session_id: session.id,
                  patch: { title: renameValue },
                },
                `Renamed research to ${renameValue.trim()}.`,
              ).then((result) => {
                if (result) setRenaming(null);
              });
            }}
          >
            <label htmlFor={`rename-${generatedId}-${session.id}`}>
              Research title
            </label>
            <input
              id={`rename-${generatedId}-${session.id}`}
              value={renameValue}
              maxLength={200}
              required
              onChange={(event) => setRenameValue(event.target.value)}
            />
            <div>
              <button
                type="submit"
                disabled={actionPending || !renameValue.trim()}
              >
                Save name
              </button>
              <button
                type="button"
                disabled={actionPending}
                onClick={() => setRenaming(null)}
              >
                Cancel
              </button>
            </div>
          </form>
        ) : (
          <div
            className="research-session-actions"
            role="group"
            aria-label={`Actions for ${title}`}
          >
            <button
              type="button"
              disabled={actionPending || !scope.enabled}
              onClick={() => {
                setRenaming(session);
                setRenameValue(title);
              }}
            >
              Rename
            </button>
            {session.archived_at === null ? (
              <button
                type="button"
                disabled={actionPending || !scope.enabled}
                onClick={() =>
                  void runLifecycle(
                    {
                      type: "patch",
                      session_id: session.id,
                      patch: { is_pinned: !session.is_pinned },
                    },
                    session.is_pinned
                      ? `Unpinned ${title}.`
                      : `Pinned ${title}.`,
                  )
                }
              >
                {session.is_pinned ? "Unpin" : "Pin"}
              </button>
            ) : null}
            <button
              type="button"
              disabled={actionPending || !scope.enabled}
              onClick={() =>
                void runLifecycle(
                  { type: "duplicate", session_id: session.id },
                  `Duplicated ${title}.`,
                )
              }
            >
              Duplicate
            </button>
            <button
              type="button"
              disabled={actionPending || !scope.enabled}
              onClick={() => void exportSession(session)}
            >
              Export
            </button>
            <button
              type="button"
              disabled={actionPending || !scope.enabled}
              onClick={() =>
                void runLifecycle(
                  {
                    type:
                      session.archived_at === null ? "archive" : "restore",
                    session_id: session.id,
                  },
                  session.archived_at === null
                    ? `Archived ${title}.`
                    : `Restored ${title}.`,
                )
              }
            >
              {session.archived_at === null ? "Archive" : "Restore"}
            </button>
            <button
              type="button"
              disabled={actionPending || !scope.enabled}
              onClick={() => setConfirmDeleteId(session.id)}
            >
              Delete
            </button>
          </div>
        )}
        {isConfirmingDelete ? (
          <div className="research-session-delete-confirmation" role="alert">
            <p>Delete this research workspace?</p>
            <button
              type="button"
              disabled={actionPending}
              onClick={() =>
                void runLifecycle(
                  { type: "delete", session_id: session.id },
                  `Deleted ${title}.`,
                )
              }
            >
              Confirm delete
            </button>
            <button
              type="button"
              disabled={actionPending}
              onClick={() => setConfirmDeleteId(null)}
            >
              Keep research
            </button>
          </div>
        ) : null}
      </li>
    );
  }

  const noResults =
    sessionsQuery.isSuccess &&
    sessions.length === 0 &&
    (!pinnedQuery.isSuccess || pinnedSessions.length === 0);

  return (
    <div className="research-session-rail">
      <form
        className="research-session-search"
        aria-label="Search research conversations"
        onSubmit={submitSearch}
      >
        <label htmlFor={queryId}>Search conversations</label>
        <input
          id={queryId}
          type="search"
          value={queryInput}
          maxLength={200}
          placeholder="Title, content, entity, or source"
          onChange={(event) => setQueryInput(event.target.value)}
        />
        <label htmlFor={entityId}>Entity filter</label>
        <input
          id={entityId}
          value={entityInput}
          maxLength={200}
          onChange={(event) => setEntityInput(event.target.value)}
        />
        <label htmlFor={modeId}>Knowledge mode</label>
        <select
          id={modeId}
          value={modeInput}
          onChange={(event) =>
            setModeInput(
              event.target.value as
                | ""
                | "official"
                | "general"
                | "live",
            )
          }
        >
          <option value="">All modes</option>
          <option value="official">Official corpus</option>
          <option value="general">General AI</option>
          <option value="live">Live intelligence</option>
        </select>
        <div>
          <button type="submit">Search</button>
          {hasFilters ? (
            <button type="button" onClick={clearSearch}>
              Clear
            </button>
          ) : null}
        </div>
      </form>

      <div
        className="research-session-view-switch"
        role="group"
        aria-label="Session view"
      >
        <button
          type="button"
          aria-pressed={view === "active"}
          onClick={() => setView("active")}
        >
          Active
        </button>
        <button
          type="button"
          aria-pressed={view === "archived"}
          onClick={() => setView("archived")}
        >
          Archived
        </button>
      </div>

      {statusMessage ? (
        <p className="research-session-status" role="status">
          {statusMessage}
        </p>
      ) : null}
      {errorMessage ? (
        <p className="research-session-error" role="alert">
          {errorMessage}
        </p>
      ) : null}
      {!scope.enabled ? (
        <p className="research-session-status" role="status">
          Research sessions are unavailable until authentication is ready.
        </p>
      ) : null}
      {scope.enabled &&
      (sessionsQuery.isPending ||
        (pinnedQuery.isPending && view === "active" && !hasFilters)) ? (
        <p className="research-session-status" role="status">
          Loading research sessions...
        </p>
      ) : null}
      {sessionsQuery.isError || pinnedQuery.isError ? (
        <div className="research-session-error" role="alert">
          <p>Research sessions could not be loaded.</p>
          <button
            type="button"
            onClick={() => {
              void sessionsQuery.refetch();
              if (view === "active" && !hasFilters) {
                void pinnedQuery.refetch();
              }
            }}
          >
            Retry
          </button>
        </div>
      ) : null}

      {view === "active" && !hasFilters && pinnedSessions.length > 0 ? (
        <section
          aria-labelledby={`research-pinned-heading-${generatedId}`}
        >
          <h3 id={`research-pinned-heading-${generatedId}`}>Pinned</h3>
          <ul>{pinnedSessions.map(renderSession)}</ul>
          {pinnedQuery.hasNextPage ? (
            <button
              type="button"
              disabled={pinnedQuery.isFetchingNextPage}
              onClick={() => void pinnedQuery.fetchNextPage()}
            >
              {pinnedQuery.isFetchingNextPage
                ? "Loading pinned research..."
                : "Load more pinned research"}
            </button>
          ) : null}
        </section>
      ) : null}

      {hasFilters && sessions.length > 0 ? (
        <section
          aria-labelledby={`research-search-results-heading-${generatedId}`}
        >
          <h3 id={`research-search-results-heading-${generatedId}`}>
            Search results
          </h3>
          <ul>{sessions.map(renderSession)}</ul>
        </section>
      ) : null}

      {!hasFilters
        ? groups.map((group, index) => (
            <section
              key={group.label}
              aria-labelledby={`research-session-group-${generatedId}-${index}`}
            >
              <h3 id={`research-session-group-${generatedId}-${index}`}>
                {view === "archived"
                  ? `Archived: ${group.label}`
                  : group.label}
              </h3>
              <ul>{group.sessions.map(renderSession)}</ul>
            </section>
          ))
        : null}

      {noResults ? (
        <p className="research-session-status" role="status">
          {hasFilters
            ? "No research sessions match these filters."
            : view === "archived"
              ? "No archived research sessions."
              : "No research sessions yet."}
        </p>
      ) : null}

      {sessionsQuery.hasNextPage ? (
        <button
          type="button"
          className="research-session-load-more"
          disabled={sessionsQuery.isFetchingNextPage}
          onClick={() => void sessionsQuery.fetchNextPage()}
        >
          {sessionsQuery.isFetchingNextPage
            ? "Loading more research..."
            : "Load more research"}
        </button>
      ) : null}
    </div>
  );
}
