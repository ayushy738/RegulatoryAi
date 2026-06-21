from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import text

from backend.core.db import session_scope
from backend.core.models import (
    DiscoveredDoc,
    ExtractedDoc,
    FetchedFile,
    PriorVersionReference,
    RegulatoryChange,
)
from backend.core.repository import record_regulatory_change_audit
from backend.core.utils import sha256_normalized_text
from backend.pipeline.change_detector import (
    detect_regulatory_change,
    is_related_title,
    title_similarity,
)
from backend.pipeline.intelligence_gate import assess_event_intelligence
from backend.pipeline.quality_gate import classify_candidate

REPORT_PATH = Path("E:/RegulatoryAi/reports/STEP16_CHANGE_DETECTION_AUDIT.md")
PRIMARY_TEXT_MIN_CHARS = 250
EXAMPLE_TYPES = [
    "NEW_DOCUMENT",
    "AMENDMENT",
    "DEADLINE_CHANGE",
    "CORRIGENDUM",
    "REISSUED_DOCUMENT",
    "NO_MATERIAL_CHANGE",
]


@dataclass
class BacktestResult:
    document_id: int
    version_id: int | None
    event_id: int | None
    title: str
    issuer: str
    source_url: str
    content_length: int
    prior_reference: PriorVersionReference | None
    change: RegulatoryChange
    freshness: str
    intelligence_allowed: bool
    primary_text_present: bool
    would_generate_event: bool
    false_positive: bool


def main() -> None:
    rows = _load_documents()
    results = _run_backtest(rows)
    report = _markdown_report(results)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(report, encoding="utf-8")
    print(report)


def _load_documents() -> list[dict]:
    with session_scope() as session:
        rows = session.execute(
            text(
                """
                select
                  d.id as document_id,
                  d.title,
                  d.issuing_body,
                  d.jurisdiction::text as jurisdiction,
                  d.issue_date,
                  d.issue_date_precision::text as issue_date_precision,
                  d.doc_type,
                  d.source_url,
                  coalesce(s.code, e.digest_origin, 'unknown') as source_code,
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
                  prior.version_id as prior_version_id,
                  prior.content_hash as prior_content_hash,
                  prior.text_content as prior_text_content,
                  e.id as event_id,
                  e.raw_summary,
                  e.topic_tags
                from documents d
                left join sources s on s.id = d.source_id
                left join lateral (
                  select *
                  from document_versions
                  where document_id = d.id
                  order by fetched_at desc
                  limit 1
                ) dv on true
                left join document_texts dt on dt.content_hash = dv.content_hash
                left join lateral (
                  select
                    pv.id as version_id,
                    pv.content_hash,
                    pdt.text_content
                  from document_versions pv
                  left join document_texts pdt on pdt.content_hash = pv.content_hash
                  where pv.document_id = d.id
                    and (dv.id is null or pv.id <> dv.id)
                  order by pv.fetched_at desc
                  limit 1
                ) prior on true
                left join lateral (
                  select id, raw_summary, topic_tags, digest_origin
                  from events
                  where document_id = d.id
                  order by detected_at desc
                  limit 1
                ) e on true
                order by d.id
                """
            )
        ).mappings()
        return [dict(row) for row in rows]


def _run_backtest(rows: list[dict]) -> list[BacktestResult]:
    results: list[BacktestResult] = []
    for row in rows:
        extracted = _row_to_extracted(row)
        prior = _same_document_prior(row) or _related_prior(row, rows)
        change = detect_regulatory_change(extracted, prior=prior)
        intelligence = assess_event_intelligence(
            extracted,
            topics=list(row.get("topic_tags") or []),
        )
        primary_present = int(row.get("content_length") or 0) >= PRIMARY_TEXT_MIN_CHARS
        would_generate = (
            primary_present
            and change.is_material
            and change.change_type != "NO_MATERIAL_CHANGE"
            and intelligence.event_allowed
        )
        false_positive = (
            change.is_material
            and change.change_type != "NO_MATERIAL_CHANGE"
            and not would_generate
        )
        record_regulatory_change_audit(
            event_id=row.get("event_id"),
            document_id=row["document_id"],
            version_id=row.get("version_id"),
            source_url=row["source_url"],
            content_hash=row.get("content_hash"),
            title=row["title"],
            change=change,
        )
        results.append(
            BacktestResult(
                document_id=row["document_id"],
                version_id=row.get("version_id"),
                event_id=row.get("event_id"),
                title=row["title"],
                issuer=row.get("issuing_body") or "",
                source_url=row["source_url"],
                content_length=int(row.get("content_length") or 0),
                prior_reference=prior,
                change=change,
                freshness=intelligence.freshness,
                intelligence_allowed=intelligence.event_allowed,
                primary_text_present=primary_present,
                would_generate_event=would_generate,
                false_positive=false_positive,
            )
        )
    return results


def _row_to_extracted(row: dict) -> ExtractedDoc:
    fallback_text = row.get("text_content") or row.get("raw_summary") or row["title"]
    candidate = DiscoveredDoc(
        source_code=row.get("source_code") or "unknown",
        title=row["title"],
        source_url=row["source_url"],
        issuing_body=row.get("issuing_body"),
        issue_date=row.get("issue_date"),
        issue_date_precision=row.get("issue_date_precision") or "unknown",
        doc_type=row.get("doc_type") or _doc_type(row["source_url"]),
        jurisdiction=row.get("jurisdiction"),
        raw_summary=row.get("raw_summary"),
    )
    quality = classify_candidate(candidate, content_text=fallback_text)
    content_hash = row.get("content_hash") or sha256_normalized_text(fallback_text)
    return ExtractedDoc(
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
        classification=quality.classification,
        quality_score=quality.confidence,
        evidence_excerpt=fallback_text[:600],
    )


def _same_document_prior(row: dict) -> PriorVersionReference | None:
    if not row.get("prior_version_id"):
        return None
    return PriorVersionReference(
        document_id=row["document_id"],
        version_id=row.get("prior_version_id"),
        title=row["title"],
        source_url=row["source_url"],
        content_hash=row.get("prior_content_hash"),
        text=row.get("prior_text_content"),
        reference_type="same_url",
    )


def _related_prior(row: dict, rows: list[dict]) -> PriorVersionReference | None:
    best_row: dict | None = None
    best_score = 0.0
    for candidate in rows:
        if candidate["document_id"] == row["document_id"]:
            continue
        if not candidate.get("text_content"):
            continue
        same_source = candidate.get("source_code") == row.get("source_code")
        same_issuer = candidate.get("issuing_body") and candidate.get("issuing_body") == row.get(
            "issuing_body"
        )
        if not same_source and not same_issuer:
            continue
        score = title_similarity(row["title"], candidate["title"])
        if score > best_score and is_related_title(row["title"], candidate["title"]):
            best_score = score
            best_row = candidate
    if not best_row:
        return None
    return PriorVersionReference(
        document_id=best_row["document_id"],
        version_id=best_row.get("version_id"),
        title=best_row["title"],
        source_url=best_row["source_url"],
        content_hash=best_row.get("content_hash"),
        text=best_row.get("text_content"),
        similarity_score=best_score,
        reference_type="related_document",
    )


def _markdown_report(results: list[BacktestResult]) -> str:
    meaningful = [item for item in results if item.change.is_material]
    generating = [item for item in results if item.would_generate_event]
    no_material = [item for item in results if not item.change.is_material]
    historical = [item for item in results if item.freshness in {"HISTORICAL", "ARCHIVAL"}]
    comparisons = [item for item in results if item.prior_reference]
    false_positives = [item for item in results if item.false_positive]
    change_counts = Counter(item.change.change_type for item in results)
    freshness_counts = Counter(item.freshness for item in results)
    lines = [
        "# Step 16 Regulatory Change Detection Backtest",
        "",
        f"Generated at: {datetime.now(UTC).isoformat()}",
        "",
        "## Engine Logic",
        "",
        "- Change types: NEW_DOCUMENT, UPDATED_DOCUMENT, AMENDMENT, CORRIGENDUM, "
        "ADDENDUM, DEADLINE_CHANGE, TENDER_UPDATE, CONSULTATION_UPDATE, POLICY_UPDATE, "
        "WITHDRAWAL, REISSUED_DOCUMENT, NO_MATERIAL_CHANGE.",
        "- Version comparison uses same-document prior versions first, then related-document "
        "title similarity within the same source or issuer.",
        "- Material change detection ignores exact content-hash matches and near-identical "
        "text unless deadline, amendment, tender, consultation, tariff, compliance, "
        "withdrawal, or supersession signals are present.",
        "- Deadline intelligence compares typed deadlines and classifies ADDED, REMOVED, "
        "EXTENDED, or SHORTENED changes.",
        "- Event generation requires primary text, a material change, and Step 15 "
        "intelligence approval.",
        "",
        "## Metrics",
        "",
        f"- Total documents analyzed: {len(results)}",
        f"- Total version comparisons: {len(comparisons)}",
        f"- Documents with no material change: {len(no_material)}",
        f"- Documents classified as historical/archival: {len(historical)}",
        f"- Meaningful changes detected before quality gates: {len(meaningful)}",
        f"- Meaningful change events surviving all gates: {len(generating)}",
        f"- False positives identified by later gates: {len(false_positives)}",
        f"- Event survival rate after change detection: {_pct(len(generating), len(results)):.1f}%",
        "",
        "## Change Type Mix",
        "",
    ]
    lines.extend(f"- {name}: {count}" for name, count in change_counts.most_common())
    lines.extend(["", "## Freshness Mix", ""])
    lines.extend(f"- {name}: {count}" for name, count in freshness_counts.most_common())
    lines.extend(["", "## Meaningful Events That Would Be Generated", ""])
    if generating:
        for item in generating:
            lines.extend(_result_block(item))
    else:
        lines.append(
            "- None. Current stored documents do not survive the Step 15 intelligence gate."
        )
    lines.extend(["", "## Requested Examples", ""])
    by_type: dict[str, list[BacktestResult]] = defaultdict(list)
    for item in results:
        by_type[item.change.change_type].append(item)
    for change_type in EXAMPLE_TYPES:
        lines.append(f"### {change_type}")
        lines.append("")
        examples = by_type.get(change_type) or []
        if not examples:
            lines.append(f"- No {change_type} example exists in the current stored corpus.")
            lines.append("")
            continue
        for item in examples[:2]:
            lines.extend(_result_block(item))
    lines.extend(["", "## False Positives Blocked", ""])
    if false_positives:
        for item in false_positives[:12]:
            lines.append(
                f"- Document {item.document_id}: {item.title} "
                f"({item.change.change_type}, freshness {item.freshness}, "
                f"primary_text={item.primary_text_present})"
            )
    else:
        lines.append("- None.")
    return "\n".join(lines)


def _result_block(item: BacktestResult) -> list[str]:
    prior = item.prior_reference
    prior_label = prior.source_url if prior and prior.source_url else "none"
    deadlines = [
        f"{change.deadline_type} {change.change}: {change.old_date} -> {change.new_date}"
        for change in item.change.deadline_changes
    ]
    return [
        f"- Document {item.document_id}: {item.title}",
        f"  - Issuer: {item.issuer}",
        f"  - Change type: {item.change.change_type}",
        f"  - Material: {item.change.is_material}",
        f"  - Confidence: {item.change.confidence}",
        f"  - Prior reference: {prior_label}",
        f"  - Previous state: {item.change.previous_state or ''}",
        f"  - New state: {item.change.new_state or ''}",
        f"  - Why it matters: {item.change.why_it_matters}",
        f"  - Affected: {', '.join(item.change.affected_parties) or 'unknown'}",
        f"  - Deadlines: {'; '.join(deadlines) if deadlines else 'none'}",
        f"  - Evidence: {_clip(item.change.evidence)}",
        f"  - Would generate event: {item.would_generate_event}",
        "",
    ]


def _doc_type(url: str) -> str:
    return "pdf" if url.lower().split("?", 1)[0].endswith(".pdf") else "html"


def _clip(value: str, limit: int = 420) -> str:
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
