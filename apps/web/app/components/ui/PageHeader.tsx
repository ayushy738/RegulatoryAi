"use client";

import type { ReactNode } from "react";
import type { LucideIcon } from "lucide-react";

/**
 * Compact page header. Hierarchy comes from type, not from an oversized
 * container: eyebrow → title → one-line description, actions on the right.
 */
export function PageHeader({
  eyebrow,
  title,
  description,
  actions,
}: {
  eyebrow?: string;
  title: string;
  description?: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <header className="rv-page-header">
      <div className="rv-page-header__text">
        {eyebrow ? <p className="rv-eyebrow">{eyebrow}</p> : null}
        <h1 className="rv-page-title">{title}</h1>
        {description ? <p className="rv-page-subtitle">{description}</p> : null}
      </div>
      {actions ? <div className="rv-page-header__actions">{actions}</div> : null}
    </header>
  );
}

export function SectionHeader({
  title,
  count,
  actions,
  as: Tag = "h2",
}: {
  title: ReactNode;
  count?: ReactNode;
  actions?: ReactNode;
  as?: "h2" | "h3";
}) {
  return (
    <div className="rv-section__header">
      <div className="rv-section__heading">
        <Tag className="rv-section-title">{title}</Tag>
        {count !== undefined ? <span className="rv-section__count">{count}</span> : null}
      </div>
      {actions ? <div className="rv-btn-group">{actions}</div> : null}
    </div>
  );
}

export type MetricTone = "neutral" | "success" | "warning" | "danger";

/**
 * Metric strip cell. Deliberately small: a summary metric is a number with a
 * label, not a card that eats a third of the viewport.
 */
export function Metric({
  label,
  value,
  hint,
  tone = "neutral",
  Icon,
}: {
  label: string;
  value: ReactNode;
  hint?: string;
  tone?: MetricTone;
  Icon?: LucideIcon;
}) {
  return (
    <div className={`rv-metric${tone !== "neutral" ? ` rv-metric--${tone}` : ""}`}>
      <span className="rv-metric__label">
        {Icon ? <Icon size={13} aria-hidden /> : null}
        {label}
      </span>
      <span className="rv-metric__value">{value}</span>
      {hint ? <span className="rv-metric__hint">{hint}</span> : null}
    </div>
  );
}

export function MetricStrip({
  children,
  ariaLabel,
}: {
  children: ReactNode;
  ariaLabel: string;
}) {
  return (
    <section className="rv-metrics" aria-label={ariaLabel}>
      {children}
    </section>
  );
}

export function Fact({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="rv-fact">
      <span className="rv-fact__label">{label}</span>
      <span className="rv-fact__value">{value}</span>
    </div>
  );
}

export function FactList({
  children,
  ariaLabel,
}: {
  children: ReactNode;
  ariaLabel?: string;
}) {
  return (
    <div className="rv-facts" aria-label={ariaLabel}>
      {children}
    </div>
  );
}
