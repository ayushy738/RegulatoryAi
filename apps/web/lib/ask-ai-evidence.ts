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

export const askVerifierIdentitySchema = z.object({
  provider: z.string().min(1),
  verifier_version: z.string().min(1),
  model_version: z.string().min(1),
  prompt_version: z.string().min(1),
  policy_version: z.string().min(1),
});

export const askVerificationSummarySchema = z.object({
  outcome: z.enum([
    "supported",
    "partial_support",
    "contradiction",
    "unknown",
  ]),
  confidence: z.number().min(0).max(1).nullable(),
  publication_mode: z.enum(["grounded_prose", "evidence_only"]),
  final_claim_text: z.string().min(1),
  terminal_reason: z.string().regex(/^[A-Z][A-Z0-9_]{0,99}$/),
  latency_ms: z.number().int().nonnegative(),
  evidence_ids: z.array(z.string().min(1)),
  correction_applied: z.boolean(),
  verifier_identity: askVerifierIdentitySchema.nullable(),
});

export const askCitationDetailSchema = z.object({
  schema_version: z.literal("1"),
  message_id: z.uuid(),
  response_version: z.number().int().positive(),
  claim_id: z.uuid(),
  claim_key: z.string().min(1),
  claim_ordinal: z.number().int().nonnegative(),
  claim_text: z.string().min(1),
  support_status: z.string().min(1),
  support_score: z.number().min(0).max(1).nullable(),
  citation_id: z.uuid(),
  evidence_key: z.string().min(1),
  citation_ordinal: z.number().int().nonnegative(),
  marker: z.string().nullable(),
  verification_status: z.string().min(1),
  verifier_provider: z.string().nullable(),
  verifier_version: z.string().nullable(),
  verifier_model: z.string().nullable(),
  verifier_prompt_version: z.string().nullable(),
  verifier_policy_version: z.string().nullable(),
  verification_latency_ms: z.number().int().nonnegative().nullable(),
  verification: askVerificationSummarySchema.nullable(),
  provenance: jsonObjectSchema.nullable(),
  confidence_result: jsonObjectSchema.nullable(),
  source: askSourceSchema,
  current_source_status: z.enum([
    "current",
    "superseded",
    "available_unclassified",
    "not_applicable",
  ]),
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
export type AskCitationDetail = z.infer<typeof askCitationDetailSchema>;
export type AskSavedItemCreateRequest = z.infer<
  typeof askSavedItemCreateRequestSchema
>;
export type AskSavedItem = z.infer<typeof askSavedItemSchema>;
export type AskSavedItemList = z.infer<typeof askSavedItemListSchema>;
