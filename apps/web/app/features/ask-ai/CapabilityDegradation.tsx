"use client";

import { AlertCircle, Info, Search } from "lucide-react";

import {
  askCapabilityDegradationSchema,
  type AskCapabilityDegradation,
  type AskDegradationAction,
} from "@/lib/ask-ai-degradation";

export function CapabilityDegradation({
  value,
  onAction,
}: {
  value: AskCapabilityDegradation;
  onAction?: (action: AskDegradationAction) => void;
}) {
  const projection = askCapabilityDegradationSchema.parse(value);
  if (!projection.visible) {
    return null;
  }
  const commandActions = projection.actions.filter(
    (action) => action.kind !== "navigate",
  );
  if (commandActions.length > 0 && onAction === undefined) {
    throw new Error("Executable degradation actions require a handler");
  }
  const Icon =
    projection.severity === "information" || projection.severity === "needs_input"
      ? Info
      : AlertCircle;
  const stateClass =
    projection.severity === "information"
      ? "empty"
      : projection.severity === "needs_input"
        ? "pending"
        : "degraded";
  const titleId = `ask-degradation-${projection.capability}-${projection.safe_notice_code}`;

  return (
    <section
      className={`ask-mode-state ${stateClass}`}
      role="status"
      aria-labelledby={titleId}
      data-capability={projection.capability}
      data-severity={projection.severity}
      data-confidence-effect={projection.confidence_effect}
      data-terminal-state={projection.terminal_state}
    >
      <Icon size={20} aria-hidden="true" />
      <div>
        <h4 id={titleId}>{projection.title}</h4>
        <p>{projection.body}</p>
        {projection.actions.length > 0 ? (
          <div className="ask-degradation-actions" aria-label="Available actions">
            {projection.actions.map((action) =>
              action.kind === "navigate" ? (
                <a
                  className="ask-mode-state-action"
                  href={action.target}
                  key={action.action}
                >
                  <Search size={15} aria-hidden="true" />
                  {action.label}
                </a>
              ) : (
                <button
                  className="ask-mode-state-action"
                  key={action.action}
                  type="button"
                  onClick={() => onAction?.(action)}
                >
                  {action.label}
                </button>
              ),
            )}
          </div>
        ) : null}
      </div>
    </section>
  );
}
