import type { DigestEvent, IntelligenceDeadline } from "@/lib/api";
import { clampText, eventSummary, formatShortDate } from "@/app/workspace/format";

export type NotificationCategory =
  | "deadline"
  | "consultation"
  | "amendment"
  | "tender"
  | "update";

export type NotificationTab =
  | "all"
  | "unread"
  | "mentions"
  | "deadline"
  | "consultation"
  | "amendment"
  | "tender";

export type NotificationItem = {
  id: string;
  title: string;
  /** One line of context — what changed, not a summary of the whole document. */
  context: string;
  href: string;
  external: boolean;
  source: string;
  /** Single compact date, already formatted. */
  date: string | null;
  category: NotificationCategory;
  mentioned: boolean;
  urgent: boolean;
  isRead: boolean;
};

export const NOTIFICATION_TABS: Array<{ value: NotificationTab; label: string }> = [
  { value: "all", label: "All" },
  { value: "unread", label: "Unread" },
  { value: "mentions", label: "Mentions" },
  { value: "deadline", label: "Deadlines" },
  { value: "consultation", label: "Consultations" },
  { value: "amendment", label: "Amendments" },
  { value: "tender", label: "Tenders" },
];

function categorise(text: string): NotificationCategory {
  const haystack = text.toLowerCase();
  if (/tender|bid|auction|rfp|rfs/.test(haystack)) return "tender";
  if (/consultation|comment|draft|discussion paper/.test(haystack)) return "consultation";
  if (/amendment|amended|revision|revised/.test(haystack)) return "amendment";
  return "update";
}

function deadlineId(deadline: IntelligenceDeadline) {
  return [
    "deadline",
    deadline.document_id,
    deadline.deadline_type,
    deadline.deadline_date ?? deadline.raw_date ?? "unknown",
  ].join("-");
}

/**
 * Build the notification feed from data the product already has: regulatory
 * events and active deadlines.
 *
 * Deadlines lead because they expire; within each group the newest item wins.
 * Each item carries exactly one date, so the drawer never repeats a timestamp
 * the way the content cards used to.
 */
export function buildNotificationFeed({
  events,
  deadlines,
  topics,
  readIds,
  dismissedIds,
  limit = 40,
}: {
  events: DigestEvent[];
  deadlines: IntelligenceDeadline[];
  topics: string[];
  readIds: ReadonlySet<string>;
  dismissedIds: ReadonlySet<string>;
  limit?: number;
}): NotificationItem[] {
  const topicText = topics.join(" ").toLowerCase();

  const deadlineItems: NotificationItem[] = deadlines.slice(0, 15).map((deadline) => {
    const id = deadlineId(deadline);
    const days = deadline.days_remaining;
    return {
      id,
      title: deadline.title,
      context:
        days === null || days === undefined
          ? deadline.deadline_type.replace(/_/g, " ").toLowerCase()
          : days <= 0
            ? "Due today"
            : `${days} day${days === 1 ? "" : "s"} remaining`,
      href: deadline.source_url,
      external: true,
      source: deadline.issuer ?? "Regulator",
      date: formatShortDate(deadline.deadline_date ?? deadline.raw_date),
      category: "deadline",
      mentioned: false,
      urgent: typeof days === "number" && days <= 7,
      isRead: readIds.has(id),
    };
  });

  const eventItems: NotificationItem[] = events.slice(0, 30).map((event) => {
    const id = `event-${event.id}`;
    const summary = eventSummary(event);
    return {
      id,
      title: event.title,
      context: clampText(summary, 120),
      href: `/events/${event.id}`,
      external: false,
      source: event.issuing_body ?? "Resolven",
      date: formatShortDate(event.issue_date ?? event.detected_at),
      category: categorise(`${event.title} ${event.topic_tags.join(" ")} ${summary}`),
      mentioned:
        topicText.length > 0 &&
        event.topic_tags.some((tag) => topicText.includes(tag.toLowerCase())),
      urgent: event.event_type === "CHANGED",
      isRead: event.is_read || readIds.has(id),
    };
  });

  return [...deadlineItems, ...eventItems]
    .filter((item) => !dismissedIds.has(item.id))
    .slice(0, limit);
}

export function filterNotifications(
  items: NotificationItem[],
  tab: NotificationTab,
): NotificationItem[] {
  switch (tab) {
    case "all":
      return items;
    case "unread":
      return items.filter((item) => !item.isRead);
    case "mentions":
      return items.filter((item) => item.mentioned);
    default:
      return items.filter((item) => item.category === tab);
  }
}

export function unreadCount(items: NotificationItem[]) {
  return items.filter((item) => !item.isRead).length;
}
