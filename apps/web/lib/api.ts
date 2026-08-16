import { z } from "zod";

import { supabase } from "./supabase";
import {
  askCitationDetailSchema,
  askMessageEvidenceSchema,
  askMessageSourcesSchema,
  askSavedItemListSchema,
} from "./ask-ai-evidence";
import {
  askEntityLookupRequestSchema,
  askEntityLookupResponseSchema,
} from "./ask-ai-entities";
import type { AskEntityLookupRequest } from "./ask-ai-entities";
import {
  askManualDocumentSearchRequestSchema,
  askManualDocumentSearchResponseSchema,
} from "./ask-ai-manual-search";
import type {
  AskManualDocumentSearchRequest,
} from "./ask-ai-manual-search";
import {
  askFederatedSearchRequestSchema,
  askFederatedSearchResponseSchema,
} from "./ask-ai-search";
import type { AskFederatedSearchRequest } from "./ask-ai-search";
import {
  askSessionExportSchema,
  askSessionListQuerySchema,
  askSessionListSchema,
  askSessionPatchRequestSchema,
  askSessionSchema,
} from "./ask-ai-sessions";
import type {
  AskSessionListQuery,
  AskSessionPatchRequest,
} from "./ask-ai-sessions";
import { askTurnListSchema } from "./ask-ai-turns";
import {
  adminAnalyticsSchema,
  adminDocumentListSchema,
  adminEventListSchema,
  adminFamilyListSchema,
  adminUserListSchema,
  adminUserSchema,
  chatConversationDetailSchema,
  chatConversationSummarySchema,
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
  sourceCatalogListSchema,
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
  SourceCatalogItem,
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
import {
  parseAskErrorResponse,
} from "./ask-ai-errors";
import type { AskErrorCode } from "./ask-ai-errors";

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

async function getSessionAccessToken() {
  if (!supabase) return undefined;
  const {
    data: { session },
    error,
  } = await supabase.auth.getSession();
  if (error) throw error;
  return session?.access_token;
}

async function authorizedFetch(
  input: RequestInfo | URL,
  init: RequestInit = {},
  providedAccessToken?: string,
) {
  const accessToken = providedAccessToken ?? (await getSessionAccessToken());
  const headers = new Headers(init.headers);
  if (accessToken) {
    headers.set("Authorization", `Bearer ${accessToken}`);
  } else {
    headers.delete("Authorization");
  }
  return fetch(input, { ...init, headers });
}

export class ApiError extends Error {
  status?: number;
  code?: AskErrorCode;
  correlationId?: string;
  constructor(
    message: string,
    status?: number,
    code?: AskErrorCode,
    correlationId?: string,
  ) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.correlationId = correlationId;
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
  const headers = new Headers(init.headers);
  if (!headers.has("Content-Type")) headers.set("Content-Type", "application/json");
  const response = await authorizedFetch(
    `${API_BASE_URL}${path}`,
    { ...init, headers },
    token,
  );
  if (!response.ok) {
    const detail = await response.text().catch(() => "");
    const parsed = parseAskErrorResponse(
      detail,
      response.headers.get("x-correlation-id") ?? undefined,
    );
    throw new ApiError(
      parsed.message || `API request failed: ${response.status}`,
      response.status,
      parsed.code,
      parsed.correlationId,
    );
  }
  if (response.status === 204) return undefined as T;
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

export function sendChat(
  message: string,
  eventId: number | null,
  token?: string,
  sessionId?: string | null,
) {
  return validatedFetch("/chat", chatResponseSchema, token, {
    method: "POST",
    body: JSON.stringify({
      message,
      event_id: eventId,
      session_id: sessionId ?? null,
    }),
  });
}

export function getChatHistory(token?: string, eventId?: number | null) {
  const suffix = eventId ? `?event_id=${eventId}` : "";
  return validatedFetch(`/chat/history${suffix}`, chatHistorySchema, token);
}

export function listChatConversations(token?: string) {
  return validatedFetch(
    "/chat/conversations",
    z.array(chatConversationSummarySchema),
    token,
  );
}

export function getChatConversation(sessionId: string, token?: string) {
  return validatedFetch(
    `/chat/conversations/${sessionId}`,
    chatConversationDetailSchema,
    token,
  );
}

export function getAskSessions(
  token: string,
  page: AskSessionListQuery = {},
) {
  const query = askSessionListQuerySchema.parse(page);
  const params = new URLSearchParams();
  if (query.cursor) params.set("cursor", query.cursor);
  if (query.limit !== undefined) params.set("limit", String(query.limit));
  if (query.q !== undefined) params.set("q", query.q);
  if (query.knowledge_mode !== undefined) {
    params.set("knowledge_mode", query.knowledge_mode);
  }
  if (query.entity !== undefined) params.set("entity", query.entity);
  if (query.archived !== undefined) {
    params.set("archived", String(query.archived));
  }
  if (query.pinned !== undefined) params.set("pinned", String(query.pinned));
  const suffix = params.size > 0 ? `?${params.toString()}` : "";
  return validatedFetch(`/chat/sessions${suffix}`, askSessionListSchema, token);
}

export function resolveAskEntity(
  request: AskEntityLookupRequest,
  token: string,
) {
  const payload = askEntityLookupRequestSchema.parse(request);
  return validatedFetch(
    "/chat/entities/resolve",
    askEntityLookupResponseSchema,
    token,
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
  );
}

export function searchAskResearch(
  request: AskFederatedSearchRequest,
  token: string,
) {
  const payload = askFederatedSearchRequestSchema.parse(request);
  return validatedFetch(
    "/chat/search",
    askFederatedSearchResponseSchema,
    token,
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
  );
}

export function searchAskDocuments(
  request: AskManualDocumentSearchRequest,
  token: string,
) {
  const payload = askManualDocumentSearchRequestSchema.parse(request);
  return validatedFetch(
    "/chat/documents/search",
    askManualDocumentSearchResponseSchema,
    token,
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
  );
}

export function getAskSession(sessionId: string, token: string) {
  return validatedFetch(
    `/chat/sessions/${encodeURIComponent(sessionId)}`,
    askSessionSchema,
    token,
  );
}

export function patchAskSession(
  sessionId: string,
  patch: AskSessionPatchRequest,
  token: string,
) {
  const payload = askSessionPatchRequestSchema.parse(patch);
  return validatedFetch(
    `/chat/sessions/${encodeURIComponent(sessionId)}`,
    askSessionSchema,
    token,
    {
      method: "PATCH",
      body: JSON.stringify(payload),
    },
  );
}

function postAskSessionAction(
  sessionId: string,
  action: "archive" | "restore" | "duplicate",
  token: string,
) {
  return validatedFetch(
    `/chat/sessions/${encodeURIComponent(sessionId)}/${action}`,
    askSessionSchema,
    token,
    { method: "POST" },
  );
}

export function archiveAskSession(sessionId: string, token: string) {
  return postAskSessionAction(sessionId, "archive", token);
}

export function restoreAskSession(sessionId: string, token: string) {
  return postAskSessionAction(sessionId, "restore", token);
}

export function duplicateAskSession(sessionId: string, token: string) {
  return postAskSessionAction(sessionId, "duplicate", token);
}

export function exportAskSession(sessionId: string, token: string) {
  return validatedFetch(
    `/chat/sessions/${encodeURIComponent(sessionId)}/export`,
    askSessionExportSchema,
    token,
  );
}

export async function deleteAskSession(sessionId: string, token: string) {
  await apiFetch<void>(
    `/chat/sessions/${encodeURIComponent(sessionId)}`,
    token,
    { method: "DELETE" },
  );
}

export function getAskSessionMessages(
  sessionId: string,
  token: string,
  page: { cursor?: string | null; limit?: number } = {},
) {
  const params = new URLSearchParams();
  if (page.cursor) params.set("cursor", page.cursor);
  if (page.limit !== undefined) params.set("limit", String(page.limit));
  const suffix = params.size > 0 ? `?${params.toString()}` : "";
  const encodedSessionId = encodeURIComponent(sessionId);
  return validatedFetch(
    `/chat/sessions/${encodedSessionId}/messages${suffix}`,
    askTurnListSchema,
    token,
  );
}

export function getAskMessageEvidence(messageId: string, token: string) {
  return validatedFetch(
    `/chat/messages/${encodeURIComponent(messageId)}`,
    askMessageEvidenceSchema,
    token,
  );
}

export function getAskMessageSources(messageId: string, token: string) {
  const encodedMessageId = encodeURIComponent(messageId);
  return validatedFetch(
    `/chat/messages/${encodedMessageId}/sources`,
    askMessageSourcesSchema,
    token,
  );
}

export function getAskCitationDetail(
  messageId: string,
  citationId: string,
  token: string,
) {
  return validatedFetch(
    `/chat/messages/${encodeURIComponent(messageId)}/citations/${encodeURIComponent(citationId)}`,
    askCitationDetailSchema,
    token,
  );
}

export function getAskSavedItems(sessionId: string, token: string) {
  const encodedSessionId = encodeURIComponent(sessionId);
  return validatedFetch(
    `/chat/sessions/${encodedSessionId}/saved-items`,
    askSavedItemListSchema,
    token,
  );
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

export function getSourceCatalog(token?: string) {
  return validatedFetch("/sources/catalog", sourceCatalogListSchema, token);
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
  _token?: string,
) {
  const response = await authorizedFetch(exportLatestUrl(format));
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
