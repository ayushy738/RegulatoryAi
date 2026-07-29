import { z } from "zod";

const optionalText = (maximum: number) =>
  z.string().trim().min(1).max(maximum).transform(
    (value) => value.replace(/\s+/g, " "),
  ).optional();

export const askManualDocumentSearchRequestSchema = z
  .strictObject({
    schema_version: z.literal("1").default("1"),
    document_id: z.number().int().positive().optional(),
    registry_version_id: z.number().int().positive().optional(),
    query: optionalText(500),
    exact_phrase: z.boolean().default(false),
    title: optionalText(500),
    issuer: optionalText(300),
    document_number: optionalText(300),
    document_type: optionalText(200),
    family: optionalText(500),
    version: optionalText(300),
    status: z.enum(["current", "superseded", "draft"]).optional(),
    issued_from: z.iso.date().optional(),
    issued_to: z.iso.date().optional(),
    effective_from: z.iso.date().optional(),
    effective_to: z.iso.date().optional(),
    within_document: optionalText(500),
    cursor: z.string().trim().min(1).max(2_000).optional(),
    limit: z.number().int().min(1).max(50).default(20),
  })
  .superRefine((value, context) => {
    if (value.exact_phrase && value.query === undefined) {
      context.addIssue({
        code: "custom",
        message: "Exact phrase mode requires a query",
      });
    }
    if (
      value.issued_from !== undefined &&
      value.issued_to !== undefined &&
      value.issued_from > value.issued_to
    ) {
      context.addIssue({
        code: "custom",
        message: "Issue date range cannot be reversed",
      });
    }
    if (
      value.effective_from !== undefined &&
      value.effective_to !== undefined &&
      value.effective_from > value.effective_to
    ) {
      context.addIssue({
        code: "custom",
        message: "Effective date range cannot be reversed",
      });
    }
    const criteria = [
      value.document_id,
      value.registry_version_id,
      value.query,
      value.title,
      value.issuer,
      value.document_number,
      value.document_type,
      value.family,
      value.version,
      value.status,
      value.issued_from,
      value.issued_to,
      value.effective_from,
      value.effective_to,
      value.within_document,
    ];
    if (criteria.every((criterion) => criterion === undefined)) {
      context.addIssue({
        code: "custom",
        message: "Manual search requires at least one criterion",
      });
    }
  });

const withinDocumentMatchSchema = z.strictObject({
  chunk_id: z.number().int().positive(),
  page_number: z.number().int().positive().nullable(),
  section_title: z.string().trim().min(1).max(500).nullable(),
  excerpt: z.string().trim().min(1).max(800),
});

export const askManualDocumentSearchItemSchema = z
  .strictObject({
    result_id: z
      .string()
      .regex(/^document:[1-9][0-9]*(:[1-9][0-9]*)?$/),
    document_id: z.number().int().positive(),
    registry_version_id: z.number().int().positive().nullable(),
    document_version_id: z.number().int().positive().nullable(),
    family_id: z.number().int().positive().nullable(),
    title: z.string().trim().min(1).max(1_000),
    issuer: z.string().trim().min(1).max(500).nullable(),
    document_number: z.string().trim().min(1).max(500).nullable(),
    document_type: z.string().trim().min(1).max(300).nullable(),
    jurisdiction: z.string().trim().min(1).max(200).nullable(),
    issue_date: z.iso.date().nullable(),
    publication_date: z.iso.date().nullable(),
    effective_date: z.iso.date().nullable(),
    family_title: z.string().trim().min(1).max(1_000).nullable(),
    version_label: z.string().trim().min(1).max(500).nullable(),
    status: z.enum([
      "current",
      "superseded",
      "draft",
      "not_established",
    ]),
    metadata_state: z.enum(["complete", "partial"]),
    why_matched: z.string().trim().min(1).max(1_000),
    relevance: z.number().int().min(0).max(1_000),
    source_url: z
      .url()
      .refine((value) => /^https?:\/\//.test(value)),
    route: z
      .string()
      .trim()
      .min(1)
      .max(2_000)
      .regex(/^\/[A-Za-z0-9/?=&%._:-]+$/),
    within_document_matches: z.array(withinDocumentMatchSchema),
  })
  .superRefine((value, context) => {
    const suffix =
      value.registry_version_id === null
        ? ""
        : `:${value.registry_version_id}`;
    if (value.result_id !== `document:${value.document_id}${suffix}`) {
      context.addIssue({
        code: "custom",
        message: "Manual result identity does not match its document",
      });
    }
    if (
      value.metadata_state === "complete" &&
      (
        value.issuer === null ||
        value.document_type === null ||
        value.issue_date === null
      )
    ) {
      context.addIssue({
        code: "custom",
        message: "Complete document metadata requires core fields",
      });
    }
  });

export const askManualDocumentSearchResponseSchema = z
  .strictObject({
    schema_version: z.literal("1"),
    policy_version: z.literal(
      "ask-ai-manual-document-search-v1",
    ),
    status: z.enum(["complete", "no_match"]),
    as_of: z.iso.date(),
    items: z.array(askManualDocumentSearchItemSchema),
    next_cursor: z.string().trim().min(1).nullable(),
  })
  .superRefine((value, context) => {
    if ((value.status === "complete") !== (value.items.length > 0)) {
      context.addIssue({
        code: "custom",
        message: "Manual search status must agree with its results",
      });
    }
    if (value.status === "no_match" && value.next_cursor !== null) {
      context.addIssue({
        code: "custom",
        message: "No-match manual search cannot have a cursor",
      });
    }
    const keys = value.items.map((item) => [
      item.relevance,
      item.effective_date ??
        item.publication_date ??
        item.issue_date ??
        "0001-01-01",
      item.document_id,
      item.registry_version_id ?? 0,
    ] as const);
    const ordered = [...keys].sort((left, right) => {
      for (let index = 0; index < left.length; index += 1) {
        const leftValue = left[index]!;
        const rightValue = right[index]!;
        if (leftValue === rightValue) continue;
        return leftValue > rightValue ? -1 : 1;
      }
      return 0;
    });
    if (JSON.stringify(keys) !== JSON.stringify(ordered)) {
      context.addIssue({
        code: "custom",
        message: "Manual results require deterministic order",
      });
    }
    if (
      new Set(value.items.map((item) => item.result_id)).size !==
      value.items.length
    ) {
      context.addIssue({
        code: "custom",
        message: "Manual results must be unique",
      });
    }
  });

export type AskManualDocumentSearchRequest = z.infer<
  typeof askManualDocumentSearchRequestSchema
>;
export type AskManualDocumentSearchResponse = z.infer<
  typeof askManualDocumentSearchResponseSchema
>;
export type AskManualDocumentSearchItem = z.infer<
  typeof askManualDocumentSearchItemSchema
>;
