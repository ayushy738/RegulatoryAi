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

  it("accepts authoritative linked-document telemetry without fabricating values", () => {
    const parsed = crawlRunSchema.parse({
      id: 58,
      started_at: "2026-08-15T20:41:51Z",
      finished_at: "2026-08-16T00:00:00Z",
      status: "failed",
      sources_attempted: 1,
      sources_succeeded: 1,
      docs_found: 2,
      new_events: 1,
      errors: [],
      documents_discovered: 2,
      documents_persisted: 2,
      versions_created: 2,
      graph_extractions: 1,
      entities_extracted: 18,
      obligations_extracted: 12,
      stakeholders_extracted: 2,
      rag_jobs_enqueued: 1,
      rag_jobs_completed: 1,
      rag_ready_documents: 1,
      chunks_indexed: 25,
      rag_indexed: 1,
    });
    expect(parsed.graph_extractions).toBe(1);
    expect(parsed.entities_extracted).toBe(18);
    expect(parsed.chunks_indexed).toBe(25);
    expect(parsed.rag_indexed).toBe(1);
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
