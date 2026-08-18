import { describe, expect, it } from "vitest";

import { citationKey, dedupeCitations, stripEmbeddedSources } from "./citations";

const kerc = {
  document_id: 10,
  title: "Draft KERC DSM Framework",
  issuer: "KERC",
  issue_date: "2026-03-10",
  source_url: "https://example.gov.in/dsm",
};

describe("citation helpers", () => {
  it("deduplicates retrieved chunks of the same document", () => {
    const unique = dedupeCitations([
      { ...kerc, evidence: "chunk one" },
      { ...kerc, evidence: "chunk two", page_number: 4 },
      {
        document_id: 11,
        title: "CERC Tariff Regulations",
        source_url: "https://example.gov.in/cerc",
      },
      { title: "Draft KERC DSM Framework", source_url: kerc.source_url },
    ]);

    expect(unique).toHaveLength(2);
    expect(unique.map((item) => item.document_id)).toEqual([10, 11]);
  });

  it("falls back to URL then title when document id is missing", () => {
    expect(
      citationKey({ title: "Same", source_url: "https://a.example/doc" }),
    ).toBe("url:https://a.example/doc");
    expect(dedupeCitations([{ title: "Alpha" }, { title: "Alpha" }, { title: "Beta" }])).toHaveLength(
      2,
    );
  });

  it("strips an embedded Sources section when structured citations exist", () => {
    const body = [
      "DSM is Demand Side Management.",
      "",
      "## Sources",
      "1. Draft KERC DSM Framework",
      "   KERC · 2026-03-10",
    ].join("\n");

    expect(stripEmbeddedSources(body, true)).toBe("DSM is Demand Side Management.");
    expect(stripEmbeddedSources(body, false)).toContain("Sources");
  });
});
