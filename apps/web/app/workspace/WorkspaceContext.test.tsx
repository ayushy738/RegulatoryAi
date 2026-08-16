import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  cleanup,
  render,
  waitFor,
} from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { WorkspaceProvider, useWorkspace } from "./WorkspaceContext";
import type { RouteKey } from "./types";

const authFixture = vi.hoisted(() => {
  const sessionValue = ["workspace", "boot", "session"].join("-");
  return {
    sessionValue,
    state: {
      loading: false,
      session: {
        access_token: sessionValue,
      } as { access_token: string } | null,
      user: {
        id: "workspace-boot-owner",
        email: "analyst@example.com",
      } as { id: string; email: string } | null,
    },
  };
});

vi.mock("@/app/components/auth/AuthProvider", () => ({
  useAuth: () => ({
    ...authFixture.state,
    login: vi.fn(),
    logout: vi.fn(),
  }),
}));

function responseFor(path: string) {
  if (path === "/health") {
    return {
      status: "ok",
      database_configured: true,
      database_connected: true,
      storage_configured: true,
      llm_provider: "test",
      effective_llm_provider: "test",
    };
  }
  if (path === "/digests/latest") {
    return {
      digest_date: "2026-07-27",
      event_count: 0,
      events: [],
    };
  }
  if (path === "/subscriptions") {
    return {
      jurisdictions: [],
      source_ids: [],
      topics: [],
      email_enabled: false,
      frequency: "instant",
    };
  }
  if (path === "/intelligence/readiness") {
    return {
      active_deadlines: [],
      stakeholder_obligations: [],
      regulatory_impacts: [],
      consultation_tracking: [],
      status: "ready",
      notes: [],
    };
  }
  if (path === "/admin/analytics") return {};
  return [];
}

function pathFrom(input: RequestInfo | URL) {
  return new URL(String(input)).pathname;
}

function createFetchMock() {
  return vi.fn(async (input: RequestInfo | URL) => {
    const path = pathFrom(input);
    return new Response(JSON.stringify(responseFor(path)), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  });
}

function WorkspaceProbe() {
  const { route, authReady, loading } = useWorkspace();
  return (
    <output data-route={route}>
      {authReady && !loading
        ? "workspace-ready"
        : "workspace-auth-loading"}
    </output>
  );
}

function renderWorkspace({
  route,
  v2AskEnabled,
  queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
        staleTime: 0,
      },
    },
  }),
}: {
  route: RouteKey;
  v2AskEnabled: boolean;
  queryClient?: QueryClient;
}) {
  function Wrapper({ children }: { children: ReactNode }) {
    return (
      <QueryClientProvider client={queryClient}>
        {children}
      </QueryClientProvider>
    );
  }
  return render(
    <WorkspaceProvider
      initialRoute={route}
      v2AskEnabled={v2AskEnabled}
    >
      <WorkspaceProbe />
    </WorkspaceProvider>,
    { wrapper: Wrapper },
  );
}

function requestedPaths(fetchMock: ReturnType<typeof createFetchMock>) {
  return fetchMock.mock.calls.map(([input]) => pathFrom(input));
}

afterEach(() => {
  cleanup();
  authFixture.state.loading = false;
  authFixture.state.session = {
    access_token: authFixture.sessionValue,
  };
  authFixture.state.user = {
    id: "workspace-boot-owner",
    email: "analyst@example.com",
  };
  vi.unstubAllGlobals();
});

describe("Workspace Ask boot ownership", () => {
  it("starts no legacy base/admin/history request for flag-on v2 Ask", async () => {
    const fetchMock = createFetchMock();
    vi.stubGlobal("fetch", fetchMock);

    renderWorkspace({ route: "ask", v2AskEnabled: true });

    expect(document.body).toHaveTextContent("workspace-ready");
    await waitFor(() =>
      expect(requestedPaths(fetchMock)).toContain("/health"),
    );
    expect(requestedPaths(fetchMock)).toEqual(["/health"]);
  });

  it("starts no legacy base/admin/history request for /ask when the UI flag is off", async () => {
    const fetchMock = createFetchMock();
    vi.stubGlobal("fetch", fetchMock);

    renderWorkspace({ route: "ask", v2AskEnabled: false });

    expect(document.body).toHaveTextContent("workspace-ready");
    await waitFor(() =>
      expect(requestedPaths(fetchMock)).toContain("/health"),
    );
    expect(requestedPaths(fetchMock)).toEqual(["/health"]);
  });

  it("isolates flag-on manual search and preserves flag-off browse boot", async () => {
    const isolatedFetch = createFetchMock();
    vi.stubGlobal("fetch", isolatedFetch);
    const isolated = renderWorkspace({
      route: "browse",
      v2AskEnabled: true,
    });
    expect(document.querySelector("output")).toHaveAttribute(
      "data-route",
      "browse",
    );
    await waitFor(() =>
      expect(requestedPaths(isolatedFetch)).toEqual(["/health"]),
    );
    isolated.unmount();

    const legacyFetch = createFetchMock();
    vi.stubGlobal("fetch", legacyFetch);
    renderWorkspace({ route: "browse", v2AskEnabled: false });
    expect(document.querySelector("output")).toHaveAttribute(
      "data-route",
      "latest",
    );
    await waitFor(() =>
      expect(requestedPaths(legacyFetch)).toEqual(
        expect.arrayContaining([
          "/health",
          "/digests/latest",
          "/subscriptions",
          "/admin/sources",
          "/admin/runs",
        ]),
      ),
    );
  });

  it("keeps non-Ask and saved-route dependencies unchanged when v2 is enabled", async () => {
    const latestFetch = createFetchMock();
    vi.stubGlobal("fetch", latestFetch);
    const latest = renderWorkspace({
      route: "latest",
      v2AskEnabled: true,
    });

    await waitFor(() => {
      expect(requestedPaths(latestFetch)).toEqual(
        expect.arrayContaining([
          "/digests/latest",
          "/subscriptions",
          "/admin/sources",
          "/admin/runs",
        ]),
      );
    });
    latest.unmount();

    const savedFetch = createFetchMock();
    vi.stubGlobal("fetch", savedFetch);
    renderWorkspace({ route: "saved", v2AskEnabled: true });
    await waitFor(() =>
      expect(requestedPaths(savedFetch)).toContain("/chat/history"),
    );
  });

  it("does not introduce legacy requests after auth readiness or remount", async () => {
    const fetchMock = createFetchMock();
    vi.stubGlobal("fetch", fetchMock);
    authFixture.state.loading = true;
    authFixture.state.session = null;
    authFixture.state.user = null;
    const rendered = renderWorkspace({
      route: "ask",
      v2AskEnabled: true,
    });
    await waitFor(() =>
      expect(requestedPaths(fetchMock)).toEqual(["/health"]),
    );

    authFixture.state.loading = false;
    authFixture.state.session = {
      access_token: authFixture.sessionValue,
    };
    authFixture.state.user = {
      id: "workspace-boot-owner",
      email: "analyst@example.com",
    };
    rendered.rerender(
      <QueryClientProvider
        client={
          new QueryClient({
            defaultOptions: { queries: { retry: false } },
          })
        }
      >
        <WorkspaceProvider initialRoute="ask" v2AskEnabled>
          <WorkspaceProbe />
        </WorkspaceProvider>
      </QueryClientProvider>,
    );
    await waitFor(() =>
      expect(
        requestedPaths(fetchMock).filter((path) => path === "/health"),
      ).toHaveLength(2),
    );
    for (const path of [
      "/digests/latest",
      "/subscriptions",
      "/admin/sources",
      "/admin/runs",
      "/chat/history",
    ]) {
      expect(requestedPaths(fetchMock)).not.toContain(path);
    }
  });
});
