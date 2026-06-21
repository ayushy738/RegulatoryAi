from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import text

from backend.core.db import session_scope
from backend.pipeline.family_registry import RegistryInput, register_document_version_family

REPORT_PATH = Path("E:/RegulatoryAi/reports/STEP18_DOCUMENT_FAMILY_REGISTRY.md")


def main() -> None:
    with session_scope() as session:
        before = _registry_counts(session)
        rows = _load_documents(session)
        results = []
        for row in rows:
            result = register_document_version_family(session, _registry_input(row))
            results.append(result)
        after = _registry_counts(session)
        quality = _quality_snapshot(session)
        examples = _examples(session)

    report = _markdown_report(
        before=before,
        after=after,
        rows=rows,
        results=results,
        quality=quality,
        examples=examples,
    )
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(report, encoding="utf-8")
    print(report)


def _load_documents(session) -> list[dict]:
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
              d.first_seen_at,
              coalesce(s.code, e.digest_origin, 'unknown') as source_code,
              dv.id as document_version_id,
              dv.content_hash,
              dv.fetched_at,
              coalesce(dt.content_length, 0) as content_length,
              coalesce(dt.text_content, e.raw_summary, '') as text_content
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
              select raw_summary, digest_origin
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


def _registry_input(row: dict) -> RegistryInput:
    return RegistryInput(
        document_id=row["document_id"],
        document_version_id=row.get("document_version_id"),
        title=row["title"],
        issuer=row.get("issuing_body"),
        source_url=row["source_url"],
        document_type=row.get("doc_type"),
        issue_date=row.get("issue_date"),
        content_hash=row.get("content_hash"),
        text_content=row.get("text_content"),
        content_length=row.get("content_length") or 0,
        first_seen_at=row.get("first_seen_at"),
        fetched_at=row.get("fetched_at"),
    )


def _registry_counts(session) -> dict:
    row = session.execute(
        text(
            """
            select
              (select count(*) from document_families) as families,
              (select count(*) from document_family_assignments) as assignments,
              (select count(*) from document_version_registry) as registry_versions,
              (select count(*) from document_version_relationships) as relationships,
              (select count(*) from deadline_history) as deadlines
            """
        )
    ).mappings().first()
    return dict(row)


def _quality_snapshot(session) -> dict:
    row = session.execute(
        text(
            """
            with family_versions as (
              select family_id, count(*) as version_count
              from document_version_registry
              group by family_id
            ),
            amendment_families as (
              select distinct family_id
              from document_version_registry
              where amendment_number is not null
                 or lower(coalesce(version_label, '')) like '%amendment%'
            ),
            deadline_families as (
              select distinct family_id
              from deadline_history
            )
            select
              (select count(*) from documents) as documents,
              (select count(*) from document_families) as families,
              coalesce(avg(version_count), 0) as avg_versions_per_family,
              count(*) filter (where version_count > 1) as families_with_multiple_versions,
              (select count(*) from amendment_families) as families_with_amendment_chains,
              (select count(*) from deadline_families) as families_with_deadline_history,
              (select count(*) from document_family_assignments where family_id is not null)
                as documents_assigned,
              (select count(*) from document_family_assignments where family_id is null)
                as documents_unassigned
            from family_versions
            """
        )
    ).mappings().first()
    return dict(row)


def _examples(session) -> dict[str, list[dict]]:
    queries = {
        "amendment_chain": """
            select f.family_id, f.canonical_title, f.issuer,
                   count(v.registry_version_id) as versions,
                   array_agg(v.version_label order by v.version_number nulls last)
                     as labels
            from document_families f
            join document_version_registry v on v.family_id = f.family_id
            where v.amendment_number is not null
               or lower(coalesce(v.version_label, '')) like '%amendment%'
            group by f.family_id, f.canonical_title, f.issuer
            order by versions desc, f.family_id
            limit 5
        """,
        "multiple_versions": """
            select f.family_id, f.canonical_title, f.issuer,
                   count(v.registry_version_id) as versions,
                   array_agg(v.version_label order by v.version_number nulls last)
                     as labels
            from document_families f
            join document_version_registry v on v.family_id = f.family_id
            group by f.family_id, f.canonical_title, f.issuer
            having count(v.registry_version_id) > 1
            order by versions desc, f.family_id
            limit 5
        """,
        "deadline_history": """
            select f.family_id, f.canonical_title, f.issuer, count(d.deadline_id) as deadlines,
                   array_agg(distinct d.deadline_type) as deadline_types
            from document_families f
            join deadline_history d on d.family_id = f.family_id
            group by f.family_id, f.canonical_title, f.issuer
            order by deadlines desc, f.family_id
            limit 5
        """,
        "unresolved": """
            select a.document_id, d.title, d.issuing_body, a.evidence, a.confidence
            from document_family_assignments a
            join documents d on d.id = a.document_id
            where a.family_id is null
            order by a.confidence asc, a.document_id
            limit 8
        """,
    }
    examples: dict[str, list[dict]] = {}
    for key, query in queries.items():
        rows = session.execute(text(query)).mappings()
        examples[key] = [dict(row) for row in rows]
    return examples


def _markdown_report(
    *,
    before: dict,
    after: dict,
    rows: list[dict],
    results: list,
    quality: dict,
    examples: dict[str, list[dict]],
) -> str:
    assignment_counts = Counter(result.assignment_type for result in results)
    deadline_count = sum(result.deadline_count for result in results)
    amendment_count = sum(1 for result in results if result.amendment_number is not None)
    family_created = after["families"] - before["families"]
    assigned = [result for result in results if result.family_id is not None]
    unassigned = [result for result in results if result.family_id is None]

    lines = [
        "# Step 18 Document Family & Version Registry",
        "",
        f"Generated at: {datetime.now(UTC).isoformat()}",
        "",
        "## What Was Implemented",
        "",
        "- `document_families`: canonical family records for regulatory instruments.",
        "- `document_family_assignments`: document-to-family assignment with confidence.",
        "- `document_version_registry`: version lineage per family.",
        "- `document_version_relationships`: explicit amendment/corrigendum/supersession links.",
        "- `deadline_history`: normalized durable deadline rows.",
        "",
        "## Backfill Summary",
        "",
        f"- Documents processed: {len(rows)}",
        f"- Document families created in this run: {family_created}",
        f"- Total document families now: {after['families']}",
        f"- Documents assigned to families: {len(assigned)}",
        f"- Documents not assigned: {len(unassigned)}",
        f"- Registry versions now: {after['registry_versions']}",
        f"- Version relationships now: {after['relationships']}",
        f"- Deadline history rows now: {after['deadlines']}",
        f"- Deadline rows discovered during assignment pass: {deadline_count}",
        f"- Amendment/corrigendum/addendum signals discovered: {amendment_count}",
        "",
        "## Assignment Mix",
        "",
    ]
    lines.extend(f"- {name}: {count}" for name, count in assignment_counts.most_common())
    lines.extend(
        [
            "",
            "## Quality Audit",
            "",
            f"- Documents: {quality['documents']}",
            f"- Families: {quality['families']}",
            f"- Average versions per family: {float(quality['avg_versions_per_family']):.2f}",
            f"- Families with multiple versions: {quality['families_with_multiple_versions']}",
            f"- Families with amendment chains: {quality['families_with_amendment_chains']}",
            f"- Families with deadline history: {quality['families_with_deadline_history']}",
            "",
            "## Assignment Details",
            "",
            "| Document | Assignment | Confidence | Family | Evidence |",
            "|---:|---|---:|---|---|",
        ]
    )
    for result in results:
        lines.append(
            f"| {result.document_id} | {result.assignment_type} | {result.confidence:.2f} | "
            f"{result.canonical_title or ''} | {_clip(result.evidence, 120)} |"
        )
    lines.extend(["", "## Examples", ""])
    _append_examples(lines, "Family with amendment chain", examples["amendment_chain"])
    _append_examples(lines, "Family with multiple versions", examples["multiple_versions"])
    _append_examples(lines, "Family with deadline history", examples["deadline_history"])
    _append_examples(lines, "Family that could not be resolved", examples["unresolved"])
    lines.extend(
        [
            "",
            "## Readiness Assessment",
            "",
            "Choice: **PARTIALLY**.",
            "",
            "The registry now gives the system durable places to store family identity, version "
            "lineage, amendment relationships, supersession relationships, and normalized "
            "deadline history. That is the missing foundation Step 17 identified.",
            "",
            "However, the current corpus still has very little usable lineage: most stored "
            "documents are old crawler artifacts or singletons, and only a small number have "
            "primary extracted text. Genuine version-aware change detection becomes possible "
            "for future crawls once the same family receives multiple clean primary-document "
            "versions.",
        ]
    )
    return "\n".join(lines)


def _append_examples(lines: list[str], title: str, rows: list[dict]) -> None:
    lines.extend([f"### {title}", ""])
    if not rows:
        lines.extend(["- None found in the current corpus.", ""])
        return
    for row in rows:
        label = (
            row.get("canonical_title")
            or row.get("title")
            or f"document {row.get('document_id')}"
        )
        details = []
        if row.get("issuer"):
            details.append(f"issuer: {row['issuer']}")
        if row.get("versions"):
            details.append(f"versions: {row['versions']}")
        if row.get("deadlines"):
            details.append(f"deadlines: {row['deadlines']}")
        if row.get("deadline_types"):
            details.append(f"types: {', '.join(row['deadline_types'])}")
        if row.get("evidence"):
            details.append(f"evidence: {_clip(row['evidence'], 180)}")
        lines.append(f"- {label} ({'; '.join(details)})")
    lines.append("")


def _clip(value: object, limit: int = 220) -> str:
    value = " ".join(str(value or "").split())
    return value if len(value) <= limit else value[:limit].rstrip() + "..."


if __name__ == "__main__":
    main()
