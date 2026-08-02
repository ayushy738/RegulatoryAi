import { z } from "zod";

import {
  askCardEvidenceReferenceSchema,
  type AskCardEvidenceReference,
} from "./ask-ai-compliance-cards";
import {
  askStructuredDateFieldSchema,
  askStructuredTextFieldSchema,
} from "./ask-ai-core-cards";

const unique = (values: readonly string[]) =>
  new Set(values).size === values.length;

const awareTimestamp = z.string().datetime({ offset: true });

const officialReferencesSchema = z
  .array(askCardEvidenceReferenceSchema)
  .superRefine((items, context) => {
    if (!unique(items.map((item) => item.citation_id))) {
      context.addIssue({ code: "custom", message: "Citation IDs must be unique" });
    }
    if (!unique(items.map((item) => `${item.claim_id}:${item.source_id}`))) {
      context.addIssue({ code: "custom", message: "Evidence pairs must be unique" });
    }
  });

const safeHttpsUrl = z.string().trim().max(4_000).refine((value) => {
  try {
    const parsed = new URL(value);
    return (
      parsed.protocol === "https:" &&
      Boolean(parsed.hostname) &&
      parsed.username === "" &&
      parsed.password === ""
    );
  } catch {
    return false;
  }
});

export const askLiveSourceReferenceSchema = z
  .strictObject({
    claim_id: z.string().trim().min(1).max(200),
    source_id: z.string().trim().min(1).max(200),
    publisher: z.string().trim().min(1).max(500),
    source_type: z.string().trim().min(1).max(200),
    publication_at: awareTimestamp,
    retrieved_at: awareTimestamp,
    ui_badge: z.string().trim().min(1).max(200),
    attribution: z.string().trim().min(1).max(500),
    url: safeHttpsUrl,
  })
  .superRefine((value, context) => {
    if (Date.parse(value.retrieved_at) < Date.parse(value.publication_at)) {
      context.addIssue({
        code: "custom",
        message: "Live retrieval cannot precede publication",
      });
    }
  });

export const askTimelineEventCardPayloadSchema = z
  .strictObject({
    schema_version: z.literal("1"),
    date: askStructuredDateFieldSchema,
    event_type: askStructuredTextFieldSchema,
    event_title: askStructuredTextFieldSchema,
    significance: askStructuredTextFieldSchema,
    origin: z.enum(["official", "live"]),
    source_label: askStructuredTextFieldSchema,
    related_prior_event_id: z.string().trim().min(1).max(200).nullable(),
    related_next_event_id: z.string().trim().min(1).max(200).nullable(),
    official_evidence_references: officialReferencesSchema,
    live_source: askLiveSourceReferenceSchema.nullable(),
  })
  .superRefine((value, context) => {
    if (
      (value.origin === "official" &&
        (value.official_evidence_references.length === 0 || value.live_source)) ||
      (value.origin === "live" &&
        (!value.live_source || value.official_evidence_references.length > 0))
    ) {
      context.addIssue({ code: "custom", message: "Timeline origin is invalid" });
    }
    if (
      value.related_prior_event_id !== null &&
      value.related_prior_event_id === value.related_next_event_id
    ) {
      context.addIssue({ code: "custom", message: "Timeline relations must differ" });
    }
  });

export const askAmendmentCardPayloadSchema = z.strictObject({
  schema_version: z.literal("1"),
  amending_instrument: askStructuredTextFieldSchema,
  amended_instrument: askStructuredTextFieldSchema,
  issue_date: askStructuredDateFieldSchema,
  effective_date: askStructuredDateFieldSchema,
  provisions_affected: z.array(z.string().trim().min(1)).refine(unique),
  change_summary: askStructuredTextFieldSchema,
  stakeholders_affected: z.array(z.string().trim().min(1)).refine(unique),
  amending_source_id: z.string().trim().min(1).max(200).nullable(),
  amended_source_id: z.string().trim().min(1).max(200).nullable(),
  evidence_references: officialReferencesSchema,
});

export const askComparisonDimensionSchema = z
  .strictObject({
    dimension: z.string().trim().min(1).max(500),
    side_a: askStructuredTextFieldSchema,
    side_b: askStructuredTextFieldSchema,
    relationship_or_difference: askStructuredTextFieldSchema,
    side_a_evidence_references: officialReferencesSchema,
    side_b_evidence_references: officialReferencesSchema,
  })
  .superRefine((value, context) => {
    const sideACitations = new Set(
      value.side_a_evidence_references.map((item) => item.citation_id),
    );
    if (
      value.side_b_evidence_references.some((item) =>
        sideACitations.has(item.citation_id),
      )
    ) {
      context.addIssue({
        code: "custom",
        message: "Comparison sides require independent citations",
      });
    }
    for (const [field, references] of [
      [value.side_a, value.side_a_evidence_references],
      [value.side_b, value.side_b_evidence_references],
    ] as const) {
      if ((field.state === "established") !== (references.length > 0)) {
        context.addIssue({
          code: "custom",
          message: "Each comparison side requires independent evidence",
        });
      }
    }
  });

export const askComparisonCardPayloadSchema = z
  .strictObject({
    schema_version: z.literal("1"),
    side_a_label: z.string().trim().min(1).max(500),
    side_b_label: z.string().trim().min(1).max(500),
    dimensions: z.array(askComparisonDimensionSchema).min(1),
  })
  .superRefine((value, context) => {
    if (!unique(value.dimensions.map((item) => item.dimension))) {
      context.addIssue({ code: "custom", message: "Dimensions must be unique" });
    }
  });

export const askLiveNewsCardPayloadSchema = z.strictObject({
  schema_version: z.literal("1"),
  headline: z.string().trim().min(1).max(1_000),
  relevance_explanation: z.string().trim().min(1).max(2_000),
  live_source: askLiveSourceReferenceSchema,
});

export const askRelatedRegulationCardPayloadSchema = z.strictObject({
  schema_version: z.literal("1"),
  related_entity_or_document: askStructuredTextFieldSchema,
  related_entity_id: z.string().trim().min(1).max(200).nullable(),
  relationship_type: askStructuredTextFieldSchema,
  explanation: askStructuredTextFieldSchema,
  provenance_label: askStructuredTextFieldSchema,
  evidence_references: officialReferencesSchema,
});

export type AskLiveSourceReference = z.infer<typeof askLiveSourceReferenceSchema>;
export type AskTimelineEventCardPayload = z.infer<typeof askTimelineEventCardPayloadSchema>;
export type AskAmendmentCardPayload = z.infer<typeof askAmendmentCardPayloadSchema>;
export type AskComparisonCardPayload = z.infer<typeof askComparisonCardPayloadSchema>;
export type AskLiveNewsCardPayload = z.infer<typeof askLiveNewsCardPayloadSchema>;
export type AskRelatedRegulationCardPayload = z.infer<typeof askRelatedRegulationCardPayloadSchema>;

type ChangeEnvelope = {
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

type Payload =
  | AskTimelineEventCardPayload
  | AskAmendmentCardPayload
  | AskComparisonCardPayload
  | AskLiveNewsCardPayload
  | AskRelatedRegulationCardPayload;

const schemas = {
  timeline_event: askTimelineEventCardPayloadSchema,
  amendment: askAmendmentCardPayloadSchema,
  comparison: askComparisonCardPayloadSchema,
  live_news: askLiveNewsCardPayloadSchema,
  related_regulation: askRelatedRegulationCardPayloadSchema,
};

export function changeCardValidationErrors(value: ChangeEnvelope) {
  if (!(value.card_type in schemas)) return [];
  const schema = schemas[value.card_type as keyof typeof schemas];
  const result = schema.safeParse(value.payload);
  if (!result.success) return [`Invalid ${value.card_type} payload`];
  const payload = result.data as Payload;
  const errors: string[] = [];
  if (value.confidence === null) {
    errors.push("Change and intelligence cards require confidence");
    return errors;
  }
  const live =
    value.card_type === "live_news" ||
    (value.card_type === "timeline_event" &&
      (payload as AskTimelineEventCardPayload).origin === "live");
  if (
    value.knowledge_mode !== (live ? "live_intelligence" : "grounded_regulatory") ||
    value.provenance_class !== (live ? "live_web_sources" : "internal_regulatory_corpus")
  ) {
    errors.push("Change card mode and provenance do not match its source lane");
  }
  const identity = identities(value.card_type, payload);
  if (!sameSet(identity.claims, value.claim_ids) || !sameSet(identity.sources, value.source_ids)) {
    errors.push("Change card evidence must match envelope references");
  }
  const incomplete = isIncomplete(value.card_type, payload);
  if (value.state === "ready" && incomplete) {
    errors.push("Ready change cards require all frozen fields");
  } else if (value.state === "partial" && (!incomplete || identity.sources.length === 0)) {
    errors.push("Partial change cards require evidence and visible gaps");
  } else if (!(["ready", "partial"] as const).includes(value.state as "ready" | "partial")) {
    errors.push("Change cards support only Ready or Partial state");
  } else if (value.state === "partial" && value.confidence.label === "high") {
    errors.push("Partial change cards cannot be High confidence");
  }
  validateActions(value, payload, identity.citations, errors);
  return errors;
}

function identities(cardType: string, payload: Payload) {
  const official: AskCardEvidenceReference[] = [];
  const live: AskLiveSourceReference[] = [];
  if (cardType === "timeline_event") {
    const item = payload as AskTimelineEventCardPayload;
    official.push(...item.official_evidence_references);
    if (item.live_source) live.push(item.live_source);
  } else if (cardType === "amendment") {
    official.push(...(payload as AskAmendmentCardPayload).evidence_references);
  } else if (cardType === "comparison") {
    for (const dimension of (payload as AskComparisonCardPayload).dimensions) {
      official.push(...dimension.side_a_evidence_references, ...dimension.side_b_evidence_references);
    }
  } else if (cardType === "live_news") {
    live.push((payload as AskLiveNewsCardPayload).live_source);
  } else {
    official.push(...(payload as AskRelatedRegulationCardPayload).evidence_references);
  }
  return {
    claims: [...new Set([...official, ...live].map((item) => item.claim_id))],
    sources: [...new Set([...official, ...live].map((item) => item.source_id))],
    citations: new Set(official.map((item) => item.citation_id)),
  };
}

function isIncomplete(cardType: string, payload: Payload) {
  const missing = (field: { state: string }) => field.state === "not_established";
  if (cardType === "timeline_event") {
    const item = payload as AskTimelineEventCardPayload;
    return [item.date, item.event_type, item.event_title, item.significance, item.source_label].some(missing);
  }
  if (cardType === "amendment") {
    const item = payload as AskAmendmentCardPayload;
    return [item.amending_instrument, item.amended_instrument, item.issue_date, item.effective_date, item.change_summary].some(missing) || item.provisions_affected.length === 0 || item.stakeholders_affected.length === 0 || !item.amending_source_id || !item.amended_source_id;
  }
  if (cardType === "comparison") {
    return (payload as AskComparisonCardPayload).dimensions.some((item) => [item.side_a, item.side_b, item.relationship_or_difference].some(missing));
  }
  if (cardType === "live_news") return false;
  const item = payload as AskRelatedRegulationCardPayload;
  return [item.related_entity_or_document, item.relationship_type, item.explanation, item.provenance_label].some(missing) || !item.related_entity_id;
}

function validateActions(card: ChangeEnvelope, payload: Payload, citations: Set<string>, errors: string[]) {
  const actions = new Map(card.actions.map((item) => [item.action, item]));
  const expected = card.card_type === "timeline_event"
    ? ((payload as AskTimelineEventCardPayload).origin === "official" ? ["inspect_evidence"] : ["open_source"])
    : card.card_type === "amendment" ? ["inspect_evidence", "compare"]
    : card.card_type === "comparison" ? ["inspect_evidence"]
    : card.card_type === "live_news" ? ["open_source", "find_official_basis"]
    : ["inspect_evidence", "open_entity"];
  if (!sameSet([...actions.keys()], expected)) {
    errors.push(`${card.card_type} card actions do not match policy`);
    return;
  }
  if (actions.has("inspect_evidence") && !available(actions.get("inspect_evidence"), citations)) errors.push("Inspect evidence target is invalid");
  if (actions.has("open_source")) {
    const live = card.card_type === "live_news" ? (payload as AskLiveNewsCardPayload).live_source : (payload as AskTimelineEventCardPayload).live_source;
    if (!live || !available(actions.get("open_source"), new Set([live.url]))) errors.push("Live source target is invalid");
  }
  if (actions.has("find_official_basis") && !available(actions.get("find_official_basis"), new Set(card.claim_ids))) errors.push("Official-basis target is invalid");
  if (actions.has("compare")) {
    const item = payload as AskAmendmentCardPayload;
    const target = item.amending_source_id && item.amended_source_id ? `${item.amending_source_id}:${item.amended_source_id}` : null;
    if (!optional(actions.get("compare"), target ? new Set([target]) : new Set())) errors.push("Compare target is invalid");
  }
  if (actions.has("open_entity")) {
    const target = (payload as AskRelatedRegulationCardPayload).related_entity_id;
    if (!optional(actions.get("open_entity"), target ? new Set([target]) : new Set())) errors.push("Entity target is invalid");
  }
}

function available(action: { state: string; target: string | null } | undefined, targets: Set<string>) {
  return action?.state === "available" && action.target !== null && targets.has(action.target);
}

function optional(action: { state: string; target: string | null } | undefined, targets: Set<string>) {
  return targets.size ? available(action, targets) : action?.state === "disabled" && action.target === null;
}

function sameSet(left: readonly string[], right: readonly string[]) {
  const a = new Set(left);
  const b = new Set(right);
  return a.size === b.size && [...a].every((item) => b.has(item));
}
