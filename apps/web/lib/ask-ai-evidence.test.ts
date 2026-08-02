import { describe, expect, it } from "vitest";

import evidenceContract from "../../api/backend/tests/fixtures/ask_evidence_contract.json";
import {
  askCitationDetailSchema,
  askFeedbackRequestSchema,
  askFeedbackSchema,
  askMessageEvidenceSchema,
  askMessageSourcesSchema,
  askSavedItemCreateRequestSchema,
  askSavedItemListSchema,
  askSavedItemSchema,
} from "./ask-ai-evidence";

describe("Ask AI evidence contracts", () => {
  it("parses exact message evidence and source artifacts", () => {
    expect(askMessageEvidenceSchema.parse(evidenceContract.message_response)).toEqual(
      evidenceContract.message_response,
    );
    expect(askMessageSourcesSchema.parse(evidenceContract.sources_response)).toEqual(
      evidenceContract.sources_response,
    );
  });

  it("parses version-specific feedback request and response contracts", () => {
    expect(askFeedbackRequestSchema.parse(evidenceContract.feedback_request)).toEqual(
      evidenceContract.feedback_request,
    );
    expect(askFeedbackSchema.parse(evidenceContract.feedback_response)).toEqual(
      evidenceContract.feedback_response,
    );
  });

  it("parses saved-item request, response, and list contracts", () => {
    expect(
      askSavedItemCreateRequestSchema.parse(evidenceContract.saved_item_request),
    ).toEqual(evidenceContract.saved_item_request);
    expect(askSavedItemSchema.parse(evidenceContract.saved_item_response)).toEqual(
      evidenceContract.saved_item_response,
    );
    const list = {
      schema_version: "1",
      items: [evidenceContract.saved_item_response],
    };
    expect(askSavedItemListSchema.parse(list)).toEqual(list);
  });

  it("parses the owner-scoped citation restoration contract", () => {
    const citationDetail = {
      schema_version: "1",
      message_id: evidenceContract.message_response.message.id,
      response_version: 2,
      claim_id: "99999999-9999-4999-8999-999999999999",
      claim_key: "claim-1",
      claim_ordinal: 0,
      claim_text: "The consultation deadline changed.",
      support_status: "supported",
      support_score: 0.98,
      citation_id: "88888888-8888-4888-8888-888888888888",
      evidence_key: "evidence-1",
      citation_ordinal: 0,
      marker: "[1]",
      verification_status: "supported",
      verifier_provider: "contract-verifier",
      verifier_version: "verifier-1",
      verifier_model: "model-1",
      verifier_prompt_version: "prompt-1",
      verifier_policy_version: "ask-ai-claim-verifier-v1",
      verification_latency_ms: 125,
      verification: {
        outcome: "supported",
        confidence: 0.98,
        publication_mode: "evidence_only",
        final_claim_text: "The consultation deadline changed.",
        terminal_reason: "CLAIM_VERIFIER_RELEASE_NOT_APPROVED",
        latency_ms: 125,
        evidence_ids: ["evidence-1"],
        correction_applied: false,
        verifier_identity: {
          provider: "contract-verifier",
          verifier_version: "verifier-1",
          model_version: "model-1",
          prompt_version: "prompt-1",
          policy_version: "ask-ai-claim-verifier-v1",
        },
      },
      provenance: { knowledge_mode: "grounded_regulatory" },
      confidence_result: { score: 0.98 },
      source: {
        id: "66666666-6666-4666-8666-666666666666",
        ordinal: 0,
        source_key: "official:consultation",
        source_class: "official",
        source_type: "regulation",
        document_id: 91,
        document_version_id: 92,
        chunk_id: 93,
        graph_reference: null,
        title_snapshot: "Consultation regulation",
        url_snapshot: "https://official.example.test/consultation",
        issuer_snapshot: "Regulator",
        publisher_snapshot: null,
        jurisdiction_snapshot: "central",
        published_at: "2026-07-27T08:30:00Z",
        retrieved_at: "2026-07-27T09:04:00Z",
        evidence_snapshot: "Responses are due by 31 August.",
        locator_snapshot: "paragraph 4",
        content_hash: "sha256:contract",
        metadata: { language: "en" },
        created_at: "2026-07-27T09:04:00Z",
      },
      current_source_status: "current",
    } as const;

    expect(askCitationDetailSchema.parse(citationDetail)).toEqual(citationDetail);
  });
});
