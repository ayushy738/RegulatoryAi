import { z } from "zod";

import {
  askStructuredDateFieldSchema,
  askStructuredTextFieldSchema,
} from "./ask-ai-core-cards";

const unique = (values: readonly string[]) =>
  new Set(values).size === values.length;

export const askCardEvidenceReferenceSchema = z.strictObject({
  citation_id: z.string().trim().min(1).max(200),
  claim_id: z.string().trim().min(1).max(200),
  source_id: z.string().trim().min(1).max(200),
  marker: z.string().trim().min(1).max(50),
  locator: askStructuredTextFieldSchema,
});

const evidenceReferencesSchema = z
  .array(askCardEvidenceReferenceSchema)
  .superRefine((items, context) => {
    if (!unique(items.map((item) => item.citation_id))) {
      context.addIssue({ code: "custom", message: "Citation IDs must be unique" });
    }
    if (!unique(items.map((item) => `${item.claim_id}:${item.source_id}`))) {
      context.addIssue({ code: "custom", message: "Evidence pairs must be unique" });
    }
  });

export const askObligationPayloadSchema = z.strictObject({
  schema_version: z.literal("1"),
  responsible_party: askStructuredTextFieldSchema,
  required_action: askStructuredTextFieldSchema,
  timing_or_frequency: askStructuredTextFieldSchema,
  trigger_or_scope: askStructuredTextFieldSchema,
  jurisdiction: askStructuredTextFieldSchema,
  official_basis: askStructuredTextFieldSchema,
  evidence_references: evidenceReferencesSchema,
});

export const askDeadlinePayloadSchema = z.strictObject({
  schema_version: z.literal("1"),
  date: askStructuredDateFieldSchema,
  deadline_type: askStructuredTextFieldSchema,
  responsible_stakeholder: askStructuredTextFieldSchema,
  status: z.enum(["upcoming", "today", "elapsed", "extended", "unverified"]),
  source_label: askStructuredTextFieldSchema,
  evidence_references: evidenceReferencesSchema,
});

export const askStakeholderPayloadSchema = z.strictObject({
  schema_version: z.literal("1"),
  stakeholder: askStructuredTextFieldSchema,
  stakeholder_entity_id: z.string().trim().min(1).max(200).nullable(),
  role: askStructuredTextFieldSchema,
  impact: askStructuredTextFieldSchema,
  obligations: z.array(z.string().trim().min(1)).refine(unique),
  relevant_regulations: z.array(z.string().trim().min(1)).refine(unique),
  jurisdiction: askStructuredTextFieldSchema,
  evidence_coverage_percent: z.number().finite().min(0).max(100),
  evidence_references: evidenceReferencesSchema,
});

export type AskObligationPayload = z.infer<typeof askObligationPayloadSchema>;
export type AskDeadlinePayload = z.infer<typeof askDeadlinePayloadSchema>;
export type AskStakeholderPayload = z.infer<typeof askStakeholderPayloadSchema>;
export type AskCardEvidenceReference = z.infer<
  typeof askCardEvidenceReferenceSchema
>;

type ComplianceCardEnvelope = {
  card_type: string;
  state: "ready" | "partial" | "not_established" | "unavailable";
  knowledge_mode: string;
  provenance_class: string;
  confidence: { label: "high" | "medium" | "low" | "unknown" } | null;
  claim_ids: string[];
  source_ids: string[];
  actions: Array<{ action: string; state: string; target: string | null }>;
  payload: Record<string, unknown>;
};

export function complianceCardValidationErrors(value: ComplianceCardEnvelope) {
  if (!["obligation", "deadline", "stakeholder"].includes(value.card_type)) {
    return [];
  }
  const errors: string[] = [];
  const parsed = parsePayload(value.card_type, value.payload);
  if (!parsed) return [`Invalid ${value.card_type} payload`];
  if (
    value.knowledge_mode !== "grounded_regulatory" ||
    value.provenance_class !== "internal_regulatory_corpus"
  ) {
    errors.push("Compliance cards require grounded official provenance");
  }
  if (value.confidence === null) {
    errors.push("Compliance cards require confidence");
    return errors;
  }
  const references = parsed.evidence_references;
  if (
    !sameSet(references.map((item) => item.claim_id), value.claim_ids) ||
    !sameSet(references.map((item) => item.source_id), value.source_ids)
  ) {
    errors.push("Compliance card evidence must match envelope references");
  }
  const incomplete = payloadIncomplete(value.card_type, parsed);
  if (value.state === "ready" && (incomplete || references.length === 0)) {
    errors.push("Ready compliance cards require complete cited fields");
  } else if (
    value.state === "partial" &&
    (!incomplete || references.length === 0)
  ) {
    errors.push("Partial compliance cards require cited missing fields");
  } else if (value.state === "partial" && value.confidence.label === "high") {
    errors.push("Partial compliance cards cannot be High confidence");
  } else if (
    value.state === "not_established" &&
    (references.length > 0 ||
      value.claim_ids.length > 0 ||
      value.source_ids.length > 0 ||
      !incomplete ||
      payloadHasEstablishedContent(value.card_type, parsed) ||
      value.confidence.label !== "unknown")
  ) {
    errors.push("Not-established compliance card state is invalid");
  } else if (value.state === "unavailable") {
    errors.push("Compliance cards cannot use unavailable state");
  }
  validateActions(value, parsed, errors);
  return errors;
}

type Payload =
  | AskObligationPayload
  | AskDeadlinePayload
  | AskStakeholderPayload;

function parsePayload(cardType: string, payload: Record<string, unknown>): Payload | null {
  const schema = {
    obligation: askObligationPayloadSchema,
    deadline: askDeadlinePayloadSchema,
    stakeholder: askStakeholderPayloadSchema,
  }[cardType as "obligation" | "deadline" | "stakeholder"];
  const result = schema.safeParse(payload);
  return result.success ? result.data : null;
}

function fieldMissing(field: { state: string }) {
  return field.state === "not_established";
}

function payloadIncomplete(cardType: string, payload: Payload) {
  if (cardType === "obligation") {
    const value = payload as AskObligationPayload;
    return [
      value.responsible_party,
      value.required_action,
      value.timing_or_frequency,
      value.trigger_or_scope,
      value.jurisdiction,
      value.official_basis,
    ].some(fieldMissing);
  }
  if (cardType === "deadline") {
    const value = payload as AskDeadlinePayload;
    return (
      fieldMissing(value.date) ||
      fieldMissing(value.deadline_type) ||
      fieldMissing(value.responsible_stakeholder) ||
      fieldMissing(value.source_label) ||
      value.status === "unverified"
    );
  }
  const value = payload as AskStakeholderPayload;
  return (
    [value.stakeholder, value.role, value.impact, value.jurisdiction].some(
      fieldMissing,
    ) ||
    value.obligations.length === 0 ||
    value.relevant_regulations.length === 0 ||
    value.evidence_coverage_percent === 0
  );
}

function payloadHasEstablishedContent(cardType: string, payload: Payload) {
  if (cardType === "obligation") {
    const value = payload as AskObligationPayload;
    return [
      value.responsible_party,
      value.required_action,
      value.timing_or_frequency,
      value.trigger_or_scope,
      value.jurisdiction,
      value.official_basis,
    ].some((field) => field.state === "established");
  }
  if (cardType === "deadline") {
    const value = payload as AskDeadlinePayload;
    return (
      value.date.state === "established" ||
      [value.deadline_type, value.responsible_stakeholder, value.source_label].some(
        (field) => field.state === "established",
      ) ||
      value.status !== "unverified"
    );
  }
  const value = payload as AskStakeholderPayload;
  return (
    [value.stakeholder, value.role, value.impact, value.jurisdiction].some(
      (field) => field.state === "established",
    ) ||
    value.obligations.length > 0 ||
    value.relevant_regulations.length > 0 ||
    value.evidence_coverage_percent > 0 ||
    value.stakeholder_entity_id !== null
  );
}

function validateActions(
  card: ComplianceCardEnvelope,
  payload: Payload,
  errors: string[],
) {
  const actions = new Map(
    card.actions.map((action) => [action.action, action] as const),
  );
  const expected = {
    obligation: ["inspect_evidence", "check_applicability"],
    deadline: ["inspect_evidence", "add_to_tracker"],
    stakeholder: ["inspect_evidence", "open_entity"],
  }[card.card_type as "obligation" | "deadline" | "stakeholder"];
  if (!sameSet([...actions.keys()], expected)) {
    errors.push(`${card.card_type} card actions do not match policy`);
    return;
  }
  const citations = new Set(payload.evidence_references.map((item) => item.citation_id));
  const inspect = actions.get("inspect_evidence");
  if (
    citations.size > 0
      ? inspect?.state !== "available" || !citations.has(inspect.target ?? "")
      : inspect?.state !== "disabled" || inspect.target !== null
  ) {
    errors.push("Inspect evidence must match card citations");
  }
  const secondary = actions.get(expected[1]);
  if (card.card_type === "deadline") {
    if (secondary?.state !== "disabled" || secondary.target !== null) {
      errors.push("Deadline tracking remains disabled in this phase");
    }
    return;
  }
  const allowed: Set<string | null> =
    card.card_type === "obligation"
      ? new Set(card.claim_ids)
      : new Set([(payload as AskStakeholderPayload).stakeholder_entity_id]);
  allowed.delete(null);
  if (
    allowed.size > 0
      ? secondary?.state !== "available" || !allowed.has(secondary.target)
      : secondary?.state !== "disabled" || secondary.target !== null
  ) {
    errors.push("Secondary compliance-card action has the wrong target");
  }
}

function sameSet(left: readonly string[], right: readonly string[]) {
  const leftSet = new Set(left);
  const rightSet = new Set(right);
  return (
    leftSet.size === rightSet.size &&
    [...leftSet].every((item) => rightSet.has(item))
  );
}
