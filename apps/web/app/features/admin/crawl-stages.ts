import type { CrawlRun } from "@/lib/api";

export type StageStatus = "done" | "active" | "failed" | "skipped" | "pending";

export type PipelineStage = {
  id: string;
  name: string;
  /** What this stage achieved, in operator language. */
  result: string;
  status: StageStatus;
};

function metric(value: number | null | undefined) {
  return typeof value === "number" ? value : null;
}

function plural(count: number, singular: string, pluralForm = `${singular}s`) {
  return `${count} ${count === 1 ? singular : pluralForm}`;
}

/**
 * Derive a pipeline stage timeline from the metrics a crawl run already reports.
 *
 * The backend does not persist stage-level timings, so rather than inventing
 * durations we infer each stage's outcome from its own counters. A stage is
 * `done` when it produced output, `failed` when the run failed before reaching
 * it, `skipped` when an upstream stage produced nothing for it to do, and
 * `active` while the run is still in flight.
 */
export function pipelineStages(run: CrawlRun): PipelineStage[] {
  const terminal = ["success", "partial", "failed"].includes(
    (run.status ?? "").toLowerCase(),
  );
  const inFlight = !terminal;

  const pagesAttempted = metric(run.pages_attempted);
  const pagesSucceeded = metric(run.pages_succeeded);
  const discovered = metric(run.documents_discovered) ?? run.docs_found ?? 0;
  const withContent = metric(run.documents_with_content);
  const persisted = metric(run.documents_persisted);
  const versions = metric(run.versions_created);
  const events = metric(run.events_created) ?? run.new_events ?? 0;
  const graph = metric(run.graph_extractions);
  const ragQueued = metric(run.rag_jobs_enqueued);
  const ragIndexed = metric(run.rag_indexed) ?? metric(run.rag_ready_documents);
  const ragFailed = metric(run.rag_jobs_failed);

  function stage(
    id: string,
    name: string,
    produced: number | null,
    result: string,
    upstream: number | null,
  ): PipelineStage {
    let status: StageStatus;
    if (produced === null) {
      status = inFlight ? "active" : "pending";
    } else if (produced > 0) {
      status = "done";
    } else if (upstream !== null && upstream === 0) {
      status = "skipped";
    } else if (inFlight) {
      status = "active";
    } else {
      status = "failed";
    }
    return { id, name, result, status };
  }

  const hasFailures = run.errors.length > 0;

  return [
    {
      id: "selection",
      name: "Selection",
      result:
        pagesAttempted === null
          ? "Page selection not recorded for this run"
          : plural(pagesAttempted, "page") + " selected to crawl",
      status:
        pagesAttempted === null
          ? inFlight
            ? "active"
            : "pending"
          : pagesAttempted > 0
            ? "done"
            : "failed",
    },
    {
      id: "discovery",
      name: "Discovery",
      result: `${plural(discovered, "candidate document")} discovered${
        pagesSucceeded !== null && pagesAttempted !== null
          ? ` across ${pagesSucceeded} of ${pagesAttempted} pages`
          : ""
      }`,
      status:
        discovered > 0
          ? "done"
          : inFlight
            ? "active"
            : hasFailures
              ? "failed"
              : "skipped",
    },
    stage(
      "download",
      "Download",
      withContent,
      withContent === null
        ? "Download results not recorded"
        : `${plural(withContent, "document")} downloaded with readable content`,
      discovered,
    ),
    stage(
      "parse",
      "Parse",
      versions,
      versions === null
        ? "Parse results not recorded"
        : `${plural(versions, "document version")} parsed`,
      withContent,
    ),
    stage(
      "persistence",
      "Persistence",
      persisted,
      persisted === null
        ? "Persistence results not recorded"
        : `${plural(persisted, "document")} persisted, ${plural(events, "event")} created`,
      versions,
    ),
    stage(
      "graph",
      "Graph",
      graph,
      graph === null
        ? "Graph extraction not recorded"
        : `${plural(graph, "document")} analysed into the knowledge graph`,
      persisted,
    ),
    {
      id: "rag",
      name: "RAG",
      result:
        ragQueued === null
          ? "RAG indexing not recorded"
          : `${plural(ragQueued, "job")} queued, ${ragIndexed ?? 0} indexed${
              ragFailed ? `, ${ragFailed} failed` : ""
            }`,
      status:
        ragFailed && ragFailed > 0
          ? "failed"
          : ragQueued === null
            ? inFlight
              ? "active"
              : "pending"
            : ragQueued > 0
              ? "done"
              : (persisted ?? 0) === 0
                ? "skipped"
                : "active",
    },
    {
      id: "notifications",
      name: "Notifications",
      result: events
        ? `${plural(events, "event")} eligible for subscriber alerts`
        : "No new events to notify on",
      status: events > 0 ? "done" : terminal ? "skipped" : "active",
    },
  ];
}
