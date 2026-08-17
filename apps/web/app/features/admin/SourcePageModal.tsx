"use client";

import { useEffect, useState } from "react";
import { useMutation } from "@tanstack/react-query";

import { Button } from "@/app/components/ui/Button";
import { CheckboxField, TextField } from "@/app/components/ui/Field";
import { Overlay } from "@/app/components/ui/Overlay";
import { createSourcePage, updateSourcePage } from "@/lib/api";
import type { SourcePage } from "@/lib/api";

import { emptyPageDraft, pagePayloadFromDraft, validatePageDraft } from "./source-form";
import type { FieldErrors, SourcePageDraft } from "./source-form";

/**
 * Add or edit one monitored page. Uses the same admin source-page endpoints and
 * therefore the same server-side URL policy validation as every other path — no
 * client-side allowlist is introduced here.
 */
export function SourcePageModal({
  open,
  sourceId,
  sourceName,
  page,
  token,
  onClose,
  onSaved,
}: {
  open: boolean;
  sourceId: number;
  sourceName: string;
  /** Provided when editing an existing page; omitted when adding. */
  page?: SourcePage | null;
  token?: string;
  onClose: () => void;
  onSaved: (message: string) => void;
}) {
  const editing = Boolean(page);
  const [draft, setDraft] = useState<SourcePageDraft>({ ...emptyPageDraft });
  const [errors, setErrors] = useState<FieldErrors>({});
  const [submitError, setSubmitError] = useState("");

  useEffect(() => {
    if (!open) return;
    setErrors({});
    setSubmitError("");
    setDraft(
      page
        ? {
            name: page.name,
            url: page.url,
            page_type: page.page_type,
            priority: page.priority,
            enabled: page.enabled,
          }
        : { ...emptyPageDraft },
    );
  }, [open, page]);

  const saveMutation = useMutation({
    mutationFn: () =>
      editing && page
        ? updateSourcePage(page.id, pagePayloadFromDraft(draft), token)
        : createSourcePage(sourceId, pagePayloadFromDraft(draft), token),
    onSuccess: (saved) => {
      onSaved(
        editing
          ? `Updated monitored page "${saved.name}".`
          : `Added monitored page "${saved.name}".`,
      );
      onClose();
    },
    onError: (error) =>
      setSubmitError(
        error instanceof Error ? error.message : "Unable to save source page.",
      ),
  });

  function submit() {
    setSubmitError("");
    const validation = validatePageDraft(draft);
    setErrors(validation);
    if (Object.keys(validation).length) return;
    saveMutation.mutate();
  }

  return (
    <Overlay
      open={open}
      onClose={() => {
        if (!saveMutation.isPending) onClose();
      }}
      title={editing ? "Edit monitored page" : "Add monitored page"}
      description={sourceName}
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={saveMutation.isPending}>
            Cancel
          </Button>
          <Button variant="primary" onClick={submit} loading={saveMutation.isPending}>
            {editing ? "Save page" : "Add page"}
          </Button>
        </>
      }
    >
      <form
        className="rv-form"
        noValidate
        onSubmit={(event) => {
          event.preventDefault();
          submit();
        }}
      >
        {submitError ? (
          <p className="rv-field__error" role="alert">
            {submitError}
          </p>
        ) : null}
        <div className="rv-field-grid">
          <TextField
            label="Page name"
            wide
            autoFocus
            value={draft.name}
            error={errors.name}
            placeholder="Draft Regulations"
            onChange={(value) => setDraft({ ...draft, name: value })}
          />
          <TextField
            label="Page URL"
            type="url"
            wide
            value={draft.url}
            error={errors.url}
            hint="Must sit within the source website or one of its allowed domains."
            placeholder="https://example.gov.in/regulations/draft"
            onChange={(value) => setDraft({ ...draft, url: value })}
          />
          <TextField
            label="Type"
            value={draft.page_type}
            placeholder="listing"
            onChange={(value) => setDraft({ ...draft, page_type: value })}
          />
          <TextField
            label="Priority"
            type="number"
            min={1}
            value={draft.priority}
            hint="Lower runs first."
            onChange={(value) =>
              setDraft({ ...draft, priority: Number(value) || 100 })
            }
          />
        </div>
        <CheckboxField
          label="Enabled"
          hint="Disabled pages are kept but skipped by crawls."
          checked={draft.enabled}
          onChange={(checked) => setDraft({ ...draft, enabled: checked })}
        />
      </form>
    </Overlay>
  );
}
