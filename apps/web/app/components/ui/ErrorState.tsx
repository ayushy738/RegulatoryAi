"use client";

import type { ReactNode } from "react";
import { AlertTriangle, RefreshCw } from "lucide-react";

import { Button } from "./Button";

/**
 * User-facing failure state. The headline says which capability is unavailable;
 * raw technical text is only rendered for admins, behind a disclosure, so
 * end users never read a stack trace.
 */
export function ErrorState({
  title = "Something went wrong",
  body = "We couldn't retrieve this data.",
  error,
  onRetry,
  retryLabel = "Try again",
  showTechnicalDetails = false,
  compact = false,
  action,
}: {
  title?: string;
  body?: string;
  error?: unknown;
  onRetry?: () => void;
  retryLabel?: string;
  showTechnicalDetails?: boolean;
  compact?: boolean;
  action?: ReactNode;
}) {
  const technical =
    error instanceof Error
      ? `${error.name}: ${error.message}`
      : error
        ? String(error)
        : "";

  return (
    <div
      className={`rv-state rv-state--error${compact ? " rv-state--inline" : ""}`}
      role="alert"
    >
      <span className="rv-state__icon" aria-hidden>
        <AlertTriangle size={18} />
      </span>
      <h3 className="rv-state__title">{title}</h3>
      <p className="rv-state__body">{body}</p>
      <div className="rv-btn-group">
        {onRetry ? (
          <Button variant="secondary" Icon={RefreshCw} onClick={onRetry}>
            {retryLabel}
          </Button>
        ) : null}
        {action}
      </div>
      {showTechnicalDetails && technical ? (
        <details className="rv-disclosure" style={{ width: "100%", textAlign: "left" }}>
          <summary>Technical details</summary>
          <div className="rv-disclosure__content">
            <code className="rv-code">{technical}</code>
          </div>
        </details>
      ) : null}
    </div>
  );
}
