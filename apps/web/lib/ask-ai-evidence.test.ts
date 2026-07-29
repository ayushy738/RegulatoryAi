import { describe, expect, it } from "vitest";

import evidenceContract from "../../api/backend/tests/fixtures/ask_evidence_contract.json";
import {
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
});
