"use client";

import type { ReactNode } from "react";
import {
  AlertTriangle,
  Ban,
  CheckCircle2,
  CircleDashed,
  Clock,
  HelpCircle,
  Loader2,
  MinusCircle,
  ShieldCheck,
  XCircle,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";

export type BadgeTone = "neutral" | "success" | "warning" | "danger" | "info" | "brand";

export function Badge({
  tone = "neutral",
  Icon,
  mono = false,
  children,
}: {
  tone?: BadgeTone;
  Icon?: LucideIcon;
  mono?: boolean;
  children: ReactNode;
}) {
  return (
    <span
      className={`rv-badge rv-badge--${tone}${mono ? " rv-badge--code" : ""}`}
    >
      {Icon ? <Icon size={12} aria-hidden /> : null}
      {children}
    </span>
  );
}

/** Operational health of a monitored source. */
export type SourceHealthStatus =
  | "healthy"
  | "running"
  | "never_crawled"
  | "degraded"
  | "failed"
  | "disabled";

/** Lifecycle status of a crawl run or a single page result. */
export type RunStatus =
  | "queued"
  | "running"
  | "success"
  | "partial"
  | "failed"
  | "no_documents"
  | "unknown";

type Descriptor = { label: string; tone: BadgeTone; Icon: LucideIcon };

const SOURCE_HEALTH: Record<SourceHealthStatus, Descriptor> = {
  healthy: { label: "Healthy", tone: "success", Icon: ShieldCheck },
  running: { label: "Running", tone: "info", Icon: Loader2 },
  never_crawled: { label: "Never crawled", tone: "neutral", Icon: CircleDashed },
  degraded: { label: "Partial", tone: "warning", Icon: AlertTriangle },
  failed: { label: "Failed", tone: "danger", Icon: XCircle },
  disabled: { label: "Disabled", tone: "neutral", Icon: Ban },
};

const RUN_STATUS: Record<RunStatus, Descriptor> = {
  queued: { label: "Queued", tone: "neutral", Icon: Clock },
  running: { label: "Running", tone: "info", Icon: Loader2 },
  success: { label: "Success", tone: "success", Icon: CheckCircle2 },
  partial: { label: "Partial", tone: "warning", Icon: AlertTriangle },
  failed: { label: "Failed", tone: "danger", Icon: XCircle },
  no_documents: { label: "No documents", tone: "neutral", Icon: MinusCircle },
  unknown: { label: "Unknown", tone: "neutral", Icon: HelpCircle },
};

/**
 * Status is always icon + text, never colour alone, so it survives greyscale,
 * colour-blindness and screen readers.
 */
export function StatusBadge({
  status,
  kind,
}: {
  status: string;
  kind: "source" | "run";
}) {
  const table = kind === "source" ? SOURCE_HEALTH : RUN_STATUS;
  const descriptor =
    (table as Record<string, Descriptor>)[status] ?? RUN_STATUS.unknown;
  const spins = descriptor.Icon === Loader2;

  return (
    <span
      className={`rv-badge rv-badge--${descriptor.tone}${spins ? " rv-badge--running" : ""}`}
    >
      <descriptor.Icon size={12} aria-hidden />
      {descriptor.label}
    </span>
  );
}

export function RoleBadge({ role }: { role: string }) {
  return role === "admin" ? (
    <Badge tone="brand" Icon={ShieldCheck}>
      Admin
    </Badge>
  ) : (
    <Badge tone="neutral">User</Badge>
  );
}

/**
 * Derive a source's operational health from the fields the registry already
 * stores. `last_status` is the HTTP status of the last check, so it is only
 * consulted after the failure counters, which describe sustained trouble
 * rather than one bad response. Disabled wins over everything: an operator who
 * turned a source off should not see crawl failures as the headline problem.
 */
export function sourceHealth(source: {
  enabled: boolean;
  last_status?: number | null;
  last_checked_at?: string | null;
  consecutive_failures?: number | null;
}): SourceHealthStatus {
  if (!source.enabled) return "disabled";

  const failures = source.consecutive_failures ?? 0;
  if (failures >= 3) return "failed";
  if (failures > 0) return "degraded";
  if (!source.last_checked_at) return "never_crawled";

  const status = source.last_status;
  if (typeof status === "number" && status >= 400) return "failed";
  return "healthy";
}

/** "HTTP 200" / "No response recorded" for the last check of a source. */
export function lastStatusLabel(status?: number | null) {
  return typeof status === "number" ? `HTTP ${status}` : "No response recorded";
}

export function normalizeRunStatus(status: string | null | undefined): RunStatus {
  const value = (status ?? "").toLowerCase();
  if (value in RUN_STATUS) return value as RunStatus;
  return "unknown";
}
