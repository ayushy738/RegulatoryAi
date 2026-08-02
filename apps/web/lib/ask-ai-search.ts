import { z } from "zod";

export const askSearchGroupValues = [
  "best_match",
  "entities",
  "official_regulations",
  "official_documents",
  "amendments",
  "consultations",
  "deadlines",
  "previous_research",
] as const;

const searchableGroupSchema = z.enum(
  askSearchGroupValues.filter(
    (group) => group !== "best_match",
  ) as [
    Exclude<(typeof askSearchGroupValues)[number], "best_match">,
    ...Exclude<
      (typeof askSearchGroupValues)[number],
      "best_match"
    >[],
  ],
);
const optionalText = (maximum: number) =>
  z.string().trim().min(1).max(maximum).optional();

export const askSearchFiltersSchema = z
  .strictObject({
    provenance: z
      .enum(["internal_regulatory_corpus", "owned_research"])
      .optional(),
    jurisdiction: optionalText(200),
    regulator: optionalText(300),
    document_type: optionalText(200),
    entity_class: optionalText(100),
    status: optionalText(100),
    stakeholder: optionalText(300),
    topic: optionalText(300),
    lifecycle: z
      .enum(["current", "superseded", "draft"])
      .optional(),
    date_from: z.iso.date().optional(),
    date_to: z.iso.date().optional(),
  })
  .superRefine((value, context) => {
    if (
      value.date_from !== undefined &&
      value.date_to !== undefined &&
      value.date_from > value.date_to
    ) {
      context.addIssue({
        code: "custom",
        message: "Search date range cannot be reversed",
      });
    }
  });

export const askFederatedSearchRequestSchema = z
  .strictObject({
    schema_version: z.literal("1").default("1"),
    query: z
      .string()
      .trim()
      .min(1)
      .max(500)
      .transform((value) => value.replace(/\s+/g, " ")),
    correction_mode: z
      .enum(["auto", "original"])
      .default("auto"),
    filters: askSearchFiltersSchema.default({}),
    group: searchableGroupSchema.optional(),
    cursor: z.string().trim().min(1).max(2_000).optional(),
    limit: z.number().int().min(1).max(20).default(5),
  })
  .superRefine((value, context) => {
    if (value.cursor !== undefined && value.group === undefined) {
      context.addIssue({
        code: "custom",
        message: "A search cursor requires its result group",
      });
    }
  });

const resultTypeSchema = z.enum([
  "entity",
  "official_regulation",
  "official_document",
  "amendment",
  "consultation",
  "deadline",
  "previous_research",
]);
const groupType = {
  entities: "entity",
  official_regulations: "official_regulation",
  official_documents: "official_document",
  amendments: "amendment",
  consultations: "consultation",
  deadlines: "deadline",
  previous_research: "previous_research",
} as const;

export const askSearchItemSchema = z.strictObject({
  result_id: z.string().regex(/^[a-z_]+:[A-Za-z0-9._:-]+$/),
  result_type: resultTypeSchema,
  title: z.string().trim().min(1).max(1_000),
  subtitle: z.string().trim().min(1).max(2_000),
  why_matched: z.string().trim().min(1).max(2_000),
  provenance: z.enum([
    "internal_regulatory_corpus",
    "owned_research",
  ]),
  relevance: z.number().int().min(0).max(1_000),
  route: z
    .string()
    .trim()
    .min(1)
    .max(2_000)
    .regex(/^\/[A-Za-z0-9/?=&%._:-]+$/),
});

export const askSearchResultGroupSchema = z
  .strictObject({
    group: z.enum(askSearchGroupValues),
    status: z.enum([
      "complete",
      "no_match",
      "not_requested",
      "unavailable",
    ]),
    items: z.array(askSearchItemSchema),
    next_cursor: z.string().min(1).nullable(),
  })
  .superRefine((value, context) => {
    if (
      value.group === "best_match" &&
      (value.items.length > 1 || value.next_cursor !== null)
    ) {
      context.addIssue({
        code: "custom",
        message: "Best Match permits one item and no cursor",
      });
    }
    if (value.group !== "best_match") {
      const expectedType = groupType[value.group];
      if (
        value.items.some(
          (item) => item.result_type !== expectedType,
        )
      ) {
        context.addIssue({
          code: "custom",
          message: "Search item type does not match its group",
        });
      }
    }
    if (
      (value.status === "complete") !== (value.items.length > 0) ||
      (value.status !== "complete" && value.next_cursor !== null)
    ) {
      context.addIssue({
        code: "custom",
        message: "Search group status does not match its results",
      });
    }
    if (
      value.items.some(
        (item, index) =>
          index > 0 &&
          item.relevance > value.items[index - 1]!.relevance,
      ) ||
      new Set(value.items.map((item) => item.result_id)).size !==
        value.items.length
    ) {
      context.addIssue({
        code: "custom",
        message: "Search results require unique relevance order",
      });
    }
  });

export const askFederatedSearchResponseSchema = z
  .strictObject({
    schema_version: z.literal("1"),
    policy_version: z.literal("ask-ai-federated-search-v1"),
    original_query: z.string().trim().min(1),
    applied_query: z.string().trim().min(1),
    filters: askSearchFiltersSchema,
    correction: z
      .strictObject({
        kind: z.enum(["acronym_expansion", "spelling"]),
        original_query: z.string().trim().min(1),
        suggested_query: z.string().trim().min(1),
        reversible: z.literal(true),
      })
      .nullable(),
    groups: z.array(askSearchResultGroupSchema).length(
      askSearchGroupValues.length,
    ),
  })
  .superRefine((value, context) => {
    if (
      JSON.stringify(value.groups.map((group) => group.group)) !==
      JSON.stringify(askSearchGroupValues)
    ) {
      context.addIssue({
        code: "custom",
        message: "Search groups require canonical order",
      });
    }
    if (
      value.correction === null
        ? value.original_query !== value.applied_query
        : value.correction.original_query !== value.original_query ||
          value.correction.suggested_query !== value.applied_query
    ) {
      context.addIssue({
        code: "custom",
        message: "Search correction does not match query state",
      });
    }
  });

export type AskFederatedSearchRequest = z.infer<
  typeof askFederatedSearchRequestSchema
>;
export type AskFederatedSearchResponse = z.infer<
  typeof askFederatedSearchResponseSchema
>;
export type AskSearchItem = z.infer<typeof askSearchItemSchema>;
