import {
  QueryClient,
  QueryClientProvider,
} from "@tanstack/react-query";
import {
  act,
  renderHook,
  waitFor,
} from "@testing-library/react";
import type { ReactNode } from "react";
import {
  afterEach,
  describe,
  expect,
  it,
  vi,
} from "vitest";

import evidenceContract from "../../api/backend/tests/fixtures/ask_evidence_contract.json";
import responseContract from "../../api/backend/tests/fixtures/ask_response_contract.json";
import sessionContract from "../../api/backend/tests/fixtures/ask_session_contract.json";
import turnContract from "../../api/backend/tests/fixtures/ask_turn_contract.json";
import { federatedSearchFixture } from "../test/federated-search-fixture";
import {
  manualDocumentSearchFixture,
} from "../test/manual-document-search-fixture";
import {
  ResearchWorkspaceDataProvider,
  researchWorkspaceKeys,
  useFederatedResearchSearch,
  useManualDocumentSearch,
  useResearchMessageEvidence,
  useResearchMessageSources,
  useResolveResearchEntity,
  useResearchRun,
  useResearchSavedItems,
  useResearchSession,
  useResearchSessionExport,
  useResearchSessionLifecycle,
  useResearchSessions,
  useResearchStructuredResponse,
  useResearchTurns,
} from "./ask-ai-data";
import type {
  ResearchRunIdentity,
  ResearchWorkspaceClient,
} from "./ask-ai-data";
import {
  getAskSession,
  resolveAskEntity,
  searchAskDocuments,
  searchAskResearch,
} from "./api";

const authFixture = vi.hoisted(() => {
  const ownerOneAuth = ["owner", "one", "session"].join("-");
  const ownerTwoAuth = ["owner", "two", "session"].join("-");
  const explicitAuth = ["explicit", "owner", "session"].join("-");
  return {
    explicitAuth,
    ownerOneAuth,
    ownerTwoAuth,
    state: {
      loading: false,
      session: {
        access_token: ownerOneAuth,
      },
      user: {
        id: "owner-one",
      },
    },
  };
});
const authState = authFixture.state;

vi.mock("@/app/components/auth/AuthProvider", () => ({
  useAuth: () => authState,
}));

afterEach(() => {
  authState.loading = false;
  authState.session = {
    access_token: authFixture.ownerOneAuth,
  };
  authState.user = {
    id: "owner-one",
  };
  vi.unstubAllGlobals();
});

function createClient(
  overrides: Partial<ResearchWorkspaceClient> = {},
): ResearchWorkspaceClient {
  return {
    listSessions: vi.fn(async () => sessionContract.list_response),
    getSession: vi.fn(async () => sessionContract.session_response),
    listTurns: vi.fn(async () => turnContract.turn_list_response),
    getMessageEvidence: vi.fn(
      async () => evidenceContract.message_response,
    ),
    getMessageSources: vi.fn(
      async () => evidenceContract.sources_response,
    ),
    listSavedItems: vi.fn(async () => ({
      schema_version: "1",
      items: [evidenceContract.saved_item_response],
    })),
    patchSession: vi.fn(async () => sessionContract.session_response),
    archiveSession: vi.fn(async () => sessionContract.session_response),
    restoreSession: vi.fn(async () => sessionContract.session_response),
    duplicateSession: vi.fn(async () => sessionContract.session_response),
    exportSession: vi.fn(async () => ({
      schema_version: "1",
      session: sessionContract.session_response,
      turns: [],
      saved_items: [],
    })),
    deleteSession: vi.fn(async () => undefined),
    ...overrides,
  };
}

describe("Research Workspace entity lookup mutation", () => {
  it("forwards normalized authenticated input and validates the result", async () => {
    const response = {
      schema_version: "1",
      policy_version: "ask-ai-decision-v1",
      status: "resolved",
      mention: "DSM",
      match_rule: "exact_alias",
      selected: {
        canonical_id: "in.central.dsm",
        canonical_name: "Deviation Settlement Mechanism",
        entity_class: "regulatory_concept",
        jurisdiction: "India/Central",
        aliases: ["DSM"],
        confidence: 0.95,
        assumed: false,
        match_reason: "Matched an approved alias.",
        entity_route: "/ask?entity=in.central.dsm",
      },
      candidates: [],
      clarification_question: null,
      surface: "entity_intelligence_page",
    };
    const resolveEntity = vi.fn(async () => response);
    const client = createClient({ resolveEntity });
    const { Wrapper } = createWrapper({ client });
    const { result } = renderHook(() => useResolveResearchEntity(), {
      wrapper: Wrapper,
    });

    expect(result.current.available).toBe(true);
    let resolved: unknown;
    await act(async () => {
      resolved = await result.current.mutateAsync({
        mention: " DSM ",
        active_jurisdiction: " India/Central ",
      });
    });

    expect(resolveEntity).toHaveBeenCalledWith({
      accessToken: authFixture.ownerOneAuth,
      schema_version: "1",
      mention: "DSM",
      active_jurisdiction: "India/Central",
    });
    expect(resolved).toEqual(response);
  });

  it("fails closed before client access when disabled or malformed", async () => {
    const resolveEntity = vi.fn();
    const client = createClient({ resolveEntity });
    const { Wrapper } = createWrapper({ client, enabled: false });
    const { result } = renderHook(() => useResolveResearchEntity(), {
      wrapper: Wrapper,
    });

    expect(result.current.available).toBe(false);
    await expect(
      result.current.mutateAsync({ mention: "DSM" }),
    ).rejects.toThrow("unavailable");
    expect(resolveEntity).not.toHaveBeenCalled();
  });
});

describe("Research Workspace federated search mutation", () => {
  it("forwards normalized authenticated search input and validates the result", async () => {
    const searchResearch = vi.fn(async () => federatedSearchFixture());
    const client = createClient({ searchResearch });
    const { Wrapper } = createWrapper({ client });
    const { result } = renderHook(
      () => useFederatedResearchSearch(),
      { wrapper: Wrapper },
    );

    expect(result.current.available).toBe(true);
    let response: unknown;
    await act(async () => {
      response = await result.current.mutateAsync({
        schema_version: "1",
        query: "  DSM   regulation ",
        correction_mode: "auto",
        filters: { regulator: " CERC " },
        limit: 5,
      });
    });

    expect(searchResearch).toHaveBeenCalledWith({
      accessToken: authFixture.ownerOneAuth,
      schema_version: "1",
      query: "DSM regulation",
      correction_mode: "auto",
      filters: { regulator: "CERC" },
      limit: 5,
    });
    expect(response).toEqual(federatedSearchFixture());
  });

  it("fails closed before client access when search is unavailable", async () => {
    const client = createClient();
    const { Wrapper } = createWrapper({ client });
    const { result } = renderHook(
      () => useFederatedResearchSearch(),
      { wrapper: Wrapper },
    );

    expect(result.current.available).toBe(false);
    await expect(
      result.current.mutateAsync({
        schema_version: "1",
        query: "DSM",
        correction_mode: "auto",
        filters: {},
        limit: 5,
      }),
    ).rejects.toThrow("unavailable");
  });
});

describe("Research Workspace manual document search mutation", () => {
  it("forwards normalized authenticated filters and validates the result", async () => {
    const searchDocuments = vi.fn(
      async () => manualDocumentSearchFixture(),
    );
    const client = createClient({ searchDocuments });
    const { Wrapper } = createWrapper({ client });
    const { result } = renderHook(
      () => useManualDocumentSearch(),
      { wrapper: Wrapper },
    );

    expect(result.current.available).toBe(true);
    let response: unknown;
    await act(async () => {
      response = await result.current.mutateAsync({
        schema_version: "1",
        query: " deviation   charge ",
        exact_phrase: true,
        issuer: " CERC ",
        within_document: " generators ",
        limit: 20,
      });
    });

    expect(searchDocuments).toHaveBeenCalledWith({
      accessToken: authFixture.ownerOneAuth,
      schema_version: "1",
      query: "deviation charge",
      exact_phrase: true,
      issuer: "CERC",
      within_document: "generators",
      limit: 20,
    });
    expect(response).toEqual(manualDocumentSearchFixture());
  });

  it("fails closed before client access when manual search is unavailable", async () => {
    const client = createClient();
    const { Wrapper } = createWrapper({ client });
    const { result } = renderHook(
      () => useManualDocumentSearch(),
      { wrapper: Wrapper },
    );

    expect(result.current.available).toBe(false);
    await expect(
      result.current.mutateAsync({
        schema_version: "1",
        title: "DSM",
        exact_phrase: false,
        limit: 20,
      }),
    ).rejects.toThrow("unavailable");
  });
});

function createWrapper({
  client,
  enabled = true,
  queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
      },
    },
  }),
}: {
  client: ResearchWorkspaceClient;
  enabled?: boolean;
  queryClient?: QueryClient;
}) {
  function Wrapper({ children }: { children: ReactNode }) {
    return (
      <QueryClientProvider client={queryClient}>
        <ResearchWorkspaceDataProvider
          client={client}
          enabled={enabled}
        >
          {children}
        </ResearchWorkspaceDataProvider>
      </QueryClientProvider>
    );
  }
  return { queryClient, Wrapper };
}

describe("Research Workspace query keys", () => {
  it("is stable, owner-scoped, pagination-aware, and isolated from legacy chat", () => {
    expect(researchWorkspaceKeys.sessionList("owner-one")).toEqual(
      researchWorkspaceKeys.sessionList("owner-one", 20),
    );
    expect(researchWorkspaceKeys.sessionList("owner-one", 10)).not.toEqual(
      researchWorkspaceKeys.sessionList("owner-one", 20),
    );
    expect(
      researchWorkspaceKeys.turns("owner-one", "session-one", 10),
    ).not.toEqual(
      researchWorkspaceKeys.turns("owner-one", "session-one", 20),
    );
    expect(researchWorkspaceKeys.session("owner-one", "session-one")).not.toEqual(
      researchWorkspaceKeys.session("owner-two", "session-one"),
    );
    expect(
      researchWorkspaceKeys.messageEvidence("owner-one", "message-one"),
    ).toEqual(researchWorkspaceKeys.run("owner-one", "message-one"));
    const runIdentity = {
      sessionId: "session-one",
      messageId: "message-one",
      runId: "run-one",
      responseVersion: 1,
    };
    expect(
      researchWorkspaceKeys.structuredResponse("owner-one", runIdentity),
    ).not.toEqual(
      researchWorkspaceKeys.structuredResponse("owner-one", {
        ...runIdentity,
        sessionId: "session-two",
      }),
    );
    expect(researchWorkspaceKeys.root[0]).toBe("ask-ai-v2");
    expect(researchWorkspaceKeys.root).not.toContain("chat");
  });
});

describe("Research Workspace read hooks", () => {
  it("gates every request on feature, auth, and stable resource identity", async () => {
    const client = createClient();
    const disabled = createWrapper({ client, enabled: false });
    const { result } = renderHook(
      () => ({
        sessions: useResearchSessions(),
        session: useResearchSession("session-one"),
        turns: useResearchTurns("session-one"),
        evidence: useResearchMessageEvidence("message-one"),
        sources: useResearchMessageSources("message-one"),
        saved: useResearchSavedItems("session-one"),
        structured: useResearchStructuredResponse(null),
      }),
      { wrapper: disabled.Wrapper },
    );

    expect(result.current.sessions.fetchStatus).toBe("idle");
    expect(result.current.session.fetchStatus).toBe("idle");
    expect(result.current.turns.fetchStatus).toBe("idle");
    expect(result.current.evidence.fetchStatus).toBe("idle");
    expect(result.current.sources.fetchStatus).toBe("idle");
    expect(result.current.saved.fetchStatus).toBe("idle");
    expect(result.current.structured.fetchStatus).toBe("idle");
    expect(client.listSessions).not.toHaveBeenCalled();
    expect(client.getSession).not.toHaveBeenCalled();

    authState.loading = true;
    const loadingAuth = createWrapper({ client, enabled: true });
    renderHook(() => useResearchSessions(), {
      wrapper: loadingAuth.Wrapper,
    });
    await Promise.resolve();
    expect(client.listSessions).not.toHaveBeenCalled();

    authState.loading = false;
    authState.session = { access_token: "" };
    const missingToken = createWrapper({ client, enabled: true });
    renderHook(() => useResearchSessions(), {
      wrapper: missingToken.Wrapper,
    });
    await Promise.resolve();
    expect(client.listSessions).not.toHaveBeenCalled();
  });

  it("uses opaque cursors as page parameters without fragmenting the cache key", async () => {
    const firstPage = {
      ...sessionContract.list_response,
      next_cursor: "opaque-session-cursor",
    };
    const client = createClient({
      listSessions: vi
        .fn()
        .mockResolvedValueOnce(firstPage)
        .mockResolvedValueOnce({
          ...sessionContract.list_response,
          items: [],
          next_cursor: null,
        }),
    });
    const harness = createWrapper({ client });
    const { result } = renderHook(
      () => useResearchSessions({ limit: 7 }),
      { wrapper: harness.Wrapper },
    );

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(client.listSessions).toHaveBeenNthCalledWith(1, {
      accessToken: authFixture.ownerOneAuth,
      cursor: null,
      limit: 7,
    });

    let nextPageResult:
      | Awaited<ReturnType<typeof result.current.fetchNextPage>>
      | undefined;
    await act(async () => {
      nextPageResult = await result.current.fetchNextPage();
    });

    expect(client.listSessions).toHaveBeenNthCalledWith(2, {
      accessToken: authFixture.ownerOneAuth,
      cursor: "opaque-session-cursor",
      limit: 7,
    });
    expect(nextPageResult?.data?.pages).toHaveLength(2);
    expect(nextPageResult?.data?.pageParams).toEqual([
      null,
      "opaque-session-cursor",
    ]);
  });

  it("normalizes session filters into both the cache key and request", async () => {
    const client = createClient();
    const harness = createWrapper({ client });
    const { result } = renderHook(
      () =>
        useResearchSessions({
          limit: 9,
          q: "  GRID   Code ",
          knowledge_mode: "official",
          entity: " CERC ",
          archived: true,
          pinned: false,
        }),
      { wrapper: harness.Wrapper },
    );

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(client.listSessions).toHaveBeenCalledWith({
      accessToken: authFixture.ownerOneAuth,
      cursor: null,
      limit: 9,
      q: "grid code",
      knowledge_mode: "official",
      entity: "cerc",
      archived: true,
      pinned: false,
    });
    expect(
      researchWorkspaceKeys.sessionList("owner-one", 9, {
        q: "grid code",
        knowledge_mode: "official",
        entity: "cerc",
        archived: true,
        pinned: false,
      }),
    ).not.toEqual(researchWorkspaceKeys.sessionList("owner-one", 9));
  });

  it("continues complete turns with the backend's opaque message cursor", async () => {
    const firstPage = {
      ...turnContract.turn_list_response,
      next_cursor: "opaque-turn-cursor",
    };
    const client = createClient({
      listTurns: vi
        .fn()
        .mockResolvedValueOnce(firstPage)
        .mockResolvedValueOnce({
          ...turnContract.turn_list_response,
          items: [],
          next_cursor: null,
        }),
    });
    const harness = createWrapper({ client });
    const sessionId = sessionContract.session_response.id;
    const { result } = renderHook(
      () => useResearchTurns(sessionId, { limit: 9 }),
      { wrapper: harness.Wrapper },
    );

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    await act(async () => {
      await result.current.fetchNextPage();
    });

    expect(client.listTurns).toHaveBeenNthCalledWith(2, {
      accessToken: authFixture.ownerOneAuth,
      sessionId,
      cursor: "opaque-turn-cursor",
      limit: 9,
    });
  });

  it("parses E2 reads and shares one canonical message/run cache record", async () => {
    const client = createClient();
    const harness = createWrapper({ client });
    const sessionId = sessionContract.session_response.id;
    const messageId = evidenceContract.message_response.message.id;
    const { result } = renderHook(
      () => ({
        session: useResearchSession(sessionId),
        turns: useResearchTurns(sessionId, { limit: 11 }),
        evidence: useResearchMessageEvidence(messageId),
        run: useResearchRun(messageId),
        sources: useResearchMessageSources(messageId),
        saved: useResearchSavedItems(sessionId),
      }),
      { wrapper: harness.Wrapper },
    );

    await waitFor(() => {
      expect(result.current.session.isSuccess).toBe(true);
      expect(result.current.turns.isSuccess).toBe(true);
      expect(result.current.evidence.isSuccess).toBe(true);
      expect(result.current.run.isSuccess).toBe(true);
      expect(result.current.sources.isSuccess).toBe(true);
      expect(result.current.saved.isSuccess).toBe(true);
    });

    expect(result.current.session.data).toEqual(
      sessionContract.session_response,
    );
    expect(result.current.turns.data?.pages[0]).toEqual(
      turnContract.turn_list_response,
    );
    expect(result.current.run.data).toEqual(
      evidenceContract.message_response.run,
    );
    expect(result.current.sources.data).toEqual(
      evidenceContract.sources_response,
    );
    expect(result.current.saved.data?.items).toEqual([
      evidenceContract.saved_item_response,
    ]);
    expect(client.getMessageEvidence).toHaveBeenCalledTimes(1);
    expect(client.listTurns).toHaveBeenCalledWith({
      accessToken: authFixture.ownerOneAuth,
      sessionId,
      cursor: null,
      limit: 11,
    });
  });

  it("rejects invalid server payloads at the hook boundary", async () => {
    const client = createClient({
      getSession: vi.fn(async () => ({
        ...sessionContract.session_response,
        schema_version: "future",
      })),
    });
    const harness = createWrapper({ client });
    const { result } = renderHook(
      () => useResearchSession(sessionContract.session_response.id),
      { wrapper: harness.Wrapper },
    );

    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(result.current.data).toBeUndefined();
  });

  it("parses injected E8.1 structured results under exact run/version keys", async () => {
    const identity: ResearchRunIdentity = {
      sessionId: sessionContract.session_response.id,
      messageId: evidenceContract.message_response.message.id,
      runId: evidenceContract.message_response.run.id,
      responseVersion: evidenceContract.message_response.response_version,
    };
    const client = createClient({
      getStructuredResponse: vi.fn(async () => responseContract),
    });
    const harness = createWrapper({ client });
    const { result } = renderHook(
      () => useResearchStructuredResponse(identity),
      { wrapper: harness.Wrapper },
    );

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toEqual(responseContract);
    expect(client.getStructuredResponse).toHaveBeenCalledWith({
      accessToken: authFixture.ownerOneAuth,
      ...identity,
    });
    expect(
      harness.queryClient.getQueryData(
        researchWorkspaceKeys.structuredResponse("owner-one", identity),
      ),
    ).toEqual(responseContract);
  });

  it("keeps identical resource IDs isolated across authenticated owners", async () => {
    const client = createClient();
    const queryClient = new QueryClient({
      defaultOptions: {
        queries: {
          retry: false,
        },
      },
    });
    const first = createWrapper({ client, queryClient });
    const sessionId = sessionContract.session_response.id;
    const firstHook = renderHook(() => useResearchSession(sessionId), {
      wrapper: first.Wrapper,
    });
    await waitFor(() => expect(firstHook.result.current.isSuccess).toBe(true));
    firstHook.unmount();

    authState.session = { access_token: authFixture.ownerTwoAuth };
    authState.user = { id: "owner-two" };
    const second = createWrapper({ client, queryClient });
    const secondHook = renderHook(() => useResearchSession(sessionId), {
      wrapper: second.Wrapper,
    });
    await waitFor(() => expect(secondHook.result.current.isSuccess).toBe(true));

    expect(client.getSession).toHaveBeenCalledTimes(2);
    expect(client.getSession).toHaveBeenNthCalledWith(2, {
      accessToken: authFixture.ownerTwoAuth,
      sessionId,
    });
    expect(
      queryClient.getQueryData(
        researchWorkspaceKeys.session("owner-one", sessionId),
      ),
    ).toEqual(sessionContract.session_response);
    expect(
      queryClient.getQueryData(
        researchWorkspaceKeys.session("owner-two", sessionId),
      ),
    ).toEqual(sessionContract.session_response);
  });
});

describe("Research Workspace session actions", () => {
  it("uses exact owner credentials and refreshes canonical session state", async () => {
    const renamedSession = {
      ...sessionContract.session_response,
      title: "Renamed research",
    };
    const duplicateSession = {
      ...sessionContract.session_response,
      id: "33333333-3333-4333-8333-333333333333",
      title: "CERC tariff research copy",
    };
    const exportPayload = {
      schema_version: "1" as const,
      session: sessionContract.session_response,
      turns: [],
      saved_items: [],
    };
    const client = createClient({
      patchSession: vi.fn(async () => renamedSession),
      archiveSession: vi.fn(async () => ({
        ...renamedSession,
        archived_at: "2026-07-27T07:00:00Z",
      })),
      restoreSession: vi.fn(async () => renamedSession),
      duplicateSession: vi.fn(async () => duplicateSession),
      exportSession: vi.fn(async () => exportPayload),
      deleteSession: vi.fn(async () => undefined),
    });
    const harness = createWrapper({ client });
    const sessionId = sessionContract.session_response.id;
    const { result } = renderHook(
      () => ({
        sessions: useResearchSessions(),
        lifecycle: useResearchSessionLifecycle(),
        exporter: useResearchSessionExport(),
      }),
      { wrapper: harness.Wrapper },
    );
    await waitFor(() => expect(result.current.sessions.isSuccess).toBe(true));
    const initialListCalls = vi.mocked(client.listSessions).mock.calls.length;

    await act(async () => {
      await result.current.lifecycle.mutateAsync({
        type: "patch",
        session_id: sessionId,
        patch: { title: " Renamed research " },
      });
    });
    expect(client.patchSession).toHaveBeenCalledWith({
      accessToken: authFixture.ownerOneAuth,
      sessionId,
      patch: { title: "Renamed research" },
    });
    expect(
      harness.queryClient.getQueryData(
        researchWorkspaceKeys.session("owner-one", sessionId),
      ),
    ).toEqual(renamedSession);
    expect(vi.mocked(client.listSessions).mock.calls.length).toBeGreaterThan(
      initialListCalls,
    );

    await act(async () => {
      await result.current.lifecycle.mutateAsync({
        type: "archive",
        session_id: sessionId,
      });
      await result.current.lifecycle.mutateAsync({
        type: "restore",
        session_id: sessionId,
      });
      await result.current.lifecycle.mutateAsync({
        type: "duplicate",
        session_id: sessionId,
      });
      await result.current.exporter.mutateAsync(sessionId);
    });
    expect(client.archiveSession).toHaveBeenCalledWith({
      accessToken: authFixture.ownerOneAuth,
      sessionId,
    });
    expect(client.restoreSession).toHaveBeenCalledWith({
      accessToken: authFixture.ownerOneAuth,
      sessionId,
    });
    expect(client.duplicateSession).toHaveBeenCalledWith({
      accessToken: authFixture.ownerOneAuth,
      sessionId,
    });
    expect(client.exportSession).toHaveBeenCalledWith({
      accessToken: authFixture.ownerOneAuth,
      sessionId,
    });
    expect(result.current.exporter.data).toEqual(exportPayload);

    await act(async () => {
      await result.current.lifecycle.mutateAsync({
        type: "delete",
        session_id: sessionId,
      });
    });
    expect(client.deleteSession).toHaveBeenCalledWith({
      accessToken: authFixture.ownerOneAuth,
      sessionId,
    });
    expect(
      harness.queryClient.getQueryData(
        researchWorkspaceKeys.session("owner-one", sessionId),
      ),
    ).toBeUndefined();
  });

  it("rejects malformed lifecycle/export results and makes no signed-out request", async () => {
    const malformedClient = createClient({
      patchSession: vi.fn(async () => ({
        ...sessionContract.session_response,
        schema_version: "future",
      })),
      exportSession: vi.fn(async () => ({
        schema_version: "future",
      })),
    });
    const harness = createWrapper({ client: malformedClient });
    const sessionId = sessionContract.session_response.id;
    const { result } = renderHook(
      () => ({
        lifecycle: useResearchSessionLifecycle(),
        exporter: useResearchSessionExport(),
      }),
      { wrapper: harness.Wrapper },
    );

    await expect(
      result.current.lifecycle.mutateAsync({
        type: "patch",
        session_id: sessionId,
        patch: { title: "Changed" },
      }),
    ).rejects.toThrow();
    await expect(
      result.current.exporter.mutateAsync(sessionId),
    ).rejects.toThrow();

    authState.session = { access_token: "" };
    const signedOut = createWrapper({ client: malformedClient });
    const signedOutHook = renderHook(
      () => useResearchSessionLifecycle(),
      { wrapper: signedOut.Wrapper },
    );
    await expect(
      signedOutHook.result.current.mutateAsync({
        type: "archive",
        session_id: sessionId,
      }),
    ).rejects.toThrow("Research Workspace is unavailable");
    expect(malformedClient.archiveSession).not.toHaveBeenCalled();
  });
});

describe("ASK_AI v2 API authentication", () => {
  it("uses the provider's exact token instead of a second global-session read", async () => {
    const fetchMock = vi.fn(
      async (_input: RequestInfo | URL, _init?: RequestInit) =>
        new Response(JSON.stringify(sessionContract.session_response), {
          status: 200,
          headers: {
            "Content-Type": "application/json",
          },
        }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await getAskSession(
      sessionContract.session_response.id,
      authFixture.explicitAuth,
    );

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const init = fetchMock.mock.calls[0]?.[1];
    expect(init).toBeDefined();
    expect(new Headers(init?.headers).get("Authorization")).toBe(
      `Bearer ${authFixture.explicitAuth}`,
    );
  });

  it("uses the exact entity route, token, method, and normalized body", async () => {
    const response = {
      schema_version: "1",
      policy_version: "ask-ai-decision-v1",
      status: "no_match",
      mention: "unknown",
      match_rule: "clarification",
      selected: null,
      candidates: [],
      clarification_question:
        "Which regulatory entity or jurisdiction do you mean?",
      surface: null,
    };
    const fetchMock = vi.fn(
      async (_input: RequestInfo | URL, _init?: RequestInit) =>
        new Response(JSON.stringify(response), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await resolveAskEntity(
      {
        mention: " unknown ",
        active_jurisdiction: " India/Central ",
      },
      authFixture.explicitAuth,
    );

    const [input, init] = fetchMock.mock.calls[0] ?? [];
    expect(new URL(String(input)).pathname).toBe(
      "/chat/entities/resolve",
    );
    expect(init?.method).toBe("POST");
    expect(new Headers(init?.headers).get("Authorization")).toBe(
      `Bearer ${authFixture.explicitAuth}`,
    );
    expect(JSON.parse(String(init?.body))).toEqual({
      schema_version: "1",
      mention: "unknown",
      active_jurisdiction: "India/Central",
    });
  });

  it("uses the exact federated search route, token, method, and normalized body", async () => {
    const fetchMock = vi.fn(
      async (_input: RequestInfo | URL, _init?: RequestInit) =>
        new Response(JSON.stringify(federatedSearchFixture()), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await searchAskResearch(
      {
        schema_version: "1",
        query: " DSM ",
        correction_mode: "auto",
        filters: { jurisdiction: " India/Central " },
        limit: 5,
      },
      authFixture.explicitAuth,
    );

    const [input, init] = fetchMock.mock.calls[0] ?? [];
    expect(new URL(String(input)).pathname).toBe("/chat/search");
    expect(init?.method).toBe("POST");
    expect(new Headers(init?.headers).get("Authorization")).toBe(
      `Bearer ${authFixture.explicitAuth}`,
    );
    expect(JSON.parse(String(init?.body))).toEqual({
      schema_version: "1",
      query: "DSM",
      correction_mode: "auto",
      filters: { jurisdiction: "India/Central" },
      limit: 5,
    });
  });

  it("uses the exact manual document route, token, method, and normalized body", async () => {
    const fetchMock = vi.fn(
      async (_input: RequestInfo | URL, _init?: RequestInit) =>
        new Response(JSON.stringify(manualDocumentSearchFixture()), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await searchAskDocuments(
      {
        schema_version: "1",
        query: " deviation   charge ",
        exact_phrase: true,
        issuer: " CERC ",
        within_document: " generators ",
        limit: 20,
      },
      authFixture.explicitAuth,
    );

    const [input, init] = fetchMock.mock.calls[0] ?? [];
    expect(new URL(String(input)).pathname).toBe(
      "/chat/documents/search",
    );
    expect(init?.method).toBe("POST");
    expect(new Headers(init?.headers).get("Authorization")).toBe(
      `Bearer ${authFixture.explicitAuth}`,
    );
    expect(JSON.parse(String(init?.body))).toEqual({
      schema_version: "1",
      query: "deviation charge",
      exact_phrase: true,
      issuer: "CERC",
      within_document: "generators",
      limit: 20,
    });
  });
});
