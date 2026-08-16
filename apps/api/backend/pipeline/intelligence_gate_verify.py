"""Read-only intelligence-gate diagnostics for stored documents.

Loads durable document text, reconstructs acquisition classification via
``classify_candidate``, and runs ``assess_event_intelligence``. Never writes.
"""

from __future__ import annotations

from datetime import date
from typing import Any, Mapping

from sqlalchemy import text

from backend.core.db import session_scope
from backend.core.models import DiscoveredDoc, ExtractedDoc, FetchedFile
from backend.core.repository import _summary_from_extracted, _topic_tags
from backend.pipeline.intelligence_gate import assess_event_intelligence
from backend.pipeline.quality_gate import classify_candidate


def load_document_row_for_verify(document_id: int) -> dict[str, Any] | None:
    """SELECT-only load of the latest version + text for a document."""

    with session_scope() as session:
        row = session.execute(
            text(
                """
                select
                  d.id as document_id,
                  d.source_id,
                  d.title,
                  d.source_url,
                  d.issuing_body,
                  d.issue_date,
                  d.issue_date_precision::text as issue_date_precision,
                  d.doc_type,
                  d.jurisdiction::text as jurisdiction,
                  s.code as source_code,
                  dv.id as version_id,
                  dv.file_hash,
                  dv.content_hash,
                  dv.raw_file_path,
                  dv.text_path,
                  dv.page_count,
                  dv.needs_ocr,
                  dv.http_status,
                  coalesce(dt.text_content, '') as text_content
                from documents d
                left join sources s on s.id = d.source_id
                join lateral (
                  select *
                  from document_versions
                  where document_id = d.id
                  order by fetched_at desc
                  limit 1
                ) dv on true
                left join document_texts dt on dt.content_hash = dv.content_hash
                where d.id = :document_id
                """
            ),
            {"document_id": document_id},
        ).mappings().first()
        return dict(row) if row else None


def build_extracted_doc_for_verify(row: Mapping[str, Any]) -> ExtractedDoc:
    """Rebuild ExtractedDoc the way acquisition would: classify from stored text."""

    text_content = str(row.get("text_content") or "")
    if not text_content.strip():
        raise ValueError("Document has no stored text_content for intelligence verify.")

    discovered = DiscoveredDoc(
        source_code=str(row.get("source_code") or "unknown"),
        title=str(row["title"]),
        source_url=str(row["source_url"]),
        issuing_body=row.get("issuing_body"),
        issue_date=row.get("issue_date"),
        issue_date_precision=row.get("issue_date_precision") or "unknown",
        doc_type=row.get("doc_type"),
        jurisdiction=row.get("jurisdiction"),
    )
    quality = classify_candidate(discovered, content_text=text_content)
    fetched = FetchedFile(
        discovered=discovered,
        file_hash=str(row.get("file_hash") or row["content_hash"]),
        raw_file_path=str(row.get("raw_file_path") or ""),
        http_status=int(row.get("http_status") or 200),
    )
    return ExtractedDoc(
        fetched=fetched,
        text=text_content,
        content_hash=str(row["content_hash"]),
        page_count=int(row.get("page_count") or 0),
        needs_ocr=bool(row.get("needs_ocr")),
        text_path=str(row.get("text_path") or ""),
        classification=quality.classification,
        quality_score=float(quality.confidence),
        evidence_excerpt=text_content[:600],
    )


def diagnose_document_intelligence(
    document_id: int,
    *,
    today: date | None = None,
    row: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Assess whether a stored document would pass the intelligence gate.

    Read-only: never inserts events, audits, RAG jobs, or notifications.
    """

    loaded = dict(row) if row is not None else load_document_row_for_verify(document_id)
    if loaded is None:
        return {
            "document_id": document_id,
            "status": "NOT_FOUND",
            "error": "Document/version/text could not be loaded.",
            "classification": None,
            "actionability": None,
            "freshness": None,
            "quality_score": None,
            "rejection_reason": None,
            "event_allowed": None,
            "would_reject_as_expired_opportunity": None,
            "read_only": True,
        }

    extracted = build_extracted_doc_for_verify(loaded)
    topics = _topic_tags(f"{extracted.fetched.discovered.title}\n{extracted.text}")
    summary = _summary_from_extracted(extracted)
    intelligence = assess_event_intelligence(
        extracted,
        topics=topics,
        summary=summary,
        today=today,
    )
    return {
        "document_id": int(loaded["document_id"]),
        "status": "OK",
        "source_id": loaded.get("source_id"),
        "source_url": loaded.get("source_url"),
        "title": loaded.get("title"),
        "version_id": loaded.get("version_id"),
        "classification": extracted.classification,
        "actionability": intelligence.actionability,
        "freshness": intelligence.freshness,
        "quality_score": intelligence.quality_score,
        "rejection_reason": intelligence.rejection_reason,
        "event_allowed": intelligence.event_allowed,
        "would_reject_as_expired_opportunity": (
            intelligence.rejection_reason == "EXPIRED_OPPORTUNITY"
        ),
        "read_only": True,
    }
