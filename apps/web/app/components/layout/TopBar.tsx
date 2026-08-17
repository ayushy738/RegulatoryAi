"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";
import { Bell, LogOut, Menu, Search, Settings2, UserCircle, X } from "lucide-react";

import { IconButton } from "@/app/components/ui/Button";
import { buildNotificationFeed, unreadCount } from "@/app/features/notifications/notification-feed";
import { adminNav, userNav } from "@/app/workspace/nav";
import { useWorkspace } from "@/app/workspace/WorkspaceContext";

import { NotificationDrawer } from "./NotificationDrawer";

function userNameFromEmail(email: string) {
  if (!email) return "Regulatory Analyst";
  const [name] = email.split("@");
  return (
    name
      .split(/[._-]/)
      .filter(Boolean)
      .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
      .join(" ") || "Regulatory Analyst"
  );
}

/** Profile menu: closes on outside click and on Escape, like every other menu. */
function ProfileMenu() {
  const { userEmail, isAuthenticated, handleSignOut } = useWorkspace();
  const [open, setOpen] = useState(false);
  const shellRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!open) return undefined;
    const onPointerDown = (event: MouseEvent) => {
      if (!shellRef.current?.contains(event.target as Node)) setOpen(false);
    };
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("mousedown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open]);

  return (
    <div className="rv-profile" ref={shellRef}>
      <IconButton
        label="Account menu"
        Icon={UserCircle}
        aria-expanded={open}
        aria-haspopup="menu"
        onClick={() => setOpen((current) => !current)}
      />
      {open ? (
        <div className="rv-profile__panel" role="menu">
          <span className="rv-profile__name">{userNameFromEmail(userEmail)}</span>
          <span className="rv-profile__email">{userEmail || "Public reader"}</span>
          <Link
            className="rv-menu__item"
            role="menuitem"
            href="/notifications"
            onClick={() => setOpen(false)}
          >
            <Settings2 size={15} aria-hidden />
            Notification preferences
          </Link>
          {isAuthenticated ? (
            <button
              className="rv-menu__item"
              role="menuitem"
              type="button"
              onClick={handleSignOut}
            >
              <LogOut size={15} aria-hidden />
              Sign out
            </button>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

export function TopBar() {
  const {
    route,
    v2AskEnabled,
    query,
    setQuery,
    events,
    activeDeadlines,
    settings,
  } = useWorkspace();
  const router = useRouter();
  const [navOpen, setNavOpen] = useState(false);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [readIds, setReadIds] = useState<ReadonlySet<string>>(new Set());
  const [dismissedIds, setDismissedIds] = useState<ReadonlySet<string>>(new Set());

  const notifications = useMemo(
    () =>
      buildNotificationFeed({
        events,
        deadlines: activeDeadlines,
        topics: settings.topics,
        readIds,
        dismissedIds,
      }),
    [activeDeadlines, dismissedIds, events, readIds, settings.topics],
  );
  const unread = unreadCount(notifications);

  const links = useMemo(
    () =>
      v2AskEnabled
        ? [
            ...userNav,
            {
              href: "/browse",
              label: "Documents",
              route: "browse" as const,
              Icon: Search,
            },
          ]
        : userNav,
    [v2AskEnabled],
  );

  function submitSearch(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const suffix = query.trim() ? `?q=${encodeURIComponent(query.trim())}` : "";
    router.push(`/latest${suffix}`);
    setNavOpen(false);
  }

  return (
    <>
      <header className="rv-topbar">
        <IconButton
          className="rv-topbar__menu-button"
          label={navOpen ? "Close navigation" : "Open navigation"}
          Icon={navOpen ? X : Menu}
          aria-expanded={navOpen}
          onClick={() => setNavOpen((open) => !open)}
        />

        <Link className="rv-topbar__brand" href="/latest">
          <img src="/logo_mark.png" alt="" />
          <span>
            <strong>Resolven</strong>
            <small>Regulatory AI</small>
          </span>
        </Link>

        <nav
          className="rv-topbar__nav rv-topbar__nav--inline"
          aria-label="Primary navigation"
        >
          {links.map((item) => (
            <Link
              key={item.href}
              className="rv-topbar__link"
              href={item.href}
              aria-current={route === item.route ? "page" : undefined}
            >
              {item.label}
            </Link>
          ))}
        </nav>

        <div className="rv-topbar__actions">
          <form className="rv-topbar__search" role="search" onSubmit={submitSearch}>
            <Search size={15} aria-hidden />
            <input
              aria-label="Search regulatory updates"
              placeholder="Search updates"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
            />
          </form>
          <span className="rv-topbar__bell">
            <IconButton
              label={
                unread
                  ? `Notifications, ${unread} unread`
                  : "Notifications, none unread"
              }
              Icon={Bell}
              onClick={() => setDrawerOpen(true)}
            />
            {unread ? (
              <span className="rv-topbar__bell-count" aria-hidden>
                {unread > 9 ? "9+" : unread}
              </span>
            ) : null}
          </span>
          <ProfileMenu />
        </div>
      </header>

      {navOpen ? (
        <nav className="rv-mobile-nav" aria-label="Primary navigation">
          <form className="rv-search" role="search" onSubmit={submitSearch}>
            <Search size={15} aria-hidden />
            <input
              aria-label="Search regulatory updates"
              placeholder="Search updates"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
            />
          </form>
          {links.map((item) => (
            <Link
              key={item.href}
              className="rv-topbar__link"
              href={item.href}
              aria-current={route === item.route ? "page" : undefined}
              onClick={() => setNavOpen(false)}
            >
              <item.Icon size={16} aria-hidden />
              {item.label}
            </Link>
          ))}
          <div className="rv-mobile-nav__footer">
            <Link
              className="rv-topbar__link"
              href="/notifications"
              onClick={() => setNavOpen(false)}
            >
              <Settings2 size={16} aria-hidden />
              Notification preferences
            </Link>
          </div>
        </nav>
      ) : null}

      <NotificationDrawer
        open={drawerOpen}
        items={notifications}
        onClose={() => setDrawerOpen(false)}
        onRead={(id) => setReadIds((current) => new Set([...current, id]))}
        onMarkAllRead={() =>
          setReadIds(new Set(notifications.map((item) => item.id)))
        }
        onClearRead={() =>
          setDismissedIds(
            new Set(
              notifications.filter((item) => item.isRead).map((item) => item.id),
            ),
          )
        }
      />
    </>
  );
}

export function AdminTopBar() {
  const { route, pipelineStatus } = useWorkspace();
  const [navOpen, setNavOpen] = useState(false);

  const statusLabel =
    pipelineStatus === "online"
      ? "Pipeline online"
      : pipelineStatus === "degraded"
        ? "Pipeline degraded"
        : "Pipeline offline";

  return (
    <>
      <header className="rv-topbar rv-topbar--admin">
        <IconButton
          className="rv-topbar__menu-button"
          label={navOpen ? "Close navigation" : "Open navigation"}
          Icon={navOpen ? X : Menu}
          aria-expanded={navOpen}
          onClick={() => setNavOpen((open) => !open)}
        />

        <Link className="rv-topbar__brand" href="/admin">
          <img src="/logo_mark.png" alt="" />
          <span>
            <strong>Resolven</strong>
            <small>Operations</small>
          </span>
        </Link>

        <nav
          className="rv-topbar__nav rv-topbar__nav--inline"
          aria-label="Admin navigation"
        >
          {adminNav.map((item) => (
            <Link
              key={item.href}
              className="rv-topbar__link"
              href={item.href}
              aria-current={
                route === item.route ||
                (item.route === "admin-runs" && route === "admin-run")
                  ? "page"
                  : undefined
              }
            >
              {item.label}
            </Link>
          ))}
        </nav>

        <div className="rv-topbar__actions">
          <span className={`status-pill ${pipelineStatus}`} title={statusLabel}>
            <span aria-hidden />
            {statusLabel}
          </span>
          <Link className="rv-btn rv-btn--secondary rv-btn--sm" href="/latest">
            Main product
          </Link>
          <ProfileMenu />
        </div>
      </header>

      {navOpen ? (
        <nav className="rv-mobile-nav" aria-label="Admin navigation">
          {adminNav.map((item) => (
            <Link
              key={item.href}
              className="rv-topbar__link"
              href={item.href}
              aria-current={route === item.route ? "page" : undefined}
              onClick={() => setNavOpen(false)}
            >
              <item.Icon size={16} aria-hidden />
              {item.label}
            </Link>
          ))}
          <div className="rv-mobile-nav__footer">
            <Link
              className="rv-topbar__link"
              href="/latest"
              onClick={() => setNavOpen(false)}
            >
              Return to main product
            </Link>
          </div>
        </nav>
      ) : null}
    </>
  );
}
