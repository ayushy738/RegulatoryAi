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

/** Absolute date + time, for operational logs where the exact moment matters. */
export function formatDateTime(value?: string | null) {
  if (!value) return "Not available";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("en-IN", {
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

/**
 * Short compact date for content cards: "11 Aug" within the current year,
 * "11 Aug 2025" otherwise. Keeps feed metadata to one glanceable token.
 */
export function formatShortDate(value?: string | null) {
  if (!value) return null;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return null;
  const sameYear = date.getFullYear() === new Date().getFullYear();
  return new Intl.DateTimeFormat("en-IN", {
    day: "numeric",
    month: "short",
    ...(sameYear ? {} : { year: "numeric" }),
  }).format(date);
}

/** Elapsed wall-clock time between two timestamps, rendered as 22s / 4m 10s / 1h 6m. */
export function formatDuration(
  startedAt?: string | null,
  finishedAt?: string | null,
) {
  if (!startedAt) return "—";
  const start = new Date(startedAt).getTime();
  if (!Number.isFinite(start)) return "—";
  const end = finishedAt ? new Date(finishedAt).getTime() : Date.now();
  if (!Number.isFinite(end) || end < start) return "—";

  const seconds = Math.max(1, Math.round((end - start) / 1000));
  if (seconds < 60) return `${seconds}s`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) {
    const rest = seconds % 60;
    return rest ? `${minutes}m ${rest}s` : `${minutes}m`;
  }
  const hours = Math.floor(minutes / 60);
  const restMinutes = minutes % 60;
  return restMinutes ? `${hours}h ${restMinutes}m` : `${hours}h`;
}

/**
 * Pick the one or two dates worth showing on a content card.
 *
 * Content items carry up to three timestamps that frequently coincide. Showing
 * all of them is noise, so this returns a published date plus a deadline only
 * when the deadline is genuinely different information.
 */
export function contentDates(input: {
  issueDate?: string | null;
  detectedAt?: string | null;
  deadline?: string | null;
}): Array<{ label: string; value: string }> {
  const dates: Array<{ label: string; value: string }> = [];
  const published = formatShortDate(input.issueDate ?? input.detectedAt);
  if (published) {
    dates.push({
      label: input.issueDate ? "Published" : "Detected",
      value: published,
    });
  }

  const deadline = formatShortDate(input.deadline);
  if (deadline && deadline !== published) {
    dates.push({ label: "Deadline", value: deadline });
  }
  return dates;
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
