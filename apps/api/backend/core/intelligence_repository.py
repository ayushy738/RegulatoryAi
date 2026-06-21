from __future__ import annotations

import re
from collections import defaultdict
from datetime import date
from typing import Any

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from backend.core.db import session_scope
from backend.core.models import (
    IntelligenceDeadline,
    IntelligenceDocumentRef,
    IntelligenceObligation,
    IntelligenceReadinessReport,
    StakeholderIntelligence,
    StakeholderObligationGroup,
)

TARGET_STAKEHOLDERS = [
    "Solar Developers",
    "Wind Developers",
    "DISCOMs",
    "Transmission Licensees",
    "Power Exchanges",
    "Generators",
]

STAKEHOLDER_ALIASES = {
    "solar-developers": ["solar", "renewable"],
    "solar developers": ["solar", "renewable"],
    "wind-developers": ["wind", "renewable"],
    "wind developers": ["wind", "renewable"],
    "discoms": ["discom", "distribution"],
    "transmission-licensees": ["transmission", "tsp"],
    "transmission licensees": ["transmission", "tsp"],
    "power-exchanges": ["power exchange", "market"],
    "power exchanges": ["power exchange", "market"],
    "generators": ["generator", "generating"],
}


def list_intelligence_deadlines(
    *,
    issuer: str | None = None,
    deadline_type: str | None = None,
    stakeholder: str | None = None,
    status: str = "active",
    limit: int = 100,
) -> list[IntelligenceDeadline]:
    clauses = []
    params: dict[str, Any] = {"today": date.today(), "limit": limit}
    if status == "active":
        clauses.append("gd.deadline_date is not null and gd.deadline_date >= :today")
    elif status == "historical":
        clauses.append("gd.deadline_date is not null and gd.deadline_date < :today")
    if issuer:
        clauses.append("d.issuing_body ilike :issuer")
        params["issuer"] = f"%{issuer}%"
    if deadline_type and deadline_type != "all":
        clauses.append("gd.deadline_type = :deadline_type")
        params["deadline_type"] = deadline_type
    if stakeholder and stakeholder != "all":
        clauses.append(_stakeholder_exists_clause("gd.document_id"))
        params.update(_stakeholder_params(stakeholder))
    where_sql = f"where {' and '.join(clauses)}" if clauses else ""

    query = text(
        f"""
        select
          gd.document_id,
          d.title,
          d.issuing_body as issuer,
          d.source_url,
          gd.deadline_type,
          gd.deadline_date,
          gd.raw_date,
          gd.confidence,
          gd.evidence,
          coalesce(st.stakeholders, array[]::text[]) as stakeholders
        from regulatory_graph_deadlines gd
        join documents d on d.id = gd.document_id
        left join lateral (
          select array_agg(distinct s.stakeholder) as stakeholders
          from regulatory_graph_stakeholders s
          where s.document_id = gd.document_id
        ) st on true
        {where_sql}
        order by
          case when gd.deadline_date is null then 1 else 0 end,
          gd.deadline_date asc nulls last,
          gd.confidence desc
        limit :limit
        """
    )
    try:
        with session_scope() as session:
            rows = session.execute(query, params).mappings()
            return [_deadline_from_row(row) for row in rows]
    except SQLAlchemyError:
        return []


def list_obligation_groups(
    *,
    stakeholder: str | None = None,
    issuer: str | None = None,
    limit: int = 200,
) -> list[StakeholderObligationGroup]:
    obligations = list_obligations(stakeholder=stakeholder, issuer=issuer, limit=limit)
    groups: dict[str, list[IntelligenceObligation]] = defaultdict(list)
    for obligation in obligations:
        groups[obligation.stakeholder].append(obligation)
    return [
        StakeholderObligationGroup(stakeholder=name, obligations=items)
        for name, items in sorted(groups.items(), key=lambda item: (-len(item[1]), item[0]))
    ]


def list_obligations(
    *,
    stakeholder: str | None = None,
    issuer: str | None = None,
    limit: int = 200,
) -> list[IntelligenceObligation]:
    clauses = []
    params: dict[str, Any] = {"limit": limit}
    if stakeholder and stakeholder != "all":
        clauses.append(
            f"""
            (
              {_stakeholder_exists_clause("o.document_id")}
              or lower(coalesce(o.affected_party, '')) like :stakeholder_like_0
            )
            """
        )
        params.update(_stakeholder_params(stakeholder))
    if issuer:
        clauses.append("d.issuing_body ilike :issuer")
        params["issuer"] = f"%{issuer}%"
    where_sql = f"where {' and '.join(clauses)}" if clauses else ""
    query = text(
        f"""
        select
          o.document_id,
          d.title,
          d.issuing_body as issuer,
          d.source_url,
          o.obligation,
          coalesce(nullif(o.affected_party, ''), st.stakeholder, 'Unresolved')
            as stakeholder,
          o.deadline_date,
          o.deadline_type,
          o.confidence,
          o.evidence
        from regulatory_graph_obligations o
        join documents d on d.id = o.document_id
        left join lateral (
          select stakeholder
          from regulatory_graph_stakeholders s
          where s.document_id = o.document_id
          order by s.confidence desc, s.stakeholder
          limit 1
        ) st on true
        {where_sql}
        order by o.confidence desc, d.title, o.obligation
        limit :limit
        """
    )
    try:
        with session_scope() as session:
            rows = session.execute(query, params).mappings()
            return [_obligation_from_row(row) for row in rows]
    except SQLAlchemyError:
        return []


def list_stakeholder_intelligence(
    stakeholder: str | None = None,
) -> list[StakeholderIntelligence]:
    names = [_display_stakeholder(stakeholder)] if stakeholder else TARGET_STAKEHOLDERS
    return [get_stakeholder_intelligence(name) for name in names]


def get_stakeholder_intelligence(stakeholder: str) -> StakeholderIntelligence:
    display = _display_stakeholder(stakeholder)
    obligations = list_obligations(stakeholder=display, limit=80)
    deadlines = list_intelligence_deadlines(stakeholder=display, status="all", limit=80)
    documents = _stakeholder_documents(display)
    regulations = [doc for doc in documents if doc.document_type in _REGULATORY_TYPES]
    consultations = [doc for doc in documents if doc.document_type == "CONSULTATION"]
    tenders = [doc for doc in documents if doc.document_type == "TENDER"]
    counts = {
        "regulations": len(regulations),
        "consultations": len(consultations),
        "obligations": len(obligations),
        "deadlines": len(deadlines),
        "tenders": len(tenders),
    }
    return StakeholderIntelligence(
        stakeholder=display,
        impact_summary=_impact_summary(display, counts, documents),
        compliance_summary=_compliance_summary(display, obligations),
        action_summary=_action_summary(display, deadlines),
        regulations=regulations,
        consultations=consultations,
        obligations=obligations,
        deadlines=deadlines,
        tenders=tenders,
        counts=counts,
    )


def intelligence_readiness_report() -> IntelligenceReadinessReport:
    active_deadlines = list_intelligence_deadlines(status="active", limit=12)
    obligations = list_obligation_groups(limit=60)
    impacts = list_stakeholder_intelligence()
    consultations = _consultation_documents()
    notes = [
        "Deadlines are future-dated only in the active API.",
        "Stakeholder views also surface historical extracted deadlines for auditability.",
    ]
    if not active_deadlines:
        notes.append("The current graph has no future-dated active deadline rows.")
    if not consultations:
        notes.append("The current graph has no accepted primary consultation documents.")
    status = "ready" if obligations or active_deadlines or impacts else "empty"
    return IntelligenceReadinessReport(
        active_deadlines=active_deadlines,
        stakeholder_obligations=obligations,
        regulatory_impacts=impacts,
        consultation_tracking=consultations,
        status=status,
        notes=notes,
    )


_REGULATORY_TYPES = {"ACT", "REGULATION", "POLICY", "ORDER", "NOTIFICATION", "GUIDELINE"}


def _stakeholder_documents(stakeholder: str) -> list[IntelligenceDocumentRef]:
    params = _stakeholder_params(stakeholder)
    query = text(
        f"""
        select
          d.id as document_id,
          d.title,
          d.issuing_body as issuer,
          d.source_url,
          coalesce(max(s.confidence), 0) as confidence,
          max(s.evidence) as evidence,
          bool_or(
            lower(d.title) like '%tender%'
            or lower(d.title) like '%rfp%'
            or lower(coalesce(d.doc_type, '')) like '%tender%'
            or ge.entity_type = 'TENDER'
          ) as is_tender,
          bool_or(
            lower(d.title) like '%consultation%'
            or lower(d.title) like '%comments%'
            or lower(d.title) like '%public hearing%'
            or ge.entity_type = 'CONSULTATION'
          ) as is_consultation,
          bool_or(
            ge.entity_type in ('ACT', 'REGULATION', 'POLICY', 'ORDER', 'NOTIFICATION',
                               'GUIDELINE')
            or lower(d.title) like '%regulation%'
            or lower(d.title) like '%act,%'
            or lower(d.title) like '%policy%'
          ) as is_regulatory
        from regulatory_graph_stakeholders s
        join documents d on d.id = s.document_id
        left join regulatory_graph_edges edge on edge.source_document_id = d.id
        left join regulatory_graph_entities ge on ge.entity_id = edge.to_entity_id
        where {_stakeholder_match_clause("s")}
        group by d.id, d.title, d.issuing_body, d.source_url
        order by confidence desc, d.title
        limit 60
        """
    )
    try:
        with session_scope() as session:
            rows = session.execute(query, params).mappings()
            return [_document_ref_from_row(row) for row in rows]
    except SQLAlchemyError:
        return []


def _consultation_documents() -> list[IntelligenceDocumentRef]:
    query = text(
        """
        select distinct
          d.id as document_id,
          d.title,
          d.issuing_body as issuer,
          d.source_url,
          coalesce(max(gde.confidence), 0) as confidence,
          max(gde.evidence) as evidence,
          true as is_consultation,
          false as is_tender,
          false as is_regulatory
        from documents d
        left join regulatory_graph_document_entities gde on gde.document_id = d.id
        left join regulatory_graph_entities ge on ge.entity_id = gde.entity_id
        where ge.entity_type = 'CONSULTATION'
           or lower(d.title) like '%consultation%'
           or lower(d.title) like '%comments%'
           or lower(d.title) like '%public hearing%'
        group by d.id, d.title, d.issuing_body, d.source_url
        order by confidence desc, d.title
        limit 30
        """
    )
    try:
        with session_scope() as session:
            rows = session.execute(query).mappings()
            return [_document_ref_from_row(row) for row in rows]
    except SQLAlchemyError:
        return []


def _deadline_from_row(row: Any) -> IntelligenceDeadline:
    deadline_date = row["deadline_date"]
    days_remaining = (deadline_date - date.today()).days if deadline_date else None
    stakeholders = sorted(item for item in list(row["stakeholders"] or []) if item)
    return IntelligenceDeadline(
        document_id=row["document_id"],
        title=row["title"],
        issuer=row["issuer"],
        deadline_type=row["deadline_type"],
        deadline_date=deadline_date,
        raw_date=row["raw_date"],
        days_remaining=days_remaining,
        stakeholders_affected=stakeholders,
        source_url=row["source_url"],
        confidence=float(row["confidence"] or 0),
        evidence=row["evidence"],
    )


def _obligation_from_row(row: Any) -> IntelligenceObligation:
    return IntelligenceObligation(
        document_id=row["document_id"],
        title=row["title"],
        issuer=row["issuer"],
        obligation=row["obligation"],
        stakeholder=row["stakeholder"] or "Unresolved",
        deadline_date=row["deadline_date"],
        deadline_type=row["deadline_type"],
        confidence=float(row["confidence"] or 0),
        evidence=row["evidence"],
        source_url=row["source_url"],
    )


def _document_ref_from_row(row: Any) -> IntelligenceDocumentRef:
    if row.get("is_tender"):
        doc_type = "TENDER"
    elif row.get("is_consultation"):
        doc_type = "CONSULTATION"
    elif row.get("is_regulatory"):
        doc_type = "REGULATION"
    else:
        doc_type = "DOCUMENT"
    return IntelligenceDocumentRef(
        document_id=row["document_id"],
        title=row["title"],
        issuer=row["issuer"],
        source_url=row["source_url"],
        document_type=doc_type,
        confidence=float(row["confidence"] or 0),
        evidence=row["evidence"],
    )


def _impact_summary(
    stakeholder: str,
    counts: dict[str, int],
    documents: list[IntelligenceDocumentRef],
) -> str:
    if not documents:
        return (
            f"No accepted primary documents in the current graph are linked to "
            f"{stakeholder} yet."
        )
    pieces = [
        f"{stakeholder} appear in {len(documents)} graph-linked document(s)",
        f"{counts['regulations']} regulatory instrument(s)",
        f"{counts['tenders']} tender/opportunity item(s)",
    ]
    return ", ".join(pieces) + "."


def _compliance_summary(
    stakeholder: str,
    obligations: list[IntelligenceObligation],
) -> str:
    if not obligations:
        return f"No explicit obligations for {stakeholder} are stored in the graph yet."
    top = obligations[0]
    return (
        f"{len(obligations)} obligation(s) are linked to {stakeholder}. "
        f"Highest-confidence item: {top.obligation}"
    )


def _action_summary(
    stakeholder: str,
    deadlines: list[IntelligenceDeadline],
) -> str:
    active = [
        item
        for item in deadlines
        if item.deadline_date and item.deadline_date >= date.today()
    ]
    if active:
        next_deadline = min(active, key=lambda item: item.deadline_date or date.max)
        return (
            f"Next deadline for {stakeholder}: {next_deadline.deadline_type} on "
            f"{next_deadline.deadline_date}."
        )
    if deadlines:
        return (
            f"{len(deadlines)} extracted date/deadline row(s) exist for {stakeholder}, "
            "but none are future-dated in the current corpus."
        )
    return f"No deadline row is currently linked to {stakeholder}."


def _display_stakeholder(value: str | None) -> str:
    if not value:
        return ""
    normalized = value.replace("-", " ").strip().lower()
    for item in TARGET_STAKEHOLDERS:
        if normalized == item.lower():
            return item
    return " ".join(part.capitalize() for part in normalized.split())


def _stakeholder_params(value: str) -> dict[str, str]:
    terms = _stakeholder_terms(value)
    params = {}
    padded = [*terms[:4], *terms[:1] * 4]
    for index, term in enumerate(padded[:4]):
        params[f"stakeholder_like_{index}"] = f"%{term.lower()}%"
    return params


def _stakeholder_terms(value: str) -> list[str]:
    normalized = value.replace("-", " ").strip().lower()
    terms = STAKEHOLDER_ALIASES.get(normalized, [normalized])
    return [re.sub(r"[^a-z0-9 ]+", "", term).strip() for term in terms if term.strip()]


def _stakeholder_exists_clause(document_id_expr: str) -> str:
    return f"""
    exists (
      select 1
      from regulatory_graph_stakeholders sx
      where sx.document_id = {document_id_expr}
        and ({_stakeholder_match_clause("sx")})
    )
    """


def _stakeholder_match_clause(alias: str) -> str:
    return " or ".join(
        [
            f"lower({alias}.normalized_stakeholder) like :stakeholder_like_{index}"
            for index in range(4)
        ]
    )
