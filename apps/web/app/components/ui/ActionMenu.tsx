"use client";

import { useEffect, useRef, useState } from "react";
import { MoreHorizontal } from "lucide-react";
import type { LucideIcon } from "lucide-react";

import { IconButton } from "./Button";

export type ActionMenuItem = {
  id: string;
  label: string;
  Icon?: LucideIcon;
  onSelect: () => void;
  destructive?: boolean;
  disabled?: boolean;
  /** Renders a divider above this item. */
  separated?: boolean;
};

/**
 * Compact overflow menu for secondary and destructive row actions, so the
 * primary action on each row stays visually obvious.
 */
export function ActionMenu({
  label,
  items,
  align = "right",
}: {
  label: string;
  items: ActionMenuItem[];
  align?: "left" | "right";
}) {
  const [open, setOpen] = useState(false);
  const shell = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!open) return undefined;

    const onPointerDown = (event: MouseEvent) => {
      if (!shell.current?.contains(event.target as Node)) setOpen(false);
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

  if (!items.length) return null;

  return (
    <div className="rv-menu-shell" ref={shell}>
      <IconButton
        label={label}
        Icon={MoreHorizontal}
        variant="secondary"
        size="sm"
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={() => setOpen((value) => !value)}
      />
      {open ? (
        <div className={`rv-menu${align === "left" ? " rv-menu--left" : ""}`} role="menu">
          {items.map((item) => (
            <div key={item.id}>
              {item.separated ? <div className="rv-menu__separator" role="none" /> : null}
              <button
                type="button"
                role="menuitem"
                className={`rv-menu__item${item.destructive ? " rv-menu__item--danger" : ""}`}
                disabled={item.disabled}
                onClick={() => {
                  setOpen(false);
                  item.onSelect();
                }}
              >
                {item.Icon ? <item.Icon size={15} aria-hidden /> : null}
                {item.label}
              </button>
            </div>
          ))}
        </div>
      ) : null}
    </div>
  );
}
