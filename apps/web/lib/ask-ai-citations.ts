import { z } from "zod";

import {
  askCitationSchema,
  askClaimSchema,
  askSourceSchema,
  type AskCitation,
  type AskClaim,
  type AskSource,
} from "./ask-ai-turns";

const timestampSchema = z.iso.datetime({ offset: true });

export const askCitationSelectionSchema = z.object({
  schema_version: z.literal("1"),
  message_id: z.uuid(),
  response_version: z.number().int().positive(),
  citation_id: z.uuid(),
  claim_id: z.uuid(),
  source_id: z.uuid(),
  marker: z.string().min(1),
  claim_text: z.string().min(1),
  support_status: z.string().min(1),
  verification_status: z.string().min(1),
  support_score: z.number().min(0).max(1).nullable(),
  source_title: z.string().min(1),
  source_issuer: z.string().min(1).nullable(),
  source_type: z.string().min(1),
  source_url: z.string(),
  published_at: timestampSchema.nullable(),
  retrieved_at: timestampSchema,
  locator_snapshot: z.string().min(1).nullable(),
  evidence_snapshot: z.string().min(1),
});

export type AskCitationSelection = z.infer<
  typeof askCitationSelectionSchema
>;

export type BuildCitationSelectionInput = {
  messageId: string;
  responseVersion: number;
  citation: AskCitation | unknown;
  claim: AskClaim | unknown;
  source: AskSource | unknown;
};

export function buildCitationSelection({
  messageId,
  responseVersion,
  citation,
  claim,
  source,
}: BuildCitationSelectionInput): AskCitationSelection {
  const safeCitation = askCitationSchema.parse(citation);
  const safeClaim = askClaimSchema.parse(claim);
  const safeSource = askSourceSchema.parse(source);

  if (safeCitation.claim_id !== safeClaim.id) {
    throw new Error("Citation claim identity does not match the selected claim");
  }
  if (safeCitation.source_id !== safeSource.id) {
    throw new Error("Citation source identity does not match the selected source");
  }
  if (
    safeClaim.knowledge_mode !== "grounded_regulatory" ||
    safeCitation.claim_knowledge_mode !== "grounded_regulatory"
  ) {
    throw new Error("Inline citations require a grounded regulatory claim");
  }
  if (
    safeSource.source_class !== "official" ||
    safeCitation.source_class !== "official"
  ) {
    throw new Error("Inline claim citations require official evidence");
  }
  if (safeCitation.evidence_snapshot !== safeSource.evidence_snapshot) {
    throw new Error("Citation evidence snapshot does not match the source snapshot");
  }
  if (safeCitation.locator_snapshot !== safeSource.locator_snapshot) {
    throw new Error("Citation locator does not match the source snapshot");
  }

  return askCitationSelectionSchema.parse({
    schema_version: "1",
    message_id: messageId,
    response_version: responseVersion,
    citation_id: safeCitation.id,
    claim_id: safeClaim.id,
    source_id: safeSource.id,
    marker: safeCitation.marker ?? `[${safeCitation.ordinal + 1}]`,
    claim_text: safeClaim.claim_text,
    support_status: safeClaim.support_status,
    verification_status: safeCitation.verification_status,
    support_score: safeCitation.support_score,
    source_title: safeSource.title_snapshot,
    source_issuer: safeSource.issuer_snapshot,
    source_type: safeSource.source_type,
    source_url: safeSource.url_snapshot,
    published_at: safeSource.published_at,
    retrieved_at: safeSource.retrieved_at,
    locator_snapshot: safeSource.locator_snapshot,
    evidence_snapshot: safeSource.evidence_snapshot,
  });
}
