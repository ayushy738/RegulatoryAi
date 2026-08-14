import { describe, expect, it } from "vitest";

import { formatRunMetric } from "@/app/features/AdminViews";
import { crawlRunSchema } from "@/lib/schemas";

describe("crawl run telemetry schema", () => {
  it("keeps run-scoped zeros distinct from unavailable nulls", () => {
    const parsed = crawlRunSchema.parse({
      id: 1,
      started_at: "2026-01-01T00:00:00Z",
      finished_at: "2026-01-01T00:01:00Z",
      status: "success",
      sources_attempted: 1,
      sources_succeeded: 1,
      docs_found: 0,
      new_events: 0,
      errors: [],
      pages_attempted: 1,
      pages_succeeded: 1,
      documents_discovered: 0,
      documents_with_content: 0,
      events_created: 0,
      versions_created: null,
      families_touched: null,
      graph_extractions: null,
      rag_jobs_enqueued: null,
      rag_indexed: null,
    });

    expect(parsed.documents_discovered).toBe(0);
    expect(parsed.rag_indexed).toBeNull();
    expect(parsed.versions_created).toBeNull();
  });

  it("does not invent global totals for missing unavailable fields", () => {
    const parsed = crawlRunSchema.parse({
      id: 2,
      started_at: "2026-01-02T00:00:00Z",
      status: "queued",
      sources_attempted: 0,
      sources_succeeded: 0,
      docs_found: 0,
      new_events: 0,
      errors: [],
    });
    expect(parsed.rag_indexed).toBeUndefined();
    expect(parsed.versions_created).toBeUndefined();
  });
});

describe("formatRunMetric", () => {
  it("renders unavailable for nullish values and zero for real zeros", () => {
    expect(formatRunMetric(null)).toBe("Not available");
    expect(formatRunMetric(undefined)).toBe("Not available");
    expect(formatRunMetric(0)).toBe("0");
    expect(formatRunMetric(12)).toBe("12");
  });
});
