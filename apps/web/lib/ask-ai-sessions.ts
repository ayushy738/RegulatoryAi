import { z } from "zod";

import { askSavedItemSchema } from "./ask-ai-evidence";
import { askTurnSchema } from "./ask-ai-turns";

const askSessionTimestampSchema = z.iso.datetime({ offset: true });
export const askSessionIdSchema = z.uuid();

export const askSessionCreateRequestSchema = z.object({
  event_id: z.number().int().positive().nullable().optional(),
  title: z.string().max(200).nullable().optional(),
  primary_entity: z.string().max(200).nullable().optional(),
  primary_topic: z.string().max(200).nullable().optional(),
  scope_snapshot: z.record(z.string(), z.unknown()).optional(),
});

export const askSessionSchema = z.object({
  schema_version: z.literal("1"),
  id: askSessionIdSchema,
  event_id: z.number().int().nullable(),
  title: z.string().nullable(),
  status: z.string(),
  primary_entity: z.string().nullable(),
  primary_topic: z.string().nullable(),
  scope_snapshot: z.record(z.string(), z.unknown()),
  knowledge_mode_summary: z.record(z.string(), z.unknown()),
  freshness_state: z.string().nullable(),
  is_pinned: z.boolean(),
  archived_at: askSessionTimestampSchema.nullable(),
  deleted_at: askSessionTimestampSchema.nullable(),
  created_at: askSessionTimestampSchema,
  updated_at: askSessionTimestampSchema,
  last_message_at: askSessionTimestampSchema.nullable(),
});

export const askSessionListSchema = z.object({
  schema_version: z.literal("1"),
  items: z.array(askSessionSchema),
  next_cursor: z.string().nullable(),
});

const normalizedSearchTextSchema = z
  .string()
  .transform((value) => value.trim().replace(/\s+/g, " ").toLocaleLowerCase())
  .pipe(z.string().min(1).max(200));

export const askSessionListQuerySchema = z.object({
  cursor: z.string().min(1).nullable().optional(),
  limit: z.number().int().min(1).max(100).optional(),
  q: normalizedSearchTextSchema.optional(),
  knowledge_mode: z.enum(["official", "general", "live"]).optional(),
  entity: normalizedSearchTextSchema.optional(),
  archived: z.boolean().optional(),
  pinned: z.boolean().optional(),
});

export const askSessionPatchRequestSchema = z
  .object({
    title: z.string().trim().min(1).max(200).optional(),
    is_pinned: z.boolean().optional(),
  })
  .refine((value) => value.title !== undefined || value.is_pinned !== undefined, {
    message: "At least one session change is required",
  });

export const askSessionLifecycleActionSchema = z.discriminatedUnion("type", [
  z.object({
    type: z.literal("patch"),
    session_id: askSessionIdSchema,
    patch: askSessionPatchRequestSchema,
  }),
  z.object({
    type: z.enum(["archive", "restore", "duplicate", "delete"]),
    session_id: askSessionIdSchema,
  }),
]);

export const askSessionExportSchema = z.object({
  schema_version: z.literal("1"),
  session: askSessionSchema,
  turns: z.array(askTurnSchema),
  saved_items: z.array(askSavedItemSchema),
});

export type AskSessionCreateRequest = z.infer<
  typeof askSessionCreateRequestSchema
>;
export type AskSession = z.infer<typeof askSessionSchema>;
export type AskSessionList = z.infer<typeof askSessionListSchema>;
export type AskSessionListQuery = z.infer<typeof askSessionListQuerySchema>;
export type AskSessionPatchRequest = z.infer<
  typeof askSessionPatchRequestSchema
>;
export type AskSessionLifecycleAction = z.infer<
  typeof askSessionLifecycleActionSchema
>;
export type AskSessionExport = z.infer<typeof askSessionExportSchema>;
