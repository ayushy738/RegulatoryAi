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

export type SourcePage = {
  id: number;
  source_id: number;
  source_code: string;
  source_name: string;
  name: string;
  url: string;
  page_type: string;
  priority: number;
  enabled: boolean;
  last_crawled_at: string | null;
  created_at: string | null;
  updated_at: string | null;
};

export type SourcePageCheckpoint = {
  source_page_id: number;
  source_code: string;
  source_name: string;
  source_page: string;
  source_page_url: string;
  checkpoint_title: string | null;
  checkpoint_url: string | null;
  checkpoint_source_record_id: string | null;
  checkpoint_issue_date: string | null;
  checkpoint_published_at: string | null;
  lookback_count: number | null;
  last_successful_run_id: number | null;
  last_successful_at: string | null;
  updated_at: string | null;
};

export type AdminDocument = {
  id: number;
  title: string;
  source_url: string;
  issuing_body: string | null;
  jurisdiction: "central" | "state" | null;
  issue_date: string | null;
  issue_date_precision: string | null;
  doc_type: string | null;
  first_seen_at: string | null;
  last_seen_at: string | null;
  source_code: string | null;
  source_name: string | null;
  latest_version_id: number | null;
  file_hash: string | null;
  content_hash: string | null;
  fetched_at: string | null;
  family_id: string | null;
  family_title: string | null;
};

export type AdminEvent = {
  id: number;
  event_type: string;
  detected_at: string;
  suppressed: boolean;
  raw_summary: string | null;
  topic_tags: string[];
  document_id: number;
  title: string;
  source_url: string;
  issuing_body: string | null;
  issue_date: string | null;
  source_code: string | null;
  quality_score: number | null;
  quality_category: string | null;
  significance_score: number | null;
  significance_category: string | null;
  actionability: string | null;
  rejection_reason: string | null;
};

export type AdminFamily = {
  family_id: string;
  canonical_title: string;
  issuer: string | null;
  document_type: string | null;
  first_seen_at: string | null;
  latest_version_id: string | null;
  created_at: string | null;
  updated_at: string | null;
  document_count: number;
  version_count: number;
  deadline_count: number;
};

export type AdminAnalytics = {
  sources?: number;
  pages?: number;
  events?: number;
  documents?: number;
  families?: number;
  checkpoints?: number;
  candidates?: number;
  accepted_candidates?: number;
  rejected_candidates?: number;
  acceptance_rate?: number;
  runtime_reduction?: number | null;
  download_reduction?: number | null;
  latest_runs?: CrawlRun[];
  rejected_reasons?: Array<{ reason_code: string | null; count: number }>;
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

export type CrawlTriggerResponse = {
  status: string;
  sources_attempted: number;
  pages_attempted: number;
  sources_succeeded: number;
  pages_succeeded: number;
  docs_found: number;
  primary_docs_found: number;
  new_events: number;
  checkpoints_advanced: number;
  notification_message_id: string | null;
  errors: Array<Record<string, unknown>>;
};

export type ChatHistoryItem = {
  id: number;
  role: "user" | "assistant";
  content: string;
  event_id: number | null;
  created_at: string | null;
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

export type IntelligenceDeadline = {
  document_id: number;
  title: string;
  issuer: string | null;
  deadline_type: string;
  deadline_date: string | null;
  raw_date: string | null;
  days_remaining: number | null;
  stakeholders_affected: string[];
  source_url: string;
  confidence: number;
  evidence: string | null;
};

export type IntelligenceObligation = {
  document_id: number;
  title: string;
  issuer: string | null;
  obligation: string;
  stakeholder: string;
  deadline_date: string | null;
  deadline_type: string | null;
  confidence: number;
  evidence: string | null;
  source_url: string;
};

export type StakeholderObligationGroup = {
  stakeholder: string;
  obligations: IntelligenceObligation[];
};

export type IntelligenceDocumentRef = {
  document_id: number;
  title: string;
  issuer: string | null;
  source_url: string;
  document_type: string;
  confidence: number;
  evidence: string | null;
};

export type StakeholderIntelligence = {
  stakeholder: string;
  impact_summary: string;
  compliance_summary: string;
  action_summary: string;
  regulations: IntelligenceDocumentRef[];
  consultations: IntelligenceDocumentRef[];
  obligations: IntelligenceObligation[];
  deadlines: IntelligenceDeadline[];
  tenders: IntelligenceDocumentRef[];
  counts: Record<string, number>;
};

export type IntelligenceReadiness = {
  active_deadlines: IntelligenceDeadline[];
  stakeholder_obligations: StakeholderObligationGroup[];
  regulatory_impacts: StakeholderIntelligence[];
  consultation_tracking: IntelligenceDocumentRef[];
  status: string;
  notes: string[];
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
  return apiFetch<IntelligenceDeadline[]>(`/intelligence/deadlines${suffix}`, token);
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
  return apiFetch<StakeholderObligationGroup[]>(`/intelligence/obligations${suffix}`, token);
}

export function getStakeholderIntelligence(token?: string) {
  return apiFetch<StakeholderIntelligence[]>("/intelligence/stakeholders", token);
}

export function getIntelligenceReadiness(token?: string) {
  return apiFetch<IntelligenceReadiness>("/intelligence/readiness", token);
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

export function getChatHistory(token?: string, eventId?: number | null) {
  const suffix = eventId ? `?event_id=${eventId}` : "";
  return apiFetch<ChatHistoryItem[]>(`/chat/history${suffix}`, token);
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

export function updateSource(
  sourceId: number,
  payload: Partial<Pick<SourceHealth, "enabled" | "name" | "code" | "url" | "jurisdiction" | "crawler_type">>,
  token?: string,
) {
  return apiFetch<SourceHealth>(`/admin/sources/${sourceId}`, token, {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}

export function toggleSource(source: SourceHealth, token?: string) {
  return updateSource(source.id, { enabled: !source.enabled }, token);
}

export function getRuns(token?: string) {
  return apiFetch<CrawlRun[]>("/admin/runs", token);
}

export function getSourcePages(token?: string) {
  return apiFetch<SourcePage[]>("/admin/pages", token);
}

export function getSourcePageCheckpoints(token?: string) {
  return apiFetch<SourcePageCheckpoint[]>("/admin/checkpoints", token);
}

export function getAdminDocuments(token?: string, limit = 100) {
  return apiFetch<AdminDocument[]>(`/admin/documents?limit=${limit}`, token);
}

export function getAdminEvents(token?: string, limit = 100) {
  return apiFetch<AdminEvent[]>(`/admin/events?limit=${limit}`, token);
}

export function getAdminFamilies(token?: string, limit = 100) {
  return apiFetch<AdminFamily[]>(`/admin/families?limit=${limit}`, token);
}

export function getAdminAnalytics(token?: string) {
  return apiFetch<AdminAnalytics>("/admin/analytics", token);
}

export function crawlSource(sourceId: number, token?: string) {
  return apiFetch<CrawlTriggerResponse>(`/admin/sources/${sourceId}/crawl`, token, {
    method: "POST",
  });
}

export function crawlSourcePage(pageId: number, token?: string) {
  return apiFetch<CrawlTriggerResponse>(`/admin/pages/${pageId}/crawl`, token, {
    method: "POST",
  });
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
