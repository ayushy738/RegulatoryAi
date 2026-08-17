"use client";

import { forwardRef } from "react";
import type { ButtonHTMLAttributes, ReactNode } from "react";
import { Loader2 } from "lucide-react";
import type { LucideIcon } from "lucide-react";

export type ButtonVariant =
  | "primary"
  | "secondary"
  | "ghost"
  | "danger"
  | "danger-solid"
  | "link";

export type ButtonSize = "sm" | "md" | "lg";

type BaseProps = {
  variant?: ButtonVariant;
  size?: ButtonSize;
  Icon?: LucideIcon;
  iconPosition?: "start" | "end";
  loading?: boolean;
  block?: boolean;
};

export type ButtonProps = BaseProps &
  Omit<ButtonHTMLAttributes<HTMLButtonElement>, "className"> & {
    children: ReactNode;
    className?: string;
  };

function classes(
  variant: ButtonVariant,
  size: ButtonSize,
  block: boolean,
  extra?: string,
) {
  return [
    "rv-btn",
    `rv-btn--${variant}`,
    size !== "md" ? `rv-btn--${size}` : "",
    block ? "rv-btn--block" : "",
    extra ?? "",
  ]
    .filter(Boolean)
    .join(" ");
}

/**
 * The single button primitive. Communicates intent through `variant`, owns its
 * hover/focus/disabled/loading states, and disables itself while loading so a
 * pending action cannot be fired twice.
 */
export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  {
    variant = "secondary",
    size = "md",
    Icon,
    iconPosition = "start",
    loading = false,
    block = false,
    disabled,
    children,
    className,
    type = "button",
    ...rest
  },
  ref,
) {
  const glyph = loading ? (
    <Loader2 className="rv-btn__spinner" size={size === "sm" ? 14 : 16} aria-hidden />
  ) : Icon ? (
    <Icon size={size === "sm" ? 14 : 16} aria-hidden />
  ) : null;

  return (
    <button
      {...rest}
      ref={ref}
      type={type}
      className={classes(variant, size, block, className)}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
    >
      {iconPosition === "start" ? glyph : null}
      <span>{children}</span>
      {iconPosition === "end" ? glyph : null}
    </button>
  );
});

export type IconButtonProps = Omit<BaseProps, "block" | "iconPosition"> &
  Omit<ButtonHTMLAttributes<HTMLButtonElement>, "className" | "children"> & {
    /** Required: an icon-only control must always expose an accessible name. */
    label: string;
    Icon: LucideIcon;
    className?: string;
  };

/**
 * Icon-only control. `label` is mandatory and becomes both the accessible name
 * and the native tooltip, so an icon never appears without context.
 */
export const IconButton = forwardRef<HTMLButtonElement, IconButtonProps>(
  function IconButton(
    {
      label,
      Icon,
      variant = "ghost",
      size = "md",
      loading = false,
      disabled,
      className,
      type = "button",
      ...rest
    },
    ref,
  ) {
    return (
      <button
        {...rest}
        ref={ref}
        type={type}
        aria-label={label}
        title={label}
        className={classes(variant, size, false, `rv-btn--icon ${className ?? ""}`)}
        disabled={disabled || loading}
        aria-busy={loading || undefined}
      >
        {loading ? (
          <Loader2 className="rv-btn__spinner" size={size === "sm" ? 14 : 16} aria-hidden />
        ) : (
          <Icon size={size === "sm" ? 14 : 16} aria-hidden />
        )}
      </button>
    );
  },
);

export type SegmentedOption<T extends string> = {
  value: T;
  label: string;
};

/** Two-to-three way exclusive choice, e.g. feed density. */
export function SegmentedControl<T extends string>({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: T;
  options: Array<SegmentedOption<T>>;
  onChange: (value: T) => void;
}) {
  return (
    <div className="rv-segmented" role="group" aria-label={label}>
      {options.map((option) => (
        <button
          key={option.value}
          type="button"
          aria-pressed={value === option.value}
          onClick={() => onChange(option.value)}
        >
          {option.label}
        </button>
      ))}
    </div>
  );
}
