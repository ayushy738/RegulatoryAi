from __future__ import annotations

from collections import Counter
from typing import Any

from sqlalchemy import text

from backend.core.db import session_scope
from backend.pipeline.regulatory_knowledge_graph import (
    GRAPH_STATUS_COMPLETED,
    GRAPH_STATUS_FAILED,
    GRAPH_STATUS_SKIPPED,
    GraphInput,
    analyze_and_persist_regulatory_graph,
)


def retry_failed_graph_extractions(
    *,
    limit: int = 50,
    use_ai: bool = True,
) -> dict[str, Any]:
    document_ids = _failed_document_ids(limit=limit)
    results: list[dict[str, Any]] = []
    for document_id in document_ids:
        with session_scope() as session:
            current_status = _current_status(session, document_id)
            if current_status in {GRAPH_STATUS_COMPLETED, GRAPH_STATUS_SKIPPED}:
                results.append(
                    {
                        "document_id": document_id,
                        "status": GRAPH_STATUS_SKIPPED,
                        "error": None,
                    }
                )
                continue
            row = _load_graph_input_row(session, document_id)
            if not row:
                results.append(
                    {
                        "document_id": document_id,
                        "status": GRAPH_STATUS_FAILED,
                        "error": "Document text/version could not be loaded.",
                    }
                )
                continue
            result = analyze_and_persist_regulatory_graph(
                session,
                _graph_input(row),
                use_ai=use_ai,
                skip_completed=True,
            )
            results.append(
                {
                    "document_id": document_id,
                    "status": result.status,
                    "used_ai": result.used_ai,
                    "error": result.error,
                    "latency_ms": result.latency_ms,
                    "entities": result.entity_count,
                    "edges": result.relationship_count,
                    "deadlines": result.deadline_count,
                    "stakeholders": result.stakeholder_count,
                    "obligations": result.obligation_count,
                }
            )

    status_counts = Counter(str(result["status"]) for result in results)
    return {
        "requested_limit": limit,
        "failed_documents_found": len(document_ids),
        "processed": len(results),
        "status_counts": dict(status_counts),
        "results": results,
    }


def _failed_document_ids(*, limit: int) -> list[int]:
    with session_scope() as session:
        rows = session.execute(
            text(
                """
                select document_id
                from regulatory_graph_extractions
                where status = :status
                order by updated_at nulls first, document_id
                limit :limit
                """
            ),
            {"status": GRAPH_STATUS_FAILED, "limit": limit},
        ).mappings()
        return [int(row["document_id"]) for row in rows]


def _current_status(session: Any, document_id: int) -> str | None:
    row = session.execute(
        text(
            """
            select status
            from regulatory_graph_extractions
            where document_id = :document_id
            """
        ),
        {"document_id": document_id},
    ).mappings().first()
    return str(row["status"]) if row else None


def _load_graph_input_row(session: Any, document_id: int) -> dict[str, Any] | None:
    row = session.execute(
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
            left join document_texts dt on dt.content_hash = dv.content_hash
            left join document_family_assignments a on a.document_id = d.id
            where d.id = :document_id
            """
        ),
        {"document_id": document_id},
    ).mappings().first()
    return dict(row) if row else None


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
