"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { BellOff, Check, ExternalLink, Settings2 } from "lucide-react";

import { Badge } from "@/app/components/ui/Badge";
import { Button } from "@/app/components/ui/Button";
import { EmptyState } from "@/app/components/ui/EmptyState";
import { Overlay } from "@/app/components/ui/Overlay";
import {
  NOTIFICATION_TABS,
  filterNotifications,
} from "@/app/features/notifications/notification-feed";
import type {
  NotificationItem,
  NotificationTab,
} from "@/app/features/notifications/notification-feed";

/**
 * Notification feed only. Subscription configuration lives on its own page —
 * mixing "what happened" with "what should happen next time" made both harder
 * to use, and made the drawer far too tall on mobile.
 */
export function NotificationDrawer({
  open,
  items,
  onClose,
  onRead,
  onMarkAllRead,
  onClearRead,
}: {
  open: boolean;
  items: NotificationItem[];
  onClose: () => void;
  onRead: (id: string) => void;
  onMarkAllRead: () => void;
  onClearRead: () => void;
}) {
  const [tab, setTab] = useState<NotificationTab>("all");
  const visible = useMemo(() => filterNotifications(items, tab), [items, tab]);
  const unread = items.filter((item) => !item.isRead).length;

  return (
    <Overlay
      open={open}
      onClose={onClose}
      variant="drawer"
      title="Notifications"
      description={
        unread ? `${unread} unread alert${unread === 1 ? "" : "s"}` : "You're all caught up"
      }
      footer={
        <>
          <Link className="rv-btn rv-btn--secondary" href="/notifications" onClick={onClose}>
            <Settings2 size={16} aria-hidden />
            <span>Notification preferences</span>
          </Link>
          <Button variant="ghost" Icon={Check} onClick={onMarkAllRead} disabled={!unread}>
            Mark all read
          </Button>
        </>
      }
    >
      <div className="rv-stack">
        <div className="rv-tabs" role="tablist" aria-label="Notification filters">
          {NOTIFICATION_TABS.map((option) => (
            <button
              key={option.value}
              type="button"
              role="tab"
              className="rv-tab"
              aria-selected={tab === option.value}
              onClick={() => setTab(option.value)}
            >
              {option.label}
            </button>
          ))}
        </div>

        {visible.length ? (
          <div className="rv-notifications">
            {visible.map((item) => (
              <a
                key={item.id}
                className={`rv-notification${item.isRead ? " rv-notification--read" : ""}`}
                href={item.href}
                target={item.external ? "_blank" : undefined}
                rel={item.external ? "noreferrer" : undefined}
                onClick={() => onRead(item.id)}
              >
                <span
                  className="rv-notification__dot"
                  aria-label={item.isRead ? "Read" : "Unread"}
                  role="img"
                />
                <span className="rv-notification__body">
                  <span className="rv-notification__title">{item.title}</span>
                  <span className="rv-notification__context">{item.context}</span>
                  <span className="rv-notification__meta">
                    <span>{item.source}</span>
                    {item.date ? <span>{item.date}</span> : null}
                    {item.urgent ? <Badge tone="warning">Action needed</Badge> : null}
                    {item.external ? <ExternalLink size={12} aria-hidden /> : null}
                  </span>
                </span>
              </a>
            ))}
          </div>
        ) : (
          <EmptyState
            compact
            title={
              tab === "unread" ? "Nothing unread" : "No notifications in this view"
            }
            body="Consultations, amendments, tenders and deadline alerts for your subscribed sources appear here."
            Icon={BellOff}
            action={
              tab === "all" ? undefined : (
                <Button variant="secondary" size="sm" onClick={() => setTab("all")}>
                  Show all notifications
                </Button>
              )
            }
          />
        )}

        {items.some((item) => item.isRead) ? (
          <Button variant="link" size="sm" onClick={onClearRead}>
            Clear read notifications
          </Button>
        ) : null}
      </div>
    </Overlay>
  );
}
