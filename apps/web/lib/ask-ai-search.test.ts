import { describe, expect, it } from "vitest";

import { federatedSearchFixture } from "../test/federated-search-fixture";
import {
  askFederatedSearchRequestSchema,
  askFederatedSearchResponseSchema,
} from "./ask-ai-search";

describe("ASK_AI federated search contract", () => {
  it("normalizes requests and accepts canonical grouped correction state", () => {
    expect(
      askFederatedSearchRequestSchema.parse({
        query: "  DSM   amendment ",
        filters: {
          provenance: "internal_regulatory_corpus",
          jurisdiction: "India/Central",
          status: "NEW",
          stakeholder: "generator",
          topic: "settlement",
          lifecycle: "current",
        },
      }),
    ).toMatchObject({
      schema_version: "1",
      query: "DSM amendment",
      correction_mode: "auto",
      filters: {
        provenance: "internal_regulatory_corpus",
        jurisdiction: "India/Central",
        status: "NEW",
        stakeholder: "generator",
        topic: "settlement",
        lifecycle: "current",
      },
      limit: 5,
    });
    expect(
      askFederatedSearchResponseSchema.parse(
        federatedSearchFixture(),
      ).groups.map((group) => group.group),
    ).toEqual([
      "best_match",
      "entities",
      "official_regulations",
      "official_documents",
      "amendments",
      "consultations",
      "deadlines",
      "previous_research",
    ]);
  });

  it("refuses cursor/filter misuse and crossed result groups", () => {
    expect(
      askFederatedSearchRequestSchema.safeParse({
        query: "DSM",
        cursor: "opaque",
      }).success,
    ).toBe(false);
    expect(
      askFederatedSearchRequestSchema.safeParse({
        query: "DSM",
        filters: {
          date_from: "2026-08-01",
          date_to: "2026-07-01",
        },
      }).success,
    ).toBe(false);
    const crossed = structuredClone(federatedSearchFixture());
    crossed.groups[1]!.items[0]!.result_type = "deadline";
    expect(
      askFederatedSearchResponseSchema.safeParse(crossed).success,
    ).toBe(false);
  });

  it("refuses reordered groups, unbound corrections, and unknown fields", () => {
    const reordered = structuredClone(federatedSearchFixture());
    [reordered.groups[1], reordered.groups[2]] = [
      reordered.groups[2]!,
      reordered.groups[1]!,
    ];
    expect(
      askFederatedSearchResponseSchema.safeParse(reordered).success,
    ).toBe(false);

    const unbound = structuredClone(federatedSearchFixture());
    unbound.correction!.suggested_query = "ABT";
    expect(
      askFederatedSearchResponseSchema.safeParse(unbound).success,
    ).toBe(false);
    expect(
      askFederatedSearchResponseSchema.safeParse({
        ...federatedSearchFixture(),
        raw_provider: "secret",
      }).success,
    ).toBe(false);
  });

  it("accepts an explicitly unavailable group only without invented results", () => {
    const partial = structuredClone(federatedSearchFixture());
    partial.groups[4] = {
      group: "amendments",
      status: "unavailable",
      items: [],
      next_cursor: null,
    };
    expect(
      askFederatedSearchResponseSchema.safeParse(partial).success,
    ).toBe(true);

    partial.groups[4]!.items = [
      partial.groups[1]!.items[0]!,
    ];
    expect(
      askFederatedSearchResponseSchema.safeParse(partial).success,
    ).toBe(false);
  });
});
