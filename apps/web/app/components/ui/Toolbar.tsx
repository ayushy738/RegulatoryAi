"use client";

import { useEffect, useId, useState } from "react";
import type { ReactNode } from "react";
import { ChevronDown, RefreshCw, Search, SlidersHorizontal, X } from "lucide-react";

import { Button } from "./Button";
import { Overlay } from "./Overlay";

/** Debounced search input so typing does not fire a request per keystroke. */
export function SearchInput({
  value,
  onChange,
  placeholder = "Search",
  label,
  debounceMs = 300,
}: {
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  label: string;
  debounceMs?: number;
}) {
  const [draft, setDraft] = useState(value);

  // Keep the field in sync when filters are cleared from outside.
  useEffect(() => {
    setDraft(value);
  }, [value]);

  useEffect(() => {
    if (draft === value) return undefined;
    const timer = window.setTimeout(() => onChange(draft), debounceMs);
    return () => window.clearTimeout(timer);
  }, [debounceMs, draft, onChange, value]);

  return (
    <label className="rv-search">
      <Search size={16} aria-hidden />
      <span className="rv-visually-hidden">{label}</span>
      <input
        type="search"
        value={draft}
        placeholder={placeholder}
        onChange={(event) => setDraft(event.target.value)}
      />
      {draft ? (
        <button
          type="button"
          className="rv-search__clear"
          aria-label="Clear search"
          onClick={() => {
            setDraft("");
            onChange("");
          }}
        >
          <X size={14} aria-hidden />
        </button>
      ) : null}
    </label>
  );
}

export type FilterOption = { value: string; label: string };

/**
 * Compact filter dropdown. Shows its label only when a non-default value is
 * selected, so an unfiltered toolbar stays visually quiet.
 */
export function FilterSelect({
  label,
  value,
  options,
  onChange,
  defaultValue = "all",
}: {
  label: string;
  value: string;
  options: FilterOption[];
  onChange: (value: string) => void;
  defaultValue?: string;
}) {
  const id = useId();
  const active = value !== defaultValue;
  const selected = options.find((option) => option.value === value);
  const display = selected
    ? selected.value === defaultValue
      ? label
      : selected.label
    : label;

  return (
    <span
      className={`rv-select${active ? " rv-select--active" : ""}`}
      title={`${label}: ${display}`}
    >
      <label className="rv-visually-hidden" htmlFor={id}>
        {label}
      </label>
      <select
        id={id}
        value={value}
        onChange={(event) => onChange(event.target.value)}
      >
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.value === defaultValue ? label : option.label}
          </option>
        ))}
      </select>
      <ChevronDown className="rv-select__chevron" size={14} aria-hidden />
    </span>
  );
}

export function Toolbar({
  search,
  filters,
  actions,
  ariaLabel,
}: {
  search?: ReactNode;
  filters?: ReactNode;
  actions?: ReactNode;
  ariaLabel: string;
}) {
  return (
    <section className="rv-toolbar" aria-label={ariaLabel}>
      {search ? <div className="rv-toolbar__search">{search}</div> : null}
      {filters ? <div className="rv-toolbar__filters">{filters}</div> : null}
      {actions ? <div className="rv-toolbar__actions">{actions}</div> : null}
    </section>
  );
}

/**
 * Below 768px the filter set collapses to a single button that opens a bottom
 * sheet, instead of consuming the viewport with stacked dropdowns.
 */
export function FilterSheet({
  title,
  activeCount,
  onClear,
  children,
}: {
  title: string;
  activeCount: number;
  onClear?: () => void;
  children: ReactNode;
}) {
  const [open, setOpen] = useState(false);

  return (
    <>
      <Button
        variant={activeCount ? "primary" : "secondary"}
        Icon={SlidersHorizontal}
        onClick={() => setOpen(true)}
        className="rv-filter-trigger"
      >
        Filters
        {activeCount ? (
          <span className="rv-filter-trigger__count">{activeCount}</span>
        ) : null}
      </Button>
      <Overlay
        open={open}
        onClose={() => setOpen(false)}
        title={title}
        variant="sheet"
        footer={
          <>
            {onClear ? (
              <Button
                variant="ghost"
                onClick={() => {
                  onClear();
                  setOpen(false);
                }}
              >
                Clear all
              </Button>
            ) : null}
            <Button variant="primary" onClick={() => setOpen(false)}>
              Show results
            </Button>
          </>
        }
      >
        <div className="rv-form">{children}</div>
      </Overlay>
    </>
  );
}

/** A labelled toolbar refresh action — never a bare icon with floating text. */
export function RefreshButton({
  onClick,
  loading = false,
  label = "Refresh data",
}: {
  onClick: () => void;
  loading?: boolean;
  label?: string;
}) {
  return (
    <Button
      variant="secondary"
      Icon={RefreshCw}
      onClick={onClick}
      loading={loading}
      title={label}
    >
      Refresh
    </Button>
  );
}

/** Removable summary of what is currently filtering a list. */
export function ActiveFilters({
  entries,
  onClearAll,
}: {
  entries: Array<{ key: string; label: string; onRemove: () => void }>;
  onClearAll?: () => void;
}) {
  if (!entries.length) return null;
  return (
    <div className="rv-active-filters">
      {entries.map((entry) => (
        <span className="rv-chip" key={entry.key}>
          {entry.label}
          <button
            type="button"
            aria-label={`Remove filter ${entry.label}`}
            onClick={entry.onRemove}
          >
            <X size={12} aria-hidden />
          </button>
        </span>
      ))}
      {onClearAll && entries.length > 1 ? (
        <Button variant="link" size="sm" onClick={onClearAll}>
          Clear all
        </Button>
      ) : null}
    </div>
  );
}
