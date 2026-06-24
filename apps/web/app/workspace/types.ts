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
  | "admin-checkpoints"
  | "admin-analytics"
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
};

export type PipelineStatus = "online" | "degraded" | "offline";

export type IntelligenceTab = "deadlines" | "obligations" | "stakeholders" | "readiness";

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
