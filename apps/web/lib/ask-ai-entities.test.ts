import { describe, expect, it } from "vitest";

import {
  askEntityLookupRequestSchema,
  askEntityLookupResponseSchema,
  askEntityRoute,
} from "./ask-ai-entities";

const candidate = {
  canonical_id: "in.central.dsm",
  canonical_name: "Deviation Settlement Mechanism",
  entity_class: "regulatory_concept",
  jurisdiction: "India/Central",
  aliases: ["DSM", "Deviation Settlement"],
  confidence: 0.95,
  assumed: false,
  match_reason: "Matched an approved alias.",
  entity_route: "/ask?entity=in.central.dsm",
} as const;

describe("Ask entity lookup contracts", () => {
  it("normalizes strict lookup requests and builds canonical routes", () => {
    expect(
      askEntityLookupRequestSchema.parse({
        mention: " DSM ",
        active_jurisdiction: " India/Central ",
      }),
    ).toEqual({
      schema_version: "1",
      mention: "DSM",
      active_jurisdiction: "India/Central",
    });
    expect(askEntityRoute("in.central.dsm")).toBe(
      "/ask?entity=in.central.dsm",
    );
    expect(() =>
      askEntityLookupRequestSchema.parse({
        mention: "DSM",
        raw_provider: "secret",
      }),
    ).toThrow();
  });

  it("accepts exact resolved, ambiguous, and no-match outcome shapes", () => {
    const common = {
      schema_version: "1",
      policy_version: "ask-ai-decision-v1",
      mention: "DSM",
      match_rule: "exact_alias",
    };
    expect(
      askEntityLookupResponseSchema.parse({
        ...common,
        status: "resolved",
        selected: candidate,
        candidates: [],
        clarification_question: null,
        surface: "entity_intelligence_page",
      }).status,
    ).toBe("resolved");
    expect(
      askEntityLookupResponseSchema.parse({
        ...common,
        status: "ambiguous",
        selected: null,
        candidates: [candidate],
        clarification_question: "Which did you mean?",
        surface: null,
      }).status,
    ).toBe("ambiguous");
    expect(
      askEntityLookupResponseSchema.parse({
        ...common,
        status: "no_match",
        selected: null,
        candidates: [],
        clarification_question: "Which entity or jurisdiction?",
        surface: null,
      }).status,
    ).toBe("no_match");
  });

  it("refuses crossed shapes, duplicate aliases/candidates, and routes", () => {
    const common = {
      schema_version: "1",
      policy_version: "ask-ai-decision-v1",
      mention: "DSM",
      match_rule: "exact_alias",
      clarification_question: null,
    };
    expect(() =>
      askEntityLookupResponseSchema.parse({
        ...common,
        status: "resolved",
        selected: null,
        candidates: [],
        surface: "entity_intelligence_page",
      }),
    ).toThrow();
    expect(() =>
      askEntityLookupResponseSchema.parse({
        ...common,
        status: "ambiguous",
        selected: null,
        candidates: [candidate, candidate],
        clarification_question: "Which one?",
        surface: null,
      }),
    ).toThrow();
    expect(() =>
      askEntityLookupResponseSchema.parse({
        ...common,
        status: "resolved",
        selected: {
          ...candidate,
          aliases: ["DSM", "DSM"],
          entity_route: "/ask?entity=wrong",
        },
        candidates: [],
        surface: "entity_intelligence_page",
      }),
    ).toThrow();
  });
});
