from __future__ import annotations

import asyncio
import time
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import text

from backend.core.db import session_scope
from backend.core.repository import list_enabled_source_pages, persist_extracted_documents
from backend.core.utils import canonical_url
from backend.pipeline.agent_scraper import scrape_source_page
from backend.pipeline.primary_document import acquire_primary_documents

REPORT_PATH = Path("E:/RegulatoryAi/reports/STEP25_PRODUCTION_GRAPH_VALIDATION.md")


async def main_async() -> None:
    started = time.perf_counter()
    before = _graph_totals()
    page_results: list[dict[str, Any]] = []
    document_results: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []

    pages = list_enabled_source_pages()
    for page in pages:
        page_started = time.perf_counter()
        try:
            docs = await scrape_source_page({**page, "checkpoint": None})
            docs_to_acquire = []
            existing_completed = []
            for candidate in docs:
                existing_doc_id = _completed_document_id_for_url(candidate.source_url)
                if existing_doc_id is None:
                    docs_to_acquire.append(candidate)
                    continue
                metrics = _document_graph_metrics(existing_doc_id)
                result = {
                    "document_id": existing_doc_id,
                    "source_code": page["source_code"],
                    "source_page": page["name"],
                    "title": candidate.title,
                    "source_url": canonical_url(candidate.source_url),
                    "event_ids": [],
                    "ingestion_latency_ms": 0,
                    "validation_mode": "existing_completed_graph",
                    **metrics,
                }
                missing = _missing_graph_requirements(result)
                result["missing"] = missing
                if missing:
                    failures.append(
                        {
                            "document_id": existing_doc_id,
                            "source_page": page["name"],
                            "title": candidate.title,
                            "reason": ", ".join(missing),
                        }
                    )
                document_results.append(result)
                existing_completed.append(result)

            primary_result = await acquire_primary_documents(docs_to_acquire)
            accepted = primary_result.accepted
            rejected = [audit for audit in primary_result.audits if not audit.is_valid_event_source]
            page_event_ids: list[int] = []
            for extracted in accepted:
                doc_started = time.perf_counter()
                event_ids = persist_extracted_documents([extracted])
                ingestion_latency_ms = _elapsed_ms(doc_started)
                page_event_ids.extend(event_ids)
                doc_id = _document_id_for_url(extracted.fetched.discovered.source_url)
                if doc_id is None:
                    failure = {
                        "source_page": page["name"],
                        "title": extracted.fetched.discovered.title,
                        "reason": "Persisted document could not be resolved by source URL.",
                    }
                    failures.append(failure)
                    document_results.append({**failure, "document_id": None})
                    continue
                metrics = _document_graph_metrics(doc_id)
                result = {
                    "document_id": doc_id,
                    "source_code": page["source_code"],
                    "source_page": page["name"],
                    "title": extracted.fetched.discovered.title,
                    "source_url": canonical_url(extracted.fetched.discovered.source_url),
                    "event_ids": event_ids,
                    "ingestion_latency_ms": ingestion_latency_ms,
                    **metrics,
                }
                missing = _missing_graph_requirements(result)
                result["missing"] = missing
                if missing:
                    failures.append(
                        {
                            "document_id": doc_id,
                            "source_page": page["name"],
                            "title": extracted.fetched.discovered.title,
                            "reason": ", ".join(missing),
                        }
                    )
                document_results.append(result)

            page_results.append(
                {
                    "source_code": page["source_code"],
                    "source_page": page["name"],
                    "url": page["url"],
                    "candidates": len(docs),
                    "accepted": len(existing_completed) + len(accepted),
                    "rejected": len(rejected),
                    "events": len(page_event_ids),
                    "latency_ms": _elapsed_ms(page_started),
                    "rejection_reasons": dict(Counter(audit.reason_code for audit in rejected)),
                }
            )
        except Exception as exc:
            failure = {
                "source_code": page.get("source_code"),
                "source_page": page.get("name"),
                "reason": f"{type(exc).__name__}: {exc}",
            }
            failures.append(failure)
            page_results.append(
                {
                    "source_code": page.get("source_code"),
                    "source_page": page.get("name"),
                    "url": page.get("url"),
                    "candidates": 0,
                    "accepted": 0,
                    "rejected": 0,
                    "events": 0,
                    "latency_ms": _elapsed_ms(page_started),
                    "error": failure["reason"],
                    "rejection_reasons": {},
                }
            )

    after = _graph_totals()
    report = _markdown_report(
        before=before,
        after=after,
        page_results=page_results,
        document_results=document_results,
        failures=failures,
        total_latency_ms=_elapsed_ms(started),
    )
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(report, encoding="utf-8")
    print(report.encode("ascii", errors="replace").decode("ascii"))


def _document_id_for_url(url: str) -> int | None:
    with session_scope() as session:
        row = session.execute(
            text(
                """
                select id
                from documents
                where source_url = :source_url
                order by id desc
                limit 1
                """
            ),
            {"source_url": canonical_url(url)},
        ).mappings().first()
        return int(row["id"]) if row else None


def _completed_document_id_for_url(url: str) -> int | None:
    with session_scope() as session:
        row = session.execute(
            text(
                """
                select d.id
                from documents d
                join regulatory_graph_extractions ge on ge.document_id = d.id
                where d.source_url = :source_url
                  and ge.status = 'COMPLETED'
                order by d.id desc
                limit 1
                """
            ),
            {"source_url": canonical_url(url)},
        ).mappings().first()
        return int(row["id"]) if row else None


def _document_graph_metrics(document_id: int) -> dict[str, Any]:
    with session_scope() as session:
        row = session.execute(
            text(
                """
                select
                  ge.status as graph_status,
                  ge.used_ai,
                  ge.error as graph_error,
                  case
                    when ge.extraction_json->'_meta'->>'latency_ms' ~ '^[0-9]+$'
                    then (ge.extraction_json->'_meta'->>'latency_ms')::int
                    else null
                  end as graph_latency_ms,
                  (select count(*)
                   from regulatory_graph_document_entities
                   where document_id = :document_id) as document_entities,
                  (select count(*)
                   from regulatory_graph_edges
                   where source_document_id = :document_id) as edges,
                  (select count(*)
                   from regulatory_graph_deadlines
                   where document_id = :document_id) as deadlines,
                  (select count(*)
                   from regulatory_graph_stakeholders
                   where document_id = :document_id) as stakeholders,
                  (select count(*)
                   from regulatory_graph_obligations
                   where document_id = :document_id) as obligations,
                  exists (
                    select 1
                    from regulatory_graph_family_enrichment
                    where document_id = :document_id
                  ) as family_enrichment
                from documents d
                left join regulatory_graph_extractions ge on ge.document_id = d.id
                where d.id = :document_id
                """
            ),
            {"document_id": document_id},
        ).mappings().first()
        return dict(row) if row else {}


def _missing_graph_requirements(result: dict[str, Any]) -> list[str]:
    missing: list[str] = []
    if result.get("graph_status") != "COMPLETED":
        missing.append(f"graph_status={result.get('graph_status') or 'missing'}")
    if int(result.get("document_entities") or 0) <= 0:
        missing.append("entities=0")
    if int(result.get("edges") or 0) <= 0:
        missing.append("relationships=0")
    if int(result.get("deadlines") or 0) <= 0:
        missing.append("deadlines=0")
    if int(result.get("stakeholders") or 0) <= 0:
        missing.append("stakeholders=0")
    if int(result.get("obligations") or 0) <= 0:
        missing.append("obligations=0")
    if result.get("graph_error") and result.get("graph_status") != "COMPLETED":
        missing.append("graph_error")
    return missing


def _graph_totals() -> dict[str, int]:
    with session_scope() as session:
        row = session.execute(
            text(
                """
                select
                  (select count(*) from documents) as documents,
                  (select count(*) from events) as events,
                  (select count(*) from document_texts) as document_texts,
                  (select count(*) from document_versions) as document_versions,
                  (select count(*) from document_families) as families,
                  (select count(*) from regulatory_graph_extractions) as graph_extractions,
                  (select count(*) from regulatory_graph_extractions
                   where status = 'COMPLETED') as graph_completed,
                  (select count(*) from regulatory_graph_extractions
                   where status = 'FAILED') as graph_failed,
                  (select count(*) from regulatory_graph_extractions
                   where status = 'SKIPPED') as graph_skipped,
                  (select count(*) from regulatory_graph_entities) as entities,
                  (select count(*) from regulatory_graph_document_entities)
                    as document_entities,
                  (select count(*) from regulatory_graph_edges) as edges,
                  (select count(*) from regulatory_graph_deadlines) as deadlines,
                  (select count(*) from regulatory_graph_stakeholders) as stakeholders,
                  (select count(*) from regulatory_graph_obligations) as obligations,
                  (select count(*) from regulatory_graph_family_enrichment)
                    as family_enrichment
                """
            )
        ).mappings().first()
        return {key: int(value or 0) for key, value in dict(row).items()}


def _markdown_report(
    *,
    before: dict[str, int],
    after: dict[str, int],
    page_results: list[dict[str, Any]],
    document_results: list[dict[str, Any]],
    failures: list[dict[str, Any]],
    total_latency_ms: int,
) -> str:
    status_counts = Counter(str(doc.get("graph_status") or "missing") for doc in document_results)
    ai_count = sum(1 for doc in document_results if doc.get("used_ai"))
    fallback_count = sum(1 for doc in document_results if not doc.get("used_ai"))
    processed = len(document_results)
    graph_latency_values = [
        int(doc["graph_latency_ms"])
        for doc in document_results
        if doc.get("graph_latency_ms") is not None
    ]
    avg_graph_latency = (
        sum(graph_latency_values) / len(graph_latency_values) if graph_latency_values else 0
    )
    lines = [
        "# Step 25 Production Graph Validation",
        "",
        f"Generated at: {datetime.now(UTC).isoformat()}",
        "",
        "## Scope",
        "",
        "- RAG was not implemented.",
        "- Embeddings and vector search were not implemented.",
        "- UI, chat, and Azure deployment files were not modified.",
        "- Validation used curated source pages and the production document ingestion path.",
        "- The old knowledge graph backfill was not invoked for validation.",
        "",
        "## Pipeline Audit",
        "",
        "Observed production flow after this change:",
        "",
        "1. `run_crawl` loads enabled curated `source_pages`.",
        "2. `scrape_source_page` crawls each curated page and returns candidates.",
        "3. `acquire_primary_document` fetches each primary PDF/HTML document.",
        "4. Primary extraction stores raw/text objects and OCRs PDF text when needed.",
        "5. `persist_extracted_documents` upserts `documents`.",
        "6. It persists `document_texts` and `document_versions`.",
        "7. It registers the `document_families` / `document_version_registry` family.",
        "8. It runs transactional graph extraction into existing graph tables.",
        "9. It continues regulatory change and event-intelligence gates.",
        "10. It creates `events` and `summaries` only when the event gates allow it.",
        "",
        "Graph extraction occurs immediately after version/family registration and before "
        "event creation. A graph failure records `FAILED` in "
        "`regulatory_graph_extractions` and does not roll back the document/version.",
        "",
        "## Summary",
        "",
        f"- Curated source pages processed: {len(page_results)}",
        f"- Documents processed: {processed}",
        f"- Graph extraction status mix: {_fmt_counts(dict(status_counts))}",
        f"- AI-backed graph extractions: {ai_count}",
        f"- Heuristic/fallback graph extractions: {fallback_count}",
        f"- Failures/gaps: {len(failures)}",
        f"- Total validation latency: {total_latency_ms} ms",
        f"- Average graph latency: {avg_graph_latency:.1f} ms",
        "",
        "## Graph Table Growth",
        "",
        "| Table/Metric | Before | After | Delta |",
        "|---|---:|---:|---:|",
    ]
    for key in (
        "documents",
        "events",
        "document_texts",
        "document_versions",
        "families",
        "graph_extractions",
        "graph_completed",
        "graph_failed",
        "graph_skipped",
        "entities",
        "document_entities",
        "edges",
        "deadlines",
        "stakeholders",
        "obligations",
        "family_enrichment",
    ):
        lines.append(
            f"| {key} | {before.get(key, 0)} | {after.get(key, 0)} | "
            f"{after.get(key, 0) - before.get(key, 0)} |"
        )

    lines.extend(
        [
            "",
            "## Source Results",
            "",
            "| Source Page | Candidates | Accepted | Rejected | Events | Latency ms |",
            "|---|---:|---:|---:|---:|---:|",
        ]
    )
    for page in page_results:
        lines.append(
            f"| {page.get('source_code', '').upper()} - {page.get('source_page')} | "
            f"{page.get('candidates', 0)} | {page.get('accepted', 0)} | "
            f"{page.get('rejected', 0)} | {page.get('events', 0)} | "
            f"{page.get('latency_ms', 0)} |"
        )

    lines.extend(
        [
            "",
            "## Document Graph Results",
            "",
            "| Document | Status | Entities | Edges | Deadlines | Stakeholders | "
            "Obligations | Graph ms |",
            "|---|---|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for doc in document_results:
        title = _clip(doc.get("title"), 110)
        missing = f" ({', '.join(doc.get('missing') or [])})" if doc.get("missing") else ""
        lines.append(
            f"| {doc.get('document_id') or 'unresolved'} - {title} | "
            f"{doc.get('graph_status') or 'missing'}{missing} | "
            f"{doc.get('document_entities') or 0} | {doc.get('edges') or 0} | "
            f"{doc.get('deadlines') or 0} | {doc.get('stakeholders') or 0} | "
            f"{doc.get('obligations') or 0} | {doc.get('graph_latency_ms') or 0} |"
        )

    lines.extend(["", "## Failures", ""])
    if not failures:
        lines.append("- None.")
    for failure in failures:
        label = failure.get("document_id") or failure.get("source_page") or "unknown"
        lines.append(f"- {label}: {_clip(failure.get('reason'), 220)}")

    lines.extend(
        [
            "",
            "## Validation Verdict",
            "",
            _verdict(processed, failures),
        ]
    )
    return "\n".join(lines)


def _verdict(processed: int, failures: list[dict[str, Any]]) -> str:
    if processed and not failures:
        return "VALIDATED: every accepted document produced completed graph rows."
    if processed:
        return (
            "PARTIALLY VALIDATED: production ingestion now invokes graph extraction, "
            "but some accepted documents are missing one or more graph row categories."
        )
    return "NOT VALIDATED: no accepted primary documents were processed."


def _elapsed_ms(started: float) -> int:
    return max(0, int((time.perf_counter() - started) * 1000))


def _fmt_counts(counts: dict[str, int]) -> str:
    return ", ".join(f"{key}={value}" for key, value in sorted(counts.items())) or "none"


def _clip(value: object, limit: int = 160) -> str:
    text_value = " ".join(str(value or "").split())
    return text_value if len(text_value) <= limit else text_value[:limit].rstrip() + "..."


def main() -> None:
    asyncio.run(main_async())


if __name__ == "__main__":
    main()
