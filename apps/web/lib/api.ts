import type { z } from "zod";

import {
  adminAnalyticsSchema,
  adminDocumentListSchema,
  adminEventListSchema,
  adminFamilyListSchema,
  adminUserListSchema,
  adminUserSchema,
  chatHistorySchema,
  chatResponseSchema,
  crawlRunListSchema,
  crawlTriggerResponseSchema,
  digestResponseSchema,
  digestEventSchema,
  eventBookmarkStateSchema,
  eventListSchema,
  eventReadStateSchema,
  healthResponseSchema,
  intelligenceDeadlineListSchema,
  intelligenceReadinessSchema,
  obligationGroupListSchema,
  ragDocumentChunkStatusListSchema,
  ragProcessResultSchema,
  ragQueueSchema,
  ragRetrievalPreviewSchema,
  ragStatusSchema,
  ragVectorSearchSchema,
  sourceHealthListSchema,
  sourceHealthSchema,
  sourcePageCheckpointListSchema,
  sourcePageListSchema,
  sourcePageSchema,
  stakeholderIntelligenceListSchema,
  subscriptionSettingsSchema,
  systemDocumentListSchema,
  systemDocumentSchema,
} from "./schemas";

export type {
  AdminAnalytics,
  AdminDocument,
  AdminEvent,
  AdminFamily,
  AdminUser,
  ChatHistoryItem,
  ChatResponse,
  CrawlRun,
  CrawlTriggerResponse,
  DigestEvent,
  DigestResponse,
  HealthResponse,
  IntelligenceDeadline,
  IntelligenceDocumentRef,
  IntelligenceObligation,
  IntelligenceReadiness,
  RagCitation,
  RagDocumentChunkStatus,
  RagProcessResult,
  RagQueueJob,
  RagRetrievalHit,
  RagRetrievalPreview,
  RagStatus,
  SourceHealth,
  SourcePage,
  SourcePageCheckpoint,
  StakeholderIntelligence,
  StakeholderObligationGroup,
  SubscriptionSettings,
  SummaryPayload,
  SystemDocument,
} from "./schemas";

import type { SourceHealth, SourcePage, SubscriptionSettings } from "./schemas";

export type SourceCreatePayload = Pick<
  SourceHealth,
  "code" | "name" | "jurisdiction" | "url" | "crawler_type" | "allowed_domains" | "enabled"
> & {
  hint?: string | null;
};

export type SourcePageCreatePayload = Pick<SourcePage, "name" | "url" | "page_type" | "priority" | "enabled">;

type ImportMetaWithEnv = ImportMeta & {
  env?: Record<string, string | undefined>;
};

const env = (import.meta as ImportMetaWithEnv).env ?? {};
const nextApiBaseUrl =
  typeof process === "undefined" ? undefined : process.env.NEXT_PUBLIC_API_BASE_URL;
const API_BASE_URL =
  nextApiBaseUrl ?? env.NEXT_PUBLIC_API_BASE_URL ?? env.VITE_API_BASE_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  status?: number;
  constructor(message: string, status?: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

export class ValidationError extends Error {
  path: string;
  issues: unknown;
  constructor(path: string, issues: unknown) {
    super(`Unexpected response shape from ${path}`);
    this.name = "ValidationError";
    this.path = path;
    this.issues = issues;
  }
}

export async function apiFetch<T>(
  path: string,
  token?: string,
  init: RequestInit = {},
): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(init.headers ?? {}),
    },
  });
  if (!response.ok) {
    const detail = await response.text().catch(() => "");
    throw new ApiError(detail || `API request failed: ${response.status}`, response.status);
  }
  return response.json() as Promise<T>;
}

async function validatedFetch<S extends z.ZodType>(
  path: string,
  schema: S,
  token?: string,
  init: RequestInit = {},
): Promise<z.infer<S>> {
  const data = await apiFetch<unknown>(path, token, init);
  const result = schema.safeParse(data);
  if (!result.success) {
    if (typeof console !== "undefined") {
      console.error(`[api] response validation failed for ${path}`, result.error.issues);
    }
    throw new ValidationError(path, result.error.issues);
  }
  return result.data;
}

export function getLatestDigest(token?: string) {
  return validatedFetch("/digests/latest", digestResponseSchema, token);
}

export function getHealth() {
  return validatedFetch("/health", healthResponseSchema);
}

export function getIntelligenceDeadlines(
  token?: string,
  filters: {
    issuer?: string;
    deadline_type?: string;
    stakeholder?: string;
    status?: "active" | "historical" | "all";
  } = {},
) {
  const params = new URLSearchParams();
  if (filters.issuer) params.set("issuer", filters.issuer);
  if (filters.deadline_type && filters.deadline_type !== "all") {
    params.set("deadline_type", filters.deadline_type);
  }
  if (filters.stakeholder && filters.stakeholder !== "all") {
    params.set("stakeholder", filters.stakeholder);
  }
  if (filters.status) params.set("status", filters.status);
  const suffix = params.toString() ? `?${params.toString()}` : "";
  return validatedFetch(`/intelligence/deadlines${suffix}`, intelligenceDeadlineListSchema, token);
}

export function getIntelligenceObligations(
  token?: string,
  filters: { stakeholder?: string; issuer?: string } = {},
) {
  const params = new URLSearchParams();
  if (filters.stakeholder && filters.stakeholder !== "all") {
    params.set("stakeholder", filters.stakeholder);
  }
  if (filters.issuer) params.set("issuer", filters.issuer);
  const suffix = params.toString() ? `?${params.toString()}` : "";
  return validatedFetch(`/intelligence/obligations${suffix}`, obligationGroupListSchema, token);
}

export function getStakeholderIntelligence(token?: string) {
  return validatedFetch("/intelligence/stakeholders", stakeholderIntelligenceListSchema, token);
}

export function getIntelligenceReadiness(token?: string) {
  return validatedFetch("/intelligence/readiness", intelligenceReadinessSchema, token);
}

export function getEvents(
  token?: string,
  filters: {
    query?: string;
    jurisdiction?: string;
    source?: string;
    topic?: string;
    bookmarked?: boolean;
    page?: number;
  } = {},
) {
  const params = new URLSearchParams();
  if (filters.query) params.set("q", filters.query);
  if (filters.jurisdiction && filters.jurisdiction !== "all") {
    params.set("jurisdiction", filters.jurisdiction);
  }
  if (filters.source) params.set("source", filters.source);
  if (filters.topic && filters.topic !== "all") params.set("topic", filters.topic);
  if (filters.bookmarked !== undefined) params.set("bookmarked", String(filters.bookmarked));
  if (filters.page) params.set("page", String(filters.page));
  const suffix = params.toString() ? `?${params.toString()}` : "";
  return validatedFetch(`/events${suffix}`, eventListSchema, token);
}

export function getEvent(eventId: number, token?: string) {
  return validatedFetch(`/events/${eventId}`, digestEventSchema, token);
}

export function sendChat(message: string, eventId: number | null, token?: string) {
  return validatedFetch("/chat", chatResponseSchema, token, {
    method: "POST",
    body: JSON.stringify({ message, event_id: eventId }),
  });
}

export function getChatHistory(token?: string, eventId?: number | null) {
  const suffix = eventId ? `?event_id=${eventId}` : "";
  return validatedFetch(`/chat/history${suffix}`, chatHistorySchema, token);
}

export function markRead(eventId: number, token?: string) {
  return validatedFetch(`/events/${eventId}/read`, eventReadStateSchema, token, {
    method: "POST",
  });
}

export function toggleBookmark(eventId: number, token?: string) {
  return validatedFetch(`/events/${eventId}/bookmark`, eventBookmarkStateSchema, token, {
    method: "POST",
  });
}

export function getSubscriptions(token?: string) {
  return validatedFetch("/subscriptions", subscriptionSettingsSchema, token);
}

export function saveSubscriptions(payload: SubscriptionSettings, token?: string) {
  return validatedFetch("/subscriptions", subscriptionSettingsSchema, token, {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}

export function getSources(token?: string) {
  return validatedFetch("/admin/sources", sourceHealthListSchema, token);
}

export function createSource(payload: SourceCreatePayload, token?: string) {
  return validatedFetch("/admin/sources", sourceHealthSchema, token, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function updateSource(
  sourceId: number,
  payload: Partial<
    Pick<SourceHealth, "enabled" | "name" | "code" | "url" | "jurisdiction" | "crawler_type">
  >,
  token?: string,
) {
  return validatedFetch(`/admin/sources/${sourceId}`, sourceHealthSchema, token, {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}

export function toggleSource(source: SourceHealth, token?: string) {
  return updateSource(source.id, { enabled: !source.enabled }, token);
}

export function deleteSource(sourceId: number, token?: string) {
  return apiFetch<{ source_id: number; deleted: boolean }>(`/admin/sources/${sourceId}`, token, {
    method: "DELETE",
  });
}

export function createSourcePage(sourceId: number, payload: SourcePageCreatePayload, token?: string) {
  return validatedFetch(`/admin/sources/${sourceId}/pages`, sourcePageSchema, token, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function updateSourcePage(
  pageId: number,
  payload: Partial<SourcePageCreatePayload>,
  token?: string,
) {
  return validatedFetch(`/admin/pages/${pageId}`, sourcePageSchema, token, {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}

export function deleteSourcePage(pageId: number, token?: string) {
  return apiFetch<{ page_id: number; source_id: number | null; deleted: boolean }>(
    `/admin/pages/${pageId}`,
    token,
    { method: "DELETE" },
  );
}

export function getRuns(token?: string) {
  return validatedFetch("/admin/runs", crawlRunListSchema, token);
}

export function getSourcePages(token?: string) {
  return validatedFetch("/admin/pages", sourcePageListSchema, token);
}

export function getSourcePageCheckpoints(token?: string) {
  return validatedFetch("/admin/checkpoints", sourcePageCheckpointListSchema, token);
}

export function getAdminDocuments(token?: string, limit = 100) {
  return validatedFetch(`/admin/documents?limit=${limit}`, adminDocumentListSchema, token);
}

export function getAdminEvents(token?: string, limit = 100) {
  return validatedFetch(`/admin/events?limit=${limit}`, adminEventListSchema, token);
}

export function getAdminFamilies(token?: string, limit = 100) {
  return validatedFetch(`/admin/families?limit=${limit}`, adminFamilyListSchema, token);
}

export function getAdminAnalytics(token?: string) {
  return validatedFetch("/admin/analytics", adminAnalyticsSchema, token);
}

export function getAdminUsers(token?: string) {
  return validatedFetch("/admin/users", adminUserListSchema, token);
}

export function updateAdminUserRole(userId: string, role: "user" | "admin", token?: string) {
  return validatedFetch(`/admin/users/${userId}`, adminUserSchema, token, {
    method: "PUT",
    body: JSON.stringify({ role }),
  });
}

export function getRagStatus(token?: string) {
  return validatedFetch("/admin/rag/status", ragStatusSchema, token);
}

export function getRagQueue(token?: string, limit = 100) {
  return validatedFetch(`/admin/rag/queue?limit=${limit}`, ragQueueSchema, token);
}

export function processRagJobs(token?: string, limit = 25, includeProcessing = false) {
  const params = new URLSearchParams({
    limit: String(limit),
    include_processing: String(includeProcessing),
  });
  return validatedFetch(`/admin/rag/process?${params.toString()}`, ragProcessResultSchema, token, {
    method: "POST",
  });
}

export function requeueProcessingRagJobs(token?: string, limit?: number) {
  const suffix = typeof limit === "number" ? `?limit=${limit}` : "";
  return validatedFetch(`/admin/rag/requeue-processing${suffix}`, ragProcessResultSchema, token, {
    method: "POST",
  });
}

export function enqueueExistingRagDocuments(token?: string, limit?: number) {
  const suffix = typeof limit === "number" ? `?limit=${limit}` : "";
  return validatedFetch(`/admin/rag/enqueue-existing${suffix}`, ragProcessResultSchema, token, {
    method: "POST",
  });
}

export function getRagChunks(token?: string) {
  return validatedFetch("/admin/rag/chunks", ragDocumentChunkStatusListSchema, token);
}

export function inspectRagRetrieval(query: string, token?: string, limit = 15) {
  const params = new URLSearchParams({ query, limit: String(limit) });
  return validatedFetch(`/admin/rag/retrieval?${params.toString()}`, ragRetrievalPreviewSchema, token);
}

export function inspectRagContext(query: string, token?: string, limit = 15) {
  const params = new URLSearchParams({ query, limit: String(limit) });
  return validatedFetch(`/admin/rag/context?${params.toString()}`, ragRetrievalPreviewSchema, token);
}

export function inspectRagPrompt(query: string, token?: string, limit = 15) {
  const params = new URLSearchParams({ query, limit: String(limit) });
  return validatedFetch(`/admin/rag/prompt?${params.toString()}`, ragRetrievalPreviewSchema, token);
}

export function inspectRagVectorSearch(query: string, token?: string, limit = 10) {
  const params = new URLSearchParams({ query, limit: String(limit) });
  return validatedFetch(`/admin/rag/vector-search?${params.toString()}`, ragVectorSearchSchema, token);
}

export function crawlSource(sourceId: number, token?: string) {
  return validatedFetch(`/admin/sources/${sourceId}/crawl`, crawlTriggerResponseSchema, token, {
    method: "POST",
  });
}

export function crawlSourcePage(pageId: number, token?: string) {
  return validatedFetch(`/admin/pages/${pageId}/crawl`, crawlTriggerResponseSchema, token, {
    method: "POST",
  });
}

export function getDocs(token?: string) {
  return validatedFetch("/meta/docs", systemDocumentListSchema, token);
}

export function getDoc(slug: string, token?: string) {
  return validatedFetch(`/meta/docs/${slug}`, systemDocumentSchema, token);
}

export function exportLatestUrl(format: "json" | "csv" | "markdown") {
  return `${API_BASE_URL}/exports/latest?format=${format}`;
}

export async function downloadLatestExport(
  format: "json" | "csv" | "markdown",
  token?: string,
) {
  const response = await fetch(exportLatestUrl(format), {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  if (!response.ok) throw new ApiError(`Export failed: ${response.status}`, response.status);
  const blob = await response.blob();
  const disposition = response.headers.get("content-disposition") ?? "";
  const match = disposition.match(/filename="([^"]+)"/);
  const filename = match?.[1] ?? `resolven-regulatory-ai.${format === "markdown" ? "md" : format}`;
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}
