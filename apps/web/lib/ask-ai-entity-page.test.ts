import { describe, expect, it } from "vitest";

import {
  askEntityCorePageSchema,
  askEntityCoreSectionKeys,
} from "./ask-ai-entity-page";
import {
  entityCorePageFixture,
  partialEntityCorePageFixture,
} from "../test/entity-core-page-fixture";

describe("ASK_AI entity core page contract", () => {
  it("accepts the canonical five-slot page and independent partial fixture", () => {
    const complete = entityCorePageFixture();
    const partial = partialEntityCorePageFixture();

    expect(
      complete.response.sections.map((section) => section.section_key),
    ).toEqual(askEntityCoreSectionKeys);
    expect(partial.response.sections[3]).toMatchObject({
      section_key: "official_documents",
      state: "empty_by_evidence",
      cards: [],
    });
    expect(partial.response.sections[2]?.state).toBe("ready");
  });

  it("refuses crossed slots, dishonest ready states, and live core provenance", () => {
    const crossed = structuredClone(entityCorePageFixture());
    crossed.response.sections[1]!.section_key = "entity_definition";
    expect(askEntityCorePageSchema.safeParse(crossed).success).toBe(false);

    const emptyReady = structuredClone(entityCorePageFixture());
    emptyReady.response.sections[0]!.cards = [];
    expect(askEntityCorePageSchema.safeParse(emptyReady).success).toBe(false);

    const live = structuredClone(entityCorePageFixture());
    live.response.sections[4]!.knowledge_mode = "live_intelligence";
    live.response.sections[4]!.provenance_class = "live_web_sources";
    live.response.sections[4]!.state = "degraded";
    live.response.sections[4]!.cards = [];
    expect(askEntityCorePageSchema.safeParse(live).success).toBe(false);
  });

  it("is strict and binds the canonical entity identity", () => {
    const page = entityCorePageFixture();
    expect(
      askEntityCorePageSchema.safeParse({ ...page, extra: true }).success,
    ).toBe(false);
    expect(
      askEntityCorePageSchema.safeParse({
        ...page,
        canonical_id: "DSM with spaces",
      }).success,
    ).toBe(false);
  });
});
