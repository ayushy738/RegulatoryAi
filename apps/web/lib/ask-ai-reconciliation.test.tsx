import {
  QueryClient,
  QueryClientProvider,
} from "@tanstack/react-query";
import {
  act,
  renderHook,
  waitFor,
} from "@testing-library/react";
import type {
  InfiniteData,
} from "@tanstack/react-query";
import type { ReactNode } from "react";
import {
  afterEach,
  describe,
  expect,
  it,
  vi,
} from "vitest";

import sessionContract from "../../api/backend/tests/fixtures/ask_session_contract.json";
import turnContract from "../../api/backend/tests/fixtures/ask_turn_contract.json";
import {
  ResearchWorkspaceDataProvider,
  researchWorkspaceKeys,
} from "./ask-ai-data";
import type {
  ResearchWorkspaceClient,
} from "./ask-ai-data";
import {
  createResearchTurnReconciler,
  createResearchPendingTurn,
  mergeResearchTurns,
  researchPendingTurnInputSchema,
  researchTurnReconciliationSchema,
  ResearchTurnConflictError,
  useResearchTurnReconciliations,
  useResearchTurnReconciler,
  useResearchTurnsWithPending,
} from "./ask-ai-reconciliation";
import type {
  ResearchPendingTurnInput,
} from "./ask-ai-reconciliation";
import type {
  AskTurn,
  AskTurnList,
} from "./ask-ai-turns";

const authFixture = vi.hoisted(() => {
  const ownerAuth = ["reconciliation", "session"].join("-");
  return {
    ownerAuth,
    state: {
      loading: false,
      session: {
        access_token: ownerAuth,
      },
      user: {
        id: "reconciliation-owner",
      },
    },
  };
});

vi.mock("@/app/components/auth/AuthProvider", () => ({
  useAuth: () => authFixture.state,
}));

const ownerId = "reconciliation-owner";
const sessionId = sessionContract.session_response.id;
const idempotencyKey = "99999999-9999-4999-8999-999999999999";
const persistedTurn = turnContract.turn_list_response.items[0] as AskTurn;
const optimisticTurn: AskTurn = {
  schema_version: "1",
  id: persistedTurn.id,
  user_message: persistedTurn.user_message,
  assistant_message: null,
  run: null,
};
const pendingInput: ResearchPendingTurnInput = {
  session_id: sessionId,
  idempotency_key: idempotencyKey,
  turn: optimisticTurn,
};

type TurnPages = InfiniteData<AskTurnList, unknown>;

function pages(items: AskTurn[]): TurnPages {
  return {
    pages: [
      {
        schema_version: "1",
        items,
        next_cursor: null,
      },
    ],
    pageParams: [null],
  };
}

function records(queryClient: QueryClient, targetOwner = ownerId) {
  return queryClient.getQueryData(
    researchWorkspaceKeys.turnReconciliations(
      targetOwner,
      sessionId,
    ),
  );
}

function createClient(
  listTurns = vi.fn(async () => ({
    schema_version: "1",
    items: [],
    next_cursor: null,
  })),
): ResearchWorkspaceClient {
  return {
    listSessions: vi.fn(async () => sessionContract.list_response),
    getSession: vi.fn(async () => sessionContract.session_response),
    listTurns,
    getMessageEvidence: vi.fn(async () => ({})),
    getMessageSources: vi.fn(async () => ({})),
    listSavedItems: vi.fn(async () => ({
      schema_version: "1",
      items: [],
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
  };
}

function createWrapper(
  queryClient: QueryClient,
  client: ResearchWorkspaceClient,
) {
  function Wrapper({ children }: { children: ReactNode }) {
    return (
      <QueryClientProvider client={queryClient}>
        <ResearchWorkspaceDataProvider
          client={client}
          enabled
        >
          {children}
        </ResearchWorkspaceDataProvider>
      </QueryClientProvider>
    );
  }
  return Wrapper;
}

afterEach(() => {
  authFixture.state.loading = false;
  authFixture.state.session = {
    access_token: authFixture.ownerAuth,
  };
  authFixture.state.user = {
    id: ownerId,
  };
});

describe("Research turn reconciliation contracts", () => {
  it("creates stable client message and idempotency identity", () => {
    const generatedIds = [
      "77777777-7777-4777-8777-777777777777",
      "88888888-8888-4888-8888-888888888888",
    ];
    const created = createResearchPendingTurn(
      {
        session_id: sessionId,
        content: "  New research question  ",
        event_id: 41,
      },
      {
        createId: () => generatedIds.shift()!,
        now: () => "2026-07-27T10:00:00Z",
      },
    );

    expect(created).toEqual({
      session_id: sessionId,
      idempotency_key:
        "77777777-7777-4777-8777-777777777777",
      turn: {
        schema_version: "1",
        id: "88888888-8888-4888-8888-888888888888",
        user_message: {
          schema_version: "1",
          id: "88888888-8888-4888-8888-888888888888",
          event_id: 41,
          role: "user",
          content: "New research question",
          created_at: "2026-07-27T10:00:00Z",
        },
        assistant_message: null,
        run: null,
      },
    });
  });

  it("requires stable optimistic anchors and honest sync states", () => {
    expect(researchPendingTurnInputSchema.parse(pendingInput)).toEqual(
      pendingInput,
    );
    expect(
      researchPendingTurnInputSchema.safeParse({
        ...pendingInput,
        turn: {
          ...optimisticTurn,
          id: "88888888-8888-4888-8888-888888888888",
        },
      }).success,
    ).toBe(false);
    expect(
      researchPendingTurnInputSchema.safeParse({
        ...pendingInput,
        turn: persistedTurn,
      }).success,
    ).toBe(false);
    expect(
      researchTurnReconciliationSchema.safeParse({
        schema_version: "1",
        session_id: sessionId,
        idempotency_key: idempotencyKey,
        state: "unsynced",
        turn: optimisticTurn,
        safe_error_code: null,
        persisted_turn_id: null,
        resolved_turn: null,
      }).success,
    ).toBe(false);
    expect(
      researchTurnReconciliationSchema.safeParse({
        schema_version: "1",
        session_id: sessionId,
        idempotency_key: idempotencyKey,
        state: "synced",
        turn: optimisticTurn,
        safe_error_code: null,
        persisted_turn_id: optimisticTurn.id,
        resolved_turn: {
          ...persistedTurn,
          user_message: {
            ...persistedTurn.user_message!,
            content: "Crossed result",
          },
        },
      }).success,
    ).toBe(false);
  });
});

describe("Research turn cache transactions", () => {
  it("begins once per idempotency key and refuses identity collisions", () => {
    const queryClient = new QueryClient();
    const reconciler = createResearchTurnReconciler({
      queryClient,
      ownerId,
      sessionId,
    });

    const first = reconciler.begin(pendingInput);
    const repeated = reconciler.begin(pendingInput);

    expect(first.state).toBe("saving");
    expect(repeated).toEqual(first);
    expect(reconciler.records()).toHaveLength(1);
    expect(() =>
      reconciler.begin({
        ...pendingInput,
        turn: {
          ...optimisticTurn,
          user_message: {
            ...optimisticTurn.user_message!,
            content: "Different request",
          },
        },
      }),
    ).toThrowError(
      expect.objectContaining({
        code: "IDEMPOTENCY_KEY_CONFLICT",
      }),
    );
    expect(() =>
      reconciler.begin({
        ...pendingInput,
        idempotency_key:
          "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
      }),
    ).toThrowError(
      expect.objectContaining({
        code: "TURN_ID_CONFLICT",
      }),
    );
  });

  it("handles a persisted-server result that wins the begin race", () => {
    const queryClient = new QueryClient();
    queryClient.setQueryData(
      researchWorkspaceKeys.turns(ownerId, sessionId),
      pages([persistedTurn]),
    );
    const reconciler = createResearchTurnReconciler({
      queryClient,
      ownerId,
      sessionId,
    });

    const record = reconciler.begin(pendingInput);

    expect(record).toMatchObject({
      state: "synced",
      persisted_turn_id: persistedTurn.id,
    });
    expect(
      mergeResearchTurns(
        queryClient.getQueryData(
          researchWorkspaceKeys.turns(ownerId, sessionId),
        ),
        reconciler.records(),
      ),
    ).toEqual([persistedTurn]);
  });

  it("reconciles client-first results across cached page sizes exactly once", () => {
    const queryClient = new QueryClient();
    const defaultKey = researchWorkspaceKeys.turns(
      ownerId,
      sessionId,
    );
    const compactKey = researchWorkspaceKeys.turns(
      ownerId,
      sessionId,
      5,
    );
    queryClient.setQueryData(defaultKey, pages([]));
    queryClient.setQueryData(compactKey, pages([]));
    const reconciler = createResearchTurnReconciler({
      queryClient,
      ownerId,
      sessionId,
    });

    reconciler.begin(pendingInput);
    expect(
      mergeResearchTurns(
        queryClient.getQueryData(defaultKey),
        reconciler.records(),
      ),
    ).toEqual([optimisticTurn]);

    const first = reconciler.reconcile(
      idempotencyKey,
      persistedTurn,
    );
    const duplicate = reconciler.reconcile(
      idempotencyKey,
      persistedTurn,
    );

    expect(first.state).toBe("synced");
    expect(duplicate).toEqual(first);
    for (const key of [defaultKey, compactKey]) {
      const data = queryClient.getQueryData<TurnPages>(key);
      expect(data?.pages.flatMap((page) => page.items)).toEqual([
        persistedTurn,
      ]);
    }
    expect(reconciler.records()).toHaveLength(1);
  });

  it("preserves unrelated pages when persisted data arrives during saving", () => {
    const queryClient = new QueryClient();
    const otherTurn = {
      ...optimisticTurn,
      id: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
      user_message: {
        ...optimisticTurn.user_message!,
        id: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
        content: "Earlier question",
        created_at: "2026-07-27T08:00:00Z",
      },
    };
    const key = researchWorkspaceKeys.turns(ownerId, sessionId);
    queryClient.setQueryData(key, {
      pages: [
        {
          schema_version: "1",
          items: [otherTurn],
          next_cursor: "opaque-next",
        },
      ],
      pageParams: [null],
    } satisfies TurnPages);
    const reconciler = createResearchTurnReconciler({
      queryClient,
      ownerId,
      sessionId,
    });
    reconciler.begin(pendingInput);

    reconciler.reconcile(idempotencyKey, persistedTurn);
    const incomplete = queryClient.getQueryData<TurnPages>(key);
    expect(incomplete?.pages).toHaveLength(1);
    expect(incomplete?.pages.flatMap((page) => page.items)).toEqual([
      otherTurn,
    ]);
    expect(incomplete?.pageParams).toEqual([null]);
    expect(incomplete?.pages[0]?.next_cursor).toBe("opaque-next");
    expect(
      mergeResearchTurns(
        queryClient.getQueryData(key),
        reconciler.records(),
      ),
    ).toEqual([otherTurn, persistedTurn]);
    expect(reconciler.records()[0]?.resolved_turn).toEqual(
      persistedTurn,
    );

    queryClient.setQueryData(key, pages([otherTurn, persistedTurn]));
    reconciler.reconcile(idempotencyKey, persistedTurn);
    const data = queryClient.getQueryData<TurnPages>(key);
    expect(data?.pages.flatMap((page) => page.items)).toEqual([
      otherTurn,
      persistedTurn,
    ]);
    expect(reconciler.records()[0]?.resolved_turn).toBeNull();
  });

  it("keeps failed turns recoverable and retries without duplication", () => {
    const queryClient = new QueryClient();
    const reconciler = createResearchTurnReconciler({
      queryClient,
      ownerId,
      sessionId,
    });
    reconciler.begin(pendingInput);

    expect(() =>
      reconciler.markUnsynced(
        idempotencyKey,
        "unsafe provider detail",
      ),
    ).toThrow();
    const failed = reconciler.markUnsynced(
      idempotencyKey,
      "SESSION_SAVE_FAILED",
    );

    expect(failed).toMatchObject({
      state: "unsynced",
      safe_error_code: "SESSION_SAVE_FAILED",
    });
    expect(mergeResearchTurns(undefined, reconciler.records())).toEqual([
      optimisticTurn,
    ]);
    expect(reconciler.retry(idempotencyKey)).toMatchObject({
      state: "saving",
      safe_error_code: null,
    });
    expect(reconciler.records()).toHaveLength(1);
  });

  it("creates a canonical turn page when reconciliation precedes a read", () => {
    const queryClient = new QueryClient();
    const reconciler = createResearchTurnReconciler({
      queryClient,
      ownerId,
      sessionId,
    });
    reconciler.begin(pendingInput);

    reconciler.reconcile(idempotencyKey, persistedTurn);

    expect(
      queryClient.getQueryData(
        researchWorkspaceKeys.turns(ownerId, sessionId),
      ),
    ).toEqual(pages([persistedTurn]));
  });

  it("isolates owners and sessions and refuses disabled mutation", () => {
    const queryClient = new QueryClient();
    const ownerOne = createResearchTurnReconciler({
      queryClient,
      ownerId,
      sessionId,
    });
    const ownerTwo = createResearchTurnReconciler({
      queryClient,
      ownerId: "different-owner",
      sessionId,
    });
    ownerOne.begin(pendingInput);

    expect(ownerTwo.records()).toEqual([]);
    expect(records(queryClient, ownerId)).toHaveLength(1);
    expect(records(queryClient, "different-owner")).toBeUndefined();
    expect(() =>
      createResearchTurnReconciler({
        queryClient,
        ownerId,
        sessionId,
        enabled: false,
      }).begin(pendingInput),
    ).toThrow("Research turn reconciliation is disabled");
  });

  it("refuses a persisted response with crossed stable identity", () => {
    const queryClient = new QueryClient();
    const reconciler = createResearchTurnReconciler({
      queryClient,
      ownerId,
      sessionId,
    });
    reconciler.begin(pendingInput);
    const crossed = {
      ...persistedTurn,
      user_message: {
        ...persistedTurn.user_message!,
        content: "Crossed question",
      },
    };

    expect(() =>
      reconciler.reconcile(idempotencyKey, crossed),
    ).toThrowError(ResearchTurnConflictError);
    expect(queryClient.getQueriesData({
      queryKey: researchWorkspaceKeys.turnsRoot(
        ownerId,
        sessionId,
      ),
    })).toEqual([]);
  });
});

describe("Research turn reconciliation hooks", () => {
  it("keeps a pending turn visible across a provider remount", async () => {
    const queryClient = new QueryClient({
      defaultOptions: {
        queries: {
          retry: false,
          staleTime: 30_000,
        },
      },
    });
    const client = createClient();
    const wrapper = createWrapper(queryClient, client);
    const first = renderHook(
      () => ({
        records: useResearchTurnReconciliations(sessionId),
        reconciler: useResearchTurnReconciler(sessionId),
        view: useResearchTurnsWithPending(sessionId),
      }),
      { wrapper },
    );
    await waitFor(() => {
      expect(first.result.current.records.isSuccess).toBe(true);
      expect(first.result.current.view.isSuccess).toBe(true);
    });

    act(() => {
      first.result.current.reconciler.begin(pendingInput);
    });
    await waitFor(() =>
      expect(first.result.current.view.turns).toEqual([
        optimisticTurn,
      ]),
    );
    first.unmount();

    const second = renderHook(
      () => useResearchTurnsWithPending(sessionId),
      { wrapper },
    );
    await waitFor(() =>
      expect(second.result.current.turns).toEqual([
        optimisticTurn,
      ]),
    );
    expect(client.listTurns).toHaveBeenCalledTimes(1);
  });
});
