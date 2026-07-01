import Link from "next/link";
import { ArrowRight, BadgeCheck, Bookmark, Clock3, ExternalLink, Loader2 } from "lucide-react";

import type { DigestEvent } from "@/lib/api";
import {
  deadlineLabel,
  eventStakeholders,
  eventSummary,
  formatDate,
} from "@/app/workspace/format";

export function EventCard({
  event,
  compact = false,
  onBookmark,
  busy,
}: {
  event: DigestEvent;
  compact?: boolean;
  onBookmark: () => void;
  busy: boolean;
}) {
  const sourceCode =
    event.issuing_body?.split(/\s+/)[0]?.replace(/[^A-Za-z]/g, "") ||
    new URL(event.source_url, "https://example.com").hostname.split(".")[0].toUpperCase();
  return (
    <article className={`event-card ${compact ? "compact" : ""}`}>
      <div className="event-source">
        <span>{sourceCode.slice(0, 5)}</span>
        <div>
          <strong>{event.issuing_body ?? "Government source"}</strong>
          <p>{formatDate(event.issue_date)}</p>
        </div>
      </div>
      <div className="event-body">
        <div className="row-wrap">
          <span className="mini-badge green">{event.event_type}</span>
          {event.summary?.confidence ? (
            <span className={`confidence-chip ${event.summary.confidence}`}>
              <BadgeCheck size={14} /> {event.summary.confidence} confidence
            </span>
          ) : null}
          {event.topic_tags.slice(0, 4).map((tag) => (
            <span className="tag" key={tag}>
              {tag}
            </span>
          ))}
        </div>
        <h3>{event.title}</h3>
        <p>{eventSummary(event)}</p>
        <div className="row-wrap">
          {deadlineLabel(event) ? (
            <span className="deadline-chip">
              <Clock3 size={15} /> {deadlineLabel(event)}
            </span>
          ) : null}
          {eventStakeholders(event)
            .slice(0, 4)
            .map((stakeholder) => (
              <span className="tag purple" key={stakeholder}>
                {stakeholder}
              </span>
            ))}
        </div>
      </div>
      <div className="event-actions">
        <button type="button" onClick={onBookmark} disabled={busy} title="Save event">
          {busy ? <Loader2 className="spin" size={17} /> : <Bookmark size={17} />}
        </button>
        <a href={event.source_url} target="_blank" rel="noreferrer" title="Open source">
          <ExternalLink size={17} />
        </a>
        <Link href={`/events/${event.id}`} title="Open event">
          <ArrowRight size={17} />
        </Link>
      </div>
    </article>
  );
}
