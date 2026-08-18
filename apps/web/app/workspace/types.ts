import type { LucideIcon } from "lucide-react";

import type { RagCitation, SubscriptionSettings } from "@/lib/api";

export type RouteKey =
  | "landing"
  | "dashboard"
  | "latest"
  | "today"
  | "browse"
  | "intelligence"
  | "deadlines"
  | "ask"
  | "saved"
  | "event"
  | "notifications"
  | "notification-preferences"
  | "admin-dashboard"
  | "admin-sources"
  | "admin-runs"
  | "admin-run"
  | "admin-users"
  | "api-docs"
  | "flow";

export type NormalizedRoute = Exclude<RouteKey, "today">;

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
  citations?: RagCitation[];
  related_questions?: string[];
  model?: string | null;
};

export type PipelineStatus = "online" | "degraded" | "offline";

/**
 * Obligations are deliberately absent: they remain a backend/graph concept but
 * are not a user-facing destination in the product.
 */
export type IntelligenceTab = "deadlines" | "stakeholders" | "readiness" | "timeline";

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
  jurisdictions: [],
  source_ids: [],
  topics: [],
  email_enabled: false,
  frequency: "instant",
};

export function normalizeRoute(
  route: RouteKey,
  v2BrowseEnabled = false,
): NormalizedRoute {
  if (route === "today") return "dashboard";
  if (route === "browse" && !v2BrowseEnabled) return "latest";
  return route;
}
