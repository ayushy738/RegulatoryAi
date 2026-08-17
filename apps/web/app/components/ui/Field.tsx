"use client";

import { useId } from "react";
import type { ReactNode } from "react";
import { AlertCircle } from "lucide-react";

type CommonProps = {
  label: string;
  error?: string;
  hint?: string;
  optional?: boolean;
  wide?: boolean;
};

function FieldShell({
  label,
  error,
  hint,
  optional,
  wide,
  controlId,
  children,
}: CommonProps & { controlId: string; children: ReactNode }) {
  return (
    <div
      className={`rv-field${error ? " rv-field--invalid" : ""}${wide ? " rv-field--wide" : ""}`}
    >
      <label className="rv-field__label" htmlFor={controlId}>
        {label}
        {optional ? <span className="rv-field__optional">optional</span> : null}
      </label>
      {children}
      {error ? (
        <span className="rv-field__error" id={`${controlId}-error`} role="alert">
          <AlertCircle size={13} aria-hidden />
          {error}
        </span>
      ) : hint ? (
        <span className="rv-field__hint" id={`${controlId}-hint`}>
          {hint}
        </span>
      ) : null}
    </div>
  );
}

export type TextFieldProps = CommonProps & {
  value: string | number;
  onChange: (value: string) => void;
  placeholder?: string;
  type?: "text" | "url" | "email" | "number" | "password";
  min?: number;
  disabled?: boolean;
  autoFocus?: boolean;
  autoComplete?: string;
};

/** Text input with the label, hint and validation message wired to the control. */
export function TextField({
  value,
  onChange,
  placeholder,
  type = "text",
  min,
  disabled,
  autoFocus,
  autoComplete,
  ...shell
}: TextFieldProps) {
  const id = useId();
  return (
    <FieldShell {...shell} controlId={id}>
      <input
        id={id}
        type={type}
        min={min}
        value={value}
        placeholder={placeholder}
        disabled={disabled}
        autoComplete={autoComplete}
        aria-invalid={shell.error ? true : undefined}
        aria-describedby={
          shell.error ? `${id}-error` : shell.hint ? `${id}-hint` : undefined
        }
        data-autofocus={autoFocus ? "" : undefined}
        onChange={(event) => onChange(event.target.value)}
      />
    </FieldShell>
  );
}

export function TextAreaField({
  value,
  onChange,
  placeholder,
  rows = 3,
  ...shell
}: CommonProps & {
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  rows?: number;
}) {
  const id = useId();
  return (
    <FieldShell {...shell} controlId={id}>
      <textarea
        id={id}
        rows={rows}
        value={value}
        placeholder={placeholder}
        aria-invalid={shell.error ? true : undefined}
        aria-describedby={
          shell.error ? `${id}-error` : shell.hint ? `${id}-hint` : undefined
        }
        onChange={(event) => onChange(event.target.value)}
      />
    </FieldShell>
  );
}

export function SelectField<T extends string>({
  value,
  onChange,
  options,
  ...shell
}: CommonProps & {
  value: T;
  onChange: (value: T) => void;
  options: Array<{ value: T; label: string }>;
}) {
  const id = useId();
  return (
    <FieldShell {...shell} controlId={id}>
      <select
        id={id}
        value={value}
        aria-invalid={shell.error ? true : undefined}
        aria-describedby={
          shell.error ? `${id}-error` : shell.hint ? `${id}-hint` : undefined
        }
        onChange={(event) => onChange(event.target.value as T)}
      >
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
    </FieldShell>
  );
}

/**
 * The hint sits outside the label and is linked with aria-describedby, so the
 * control's accessible name stays exactly the label text.
 */
export function CheckboxField({
  label,
  hint,
  checked,
  onChange,
  disabled,
}: {
  label: string;
  hint?: string;
  checked: boolean;
  onChange: (checked: boolean) => void;
  disabled?: boolean;
}) {
  const id = useId();
  return (
    <div className="rv-checkbox-field">
      <label className="rv-checkbox" htmlFor={id}>
        <input
          id={id}
          type="checkbox"
          checked={checked}
          disabled={disabled}
          aria-describedby={hint ? `${id}-hint` : undefined}
          onChange={(event) => onChange(event.target.checked)}
        />
        <span className="rv-checkbox__text">{label}</span>
      </label>
      {hint ? (
        <span className="rv-field__hint rv-checkbox__hint" id={`${id}-hint`}>
          {hint}
        </span>
      ) : null}
    </div>
  );
}
