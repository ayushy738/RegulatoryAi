import type { SourceCreatePayload, SourcePageCreatePayload } from "@/lib/api";

export type SourcePageDraft = SourcePageCreatePayload;

export type SourceDraft = {
  url: string;
  name: string;
  code: string;
  jurisdiction: SourceCreatePayload["jurisdiction"];
  crawler_type: SourceCreatePayload["crawler_type"];
  allowed_domains: string;
  hint: string;
  enabled: boolean;
  pages: SourcePageDraft[];
};

export const emptyPageDraft: SourcePageDraft = {
  name: "",
  url: "",
  page_type: "listing",
  priority: 100,
  enabled: true,
};

export const emptySourceDraft: SourceDraft = {
  url: "",
  name: "",
  code: "",
  jurisdiction: "central",
  crawler_type: "agent",
  allowed_domains: "",
  hint: "",
  enabled: true,
  pages: [{ ...emptyPageDraft }],
};

export function parseDomains(value: string) {
  return value
    .split(/[\n,]/)
    .map((item) => item.trim())
    .filter(Boolean);
}

/** Field-keyed validation messages, rendered beside the field they belong to. */
export type FieldErrors = Record<string, string>;

function isHttpUrl(value: string) {
  try {
    const url = new URL(value);
    return url.protocol === "http:" || url.protocol === "https:";
  } catch {
    return false;
  }
}

export function validateSourceDraft(draft: SourceDraft): FieldErrors {
  const errors: FieldErrors = {};

  if (!draft.url.trim()) {
    errors.url = "Website address is required.";
  } else if (!isHttpUrl(draft.url.trim())) {
    errors.url = "Enter a full address starting with https://";
  }

  if (!draft.name.trim()) errors.name = "Source name is required.";

  const code = draft.code.trim();
  if (!code) {
    errors.code = "Code is required.";
  } else if (!/^[A-Za-z0-9_-]{2,16}$/.test(code)) {
    errors.code = "Use 2–16 letters, numbers, hyphens or underscores.";
  }

  // Blank page rows are ignored on submit; only validate rows that were started.
  draft.pages.forEach((page, index) => {
    const startedName = page.name.trim();
    const startedUrl = page.url.trim();
    if (!startedName && !startedUrl) return;
    if (!startedName) errors[`pages.${index}.name`] = "Page name is required.";
    if (!startedUrl) {
      errors[`pages.${index}.url`] = "Page URL is required.";
    } else if (!isHttpUrl(startedUrl)) {
      errors[`pages.${index}.url`] = "Enter a full page URL.";
    }
  });

  return errors;
}

export function validatePageDraft(draft: SourcePageDraft): FieldErrors {
  const errors: FieldErrors = {};
  if (!draft.name.trim()) errors.name = "Page name is required.";
  if (!draft.url.trim()) {
    errors.url = "Page URL is required.";
  } else if (!isHttpUrl(draft.url.trim())) {
    errors.url = "Enter a full page URL starting with https://";
  }
  return errors;
}

export function completedPages(draft: SourceDraft) {
  return draft.pages.filter((page) => page.name.trim() && page.url.trim());
}

export function sourcePayloadFromDraft(draft: SourceDraft): SourceCreatePayload {
  return {
    code: draft.code.trim().toUpperCase(),
    name: draft.name.trim(),
    url: draft.url.trim(),
    jurisdiction: draft.jurisdiction,
    crawler_type: draft.crawler_type,
    allowed_domains: parseDomains(draft.allowed_domains),
    hint: draft.hint.trim() || null,
    enabled: draft.enabled,
  };
}

export function pagePayloadFromDraft(
  page: SourcePageDraft,
): SourcePageCreatePayload {
  return {
    name: page.name.trim(),
    url: page.url.trim(),
    page_type: page.page_type.trim() || "listing",
    priority: Number(page.priority) || 100,
    enabled: page.enabled,
  };
}
