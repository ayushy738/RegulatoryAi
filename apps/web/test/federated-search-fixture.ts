import type { AskFederatedSearchResponse } from "../lib/ask-ai-search";

const entity = {
  result_id: "entity:in.central.dsm",
  result_type: "entity",
  title: "Deviation Settlement Mechanism",
  subtitle: "regulatory_concept · India/Central",
  why_matched: "Approved entity alias or acronym matched.",
  provenance: "internal_regulatory_corpus",
  relevance: 950,
  route: "/ask?entity=in.central.dsm",
} as const;

export function federatedSearchFixture(): AskFederatedSearchResponse {
  return {
    schema_version: "1",
    policy_version: "ask-ai-federated-search-v1",
    original_query: "DSM",
    applied_query: "Deviation Settlement Mechanism",
    filters: {},
    correction: {
      kind: "acronym_expansion",
      original_query: "DSM",
      suggested_query: "Deviation Settlement Mechanism",
      reversible: true,
    },
    groups: [
      {
        group: "best_match",
        status: "complete",
        items: [entity],
        next_cursor: null,
      },
      {
        group: "entities",
        status: "complete",
        items: [entity],
        next_cursor: "next-entities",
      },
      {
        group: "official_regulations",
        status: "no_match",
        items: [],
        next_cursor: null,
      },
      {
        group: "official_documents",
        status: "no_match",
        items: [],
        next_cursor: null,
      },
      {
        group: "amendments",
        status: "no_match",
        items: [],
        next_cursor: null,
      },
      {
        group: "consultations",
        status: "no_match",
        items: [],
        next_cursor: null,
      },
      {
        group: "deadlines",
        status: "no_match",
        items: [],
        next_cursor: null,
      },
      {
        group: "previous_research",
        status: "no_match",
        items: [],
        next_cursor: null,
      },
    ],
  };
}
