import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  cleanup,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import sessionContract from "../../../../api/backend/tests/fixtures/ask_session_contract.json";
import {
  ResearchWorkspaceDataProvider,
  type ResearchWorkspaceClient,
} from "@/lib/ask-ai-data";
import type { AskSession } from "@/lib/ask-ai-sessions";

import {
  ResearchSessionRail,
  type ResearchExportDownloader,
} from "./ResearchSessionRail";

const authFixture = vi.hoisted(() => ({
  token: "session-rail-token",
}));

vi.mock("@/app/components/auth/AuthProvider", () => ({
  useAuth: () => ({
    loading: false,
    session: { access_token: authFixture.token },
    user: { id: "session-rail-owner" },
  }),
}));

const baseSession = sessionContract.session_response as AskSession;
const pinnedSession: AskSession = {
  ...baseSession,
  id: "33333333-3333-4333-8333-333333333333",
  title: "Pinned ABT research",
  primary_entity: "ABT",
  knowledge_mode_summary: { general: 1 },
  is_pinned: true,
  updated_at: "2026-07-26T06:30:00Z",
};
const earlierSession: AskSession = {
  ...baseSession,
  id: "44444444-4444-4444-8444-444444444444",
  title: "Earlier grid-code research",
  primary_entity: null,
  knowledge_mode_summary: { live: true },
  updated_at: "2026-07-01T06:30:00Z",
};
const archivedSession: AskSession = {
  ...baseSession,
  id: "55555555-5555-4555-8555-555555555555",
  title: "Archived consultation",
  archived_at: "2026-07-20T06:30:00Z",
  updated_at: "2026-07-20T06:30:00Z",
};
const duplicatedSession: AskSession = {
  ...baseSession,
  id: "66666666-6666-4666-8666-666666666666",
  title: "CERC tariff research copy",
};
const exportPayload = {
  schema_version: "1" as const,
  session: baseSession,
  turns: [],
  saved_items: [],
};

function createClient(
  overrides: Partial<ResearchWorkspaceClient> = {},
): ResearchWorkspaceClient {
  return {
    listSessions: vi.fn(async ({ q, pinned, archived, cursor }) => {
      if (archived) {
        return {
          schema_version: "1",
          items: [archivedSession],
          next_cursor: null,
        };
      }
      if (pinned) {
        return {
          schema_version: "1",
          items: [pinnedSession],
          next_cursor: null,
        };
      }
      if (q) {
        return {
          schema_version: "1",
          items: [earlierSession],
          next_cursor: null,
        };
      }
      if (cursor) {
        return {
          schema_version: "1",
          items: [earlierSession],
          next_cursor: null,
        };
      }
      return {
        schema_version: "1",
        items: [baseSession, pinnedSession],
        next_cursor: null,
      };
    }),
    getSession: vi.fn(async () => baseSession),
    listTurns: vi.fn(async () => ({
      schema_version: "1",
      items: [],
      next_cursor: null,
    })),
    getMessageEvidence: vi.fn(async () => ({})),
    getMessageSources: vi.fn(async () => ({})),
    listSavedItems: vi.fn(async () => ({
      schema_version: "1",
      items: [],
    })),
    patchSession: vi.fn(async ({ patch }) => ({
      ...baseSession,
      ...("title" in patch ? { title: patch.title } : {}),
      ...("is_pinned" in patch ? { is_pinned: patch.is_pinned } : {}),
    })),
    archiveSession: vi.fn(async () => ({
      ...baseSession,
      archived_at: "2026-07-27T08:00:00Z",
    })),
    restoreSession: vi.fn(async () => ({
      ...archivedSession,
      archived_at: null,
    })),
    duplicateSession: vi.fn(async () => duplicatedSession),
    exportSession: vi.fn(async () => exportPayload),
    deleteSession: vi.fn(async () => undefined),
    ...overrides,
  };
}

function renderRail({
  client = createClient(),
  activeSessionId = null,
  onSelectSession = vi.fn(),
  onSessionUnavailable = vi.fn(),
  downloadExport = vi.fn(),
}: {
  client?: ResearchWorkspaceClient;
  activeSessionId?: string | null;
  onSelectSession?: (session: AskSession) => void;
  onSessionUnavailable?: (sessionId: string) => void;
  downloadExport?: ResearchExportDownloader;
} = {}) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
  function Wrapper({ children }: { children: ReactNode }) {
    return (
      <QueryClientProvider client={queryClient}>
        <ResearchWorkspaceDataProvider enabled client={client}>
          {children}
        </ResearchWorkspaceDataProvider>
      </QueryClientProvider>
    );
  }
  const rendered = render(
    <ResearchSessionRail
      activeSessionId={activeSessionId}
      onSelectSession={onSelectSession}
      onSessionUnavailable={onSessionUnavailable}
      downloadExport={downloadExport}
      now={new Date("2026-07-27T12:00:00Z")}
    />,
    { wrapper: Wrapper },
  );
  return {
    ...rendered,
    client,
    downloadExport,
    onSelectSession,
    onSessionUnavailable,
  };
}

function itemFor(title: string) {
  return screen.getByRole("button", {
    name: new RegExp(title, "i"),
  }).closest("li") as HTMLLIElement;
}

afterEach(() => {
  cleanup();
});

describe("Research Workspace session rail", () => {
  it("renders real pinned/recency groups, indicators, and controlled selection", async () => {
    const user = userEvent.setup();
    const onSelectSession = vi.fn();
    renderRail({
      activeSessionId: baseSession.id,
      onSelectSession,
    });

    expect(
      await screen.findByRole("heading", { name: "Pinned" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "Today" }),
    ).toBeInTheDocument();
    expect(itemFor("CERC tariff research")).toHaveAttribute(
      "data-active",
      "true",
    );
    expect(
      within(itemFor("CERC tariff research")).getByText("CERC"),
    ).toBeInTheDocument();
    expect(
      within(itemFor("Pinned ABT research")).getByText("general"),
    ).toBeInTheDocument();

    await user.click(
      within(itemFor("Pinned ABT research")).getByRole("button", {
        name: /Pinned ABT research/i,
      }),
    );
    expect(onSelectSession).toHaveBeenCalledWith(pinnedSession);
  });

  it("submits normalized server search filters and pages without local filtering", async () => {
    const user = userEvent.setup();
    const client = createClient({
      listSessions: vi.fn(async ({ q, pinned, archived, cursor }) => {
        if (pinned) {
          return {
            schema_version: "1",
            items: [pinnedSession],
            next_cursor: null,
          };
        }
        if (q) {
          return {
            schema_version: "1",
            items: [earlierSession],
            next_cursor: null,
          };
        }
        if (archived) {
          return {
            schema_version: "1",
            items: [archivedSession],
            next_cursor: null,
          };
        }
        return cursor
          ? {
              schema_version: "1",
              items: [earlierSession],
              next_cursor: null,
            }
          : {
              schema_version: "1",
              items: [baseSession],
              next_cursor: "opaque-next-session-page",
            };
      }),
    });
    renderRail({ client });
    await screen.findByText("CERC tariff research");

    await user.click(
      screen.getByRole("button", { name: "Load more research" }),
    );
    await waitFor(() =>
      expect(client.listSessions).toHaveBeenCalledWith({
        accessToken: authFixture.token,
        cursor: "opaque-next-session-page",
        limit: 20,
        archived: false,
      }),
    );

    await user.type(
      screen.getByRole("searchbox", { name: "Search conversations" }),
      "  GRID   Code ",
    );
    await user.type(
      screen.getByRole("textbox", { name: "Entity filter" }),
      " CERC ",
    );
    await user.selectOptions(
      screen.getByRole("combobox", { name: "Knowledge mode" }),
      "official",
    );
    await user.click(screen.getByRole("button", { name: "Search" }));

    await waitFor(() =>
      expect(client.listSessions).toHaveBeenCalledWith({
        accessToken: authFixture.token,
        cursor: null,
        limit: 20,
        q: "grid code",
        entity: "cerc",
        knowledge_mode: "official",
        archived: false,
      }),
    );
    expect(
      await screen.findByRole("heading", { name: "Search results" }),
    ).toBeInTheDocument();
    expect(screen.getByText("Earlier grid-code research")).toBeInTheDocument();
  });

  it("executes rename, pin, duplicate, export, archive, restore, and confirmed delete", async () => {
    const user = userEvent.setup();
    const harness = renderRail();
    await screen.findByText("CERC tariff research");
    let item = itemFor("CERC tariff research");

    await user.click(within(item).getByRole("button", { name: "Rename" }));
    const rename = within(item).getByRole("textbox", {
      name: "Research title",
    });
    await user.clear(rename);
    await user.type(rename, "Renamed tariff research");
    await user.click(
      within(item).getByRole("button", { name: "Save name" }),
    );
    await waitFor(() =>
      expect(harness.client.patchSession).toHaveBeenCalledWith({
        accessToken: authFixture.token,
        sessionId: baseSession.id,
        patch: { title: "Renamed tariff research" },
      }),
    );

    item = itemFor("CERC tariff research");
    await user.click(within(item).getByRole("button", { name: "Pin" }));
    await waitFor(() =>
      expect(harness.client.patchSession).toHaveBeenCalledWith({
        accessToken: authFixture.token,
        sessionId: baseSession.id,
        patch: { is_pinned: true },
      }),
    );
    await user.click(within(item).getByRole("button", { name: "Duplicate" }));
    await waitFor(() =>
      expect(harness.onSelectSession).toHaveBeenCalledWith(
        duplicatedSession,
      ),
    );
    await user.click(within(item).getByRole("button", { name: "Export" }));
    await waitFor(() =>
      expect(harness.downloadExport).toHaveBeenCalledWith(exportPayload),
    );
    await user.click(within(item).getByRole("button", { name: "Archive" }));
    await waitFor(() =>
      expect(harness.onSessionUnavailable).toHaveBeenCalledWith(
        baseSession.id,
      ),
    );

    await user.click(screen.getByRole("button", { name: "Archived" }));
    const archivedItem = await waitFor(() => itemFor("Archived consultation"));
    expect(
      within(archivedItem).queryByRole("button", { name: "Pin" }),
    ).not.toBeInTheDocument();
    await user.click(
      within(archivedItem).getByRole("button", { name: "Restore" }),
    );
    expect(harness.client.restoreSession).toHaveBeenCalledWith({
      accessToken: authFixture.token,
      sessionId: archivedSession.id,
    });

    await user.click(screen.getByRole("button", { name: "Active" }));
    item = await waitFor(() => itemFor("CERC tariff research"));
    await user.click(within(item).getByRole("button", { name: "Delete" }));
    expect(
      within(item).getByText("Delete this research workspace?"),
    ).toBeInTheDocument();
    await user.click(
      within(item).getByRole("button", { name: "Confirm delete" }),
    );
    await waitFor(() =>
      expect(harness.client.deleteSession).toHaveBeenCalledWith({
        accessToken: authFixture.token,
        sessionId: baseSession.id,
      }),
    );
  });

  it("shows safe retryable failures without exposing server detail", async () => {
    const user = userEvent.setup();
    const client = createClient({
      patchSession: vi.fn(async () => {
        throw new Error("database-owner-secret");
      }),
    });
    renderRail({ client });
    const item = await waitFor(() => itemFor("CERC tariff research"));

    await user.click(within(item).getByRole("button", { name: "Pin" }));

    expect(
      await screen.findByRole("alert"),
    ).toHaveTextContent(
      "The session action could not be completed. Your research is unchanged.",
    );
    expect(screen.queryByText("database-owner-secret")).not.toBeInTheDocument();
  });
});
