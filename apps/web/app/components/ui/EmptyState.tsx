"use client";

import type { ReactNode } from "react";
import { Inbox } from "lucide-react";
import type { LucideIcon } from "lucide-react";

/**
 * An empty state explains what is empty, why, and what to do next. `action` is
 * the recovery affordance — usually "Clear filters" or the primary create action.
 */
export function EmptyState({
  title,
  body,
  Icon = Inbox,
  action,
  compact = false,
}: {
  title: string;
  body: string;
  Icon?: LucideIcon;
  action?: ReactNode;
  compact?: boolean;
}) {
  return (
    <div className={`rv-state${compact ? " rv-state--inline" : ""}`}>
      <span className="rv-state__icon" aria-hidden>
        <Icon size={18} />
      </span>
      <h3 className="rv-state__title">{title}</h3>
      <p className="rv-state__body">{body}</p>
      {action}
    </div>
  );
}
