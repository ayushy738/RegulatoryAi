import { z } from "zod";

const capabilitySchema = z.enum([
  "intent_classifier",
  "entity_resolver",
  "regulatory_retriever",
  "knowledge_graph",
  "timeline_builder",
  "news_retriever",
  "general_ai",
  "citation_verifier",
  "response_composer",
  "follow_up_generator",
]);

const retryableCapabilities = new Set([
  "regulatory_retriever",
  "news_retriever",
  "general_ai",
  "citation_verifier",
]);
const retryableTerminalStates = new Set([
  "timed_out",
  "unavailable",
  "invalid_output",
]);
const safeLocalTarget = (value: string) =>
  value.startsWith("/") &&
  !value.startsWith("//") &&
  !value.includes("\\") &&
  !/\s/.test(value);
const unique = (values: readonly string[]) => new Set(values).size === values.length;

export const askDegradationActionSchema = z
  .strictObject({
    action: z.enum([
      "retry_official_search",
      "refresh_live_sources",
      "retry_explanation",
      "retry_citation_verification",
      "search_official_documents_manually",
      "clarify_request",
      "choose_entity",
    ]),
    kind: z.enum(["capability_retry", "navigate", "provide_input"]),
    label: z.string().trim().min(1).max(100),
    target: z.string().trim().min(1).max(2_000),
    capability: capabilitySchema.nullable(),
  })
  .superRefine((value, context) => {
    if (
      value.kind === "capability_retry" &&
      (value.capability === null || !retryableCapabilities.has(value.capability))
    ) {
      context.addIssue({
        code: "custom",
        message: "Retry action requires one retryable capability",
      });
    }
    if (value.kind !== "capability_retry" && value.capability !== null) {
      context.addIssue({
        code: "custom",
        message: "Only retry actions identify a capability",
      });
    }
    if (value.kind === "navigate" && !safeLocalTarget(value.target)) {
      context.addIssue({
        code: "custom",
        message: "Navigation target must be one safe local path",
      });
    }
  });

export const askCapabilityDegradationSchema = z
  .strictObject({
    schema_version: z.literal("1"),
    policy_version: z.literal("ask-ai-capability-degradation-v1"),
    capability: capabilitySchema,
    terminal_state: z.enum([
      "satisfied",
      "partial",
      "no_match",
      "ambiguous",
      "contradictory",
      "timed_out",
      "unavailable",
      "invalid_output",
      "superseded",
      "cancelled",
      "skipped",
    ]),
    signal: z.enum([
      "partial",
      "healthy_no_match",
      "ambiguous",
      "timed_out",
      "unavailable",
      "invalid_output",
      "evidence_rejected",
      "claim_rejected",
      "all_claims_rejected",
    ]),
    visible: z.boolean(),
    severity: z
      .enum(["information", "limited", "unavailable", "needs_input"])
      .nullable(),
    title: z.string().trim().min(1).max(200).nullable(),
    body: z.string().trim().min(1).max(2_000).nullable(),
    confidence_effect: z.enum(["unchanged", "limited", "unknown"]),
    safe_notice_code: z.string().regex(/^[A-Z][A-Z0-9_]{0,99}$/),
    affected_section_ids: z.array(z.string().trim().min(1)).refine(unique),
    unaffected_section_ids: z.array(z.string().trim().min(1)).refine(unique),
    preserved_artifact_ids: z.array(z.string().trim().min(1)).refine(unique),
    actions: z.array(askDegradationActionSchema),
  })
  .superRefine((value, context) => {
    const hasPresentation =
      value.severity !== null ||
      value.title !== null ||
      value.body !== null ||
      value.actions.length > 0;
    if (
      (value.visible &&
        (value.severity === null || value.title === null || value.body === null)) ||
      (!value.visible && hasPresentation)
    ) {
      context.addIssue({
        code: "custom",
        message: "Degradation visibility and presentation must agree",
      });
    }
    if (
      value.affected_section_ids.some((item) =>
        value.unaffected_section_ids.includes(item),
      )
    ) {
      context.addIssue({
        code: "custom",
        message: "Affected and unaffected sections must remain disjoint",
      });
    }
    if (new Set(value.actions.map((item) => item.action)).size !== value.actions.length) {
      context.addIssue({ code: "custom", message: "Actions must be unique" });
    }
    for (const action of value.actions) {
      if (
        action.kind === "capability_retry" &&
        (action.capability !== value.capability ||
          !retryableTerminalStates.has(value.terminal_state))
      ) {
        context.addIssue({
          code: "custom",
          message: "Retry action crossed its failed capability",
        });
      }
    }
  });

export type AskDegradationAction = z.infer<typeof askDegradationActionSchema>;
export type AskCapabilityDegradation = z.infer<
  typeof askCapabilityDegradationSchema
>;
