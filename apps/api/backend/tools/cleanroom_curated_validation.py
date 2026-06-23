from __future__ import annotations

import asyncio
import json
from collections import Counter, defaultdict
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import text

from backend.core.db import session_scope
from backend.core.utils import canonical_url
from backend.pipeline.regulatory_knowledge_graph import (
    GraphInput,
    analyze_and_persist_regulatory_graph,
)
from backend.pipeline.run_once import run_crawl

TIMESTAMP = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
BACKUP_PATH = Path(f"E:/RegulatoryAi/reports/backups/cleanroom_backup_{TIMESTAMP}.json")
REPORT_PATH = Path("E:/RegulatoryAi/reports/CLEANROOM_CURATED_SOURCE_VALIDATION.md")

KEEP_TABLES = [
    "sources",
    "source_pages",
    "profiles",
    "subscriptions",
]

GENERATED_TABLES = [
    "events",
    "summaries",
    "document_versions",
    "documents",
    "document_texts",
    "discovery_audit",
    "event_intelligence_audit",
    "regulatory_change_audit",
    "document_family_assignments",
    "document_version_registry",
    "document_version_relationships",
    "document_families",
    "deadline_history",
    "regulatory_graph_document_entities",
    "regulatory_graph_edges",
    "regulatory_graph_extractions",
    "regulatory_graph_stakeholders",
    "regulatory_graph_obligations",
    "regulatory_graph_deadlines",
    "regulatory_graph_family_enrichment",
    "regulatory_graph_entities",
    "crawl_runs",
    "digests",
    "digest_events",
    "notifications_log",
    "chat_messages",
    "user_event_state",
]

EXTRA_BACKUP_ONLY_TABLES = [
    "app_documents",
    "exports_log",
    "audit_log",
]

ALL_REPORT_TABLES = GENERATED_TABLES + KEEP_TABLES + EXTRA_BACKUP_ONLY_TABLES


def main() -> None:
    before_counts = _row_counts(ALL_REPORT_TABLES)
    backup_path = _backup_database(before_counts)
    _truncate_generated_tables()
    after_truncate_counts = _row_counts(ALL_REPORT_TABLES)

    crawl_result = asyncio.run(run_crawl())
    graph_result = _run_graph_extraction()
    after_counts = _row_counts(ALL_REPORT_TABLES)

    pages = _load_source_pages()
    page_metrics = [_source_page_metrics(page) for page in pages]
    accepted_documents = _accepted_document_walkthroughs()
    rejection_examples = _rejection_examples()
    latest_run = _latest_crawl_run()

    report = _markdown_report(
        backup_path=backup_path,
        before_counts=before_counts,
        after_truncate_counts=after_truncate_counts,
        after_counts=after_counts,
        crawl_result=crawl_result,
        graph_result=graph_result,
        latest_run=latest_run,
        page_metrics=page_metrics,
        accepted_documents=accepted_documents,
        rejection_examples=rejection_examples,
    )
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(report, encoding="utf-8")
    print(report.encode("ascii", errors="replace").decode("ascii"))


def _backup_database(before_counts: dict[str, int]) -> Path:
    BACKUP_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "created_at": datetime.now(UTC).isoformat(),
        "note": "Clean-room backup before truncating generated intelligence tables.",
        "tables_truncated_after_backup": GENERATED_TABLES,
        "tables_preserved": KEEP_TABLES,
        "row_counts": before_counts,
        "data": {},
    }
    with session_scope() as session:
        for table in ALL_REPORT_TABLES:
            if not _table_exists(session, table):
                payload["data"][table] = {"exists": False, "rows": []}
                continue
            rows = session.execute(text(f"select * from {table}")).mappings()
            payload["data"][table] = {
                "exists": True,
                "rows": [dict(row) for row in rows],
            }
    BACKUP_PATH.write_text(json.dumps(payload, indent=2, default=_json_default), encoding="utf-8")
    return BACKUP_PATH


def _truncate_generated_tables() -> None:
    with session_scope() as session:
        existing_tables = [table for table in GENERATED_TABLES if _table_exists(session, table)]
        if not existing_tables:
            return
        session.execute(
            text(
                "truncate table "
                + ", ".join(existing_tables)
                + " restart identity cascade"
            )
        )


def _run_graph_extraction() -> dict[str, Any]:
    with session_scope() as session:
        before = _graph_counts(session)
        rows = _load_graph_inputs(session)
        results = []
        for row in rows:
            result = analyze_and_persist_regulatory_graph(
                session,
                _graph_input(row),
                use_ai=True,
            )
            results.append(
                {
                    "document_id": row["document_id"],
                    "title": row["title"],
                    "status": getattr(result, "status", None),
                    "used_ai": getattr(result, "used_ai", None),
                }
            )
        after = _graph_counts(session)
    return {
        "documents_analyzed": len(rows),
        "results": results,
        "before": before,
        "after": after,
        "growth": {
            key: int(after.get(key, 0)) - int(before.get(key, 0))
            for key in after
        },
    }


def _load_graph_inputs(session: Any) -> list[dict[str, Any]]:
    rows = session.execute(
        text(
            """
            select
              d.id as document_id,
              d.title,
              d.issuing_body,
              d.issue_date,
              d.doc_type,
              d.source_url,
              dv.id as document_version_id,
              dv.content_hash,
              coalesce(dt.content_length, 0) as content_length,
              coalesce(dt.text_content, '') as text_content,
              a.family_id,
              a.assignment_type
            from documents d
            join lateral (
              select *
              from document_versions
              where document_id = d.id
              order by fetched_at desc
              limit 1
            ) dv on true
            join document_texts dt on dt.content_hash = dv.content_hash
            left join document_family_assignments a on a.document_id = d.id
            where coalesce(dt.content_length, 0) >= 250
            order by d.id
            """
        )
    ).mappings()
    return [dict(row) for row in rows]


def _graph_input(row: dict[str, Any]) -> GraphInput:
    return GraphInput(
        document_id=row["document_id"],
        document_version_id=row.get("document_version_id"),
        title=row["title"],
        issuer=row.get("issuing_body"),
        source_url=row["source_url"],
        document_type=row.get("doc_type"),
        issue_date=row.get("issue_date"),
        content_hash=row.get("content_hash"),
        text_content=row.get("text_content") or "",
        content_length=row.get("content_length") or 0,
        family_id=row.get("family_id"),
        assignment_type=row.get("assignment_type"),
    )


def _load_source_pages() -> list[dict[str, Any]]:
    with session_scope() as session:
        rows = session.execute(
            text(
                """
                select sp.id, sp.name, sp.url, sp.page_type, sp.priority,
                       sp.enabled, sp.last_crawled_at,
                       s.code as source_code, s.name as source_name
                from source_pages sp
                join sources s on s.id = sp.source_id
                where sp.url in (
                  'https://mnre.gov.in/en/notice-category/current-notices/',
                  'https://mnre.gov.in/en/monthly-updates/',
                  'https://cercind.gov.in/public-notice.html',
                  'https://cercind.gov.in/SPN.html',
                  'https://cercind.gov.in/notice-letter.html',
                  'https://www.seci.co.in/tenders',
                  'https://www.powermin.gov.in/whats-new'
                )
                order by s.id, sp.priority, sp.id
                """
            )
        ).mappings()
        return [dict(row) for row in rows]


def _source_page_metrics(page: dict[str, Any]) -> dict[str, Any]:
    with session_scope() as session:
        audit_rows = session.execute(
            text(
                """
                select id, source_url, title, classification, is_valid_event_source,
                       reason_code, primary_url, content_length, content_hash
                from discovery_audit
                where metadata->>'source_page_id' = :page_id
                order by id
                """
            ),
            {"page_id": str(page["id"])},
        ).mappings().all()
    audits = [dict(row) for row in audit_rows]
    synthetic_no_candidate = [
        row for row in audits
        if (
            row["source_url"] == page["url"]
            and row["reason_code"] == "NO_PRIMARY_DOCUMENT"
            and not row.get("primary_url")
        )
    ]
    candidates_found = max(0, len(audits) - len(synthetic_no_candidate))
    accepted = [row for row in audits if row["is_valid_event_source"]]
    downloaded = [
        row for row in audits
        if row.get("primary_url") and int(row.get("content_length") or 0) > 0
    ]
    rejected = [row for row in audits if not row["is_valid_event_source"]]
    doc_ids = _document_ids_for_audits(accepted)
    return {
        **page,
        "candidates_found": candidates_found,
        "primary_documents_downloaded": len(downloaded),
        "accepted": len(accepted),
        "rejected": len(rejected),
        "events_generated": _count_for_docs("events", doc_ids),
        "families_created": _families_for_docs(doc_ids),
        "graph_entities_linked": _count_for_docs("regulatory_graph_document_entities", doc_ids),
        "graph_edges": _count_for_docs("regulatory_graph_edges", doc_ids, "source_document_id"),
        "deadlines": _count_for_docs("regulatory_graph_deadlines", doc_ids),
        "obligations": _count_for_docs("regulatory_graph_obligations", doc_ids),
        "stakeholders": _distinct_stakeholders_for_docs(doc_ids),
        "rejection_reasons": dict(Counter(str(row["reason_code"]) for row in rejected)),
        "classifications": dict(Counter(str(row["classification"]) for row in audits)),
        "example_documents": [row["title"] for row in accepted[:5]],
        "doc_ids": doc_ids,
    }


def _document_ids_for_audits(audits: list[dict[str, Any]]) -> list[int]:
    if not audits:
        return []
    urls = {
        canonical_url(str(row.get("primary_url") or row.get("source_url")))
        for row in audits
        if row.get("primary_url") or row.get("source_url")
    }
    with session_scope() as session:
        rows = session.execute(
            text("select id, source_url from documents")
        ).mappings()
        doc_ids = [
            int(row["id"])
            for row in rows
            if canonical_url(str(row["source_url"])) in urls
        ]
    return sorted(set(doc_ids))


def _accepted_document_walkthroughs() -> list[dict[str, Any]]:
    accepted = _accepted_audits_by_document()
    if not accepted:
        return []
    doc_ids = sorted(accepted)
    details = _document_details(doc_ids)
    stakeholders = _group_rows(
        "regulatory_graph_stakeholders",
        doc_ids,
        ["stakeholder", "normalized_stakeholder", "confidence", "evidence"],
    )
    obligations = _group_rows(
        "regulatory_graph_obligations",
        doc_ids,
        [
            "obligation",
            "affected_party",
            "deadline_date",
            "deadline_type",
            "confidence",
            "evidence",
        ],
    )
    deadlines = _group_rows(
        "regulatory_graph_deadlines",
        doc_ids,
        ["deadline_type", "deadline_date", "raw_date", "confidence", "evidence"],
    )
    output = []
    for doc_id in doc_ids:
        detail = details.get(doc_id, {})
        audit = accepted[doc_id]
        output.append(
            {
                "document_id": doc_id,
                "source_page": audit["source_page"],
                "source_page_url": audit["source_page_url"],
                "title": detail.get("title"),
                "primary_url": detail.get("source_url"),
                "document_type": detail.get("doc_type"),
                "issuer": detail.get("issuing_body"),
                "family": detail.get("canonical_title"),
                "family_assignment": detail.get("assignment_type"),
                "stakeholders": stakeholders.get(doc_id, []),
                "obligations": obligations.get(doc_id, []),
                "deadlines": deadlines.get(doc_id, []),
                "passed_intelligence_gate": bool(detail.get("event_allowed")),
                "created_event": bool(detail.get("event_id")),
                "event_id": detail.get("event_id"),
                "event_type": detail.get("event_type"),
                "gate_rejection_reason": detail.get("rejection_reason"),
            }
        )
    return output


def _accepted_audits_by_document() -> dict[int, dict[str, Any]]:
    with session_scope() as session:
        audits = session.execute(
            text(
                """
                select da.id, da.source_url, da.primary_url, da.title,
                       da.metadata->>'source_page_id' as source_page_id,
                       da.metadata->>'source_page_name' as source_page,
                       sp.url as source_page_url
                from discovery_audit da
                left join source_pages sp on sp.id::text = da.metadata->>'source_page_id'
                where da.is_valid_event_source = true
                order by da.id
                """
            )
        ).mappings().all()
        documents = session.execute(text("select id, source_url from documents")).mappings().all()
    doc_by_url = {canonical_url(str(row["source_url"])): int(row["id"]) for row in documents}
    by_doc: dict[int, dict[str, Any]] = {}
    for audit in audits:
        url = canonical_url(str(audit["primary_url"] or audit["source_url"]))
        doc_id = doc_by_url.get(url)
        if doc_id and doc_id not in by_doc:
            by_doc[doc_id] = dict(audit)
    return by_doc


def _document_details(doc_ids: list[int]) -> dict[int, dict[str, Any]]:
    if not doc_ids:
        return {}
    with session_scope() as session:
        rows = session.execute(
            text(
                """
                select d.id, d.title, d.source_url, d.doc_type, d.issuing_body,
                       f.canonical_title, a.assignment_type,
                       e.id as event_id, e.event_type::text as event_type,
                       iga.event_allowed, iga.rejection_reason
                from documents d
                left join document_family_assignments a on a.document_id = d.id
                left join document_families f on f.family_id = a.family_id
                left join events e on e.document_id = d.id
                left join lateral (
                  select event_allowed, rejection_reason
                  from event_intelligence_audit
                  where document_id = d.id
                  order by created_at desc
                  limit 1
                ) iga on true
                where d.id = any(:doc_ids)
                order by d.id
                """
            ),
            {"doc_ids": doc_ids},
        ).mappings()
        return {int(row["id"]): dict(row) for row in rows}


def _group_rows(
    table: str,
    doc_ids: list[int],
    columns: list[str],
) -> dict[int, list[dict[str, Any]]]:
    if not doc_ids:
        return {}
    column_sql = ", ".join(columns)
    with session_scope() as session:
        rows = session.execute(
            text(
                f"""
                select document_id, {column_sql}
                from {table}
                where document_id = any(:doc_ids)
                order by document_id
                """
            ),
            {"doc_ids": doc_ids},
        ).mappings()
        grouped: dict[int, list[dict[str, Any]]] = defaultdict(list)
        for row in rows:
            data = dict(row)
            document_id = int(data.pop("document_id"))
            grouped[document_id].append(data)
        return dict(grouped)


def _rejection_examples() -> dict[str, list[dict[str, Any]]]:
    with session_scope() as session:
        rows = session.execute(
            text(
                """
                select source_code,
                       metadata->>'source_page_name' as source_page,
                       title,
                       classification,
                       reason_code,
                       metadata->>'explanation' as explanation
                from discovery_audit
                where is_valid_event_source = false
                order by source_code, reason_code, id
                """
            )
        ).mappings()
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[str(row["reason_code"])].append(dict(row))
    return {reason: examples[:5] for reason, examples in grouped.items()}


def _count_for_docs(table: str, doc_ids: list[int], column: str = "document_id") -> int:
    if not doc_ids:
        return 0
    with session_scope() as session:
        row = session.execute(
            text(f"select count(*) as count from {table} where {column} = any(:doc_ids)"),
            {"doc_ids": doc_ids},
        ).mappings().first()
    return int(row["count"] if row else 0)


def _families_for_docs(doc_ids: list[int]) -> int:
    if not doc_ids:
        return 0
    with session_scope() as session:
        row = session.execute(
            text(
                """
                select count(distinct family_id) as count
                from document_family_assignments
                where document_id = any(:doc_ids) and family_id is not null
                """
            ),
            {"doc_ids": doc_ids},
        ).mappings().first()
    return int(row["count"] if row else 0)


def _distinct_stakeholders_for_docs(doc_ids: list[int]) -> int:
    if not doc_ids:
        return 0
    with session_scope() as session:
        row = session.execute(
            text(
                """
                select count(distinct normalized_stakeholder) as count
                from regulatory_graph_stakeholders
                where document_id = any(:doc_ids)
                """
            ),
            {"doc_ids": doc_ids},
        ).mappings().first()
    return int(row["count"] if row else 0)


def _latest_crawl_run() -> dict[str, Any] | None:
    with session_scope() as session:
        row = session.execute(
            text(
                """
                select id, started_at, finished_at, status::text as status,
                       sources_attempted, sources_succeeded, docs_found,
                       new_events, errors
                from crawl_runs
                order by started_at desc
                limit 1
                """
            )
        ).mappings().first()
    return dict(row) if row else None


def _row_counts(tables: list[str]) -> dict[str, int]:
    counts = {}
    with session_scope() as session:
        for table in tables:
            if not _table_exists(session, table):
                continue
            row = session.execute(text(f"select count(*) as count from {table}")).mappings().first()
            counts[table] = int(row["count"] if row else 0)
    return counts


def _graph_counts(session: Any) -> dict[str, int]:
    row = session.execute(
        text(
            """
            select
              (select count(*) from regulatory_graph_entities) as entities,
              (select count(*) from regulatory_graph_document_entities) as document_entities,
              (select count(*) from regulatory_graph_edges) as edges,
              (select count(*) from regulatory_graph_extractions) as extractions,
              (select count(*) from regulatory_graph_stakeholders) as stakeholders,
              (select count(*) from regulatory_graph_obligations) as obligations,
              (select count(*) from regulatory_graph_deadlines) as deadlines,
              (select count(*) from regulatory_graph_family_enrichment) as family_enrichment
            """
        )
    ).mappings().first()
    return {key: int(value or 0) for key, value in dict(row).items()}


def _table_exists(session: Any, table: str) -> bool:
    row = session.execute(
        text(
            """
            select exists (
              select 1
              from information_schema.tables
              where table_schema = 'public' and table_name = :table
            ) as exists
            """
        ),
        {"table": table},
    ).mappings().first()
    return bool(row and row["exists"])


def _markdown_report(
    *,
    backup_path: Path,
    before_counts: dict[str, int],
    after_truncate_counts: dict[str, int],
    after_counts: dict[str, int],
    crawl_result: dict[str, Any],
    graph_result: dict[str, Any],
    latest_run: dict[str, Any] | None,
    page_metrics: list[dict[str, Any]],
    accepted_documents: list[dict[str, Any]],
    rejection_examples: dict[str, list[dict[str, Any]]],
) -> str:
    total_candidates = sum(int(item["candidates_found"]) for item in page_metrics)
    total_accepted = sum(int(item["accepted"]) for item in page_metrics)
    total_rejected = sum(int(item["rejected"]) for item in page_metrics)
    total_events = sum(int(item["events_generated"]) for item in page_metrics)
    verdict = _verdict(accepted_documents, after_counts)
    lines = [
        "# Clean-Room Curated Source Validation",
        "",
        f"Generated at: {datetime.now(UTC).isoformat()}",
        "",
        "## Scope",
        "",
        "- No UI was built.",
        "- No AI logic was modified.",
        "- No graph logic was modified.",
        "- No family registry logic was modified.",
        "- Generic homepage/search/archive/category/navigation discovery was not used.",
        "- The run used only Step 22 curated source pages.",
        "",
        "## Backup",
        "",
        f"- Backup file: `{backup_path}`",
        "- Backup format: JSON snapshot of generated tables, preserved configuration "
        "tables, and auxiliary app tables.",
        "",
        "## Reset Result",
        "",
        "| Table | Before | After Truncate | After Run |",
        "|---|---:|---:|---:|",
    ]
    for table in ALL_REPORT_TABLES:
        lines.append(
            f"| `{table}` | {before_counts.get(table, 0)} | "
            f"{after_truncate_counts.get(table, 0)} | {after_counts.get(table, 0)} |"
        )
    lines.extend(
        [
            "",
            "## Curated Crawl Result",
            "",
            f"- Crawl run ID: {latest_run.get('id') if latest_run else 'unknown'}",
            f"- Crawl status: {crawl_result.get('status')}",
            f"- Sources attempted: {crawl_result.get('sources_attempted')}",
            f"- Pages attempted: {crawl_result.get('pages_attempted')}",
            f"- Pages succeeded: {crawl_result.get('pages_succeeded')}",
            f"- Candidates found: {total_candidates}",
            f"- Primary documents accepted: {total_accepted}",
            f"- Rejected candidates: {total_rejected}",
            f"- Events generated: {total_events}",
            f"- Primary docs found by pipeline: {crawl_result.get('primary_docs_found')}",
            f"- Crawl errors: {len(crawl_result.get('errors') or [])}",
            "",
            "## Knowledge Graph Growth",
            "",
        ]
    )
    for key, value in graph_result["growth"].items():
        lines.append(f"- {key}: +{value}")
    lines.extend(
        [
            f"- Documents analyzed by graph extractor: {graph_result['documents_analyzed']}",
            "",
            "## Source Page Metrics",
            "",
            "| Source Page | Candidates | Downloaded | Accepted | Rejected | Events | "
            "Families | Graph Links | Deadlines | Obligations | Stakeholders |",
            "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for item in page_metrics:
        lines.append(
            f"| {item['source_code'].upper()} - {item['name']} | "
            f"{item['candidates_found']} | {item['primary_documents_downloaded']} | "
            f"{item['accepted']} | {item['rejected']} | {item['events_generated']} | "
            f"{item['families_created']} | {item['graph_entities_linked']} | "
            f"{item['deadlines']} | {item['obligations']} | {item['stakeholders']} |"
        )
    lines.extend(["", "## Source Page Details", ""])
    for item in page_metrics:
        lines.extend(
            [
                f"### {item['source_code'].upper()} - {item['name']}",
                "",
                f"- URL: `{item['url']}`",
                f"- Page type: `{item['page_type']}`",
                f"- Candidates found: {item['candidates_found']}",
                f"- Primary documents downloaded: {item['primary_documents_downloaded']}",
                f"- Accepted: {item['accepted']}",
                f"- Rejected: {item['rejected']}",
                f"- Events generated: {item['events_generated']}",
                f"- Families created/assigned: {item['families_created']}",
                f"- Knowledge graph document links: {item['graph_entities_linked']}",
                f"- Deadlines: {item['deadlines']}",
                f"- Obligations: {item['obligations']}",
                f"- Stakeholders: {item['stakeholders']}",
                f"- Rejection reasons: {_fmt_counts(item['rejection_reasons'])}",
                f"- Classifications: {_fmt_counts(item['classifications'])}",
                f"- Example documents: {_fmt_list(item['example_documents'])}",
                "",
            ]
        )
    lines.extend(["## Accepted Document Walkthroughs", ""])
    if len(accepted_documents) < 5:
        lines.append(
            f"Only {len(accepted_documents)} accepted document(s) were produced. "
            "The requested 5-10 walkthrough target was not met by this run."
        )
        lines.append("")
    for index, doc in enumerate(accepted_documents[:10], start=1):
        lines.extend(_document_walkthrough_lines(index, doc))
    lines.extend(["## Rejection Analysis", ""])
    if not rejection_examples:
        lines.append("- No rejected candidates recorded.")
    for reason, examples in rejection_examples.items():
        lines.append(f"### {reason}")
        lines.append("")
        for example in examples:
            lines.append(
                f"- {example.get('source_code', '').upper()} / "
                f"{example.get('source_page') or 'Unknown page'}: "
                f"{_clip(example.get('title'), 140)} "
                f"(`{example.get('classification')}`) - "
                f"{_clip(example.get('explanation'), 180)}"
            )
        lines.append("")
    lines.extend(
        [
            "## Architecture Verdict",
            "",
            f"Verdict: **{verdict['label']}**",
            "",
            verdict["reason"],
            "",
            "## Success Criteria Check",
            "",
            f"- 5-10 accepted walkthroughs available: "
            f"{'YES' if len(accepted_documents) >= 5 else 'NO'} "
            f"({len(accepted_documents)} accepted walkthroughs).",
            f"- Events created from curated pages: {'YES' if total_events else 'NO'} "
            f"({total_events}).",
            "- Families created/assigned: "
            f"{'YES' if after_counts.get('document_families', 0) else 'NO'} "
            f"({after_counts.get('document_families', 0)}).",
            f"- Graph obligations extracted: "
            f"{'YES' if after_counts.get('regulatory_graph_obligations', 0) else 'NO'} "
            f"({after_counts.get('regulatory_graph_obligations', 0)}).",
            f"- Graph deadlines extracted: "
            f"{'YES' if after_counts.get('regulatory_graph_deadlines', 0) else 'NO'} "
            f"({after_counts.get('regulatory_graph_deadlines', 0)}).",
            f"- Stakeholders extracted: "
            f"{'YES' if after_counts.get('regulatory_graph_stakeholders', 0) else 'NO'} "
            f"({after_counts.get('regulatory_graph_stakeholders', 0)}).",
        ]
    )
    return "\n".join(lines)


def _document_walkthrough_lines(index: int, doc: dict[str, Any]) -> list[str]:
    obligations = doc["obligations"]
    deadlines = doc["deadlines"]
    stakeholders = doc["stakeholders"]
    lines = [
        f"### {index}. {_clip(doc['title'], 160)}",
        "",
        f"- Source page: {doc['source_page']} (`{doc['source_page_url']}`)",
        f"- Primary URL: `{doc['primary_url']}`",
        f"- Issuer: {doc['issuer'] or 'Unknown'}",
        f"- Document type: `{doc['document_type'] or 'unknown'}`",
        f"- Family: {doc['family'] or 'Unassigned'}",
        f"- Family assignment: {doc['family_assignment'] or 'Unknown'}",
        f"- Passed intelligence gate: {'YES' if doc['passed_intelligence_gate'] else 'NO'}",
        f"- Created event: {'YES' if doc['created_event'] else 'NO'}"
        + (f" (event {doc['event_id']}, {doc['event_type']})" if doc["created_event"] else ""),
        f"- Gate rejection reason: {doc['gate_rejection_reason'] or 'None'}",
        "",
        "Stakeholders:",
    ]
    lines.extend(
        f"- {_clip(item.get('stakeholder') or item.get('normalized_stakeholder'), 120)}"
        for item in stakeholders[:8]
    )
    if not stakeholders:
        lines.append("- None extracted.")
    lines.append("")
    lines.append("Obligations:")
    lines.extend(
        f"- {_clip(item.get('obligation'), 180)}"
        + (f" [{item.get('affected_party')}]" if item.get("affected_party") else "")
        for item in obligations[:8]
    )
    if not obligations:
        lines.append("- None extracted.")
    lines.append("")
    lines.append("Deadlines:")
    lines.extend(
        f"- {item.get('deadline_type')}: {item.get('deadline_date') or item.get('raw_date')}"
        for item in deadlines[:8]
    )
    if not deadlines:
        lines.append("- None extracted.")
    lines.append("")
    return lines


def _verdict(accepted_documents: list[dict[str, Any]], counts: dict[str, int]) -> dict[str, str]:
    events = counts.get("events", 0)
    obligations = counts.get("regulatory_graph_obligations", 0)
    deadlines = counts.get("regulatory_graph_deadlines", 0)
    stakeholders = counts.get("regulatory_graph_stakeholders", 0)
    if len(accepted_documents) >= 5 and events >= 5 and (obligations or deadlines) and stakeholders:
        return {
            "label": "VALIDATED",
            "reason": (
                "The curated source-page architecture produced multiple accepted primary "
                "documents, events, families, graph stakeholders, and action-oriented "
                "intelligence suitable for analyst review."
            ),
        }
    if accepted_documents and events and stakeholders:
        return {
            "label": "PARTIALLY VALIDATED",
            "reason": (
                "The architecture is functioning from curated page to primary document to "
                "event/graph, but the run did not produce enough accepted examples or "
                "actionable graph rows to call it analyst-grade yet."
            ),
        }
    return {
        "label": "NOT VALIDATED",
        "reason": (
            "The curated pages did not produce enough accepted primary documents and "
            "downstream intelligence. The architecture is cleaner, but source-specific "
            "extraction or page parsing still needs work before analyst-grade validation."
        ),
    }


def _fmt_counts(value: dict[str, int]) -> str:
    if not value:
        return "none"
    return ", ".join(f"{key}={count}" for key, count in sorted(value.items()))


def _fmt_list(values: list[str]) -> str:
    values = [_clip(value, 100) for value in values if value]
    return "; ".join(values) if values else "none"


def _clip(value: object, limit: int = 180) -> str:
    text_value = " ".join(str(value or "").split())
    return text_value if len(text_value) <= limit else text_value[:limit].rstrip() + "..."


def _json_default(value: object) -> object:
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    return str(value)


if __name__ == "__main__":
    main()
