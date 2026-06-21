from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import text

from backend.core.db import session_scope
from backend.core.models import DiscoveredDoc, ExtractedDoc, FetchedFile, SummaryPayload
from backend.core.repository import record_event_intelligence_audit
from backend.core.utils import sha256_normalized_text
from backend.pipeline.intelligence_gate import assess_event_intelligence
from backend.pipeline.quality_gate import classify_candidate

REPORT_PATH = Path("E:/RegulatoryAi/reports/STEP15_EVENT_INTELLIGENCE_AUDIT.md")
PRIMARY_TEXT_MIN_CHARS = 250


@dataclass
class AuditedEvent:
    event_id: int
    title: str
    issuer: str
    source_url: str
    accepted: bool
    rejection_reason: str | None
    freshness: str
    significance_score: int
    significance_category: str
    actionability: str
    quality_score: int
    quality_category: str
    is_index_document: bool
    content_length: int
    deadlines: list[dict]
    summary: str
    why_it_matters: str


def main() -> None:
    rows = _load_active_events()
    audited = [_audit_row(row) for row in rows]
    report = _markdown_report(audited)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(report, encoding="utf-8")
    print(report)


def _load_active_events() -> list[dict]:
    with session_scope() as session:
        rows = session.execute(
            text(
                """
                select
                  e.id,
                  e.raw_summary,
                  e.topic_tags,
                  e.digest_origin,
                  d.id as document_id,
                  d.title,
                  d.issuing_body,
                  d.jurisdiction::text as jurisdiction,
                  d.issue_date,
                  d.issue_date_precision::text as issue_date_precision,
                  d.doc_type,
                  d.source_url,
                  dv.id as version_id,
                  dv.file_hash,
                  dv.raw_file_path,
                  dv.text_path,
                  dv.page_count,
                  dv.needs_ocr,
                  dv.http_status,
                  dv.content_hash,
                  coalesce(dt.content_length, 0) as content_length,
                  dt.text_content,
                  sm.summary_json
                from events e
                join documents d on d.id = e.document_id
                left join document_versions dv on dv.id = e.version_id
                left join document_texts dt on dt.content_hash = dv.content_hash
                left join lateral (
                  select summary_json
                  from summaries
                  where event_id = e.id
                  order by created_at desc
                  limit 1
                ) sm on true
                where e.suppressed = false
                order by e.id
                """
            )
        ).mappings()
        return [dict(row) for row in rows]


def _audit_row(row: dict) -> AuditedEvent:
    text_content = row.get("text_content") or ""
    content_length = int(row.get("content_length") or 0)
    primary_text_missing = content_length < PRIMARY_TEXT_MIN_CHARS
    candidate = DiscoveredDoc(
        source_code=row.get("digest_origin") or "unknown",
        title=row["title"],
        source_url=row["source_url"],
        issuing_body=row.get("issuing_body"),
        issue_date=row.get("issue_date"),
        issue_date_precision=row.get("issue_date_precision") or "unknown",
        doc_type=row.get("doc_type") or _doc_type(row["source_url"]),
        jurisdiction=row.get("jurisdiction"),
        raw_summary=row.get("raw_summary"),
    )
    classifier_text = text_content if text_content else row.get("raw_summary")
    primary_quality = classify_candidate(candidate, content_text=classifier_text)
    fallback_text = text_content or row.get("raw_summary") or row["title"]
    content_hash = row.get("content_hash") or sha256_normalized_text(fallback_text)
    extracted = ExtractedDoc(
        fetched=FetchedFile(
            discovered=candidate,
            file_hash=row.get("file_hash") or content_hash,
            raw_file_path=row.get("raw_file_path") or "",
            http_status=row.get("http_status") or 200,
        ),
        text=fallback_text,
        content_hash=content_hash,
        page_count=row.get("page_count") or 1,
        needs_ocr=bool(row.get("needs_ocr")),
        text_path=row.get("text_path") or "",
        classification=primary_quality.classification,
        quality_score=primary_quality.confidence,
        evidence_excerpt=fallback_text[:600],
    )
    summary_payload = _summary_payload(row.get("summary_json"))
    assessment = assess_event_intelligence(
        extracted,
        topics=list(row.get("topic_tags") or []),
        summary=summary_payload,
    )
    primary_rejection = None
    if not primary_quality.is_valid_event_source:
        primary_rejection = primary_quality.reason_code
    elif primary_text_missing:
        primary_rejection = "NO_PRIMARY_DOCUMENT"
    if primary_rejection:
        assessment = assessment.model_copy(
            update={
                "event_allowed": False,
                "rejection_reason": primary_rejection,
                "quality_score": min(assessment.quality_score, 30),
                "quality_category": "REJECT",
                "reasons": [primary_rejection, *assessment.reasons],
            }
        )
    record_event_intelligence_audit(
        event_id=row["id"],
        document_id=row.get("document_id"),
        version_id=row.get("version_id"),
        source_url=row["source_url"],
        content_hash=row.get("content_hash"),
        title=row["title"],
        intelligence=assessment,
    )
    return AuditedEvent(
        event_id=row["id"],
        title=row["title"],
        issuer=row.get("issuing_body") or "",
        source_url=row["source_url"],
        accepted=assessment.event_allowed,
        rejection_reason=assessment.rejection_reason,
        freshness=assessment.freshness,
        significance_score=assessment.significance_score,
        significance_category=assessment.significance_category,
        actionability=assessment.actionability,
        quality_score=assessment.quality_score,
        quality_category=assessment.quality_category,
        is_index_document=assessment.is_index_document,
        content_length=content_length,
        deadlines=[item.model_dump(mode="json") for item in assessment.deadlines[:8]],
        summary=_summary_text(summary_payload, row),
        why_it_matters=(summary_payload.why_it_matters if summary_payload else ""),
    )


def _markdown_report(events: list[AuditedEvent]) -> str:
    accepted = [event for event in events if event.accepted]
    rejected = [event for event in events if not event.accepted]
    reason_counts = Counter(event.rejection_reason or "ACCEPTED" for event in events)
    freshness_counts = Counter(event.freshness for event in events)
    quality_counts = Counter(event.quality_category for event in events)
    lines = [
        "# Step 15 Event Intelligence Audit",
        "",
        f"Generated at: {datetime.now(UTC).isoformat()}",
        "",
        "## Before / After Survival",
        "",
        f"- Active events before intelligence gate: {len(events)}",
        f"- Events accepted after intelligence gate: {len(accepted)}",
        f"- Events rejected after intelligence gate: {len(rejected)}",
        f"- Survival rate: {_pct(len(accepted), len(events)):.1f}%",
        "",
        "## Freshness Mix",
        "",
    ]
    lines.extend(f"- {name}: {count}" for name, count in freshness_counts.most_common())
    lines.extend(["", "## Quality Mix", ""])
    lines.extend(f"- {name}: {count}" for name, count in quality_counts.most_common())
    lines.extend(["", "## Rejection Reasons", ""])
    lines.extend(
        f"- {name}: {count}"
        for name, count in reason_counts.most_common()
        if name != "ACCEPTED"
    )
    lines.extend(["", "## Event 24 / 25 / 26 Evaluation", ""])
    for event in [item for item in events if item.event_id in {24, 25, 26}]:
        lines.extend(_event_block(event))
    lines.extend(["", "## Accepted", ""])
    if not accepted:
        lines.append("- None.")
    else:
        for event in accepted:
            lines.append(
                f"- Event {event.event_id}: {event.title} "
                f"(quality {event.quality_score}, {event.freshness}, "
                f"{event.significance_category})"
            )
    lines.extend(["", "## Rejected", ""])
    for event in rejected:
        lines.append(
            f"- Event {event.event_id}: {event.title} "
            f"(reason {event.rejection_reason}, quality {event.quality_score}, "
            f"freshness {event.freshness})"
        )
    lines.extend(["", "## Examples", ""])
    for event in rejected[:8]:
        lines.extend(_event_block(event))
    return "\n".join(lines)


def _event_block(event: AuditedEvent) -> list[str]:
    deadline_bits = [
        f"{item.get('raw_date')} [{item.get('deadline_type')}, {item.get('confidence')}]"
        for item in event.deadlines[:4]
    ]
    return [
        f"### Event {event.event_id}: {event.title}",
        "",
        f"- Issuer: {event.issuer}",
        f"- Decision: {'ACCEPTED' if event.accepted else 'REJECTED'}",
        f"- Rejection reason: {event.rejection_reason or ''}",
        f"- Freshness: {event.freshness}",
        f"- Significance: {event.significance_score} ({event.significance_category})",
        f"- Actionability: {event.actionability}",
        f"- Quality: {event.quality_score} ({event.quality_category})",
        f"- Index document: {event.is_index_document}",
        f"- Primary text length: {event.content_length}",
        f"- Deadlines: {', '.join(deadline_bits) if deadline_bits else 'none'}",
        f"- Summary: {_clip(event.summary)}",
        f"- Why it matters: {_clip(event.why_it_matters)}",
        f"- Source: {event.source_url}",
        "",
    ]


def _summary_payload(value: object) -> SummaryPayload | None:
    if not value:
        return None
    if isinstance(value, SummaryPayload):
        return value
    if isinstance(value, str):
        value = json.loads(value)
    return SummaryPayload.model_validate(value)


def _summary_text(summary: SummaryPayload | None, row: dict) -> str:
    if summary:
        return summary.plain_english_summary
    return row.get("raw_summary") or ""


def _doc_type(url: str) -> str:
    return "pdf" if url.lower().split("?", 1)[0].endswith(".pdf") else "html"


def _clip(value: str, limit: int = 450) -> str:
    value = " ".join((value or "").split())
    if len(value) <= limit:
        return value
    return value[:limit].rstrip() + "..."


def _pct(part: int, total: int) -> float:
    if total == 0:
        return 0.0
    return (part / total) * 100


if __name__ == "__main__":
    main()
