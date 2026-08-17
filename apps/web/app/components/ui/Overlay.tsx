"use client";

import {
  useCallback,
  useEffect,
  useId,
  useRef,
  type KeyboardEvent,
  type ReactNode,
} from "react";
import { AlertTriangle, X } from "lucide-react";

import { Button, IconButton } from "./Button";

const FOCUSABLE = [
  "a[href]",
  "button:not([disabled])",
  "input:not([disabled]):not([type='hidden'])",
  "select:not([disabled])",
  "textarea:not([disabled])",
  "summary",
  "[tabindex]:not([tabindex='-1'])",
].join(",");

/** Lock background scrolling while any overlay is mounted. */
function useScrollLock(active: boolean) {
  useEffect(() => {
    if (!active) return undefined;
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = previous;
    };
  }, [active]);
}

/**
 * Move focus into the dialog on open, keep Tab cycling inside it, and restore
 * focus to the trigger on close.
 */
function useFocusTrap(open: boolean) {
  const ref = useRef<HTMLDivElement | null>(null);
  const restoreTo = useRef<HTMLElement | null>(null);

  useEffect(() => {
    if (!open) return undefined;
    restoreTo.current = document.activeElement as HTMLElement | null;
    const node = ref.current;
    if (node) {
      const target =
        node.querySelector<HTMLElement>("[data-autofocus]") ??
        node.querySelector<HTMLElement>(FOCUSABLE) ??
        node;
      target.focus({ preventScroll: true });
    }
    return () => {
      restoreTo.current?.focus?.({ preventScroll: true });
    };
  }, [open]);

  const onKeyDown = useCallback((event: KeyboardEvent<HTMLDivElement>) => {
    if (event.key !== "Tab") return;
    const node = ref.current;
    if (!node) return;
    const focusable = Array.from(node.querySelectorAll<HTMLElement>(FOCUSABLE)).filter(
      (element) => element.offsetParent !== null || element === document.activeElement,
    );
    if (!focusable.length) return;
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  }, []);

  return { ref, onKeyDown };
}

export type OverlayVariant = "modal" | "sheet" | "drawer";
export type OverlaySize = "sm" | "md" | "lg";

export type OverlayProps = {
  open: boolean;
  onClose: () => void;
  title: string;
  description?: string;
  /** Rendered in the sticky footer. Provide the explicit Cancel action here. */
  footer?: ReactNode;
  children: ReactNode;
  variant?: OverlayVariant;
  size?: OverlaySize;
  /** Set for content that manages its own padding (e.g. a scrolling feed). */
  flushBody?: boolean;
  /** Extra element rendered beside the close button, e.g. a counter. */
  headerAside?: ReactNode;
};

/**
 * One overlay implementation behind three presentations:
 * `modal` centres on desktop, `sheet` rises from the bottom edge on mobile, and
 * `drawer` slides in from the right. All three go full-screen below 768px, trap
 * focus, close on Escape and on backdrop click, and scroll internally.
 */
export function Overlay({
  open,
  onClose,
  title,
  description,
  footer,
  children,
  variant = "modal",
  size = "md",
  flushBody = false,
  headerAside,
}: OverlayProps) {
  const titleId = useId();
  const descriptionId = useId();
  const { ref, onKeyDown } = useFocusTrap(open);

  useScrollLock(open);

  useEffect(() => {
    if (!open) return undefined;
    const handler = (event: globalThis.KeyboardEvent) => {
      if (event.key === "Escape") {
        event.stopPropagation();
        onClose();
      }
    };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [onClose, open]);

  if (!open) return null;

  const overlayClass = [
    "rv-overlay",
    variant === "sheet" ? "rv-overlay--sheet" : "",
    variant === "drawer" ? "rv-overlay--right" : "",
  ]
    .filter(Boolean)
    .join(" ");

  const dialogClass = [
    "rv-dialog",
    variant === "drawer" ? "rv-dialog--drawer" : "",
    variant !== "drawer" && size !== "md" ? `rv-dialog--${size}` : "",
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <div
      className={overlayClass}
      role="presentation"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <div
        ref={ref}
        className={dialogClass}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={description ? descriptionId : undefined}
        tabIndex={-1}
        onKeyDown={onKeyDown}
      >
        <div className="rv-dialog__header">
          <div className="rv-dialog__heading">
            <h2 className="rv-dialog__title" id={titleId}>
              {title}
            </h2>
            {description ? (
              <p className="rv-dialog__description" id={descriptionId}>
                {description}
              </p>
            ) : null}
          </div>
          <div className="rv-btn-group">
            {headerAside}
            <IconButton label={`Close ${title.toLowerCase()}`} Icon={X} onClick={onClose} />
          </div>
        </div>
        <div className={`rv-dialog__body${flushBody ? " rv-dialog__body--flush" : ""}`}>
          {children}
        </div>
        {footer ? <div className="rv-dialog__footer">{footer}</div> : null}
      </div>
    </div>
  );
}

/**
 * Confirmation for actions that destroy data or escalate privileges. Never used
 * for reversible actions — those just happen.
 */
export function ConfirmDialog({
  open,
  title,
  body,
  confirmLabel,
  cancelLabel = "Cancel",
  destructive = true,
  loading = false,
  onConfirm,
  onCancel,
}: {
  open: boolean;
  title: string;
  body: ReactNode;
  confirmLabel: string;
  cancelLabel?: string;
  destructive?: boolean;
  loading?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  return (
    <Overlay
      open={open}
      onClose={onCancel}
      title={title}
      size="sm"
      footer={
        <>
          <Button variant="secondary" onClick={onCancel} disabled={loading}>
            {cancelLabel}
          </Button>
          <Button
            variant={destructive ? "danger-solid" : "primary"}
            onClick={onConfirm}
            loading={loading}
            data-autofocus
          >
            {confirmLabel}
          </Button>
        </>
      }
    >
      <div className="rv-confirm">
        {destructive ? (
          <span className="rv-state__icon" aria-hidden>
            <AlertTriangle size={18} />
          </span>
        ) : null}
        <div className="rv-stack">
          {typeof body === "string" ? <p className="rv-page-subtitle">{body}</p> : body}
        </div>
      </div>
    </Overlay>
  );
}
