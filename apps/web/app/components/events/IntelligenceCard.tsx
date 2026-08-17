"use client";

import Link from "next/link";
import { ArrowRight, Bookmark, CalendarClock, ExternalLink, Search } from "lucide-react";

import { Badge } from "@/app/components/ui/Badge";
import { Button } from "@/app/components/ui/Button";
import type { DigestEvent } from "@/lib/api";
import {
  clampText,
  contentDates,
  deadlineLabel,
  eventStakeholders,
  eventSummary,
} from "@/app/workspace/format";

const EVENT_TONE: Record<string, "brand" | "warning" | "info" | "neutral"> = {
  NEW: "brand",
  CHANGED: "warning",
  REPLACEMENT: "info",
};

export function sourceCode(event: DigestEvent) {
  const issuer = event.issuing_body ?? "";
  const acronym = issuer
    .split(/\s+/)
    .map((part) => part.replace(/[^A-Za-z]/g, ""))
    .find((part) => part.length >= 2 && part === part.toUpperCase());
  if (acronym) return acronym;
  const first = issuer.split(/\s+/)[0]?.replace(/[^A-Za-z]/g, "");
  if (first) return first.slice(0, 5).toUpperCase();
  try {
    return new URL(event.source_url).hostname.replace(/^www\./, "").split(".")[0].toUpperCase();
  } catch {
    return "SOURCE";
  }
}

/**
 * One regulatory update, as an analyst reads it: who issued it, what it is,
 * what changed, who it affects, and what to do next.
 *
 * Dates are deliberately limited to a publication date plus a deadline when the
 * deadline is genuinely different — the previous card repeated the same day up
 * to four times under different labels.
 */
export function IntelligenceCard({
  event,
  onBookmark,
  onInspect,
  busy = false,
  compact = false,
}: {
  event: DigestEvent;
  onBookmark: () => void;
  onInspect?: () => void;
  busy?: boolean;
  compact?: boolean;
}) {
  const stakeholders = eventStakeholders(event);
  const dates = contentDates({
    issueDate: event.issue_date,
    detectedAt: event.detected_at,
    deadline: deadlineLabel(event),
  });

  return (
    <article className={`rv-intel-card${compact ? " rv-intel-card--compact" : ""}`}>
      <header className="rv-intel-card__head">
        <span className="rv-intel-card__source">
          <Badge mono>{sourceCode(event)}</Badge>
          <span className="rv-meta">{event.issuing_body ?? "Government source"}</span>
        </span>
        <Badge tone={EVENT_TONE[event.event_type] ?? "neutral"}>
          {event.event_type.replaceAll("_", " ").toLowerCase()}
        </Badge>
      </header>

      <h3 className="rv-intel-card__title">
        <Link href={`/events/${event.id}`}>{event.title}</Link>
      </h3>

      <p className="rv-intel-card__summary">
        {clampText(eventSummary(event), compact ? 180 : 320)}
      </p>

      {stakeholders.length || event.topic_tags.length ? (
        <div className="rv-intel-card__tags">
          {stakeholders.slice(0, 3).map((stakeholder) => (
            <Badge key={stakeholder} tone="brand">
              {stakeholder}
            </Badge>
          ))}
          {event.topic_tags.slice(0, compact ? 2 : 3).map((tag) => (
            <Badge key={tag}>{tag}</Badge>
          ))}
        </div>
      ) : null}

      <footer className="rv-intel-card__footer">
        <span className="rv-intel-card__dates">
          {dates.map((entry) => (
            <span className="rv-meta" key={entry.label}>
              {entry.label === "Deadline" ? (
                <CalendarClock size={13} aria-hidden />
              ) : null}
              {entry.label} {entry.value}
            </span>
          ))}
        </span>
        <span className="rv-intel-card__actions">
          {onInspect ? (
            <Button variant="ghost" size="sm" Icon={Search} onClick={onInspect}>
              Evidence
            </Button>
          ) : null}
          <Button
            variant="ghost"
            size="sm"
            Icon={Bookmark}
            loading={busy}
            aria-pressed={event.is_bookmarked}
            onClick={onBookmark}
          >
            {event.is_bookmarked ? "Saved" : "Save"}
          </Button>
          <a
            className="rv-btn rv-btn--ghost rv-btn--sm"
            href={event.source_url}
            target="_blank"
            rel="noreferrer"
          >
            <ExternalLink size={14} aria-hidden />
            <span>Source</span>
          </a>
          <Link className="rv-btn rv-btn--secondary rv-btn--sm" href={`/events/${event.id}`}>
            <span>Open</span>
            <ArrowRight size={14} aria-hidden />
          </Link>
        </span>
      </footer>
    </article>
  );
}
