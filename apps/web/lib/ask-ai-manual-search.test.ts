import { describe, expect, it } from "vitest";

import {
  manualDocumentSearchFixture,
} from "../test/manual-document-search-fixture";
import {
  askManualDocumentSearchRequestSchema,
  askManualDocumentSearchResponseSchema,
} from "./ask-ai-manual-search";

describe("ASK_AI manual document search contract", () => {
  it("normalizes every frozen filter and accepts exact result metadata", () => {
    expect(
      askManualDocumentSearchRequestSchema.parse({
        query: " deviation   charge ",
        exact_phrase: true,
        title: " DSM Regulations ",
        issuer: " CERC ",
        document_number: " CERC/DSM/2026 ",
        document_type: " regulation ",
        family: " DSM family ",
        version: " Version 2 ",
        status: "current",
        issued_from: "2026-01-01",
        effective_to: "2026-12-31",
        within_document: " generators ",
      }),
    ).toEqual({
      schema_version: "1",
      query: "deviation charge",
      exact_phrase: true,
      title: "DSM Regulations",
      issuer: "CERC",
      document_number: "CERC/DSM/2026",
      document_type: "regulation",
      family: "DSM family",
      version: "Version 2",
      status: "current",
      issued_from: "2026-01-01",
      effective_to: "2026-12-31",
      within_document: "generators",
      limit: 20,
    });
    expect(
      askManualDocumentSearchResponseSchema.parse(
        manualDocumentSearchFixture(),
      ).items[0]!.within_document_matches[0]!.page_number,
    ).toBe(4);
  });

  it("rejects empty, reversed, and unbound exact-phrase requests", () => {
    expect(
      askManualDocumentSearchRequestSchema.safeParse({}).success,
    ).toBe(false);
    expect(
      askManualDocumentSearchRequestSchema.safeParse({
        title: "DSM",
        exact_phrase: true,
      }).success,
    ).toBe(false);
    expect(
      askManualDocumentSearchRequestSchema.safeParse({
        title: "DSM",
        issued_from: "2026-02-01",
        issued_to: "2026-01-01",
      }).success,
    ).toBe(false);
  });

  it("rejects crossed identity, unsafe URLs, and invented no-match rows", () => {
    const crossed = structuredClone(manualDocumentSearchFixture());
    crossed.items[0]!.result_id = "document:99:20";
    expect(
      askManualDocumentSearchResponseSchema.safeParse(crossed).success,
    ).toBe(false);

    const unsafe = structuredClone(manualDocumentSearchFixture());
    unsafe.items[0]!.source_url = "javascript:alert(1)";
    expect(
      askManualDocumentSearchResponseSchema.safeParse(unsafe).success,
    ).toBe(false);

    const noMatch = structuredClone(manualDocumentSearchFixture());
    noMatch.status = "no_match";
    expect(
      askManualDocumentSearchResponseSchema.safeParse(noMatch).success,
    ).toBe(false);
  });
});
