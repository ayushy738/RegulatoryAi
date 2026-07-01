import {
  Database,
  FileSearch,
  Gauge,
  History,
  LayoutDashboard,
  MessageSquareText,
  Network,
  Star,
  Users,
} from "lucide-react";

import type { NavItem, NormalizedRoute } from "./types";

export const userNav: NavItem[] = [
  { href: "/latest", label: "Latest", route: "latest", Icon: FileSearch },
  { href: "/dashboard", label: "Dashboard", route: "dashboard", Icon: LayoutDashboard },
  { href: "/intelligence", label: "Intelligence", route: "intelligence", Icon: Network },
  { href: "/ask", label: "Ask AI", route: "ask", Icon: MessageSquareText },
  { href: "/saved", label: "Saved", route: "saved", Icon: Star },
];

export const adminNav: NavItem[] = [
  { href: "/admin", label: "Dashboard", route: "admin-dashboard", Icon: Gauge },
  { href: "/admin/sources", label: "Sources", route: "admin-sources", Icon: Database },
  { href: "/admin/runs", label: "Crawl Runs", route: "admin-runs", Icon: History },
  { href: "/admin/users", label: "Users", route: "admin-users", Icon: Users },
];

export const routeTitles: Record<NormalizedRoute, string> = {
  landing: "Resolven Regulatory AI",
  dashboard: "Regulatory Intelligence Dashboard",
  latest: "Latest Regulatory Updates",
  intelligence: "Intelligence Center",
  deadlines: "Deadlines Center",
  ask: "Ask AI",
  documents: "Documents",
  saved: "Saved Intelligence",
  event: "Regulatory Event",
  notifications: "Notifications",
  account: "Account",
  "admin-dashboard": "Admin Dashboard",
  "admin-sources": "Sources",
  "admin-pages": "Source Pages",
  "admin-runs": "Crawl Runs",
  "admin-events": "Events",
  "admin-documents": "Documents",
  "admin-families": "Document Families",
  "admin-versions": "Document Versions",
  "admin-graph": "Knowledge Graph",
  "admin-rag": "Hybrid RAG",
  "admin-queues": "Queues",
  "admin-checkpoints": "Checkpoints",
  "admin-analytics": "Analytics",
  "admin-users": "Users",
  "admin-subscriptions": "Subscriptions",
  "api-docs": "API Documentation",
  flow: "Data Flow",
};

export const sourceOptions = ["all", "MNRE", "CERC", "SECI", "MoP", "MERC"];

export const stakeholderOptions = [
  "all",
  "Solar Developers",
  "Wind Developers",
  "DISCOMs",
  "Transmission Licensees",
  "Power Exchanges",
  "Generators",
];

export const eventTypeOptions = ["all", "NEW", "CHANGED", "REPLACEMENT", "DUPLICATE"];

export const deadlineTypes = [
  "all",
  "CONSULTATION_DEADLINE",
  "TENDER_SUBMISSION_DEADLINE",
  "HEARING_DATE",
  "COMPLIANCE_DEADLINE",
  "IMPLEMENTATION_DATE",
  "PUBLICATION_DATE",
  "UNKNOWN_DATE",
];

export const suggestedPrompts = [
  "What changed this week?",
  "Which regulations affect solar developers?",
  "What consultations close this month?",
  "What deadlines should I care about?",
];
