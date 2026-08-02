import { z } from "zod";

import {
  askCitationSchema,
  askClaimSchema,
  askMessageSchema,
  askRunSchema,
  askSectionSchema,
  askSourceSchema,
} from "./ask-ai-turns";

const timestampSchema = z.iso.datetime({ offset: true });
const jsonObjectSchema = z.record(z.string(), z.unknown());

export const askFeedbackReasonSchema = z.enum([
  "missing_source",
  "source_does_not_support_claim",
  "outdated",
  "too_general",
  "wrong_entity",
  "incorrect_interpretation",
]);

export const askFeedbackRequestSchema = z.object({
  value: z.enum(["helpful", "not_helpful"]),
  reason_code: askFeedbackReasonSchema.nullable().optional(),
  comment: z.string().max(2000).nullable().optional(),
});

export const askFeedbackSchema = z.object({
  schema_version: z.literal("1"),
  id: z.uuid(),
  message_id: z.uuid(),
  run_id: z.uuid(),
  response_version: z.number().int().positive(),
  value: z.enum(["helpful", "not_helpful"]),
  reason_code: z.string().nullable(),
  comment: z.string().nullable(),
  created_at: timestampSchema,
  updated_at: timestampSchema,
});

export const askMessageEvidenceSchema = z.object({
  schema_version: z.literal("1"),
  message: askMessageSchema,
  response_version: z.number().int().positive(),
  run: askRunSchema,
  feedback: askFeedbackSchema.nullable(),
});

export const askMessageSourcesSchema = z.object({
  schema_version: z.literal("1"),
  message_id: z.uuid(),
  response_version: z.number().int().positive(),
  sections: z.array(askSectionSchema),
  sources: z.array(askSourceSchema),
  claims: z.array(askClaimSchema),
  citations: z.array(askCitationSchema),
});

export const askSavedItemTypeSchema = z.enum([
  "source",
  "citation",
  "card",
  "entity",
  "document",
]);

export const askSavedItemCreateRequestSchema = z.object({
  item_type: askSavedItemTypeSchema,
  target_id: z.string().trim().min(1).max(200),
});

export const askSavedItemSchema = z.object({
  schema_version: z.literal("1"),
  id: z.uuid(),
  session_id: z.uuid(),
  item_type: askSavedItemTypeSchema,
  target_id: z.string(),
  run_id: z.uuid().nullable(),
  response_version: z.number().int().positive().nullable(),
  label: z.string(),
  metadata: jsonObjectSchema,
  created_at: timestampSchema,
  updated_at: timestampSchema,
});

export const askSavedItemListSchema = z.object({
  schema_version: z.literal("1"),
  items: z.array(askSavedItemSchema),
});

export type AskFeedbackRequest = z.infer<typeof askFeedbackRequestSchema>;
export type AskFeedback = z.infer<typeof askFeedbackSchema>;
export type AskMessageEvidence = z.infer<typeof askMessageEvidenceSchema>;
export type AskMessageSources = z.infer<typeof askMessageSourcesSchema>;
export type AskSavedItemCreateRequest = z.infer<
  typeof askSavedItemCreateRequestSchema
>;
export type AskSavedItem = z.infer<typeof askSavedItemSchema>;
export type AskSavedItemList = z.infer<typeof askSavedItemListSchema>;
