import { useQuery } from "@tanstack/react-query";

import {
  getAdminAnalytics,
  getAdminDocuments,
  getAdminEvents,
  getAdminFamilies,
  getAdminUsers,
  getChatHistory,
  getEvent,
  getEvents,
  getHealth,
  getIntelligenceDeadlines,
  getIntelligenceObligations,
  getIntelligenceReadiness,
  getLatestDigest,
  getRagChunks,
  getRagQueue,
  getRagStatus,
  getRuns,
  getSourcePageCheckpoints,
  getSourcePages,
  getSources,
  getStakeholderIntelligence,
  getSubscriptions,
} from "./api";

export const queryKeys = {
  health: ["health"] as const,
  digest: ["digest", "latest"] as const,
  events: (filters: Record<string, unknown>) => ["events", filters] as const,
  subscriptions: ["subscriptions"] as const,
  event: (eventId: number) => ["event", eventId] as const,
  chatHistory: (eventId?: number | null) => ["chat", "history", eventId ?? null] as const,
  intelligence: {
    deadlines: ["intelligence", "deadlines"] as const,
    obligations: ["intelligence", "obligations"] as const,
    stakeholders: ["intelligence", "stakeholders"] as const,
    readiness: ["intelligence", "readiness"] as const,
  },
  admin: {
    sources: ["admin", "sources"] as const,
    runs: ["admin", "runs"] as const,
    pages: ["admin", "pages"] as const,
    checkpoints: ["admin", "checkpoints"] as const,
    documents: ["admin", "documents"] as const,
    events: ["admin", "events"] as const,
    families: ["admin", "families"] as const,
    analytics: ["admin", "analytics"] as const,
    users: ["admin", "users"] as const,
    ragStatus: ["admin", "rag", "status"] as const,
    ragQueue: ["admin", "rag", "queue"] as const,
    ragChunks: ["admin", "rag", "chunks"] as const,
  },
};

export function useHealthQuery() {
  return useQuery({
    queryKey: queryKeys.health,
    queryFn: () => getHealth(),
    staleTime: 60_000,
  });
}

export function useDigestQuery(token: string | undefined, enabled: boolean) {
  return useQuery({
    queryKey: queryKeys.digest,
    queryFn: () => getLatestDigest(token),
    enabled,
  });
}

export function useEventsQuery(
  token: string | undefined,
  enabled: boolean,
  filters: Parameters<typeof getEvents>[1] = {},
) {
  return useQuery({
    queryKey: queryKeys.events(filters),
    queryFn: () => getEvents(token, filters),
    enabled,
  });
}

export function useSubscriptionsQuery(token: string | undefined, enabled: boolean) {
  return useQuery({
    queryKey: queryKeys.subscriptions,
    queryFn: () => getSubscriptions(token),
    enabled,
  });
}

/** Admin gate probe: succeeds only for admins; never retried so 403 resolves fast. */
export function useSourcesQuery(token: string | undefined, enabled: boolean) {
  return useQuery({
    queryKey: queryKeys.admin.sources,
    queryFn: () => getSources(token),
    enabled,
    retry: false,
  });
}

export function useRunsQuery(token: string | undefined, enabled: boolean) {
  return useQuery({
    queryKey: queryKeys.admin.runs,
    queryFn: () => getRuns(token),
    enabled,
    retry: false,
  });
}

export function useEventQuery(eventId: number | undefined, token: string | undefined, enabled: boolean) {
  return useQuery({
    queryKey: queryKeys.event(eventId ?? -1),
    queryFn: () => getEvent(eventId as number, token),
    enabled: enabled && typeof eventId === "number" && eventId > 0,
  });
}

export function useChatHistoryQuery(token: string | undefined, enabled: boolean) {
  return useQuery({
    queryKey: queryKeys.chatHistory(null),
    queryFn: () => getChatHistory(token),
    enabled,
  });
}

export function useDeadlinesQuery(token: string | undefined, enabled: boolean) {
  return useQuery({
    queryKey: queryKeys.intelligence.deadlines,
    queryFn: () => getIntelligenceDeadlines(token, { status: "active" }),
    enabled,
  });
}

export function useObligationsQuery(token: string | undefined, enabled: boolean) {
  return useQuery({
    queryKey: queryKeys.intelligence.obligations,
    queryFn: () => getIntelligenceObligations(token),
    enabled,
  });
}

export function useStakeholdersQuery(token: string | undefined, enabled: boolean) {
  return useQuery({
    queryKey: queryKeys.intelligence.stakeholders,
    queryFn: () => getStakeholderIntelligence(token),
    enabled,
  });
}

export function useReadinessQuery(token: string | undefined, enabled: boolean) {
  return useQuery({
    queryKey: queryKeys.intelligence.readiness,
    queryFn: () => getIntelligenceReadiness(token),
    enabled,
  });
}

export function useSourcePagesQuery(token: string | undefined, enabled: boolean) {
  return useQuery({
    queryKey: queryKeys.admin.pages,
    queryFn: () => getSourcePages(token),
    enabled,
  });
}

export function useCheckpointsQuery(token: string | undefined, enabled: boolean) {
  return useQuery({
    queryKey: queryKeys.admin.checkpoints,
    queryFn: () => getSourcePageCheckpoints(token),
    enabled,
  });
}

export function useAdminDocumentsQuery(token: string | undefined, enabled: boolean) {
  return useQuery({
    queryKey: queryKeys.admin.documents,
    queryFn: () => getAdminDocuments(token),
    enabled,
  });
}

export function useAdminEventsQuery(token: string | undefined, enabled: boolean) {
  return useQuery({
    queryKey: queryKeys.admin.events,
    queryFn: () => getAdminEvents(token),
    enabled,
  });
}

export function useAdminFamiliesQuery(token: string | undefined, enabled: boolean) {
  return useQuery({
    queryKey: queryKeys.admin.families,
    queryFn: () => getAdminFamilies(token),
    enabled,
  });
}

export function useAdminAnalyticsQuery(token: string | undefined, enabled: boolean) {
  return useQuery({
    queryKey: queryKeys.admin.analytics,
    queryFn: () => getAdminAnalytics(token),
    enabled,
  });
}

export function useAdminUsersQuery(token: string | undefined, enabled: boolean) {
  return useQuery({
    queryKey: queryKeys.admin.users,
    queryFn: () => getAdminUsers(token),
    enabled,
  });
}

export function useRagStatusQuery(token: string | undefined, enabled: boolean) {
  return useQuery({
    queryKey: queryKeys.admin.ragStatus,
    queryFn: () => getRagStatus(token),
    enabled,
  });
}

export function useRagQueueQuery(token: string | undefined, enabled: boolean) {
  return useQuery({
    queryKey: queryKeys.admin.ragQueue,
    queryFn: () => getRagQueue(token),
    enabled,
  });
}

export function useRagChunksQuery(token: string | undefined, enabled: boolean) {
  return useQuery({
    queryKey: queryKeys.admin.ragChunks,
    queryFn: () => getRagChunks(token),
    enabled,
  });
}
