from __future__ import annotations

import asyncio
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import text

from backend.core.db import session_scope
from backend.core.repository import (
    create_crawl_run,
    finalize_crawl_run,
    list_sources,
    persist_extracted_documents,
    record_discovery_audits,
    record_source_check,
)
from backend.core.utils import canonical_url
from backend.pipeline.agent_scraper import scrape_source
from backend.pipeline.primary_document import acquire_primary_documents
from backend.pipeline.regulatory_knowledge_graph import (
    GraphInput,
    analyze_and_persist_regulatory_graph,
)

REPORT_PATH = Path("E:/RegulatoryAi/reports/STEP21_PRODUCT_VALIDATION_DATA_QUALITY.md")

AD_HOC_SOURCES = [
    {
        "code": "seci",
        "name": "Solar Energy Corporation of India",
        "jurisdiction": "central",
        "url": "https://www.seci.co.in/tenders",
        "crawler_type": "agent",
        "allowed_domains": ["seci.co.in", "www.seci.co.in"],
        "enabled": True,
    },
    {
        "code": "merc",
        "name": "Maharashtra Electricity Regulatory Commission",
        "jurisdiction": "state",
        "url": "https://www.merc.gov.in/",
        "crawler_type": "agent",
        "allowed_domains": ["merc.gov.in", "www.merc.gov.in"],
        "enabled": True,
    },
]

TARGET_SOURCE_CODES = ["mop", "cerc", "mnre", "seci", "merc"]


@dataclass
class SourceAudit:
    code: str
    name: str
    url: str
    candidates: int
    accepted: int
    rejected: int
    new_events: int
    families: int
    deadlines: int
    consultations: int
    obligations: int
    stakeholders: int
    graph_entities: int
    graph_edges: int
    errors: list[str]
    rejection_reasons: Counter[str]
    classifications: Counter[str]
    sample_titles: list[str]

    @property
    def roi_score(self) -> float:
        return (
            self.accepted * 2.0
            + self.new_events * 2.0
            + self.deadlines * 0.8
            + self.consultations * 3.0
            + self.obligations * 1.2
            + self.stakeholders * 0.8
            + self.families
            - self.rejected * 0.25
            - len(self.errors) * 3.0
        )


async def main_async() -> None:
    configured = {source["code"]: source for source in list_sources()}
    sources = []
    for code in TARGET_SOURCE_CODES:
        if code in configured:
            sources.append(configured[code])
            continue
        sources.extend(source for source in AD_HOC_SOURCES if source["code"] == code)

    before = _global_counts()
    run_id = create_crawl_run()
    audits: list[SourceAudit] = []
    for source in sources:
        source_before = _global_counts()
        errors: list[str] = []
        docs = []
        primary_result = None
        event_ids: list[int] = []
        document_ids: list[int] = []
        try:
            docs = await scrape_source(source)
            primary_result = await acquire_primary_documents(docs)
            record_discovery_audits(run_id, primary_result.audits)
            event_ids = persist_extracted_documents(primary_result.accepted)
            document_ids = _document_ids_for_urls(
                [item.fetched.discovered.source_url for item in primary_result.accepted]
            )
            _run_graph_for_documents(document_ids)
            record_source_check(source["code"], status=200, ok=True)
        except Exception as exc:
            record_source_check(source["code"], status=None, ok=False)
            errors.append(f"{type(exc).__name__}: {exc}")

        source_after = _global_counts()
        audits.append(
            _source_audit(
                source=source,
                docs=docs,
                primary_result=primary_result,
                event_ids=event_ids,
                document_ids=document_ids,
                before=source_before,
                after=source_after,
                errors=errors,
            )
        )

    after = _global_counts()
    finalize_crawl_run(
        run_id,
        status="success" if not any(item.errors for item in audits) else "partial",
        sources_attempted=len(sources),
        sources_succeeded=sum(1 for item in audits if not item.errors),
        docs_found=sum(item.candidates for item in audits),
        new_events=sum(item.new_events for item in audits),
        errors=[
            {"source": item.code, "error": "; ".join(item.errors)}
            for item in audits
            if item.errors
        ],
    )
    report = _markdown_report(audits, before, after)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(report, encoding="utf-8")
    print(report.encode("ascii", errors="replace").decode("ascii"))


def _global_counts() -> dict[str, int]:
    with session_scope() as session:
        row = session.execute(
            text(
                """
                select
                  (select count(*) from documents) as documents,
                  (select count(*) from events) as events,
                  (select count(*) from document_families) as families,
                  (select count(*) from deadline_history) as deadline_history,
                  (select count(*) from regulatory_graph_entities) as graph_entities,
                  (select count(*) from regulatory_graph_edges) as graph_edges,
                  (select count(*) from regulatory_graph_deadlines) as graph_deadlines,
                  (select count(*) from regulatory_graph_obligations) as graph_obligations,
                  (select count(*) from regulatory_graph_stakeholders) as graph_stakeholders
                """
            )
        ).mappings().first()
    return dict(row)


def _document_ids_for_urls(urls: list[str]) -> list[int]:
    if not urls:
        return []
    canonical_urls = [canonical_url(url) for url in urls]
    with session_scope() as session:
        rows = session.execute(
            text(
                """
                select id
                from documents
                where source_url = any(:urls)
                """
            ),
            {"urls": canonical_urls},
        ).mappings()
        return [int(row["id"]) for row in rows]


def _run_graph_for_documents(document_ids: list[int]) -> None:
    if not document_ids:
        return
    rows = _load_graph_inputs(document_ids)
    with session_scope() as session:
        for row in rows:
            analyze_and_persist_regulatory_graph(session, _graph_input(row), use_ai=True)


def _load_graph_inputs(document_ids: list[int]) -> list[dict[str, Any]]:
    with session_scope() as session:
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
                left join document_texts dt on dt.content_hash = dv.content_hash
                left join document_family_assignments a on a.document_id = d.id
                where d.id = any(:document_ids)
                order by d.id
                """
            ),
            {"document_ids": document_ids},
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


def _source_audit(
    *,
    source: dict,
    docs: list,
    primary_result: Any,
    event_ids: list[int],
    document_ids: list[int],
    before: dict[str, int],
    after: dict[str, int],
    errors: list[str],
) -> SourceAudit:
    rejection_reasons: Counter[str] = Counter()
    classifications: Counter[str] = Counter()
    accepted = 0
    sample_titles = [doc.title for doc in docs[:5]]
    if primary_result:
        accepted = len(primary_result.accepted)
        for audit in primary_result.audits:
            classifications[str(audit.classification)] += 1
            if not audit.is_valid_event_source:
                rejection_reasons[audit.reason_code] += 1
    doc_metrics = _document_metrics(document_ids)
    return SourceAudit(
        code=source["code"],
        name=source["name"],
        url=source["url"],
        candidates=len(docs),
        accepted=accepted,
        rejected=max(0, len(docs) - accepted),
        new_events=len(event_ids),
        families=doc_metrics["families"],
        deadlines=doc_metrics["deadlines"],
        consultations=doc_metrics["consultations"],
        obligations=doc_metrics["obligations"],
        stakeholders=doc_metrics["stakeholders"],
        graph_entities=after["graph_entities"] - before["graph_entities"],
        graph_edges=after["graph_edges"] - before["graph_edges"],
        errors=errors,
        rejection_reasons=rejection_reasons,
        classifications=classifications,
        sample_titles=sample_titles,
    )


def _document_metrics(document_ids: list[int]) -> dict[str, int]:
    if not document_ids:
        return {
            "families": 0,
            "deadlines": 0,
            "consultations": 0,
            "obligations": 0,
            "stakeholders": 0,
        }
    with session_scope() as session:
        row = session.execute(
            text(
                """
                select
                  (select count(distinct family_id)
                   from document_family_assignments
                   where document_id = any(:document_ids) and family_id is not null) as families,
                  (select count(*)
                   from regulatory_graph_deadlines
                   where document_id = any(:document_ids)) as deadlines,
                  (select count(*)
                   from regulatory_graph_obligations
                   where document_id = any(:document_ids)) as obligations,
                  (select count(distinct normalized_stakeholder)
                   from regulatory_graph_stakeholders
                   where document_id = any(:document_ids)) as stakeholders,
                  (select count(*)
                   from documents
                   where id = any(:document_ids)
                     and (
                       title ilike '%consultation%'
                       or title ilike '%comments%'
                       or title ilike '%public hearing%'
                     )) as consultations
                """
            ),
            {"document_ids": document_ids},
        ).mappings().first()
    return dict(row)


def _markdown_report(
    audits: list[SourceAudit],
    before: dict[str, int],
    after: dict[str, int],
) -> str:
    ranked = sorted(audits, key=lambda item: item.roi_score, reverse=True)
    lines = [
        "# Step 21 Product Validation & Data Quality Audit",
        "",
        f"Generated at: {datetime.now(UTC).isoformat()}",
        "",
        "## Run Scope",
        "",
        "- Sources: Ministry of Power, CERC, MNRE, SECI, MERC.",
        "- SECI and MERC were run as ad-hoc validation sources because they are not "
        "currently configured in the product source table.",
        "- No UI, API, crawler, or AI-layer features were added for this audit.",
        "",
        "## Platform Growth During Audit",
        "",
    ]
    for key in (
        "documents",
        "events",
        "families",
        "deadline_history",
        "graph_entities",
        "graph_edges",
        "graph_deadlines",
        "graph_obligations",
        "graph_stakeholders",
    ):
        lines.append(f"- {key}: {before[key]} -> {after[key]} ({after[key] - before[key]:+d})")
    lines.extend(["", "## Source Metrics", ""])
    lines.append(
        "| Source | Candidates | Accepted | Rejected | Events | Families | "
        "Deadlines | Consultations | Obligations | Stakeholders | Graph growth | ROI |"
    )
    lines.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
    for item in audits:
        lines.append(
            f"| {item.code} | {item.candidates} | {item.accepted} | {item.rejected} | "
            f"{item.new_events} | {item.families} | {item.deadlines} | "
            f"{item.consultations} | {item.obligations} | {item.stakeholders} | "
            f"{item.graph_entities + item.graph_edges} | {item.roi_score:.1f} |"
        )
    lines.extend(["", "## Source Quality", ""])
    for item in audits:
        lines.extend(_source_section(item))
    lines.extend(["", "## ROI Ranking", ""])
    for index, item in enumerate(ranked, start=1):
        lines.append(f"{index}. {item.name} (`{item.code}`): ROI {item.roi_score:.1f}")
    lines.extend(["", "## Product Questions", ""])
    lines.extend(_product_answers(audits, ranked))
    lines.extend(["", "## Shortest Path To A Paying Pilot", ""])
    lines.extend(_pilot_path(audits, ranked))
    return "\n".join(lines)


def _source_section(item: SourceAudit) -> list[str]:
    source_quality = _quality_label(item)
    intelligence_yield = _yield_label(item)
    stakeholder_relevance = _stakeholder_label(item)
    maintenance_cost = _maintenance_label(item)
    lines = [
        f"### {item.name} (`{item.code}`)",
        "",
        f"- Source quality: **{source_quality}**.",
        f"- Intelligence yield: **{intelligence_yield}**.",
        f"- Stakeholder relevance: **{stakeholder_relevance}**.",
        f"- Maintenance cost: **{maintenance_cost}**.",
    ]
    if item.errors:
        lines.append(f"- Errors: {'; '.join(item.errors)}")
    if item.rejection_reasons:
        lines.append(f"- Rejection reasons: {_format_counter(item.rejection_reasons)}")
    if item.classifications:
        lines.append(f"- Candidate classifications: {_format_counter(item.classifications)}")
    if item.sample_titles:
        lines.append(f"- Sample titles: {_clip('; '.join(item.sample_titles), 240)}")
    lines.append("")
    return lines


def _product_answers(audits: list[SourceAudit], ranked: list[SourceAudit]) -> list[str]:
    highest = [item for item in ranked if item.roi_score > 0][:3]
    remove = [item for item in audits if item.accepted == 0 and item.candidates == 0]
    custom = [
        item
        for item in audits
        if item.rejected > item.accepted or item.errors or item.candidates == 0
    ]
    solar_score = sum(
        item.obligations + item.deadlines + item.stakeholders
        for item in audits
        if item.code in {"mnre", "seci", "mop"}
    )
    discom_score = sum(item.obligations + item.deadlines for item in audits)
    transmission_score = sum(
        item.obligations + item.deadlines
        for item in audits
        if item.code in {"mop", "cerc", "seci"}
    )
    return [
        "### Which sources generate the highest-value intelligence?",
        "",
        _list_or_none(highest),
        "",
        "### Which sources should be removed?",
        "",
        _list_or_none(remove)
        if remove
        else "- None should be removed solely from this run; low-yield sources should first get "
        "custom extraction or better listing URLs.",
        "",
        "### Which sources need custom extraction logic?",
        "",
        _list_or_none(custom),
        "",
        "### Can the platform support solar developers?",
        "",
        _capability_answer(solar_score, "solar developers"),
        "",
        "### Can the platform support DISCOMs?",
        "",
        _capability_answer(discom_score, "DISCOMs"),
        "",
        "### Can the platform support transmission companies?",
        "",
        _capability_answer(transmission_score, "transmission companies"),
    ]


def _pilot_path(audits: list[SourceAudit], ranked: list[SourceAudit]) -> list[str]:
    top = ranked[0] if ranked else None
    return [
        "- Start with the highest-yield source cluster from this audit, not with every "
        "government portal.",
        "- Keep active-deadline and consultation promises conservative until current/future "
        "documents enter the graph.",
        "- Build the pilot around obligations and stakeholder impact first; those are the "
        "strongest signals currently produced.",
        "- Add custom extraction for the highest-maintenance high-value source before adding "
        "more portals.",
        f"- Best first pilot wedge: {top.name if top else 'not enough data'}."
        if top
        else "- Best first pilot wedge: not enough data.",
    ]


def _quality_label(item: SourceAudit) -> str:
    if item.errors:
        return "Poor - crawler/runtime error"
    if item.candidates == 0:
        return "Poor - no candidates discovered"
    if item.accepted / item.candidates >= 0.5:
        return "Good - candidate discovery produces primary documents"
    if item.accepted:
        return "Mixed - some useful documents but noisy discovery"
    return "Poor - discovery is not reaching primary documents"


def _yield_label(item: SourceAudit) -> str:
    score = item.obligations + item.deadlines + item.consultations * 2 + item.new_events * 2
    if score >= 15:
        return "High"
    if score >= 5:
        return "Medium"
    if score > 0:
        return "Low"
    return "None"


def _stakeholder_label(item: SourceAudit) -> str:
    if item.stakeholders >= 5:
        return "High"
    if item.stakeholders >= 2:
        return "Medium"
    if item.stakeholders == 1:
        return "Low"
    return "None"


def _maintenance_label(item: SourceAudit) -> str:
    if item.errors or item.candidates == 0:
        return "High"
    if item.rejected > item.accepted:
        return "Medium"
    return "Low"


def _capability_answer(score: int, segment: str) -> str:
    if score >= 15:
        return f"- **Yes, partially pilot-ready** for {segment}, based on current graph yield."
    if score >= 5:
        return f"- **Partially** for {segment}; coverage exists but is not yet broad enough."
    return f"- **Not yet** for {segment}; current source/data yield is too thin."


def _list_or_none(items: list[SourceAudit]) -> str:
    if not items:
        return "- None."
    return "\n".join(f"- {item.name} (`{item.code}`)" for item in items)


def _format_counter(counter: Counter[str]) -> str:
    return ", ".join(f"{key}={value}" for key, value in counter.most_common())


def _clip(value: str, limit: int) -> str:
    return value if len(value) <= limit else value[:limit].rstrip() + "..."


def main() -> None:
    asyncio.run(main_async())


if __name__ == "__main__":
    main()
