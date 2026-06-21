from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import text

from backend.core.db import session_scope
from backend.core.models import DiscoveredDoc
from backend.pipeline.quality_gate import classify_candidate


@dataclass
class ClassifiedEvent:
    id: int
    title: str
    source_url: str
    classification: str
    survives: bool
    reason: str
    has_primary_content: bool
    content_length: int


def main() -> None:
    events = _load_events()
    classified = [_classify(row) for row in events]
    print(_markdown_report(classified))


def _load_events() -> list[dict]:
    with session_scope() as session:
        rows = session.execute(
            text(
                """
                select
                  e.id,
                  e.raw_summary,
                  d.title,
                  d.source_url,
                  d.issuing_body,
                  d.issue_date,
                  coalesce(s.code, e.digest_origin, 'unknown') as source_code,
                  dv.text_path,
                  dv.page_count,
                  dv.content_hash,
                  coalesce(dt.content_length, 0) as content_length,
                  left(dt.text_content, 5000) as text_excerpt
                from events e
                join documents d on d.id = e.document_id
                left join sources s on s.id = d.source_id
                left join document_versions dv on dv.id = e.version_id
                left join document_texts dt on dt.content_hash = dv.content_hash
                where e.suppressed = false
                order by e.detected_at desc
                """
            )
        ).mappings()
        return [dict(row) for row in rows]


def _classify(row: dict) -> ClassifiedEvent:
    candidate = DiscoveredDoc(
        source_code=row["source_code"],
        title=row["title"],
        source_url=row["source_url"],
        issuing_body=row["issuing_body"],
        issue_date=row["issue_date"],
        doc_type="pdf" if str(row["source_url"]).lower().endswith(".pdf") else "html",
        raw_summary=row["raw_summary"],
    )
    quality = classify_candidate(candidate, content_text=row.get("text_excerpt") or None)
    has_primary = bool(
        row.get("text_path")
        and row.get("content_hash")
        and (row.get("content_length") or 0) >= 250
    )
    if not quality.is_valid_event_source:
        survives = False
        reason = quality.reason_code
    elif not has_primary:
        survives = False
        reason = "NO_PRIMARY_DOCUMENT"
    else:
        survives = True
        reason = "SURVIVES_PRIMARY_DOCUMENT_GATE"
    return ClassifiedEvent(
        id=row["id"],
        title=row["title"],
        source_url=row["source_url"],
        classification=quality.classification,
        survives=survives,
        reason=reason,
        has_primary_content=has_primary,
        content_length=row.get("content_length") or 0,
    )


def _markdown_report(events: list[ClassifiedEvent]) -> str:
    total = len(events)
    survivors = [event for event in events if event.survives]
    rejected = [event for event in events if not event.survives]
    primary_count = sum(1 for event in events if event.has_primary_content)
    link_or_listing = sum(
        1
        for event in events
        if not event.has_primary_content
        and event.reason
        in {
            "HOMEPAGE_DETECTED",
            "LISTING_PAGE_DETECTED",
            "ARCHIVE_PAGE_DETECTED",
            "CATEGORY_PAGE_DETECTED",
            "SEARCH_PAGE_DETECTED",
            "NAVIGATION_PAGE_DETECTED",
        }
    )
    generic = sum(
        1
        for event in events
        if event.classification in {"HOMEPAGE", "LISTING_PAGE", "CATEGORY_PAGE", "NAVIGATION_PAGE"}
    )
    rejection_reasons = Counter(event.reason for event in rejected)
    classifications = Counter(event.classification for event in events)
    rejected_by_bucket = _bucket_rejections(rejected)
    survival_pct = _pct(len(survivors), total)
    rejection_pct = _pct(len(rejected), total)
    disappear_pct = _pct(total - primary_count, total)

    lines = [
        "# Step 13 Event Quality Audit",
        "",
        f"Generated at: {datetime.now(UTC).isoformat()}",
        "",
        "## Event Survival Analysis",
        "",
        f"- Total current events: {total}",
        f"- Events that survive quality gate: {len(survivors)}",
        f"- Events rejected by quality gate: {len(rejected)}",
        f"- Survival percentage: {survival_pct:.1f}%",
        f"- Rejection percentage: {rejection_pct:.1f}%",
        "",
        "## Rejection Breakdown",
        "",
    ]
    for bucket in (
        "HOMEPAGE",
        "LISTING_PAGE",
        "ARCHIVE_PAGE",
        "CATEGORY_PAGE",
        "SEARCH_PAGE",
        "NAVIGATION_PAGE",
        "NO_PRIMARY_DOCUMENT",
        "OTHER",
    ):
        lines.append(f"- {bucket}: {rejected_by_bucket[bucket]}")
    lines.extend(
        [
            "",
            "## Classification Breakdown",
            "",
            *[f"- {name}: {count}" for name, count in classifications.most_common()],
            "",
            "## Rejection Reasons",
            "",
            *[f"- {name}: {count}" for name, count in rejection_reasons.most_common()],
            "",
            "## Primary Document Coverage",
            "",
            f"- Events generated from primary document content: {primary_count}",
            f"- Events generated without stored primary content: {total - primary_count}",
            f"- Likely link/listing-page generated events: {link_or_listing}",
            f"- Generic page-content events: {generic}",
            (
                "- Percentage of events that would disappear if primary-document requirements "
                f"were enforced: {disappear_pct:.1f}%"
            ),
            "",
            "## Surviving Event Examples",
            "",
        ]
    )
    if survivors:
        for event in survivors[:5]:
            lines.extend(_example(event, "Survived because it has stored primary content."))
    else:
        lines.append("- None. No current event has enough stored primary content evidence.")
    lines.extend(["", "## Rejected Event Examples", ""])
    for event in rejected[:8]:
        lines.extend(_example(event, event.reason))
    return "\n".join(lines)


def _bucket_rejections(events: list[ClassifiedEvent]) -> Counter:
    buckets: Counter = Counter()
    for event in events:
        if event.reason == "NO_PRIMARY_DOCUMENT":
            buckets["NO_PRIMARY_DOCUMENT"] += 1
        elif event.classification in {
            "HOMEPAGE",
            "LISTING_PAGE",
            "ARCHIVE_PAGE",
            "CATEGORY_PAGE",
            "SEARCH_PAGE",
            "NAVIGATION_PAGE",
        }:
            buckets[event.classification] += 1
        else:
            buckets["OTHER"] += 1
    return buckets


def _example(event: ClassifiedEvent, why: str) -> list[str]:
    return [
        f"- Title: {event.title}",
        f"  - Classification: {event.classification}",
        f"  - Reason: {why}",
        f"  - Source: {event.source_url}",
    ]


def _pct(part: int, total: int) -> float:
    if total == 0:
        return 0.0
    return (part / total) * 100


if __name__ == "__main__":
    main()
