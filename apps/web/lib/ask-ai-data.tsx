"use client";

import {
  useMutation,
  useInfiniteQuery,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import {
  createContext,
  useContext,
  useMemo,
} from "react";
import type { ReactNode } from "react";

import { useAuth } from "@/app/components/auth/AuthProvider";

import {
  archiveAskSession,
  deleteAskSession,
  duplicateAskSession,
  exportAskSession,
  getAskMessageEvidence,
  getAskMessageSources,
  getAskSavedItems,
  getAskSession,
  getAskSessionMessages,
  getAskSessions,
  patchAskSession,
  restoreAskSession,
  resolveAskEntity,
  searchAskDocuments,
  searchAskResearch,
} from "./api";
import {
  askEntityLookupRequestSchema,
  askEntityLookupResponseSchema,
} from "./ask-ai-entities";
import type {
  AskEntityLookupRequest,
  AskEntityLookupResponse,
} from "./ask-ai-entities";
import {
  askManualDocumentSearchRequestSchema,
  askManualDocumentSearchResponseSchema,
} from "./ask-ai-manual-search";
import type {
  AskManualDocumentSearchRequest,
  AskManualDocumentSearchResponse,
} from "./ask-ai-manual-search";
import {
  askMessageEvidenceSchema,
  askMessageSourcesSchema,
  askSavedItemListSchema,
} from "./ask-ai-evidence";
import { askStructuredResponseSchema } from "./ask-ai-response";
import {
  askFederatedSearchRequestSchema,
  askFederatedSearchResponseSchema,
} from "./ask-ai-search";
import type {
  AskFederatedSearchRequest,
  AskFederatedSearchResponse,
} from "./ask-ai-search";
import {
  askSessionExportSchema,
  askSessionIdSchema,
  askSessionLifecycleActionSchema,
  askSessionListQuerySchema,
  askSessionListSchema,
  askSessionSchema,
} from "./ask-ai-sessions";
import type {
  AskSession,
  AskSessionExport,
  AskSessionLifecycleAction,
  AskSessionListQuery,
} from "./ask-ai-sessions";
import { askTurnListSchema } from "./ask-ai-turns";

const DEFAULT_SESSION_PAGE_SIZE = 20;
const DEFAULT_TURN_PAGE_SIZE = 20;

export type ResearchRunIdentity = Readonly<{
  sessionId: string;
  messageId: string;
  runId: string;
  responseVersion: number;
}>;

type PageRequest = Readonly<{
  cursor: string | null;
  limit: number;
}>;

export type ResearchSessionFilters = Readonly<
  Omit<AskSessionListQuery, "cursor" | "limit">
>;

type AuthenticatedRequest = Readonly<{
  accessToken: string;
}>;

export type ResearchWorkspaceClient = Readonly<{
  listSessions: (
    request: AuthenticatedRequest & PageRequest & ResearchSessionFilters,
  ) => Promise<unknown>;
  getSession: (
    request: AuthenticatedRequest & Readonly<{ sessionId: string }>,
  ) => Promise<unknown>;
  listTurns: (
    request: AuthenticatedRequest &
      PageRequest &
      Readonly<{ sessionId: string }>,
  ) => Promise<unknown>;
  getMessageEvidence: (
    request: AuthenticatedRequest & Readonly<{ messageId: string }>,
  ) => Promise<unknown>;
  getMessageSources: (
    request: AuthenticatedRequest & Readonly<{ messageId: string }>,
  ) => Promise<unknown>;
  listSavedItems: (
    request: AuthenticatedRequest & Readonly<{ sessionId: string }>,
  ) => Promise<unknown>;
  patchSession: (
    request: AuthenticatedRequest &
      Readonly<{
        sessionId: string;
        patch: Extract<
          AskSessionLifecycleAction,
          { type: "patch" }
        >["patch"];
      }>,
  ) => Promise<unknown>;
  archiveSession: (
    request: AuthenticatedRequest & Readonly<{ sessionId: string }>,
  ) => Promise<unknown>;
  restoreSession: (
    request: AuthenticatedRequest & Readonly<{ sessionId: string }>,
  ) => Promise<unknown>;
  duplicateSession: (
    request: AuthenticatedRequest & Readonly<{ sessionId: string }>,
  ) => Promise<unknown>;
  exportSession: (
    request: AuthenticatedRequest & Readonly<{ sessionId: string }>,
  ) => Promise<unknown>;
  deleteSession: (
    request: AuthenticatedRequest & Readonly<{ sessionId: string }>,
  ) => Promise<void>;
  resolveEntity?: (
    request: AuthenticatedRequest & AskEntityLookupRequest,
  ) => Promise<unknown>;
  searchResearch?: (
    request: AuthenticatedRequest & AskFederatedSearchRequest,
  ) => Promise<unknown>;
  searchDocuments?: (
    request: AuthenticatedRequest & AskManualDocumentSearchRequest,
  ) => Promise<unknown>;
  getStructuredResponse?: (
    request: AuthenticatedRequest & ResearchRunIdentity,
  ) => Promise<unknown>;
}>;

const defaultResearchWorkspaceClient: ResearchWorkspaceClient = {
  listSessions: ({ accessToken, cursor, limit, ...filters }) =>
    getAskSessions(accessToken, { cursor, limit, ...filters }),
  getSession: ({ accessToken, sessionId }) =>
    getAskSession(sessionId, accessToken),
  listTurns: ({ accessToken, sessionId, cursor, limit }) =>
    getAskSessionMessages(sessionId, accessToken, { cursor, limit }),
  getMessageEvidence: ({ accessToken, messageId }) =>
    getAskMessageEvidence(messageId, accessToken),
  getMessageSources: ({ accessToken, messageId }) =>
    getAskMessageSources(messageId, accessToken),
  listSavedItems: ({ accessToken, sessionId }) =>
    getAskSavedItems(sessionId, accessToken),
  patchSession: ({ accessToken, sessionId, patch }) =>
    patchAskSession(sessionId, patch, accessToken),
  archiveSession: ({ accessToken, sessionId }) =>
    archiveAskSession(sessionId, accessToken),
  restoreSession: ({ accessToken, sessionId }) =>
    restoreAskSession(sessionId, accessToken),
  duplicateSession: ({ accessToken, sessionId }) =>
    duplicateAskSession(sessionId, accessToken),
  exportSession: ({ accessToken, sessionId }) =>
    exportAskSession(sessionId, accessToken),
  deleteSession: ({ accessToken, sessionId }) =>
    deleteAskSession(sessionId, accessToken),
  resolveEntity: ({ accessToken, ...request }) =>
    resolveAskEntity(request, accessToken),
  searchResearch: ({ accessToken, ...request }) =>
    searchAskResearch(request, accessToken),
  searchDocuments: ({ accessToken, ...request }) =>
    searchAskDocuments(request, accessToken),
};

export const researchWorkspaceKeys = {
  root: ["ask-ai-v2"] as const,
  owner: (ownerId: string) =>
    [...researchWorkspaceKeys.root, "owner", ownerId] as const,
  sessions: (ownerId: string) =>
    [...researchWorkspaceKeys.owner(ownerId), "sessions"] as const,
  sessionList: (
    ownerId: string,
    limit = DEFAULT_SESSION_PAGE_SIZE,
    filters: ResearchSessionFilters = {},
  ) =>
    [
      ...researchWorkspaceKeys.sessions(ownerId),
      "list",
      { limit, ...filters },
    ] as const,
  session: (ownerId: string, sessionId: string) =>
    [
      ...researchWorkspaceKeys.sessions(ownerId),
      "detail",
      sessionId,
    ] as const,
  turns: (
    ownerId: string,
    sessionId: string,
    limit = DEFAULT_TURN_PAGE_SIZE,
  ) =>
    [
      ...researchWorkspaceKeys.turnsRoot(ownerId, sessionId),
      { limit },
    ] as const,
  turnsRoot: (ownerId: string, sessionId: string) =>
    [
      ...researchWorkspaceKeys.session(ownerId, sessionId),
      "turns",
    ] as const,
  turnReconciliations: (ownerId: string, sessionId: string) =>
    [
      ...researchWorkspaceKeys.session(ownerId, sessionId),
      "turn-reconciliations",
    ] as const,
  message: (ownerId: string, messageId: string) =>
    [
      ...researchWorkspaceKeys.owner(ownerId),
      "messages",
      messageId,
    ] as const,
  run: (ownerId: string, messageId: string) =>
    [...researchWorkspaceKeys.message(ownerId, messageId), "run"] as const,
  messageEvidence: (ownerId: string, messageId: string) =>
    researchWorkspaceKeys.run(ownerId, messageId),
  messageSources: (ownerId: string, messageId: string) =>
    [
      ...researchWorkspaceKeys.message(ownerId, messageId),
      "sources",
    ] as const,
  savedItems: (ownerId: string, sessionId: string) =>
    [
      ...researchWorkspaceKeys.session(ownerId, sessionId),
      "saved-items",
    ] as const,
  structuredResponse: (
    ownerId: string,
    identity: ResearchRunIdentity,
  ) =>
    [
      ...researchWorkspaceKeys.session(ownerId, identity.sessionId),
      "messages",
      identity.messageId,
      "runs",
      identity.runId,
      "versions",
      identity.responseVersion,
      "structured-response",
    ] as const,
};

type ResearchWorkspaceDataContextValue = Readonly<{
  ownerId: string | null;
  accessToken: string | null;
  enabled: boolean;
  client: ResearchWorkspaceClient;
}>;

const ResearchWorkspaceDataContext =
  createContext<ResearchWorkspaceDataContextValue | null>(null);

export function ResearchWorkspaceDataProvider({
  children,
  enabled,
  client = defaultResearchWorkspaceClient,
}: {
  children: ReactNode;
  enabled: boolean;
  client?: ResearchWorkspaceClient;
}) {
  const { loading, session, user } = useAuth();
  const ownerId = user?.id ?? null;
  const accessToken = session?.access_token?.trim() || null;
  const value = useMemo<ResearchWorkspaceDataContextValue>(
    () => ({
      ownerId,
      accessToken,
      enabled:
        enabled &&
        !loading &&
        ownerId !== null &&
        accessToken !== null,
      client,
    }),
    [accessToken, client, enabled, loading, ownerId],
  );

  return (
    <ResearchWorkspaceDataContext.Provider value={value}>
      {children}
    </ResearchWorkspaceDataContext.Provider>
  );
}

function useResearchWorkspaceData() {
  const context = useContext(ResearchWorkspaceDataContext);
  if (context === null) {
    throw new Error(
      "Research Workspace hooks require ResearchWorkspaceDataProvider",
    );
  }
  return context;
}

export function useResearchWorkspaceScope() {
  const context = useResearchWorkspaceData();
  return {
    ownerId: context.ownerId,
    enabled: context.enabled,
  } as const;
}

function requiredIdentity(context: ResearchWorkspaceDataContextValue) {
  return {
    ownerId: context.ownerId ?? "signed-out",
    accessToken: context.accessToken ?? "",
  };
}

export function useResearchSessions({
  enabled = true,
  limit = DEFAULT_SESSION_PAGE_SIZE,
  ...requestedFilters
}: {
  enabled?: boolean;
  limit?: number;
} & ResearchSessionFilters = {}) {
  const context = useResearchWorkspaceData();
  const { ownerId, accessToken } = requiredIdentity(context);
  const normalizedRequest = askSessionListQuerySchema.parse({
    limit,
    ...requestedFilters,
  });
  const {
    limit: normalizedLimit = DEFAULT_SESSION_PAGE_SIZE,
    ...filters
  } = normalizedRequest;
  return useInfiniteQuery({
    queryKey: researchWorkspaceKeys.sessionList(
      ownerId,
      normalizedLimit,
      filters,
    ),
    initialPageParam: null as string | null,
    queryFn: async ({ pageParam }) =>
      askSessionListSchema.parse(
        await context.client.listSessions({
          accessToken,
          cursor: pageParam,
          limit: normalizedLimit,
          ...filters,
        }),
      ),
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
    enabled: context.enabled && enabled,
  });
}

export function useResearchSession(
  sessionId: string | null | undefined,
  enabled = true,
) {
  const context = useResearchWorkspaceData();
  const { ownerId, accessToken } = requiredIdentity(context);
  const stableSessionId = sessionId ?? "";
  return useQuery({
    queryKey: researchWorkspaceKeys.session(ownerId, stableSessionId),
    queryFn: async () =>
      askSessionSchema.parse(
        await context.client.getSession({
          accessToken,
          sessionId: stableSessionId,
        }),
      ),
    enabled: context.enabled && enabled && stableSessionId.length > 0,
  });
}

export type ResearchSessionLifecycleResult =
  | Readonly<{
      type: "session";
      action: Exclude<AskSessionLifecycleAction["type"], "delete">;
      session: AskSession;
    }>
  | Readonly<{
      type: "deleted";
      sessionId: string;
    }>;

export function useResearchSessionLifecycle() {
  const context = useResearchWorkspaceData();
  const queryClient = useQueryClient();
  const { ownerId, accessToken } = requiredIdentity(context);
  return useMutation<
    ResearchSessionLifecycleResult,
    Error,
    AskSessionLifecycleAction
  >({
    mutationFn: async (requestedAction) => {
      if (!context.enabled) {
        throw new Error("Research Workspace is unavailable");
      }
      const action = askSessionLifecycleActionSchema.parse(requestedAction);
      if (action.type === "delete") {
        await context.client.deleteSession({
          accessToken,
          sessionId: action.session_id,
        });
        return {
          type: "deleted",
          sessionId: action.session_id,
        };
      }
      const payload =
        action.type === "patch"
          ? await context.client.patchSession({
              accessToken,
              sessionId: action.session_id,
              patch: action.patch,
            })
          : action.type === "archive"
            ? await context.client.archiveSession({
                accessToken,
                sessionId: action.session_id,
              })
            : action.type === "restore"
              ? await context.client.restoreSession({
                  accessToken,
                  sessionId: action.session_id,
                })
              : await context.client.duplicateSession({
                  accessToken,
                  sessionId: action.session_id,
                });
      return {
        type: "session",
        action: action.type,
        session: askSessionSchema.parse(payload),
      };
    },
    onSuccess: async (result) => {
      if (result.type === "deleted") {
        queryClient.removeQueries({
          queryKey: researchWorkspaceKeys.session(
            ownerId,
            result.sessionId,
          ),
        });
      } else {
        queryClient.setQueryData(
          researchWorkspaceKeys.session(ownerId, result.session.id),
          result.session,
        );
      }
      await queryClient.invalidateQueries({
        queryKey: researchWorkspaceKeys.sessions(ownerId),
      });
    },
  });
}

export function useResearchSessionExport() {
  const context = useResearchWorkspaceData();
  const { accessToken } = requiredIdentity(context);
  return useMutation<AskSessionExport, Error, string>({
    mutationFn: async (sessionId) => {
      if (!context.enabled) {
        throw new Error("Research Workspace is unavailable");
      }
      const stableSessionId = askSessionIdSchema.parse(sessionId);
      return askSessionExportSchema.parse(
        await context.client.exportSession({
          accessToken,
          sessionId: stableSessionId,
        }),
      );
    },
  });
}

export function useResearchTurns(
  sessionId: string | null | undefined,
  {
    enabled = true,
    limit = DEFAULT_TURN_PAGE_SIZE,
  }: {
    enabled?: boolean;
    limit?: number;
  } = {},
) {
  const context = useResearchWorkspaceData();
  const { ownerId, accessToken } = requiredIdentity(context);
  const stableSessionId = sessionId ?? "";
  return useInfiniteQuery({
    queryKey: researchWorkspaceKeys.turns(
      ownerId,
      stableSessionId,
      limit,
    ),
    initialPageParam: null as string | null,
    queryFn: async ({ pageParam }) =>
      askTurnListSchema.parse(
        await context.client.listTurns({
          accessToken,
          sessionId: stableSessionId,
          cursor: pageParam,
          limit,
        }),
      ),
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
    enabled:
      context.enabled &&
      enabled &&
      stableSessionId.length > 0,
  });
}

function useResearchMessageRecord(
  messageId: string | null | undefined,
  enabled: boolean,
) {
  const context = useResearchWorkspaceData();
  const { ownerId, accessToken } = requiredIdentity(context);
  const stableMessageId = messageId ?? "";
  return useQuery({
    queryKey: researchWorkspaceKeys.messageEvidence(
      ownerId,
      stableMessageId,
    ),
    queryFn: async () =>
      askMessageEvidenceSchema.parse(
        await context.client.getMessageEvidence({
          accessToken,
          messageId: stableMessageId,
        }),
      ),
    enabled:
      context.enabled &&
      enabled &&
      stableMessageId.length > 0,
  });
}

export function useResearchMessageEvidence(
  messageId: string | null | undefined,
  enabled = true,
) {
  return useResearchMessageRecord(messageId, enabled);
}

export function useResearchRun(
  messageId: string | null | undefined,
  enabled = true,
) {
  const query = useResearchMessageRecord(messageId, enabled);
  return {
    ...query,
    data: query.data?.run,
  };
}

export function useResearchMessageSources(
  messageId: string | null | undefined,
  enabled = true,
) {
  const context = useResearchWorkspaceData();
  const { ownerId, accessToken } = requiredIdentity(context);
  const stableMessageId = messageId ?? "";
  return useQuery({
    queryKey: researchWorkspaceKeys.messageSources(
      ownerId,
      stableMessageId,
    ),
    queryFn: async () =>
      askMessageSourcesSchema.parse(
        await context.client.getMessageSources({
          accessToken,
          messageId: stableMessageId,
        }),
      ),
    enabled:
      context.enabled &&
      enabled &&
      stableMessageId.length > 0,
  });
}

export function useResearchSavedItems(
  sessionId: string | null | undefined,
  enabled = true,
) {
  const context = useResearchWorkspaceData();
  const { ownerId, accessToken } = requiredIdentity(context);
  const stableSessionId = sessionId ?? "";
  return useQuery({
    queryKey: researchWorkspaceKeys.savedItems(
      ownerId,
      stableSessionId,
    ),
    queryFn: async () =>
      askSavedItemListSchema.parse(
        await context.client.listSavedItems({
          accessToken,
          sessionId: stableSessionId,
        }),
      ),
    enabled:
      context.enabled &&
      enabled &&
      stableSessionId.length > 0,
  });
}

export function useResearchStructuredResponse(
  identity: ResearchRunIdentity | null | undefined,
  enabled = true,
) {
  const context = useResearchWorkspaceData();
  const { ownerId, accessToken } = requiredIdentity(context);
  const stableIdentity = identity ?? {
    sessionId: "",
    messageId: "",
    runId: "",
    responseVersion: 0,
  };
  return useQuery({
    queryKey: researchWorkspaceKeys.structuredResponse(
      ownerId,
      stableIdentity,
    ),
    queryFn: async () => {
      const getStructuredResponse =
        context.client.getStructuredResponse;
      if (getStructuredResponse === undefined) {
        throw new Error(
          "Structured response read projection is unavailable",
        );
      }
      return askStructuredResponseSchema.parse(
        await getStructuredResponse({
          accessToken,
          ...stableIdentity,
        }),
      );
    },
    enabled:
      context.enabled &&
      enabled &&
      identity !== null &&
      identity !== undefined &&
      stableIdentity.sessionId.length > 0 &&
      stableIdentity.messageId.length > 0 &&
      stableIdentity.runId.length > 0 &&
      stableIdentity.responseVersion > 0 &&
      context.client.getStructuredResponse !== undefined,
  });
}

export function useResolveResearchEntity() {
  const context = useResearchWorkspaceData();
  const { accessToken } = requiredIdentity(context);
  const available =
    context.enabled && context.client.resolveEntity !== undefined;
  const mutation = useMutation<
    AskEntityLookupResponse,
    Error,
    AskEntityLookupRequest
  >({
    mutationFn: async (requestedLookup) => {
      if (!available || context.client.resolveEntity === undefined) {
        throw new Error("Entity lookup is unavailable");
      }
      const request =
        askEntityLookupRequestSchema.parse(requestedLookup);
      return askEntityLookupResponseSchema.parse(
        await context.client.resolveEntity({
          accessToken,
          ...request,
        }),
      );
    },
  });
  return {
    ...mutation,
    available,
  };
}

export function useFederatedResearchSearch() {
  const context = useResearchWorkspaceData();
  const { accessToken } = requiredIdentity(context);
  const available =
    context.enabled && context.client.searchResearch !== undefined;
  const mutation = useMutation<
    AskFederatedSearchResponse,
    Error,
    AskFederatedSearchRequest
  >({
    mutationFn: async (requestedSearch) => {
      if (!available || context.client.searchResearch === undefined) {
        throw new Error("Research search is unavailable");
      }
      const request =
        askFederatedSearchRequestSchema.parse(requestedSearch);
      return askFederatedSearchResponseSchema.parse(
        await context.client.searchResearch({
          accessToken,
          ...request,
        }),
      );
    },
  });
  return {
    ...mutation,
    available,
  };
}

export function useManualDocumentSearch() {
  const context = useResearchWorkspaceData();
  const { accessToken } = requiredIdentity(context);
  const available =
    context.enabled && context.client.searchDocuments !== undefined;
  const mutation = useMutation<
    AskManualDocumentSearchResponse,
    Error,
    AskManualDocumentSearchRequest
  >({
    mutationFn: async (requestedSearch) => {
      if (!available || context.client.searchDocuments === undefined) {
        throw new Error("Manual document search is unavailable");
      }
      const request =
        askManualDocumentSearchRequestSchema.parse(requestedSearch);
      return askManualDocumentSearchResponseSchema.parse(
        await context.client.searchDocuments({
          accessToken,
          ...request,
        }),
      );
    },
  });
  return {
    ...mutation,
    available,
  };
}
