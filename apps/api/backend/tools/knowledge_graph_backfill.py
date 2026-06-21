from __future__ import annotations

import argparse
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import text

from backend.core.db import session_scope
from backend.pipeline.regulatory_knowledge_graph import (
    GraphInput,
    analyze_and_persist_regulatory_graph,
)

REPORT_PATH = Path("E:/RegulatoryAi/reports/STEP19_AI_REGULATORY_KNOWLEDGE_GRAPH.md")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Backfill AI regulatory knowledge graph records for primary documents."
    )
    parser.add_argument(
        "--no-ai",
        action="store_true",
        help="Use deterministic extraction only.",
    )
    parser.add_argument(
        "--reset-graph",
        action="store_true",
        help="Clear only Step 19 graph tables before backfill.",
    )
    args = parser.parse_args()

    with session_scope() as session:
        if args.reset_graph:
            _reset_graph_tables(session)
        before = _snapshot(session)
        rows = _load_primary_documents(session)
        results = []
        for row in rows:
            result = analyze_and_persist_regulatory_graph(
                session,
                _graph_input(row),
                use_ai=not args.no_ai,
            )
            results.append(result)
        after = _snapshot(session)
        examples = _examples(session)

    report = _markdown_report(
        before=before,
        after=after,
        rows=rows,
        results=results,
        examples=examples,
        ai_requested=not args.no_ai,
    )
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(report, encoding="utf-8")
    print(report)


def _reset_graph_tables(session: Any) -> None:
    session.execute(
        text(
            """
            truncate table
              regulatory_graph_family_enrichment,
              regulatory_graph_deadlines,
              regulatory_graph_obligations,
              regulatory_graph_stakeholders,
              regulatory_graph_extractions,
              regulatory_graph_edges,
              regulatory_graph_document_entities,
              regulatory_graph_entities
            restart identity cascade
            """
        )
    )


def _load_primary_documents(session: Any) -> list[dict[str, Any]]:
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
              and a.family_id is not null
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


def _snapshot(session: Any) -> dict[str, Any]:
    row = session.execute(
        text(
            """
            select
              (select count(*) from regulatory_graph_entities) as entities,
              (select count(*) from regulatory_graph_edges) as edges,
              (select count(*) from regulatory_graph_extractions) as extractions,
              (select count(*) from regulatory_graph_stakeholders) as stakeholders,
              (select count(*) from regulatory_graph_obligations) as obligations,
              (select count(*) from regulatory_graph_deadlines) as graph_deadlines,
              (select count(*) from regulatory_graph_deadlines
               where deadline_date >= current_date) as active_graph_deadlines,
              (select count(*) from regulatory_graph_deadlines
               where deadline_type = 'CONSULTATION_DEADLINE'
                 and deadline_date >= current_date) as active_consultation_deadlines,
              (select count(*) from regulatory_graph_entities
               where entity_type = 'CONSULTATION') as consultation_entities,
              (select count(*) from regulatory_graph_family_enrichment)
                as family_enrichments,
              (select count(*) from regulatory_graph_family_enrichment where applied)
                as family_enrichments_applied,
              (select count(*) from document_families) as document_families,
              (select count(*) from document_family_assignments where family_id is not null)
                as assigned_documents,
              (select count(*) from document_family_assignments where family_id is null)
                as unassigned_documents,
              (select count(*) from document_version_registry) as registry_versions,
              (select count(*) from document_version_relationships) as version_relationships
            """
        )
    ).mappings().first()
    return dict(row)


def _examples(session: Any) -> dict[str, list[dict[str, Any]]]:
    queries = {
        "entity_counts": """
            select entity_type, count(*) as count
            from regulatory_graph_entities
            group by entity_type
            order by count desc, entity_type
        """,
        "relationship_counts": """
            select relationship_type, count(*) as count
            from regulatory_graph_edges
            group by relationship_type
            order by count desc, relationship_type
        """,
        "relationships": """
            select e.relationship_type,
                   source.name as source_entity,
                   target.name as target_entity,
                   e.confidence,
                   e.evidence
            from regulatory_graph_edges e
            join regulatory_graph_entities source on source.entity_id = e.from_entity_id
            join regulatory_graph_entities target on target.entity_id = e.to_entity_id
            where e.relationship_type in
              ('AMENDS', 'SUPERSEDES', 'REFERENCES', 'IMPLEMENTS', 'REPEALS', 'EXTENDS')
            order by e.confidence desc, e.edge_id
            limit 12
        """,
        "family_enrichment": """
            select fe.document_id,
                   d.title,
                   fe.before_family_id,
                   fe.after_family_id,
                   fe.before_assignment_type,
                   fe.after_assignment_type,
                   fe.inferred_family,
                   fe.confidence,
                   fe.applied,
                   fe.evidence
            from regulatory_graph_family_enrichment fe
            join documents d on d.id = fe.document_id
            order by fe.applied desc, fe.confidence desc, fe.document_id
            limit 12
        """,
        "stakeholders": """
            select stakeholder, count(*) as documents, max(confidence) as confidence,
                   max(evidence) as evidence
            from regulatory_graph_stakeholders
            group by stakeholder
            order by documents desc, confidence desc, stakeholder
            limit 12
        """,
        "obligations": """
            select document_id,
                   obligation,
                   affected_party,
                   deadline_date,
                   deadline_type,
                   confidence,
                   evidence
            from regulatory_graph_obligations
            order by confidence desc, obligation_id
            limit 12
        """,
        "deadlines": """
            select document_id,
                   deadline_type,
                   deadline_date,
                   raw_date,
                   confidence,
                   evidence
            from regulatory_graph_deadlines
            order by deadline_date nulls last, confidence desc
            limit 12
        """,
        "amendment_chains": """
            select f.canonical_title,
                   dvr.version_label,
                   dvr.amendment_number,
                   dvr.parent_registry_version_id,
                   dvr.referenced_instrument
            from document_version_registry dvr
            join document_families f on f.family_id = dvr.family_id
            where dvr.amendment_number is not null
               or lower(coalesce(dvr.version_label, '')) like '%amend%'
            order by f.family_id, dvr.version_number nulls last
            limit 12
        """,
    }
    examples: dict[str, list[dict[str, Any]]] = {}
    for key, query in queries.items():
        rows = session.execute(text(query)).mappings()
        examples[key] = [dict(row) for row in rows]
    return examples


def _markdown_report(
    *,
    before: dict[str, Any],
    after: dict[str, Any],
    rows: list[dict[str, Any]],
    results: list[Any],
    examples: dict[str, list[dict[str, Any]]],
    ai_requested: bool,
) -> str:
    status_counts = Counter(result.status for result in results)
    ai_successes = sum(1 for result in results if result.used_ai)
    fallback_count = len(results) - ai_successes
    errors = [result for result in results if result.error]
    family_improvements = [
        result
        for result in results
        if result.family_applied or result.family_before != result.family_after
    ]
    capability = _capability_assessment(examples, after)

    lines = [
        "# Step 19 AI Regulatory Knowledge Graph & Family Resolution",
        "",
        f"Generated at: {datetime.now(UTC).isoformat()}",
        "",
        "## Knowledge Graph Schema",
        "",
        "- `regulatory_graph_entities`: Document, Regulation, Notification, Consultation, "
        "Tender, Stakeholder, Obligation, Deadline, Issuer, and related nodes.",
        "- `regulatory_graph_document_entities`: document-to-entity role links.",
        "- `regulatory_graph_edges`: AMENDS, SUPERSEDES, REFERENCES, IMPLEMENTS, "
        "REPEALS, EXTENDS, AFFECTS, HAS_DEADLINE, HAS_OBLIGATION, ISSUED_BY, and "
        "BELONGS_TO_FAMILY edges.",
        "- `regulatory_graph_extractions`: extraction audit per document with provider, "
        "model, status, JSON payload, and errors.",
        "- `regulatory_graph_stakeholders`: normalized affected-entity rows.",
        "- `regulatory_graph_obligations`: actionable obligation rows.",
        "- `regulatory_graph_deadlines`: graph-level deadline rows.",
        "- `regulatory_graph_family_enrichment`: before/after family-resolution audit.",
        "",
        "## Extraction Architecture",
        "",
        "1. Load accepted primary documents with stored extracted text.",
        "2. Run AI extraction with a strict regulatory graph JSON schema.",
        "3. Merge AI output with deterministic grounded extraction for dates, "
        "stakeholders, obligations, and relationship hints.",
        "4. Persist graph entities and edges.",
        "5. Enrich the Step 18 family registry when AI produces a high-confidence "
        "family resolution.",
        "6. Produce an auditable report showing counts, examples, and readiness.",
        "",
        "## Backfill Summary",
        "",
        f"- AI requested: {'yes' if ai_requested else 'no'}",
        f"- Primary documents processed: {len(rows)}",
        f"- AI successful extractions: {ai_successes}",
        f"- Heuristic/fallback extractions: {fallback_count}",
        f"- Extraction status mix: {_format_counter(status_counts)}",
        f"- Extraction errors: {len(errors)}",
        "",
        "## Entity Counts",
        "",
    ]
    _append_count_table(lines, examples["entity_counts"], "entity_type")
    lines.extend(["", "## Relationship Counts", ""])
    _append_count_table(lines, examples["relationship_counts"], "relationship_type")
    lines.extend(
        [
            "",
            "## Family Enrichment Results",
            "",
            f"- Document families before AI: {before['document_families']}",
            f"- Document families after AI: {after['document_families']}",
            f"- Assigned documents before AI: {before['assigned_documents']}",
            f"- Assigned documents after AI: {after['assigned_documents']}",
            f"- Unassigned documents before AI: {before['unassigned_documents']}",
            f"- Unassigned documents after AI: {after['unassigned_documents']}",
            f"- Family enrichments applied: {after['family_enrichments_applied']}",
            f"- Documents improved in this run: {len(family_improvements)}",
            "",
            "### Family Enrichment Examples",
            "",
        ]
    )
    _append_family_examples(lines, examples["family_enrichment"])
    lines.extend(["", "## Amendment Chain Results", ""])
    _append_amendment_examples(lines, examples["amendment_chains"])
    lines.extend(["", "## Relationship Examples", ""])
    _append_relationship_examples(lines, examples["relationships"])
    lines.extend(["", "## Stakeholder Extraction Results", ""])
    _append_stakeholder_examples(lines, examples["stakeholders"])
    lines.extend(["", "## Obligation Extraction Results", ""])
    _append_obligation_examples(lines, examples["obligations"])
    lines.extend(["", "## Deadline Intelligence Results", ""])
    _append_deadline_examples(lines, examples["deadlines"])
    lines.extend(["", "## Example Graph Outputs", ""])
    _append_graph_output_examples(lines, examples)
    lines.extend(["", "## New User Capabilities", ""])
    for item in capability:
        lines.append(f"- {item}")
    lines.extend(
        [
            "",
            "## Readiness Assessment",
            "",
            _readiness_assessment(after, examples),
        ]
    )
    if errors:
        lines.extend(["", "## Extraction Error Notes", ""])
        for result in errors[:8]:
            lines.append(f"- Document {result.document_id}: {_clip(result.error, 220)}")
    return "\n".join(lines)


def _capability_assessment(
    examples: dict[str, list[dict[str, Any]]],
    after: dict[str, Any],
) -> list[str]:
    relationship_counts = {
        row["relationship_type"]: row["count"] for row in examples["relationship_counts"]
    }
    stakeholders = {row["stakeholder"].lower() for row in examples["stakeholders"]}
    has_solar = any("solar" in item or "renewable" in item for item in stakeholders)
    has_transmission = any("transmission" in item for item in stakeholders)
    has_obligations = after["obligations"] > 0
    has_active_deadlines = after["active_graph_deadlines"] > 0
    has_active_consultations = (
        after["active_consultation_deadlines"] > 0 or after["consultation_entities"] > 0
    )
    has_amendment_signal = relationship_counts.get("AMENDS", 0) > 0
    return [
        "What amendments affect solar developers? "
        + _yes_partial_no(has_amendment_signal and has_solar, has_amendment_signal or has_solar),
        "Show all active consultations: "
        + _yes_partial_no(has_active_consultations, after["graph_deadlines"] > 0),
        "Show all obligations for transmission licensees: "
        + _yes_partial_no(has_obligations and has_transmission, has_obligations),
        "Which regulations changed this month? "
        + "PARTIAL - graph relationships exist, but true month-over-month version "
        "comparison still needs repeated clean versions.",
        "Show amendment history of DSM Regulations: "
        + (
            "PARTIAL - amendment labels exist, but parent version links are still sparse."
            if examples["amendment_chains"]
            else "NO"
        ),
        "What deadlines exist this quarter? "
        + _yes_partial_no(has_active_deadlines, after["graph_deadlines"] > 0),
    ]


def _readiness_assessment(after: dict[str, Any], examples: dict[str, list[dict[str, Any]]]) -> str:
    has_core_graph = after["entities"] > 0 and after["edges"] > 0
    has_family = after["family_enrichments"] > 0
    has_action = after["obligations"] > 0 or after["graph_deadlines"] > 0
    has_amendments = bool(examples["amendment_chains"])
    if has_core_graph and has_family and has_action and has_amendments:
        choice = "PARTIALLY"
        reason = (
            "The system now has an AI-assisted regulatory understanding layer and can "
            "persist entities, relationships, stakeholders, obligations, deadlines, and "
            "family-enrichment evidence. It is still partial because the current corpus "
            "does not contain enough clean repeated versions to prove complete amendment "
            "lineage."
        )
    elif has_core_graph:
        choice = "PARTIALLY"
        reason = (
            "Graph storage and extraction work, but the current data is too thin for "
            "strong lineage and actionability."
        )
    else:
        choice = "NO"
        reason = "No meaningful graph was produced from the current corpus."
    return f"Choice: **{choice}**.\n\n{reason}"


def _append_count_table(lines: list[str], rows: list[dict[str, Any]], label: str) -> None:
    if not rows:
        lines.append("- None.")
        return
    lines.extend([f"| {label} | Count |", "|---|---:|"])
    for row in rows:
        lines.append(f"| {row[label]} | {row['count']} |")


def _append_family_examples(lines: list[str], rows: list[dict[str, Any]]) -> None:
    if not rows:
        lines.append("- None.")
        return
    for row in rows:
        changed = "applied" if row["applied"] else "recorded"
        lines.append(
            f"- Document {row['document_id']} ({changed}, confidence "
            f"{float(row['confidence']):.2f}): {_clip(row['title'], 80)} -> "
            f"{_clip(row['inferred_family'], 120)}"
        )


def _append_amendment_examples(lines: list[str], rows: list[dict[str, Any]]) -> None:
    if not rows:
        lines.append("- None found.")
        return
    for row in rows:
        lines.append(
            f"- {_clip(row['canonical_title'], 120)} | version={row['version_label']} | "
            f"amendment={row['amendment_number']} | parent="
            f"{row['parent_registry_version_id'] or 'not linked'}"
        )


def _append_relationship_examples(lines: list[str], rows: list[dict[str, Any]]) -> None:
    if not rows:
        lines.append("- None found.")
        return
    for row in rows:
        lines.append(
            f"- {row['relationship_type']}: {_clip(row['source_entity'], 80)} -> "
            f"{_clip(row['target_entity'], 120)} "
            f"(confidence {float(row['confidence']):.2f}; evidence: "
            f"{_clip(row['evidence'], 160)})"
        )


def _append_stakeholder_examples(lines: list[str], rows: list[dict[str, Any]]) -> None:
    if not rows:
        lines.append("- None found.")
        return
    for row in rows:
        lines.append(
            f"- {row['stakeholder']}: {row['documents']} document(s), confidence "
            f"{float(row['confidence']):.2f}; evidence: {_clip(row['evidence'], 160)}"
        )


def _append_obligation_examples(lines: list[str], rows: list[dict[str, Any]]) -> None:
    if not rows:
        lines.append("- None found.")
        return
    for row in rows:
        deadline = row["deadline_date"] or row["deadline_type"] or "no deadline"
        party = row["affected_party"] or "affected party unresolved"
        lines.append(
            f"- Document {row['document_id']}: {_clip(row['obligation'], 180)} "
            f"({party}; {deadline}; confidence {float(row['confidence']):.2f})"
        )


def _append_deadline_examples(lines: list[str], rows: list[dict[str, Any]]) -> None:
    if not rows:
        lines.append("- None found.")
        return
    for row in rows:
        lines.append(
            f"- Document {row['document_id']}: {row['deadline_type']} -> "
            f"{row['deadline_date'] or row['raw_date']} "
            f"(confidence {float(row['confidence']):.2f}; evidence: "
            f"{_clip(row['evidence'], 150)})"
        )


def _append_graph_output_examples(
    lines: list[str],
    examples: dict[str, list[dict[str, Any]]],
) -> None:
    relationship = examples["relationships"][0] if examples["relationships"] else None
    stakeholder = examples["stakeholders"][0] if examples["stakeholders"] else None
    obligation = examples["obligations"][0] if examples["obligations"] else None
    if relationship:
        lines.append(
            f"- Graph edge: DOCUMENT --{relationship['relationship_type']}--> "
            f"{_clip(relationship['target_entity'], 100)}"
        )
    if stakeholder:
        lines.append(f"- Stakeholder node: {stakeholder['stakeholder']}")
    if obligation:
        lines.append(f"- Obligation node: {_clip(obligation['obligation'], 140)}")
    if not any((relationship, stakeholder, obligation)):
        lines.append("- No graph examples available.")


def _format_counter(counter: Counter[str]) -> str:
    if not counter:
        return "none"
    return ", ".join(f"{name}={count}" for name, count in counter.most_common())


def _yes_partial_no(yes: bool, partial: bool) -> str:
    if yes:
        return "YES"
    if partial:
        return "PARTIAL"
    return "NO"


def _clip(value: object, limit: int = 220) -> str:
    value = " ".join(str(value or "").split())
    return value if len(value) <= limit else value[:limit].rstrip() + "..."


if __name__ == "__main__":
    main()
