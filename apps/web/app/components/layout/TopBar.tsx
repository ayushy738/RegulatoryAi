"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";
import {
  Bell,
  Check,
  ExternalLink,
  LogOut,
  Menu,
  Search,
  Settings2,
  UserCircle,
  X,
} from "lucide-react";

import { adminNav, userNav } from "@/app/workspace/nav";
import { clampText, eventSummary, formatDate } from "@/app/workspace/format";
import { useWorkspace } from "@/app/workspace/WorkspaceContext";

type NotificationFilter =
  | "unread"
  | "read"
  | "mentioned"
  | "deadline"
  | "consultation"
  | "amendment"
  | "tender"
  | "saved";

type NotificationItem = {
  id: string;
  title: string;
  body: string;
  href?: string;
  source?: string | null;
  date?: string | null;
  category: NotificationFilter;
  priority: "normal" | "high";
  isRead: boolean;
};

const notificationFilters: Array<{ value: NotificationFilter; label: string }> = [
  { value: "unread", label: "Unread" },
  { value: "read", label: "Read" },
  { value: "mentioned", label: "Mentioned" },
  { value: "deadline", label: "Deadline alerts" },
  { value: "consultation", label: "Consultations" },
  { value: "amendment", label: "Amendments" },
  { value: "tender", label: "Tenders" },
  { value: "saved", label: "Saved topics" },
];

function statusLabel(status: string) {
  if (status === "online") return "Online";
  if (status === "degraded") return "Degraded";
  return "Offline";
}

function userNameFromEmail(email: string) {
  if (!email) return "Regulatory Analyst";
  const [name] = email.split("@");
  return name
    .split(/[._-]/)
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ") || "Regulatory Analyst";
}

function classifyEvent(title: string, tags: string[], summary: string): NotificationFilter {
  const text = `${title} ${tags.join(" ")} ${summary}`.toLowerCase();
  if (text.includes("tender") || text.includes("bid") || text.includes("auction")) return "tender";
  if (text.includes("amendment") || text.includes("changed") || text.includes("revision")) return "amendment";
  if (text.includes("consultation") || text.includes("comment") || text.includes("draft")) return "consultation";
  return "saved";
}

export function TopBar() {
  const {
    route,
    query,
    setQuery,
    pipelineStatus,
    events,
    activeDeadlines,
    settings,
    setSettings,
    handleSaveSettings,
    busyAction,
    userEmail,
    handleSignOut,
  } = useWorkspace();
  const router = useRouter();
  const [navOpen, setNavOpen] = useState(false);
  const [notificationsOpen, setNotificationsOpen] = useState(false);
  const [profileOpen, setProfileOpen] = useState(false);
  const [filter, setFilter] = useState<NotificationFilter>("unread");
  const [readIds, setReadIds] = useState<Set<string>>(new Set());
  const [clearedReadIds, setClearedReadIds] = useState<Set<string>>(new Set());
  const [priorityAlerts, setPriorityAlerts] = useState(true);

  const userName = userNameFromEmail(userEmail);
  const notifications = useMemo<NotificationItem[]>(() => {
    const topicText = settings.topics.join(" ").toLowerCase();
    const eventItems = events.slice(0, 24).map((event) => {
      const summary = eventSummary(event);
      const category = classifyEvent(event.title, event.topic_tags, summary);
      const isMentioned =
        topicText.length > 0 &&
        event.topic_tags.some((tag) => topicText.includes(tag.toLowerCase()));
      return {
        id: `event-${event.id}`,
        title: event.title,
        body: clampText(summary, 150),
        href: `/events/${event.id}`,
        source: event.issuing_body,
        date: event.issue_date ?? event.detected_at,
        category: isMentioned ? "mentioned" : category,
        priority: event.event_type === "CHANGED" || category === "deadline" ? "high" : "normal",
        isRead: event.is_read || readIds.has(`event-${event.id}`),
      } satisfies NotificationItem;
    });
    const deadlineItems = activeDeadlines.slice(0, 12).map((deadline) => {
      const id = `deadline-${deadline.document_id}-${deadline.deadline_type}-${deadline.deadline_date ?? deadline.raw_date ?? "unknown"}`;
      const priority: NotificationItem["priority"] =
        deadline.days_remaining !== null && deadline.days_remaining <= 7 ? "high" : "normal";
      return {
        id,
        title: deadline.title,
        body: `${deadline.deadline_type.replace(/_/g, " ")} due ${formatDate(deadline.deadline_date ?? deadline.raw_date)}`,
        href: deadline.source_url,
        source: deadline.issuer,
        date: deadline.deadline_date ?? deadline.raw_date,
        category: "deadline",
        priority,
        isRead: readIds.has(id),
      } satisfies NotificationItem;
    });
    return [...deadlineItems, ...eventItems].filter((item) => !clearedReadIds.has(item.id));
  }, [activeDeadlines, clearedReadIds, events, readIds, settings.topics]);

  const unreadCount = notifications.filter((item) => !item.isRead).length;
  const filteredNotifications = notifications.filter((item) => {
    if (filter === "unread") return !item.isRead;
    if (filter === "read") return item.isRead;
    return item.category === filter;
  });

  function submitSearch(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const suffix = query.trim() ? `?q=${encodeURIComponent(query.trim())}` : "";
    router.push(`/latest${suffix}`);
    setNavOpen(false);
  }

  function markAllRead() {
    setReadIds(new Set(notifications.map((item) => item.id)));
  }

  function clearRead() {
    setClearedReadIds(new Set(notifications.filter((item) => item.isRead).map((item) => item.id)));
  }

  function toggleTopic(topic: string) {
    const current = new Set(settings.topics);
    if (current.has(topic)) current.delete(topic);
    else current.add(topic);
    setSettings({ ...settings, topics: Array.from(current) });
  }

  return (
    <>
      <header className="product-topnav">
        <div className="product-topnav-left">
          <button
            className="topnav-menu-button"
            type="button"
            aria-label="Open navigation"
            onClick={() => setNavOpen((open) => !open)}
          >
            {navOpen ? <X size={18} /> : <Menu size={18} />}
          </button>
          <Link className="product-brand" href="/latest" aria-label="Resolven latest updates">
            <img src="/logo_mark.png" alt="" />
            <span className="product-brand-text">
              <strong>Resolven</strong>
              <small>RegulatoryAi</small>
            </span>
          </Link>
        </div>

        <nav className={`product-nav-center ${navOpen ? "open" : ""}`} aria-label="Primary navigation">
          {userNav.map((item) => (
            <Link
              key={item.href}
              className={route === item.route ? "active" : ""}
              href={item.href}
              onClick={() => setNavOpen(false)}
            >
              {item.label}
            </Link>
          ))}
        </nav>

        <div className="product-topnav-right">
          <form className="global-search" role="search" onSubmit={submitSearch}>
            <Search size={16} />
            <input
              aria-label="Global search"
              placeholder="Search"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
            />
            <kbd>/</kbd>
          </form>
          <button
            className="topnav-icon-button"
            type="button"
            aria-label={`${unreadCount} unread notifications`}
            onClick={() => setNotificationsOpen(true)}
          >
            <Bell size={18} />
            {unreadCount ? <span>{unreadCount > 9 ? "9+" : unreadCount}</span> : null}
          </button>
          <div className="profile-menu-shell">
            <button className="profile-trigger" type="button" onClick={() => setProfileOpen((open) => !open)}>
              <UserCircle size={19} />
            </button>
            {profileOpen ? (
              <div className="profile-menu">
                <strong>{userName}</strong>
                <span>{userEmail || "Signed in"}</span>
                <button type="button" onClick={handleSignOut}>
                  <LogOut size={16} />
                  Sign Out
                </button>
              </div>
            ) : null}
          </div>
        </div>
      </header>

      {notificationsOpen ? (
        <div className="notification-backdrop" onClick={() => setNotificationsOpen(false)}>
          <aside className="notification-drawer" aria-label="Notifications" onClick={(event) => event.stopPropagation()}>
            <div className="notification-drawer-header">
              <div>
                <p>Notifications</p>
                <h2>Regulatory alerts</h2>
              </div>
              <button type="button" aria-label="Close notifications" onClick={() => setNotificationsOpen(false)}>
                <X size={18} />
              </button>
            </div>

            <div className="notification-actions">
              <button type="button" onClick={markAllRead}>
                <Check size={15} />
                Mark all read
              </button>
              <button type="button" onClick={clearRead}>Clear read</button>
            </div>

            <div className="notification-filter-row" role="tablist" aria-label="Notification filters">
              {notificationFilters.map((item) => (
                <button
                  key={item.value}
                  type="button"
                  className={filter === item.value ? "active" : ""}
                  onClick={() => setFilter(item.value)}
                >
                  {item.label}
                </button>
              ))}
            </div>

            <div className="notification-list">
              {filteredNotifications.length ? (
                filteredNotifications.map((item) => (
                  <a
                    key={item.id}
                    className={`notification-item ${item.isRead ? "read" : "unread"} ${item.priority}`}
                    href={item.href ?? "#"}
                    target={item.href?.startsWith("http") ? "_blank" : undefined}
                    rel={item.href?.startsWith("http") ? "noreferrer" : undefined}
                    onClick={() => setReadIds((current) => new Set([...current, item.id]))}
                  >
                    <span className="notification-dot" />
                    <div>
                      <strong>{item.title}</strong>
                      <p>{item.body}</p>
                      <small>
                        {item.source ?? "Resolven"} {item.date ? `- ${formatDate(item.date)}` : ""}
                      </small>
                    </div>
                    {item.href?.startsWith("http") ? <ExternalLink size={15} /> : null}
                  </a>
                ))
              ) : (
                <div className="notification-empty">
                  <strong>No alerts in this view</strong>
                  <p>New consultations, amendments, tenders, deadline alerts, and saved topic alerts appear here.</p>
                </div>
              )}
            </div>

            <div className="notification-preferences">
              <div className="notification-preferences-title">
                <Settings2 size={16} />
                Preferences
              </div>
              <label>
                <input
                  type="checkbox"
                  checked={settings.email_enabled}
                  onChange={(event) => setSettings({ ...settings, email_enabled: event.target.checked })}
                />
                Email alerts
              </label>
              <label>
                <input type="checkbox" checked readOnly />
                In-app alerts
              </label>
              <label>
                <input type="checkbox" checked={priorityAlerts} onChange={(event) => setPriorityAlerts(event.target.checked)} />
                Priority alerts
              </label>
              <div className="frequency-control">
                <span>Frequency</span>
                <button
                  type="button"
                  className={settings.frequency === "daily" ? "active" : ""}
                  onClick={() => setSettings({ ...settings, frequency: "daily" })}
                >
                  Daily
                </button>
                <button
                  type="button"
                  className={settings.frequency === "instant" ? "active" : ""}
                  onClick={() => setSettings({ ...settings, frequency: "instant" })}
                >
                  Instant
                </button>
              </div>
              <div className="topic-subscriptions">
                {["solar", "tariff", "open access", "RPO/REC", "storage", "transmission"].map((topic) => (
                  <button
                    key={topic}
                    type="button"
                    className={settings.topics.includes(topic) ? "active" : ""}
                    onClick={() => toggleTopic(topic)}
                  >
                    {topic}
                  </button>
                ))}
              </div>
              <button className="primary-button full" type="button" onClick={handleSaveSettings} disabled={busyAction === "settings"}>
                {busyAction === "settings" ? "Saving..." : "Save preferences"}
              </button>
            </div>
          </aside>
        </div>
      ) : null}
    </>
  );
}

export function AdminTopBar() {
  const { route, pipelineStatus, userEmail, handleSignOut } = useWorkspace();
  const [profileOpen, setProfileOpen] = useState(false);
  const status = statusLabel(pipelineStatus);
  return (
    <header className="admin-topnav">
      <div className="admin-topnav-left">
        <Link className="product-brand" href="/admin">
          <img src="/logo_mark.png" alt="" />
          <span className="product-brand-text">
            <strong>Resolven</strong>
            <small>Admin</small>
          </span>
        </Link>
        <span className={`status-pill ${pipelineStatus}`}>
          <span />
          {status}
        </span>
      </div>
      <nav className="admin-nav-center" aria-label="Admin navigation">
        {adminNav.map((item) => (
          <Link key={item.href} className={route === item.route ? "active" : ""} href={item.href}>
            {item.label}
          </Link>
        ))}
      </nav>
      <div className="admin-topnav-right">
        <Link className="secondary-button compact" href="/latest">
          Return to Main Product
        </Link>
        <div className="profile-menu-shell">
          <button className="profile-trigger" type="button" onClick={() => setProfileOpen((open) => !open)}>
            <UserCircle size={19} />
          </button>
          {profileOpen ? (
            <div className="profile-menu">
              <strong>{userNameFromEmail(userEmail)}</strong>
              <span>{userEmail || "Signed in"}</span>
              <button type="button" onClick={handleSignOut}>
                <LogOut size={16} />
                Sign Out
              </button>
            </div>
          ) : null}
        </div>
      </div>
    </header>
  );
}
