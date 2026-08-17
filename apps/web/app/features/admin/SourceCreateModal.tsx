"use client";

import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { Plus, Trash2 } from "lucide-react";

import { Button, IconButton } from "@/app/components/ui/Button";
import {
  CheckboxField,
  SelectField,
  TextAreaField,
  TextField,
} from "@/app/components/ui/Field";
import { Overlay } from "@/app/components/ui/Overlay";
import { createSource, createSourcePage } from "@/lib/api";

import {
  completedPages,
  emptyPageDraft,
  emptySourceDraft,
  pagePayloadFromDraft,
  sourcePayloadFromDraft,
  validateSourceDraft,
} from "./source-form";
import type { FieldErrors, SourceDraft, SourcePageDraft } from "./source-form";

/**
 * Create Source as a modal (full-screen sheet on mobile) rather than a permanent
 * card occupying the top of the Sources page. Sectioned into source identity,
 * crawl configuration, and monitored pages, with per-field validation.
 */
export function SourceCreateModal({
  open,
  token,
  onClose,
  onCreated,
}: {
  open: boolean;
  token?: string;
  onClose: () => void;
  onCreated: (message: string) => void;
}) {
  const [draft, setDraft] = useState<SourceDraft>(emptySourceDraft);
  const [errors, setErrors] = useState<FieldErrors>({});
  const [submitError, setSubmitError] = useState("");

  function patch(changes: Partial<SourceDraft>) {
    setDraft((current) => ({ ...current, ...changes }));
  }

  function patchPage(index: number, changes: Partial<SourcePageDraft>) {
    setDraft((current) => ({
      ...current,
      pages: current.pages.map((page, pageIndex) =>
        pageIndex === index ? { ...page, ...changes } : page,
      ),
    }));
  }

  function addPageRow() {
    setDraft((current) => ({
      ...current,
      pages: [...current.pages, { ...emptyPageDraft }],
    }));
  }

  function removePageRow(index: number) {
    setDraft((current) => ({
      ...current,
      pages:
        current.pages.length === 1
          ? [{ ...emptyPageDraft }]
          : current.pages.filter((_, pageIndex) => pageIndex !== index),
    }));
  }

  function reset() {
    setDraft(emptySourceDraft);
    setErrors({});
    setSubmitError("");
  }

  const createMutation = useMutation({
    mutationFn: async () => {
      const source = await createSource(sourcePayloadFromDraft(draft), token);
      const pages = completedPages(draft);
      // Pages are created sequentially so a policy rejection names the row that
      // failed rather than surfacing an opaque aggregate error.
      const created: string[] = [];
      for (const page of pages) {
        const saved = await createSourcePage(
          source.id,
          pagePayloadFromDraft(page),
          token,
        );
        created.push(saved.name);
      }
      return { source, pageCount: created.length };
    },
    onSuccess: ({ source, pageCount }) => {
      onCreated(
        pageCount
          ? `Created ${source.name} with ${pageCount} monitored page${pageCount === 1 ? "" : "s"}.`
          : `Created ${source.name}. Add monitored pages to start crawling.`,
      );
      reset();
      onClose();
    },
    onError: (error) =>
      setSubmitError(
        error instanceof Error ? error.message : "Unable to create source.",
      ),
  });

  function submit() {
    setSubmitError("");
    const validation = validateSourceDraft(draft);
    setErrors(validation);
    if (Object.keys(validation).length) return;
    createMutation.mutate();
  }

  const pageCount = completedPages(draft).length;

  return (
    <Overlay
      open={open}
      onClose={() => {
        if (createMutation.isPending) return;
        reset();
        onClose();
      }}
      title="Add source"
      description="Register a regulatory website and the pages Resolven should monitor."
      size="lg"
      footer={
        <>
          <Button
            variant="secondary"
            onClick={() => {
              reset();
              onClose();
            }}
            disabled={createMutation.isPending}
          >
            Cancel
          </Button>
          <Button variant="primary" onClick={submit} loading={createMutation.isPending}>
            Create source
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

        <fieldset className="rv-fieldset">
          <legend>Source details</legend>
          <div className="rv-field-grid">
            <TextField
              label="Website"
              type="url"
              wide
              autoFocus
              value={draft.url}
              error={errors.url}
              hint="The site root Resolven will crawl from."
              placeholder="https://example.gov.in"
              onChange={(value) => patch({ url: value })}
            />
            <TextField
              label="Source name"
              value={draft.name}
              error={errors.name}
              placeholder="Central Electricity Regulatory Commission"
              onChange={(value) => patch({ name: value })}
            />
            <TextField
              label="Code"
              value={draft.code}
              error={errors.code}
              hint="Short identifier used across the workspace."
              placeholder="CERC"
              onChange={(value) => patch({ code: value })}
            />
            <SelectField
              label="Jurisdiction"
              value={draft.jurisdiction}
              options={[
                { value: "central", label: "Central" },
                { value: "state", label: "State" },
              ]}
              onChange={(value) => patch({ jurisdiction: value })}
            />
            <SelectField
              label="Crawler"
              value={draft.crawler_type}
              options={[
                { value: "agent", label: "Agent" },
                { value: "digest", label: "Digest" },
                { value: "static", label: "Static" },
              ]}
              onChange={(value) => patch({ crawler_type: value })}
            />
          </div>
        </fieldset>

        <fieldset className="rv-fieldset">
          <legend>Crawl configuration</legend>
          <div className="rv-field-grid">
            <TextField
              label="Allowed domains"
              wide
              optional
              value={draft.allowed_domains}
              hint="Extra CDN or mirror hosts, comma separated. The website host is always allowed."
              placeholder="cdn.example.gov.in, files.example.gov.in"
              onChange={(value) => patch({ allowed_domains: value })}
            />
            <TextAreaField
              label="Crawl hint"
              wide
              optional
              rows={2}
              value={draft.hint}
              hint="Guidance for the agent crawler about which sections matter."
              placeholder="Prioritise current notices, tenders, public consultations and amendments."
              onChange={(value) => patch({ hint: value })}
            />
          </div>
          <CheckboxField
            label="Enable this source immediately"
            hint="Disabled sources stay in the registry but are skipped by crawls."
            checked={draft.enabled}
            onChange={(checked) => patch({ enabled: checked })}
          />
        </fieldset>

        <fieldset className="rv-fieldset">
          <legend>Monitored pages</legend>
          <p className="rv-helper">
            {pageCount
              ? `${pageCount} page${pageCount === 1 ? "" : "s"} ready to create.`
              : "Add at least one page to crawl, or add them later from the source row."}
          </p>
          {draft.pages.map((page, index) => (
            <div className="rv-card" key={`page-draft-${index}`}>
              <div className="rv-card__header">
                <h3 className="rv-card-title">Page {index + 1}</h3>
                <IconButton
                  label={`Remove page ${index + 1}`}
                  Icon={Trash2}
                  size="sm"
                  variant="ghost"
                  onClick={() => removePageRow(index)}
                />
              </div>
              <div className="rv-field-grid">
                <TextField
                  label="Page name"
                  value={page.name}
                  error={errors[`pages.${index}.name`]}
                  placeholder="Current Notices"
                  onChange={(value) => patchPage(index, { name: value })}
                />
                <TextField
                  label="Page URL"
                  type="url"
                  value={page.url}
                  error={errors[`pages.${index}.url`]}
                  placeholder="https://example.gov.in/notices"
                  onChange={(value) => patchPage(index, { url: value })}
                />
                <TextField
                  label="Type"
                  value={page.page_type}
                  placeholder="listing"
                  onChange={(value) => patchPage(index, { page_type: value })}
                />
                <TextField
                  label="Priority"
                  type="number"
                  min={1}
                  value={page.priority}
                  hint="Lower runs first."
                  onChange={(value) =>
                    patchPage(index, { priority: Number(value) || 100 })
                  }
                />
              </div>
              <CheckboxField
                label="Enabled"
                checked={page.enabled}
                onChange={(checked) => patchPage(index, { enabled: checked })}
              />
            </div>
          ))}
          <div>
            <Button variant="secondary" Icon={Plus} size="sm" onClick={addPageRow}>
              Add another page
            </Button>
          </div>
        </fieldset>
      </form>
    </Overlay>
  );
}
