import { z } from "zod";

const knowledgeModeSchema = z.enum([
  "grounded_regulatory",
  "general_ai",
  "live_intelligence",
]);
const structuredFieldStateSchema = z.enum([
  "established",
  "not_established",
]);
const confidenceLabelSchema = z.enum(["high", "medium", "low", "unknown"]);
const sourceStatusSchema = z.enum([
  "draft",
  "consultation",
  "in_force",
  "superseded",
  "repealed",
  "unknown",
]);
const reasonKindSchema = z.enum([
  "evidence",
  "coverage",
  "freshness",
  "scope",
  "capability",
]);
const introspection =
  /\b(?:chain[- ]of[- ]thought|internal reasoning|hidden reasoning|model reasoning|system prompt|i think|i believe)\b/i;

const unique = (values: readonly string[]) =>
  new Set(values).size === values.length;

export const askStructuredTextFieldSchema = z
  .strictObject({
    state: structuredFieldStateSchema,
    value: z.string().trim().min(1).max(50_000).nullable(),
  })
  .superRefine((value, context) => {
    if (
      (value.state === "established" && value.value === null) ||
      (value.state === "not_established" && value.value !== null)
    ) {
      context.addIssue({
        code: "custom",
        message: "Structured text state must match its value",
      });
    }
  });

function isCalendarDate(value: string) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
  const [year, month, day] = value.split("-").map(Number);
  const parsed = new Date(Date.UTC(year, month - 1, day));
  return (
    parsed.getUTCFullYear() === year &&
    parsed.getUTCMonth() === month - 1 &&
    parsed.getUTCDate() === day
  );
}

export const askStructuredDateFieldSchema = z
  .strictObject({
    state: structuredFieldStateSchema,
    value: z.string().trim().refine(isCalendarDate).nullable(),
  })
  .superRefine((value, context) => {
    if (
      (value.state === "established" && value.value === null) ||
      (value.state === "not_established" && value.value !== null)
    ) {
      context.addIssue({
        code: "custom",
        message: "Structured date state must match its value",
      });
    }
  });

export const askAnswerSummaryPayloadSchema = z.strictObject({
  schema_version: z.literal("1"),
  direct_answer: z.string().trim().min(1).max(50_000),
  why_it_matters: askStructuredTextFieldSchema,
  unresolved_assumptions: z
    .array(z.string().trim().min(1))
    .refine(unique),
  source_count: z.number().int().nonnegative(),
});

export const askDefinitionPayloadSchema = z.strictObject({
  schema_version: z.literal("1"),
  term: z.string().trim().min(1).max(500),
  official_definition: askStructuredTextFieldSchema,
  plain_language_explanation: z.string().trim().min(1).max(50_000),
  acronym_expansion: askStructuredTextFieldSchema,
  common_confusion: askStructuredTextFieldSchema,
  official_source_label: askStructuredTextFieldSchema,
});

export const askOfficialSourcePayloadSchema = z.strictObject({
  schema_version: z.literal("1"),
  source_id: z.string().trim().min(1).max(200),
  document_title: z.string().trim().min(1).max(1_000),
  issuer: z.string().trim().min(1).max(500),
  document_type: z.string().trim().min(1).max(300),
  issue_date: askStructuredDateFieldSchema,
  effective_date: askStructuredDateFieldSchema,
  current_status: sourceStatusSchema,
  cited_locator: z.string().trim().min(1).max(1_000),
  excerpt: z.string().trim().min(1).max(50_000),
  relationship: z.string().trim().min(1).max(2_000),
});

const confidenceReasonSchema = z.strictObject({
  kind: reasonKindSchema,
  text: z
    .string()
    .trim()
    .min(1)
    .max(2_000)
    .refine((value) => !introspection.test(value)),
});

export const askConfidenceCoveragePayloadSchema = z
  .strictObject({
    schema_version: z.literal("1"),
    modes_used: z.array(knowledgeModeSchema).min(1),
    coverage_percent: z.number().finite().min(0).max(100),
    official_documents_found: z.number().int().nonnegative(),
    live_sources_found: z.number().int().nonnegative(),
    reasons: z.array(confidenceReasonSchema).min(1),
    unsupported_or_inferred_areas: z.array(z.string().trim().min(1)),
    corpus_freshness: askStructuredTextFieldSchema,
    what_would_improve_confidence: z.array(z.string().trim().min(1)),
  })
  .superRefine((value, context) => {
    if (
      !unique(value.modes_used) ||
      !unique(value.reasons.map((reason) => reason.text)) ||
      !unique(value.unsupported_or_inferred_areas) ||
      !unique(value.what_would_improve_confidence)
    ) {
      context.addIssue({
        code: "custom",
        message: "Confidence Card metadata must be unique",
      });
    }
  });

export type AskAnswerSummaryPayload = z.infer<
  typeof askAnswerSummaryPayloadSchema
>;
export type AskDefinitionPayload = z.infer<typeof askDefinitionPayloadSchema>;
export type AskOfficialSourcePayload = z.infer<
  typeof askOfficialSourcePayloadSchema
>;
export type AskConfidenceCoveragePayload = z.infer<
  typeof askConfidenceCoveragePayloadSchema
>;
export type AskStructuredTextField = z.infer<
  typeof askStructuredTextFieldSchema
>;
export type AskStructuredDateField = z.infer<
  typeof askStructuredDateFieldSchema
>;

type CoreCardEnvelope = {
  card_type: string;
  state: "ready" | "partial" | "not_established" | "unavailable";
  knowledge_mode:
    | "grounded_regulatory"
    | "general_ai"
    | "live_intelligence";
  provenance_class:
    | "internal_regulatory_corpus"
    | "live_web_sources"
    | "general_ai_knowledge";
  confidence: {
    score: number;
    label: "high" | "medium" | "low" | "unknown";
    reasons: string[];
  } | null;
  source_ids: string[];
  actions: Array<{
    action: string;
    state: "available" | "disabled";
    target: string | null;
  }>;
  payload: Record<string, unknown>;
};

const labelRank = { unknown: 0, low: 1, medium: 2, high: 3 } as const;

function numericLabel(score: number): keyof typeof labelRank {
  if (score >= 80) return "high";
  if (score >= 60) return "medium";
  if (score >= 35) return "low";
  return "unknown";
}

export function coreCardValidationErrors(value: CoreCardEnvelope) {
  const errors: string[] = [];
  if (
    !["answer_summary", "definition", "official_source", "confidence_coverage"].includes(
      value.card_type,
    )
  ) {
    return errors;
  }
  if (!["ready", "partial"].includes(value.state)) {
    errors.push("Core cards must expose ready or partial content");
  }
  const expectedProvenance = {
    grounded_regulatory: "internal_regulatory_corpus",
    general_ai: "general_ai_knowledge",
    live_intelligence: "live_web_sources",
  }[value.knowledge_mode];
  if (value.provenance_class !== expectedProvenance) {
    errors.push("Core Card mode and provenance must remain pure");
  }
  if (
    value.confidence !== null &&
    labelRank[value.confidence.label] >
      labelRank[numericLabel(value.confidence.score)]
  ) {
    errors.push("Confidence label cannot exceed its numeric band");
  }
  if (
    value.knowledge_mode === "general_ai" &&
    value.confidence?.label === "high"
  ) {
    errors.push("General AI confidence cannot be High");
  }

  if (value.card_type === "answer_summary") {
    const result = askAnswerSummaryPayloadSchema.safeParse(value.payload);
    if (!result.success) return ["Invalid answer_summary payload", ...errors];
    if (value.confidence === null) {
      errors.push("Answer Summary requires confidence");
    }
    if (result.data.source_count !== value.source_ids.length) {
      errors.push("Summary source count must match card sources");
    }
    if (
      value.knowledge_mode === "general_ai" &&
      (result.data.source_count !== 0 || value.source_ids.length !== 0)
    ) {
      errors.push("General AI Summary cannot expose sources");
    }
    if (
      value.knowledge_mode !== "general_ai" &&
      result.data.source_count === 0
    ) {
      errors.push("Evidence-backed Summary requires sources");
    }
    if (
      result.data.why_it_matters.state === "not_established" &&
      value.state !== "partial"
    ) {
      errors.push("Missing Summary fields require partial state");
    }
    return errors;
  }

  if (value.card_type === "definition") {
    const result = askDefinitionPayloadSchema.safeParse(value.payload);
    if (!result.success) return ["Invalid definition payload", ...errors];
    if (value.knowledge_mode === "live_intelligence") {
      errors.push("Definition cards cannot use live provenance");
    }
    if (value.confidence === null) {
      errors.push("Definition Card requires confidence");
    }
    if (value.knowledge_mode === "grounded_regulatory") {
      if (
        value.provenance_class !== "internal_regulatory_corpus" ||
        value.source_ids.length === 0 ||
        result.data.official_definition.state !== "established" ||
        result.data.official_source_label.state !== "established"
      ) {
        errors.push(
          "Grounded Definition requires official definition and source",
        );
      }
    } else if (
      value.source_ids.length !== 0 ||
      result.data.official_definition.state !== "not_established" ||
      result.data.official_source_label.state !== "not_established"
    ) {
      errors.push(
        "General AI Definition cannot claim official definition or source",
      );
    }
    return errors;
  }

  if (value.card_type === "official_source") {
    const result = askOfficialSourcePayloadSchema.safeParse(value.payload);
    if (!result.success) return ["Invalid official_source payload", ...errors];
    if (
      value.knowledge_mode !== "grounded_regulatory" ||
      value.provenance_class !== "internal_regulatory_corpus"
    ) {
      errors.push("Official Source Card requires grounded provenance");
    }
    if (
      value.source_ids.length !== 1 ||
      value.source_ids[0] !== result.data.source_id
    ) {
      errors.push("Official Source Card requires its exact one source");
    }
    const actions = new Set(value.actions.map((action) => action.action));
    if (
      actions.size !== 3 ||
      !["open_source", "save", "compare"].every((action) =>
        actions.has(action),
      )
    ) {
      errors.push("Official Source Card requires Open, Save, and Compare");
    }
    if (
      value.actions.some(
        (action) =>
          ["open_source", "save"].includes(action.action) &&
          action.state === "available" &&
          action.target !== result.data.source_id,
      )
    ) {
      errors.push("Official Source action must target its source");
    }
    const incomplete =
      result.data.issue_date.state === "not_established" ||
      result.data.effective_date.state === "not_established" ||
      result.data.current_status === "unknown";
    if (incomplete !== (value.state === "partial")) {
      errors.push("Official Source state must reflect missing metadata");
    }
    return errors;
  }

  const result = askConfidenceCoveragePayloadSchema.safeParse(value.payload);
  if (!result.success) return ["Invalid confidence_coverage payload", ...errors];
  if (value.confidence === null) {
    errors.push("Confidence and Coverage Card requires confidence");
    return errors;
  }
  if (
    result.data.modes_used.length !== 1 ||
    result.data.modes_used[0] !== value.knowledge_mode
  ) {
    errors.push("Confidence Card cannot flatten provenance modes");
  }
  if (
    JSON.stringify(result.data.reasons.map((reason) => reason.text)) !==
    JSON.stringify(value.confidence.reasons)
  ) {
    errors.push("Confidence Card reasons must match its snapshot");
  }
  const officialCount =
    value.knowledge_mode === "grounded_regulatory"
      ? value.source_ids.length
      : 0;
  const liveCount =
    value.knowledge_mode === "live_intelligence"
      ? value.source_ids.length
      : 0;
  if (
    result.data.official_documents_found !== officialCount ||
    result.data.live_sources_found !== liveCount
  ) {
    errors.push("Confidence evidence counts must match card provenance");
  }
  if (
    value.knowledge_mode === "general_ai" &&
    result.data.corpus_freshness.state !== "not_established"
  ) {
    errors.push("General AI cannot claim corpus freshness");
  }
  if (value.actions.some((action) => action.action !== "inspect_evidence")) {
    errors.push("Confidence Card permits only Inspect evidence");
  }
  return errors;
}
