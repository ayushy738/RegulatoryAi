import { z } from "zod";

import { coreCardValidationErrors } from "./ask-ai-core-cards";

export const askResponseStrategyValues = [
  "definition_card",
  "entity_intelligence_page",
  "official_documents_overview",
  "deadline_cards_timeline",
  "stakeholder_cards",
  "comparison_table",
  "latest_intelligence",
  "timeline",
  "compliance_checklist",
  "executive_summary",
  "document_explanation",
  "amendment_cards",
  "consultation_deadline_cards",
  "conversation",
  "research_report",
] as const;

export const askResponseCardTypeValues = [
  "answer_summary",
  "definition",
  "official_source",
  "live_news",
  "obligation",
  "deadline",
  "timeline_event",
  "amendment",
  "comparison",
  "stakeholder",
  "related_regulation",
  "confidence_coverage",
] as const;

export const askCardActionTypeValues = [
  "inspect_evidence",
  "open_source",
  "save",
  "add_to_workspace",
  "compare",
  "open_entity",
  "ask_follow_up",
  "find_official_basis",
  "check_applicability",
  "add_to_tracker",
] as const;

const knowledgeModeSchema = z.enum([
  "grounded_regulatory",
  "general_ai",
  "live_intelligence",
]);
const provenanceClassSchema = z.enum([
  "internal_regulatory_corpus",
  "live_web_sources",
  "general_ai_knowledge",
]);
const confidenceLabelSchema = z.enum(["high", "medium", "low", "unknown"]);
const sectionTerminalStateSchema = z.enum([
  "ready",
  "ready_without_synthesis",
  "degraded",
  "empty_by_evidence",
  "omitted",
  "needs_clarification",
  "cancelled",
]);
const responseStrategySchema = z.enum(askResponseStrategyValues);
const responseCardTypeSchema = z.enum(askResponseCardTypeValues);
const cardActionTypeSchema = z.enum(askCardActionTypeValues);
const safeCode = /^[A-Z][A-Z0-9_]{0,99}$/;
const cardType = /^[a-z][a-z0-9_]{0,63}$/;

const unique = (values: readonly string[]) => new Set(values).size === values.length;

export const askResponseConfidenceSchema = z.strictObject({
  score: z.number().finite().min(0).max(100),
  label: confidenceLabelSchema,
  reasons: z.array(z.string().trim().min(1)).refine(unique),
});

export const askCardActionSchema = z
  .strictObject({
    action: cardActionTypeSchema,
    state: z.enum(["available", "disabled"]),
    target: z.string().trim().min(1).max(2_000).nullable(),
    disabled_reason_code: z.string().trim().regex(safeCode).nullable(),
  })
  .superRefine((value, context) => {
    if (
      value.state === "available" &&
      (value.target === null || value.disabled_reason_code !== null)
    ) {
      context.addIssue({
        code: "custom",
        message: "Available card actions require only a target",
      });
    }
    if (
      value.state === "disabled" &&
      (value.target !== null || value.disabled_reason_code === null)
    ) {
      context.addIssue({
        code: "custom",
        message: "Disabled card actions require only a safe reason",
      });
    }
  });

export const askResponseCardSchema = z
  .strictObject({
    schema_version: z.literal("1"),
    card_id: z.string().trim().min(1).max(200),
    order: z.number().int().nonnegative(),
    card_type: z.string().trim().regex(cardType),
    known_type: responseCardTypeSchema.nullable(),
    rendering: z.enum(["known", "unknown_fallback"]),
    fallback_title: z.string().trim().min(1).max(200).nullable(),
    title: z.string().trim().min(1).max(500),
    state: z.enum(["ready", "partial", "not_established", "unavailable"]),
    knowledge_mode: knowledgeModeSchema,
    provenance_class: provenanceClassSchema,
    confidence: askResponseConfidenceSchema.nullable(),
    claim_ids: z.array(z.string().trim().min(1)).refine(unique),
    source_ids: z.array(z.string().trim().min(1)).refine(unique),
    actions: z
      .array(askCardActionSchema)
      .refine((items) => unique(items.map((item) => item.action))),
    payload: z
      .record(z.string(), z.json())
      .refine((value) => Object.keys(value).length > 0),
  })
  .superRefine((value, context) => {
    const known = askResponseCardTypeValues.includes(
      value.card_type as (typeof askResponseCardTypeValues)[number],
    );
    if (
      known &&
      (value.known_type !== value.card_type ||
        value.rendering !== "known" ||
        value.fallback_title !== null)
    ) {
      context.addIssue({
        code: "custom",
        message: "Known cards require exact known rendering identity",
      });
    }
    if (
      !known &&
      (value.known_type !== null ||
        value.rendering !== "unknown_fallback" ||
        value.fallback_title === null)
    ) {
      context.addIssue({
        code: "custom",
        message: "Unknown cards require explicit fallback identity",
      });
    }
    for (const message of coreCardValidationErrors(value)) {
      context.addIssue({
        code: "custom",
        message,
      });
    }
  });

export const askStructuredResponseSectionSchema = z
  .strictObject({
    schema_version: z.literal("1"),
    section_id: z.string().trim().min(1).max(200),
    section_key: z.string().trim().min(1).max(200),
    order: z.number().int().nonnegative(),
    strategy: responseStrategySchema,
    title: z.string().trim().min(1).max(500),
    state: sectionTerminalStateSchema,
    knowledge_mode: knowledgeModeSchema,
    provenance_class: provenanceClassSchema,
    confidence: askResponseConfidenceSchema,
    claim_ids: z.array(z.string().trim().min(1)).refine(unique),
    source_ids: z.array(z.string().trim().min(1)).refine(unique),
    assumptions: z.array(z.string().trim().min(1)).refine(unique),
    gaps: z.array(z.string().trim().min(1)).refine(unique),
    cards: z.array(askResponseCardSchema),
  })
  .superRefine((value, context) => {
    const expectedProvenance = {
      grounded_regulatory: "internal_regulatory_corpus",
      general_ai: "general_ai_knowledge",
      live_intelligence: "live_web_sources",
    }[value.knowledge_mode];
    if (value.provenance_class !== expectedProvenance) {
      context.addIssue({
        code: "custom",
        message: "Section mode and provenance must remain pure",
      });
    }
    if (
      value.cards.some((card, index) => card.order !== index) ||
      !unique(value.cards.map((card) => card.card_id))
    ) {
      context.addIssue({
        code: "custom",
        message: "Cards require unique contiguous order",
      });
    }
    const claimIds = new Set(value.claim_ids);
    const sourceIds = new Set(value.source_ids);
    if (
      value.cards.some(
        (card) =>
          card.knowledge_mode !== value.knowledge_mode ||
          card.provenance_class !== value.provenance_class ||
          card.claim_ids.some((id) => !claimIds.has(id)) ||
          card.source_ids.some((id) => !sourceIds.has(id)),
      )
    ) {
      context.addIssue({
        code: "custom",
        message: "Cards cannot cross section identity or provenance",
      });
    }
  });

export const askStructuredResponseSchema = z
  .strictObject({
    schema_version: z.literal("1"),
    policy_version: z.string().trim().min(1),
    response_id: z.string().trim().min(1).max(200),
    response_strategy: responseStrategySchema,
    sections: z.array(askStructuredResponseSectionSchema).min(1),
    overall_confidence: askResponseConfidenceSchema,
    compatibility_summary: z.string().trim().min(1).max(50_000),
    assumptions: z.array(z.string().trim().min(1)).refine(unique),
    gaps: z.array(z.string().trim().min(1)).refine(unique),
  })
  .superRefine((value, context) => {
    const sectionIds = value.sections.map((section) => section.section_id);
    const sectionKeys = value.sections.map((section) => section.section_key);
    const cardIds = value.sections.flatMap((section) =>
      section.cards.map((card) => card.card_id),
    );
    if (
      value.sections.some((section, index) => section.order !== index) ||
      !unique(sectionIds) ||
      !unique(sectionKeys) ||
      !unique(cardIds)
    ) {
      context.addIssue({
        code: "custom",
        message: "Response sections and cards require unique contiguous identity",
      });
    }
  });

export type AskResponseConfidence = z.infer<typeof askResponseConfidenceSchema>;
export type AskCardAction = z.infer<typeof askCardActionSchema>;
export type AskResponseCard = z.infer<typeof askResponseCardSchema>;
export type AskStructuredResponseSection = z.infer<
  typeof askStructuredResponseSectionSchema
>;
export type AskStructuredResponse = z.infer<typeof askStructuredResponseSchema>;
