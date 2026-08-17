import { z } from "zod";

/**
 * Runtime validation schemas for every backend response consumed by the web app.
 *
 * - Endpoints backed by Pydantic models (events, digests, intelligence, chat,
 *   subscriptions) are validated strictly (unknown keys are stripped).
 * - Admin endpoints return raw SQL dicts (`list[dict]`), so their schemas are
 *   intentionally lenient (`looseObject` + nullish fields) to avoid breaking the
 *   UI on optional/nullable columns while still catching gross shape mismatches.
 *
 * All TypeScript types are inferred from these schemas to keep the client and
 * the runtime contract in lockstep.
 */

const jurisdictionSchema = z.enum(["central", "state"]);
const eventTypeSchema = z.enum(["NEW", "CHANGED", "REPLACEMENT", "DUPLICATE"]);

export const summaryPayloadSchema = z.object({
  plain_english_summary: z.string(),
  why_it_matters: z.string(),
  affected_segments: z.array(z.string()).default([]),
  important_dates: z.array(z.string()).default([]),
  action_required: z.enum(["none", "monitor", "urgent"]),
  confidence: z.enum(["high", "medium", "low"]),
  evidence_quotes: z.array(z.record(z.string(), z.unknown())).default([]),
});

export const digestEventSchema = z.object({
  id: z.number(),
  title: z.string(),
  issuing_body: z.string().nullable(),
  jurisdiction: jurisdictionSchema.nullable(),
  issue_date: z.string().nullable(),
  event_type: eventTypeSchema,
  topic_tags: z.array(z.string()).default([]),
  raw_summary: z.string().nullable(),
  summary: summaryPayloadSchema.nullable(),
  source_url: z.string(),
  detected_at: z.string(),
  is_read: z.boolean().default(false),
  is_bookmarked: z.boolean().default(false),
});

export const digestResponseSchema = z.object({
  digest_date: z.string(),
  event_count: z.number(),
  events: z.array(digestEventSchema).default([]),
});

export const eventListSchema = z.array(digestEventSchema);

export const subscriptionSettingsSchema = z.object({
  jurisdictions: z.array(jurisdictionSchema).default([]),
  source_ids: z.array(z.number()).default([]),
  topics: z.array(z.string()).default([]),
  email_enabled: z.boolean(),
  frequency: z.enum(["daily", "instant"]),
});

export const sourceCatalogItemSchema = z.object({
  id: z.number(),
  code: z.string(),
  name: z.string(),
  jurisdiction: jurisdictionSchema.optional(),
  enabled: z.boolean().optional(),
});

export const sourceCatalogListSchema = z.array(sourceCatalogItemSchema);

export const healthResponseSchema = z.object({
  status: z.enum(["ok", "degraded"]),
  database_configured: z.boolean(),
  database_connected: z.boolean(),
  storage_configured: z.boolean(),
  llm_provider: z.string(),
  effective_llm_provider: z.string(),
});

export const eventReadStateSchema = z.object({
  event_id: z.number(),
  is_read: z.boolean(),
});

export const eventBookmarkStateSchema = z.object({
  event_id: z.number(),
  is_bookmarked: z.boolean(),
});

export const ragCitationSchema = z.looseObject({
  document_id: z.coerce.number(),
  title: z.string(),
  issuer: z.string().nullable().optional(),
  issue_date: z.string().nullable().optional(),
  source_url: z.string(),
  chunk_id: z.coerce.number().nullable().optional(),
  page_number: z.coerce.number().nullable().optional(),
  section_title: z.string().nullable().optional(),
  evidence: z.string().nullable().optional(),
});

export const chatResponseSchema = z.object({
  reply: z.string(),
  model: z.string(),
  event_id: z.number().nullable(),
  session_id: z.string().nullable().optional(),
  intent: z.string().nullable().optional(),
  knowledge_basis: z.enum(["official", "general", "none"]).optional(),
  citations: z.array(ragCitationSchema).default([]),
  related_questions: z.array(z.string()).default([]),
});

export const chatConversationSummarySchema = z.object({
  id: z.string(),
  title: z.string().nullable().optional(),
  created_at: z.union([z.string(), z.number()]).nullable().optional(),
  updated_at: z.union([z.string(), z.number()]).nullable().optional(),
  last_message_at: z.union([z.string(), z.number()]).nullable().optional(),
});

export const chatConversationMessageSchema = z.object({
  id: z.union([z.string(), z.number()]),
  role: z.enum(["user", "assistant"]),
  content: z.string(),
  created_at: z.union([z.string(), z.number()]).nullable().optional(),
  knowledge_basis: z
    .enum(["official", "general", "none"])
    .nullable()
    .optional(),
  citations: z.array(ragCitationSchema).default([]),
});

export const chatConversationDetailSchema = z.object({
  id: z.string(),
  messages: z.array(chatConversationMessageSchema),
});

export const chatHistoryItemSchema = z.looseObject({
  id: z.number(),
  role: z.enum(["user", "assistant"]),
  content: z.string(),
  event_id: z.number().nullable().optional(),
  created_at: z.string().nullable().optional(),
});

export const chatHistorySchema = z.array(chatHistoryItemSchema);

/* ---------------- Intelligence ---------------- */

export const intelligenceDeadlineSchema = z.object({
  document_id: z.number(),
  title: z.string(),
  issuer: z.string().nullable(),
  deadline_type: z.string(),
  deadline_date: z.string().nullable(),
  raw_date: z.string().nullable(),
  days_remaining: z.number().nullable(),
  stakeholders_affected: z.array(z.string()).default([]),
  source_url: z.string(),
  confidence: z.number(),
  evidence: z.string().nullable(),
});

export const intelligenceObligationSchema = z.object({
  document_id: z.number(),
  title: z.string(),
  issuer: z.string().nullable(),
  obligation: z.string(),
  stakeholder: z.string(),
  deadline_date: z.string().nullable(),
  deadline_type: z.string().nullable(),
  confidence: z.number(),
  evidence: z.string().nullable(),
  source_url: z.string(),
});

export const stakeholderObligationGroupSchema = z.object({
  stakeholder: z.string(),
  obligations: z.array(intelligenceObligationSchema).default([]),
});

export const intelligenceDocumentRefSchema = z.object({
  document_id: z.number(),
  title: z.string(),
  issuer: z.string().nullable(),
  source_url: z.string(),
  document_type: z.string(),
  confidence: z.number().default(0),
  evidence: z.string().nullable(),
});

export const stakeholderIntelligenceSchema = z.object({
  stakeholder: z.string(),
  impact_summary: z.string(),
  compliance_summary: z.string(),
  action_summary: z.string(),
  regulations: z.array(intelligenceDocumentRefSchema).default([]),
  consultations: z.array(intelligenceDocumentRefSchema).default([]),
  obligations: z.array(intelligenceObligationSchema).default([]),
  deadlines: z.array(intelligenceDeadlineSchema).default([]),
  tenders: z.array(intelligenceDocumentRefSchema).default([]),
  counts: z.record(z.string(), z.number()).default({}),
});

export const intelligenceReadinessSchema = z.object({
  active_deadlines: z.array(intelligenceDeadlineSchema).default([]),
  stakeholder_obligations: z.array(stakeholderObligationGroupSchema).default([]),
  regulatory_impacts: z.array(stakeholderIntelligenceSchema).default([]),
  consultation_tracking: z.array(intelligenceDocumentRefSchema).default([]),
  status: z.string(),
  notes: z.array(z.string()).default([]),
});

export const intelligenceDeadlineListSchema = z.array(intelligenceDeadlineSchema);
export const obligationGroupListSchema = z.array(stakeholderObligationGroupSchema);
export const stakeholderIntelligenceListSchema = z.array(stakeholderIntelligenceSchema);

/* ---------------- Crawl / admin (lenient: raw SQL dicts) ---------------- */

export const crawlRunSchema = z.looseObject({
  id: z.number(),
  started_at: z.string(),
  finished_at: z.string().nullable().optional(),
  status: z.string(),
  sources_attempted: z.coerce.number().default(0),
  sources_succeeded: z.coerce.number().default(0),
  docs_found: z.coerce.number().default(0),
  new_events: z.coerce.number().default(0),
  errors: z.array(z.record(z.string(), z.unknown())).default([]),
  // Explicit run-scoped metrics. null means not derivable from current schema.
  pages_attempted: z.number().nullable().optional(),
  pages_succeeded: z.number().nullable().optional(),
  documents_discovered: z.coerce.number().optional(),
  documents_with_content: z.number().nullable().optional(),
  events_created: z.coerce.number().optional(),
  versions_created: z.number().nullable().optional(),
  families_touched: z.number().nullable().optional(),
  graph_extractions: z.number().nullable().optional(),
  entities_extracted: z.number().nullable().optional(),
  obligations_extracted: z.number().nullable().optional(),
  stakeholders_extracted: z.number().nullable().optional(),
  documents_persisted: z.number().nullable().optional(),
  rag_jobs_enqueued: z.number().nullable().optional(),
  rag_jobs_completed: z.number().nullable().optional(),
  rag_jobs_failed: z.number().nullable().optional(),
  rag_ready_documents: z.number().nullable().optional(),
  chunks_indexed: z.number().nullable().optional(),
  rag_indexed: z.number().nullable().optional(),
});

export const crawlRunListSchema = z.array(crawlRunSchema);

export const crawlRunSummarySchema = z.object({
  runs_today: z.coerce.number().default(0),
  queued: z.coerce.number().default(0),
  running: z.coerce.number().default(0),
  success: z.coerce.number().default(0),
  partial: z.coerce.number().default(0),
  failed: z.coerce.number().default(0),
});

/** Per-page result for one crawl run, derived from discovery audit + errors. */
export const crawlRunPageResultSchema = z.looseObject({
  page_id: z.number().nullable().optional(),
  page_name: z.string(),
  page_url: z.string().nullable().optional(),
  page_type: z.string().nullable().optional(),
  priority: z.coerce.number().nullable().optional(),
  enabled: z.boolean().nullable().optional(),
  source_code: z.string().nullable().optional(),
  source_name: z.string().nullable().optional(),
  documents_discovered: z.coerce.number().default(0),
  documents_accepted: z.coerce.number().default(0),
  documents_with_content: z.coerce.number().default(0),
  first_seen_at: z.string().nullable().optional(),
  last_seen_at: z.string().nullable().optional(),
  errors: z.array(z.record(z.string(), z.unknown())).default([]),
  status: z.enum(["success", "failed", "no_documents"]).default("no_documents"),
});

export const crawlRunPageResultListSchema = z.array(crawlRunPageResultSchema);

export const crawlRunSourceOptionSchema = z.object({
  code: z.string(),
  name: z.string().nullable().optional(),
});

export const crawlRunSourceOptionListSchema = z.array(crawlRunSourceOptionSchema);

export const adminCrawlRunSchema = crawlRunSchema.extend({
  source_codes: z.array(z.string()).default([]),
});

export const adminCrawlRunPageResponseSchema = paginated(adminCrawlRunSchema).extend({
  summary: crawlRunSummarySchema.default({
    runs_today: 0,
    queued: 0,
    running: 0,
    success: 0,
    partial: 0,
    failed: 0,
  }),
});

export const crawlTriggerResponseSchema = z.looseObject({
  run_id: z.coerce.number(),
  status: z.string(),
  sources_attempted: z.coerce.number().default(0),
  pages_attempted: z.coerce.number().default(0),
  sources_succeeded: z.coerce.number().default(0),
  pages_succeeded: z.coerce.number().default(0),
  docs_found: z.coerce.number().default(0),
  primary_docs_found: z.coerce.number().default(0),
  new_events: z.coerce.number().default(0),
  checkpoints_advanced: z.coerce.number().default(0),
  notification_message_id: z.string().nullable().optional(),
  errors: z.array(z.record(z.string(), z.unknown())).default([]),
});

export const sourceHealthSchema = z.looseObject({
  id: z.number(),
  code: z.string(),
  name: z.string(),
  jurisdiction: jurisdictionSchema,
  url: z.string(),
  crawler_type: z.enum(["digest", "agent", "static"]),
  allowed_domains: z.array(z.string()).default([]),
  enabled: z.boolean(),
  last_checked_at: z.string().nullable().optional(),
  last_status: z.number().nullable().optional(),
  consecutive_failures: z.coerce.number().default(0),
});

export const sourceHealthListSchema = z.array(sourceHealthSchema);

/** Server-side paging envelope shared by the admin list endpoints. */
function paginated<S extends z.ZodType>(item: S) {
  return z.object({
    items: z.array(item),
    total: z.coerce.number().default(0),
    page: z.coerce.number().default(1),
    page_size: z.coerce.number().default(20),
    total_pages: z.coerce.number().default(0),
  });
}

/** Source row enriched with the page counts the registry lateral provides. */
export const adminSourceSchema = sourceHealthSchema.extend({
  page_count: z.coerce.number().default(0),
  enabled_page_count: z.coerce.number().default(0),
  last_page_crawled_at: z.string().nullable().optional(),
});

export const sourceFacetsSchema = z.object({
  total: z.coerce.number().default(0),
  enabled: z.coerce.number().default(0),
  disabled: z.coerce.number().default(0),
  degraded: z.coerce.number().default(0),
  never_crawled: z.coerce.number().default(0),
});

export const adminSourcePageResponseSchema = paginated(adminSourceSchema).extend({
  facets: sourceFacetsSchema.default({
    total: 0,
    enabled: 0,
    disabled: 0,
    degraded: 0,
    never_crawled: 0,
  }),
});

export const sourcePageSchema = z.looseObject({
  id: z.number(),
  source_id: z.number(),
  source_code: z.string().optional().default(""),
  source_name: z.string().optional().default(""),
  name: z.string(),
  url: z.string(),
  page_type: z.string(),
  priority: z.coerce.number().default(100),
  enabled: z.boolean(),
  last_crawled_at: z.string().nullable().optional(),
  created_at: z.string().nullable().optional(),
  updated_at: z.string().nullable().optional(),
  deleted_at: z.string().nullable().optional(),
  deleted_by: z.string().nullable().optional(),
});

export const sourcePageListSchema = z.array(sourcePageSchema);

export const adminUserSchema = z.looseObject({
  id: z.string(),
  email: z.string().nullable().optional(),
  full_name: z.string().nullable().optional(),
  role: z.enum(["user", "admin"]),
  created_at: z.string().nullable().optional(),
  email_enabled: z.boolean().nullable().optional(),
  frequency: z.string().nullable().optional(),
  topics: z.array(z.string()).default([]),
});

export const adminUserListSchema = z.array(adminUserSchema);

export const adminUserSummarySchema = z.object({
  total: z.coerce.number().default(0),
  admins: z.coerce.number().default(0),
  users: z.coerce.number().default(0),
  email_enabled: z.coerce.number().default(0),
});

export const adminUserPageResponseSchema = paginated(adminUserSchema).extend({
  summary: adminUserSummarySchema.default({
    total: 0,
    admins: 0,
    users: 0,
    email_enabled: 0,
  }),
});

export const sourcePageCheckpointSchema = z.looseObject({
  source_page_id: z.number(),
  source_code: z.string(),
  source_name: z.string(),
  source_page: z.string(),
  source_page_url: z.string(),
  checkpoint_title: z.string().nullable().optional(),
  checkpoint_url: z.string().nullable().optional(),
  checkpoint_source_record_id: z.string().nullable().optional(),
  checkpoint_issue_date: z.string().nullable().optional(),
  checkpoint_published_at: z.string().nullable().optional(),
  lookback_count: z.number().nullable().optional(),
  last_successful_run_id: z.number().nullable().optional(),
  last_successful_at: z.string().nullable().optional(),
  updated_at: z.string().nullable().optional(),
});

export const sourcePageCheckpointListSchema = z.array(sourcePageCheckpointSchema);

export const adminDocumentSchema = z.looseObject({
  id: z.number(),
  title: z.string(),
  source_url: z.string(),
  issuing_body: z.string().nullable().optional(),
  jurisdiction: jurisdictionSchema.nullable().optional(),
  issue_date: z.string().nullable().optional(),
  issue_date_precision: z.string().nullable().optional(),
  doc_type: z.string().nullable().optional(),
  first_seen_at: z.string().nullable().optional(),
  last_seen_at: z.string().nullable().optional(),
  source_code: z.string().nullable().optional(),
  source_name: z.string().nullable().optional(),
  latest_version_id: z.number().nullable().optional(),
  file_hash: z.string().nullable().optional(),
  content_hash: z.string().nullable().optional(),
  fetched_at: z.string().nullable().optional(),
  family_id: z.number().nullable().optional(),
  family_title: z.string().nullable().optional(),
});

export const adminDocumentListSchema = z.array(adminDocumentSchema);

export const adminEventSchema = z.looseObject({
  id: z.number(),
  event_type: z.string(),
  detected_at: z.string(),
  suppressed: z.boolean().default(false),
  raw_summary: z.string().nullable().optional(),
  topic_tags: z.array(z.string()).default([]),
  document_id: z.number(),
  title: z.string(),
  source_url: z.string(),
  issuing_body: z.string().nullable().optional(),
  issue_date: z.string().nullable().optional(),
  source_code: z.string().nullable().optional(),
  quality_score: z.number().nullable().optional(),
  quality_category: z.string().nullable().optional(),
  significance_score: z.number().nullable().optional(),
  significance_category: z.string().nullable().optional(),
  actionability: z.string().nullable().optional(),
  rejection_reason: z.string().nullable().optional(),
});

export const adminEventListSchema = z.array(adminEventSchema);

export const adminFamilySchema = z.looseObject({
  family_id: z.string(),
  canonical_title: z.string(),
  issuer: z.string().nullable().optional(),
  document_type: z.string().nullable().optional(),
  first_seen_at: z.string().nullable().optional(),
  latest_version_id: z.string().nullable().optional(),
  created_at: z.string().nullable().optional(),
  updated_at: z.string().nullable().optional(),
  document_count: z.coerce.number().default(0),
  version_count: z.coerce.number().default(0),
  deadline_count: z.coerce.number().default(0),
});

export const adminFamilyListSchema = z.array(adminFamilySchema);

export const adminAnalyticsSchema = z.looseObject({
  sources: z.coerce.number().optional(),
  pages: z.coerce.number().optional(),
  events: z.coerce.number().optional(),
  documents: z.coerce.number().optional(),
  families: z.coerce.number().optional(),
  checkpoints: z.coerce.number().optional(),
  candidates: z.coerce.number().optional(),
  accepted_candidates: z.coerce.number().optional(),
  rejected_candidates: z.coerce.number().optional(),
  acceptance_rate: z.coerce.number().optional(),
  runtime_reduction: z.number().nullable().optional(),
  download_reduction: z.number().nullable().optional(),
  latest_runs: z.array(z.looseObject({})).optional(),
  rejected_reasons: z
    .array(
      z.looseObject({
        reason_code: z.string().nullable().optional(),
        count: z.coerce.number().default(0),
      }),
    )
    .optional(),
});

export const ragStatusSchema = z.looseObject({
  chunks: z.coerce.number().default(0),
  embeddings: z.coerce.number().default(0),
  ready: z.coerce.number().default(0),
  failed: z.coerce.number().default(0),
  pending_jobs: z.coerce.number().default(0),
  failed_jobs: z.coerce.number().default(0),
  embedding_provider: z.record(z.string(), z.unknown()).default({}),
  vector_store: z.record(z.string(), z.unknown()).default({}),
});

export const ragQueueJobSchema = z.looseObject({
  job_id: z.coerce.number(),
  document_id: z.coerce.number(),
  version_id: z.coerce.number().nullable().optional(),
  status: z.string(),
  attempts: z.coerce.number().default(0),
  last_error: z.string().nullable().optional(),
  created_at: z.string().nullable().optional(),
  updated_at: z.string().nullable().optional(),
});

export const ragQueueSchema = z.array(ragQueueJobSchema);

export const ragDocumentChunkStatusSchema = z.looseObject({
  document_id: z.coerce.number(),
  title: z.string(),
  status: z.string(),
  chunk_count: z.coerce.number().default(0),
  embedded_chunk_count: z.coerce.number().default(0),
  provider: z.string().nullable().optional(),
  model: z.string().nullable().optional(),
  error: z.string().nullable().optional(),
});

export const ragDocumentChunkStatusListSchema = z.array(ragDocumentChunkStatusSchema);

export const ragProcessResultSchema = z.looseObject({
  processed: z.coerce.number().default(0),
  completed: z.coerce.number().default(0),
  failed: z.coerce.number().default(0),
  requeued: z.coerce.number().optional(),
  enqueued: z.coerce.number().optional(),
  errors: z.array(z.unknown()).default([]),
});

export const ragRetrievalHitSchema = z.looseObject({
  source: z.string(),
  document_id: z.coerce.number(),
  version_id: z.coerce.number().nullable().optional(),
  family_id: z.coerce.number().nullable().optional(),
  chunk_id: z.coerce.number().nullable().optional(),
  title: z.string(),
  source_url: z.string(),
  final_score: z.coerce.number().default(0),
  vector_score: z.coerce.number().default(0),
  keyword_score: z.coerce.number().default(0),
  graph_score: z.coerce.number().default(0),
  metadata: z.record(z.string(), z.unknown()).default({}),
});

export const ragRetrievalPreviewSchema = z.looseObject({
  intent: z.string().optional(),
  retrieval_latency_ms: z.coerce.number().default(0),
  hits: z.array(ragRetrievalHitSchema).default([]),
  citations: z.array(ragCitationSchema).default([]),
  related_questions: z.array(z.string()).default([]),
  estimated_tokens: z.coerce.number().optional(),
  context: z.string().optional(),
  system_prompt: z.string().optional(),
  user_prompt: z.string().optional(),
});

export const ragVectorSearchSchema = z.array(ragRetrievalHitSchema);

export const systemDocumentSchema = z.looseObject({
  slug: z.string(),
  title: z.string(),
  category: z.string(),
  content_md: z.string().optional(),
});

export const systemDocumentListSchema = z.array(systemDocumentSchema);

/* ---------------- Inferred types ---------------- */

export type SummaryPayload = z.infer<typeof summaryPayloadSchema>;
export type DigestEvent = z.infer<typeof digestEventSchema>;
export type DigestResponse = z.infer<typeof digestResponseSchema>;
export type SubscriptionSettings = z.infer<typeof subscriptionSettingsSchema>;
export type SourceCatalogItem = z.infer<typeof sourceCatalogItemSchema>;
export type HealthResponse = z.infer<typeof healthResponseSchema>;
export type ChatHistoryItem = z.infer<typeof chatHistoryItemSchema>;
export type ChatResponse = z.infer<typeof chatResponseSchema>;
export type RagCitation = z.infer<typeof ragCitationSchema>;
export type SourceHealth = z.infer<typeof sourceHealthSchema>;
export type AdminSource = z.infer<typeof adminSourceSchema>;
export type AdminSourcePageResponse = z.infer<typeof adminSourcePageResponseSchema>;
export type SourceFacets = z.infer<typeof sourceFacetsSchema>;
export type AdminCrawlRun = z.infer<typeof adminCrawlRunSchema>;
export type AdminCrawlRunPageResponse = z.infer<
  typeof adminCrawlRunPageResponseSchema
>;
export type CrawlRunSummary = z.infer<typeof crawlRunSummarySchema>;
export type CrawlRunPageResult = z.infer<typeof crawlRunPageResultSchema>;
export type CrawlRunSourceOption = z.infer<typeof crawlRunSourceOptionSchema>;
export type AdminUserPageResponse = z.infer<typeof adminUserPageResponseSchema>;
export type AdminUserSummary = z.infer<typeof adminUserSummarySchema>;
export type SourcePage = z.infer<typeof sourcePageSchema>;
export type AdminUser = z.infer<typeof adminUserSchema>;
export type SourcePageCheckpoint = z.infer<typeof sourcePageCheckpointSchema>;
export type AdminDocument = z.infer<typeof adminDocumentSchema>;
export type AdminEvent = z.infer<typeof adminEventSchema>;
export type AdminFamily = z.infer<typeof adminFamilySchema>;
export type AdminAnalytics = z.infer<typeof adminAnalyticsSchema>;
export type RagStatus = z.infer<typeof ragStatusSchema>;
export type RagQueueJob = z.infer<typeof ragQueueJobSchema>;
export type RagDocumentChunkStatus = z.infer<typeof ragDocumentChunkStatusSchema>;
export type RagProcessResult = z.infer<typeof ragProcessResultSchema>;
export type RagRetrievalHit = z.infer<typeof ragRetrievalHitSchema>;
export type RagRetrievalPreview = z.infer<typeof ragRetrievalPreviewSchema>;
export type CrawlRun = z.infer<typeof crawlRunSchema>;
export type CrawlTriggerResponse = z.infer<typeof crawlTriggerResponseSchema>;
export type IntelligenceDeadline = z.infer<typeof intelligenceDeadlineSchema>;
export type IntelligenceObligation = z.infer<typeof intelligenceObligationSchema>;
export type StakeholderObligationGroup = z.infer<typeof stakeholderObligationGroupSchema>;
export type IntelligenceDocumentRef = z.infer<typeof intelligenceDocumentRefSchema>;
export type StakeholderIntelligence = z.infer<typeof stakeholderIntelligenceSchema>;
export type IntelligenceReadiness = z.infer<typeof intelligenceReadinessSchema>;
export type SystemDocument = z.infer<typeof systemDocumentSchema>;
