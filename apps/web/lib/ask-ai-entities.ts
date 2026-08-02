import { z } from "zod";

export const askEntityClassValues = [
  "regulatory_concept",
  "regulation_family",
  "legal_instrument",
  "regulator",
  "scheme_or_policy",
  "market_or_commodity",
  "stakeholder",
  "obligation",
  "document",
  "jurisdiction",
  "status",
] as const;

export const askEntityLookupRequestSchema = z
  .object({
    schema_version: z.literal("1").default("1"),
    mention: z.string().trim().min(1).max(200),
    active_jurisdiction: z.string().trim().min(1).max(200).optional(),
  })
  .strict();

export function askEntityRoute(canonicalId: string) {
  return `/ask?entity=${encodeURIComponent(canonicalId)}`;
}

export const askEntityLookupCandidateSchema = z
  .object({
    canonical_id: z
      .string()
      .regex(/^[a-z0-9][a-z0-9._:-]{0,199}$/),
    canonical_name: z.string().min(1),
    entity_class: z.enum(askEntityClassValues),
    jurisdiction: z.string().min(1),
    aliases: z.array(z.string().min(1)),
    confidence: z.number().min(0).max(1),
    assumed: z.boolean(),
    match_reason: z.string().min(1),
    entity_route: z.string().min(1),
  })
  .strict()
  .superRefine((candidate, context) => {
    if (candidate.entity_route !== askEntityRoute(candidate.canonical_id)) {
      context.addIssue({
        code: "custom",
        path: ["entity_route"],
        message: "Entity route must use canonical identity",
      });
    }
    if (new Set(candidate.aliases).size !== candidate.aliases.length) {
      context.addIssue({
        code: "custom",
        path: ["aliases"],
        message: "Entity aliases must be unique",
      });
    }
  });

export const askEntityLookupResponseSchema = z
  .object({
    schema_version: z.literal("1"),
    policy_version: z.literal("ask-ai-decision-v1"),
    status: z.enum(["resolved", "ambiguous", "no_match"]),
    mention: z.string().min(1),
    match_rule: z.string().min(1),
    selected: askEntityLookupCandidateSchema.nullable().default(null),
    candidates: z.array(askEntityLookupCandidateSchema),
    clarification_question: z.string().min(1).nullable().default(null),
    surface: z.literal("entity_intelligence_page").nullable().default(null),
  })
  .strict()
  .superRefine((result, context) => {
    const candidateIds = result.candidates.map(
      (candidate) => candidate.canonical_id,
    );
    if (new Set(candidateIds).size !== candidateIds.length) {
      context.addIssue({
        code: "custom",
        path: ["candidates"],
        message: "Entity candidates must be unique",
      });
    }
    const valid =
      result.status === "resolved"
        ? result.selected !== null &&
          result.surface === "entity_intelligence_page" &&
          result.clarification_question === null
        : result.status === "ambiguous"
          ? result.selected === null &&
            result.candidates.length > 0 &&
            result.surface === null &&
            result.clarification_question !== null
          : result.selected === null &&
            result.candidates.length === 0 &&
            result.surface === null &&
            result.clarification_question !== null;
    if (!valid) {
      context.addIssue({
        code: "custom",
        message: "Entity lookup outcome shape is inconsistent",
      });
    }
  });

export type AskEntityLookupRequest = z.input<
  typeof askEntityLookupRequestSchema
>;
export type AskEntityLookupCandidate = z.infer<
  typeof askEntityLookupCandidateSchema
>;
export type AskEntityLookupResponse = z.infer<
  typeof askEntityLookupResponseSchema
>;
