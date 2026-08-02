import { z } from "zod";

const timestampSchema = z.iso.datetime({ offset: true });
const jsonObjectSchema = z.record(z.string(), z.unknown());

export const askMessageSchema = z.object({
  schema_version: z.literal("1"),
  id: z.uuid(),
  event_id: z.number().int().nullable(),
  role: z.enum(["user", "assistant"]),
  content: z.string(),
  created_at: timestampSchema,
});

export const askSectionSchema = z.object({
  id: z.uuid(),
  response_version: z.number().int().positive(),
  ordinal: z.number().int().nonnegative(),
  section_type: z.string(),
  status: z.string(),
  knowledge_mode: z.string(),
  provenance_label: z.string().nullable(),
  title: z.string().nullable(),
  plain_text: z.string().nullable(),
  content: jsonObjectSchema,
  card_schema_version: z.string(),
  model: z.string().nullable(),
  policy_version: z.string().nullable(),
  prompt_version: z.string().nullable(),
  required_disclosure: z.string().nullable(),
  created_at: timestampSchema,
  updated_at: timestampSchema,
});

export const askSourceSchema = z.object({
  id: z.uuid(),
  ordinal: z.number().int().nonnegative(),
  source_key: z.string(),
  source_class: z.string(),
  source_type: z.string(),
  document_id: z.number().int().nullable(),
  document_version_id: z.number().int().nullable(),
  chunk_id: z.number().int().nullable(),
  graph_reference: jsonObjectSchema.nullable(),
  title_snapshot: z.string(),
  url_snapshot: z.string(),
  issuer_snapshot: z.string().nullable(),
  publisher_snapshot: z.string().nullable(),
  jurisdiction_snapshot: z.string().nullable(),
  published_at: timestampSchema.nullable(),
  retrieved_at: timestampSchema,
  evidence_snapshot: z.string(),
  locator_snapshot: z.string().nullable(),
  content_hash: z.string().nullable(),
  metadata: jsonObjectSchema,
  created_at: timestampSchema,
});

export const askClaimSchema = z.object({
  id: z.uuid(),
  section_id: z.uuid(),
  ordinal: z.number().int().nonnegative(),
  knowledge_mode: z.string(),
  claim_text: z.string(),
  is_material: z.boolean(),
  support_status: z.string(),
  support_score: z.number().min(0).max(1).nullable(),
  model: z.string().nullable(),
  policy_version: z.string().nullable(),
  prompt_version: z.string().nullable(),
  required_disclosure: z.string().nullable(),
  verifier_model: z.string().nullable(),
  verifier_policy_version: z.string().nullable(),
  created_at: timestampSchema,
});

export const askCitationSchema = z.object({
  id: z.uuid(),
  claim_id: z.uuid(),
  source_id: z.uuid(),
  ordinal: z.number().int().nonnegative(),
  claim_knowledge_mode: z.string(),
  source_class: z.string(),
  citation_kind: z.string(),
  marker: z.string().nullable(),
  evidence_snapshot: z.string(),
  locator_snapshot: z.string().nullable(),
  support_score: z.number().min(0).max(1).nullable(),
  verification_status: z.string(),
  verifier_model: z.string().nullable(),
  verifier_policy_version: z.string().nullable(),
  created_at: timestampSchema,
});

export const askFollowupSchema = z.object({
  id: z.uuid(),
  ordinal: z.number().int().nonnegative(),
  label: z.string(),
  question: z.string(),
  action_type: z.string(),
  payload: jsonObjectSchema,
  created_at: timestampSchema,
});

export const askRunSchema = z.object({
  schema_version: z.literal("1"),
  id: z.uuid(),
  status: z.string(),
  knowledge_mode_summary: jsonObjectSchema,
  model: z.string().nullable(),
  policy_version: z.string().nullable(),
  prompt_version: z.string().nullable(),
  general_ai_disclosure: z.string().nullable(),
  safe_error_code: z.string().nullable(),
  safe_error_message: z.string().nullable(),
  started_at: timestampSchema.nullable(),
  completed_at: timestampSchema.nullable(),
  created_at: timestampSchema,
  updated_at: timestampSchema,
  sections: z.array(askSectionSchema),
  sources: z.array(askSourceSchema),
  claims: z.array(askClaimSchema),
  citations: z.array(askCitationSchema),
  followups: z.array(askFollowupSchema),
});

export const askTurnSchema = z
  .object({
    schema_version: z.literal("1"),
    id: z.uuid(),
    user_message: askMessageSchema.nullable(),
    assistant_message: askMessageSchema.nullable(),
    run: askRunSchema.nullable(),
  })
  .refine((turn) => turn.user_message !== null || turn.assistant_message !== null, {
    message: "A persisted turn must contain at least one message",
  });

export const askTurnListSchema = z.object({
  schema_version: z.literal("1"),
  items: z.array(askTurnSchema),
  next_cursor: z.string().nullable(),
});

export type AskMessage = z.infer<typeof askMessageSchema>;
export type AskSource = z.infer<typeof askSourceSchema>;
export type AskClaim = z.infer<typeof askClaimSchema>;
export type AskCitation = z.infer<typeof askCitationSchema>;
export type AskRun = z.infer<typeof askRunSchema>;
export type AskTurn = z.infer<typeof askTurnSchema>;
export type AskTurnList = z.infer<typeof askTurnListSchema>;
