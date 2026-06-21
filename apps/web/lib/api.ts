export type DigestEvent = {
  id: number;
  title: string;
  issuing_body: string | null;
  jurisdiction: "central" | "state" | null;
  issue_date: string | null;
  event_type: "NEW" | "CHANGED" | "REPLACEMENT" | "DUPLICATE";
  topic_tags: string[];
  raw_summary: string | null;
  summary: {
    plain_english_summary: string;
    why_it_matters: string;
    affected_segments: string[];
    important_dates: string[];
    action_required: "none" | "monitor" | "urgent";
    confidence: "high" | "medium" | "low";
    evidence_quotes: Array<Record<string, unknown>>;
  } | null;
  source_url: string;
  detected_at: string;
  is_read: boolean;
  is_bookmarked: boolean;
};

export type DigestResponse = {
  digest_date: string;
  event_count: number;
  events: DigestEvent[];
};

export type SubscriptionSettings = {
  jurisdictions: Array<"central" | "state">;
  source_ids: number[];
  topics: string[];
  email_enabled: boolean;
  frequency: "daily" | "instant";
};

export type SourceHealth = {
  id: number;
  code: string;
  name: string;
  jurisdiction: "central" | "state";
  url: string;
  crawler_type: "digest" | "agent" | "static";
  allowed_domains: string[];
  enabled: boolean;
  last_checked_at: string | null;
  last_status: number | null;
  consecutive_failures: number;
};

export type CrawlRun = {
  id: number;
  started_at: string;
  finished_at: string | null;
  status: "running" | "success" | "partial" | "failed";
  sources_attempted: number;
  sources_succeeded: number;
  docs_found: number;
  new_events: number;
  errors: Array<Record<string, unknown>>;
};

export type SystemDocument = {
  slug: string;
  title: string;
  category: string;
  content_md?: string;
};

export type HealthResponse = {
  status: "ok" | "degraded";
  database_configured: boolean;
  database_connected: boolean;
  storage_configured: boolean;
  llm_provider: string;
  effective_llm_provider: string;
};

type ImportMetaWithEnv = ImportMeta & {
  env?: Record<string, string | undefined>;
};

const env = (import.meta as ImportMetaWithEnv).env ?? {};
const API_BASE_URL =
  env.NEXT_PUBLIC_API_BASE_URL ?? env.VITE_API_BASE_URL ?? "http://localhost:8001";

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
    throw new Error(detail || `API request failed: ${response.status}`);
  }
  return response.json() as Promise<T>;
}

export function getLatestDigest(token?: string) {
  return apiFetch<DigestResponse>("/digests/latest", token);
}

export function getHealth() {
  return apiFetch<HealthResponse>("/health");
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
  return apiFetch<DigestEvent[]>(`/events${suffix}`, token);
}

export function getEvent(eventId: number, token?: string) {
  return apiFetch<DigestEvent>(`/events/${eventId}`, token);
}

export function sendChat(message: string, eventId: number | null, token?: string) {
  return apiFetch<{ reply: string; model: string; event_id: number | null }>("/chat", token, {
    method: "POST",
    body: JSON.stringify({ message, event_id: eventId }),
  });
}

export function markRead(eventId: number, token?: string) {
  return apiFetch<{ event_id: number; is_read: boolean }>(`/events/${eventId}/read`, token, {
    method: "POST",
  });
}

export function toggleBookmark(eventId: number, token?: string) {
  return apiFetch<{ event_id: number; is_bookmarked: boolean }>(
    `/events/${eventId}/bookmark`,
    token,
    { method: "POST" },
  );
}

export function getSubscriptions(token?: string) {
  return apiFetch<SubscriptionSettings>("/subscriptions", token);
}

export function saveSubscriptions(payload: SubscriptionSettings, token?: string) {
  return apiFetch<SubscriptionSettings>("/subscriptions", token, {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}

export function getSources(token?: string) {
  return apiFetch<SourceHealth[]>("/admin/sources", token);
}

export function toggleSource(sourceId: number, token?: string) {
  return apiFetch<{ source_id: number; enabled: boolean }>(`/admin/sources/${sourceId}/toggle`, token, {
    method: "POST",
  });
}

export function getRuns(token?: string) {
  return apiFetch<CrawlRun[]>("/admin/runs", token);
}

export function getDocs(token?: string) {
  return apiFetch<SystemDocument[]>("/meta/docs", token);
}

export function getDoc(slug: string, token?: string) {
  return apiFetch<SystemDocument>(`/meta/docs/${slug}`, token);
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
  if (!response.ok) throw new Error(`Export failed: ${response.status}`);
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
