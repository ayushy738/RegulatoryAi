import type { LucideIcon } from "lucide-react";

import type { SubscriptionSettings } from "@/lib/api";

export type RouteKey =
  | "landing"
  | "dashboard"
  | "latest"
  | "today"
  | "browse"
  | "intelligence"
  | "deadlines"
  | "ask"
  | "documents"
  | "saved"
  | "event"
  | "notifications"
  | "account"
  | "admin-dashboard"
  | "admin-sources"
  | "admin-pages"
  | "admin-runs"
  | "admin-events"
  | "admin-documents"
  | "admin-families"
  | "admin-versions"
  | "admin-graph"
  | "admin-rag"
  | "admin-queues"
  | "admin-checkpoints"
  | "admin-analytics"
  | "admin-users"
  | "admin-subscriptions"
  | "api-docs"
  | "flow";

export type NormalizedRoute = Exclude<RouteKey, "today" | "browse">;

export type NavItem = {
  href: string;
  label: string;
  route: NormalizedRoute;
  Icon: LucideIcon;
};

export type ChatMessage = {
  role: "user" | "assistant";
  content: string;
  created_at?: string | null;
  intent?: string | null;
  citations?: Array<{
    document_id: number;
    title: string;
    issuer?: string | null;
    issue_date?: string | null;
    source_url: string;
    chunk_id?: number | null;
    page_number?: number | null;
    section_title?: string | null;
    evidence?: string | null;
  }>;
  related_questions?: string[];
  model?: string | null;
};

export type PipelineStatus = "online" | "degraded" | "offline";

export type IntelligenceTab = "deadlines" | "obligations" | "stakeholders" | "readiness" | "timeline";

export type EvidenceItem = {
  title: string;
  issuer?: string | null;
  date?: string | null;
  summary?: string | null;
  evidence?: string | null;
  sourceUrl?: string | null;
  family?: string | null;
  version?: string | number | null;
  documentId?: number | null;
  chunkId?: number | null;
  pageNumber?: number | null;
  relationships?: string[];
};

export const defaultSettings: SubscriptionSettings = {
  jurisdictions: ["central"],
  source_ids: [],
  topics: ["solar", "tariff", "open access", "RPO/REC", "storage", "transmission"],
  email_enabled: true,
  frequency: "daily",
};

export function normalizeRoute(route: RouteKey): NormalizedRoute {
  if (route === "today") return "dashboard";
  if (route === "browse") return "latest";
  return route;
}
