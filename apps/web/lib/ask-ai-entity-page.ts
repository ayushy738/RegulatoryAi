import { z } from "zod";

import {
  askStructuredResponseSchema,
  type AskStructuredResponseSection,
} from "./ask-ai-response";

export const askEntityCoreSectionKeys = [
  "overview",
  "definition",
  "official_regulations",
  "official_documents",
  "confidence",
] as const;

const canonicalId = /^[a-z0-9][a-z0-9._:-]{0,199}$/;
const contentStates = new Set(["ready", "ready_without_synthesis"]);
const emptyStates = new Set([
  "empty_by_evidence",
  "omitted",
  "needs_clarification",
  "cancelled",
]);
const sectionRules = {
  overview: {
    title: "Overview",
    strategy: "entity_intelligence_page",
    cardType: "answer_summary",
    singleton: true,
  },
  definition: {
    title: "Definition",
    strategy: "definition_card",
    cardType: "definition",
    singleton: true,
  },
  official_regulations: {
    title: "Official Regulations",
    strategy: "official_documents_overview",
    cardType: "official_source",
    singleton: false,
  },
  official_documents: {
    title: "Official Documents",
    strategy: "official_documents_overview",
    cardType: "official_source",
    singleton: false,
  },
  confidence: {
    title: "Confidence",
    strategy: "entity_intelligence_page",
    cardType: "confidence_coverage",
    singleton: true,
  },
} as const;

export const askEntityCorePageSchema = z
  .strictObject({
    schema_version: z.literal("1"),
    policy_version: z.literal("ask-ai-entity-core-page-v1"),
    canonical_id: z.string().regex(canonicalId),
    response: askStructuredResponseSchema,
  })
  .superRefine((value, context) => {
    if (value.response.response_strategy !== "entity_intelligence_page") {
      context.addIssue({
        code: "custom",
        message:
          "Entity core page requires the entity intelligence strategy",
      });
    }
    const sectionKeys = value.response.sections.map(
      (section) => section.section_key,
    );
    if (
      JSON.stringify(sectionKeys) !==
      JSON.stringify(askEntityCoreSectionKeys)
    ) {
      context.addIssue({
        code: "custom",
        message: "Entity core sections require the canonical five-slot order",
      });
      return;
    }
    value.response.sections.forEach((section, index) => {
      validateSection(
        askEntityCoreSectionKeys[index],
        section,
        context,
      );
    });
  });

function validateSection(
  key: (typeof askEntityCoreSectionKeys)[number],
  section: AskStructuredResponseSection,
  context: z.RefinementCtx,
) {
  const rule = sectionRules[key];
  const issue = (message: string) =>
    context.addIssue({
      code: "custom",
      path: ["response", "sections", section.order],
      message,
    });
  if (section.title !== rule.title) {
    issue("Entity core section title does not match its slot");
  }
  if (section.strategy !== rule.strategy) {
    issue("Entity core section strategy does not match its slot");
  }
  if (section.knowledge_mode === "live_intelligence") {
    issue("Entity core sections cannot introduce live provenance");
  }
  if (section.cards.some((card) => card.known_type !== rule.cardType)) {
    issue("Entity core card does not belong to its section");
  }
  if (contentStates.has(section.state) && section.cards.length === 0) {
    issue("Ready entity core sections require content");
  }
  if (emptyStates.has(section.state) && section.cards.length > 0) {
    issue("Non-content entity core sections cannot contain cards");
  }
  if (rule.singleton && section.cards.length > 1) {
    issue("Singleton entity core sections permit at most one card");
  }
}

export type AskEntityCorePage = z.infer<typeof askEntityCorePageSchema>;
