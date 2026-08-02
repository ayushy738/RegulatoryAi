import responseContract from "../../api/backend/tests/fixtures/ask_response_contract.json";

import {
  askEntityCorePageSchema,
  type AskEntityCorePage,
} from "../lib/ask-ai-entity-page";
import {
  askResponseCardSchema,
  askStructuredResponseSchema,
  askStructuredResponseSectionSchema,
  type AskResponseCard,
} from "../lib/ask-ai-response";

function card(cardType: string): AskResponseCard {
  const response = askStructuredResponseSchema.parse(responseContract);
  const selected = response.sections[0]?.cards.find(
    (candidate) => candidate.card_type === cardType,
  );
  if (selected === undefined) {
    throw new Error(`Missing test card: ${cardType}`);
  }
  return structuredClone(selected);
}

function sourceCard({
  cardId,
  sourceId,
  title,
}: {
  cardId: string;
  sourceId: string;
  title: string;
}) {
  const selected = card("official_source");
  return askResponseCardSchema.parse({
    ...selected,
    card_id: cardId,
    title,
    source_ids: [sourceId],
    actions: selected.actions.map((action) =>
      ["open_source", "save"].includes(action.action)
        ? { ...action, target: sourceId }
        : action,
    ),
    payload: {
      ...selected.payload,
      source_id: sourceId,
      document_title: title,
    },
  });
}

function section({
  sectionId,
  key,
  order,
  strategy,
  title,
  selectedCard,
}: {
  sectionId: string;
  key: string;
  order: number;
  strategy: string;
  title: string;
  selectedCard: AskResponseCard;
}) {
  return askStructuredResponseSectionSchema.parse({
    schema_version: "1",
    section_id: sectionId,
    section_key: key,
    order,
    strategy,
    title,
    state: "ready",
    knowledge_mode: selectedCard.knowledge_mode,
    provenance_class: selectedCard.provenance_class,
    confidence: {
      score: 88,
      label: "high",
      reasons: ["Current official evidence supports this section."],
    },
    claim_ids: selectedCard.claim_ids,
    source_ids: selectedCard.source_ids,
    assumptions: [],
    gaps: [],
    cards: [{ ...selectedCard, order: 0 }],
  });
}

export function entityCorePageFixture(): AskEntityCorePage {
  const sections = [
    section({
      sectionId: "entity-overview",
      key: "overview",
      order: 0,
      strategy: "entity_intelligence_page",
      title: "Overview",
      selectedCard: card("answer_summary"),
    }),
    section({
      sectionId: "entity-definition",
      key: "definition",
      order: 1,
      strategy: "definition_card",
      title: "Definition",
      selectedCard: card("definition"),
    }),
    section({
      sectionId: "entity-regulations",
      key: "official_regulations",
      order: 2,
      strategy: "official_documents_overview",
      title: "Official Regulations",
      selectedCard: sourceCard({
        cardId: "card-regulation",
        sourceId: "source-regulation",
        title: "DSM Regulations",
      }),
    }),
    section({
      sectionId: "entity-documents",
      key: "official_documents",
      order: 3,
      strategy: "official_documents_overview",
      title: "Official Documents",
      selectedCard: sourceCard({
        cardId: "card-document",
        sourceId: "source-document",
        title: "DSM Official Order",
      }),
    }),
    section({
      sectionId: "entity-confidence",
      key: "confidence",
      order: 4,
      strategy: "entity_intelligence_page",
      title: "Confidence",
      selectedCard: card("confidence_coverage"),
    }),
  ];
  return askEntityCorePageSchema.parse({
    schema_version: "1",
    policy_version: "ask-ai-entity-core-page-v1",
    canonical_id: "dsm",
    response: {
      schema_version: "1",
      policy_version: "ask-ai-response-contract-v1",
      response_id: "entity-response-1",
      response_strategy: "entity_intelligence_page",
      sections,
      overall_confidence: {
        score: 88,
        label: "high",
        reasons: ["Core entity evidence is strongly grounded."],
      },
      compatibility_summary: "DSM core entity page.",
      assumptions: [],
      gaps: [],
    },
  });
}

export function partialEntityCorePageFixture(): AskEntityCorePage {
  const page = entityCorePageFixture();
  const documents = page.response.sections[3];
  if (documents === undefined) {
    throw new Error("Missing official documents test section");
  }
  const sections = page.response.sections.map((section, index) =>
    index === 3
      ? {
          ...documents,
          state: "empty_by_evidence" as const,
          claim_ids: [],
          source_ids: [],
          gaps: ["Official documents were not established."],
          cards: [],
        }
      : section,
  );
  return askEntityCorePageSchema.parse({
    ...page,
    response: {
      ...page.response,
      sections,
      gaps: ["Official documents were not established."],
    },
  });
}
