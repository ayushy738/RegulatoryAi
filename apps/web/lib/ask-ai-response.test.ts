import { describe, expect, it } from "vitest";

import responseContract from "../../api/backend/tests/fixtures/ask_response_contract.json";
import {
  askCardActionSchema,
  askCardActionTypeValues,
  askResponseCardTypeValues,
  askResponseStrategyValues,
  askStructuredResponseSchema,
} from "./ask-ai-response";

describe("Ask AI structured response contracts", () => {
  it("parses the exact shared backend fixture", () => {
    expect(askStructuredResponseSchema.parse(responseContract)).toEqual(
      responseContract,
    );
  });

  it("freezes every response strategy and known card type", () => {
    expect(askResponseStrategyValues).toEqual([
      "definition_card",
      "entity_intelligence_page",
      "official_documents_overview",
      "deadline_cards_timeline",
      "stakeholder_cards",
      "comparison_table",
      "latest_intelligence",
      "timeline",
      "compliance_checklist",
      "executive_summary",
      "document_explanation",
      "amendment_cards",
      "consultation_deadline_cards",
      "conversation",
      "research_report",
    ]);
    expect(askResponseCardTypeValues).toEqual([
      "answer_summary",
      "definition",
      "official_source",
      "live_news",
      "obligation",
      "deadline",
      "timeline_event",
      "amendment",
      "comparison",
      "stakeholder",
      "related_regulation",
      "confidence_coverage",
    ]);
    expect(
      new Set(
        responseContract.sections.flatMap((section) =>
          section.cards.flatMap((card) =>
            card.known_type === null ? [] : [card.known_type],
          ),
        ),
      ),
    ).toEqual(new Set(askResponseCardTypeValues));
  });

  it("preserves unknown future cards only through explicit fallback", () => {
    const unknown = responseContract.sections[0].cards.at(-1);
    expect(unknown).toMatchObject({
      card_type: "regulatory_heatmap",
      known_type: null,
      rendering: "unknown_fallback",
      fallback_title: "Unsupported card",
    });
    const invalid = structuredClone(responseContract);
    invalid.sections[0].cards[11].rendering = "known" as "unknown_fallback";
    expect(askStructuredResponseSchema.safeParse(invalid).success).toBe(false);
  });

  it("rejects extra fields, noncontiguous order, and provenance crossing", () => {
    const extra = {
      ...responseContract,
      unexpected: true,
    };
    expect(askStructuredResponseSchema.safeParse(extra).success).toBe(false);

    const gapped = structuredClone(responseContract);
    gapped.sections[1].order = 3;
    expect(askStructuredResponseSchema.safeParse(gapped).success).toBe(false);

    const crossed = structuredClone(responseContract);
    crossed.sections[1].cards[0].provenance_class =
      "internal_regulatory_corpus" as "live_web_sources";
    expect(askStructuredResponseSchema.safeParse(crossed).success).toBe(false);
  });

  it("requires honest action availability metadata", () => {
    expect(askCardActionTypeValues).toContain("find_official_basis");
    expect(
      askCardActionSchema.safeParse({
        action: "open_source",
        state: "available",
        target: null,
        disabled_reason_code: null,
      }).success,
    ).toBe(false);
    expect(
      askCardActionSchema.safeParse({
        action: "add_to_tracker",
        state: "disabled",
        target: null,
        disabled_reason_code: "FUTURE_PHASE",
      }).success,
    ).toBe(true);
  });
});
