import {
  BarChart3,
  Bell,
  CalendarClock,
  CheckCircle2,
  ClipboardCheck,
  Database,
  FileSearch,
  FileText,
  Gauge,
  History,
  LayoutDashboard,
  Layers3,
  MessageSquareText,
  Network,
  Star,
  UserCircle,
} from "lucide-react";

import type { NavItem, NormalizedRoute } from "./types";

export const userNav: NavItem[] = [
  { href: "/dashboard", label: "Dashboard", route: "dashboard", Icon: LayoutDashboard },
  { href: "/latest", label: "Latest Updates", route: "latest", Icon: FileSearch },
  { href: "/intelligence", label: "Intelligence", route: "intelligence", Icon: Network },
  { href: "/deadlines", label: "Deadlines", route: "deadlines", Icon: CalendarClock },
  { href: "/ask", label: "Ask AI", route: "ask", Icon: MessageSquareText },
  { href: "/saved", label: "Saved", route: "saved", Icon: Star },
  { href: "/notifications", label: "Notifications", route: "notifications", Icon: Bell },
  { href: "/account", label: "Account", route: "account", Icon: UserCircle },
];

export const adminNav: NavItem[] = [
  { href: "/admin", label: "Dashboard", route: "admin-dashboard", Icon: Gauge },
  { href: "/admin/sources", label: "Sources", route: "admin-sources", Icon: Database },
  { href: "/admin/pages", label: "Source Pages", route: "admin-pages", Icon: Layers3 },
  { href: "/admin/runs", label: "Crawl Runs", route: "admin-runs", Icon: History },
  { href: "/admin/events", label: "Events", route: "admin-events", Icon: ClipboardCheck },
  { href: "/admin/documents", label: "Documents", route: "admin-documents", Icon: FileText },
  { href: "/admin/families", label: "Families", route: "admin-families", Icon: Network },
  { href: "/admin/checkpoints", label: "Checkpoints", route: "admin-checkpoints", Icon: CheckCircle2 },
  { href: "/admin/analytics", label: "Analytics", route: "admin-analytics", Icon: BarChart3 },
];

export const routeTitles: Record<NormalizedRoute, string> = {
  landing: "Resolven Regulatory AI",
  dashboard: "Regulatory Intelligence Dashboard",
  latest: "Latest Regulatory Updates",
  intelligence: "Intelligence Center",
  deadlines: "Deadlines Center",
  ask: "Ask AI",
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
  "admin-checkpoints": "Checkpoints",
  "admin-analytics": "Analytics",
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
