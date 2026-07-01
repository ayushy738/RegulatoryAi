import type { DigestEvent } from "@/lib/api";

const OCR_ARTIFACT_RE = /\(cid:\d+\)|\uFFFD|ï¿½|�/gi;
const REPEATED_WHITESPACE_RE = /[ \t\r\n]+/g;

export function cleanText(value?: string | null, fallback = "Not available") {
  const clean = (value ?? "")
    .replace(OCR_ARTIFACT_RE, " ")
    .replace(REPEATED_WHITESPACE_RE, " ")
    .replace(/\s+([,.;:!?])/g, "$1")
    .trim();
  return clean || fallback;
}

export function clampText(value?: string | null, max = 220, fallback = "Not available") {
  const clean = cleanText(value, fallback);
  if (clean.length <= max) return clean;
  const clipped = clean.slice(0, max - 1).trimEnd();
  return `${clipped}${clipped.endsWith(".") ? "" : "..."}`;
}

export function formatDate(value?: string | null) {
  if (!value) return "Not specified";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("en-IN", {
    day: "2-digit",
    month: "short",
    year: "numeric",
  }).format(date);
}

export function formatRelativeDate(value?: string | null) {
  if (!value) return "No recent run";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("en-IN", {
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

export function compactNumber(value?: number | null) {
  return new Intl.NumberFormat("en-IN").format(value ?? 0);
}

export function deadlineLabel(event: DigestEvent) {
  const dates = event.summary?.important_dates ?? [];
  return dates[0] ?? null;
}

export function eventStakeholders(event: DigestEvent) {
  return event.summary?.affected_segments?.filter(Boolean) ?? [];
}

export function eventSummary(event: DigestEvent) {
  return cleanText(
    event.summary?.plain_english_summary ||
    event.raw_summary ||
      "Regulatory update detected from the source document. Review the source for full details.",
  );
}

export function isConsultation(event: DigestEvent) {
  const haystack = `${event.title} ${event.topic_tags.join(" ")} ${eventSummary(event)}`.toLowerCase();
  return haystack.includes("comment") || haystack.includes("consultation") || haystack.includes("draft");
}

export function isHighImpact(event: DigestEvent) {
  return (
    event.event_type === "CHANGED" ||
    event.summary?.action_required === "urgent" ||
    (event.summary?.confidence === "high" && eventStakeholders(event).length > 0)
  );
}

export function stripMarkdownNoise(line: string) {
  return cleanText(
    line
      .replace(/^#{1,6}\s*/, "")
      .replace(/^\*\s*/, "")
      .replace(/\*\*/g, "")
      .trim(),
    "",
  );
}
