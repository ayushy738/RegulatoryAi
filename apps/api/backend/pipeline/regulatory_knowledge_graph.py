from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import date
from typing import Any

from dateutil import parser as date_parser
from sqlalchemy import text

from backend.core.config import settings
from backend.core.llm import get_llm_client
from backend.pipeline.intelligence_gate import extract_deadline_intelligence

GRAPH_SYSTEM_PROMPT = """
You are building a regulatory knowledge graph for Indian power-sector regulation.
Extract only grounded facts from the supplied primary document text.
Use evidence snippets copied from the document. Do not invent prior versions.
Return strict JSON with this shape:
{
  "core_identity": {
    "issuer": string|null,
    "regulation_name": string|null,
    "notification_name": string|null,
    "document_title": string,
    "document_type": string,
    "confidence": number,
    "evidence": string
  },
  "metadata": {
    "regulation_number": string|null,
    "notification_number": string|null,
    "gazette_number": string|null,
    "amendment_number": integer|null,
    "publication_date": "YYYY-MM-DD"|null,
    "effective_date": "YYYY-MM-DD"|null,
    "confidence": number,
    "evidence": string
  },
  "family_resolution": {
    "inferred_family": string|null,
    "document_type": string|null,
    "amendment_number": integer|null,
    "relationship": "AMENDS|SUPERSEDES|REFERENCES|IMPLEMENTS|REPEALS|EXTENDS|NONE",
    "confidence": number,
    "evidence": string
  },
  "relationships": [
    {
      "relationship_type": "AMENDS|SUPERSEDES|REFERENCES|IMPLEMENTS|REPEALS|EXTENDS",
      "target_entity": string,
      "target_entity_type": "REGULATION|NOTIFICATION|POLICY|TENDER|CONSULTATION|DOCUMENT|OTHER",
      "confidence": number,
      "evidence": string
    }
  ],
  "stakeholders": [
    {"stakeholder": string, "confidence": number, "evidence": string}
  ],
  "obligations": [
    {
      "obligation": string,
      "deadline": "YYYY-MM-DD"|null,
      "deadline_type": string|null,
      "affected_party": string|null,
      "confidence": number,
      "evidence": string
    }
  ],
  "deadlines": [
    {
      "deadline_type": string,
      "deadline_date": "YYYY-MM-DD"|null,
      "raw_date": string|null,
      "confidence": number,
      "evidence": string
    }
  ]
}
""".strip()

DOCUMENT_TYPE_TERMS = {
    "TENDER": ("tender", "rfp", "request for proposal", "bid", "bidding"),
    "CONSULTATION": ("consultation", "comments", "suggestions", "public hearing"),
    "CORRIGENDUM": ("corrigendum",),
    "ADDENDUM": ("addendum",),
    "AMENDMENT": ("amendment",),
    "REGULATION": ("regulation", "regulations"),
    "NOTIFICATION": ("notification", "gazette"),
    "ORDER": ("order", "petition"),
    "POLICY": ("policy", "scheme", "trajectory"),
    "ACT": ("act,", " act "),
    "GUIDELINE": ("guideline", "guidelines", "procedure"),
    "CIRCULAR": ("circular",),
}

ORDINALS = {
    "first": 1,
    "second": 2,
    "third": 3,
    "fourth": 4,
    "fifth": 5,
    "sixth": 6,
    "seventh": 7,
    "eighth": 8,
    "ninth": 9,
    "tenth": 10,
}

STAKEHOLDER_PATTERNS = {
    "Renewable Developers": (
        "renewable developer",
        "renewable energy",
        "solar",
        "wind",
        "hybrid",
    ),
    "Solar Developers": ("solar developer", "solar power", "solar project", "solar energy"),
    "Wind Developers": ("wind developer", "wind power", "wind project"),
    "DISCOMs": ("discom", "distribution licensee", "distribution company"),
    "Transmission Licensees": (
        "transmission licensee",
        "transmission service provider",
        "transmission system",
    ),
    "Power Exchanges": ("power exchange", "market coupling", "power market"),
    "Generators": ("generator", "generating company", "generating station"),
    "Open Access Consumers": ("open access consumer", "open access"),
    "Bidders": ("bidder", "bidding", "tenderer"),
    "Consumers": ("consumer", "end consumer"),
}

RELATIONSHIP_TERMS = {
    "AMENDS": ("amends", "amendment", "substituted", "inserted", "omitted"),
    "SUPERSEDES": ("supersedes", "in supersession of", "replaces"),
    "REPEALS": ("repeals", "repealed", "withdrawn"),
    "IMPLEMENTS": ("implements", "implementation of", "in pursuance of"),
    "EXTENDS": ("extended", "extension", "last date", "revised deadline"),
}


@dataclass(frozen=True)
class GraphInput:
    document_id: int
    document_version_id: int | None
    title: str
    issuer: str | None
    source_url: str
    document_type: str | None
    issue_date: date | None
    content_hash: str | None
    text_content: str
    content_length: int
    family_id: int | None = None
    assignment_type: str | None = None


@dataclass(frozen=True)
class GraphPersistenceResult:
    document_id: int
    used_ai: bool
    status: str
    entity_count: int
    relationship_count: int
    stakeholder_count: int
    obligation_count: int
    deadline_count: int
    family_before: int | None
    family_after: int | None
    family_applied: bool
    error: str | None = None


def analyze_and_persist_regulatory_graph(
    session: Any,
    item: GraphInput,
    *,
    use_ai: bool = True,
) -> GraphPersistenceResult:
    extraction, used_ai, error = extract_regulatory_knowledge(item, use_ai=use_ai)
    result = persist_regulatory_knowledge_graph(session, item, extraction)
    _upsert_extraction_audit(session, item, extraction, used_ai=used_ai, error=error)
    return GraphPersistenceResult(
        document_id=item.document_id,
        used_ai=used_ai,
        status="AI" if used_ai else "HEURISTIC",
        error=error,
        **result,
    )


def extract_regulatory_knowledge(
    item: GraphInput,
    *,
    use_ai: bool = True,
) -> tuple[dict[str, Any], bool, str | None]:
    heuristic = _heuristic_extraction(item)
    if not use_ai or item.content_length < 250:
        return heuristic, False, None

    model = (
        settings.llm_model_agent
        or settings.llm_model_summary
        or settings.llm_model_chat
        or "offline-demo"
    )
    prompt = _build_graph_prompt(item)
    try:
        payload = get_llm_client().complete_json(GRAPH_SYSTEM_PROMPT, prompt, model)
        if not _looks_like_graph_payload(payload):
            return heuristic, False, "AI response did not match graph schema."
        return _merge_with_heuristic(payload, heuristic), True, None
    except Exception as exc:
        return heuristic, False, f"{type(exc).__name__}: {exc}"


def persist_regulatory_knowledge_graph(
    session: Any,
    item: GraphInput,
    extraction: dict[str, Any],
) -> dict[str, Any]:
    document_entity = _upsert_entity(
        session,
        entity_type="DOCUMENT",
        name=item.title,
        canonical_name=f"document:{item.document_id}",
        issuer=item.issuer,
        external_ref=f"document:{item.document_id}",
        confidence=1.0,
        evidence=item.source_url,
        metadata={"source_url": item.source_url, "content_hash": item.content_hash},
    )
    _link_document_entity(session, item, document_entity, "SELF", 1.0, item.source_url)

    entity_ids = {document_entity}
    relationship_count = 0
    core = _as_dict(extraction.get("core_identity"))
    issuer = _clean(core.get("issuer") or item.issuer)
    if issuer:
        issuer_entity = _upsert_entity(
            session,
            entity_type="ISSUER",
            name=issuer,
            canonical_name=_canonical(issuer),
            issuer=None,
            external_ref=None,
            confidence=_confidence(core.get("confidence"), 0.75),
            evidence=core.get("evidence") or issuer,
            metadata={},
        )
        entity_ids.add(issuer_entity)
        relationship_count += _upsert_edge(
            session,
            document_entity,
            issuer_entity,
            "ISSUED_BY",
            item,
            _confidence(core.get("confidence"), 0.75),
            core.get("evidence") or issuer,
        )

    family_result = _apply_family_enrichment(session, item, extraction)
    family = _as_dict(extraction.get("family_resolution"))
    family_name = _clean(family.get("inferred_family"))
    if family_name:
        family_entity = _upsert_entity(
            session,
            entity_type=_entity_type(family.get("document_type") or core.get("document_type")),
            name=family_name,
            canonical_name=_canonical(family_name),
            issuer=issuer or item.issuer,
            external_ref=f"family:{family_result['family_after']}"
            if family_result["family_after"]
            else None,
            confidence=_confidence(family.get("confidence"), 0.65),
            evidence=family.get("evidence") or family_name,
            metadata={"family_id": family_result["family_after"]},
        )
        entity_ids.add(family_entity)
        relationship_count += _upsert_edge(
            session,
            document_entity,
            family_entity,
            "BELONGS_TO_FAMILY",
            item,
            _confidence(family.get("confidence"), 0.65),
            family.get("evidence") or family_name,
        )

    core_document_type = _entity_type(core.get("document_type"))
    for rel in _list_of_dicts(extraction.get("relationships")):
        target = _clean(rel.get("target_entity"))
        relationship_type = _relationship_type(rel.get("relationship_type"))
        if not target or not relationship_type:
            continue
        if not _relationship_is_grounded(
            relationship_type,
            core_document_type,
            rel.get("evidence"),
        ):
            continue
        target_entity = _upsert_entity(
            session,
            entity_type=_entity_type(rel.get("target_entity_type")),
            name=target,
            canonical_name=_canonical(target),
            issuer=issuer or item.issuer,
            external_ref=None,
            confidence=_confidence(rel.get("confidence"), 0.6),
            evidence=rel.get("evidence") or target,
            metadata={},
        )
        entity_ids.add(target_entity)
        relationship_count += _upsert_edge(
            session,
            document_entity,
            target_entity,
            relationship_type,
            item,
            _confidence(rel.get("confidence"), 0.6),
            rel.get("evidence") or target,
        )

    stakeholder_count = 0
    for stakeholder in _list_of_dicts(extraction.get("stakeholders")):
        label = _clean(stakeholder.get("stakeholder"))
        if not label:
            continue
        stakeholder_count += _upsert_stakeholder(session, item, stakeholder)
        stakeholder_entity = _upsert_entity(
            session,
            entity_type="STAKEHOLDER",
            name=label,
            canonical_name=_canonical(label),
            issuer=None,
            external_ref=None,
            confidence=_confidence(stakeholder.get("confidence"), 0.6),
            evidence=stakeholder.get("evidence") or label,
            metadata={},
        )
        entity_ids.add(stakeholder_entity)
        relationship_count += _upsert_edge(
            session,
            document_entity,
            stakeholder_entity,
            "AFFECTS",
            item,
            _confidence(stakeholder.get("confidence"), 0.6),
            stakeholder.get("evidence") or label,
        )

    obligation_count = 0
    for obligation in _list_of_dicts(extraction.get("obligations")):
        label = _clean(obligation.get("obligation"))
        if not label:
            continue
        obligation_count += _upsert_obligation(session, item, obligation)
        obligation_entity = _upsert_entity(
            session,
            entity_type="OBLIGATION",
            name=label,
            canonical_name=_obligation_key(item.document_id, label),
            issuer=issuer or item.issuer,
            external_ref=None,
            confidence=_confidence(obligation.get("confidence"), 0.6),
            evidence=obligation.get("evidence") or label,
            metadata={
                "deadline": obligation.get("deadline"),
                "affected_party": obligation.get("affected_party"),
            },
        )
        entity_ids.add(obligation_entity)
        relationship_count += _upsert_edge(
            session,
            document_entity,
            obligation_entity,
            "HAS_OBLIGATION",
            item,
            _confidence(obligation.get("confidence"), 0.6),
            obligation.get("evidence") or label,
        )

    deadline_count = 0
    for deadline in _list_of_dicts(extraction.get("deadlines")):
        label = _deadline_label(deadline)
        if not label:
            continue
        deadline_count += _upsert_graph_deadline(session, item, deadline)
        deadline_entity = _upsert_entity(
            session,
            entity_type="DEADLINE",
            name=label,
            canonical_name=_deadline_key(item.document_id, deadline),
            issuer=issuer or item.issuer,
            external_ref=None,
            confidence=_confidence(deadline.get("confidence"), 0.55),
            evidence=deadline.get("evidence") or label,
            metadata={
                "deadline_type": deadline.get("deadline_type"),
                "deadline_date": deadline.get("deadline_date"),
                "raw_date": deadline.get("raw_date"),
            },
        )
        entity_ids.add(deadline_entity)
        relationship_count += _upsert_edge(
            session,
            document_entity,
            deadline_entity,
            "HAS_DEADLINE",
            item,
            _confidence(deadline.get("confidence"), 0.55),
            deadline.get("evidence") or label,
        )

    return {
        "entity_count": len(entity_ids),
        "relationship_count": relationship_count,
        "stakeholder_count": stakeholder_count,
        "obligation_count": obligation_count,
        "deadline_count": deadline_count,
        **family_result,
    }


def _heuristic_extraction(item: GraphInput) -> dict[str, Any]:
    title = _clean(item.title)
    body = _clean(item.text_content)
    haystack = f"{title}\n{body[:18000]}"
    document_type = _detect_document_type(haystack, item.document_type)
    metadata = _extract_metadata(haystack, item.issue_date)
    family_name, family_confidence, family_evidence = _infer_family(title, haystack, document_type)
    relationships = _extract_relationships(haystack, family_name, document_type)
    stakeholders = _extract_stakeholders(haystack)
    deadlines = _extract_deadlines(body or title)
    obligations = _extract_obligations(body, stakeholders, deadlines)

    relation = "NONE"
    if relationships:
        relation = relationships[0]["relationship_type"]
    return {
        "core_identity": {
            "issuer": item.issuer,
            "regulation_name": (
                family_name if document_type in {"REGULATION", "AMENDMENT"} else None
            ),
            "notification_name": title if document_type == "NOTIFICATION" else None,
            "document_title": title,
            "document_type": document_type,
            "confidence": 0.65 if family_name else 0.45,
            "evidence": _clip(title, 300),
        },
        "metadata": {
            **metadata,
            "confidence": 0.68 if any(metadata.values()) else 0.35,
            "evidence": _clip(haystack, 450),
        },
        "family_resolution": {
            "inferred_family": family_name,
            "document_type": document_type,
            "amendment_number": metadata.get("amendment_number"),
            "relationship": relation,
            "confidence": family_confidence,
            "evidence": family_evidence,
        },
        "relationships": relationships,
        "stakeholders": stakeholders,
        "obligations": obligations,
        "deadlines": deadlines,
        "_meta": {"extractor": "heuristic"},
    }


def _build_graph_prompt(item: GraphInput) -> str:
    excerpt = _clean(item.text_content)[:10000]
    return "\n".join(
        [
            f"Document ID: {item.document_id}",
            f"Title: {item.title}",
            f"Issuer: {item.issuer or 'unknown'}",
            f"Source URL: {item.source_url}",
            f"Existing document type: {item.document_type or 'unknown'}",
            f"Issue date: {item.issue_date.isoformat() if item.issue_date else 'unknown'}",
            "",
            "Primary document text excerpt:",
            excerpt,
        ]
    )


def _looks_like_graph_payload(payload: dict[str, Any]) -> bool:
    return all(
        key in payload
        for key in (
            "core_identity",
            "family_resolution",
            "relationships",
            "stakeholders",
            "obligations",
            "deadlines",
        )
    )


def _merge_with_heuristic(ai_payload: dict[str, Any], heuristic: dict[str, Any]) -> dict[str, Any]:
    merged = dict(heuristic)
    for key in (
        "core_identity",
        "metadata",
        "family_resolution",
        "relationships",
        "stakeholders",
        "obligations",
        "deadlines",
    ):
        value = ai_payload.get(key)
        if value:
            merged[key] = value

    merged["relationships"] = _dedupe_records(
        [
            *_list_of_dicts(merged.get("relationships")),
            *_list_of_dicts(heuristic.get("relationships")),
        ],
        key_fields=("relationship_type", "target_entity"),
    )
    merged["stakeholders"] = _dedupe_records(
        [
            *_list_of_dicts(merged.get("stakeholders")),
            *_list_of_dicts(heuristic.get("stakeholders")),
        ],
        key_fields=("stakeholder",),
    )
    merged["obligations"] = _dedupe_records(
        [*_list_of_dicts(merged.get("obligations")), *_list_of_dicts(heuristic.get("obligations"))],
        key_fields=("obligation", "affected_party"),
    )
    merged["deadlines"] = _dedupe_records(
        [*_list_of_dicts(merged.get("deadlines")), *_list_of_dicts(heuristic.get("deadlines"))],
        key_fields=("deadline_type", "deadline_date", "raw_date"),
    )
    merged["_meta"] = {"extractor": "ai_plus_heuristic"}
    return merged


def _apply_family_enrichment(
    session: Any,
    item: GraphInput,
    extraction: dict[str, Any],
) -> dict[str, Any]:
    current = _current_family_assignment(session, item.document_id)
    before_family_id = current.get("family_id")
    before_assignment_type = current.get("assignment_type")

    family = _as_dict(extraction.get("family_resolution"))
    inferred_family = _clean(family.get("inferred_family"))
    confidence = _confidence(family.get("confidence"), 0.0)
    evidence = _clean(family.get("evidence"))

    applied = False
    after_family_id = before_family_id
    after_assignment_type = before_assignment_type
    if inferred_family and confidence >= 0.72 and _is_real_family_name(inferred_family):
        if before_family_id:
            after_family_id = before_family_id
            applied = _maybe_update_family_title(
                session,
                before_family_id,
                inferred_family,
                family.get("document_type"),
                confidence,
            )
        else:
            after_family_id = _find_or_create_graph_family(
                session,
                inferred_family,
                item.issuer,
                family.get("document_type"),
            )
            applied = True
        after_assignment_type = "AI_ENRICHED_FAMILY" if applied else "AI_CONFIRMED_FAMILY"
        _upsert_family_assignment(
            session,
            item.document_id,
            after_family_id,
            after_assignment_type,
            confidence,
            evidence,
        )
        if item.document_version_id and after_family_id:
            registry_version_id = _upsert_family_registry_version(
                session,
                item,
                after_family_id,
                extraction,
            )
            _refresh_family_latest_version(session, after_family_id)
            _maybe_link_prior_family_version(
                session,
                after_family_id,
                registry_version_id,
                family.get("relationship"),
                confidence,
                evidence,
            )

    session.execute(
        text(
            """
            insert into regulatory_graph_family_enrichment (
              document_id,
              document_version_id,
              before_family_id,
              after_family_id,
              before_assignment_type,
              after_assignment_type,
              inferred_family,
              confidence,
              evidence,
              applied
            )
            values (
              :document_id,
              :document_version_id,
              :before_family_id,
              :after_family_id,
              :before_assignment_type,
              :after_assignment_type,
              :inferred_family,
              :confidence,
              :evidence,
              :applied
            )
            on conflict (document_id) do update set
              document_version_id = excluded.document_version_id,
              before_family_id = excluded.before_family_id,
              after_family_id = excluded.after_family_id,
              before_assignment_type = excluded.before_assignment_type,
              after_assignment_type = excluded.after_assignment_type,
              inferred_family = excluded.inferred_family,
              confidence = excluded.confidence,
              evidence = excluded.evidence,
              applied = excluded.applied,
              updated_at = now()
            """
        ),
        {
            "document_id": item.document_id,
            "document_version_id": item.document_version_id,
            "before_family_id": before_family_id,
            "after_family_id": after_family_id,
            "before_assignment_type": before_assignment_type,
            "after_assignment_type": after_assignment_type,
            "inferred_family": inferred_family,
            "confidence": confidence,
            "evidence": evidence,
            "applied": applied,
        },
    )
    return {
        "family_before": before_family_id,
        "family_after": after_family_id,
        "family_applied": applied,
    }


def _upsert_entity(
    session: Any,
    *,
    entity_type: str,
    name: str,
    canonical_name: str,
    issuer: str | None,
    external_ref: str | None,
    confidence: float,
    evidence: str | None,
    metadata: dict[str, Any],
) -> int:
    row = session.execute(
        text(
            """
            select entity_id
            from regulatory_graph_entities
            where entity_type = :entity_type
              and canonical_name = :canonical_name
              and coalesce(issuer, '') = coalesce(:issuer, '')
              and coalesce(external_ref, '') = coalesce(:external_ref, '')
            limit 1
            """
        ),
        {
            "entity_type": entity_type,
            "canonical_name": canonical_name,
            "issuer": issuer,
            "external_ref": external_ref,
        },
    ).mappings().first()
    if row:
        session.execute(
            text(
                """
                update regulatory_graph_entities
                set name = :name,
                    confidence = greatest(confidence, :confidence),
                    evidence = coalesce(:evidence, evidence),
                    metadata = regulatory_graph_entities.metadata || cast(:metadata as jsonb),
                    updated_at = now()
                where entity_id = :entity_id
                """
            ),
            {
                "entity_id": row["entity_id"],
                "name": name,
                "confidence": confidence,
                "evidence": evidence,
                "metadata": json.dumps(metadata, default=str),
            },
        )
        return int(row["entity_id"])

    inserted = session.execute(
        text(
            """
            insert into regulatory_graph_entities (
              entity_type,
              name,
              canonical_name,
              issuer,
              external_ref,
              confidence,
              evidence,
              metadata
            )
            values (
              :entity_type,
              :name,
              :canonical_name,
              :issuer,
              :external_ref,
              :confidence,
              :evidence,
              cast(:metadata as jsonb)
            )
            returning entity_id
            """
        ),
        {
            "entity_type": entity_type,
            "name": name,
            "canonical_name": canonical_name,
            "issuer": issuer,
            "external_ref": external_ref,
            "confidence": confidence,
            "evidence": evidence,
            "metadata": json.dumps(metadata, default=str),
        },
    ).scalar_one()
    return int(inserted)


def _link_document_entity(
    session: Any,
    item: GraphInput,
    entity_id: int,
    role: str,
    confidence: float,
    evidence: str | None,
) -> None:
    session.execute(
        text(
            """
            insert into regulatory_graph_document_entities (
              document_id,
              document_version_id,
              entity_id,
              role,
              confidence,
              evidence
            )
            values (
              :document_id,
              :document_version_id,
              :entity_id,
              :role,
              :confidence,
              :evidence
            )
            on conflict (document_id, entity_id, role) do update set
              document_version_id = excluded.document_version_id,
              confidence = greatest(regulatory_graph_document_entities.confidence,
                                    excluded.confidence),
              evidence = coalesce(excluded.evidence,
                                  regulatory_graph_document_entities.evidence)
            """
        ),
        {
            "document_id": item.document_id,
            "document_version_id": item.document_version_id,
            "entity_id": entity_id,
            "role": role,
            "confidence": confidence,
            "evidence": evidence,
        },
    )


def _upsert_edge(
    session: Any,
    from_entity_id: int,
    to_entity_id: int,
    relationship_type: str,
    item: GraphInput,
    confidence: float,
    evidence: str | None,
    metadata: dict[str, Any] | None = None,
) -> int:
    row = session.execute(
        text(
            """
            select edge_id
            from regulatory_graph_edges
            where from_entity_id = :from_entity_id
              and to_entity_id = :to_entity_id
              and relationship_type = :relationship_type
              and coalesce(source_document_id, 0) = coalesce(:source_document_id, 0)
            limit 1
            """
        ),
        {
            "from_entity_id": from_entity_id,
            "to_entity_id": to_entity_id,
            "relationship_type": relationship_type,
            "source_document_id": item.document_id,
        },
    ).mappings().first()
    if row:
        session.execute(
            text(
                """
                update regulatory_graph_edges
                set confidence = greatest(confidence, :confidence),
                    evidence = coalesce(:evidence, evidence),
                    metadata = regulatory_graph_edges.metadata || cast(:metadata as jsonb),
                    updated_at = now()
                where edge_id = :edge_id
                """
            ),
            {
                "edge_id": row["edge_id"],
                "confidence": confidence,
                "evidence": evidence,
                "metadata": json.dumps(metadata or {}, default=str),
            },
        )
        return 0
    session.execute(
        text(
            """
            insert into regulatory_graph_edges (
              from_entity_id,
              to_entity_id,
              relationship_type,
              source_document_id,
              source_document_version_id,
              confidence,
              evidence,
              metadata
            )
            values (
              :from_entity_id,
              :to_entity_id,
              :relationship_type,
              :source_document_id,
              :source_document_version_id,
              :confidence,
              :evidence,
              cast(:metadata as jsonb)
            )
            """
        ),
        {
            "from_entity_id": from_entity_id,
            "to_entity_id": to_entity_id,
            "relationship_type": relationship_type,
            "source_document_id": item.document_id,
            "source_document_version_id": item.document_version_id,
            "confidence": confidence,
            "evidence": evidence,
            "metadata": json.dumps(metadata or {}, default=str),
        },
    )
    return 1


def _upsert_extraction_audit(
    session: Any,
    item: GraphInput,
    extraction: dict[str, Any],
    *,
    used_ai: bool,
    error: str | None,
) -> None:
    model = (
        settings.llm_model_agent
        or settings.llm_model_summary
        or settings.llm_model_chat
        or "offline-demo"
    )
    provider = settings.llm_provider
    if provider == "offline" and settings.parallel_api_key:
        provider = "parallel"
    status = "AI_EXTRACTED" if used_ai else ("FALLBACK_EXTRACTED" if error else "HEURISTIC")
    session.execute(
        text(
            """
            insert into regulatory_graph_extractions (
              document_id,
              document_version_id,
              provider,
              model,
              status,
              used_ai,
              extraction_json,
              error
            )
            values (
              :document_id,
              :document_version_id,
              :provider,
              :model,
              :status,
              :used_ai,
              cast(:extraction_json as jsonb),
              :error
            )
            on conflict (document_id) do update set
              document_version_id = excluded.document_version_id,
              provider = excluded.provider,
              model = excluded.model,
              status = excluded.status,
              used_ai = excluded.used_ai,
              extraction_json = excluded.extraction_json,
              error = excluded.error,
              updated_at = now()
            """
        ),
        {
            "document_id": item.document_id,
            "document_version_id": item.document_version_id,
            "provider": provider,
            "model": model,
            "status": status,
            "used_ai": used_ai,
            "extraction_json": json.dumps(extraction, default=str),
            "error": error,
        },
    )


def _upsert_stakeholder(session: Any, item: GraphInput, stakeholder: dict[str, Any]) -> int:
    label = _clean(stakeholder.get("stakeholder"))
    session.execute(
        text(
            """
            insert into regulatory_graph_stakeholders (
              document_id,
              document_version_id,
              stakeholder,
              normalized_stakeholder,
              confidence,
              evidence
            )
            values (
              :document_id,
              :document_version_id,
              :stakeholder,
              :normalized_stakeholder,
              :confidence,
              :evidence
            )
            on conflict (document_id, normalized_stakeholder) do update set
              stakeholder = excluded.stakeholder,
              confidence = greatest(regulatory_graph_stakeholders.confidence,
                                    excluded.confidence),
              evidence = coalesce(excluded.evidence,
                                  regulatory_graph_stakeholders.evidence)
            """
        ),
        {
            "document_id": item.document_id,
            "document_version_id": item.document_version_id,
            "stakeholder": label,
            "normalized_stakeholder": _canonical(label),
            "confidence": _confidence(stakeholder.get("confidence"), 0.6),
            "evidence": stakeholder.get("evidence"),
        },
    )
    return 1


def _upsert_obligation(session: Any, item: GraphInput, obligation: dict[str, Any]) -> int:
    session.execute(
        text(
            """
            insert into regulatory_graph_obligations (
              document_id,
              document_version_id,
              obligation,
              deadline_date,
              deadline_type,
              affected_party,
              confidence,
              evidence
            )
            values (
              :document_id,
              :document_version_id,
              :obligation,
              :deadline_date,
              :deadline_type,
              :affected_party,
              :confidence,
              :evidence
            )
            on conflict do nothing
            """
        ),
        {
            "document_id": item.document_id,
            "document_version_id": item.document_version_id,
            "obligation": _clean(obligation.get("obligation")),
            "deadline_date": _parse_date(obligation.get("deadline")),
            "deadline_type": _clean(obligation.get("deadline_type")),
            "affected_party": _clean(obligation.get("affected_party")),
            "confidence": _confidence(obligation.get("confidence"), 0.6),
            "evidence": obligation.get("evidence"),
        },
    )
    return 1


def _upsert_graph_deadline(session: Any, item: GraphInput, deadline: dict[str, Any]) -> int:
    session.execute(
        text(
            """
            insert into regulatory_graph_deadlines (
              document_id,
              document_version_id,
              deadline_type,
              deadline_date,
              raw_date,
              confidence,
              evidence
            )
            values (
              :document_id,
              :document_version_id,
              :deadline_type,
              :deadline_date,
              :raw_date,
              :confidence,
              :evidence
            )
            on conflict do nothing
            """
        ),
        {
            "document_id": item.document_id,
            "document_version_id": item.document_version_id,
            "deadline_type": _clean(deadline.get("deadline_type")) or "UNKNOWN_DATE",
            "deadline_date": _parse_date(deadline.get("deadline_date")),
            "raw_date": _clean(deadline.get("raw_date")),
            "confidence": _confidence(deadline.get("confidence"), 0.55),
            "evidence": deadline.get("evidence"),
        },
    )
    return 1


def _current_family_assignment(session: Any, document_id: int) -> dict[str, Any]:
    row = session.execute(
        text(
            """
            select family_id, assignment_type
            from document_family_assignments
            where document_id = :document_id
            """
        ),
        {"document_id": document_id},
    ).mappings().first()
    return dict(row) if row else {"family_id": None, "assignment_type": None}


def _maybe_update_family_title(
    session: Any,
    family_id: int,
    inferred_family: str,
    document_type: str | None,
    confidence: float,
) -> bool:
    row = session.execute(
        text(
            """
            select canonical_title
            from document_families
            where family_id = :family_id
            """
        ),
        {"family_id": family_id},
    ).mappings().first()
    if not row:
        return False
    current = _clean(row["canonical_title"])
    if not _family_title_is_better(inferred_family, current, confidence):
        return False
    session.execute(
        text(
            """
            update document_families
            set canonical_title = :canonical_title,
                document_type = coalesce(:document_type, document_type),
                updated_at = now()
            where family_id = :family_id
            """
        ),
        {
            "family_id": family_id,
            "canonical_title": inferred_family,
            "document_type": document_type,
        },
    )
    return True


def _find_or_create_graph_family(
    session: Any,
    inferred_family: str,
    issuer: str | None,
    document_type: str | None,
) -> int:
    row = session.execute(
        text(
            """
            select family_id
            from document_families
            where lower(canonical_title) = lower(:canonical_title)
              and coalesce(lower(issuer), '') = coalesce(lower(:issuer), '')
            limit 1
            """
        ),
        {"canonical_title": inferred_family, "issuer": issuer},
    ).mappings().first()
    if row:
        return int(row["family_id"])
    inserted = session.execute(
        text(
            """
            insert into document_families (
              canonical_title,
              issuer,
              document_type
            )
            values (
              :canonical_title,
              :issuer,
              :document_type
            )
            returning family_id
            """
        ),
        {
            "canonical_title": inferred_family,
            "issuer": issuer,
            "document_type": document_type,
        },
    ).scalar_one()
    return int(inserted)


def _upsert_family_assignment(
    session: Any,
    document_id: int,
    family_id: int | None,
    assignment_type: str,
    confidence: float,
    evidence: str | None,
) -> None:
    session.execute(
        text(
            """
            insert into document_family_assignments (
              document_id,
              family_id,
              assignment_type,
              confidence,
              evidence
            )
            values (
              :document_id,
              :family_id,
              :assignment_type,
              :confidence,
              :evidence
            )
            on conflict (document_id) do update set
              family_id = excluded.family_id,
              assignment_type = excluded.assignment_type,
              confidence = greatest(document_family_assignments.confidence,
                                    excluded.confidence),
              evidence = excluded.evidence,
              updated_at = now()
            """
        ),
        {
            "document_id": document_id,
            "family_id": family_id,
            "assignment_type": assignment_type,
            "confidence": confidence,
            "evidence": evidence,
        },
    )


def _upsert_family_registry_version(
    session: Any,
    item: GraphInput,
    family_id: int,
    extraction: dict[str, Any],
) -> int:
    metadata = _as_dict(extraction.get("metadata"))
    family = _as_dict(extraction.get("family_resolution"))
    amendment_number = _int_or_none(family.get("amendment_number")) or _int_or_none(
        metadata.get("amendment_number")
    )
    version_number = amendment_number + 1 if amendment_number else 1
    version_label = (
        f"Amendment {amendment_number}"
        if amendment_number
        else _clean(family.get("relationship")) or "AI resolved version"
    )
    row = session.execute(
        text(
            """
            select registry_version_id
            from document_version_registry
            where document_version_id = :document_version_id
            limit 1
            """
        ),
        {"document_version_id": item.document_version_id},
    ).mappings().first()
    params = {
        "family_id": family_id,
        "document_id": item.document_id,
        "document_version_id": item.document_version_id,
        "version_number": version_number,
        "version_label": version_label,
        "publication_date": _parse_date(metadata.get("publication_date")) or item.issue_date,
        "issue_date": item.issue_date,
        "effective_date": _parse_date(metadata.get("effective_date")),
        "content_hash": item.content_hash,
        "amendment_number": amendment_number,
        "amendment_label": version_label if amendment_number else None,
        "referenced_instrument": family.get("inferred_family"),
        "referenced_notification": metadata.get("notification_number"),
    }
    if row:
        session.execute(
            text(
                """
                update document_version_registry
                set family_id = :family_id,
                    version_number = coalesce(:version_number, version_number),
                    version_label = coalesce(:version_label, version_label),
                    publication_date = coalesce(:publication_date, publication_date),
                    issue_date = coalesce(:issue_date, issue_date),
                    effective_date = coalesce(:effective_date, effective_date),
                    amendment_number = coalesce(:amendment_number, amendment_number),
                    amendment_label = coalesce(:amendment_label, amendment_label),
                    referenced_instrument = coalesce(:referenced_instrument,
                                                     referenced_instrument),
                    referenced_notification = coalesce(:referenced_notification,
                                                       referenced_notification),
                    updated_at = now()
                where registry_version_id = :registry_version_id
                """
            ),
            {**params, "registry_version_id": row["registry_version_id"]},
        )
        return int(row["registry_version_id"])

    inserted = session.execute(
        text(
            """
            insert into document_version_registry (
              family_id,
              document_id,
              document_version_id,
              version_number,
              version_label,
              publication_date,
              issue_date,
              effective_date,
              content_hash,
              amendment_number,
              amendment_label,
              referenced_instrument,
              referenced_notification
            )
            values (
              :family_id,
              :document_id,
              :document_version_id,
              :version_number,
              :version_label,
              :publication_date,
              :issue_date,
              :effective_date,
              :content_hash,
              :amendment_number,
              :amendment_label,
              :referenced_instrument,
              :referenced_notification
            )
            returning registry_version_id
            """
        ),
        params,
    ).scalar_one()
    return int(inserted)


def _refresh_family_latest_version(session: Any, family_id: int) -> None:
    session.execute(
        text(
            """
            update document_families f
            set latest_version_id = latest.registry_version_id,
                updated_at = now()
            from (
              select registry_version_id
              from document_version_registry
              where family_id = :family_id
              order by
                publication_date desc nulls last,
                issue_date desc nulls last,
                registry_version_id desc
              limit 1
            ) latest
            where f.family_id = :family_id
            """
        ),
        {"family_id": family_id},
    )


def _maybe_link_prior_family_version(
    session: Any,
    family_id: int,
    registry_version_id: int,
    relationship: str | None,
    confidence: float,
    evidence: str | None,
) -> None:
    relationship_type = _relationship_type(relationship)
    if relationship_type not in {"AMENDS", "SUPERSEDES", "REPEALS", "EXTENDS"}:
        return
    prior = session.execute(
        text(
            """
            select registry_version_id
            from document_version_registry
            where family_id = :family_id
              and registry_version_id <> :registry_version_id
            order by
              version_number desc nulls last,
              publication_date desc nulls last,
              registry_version_id desc
            limit 1
            """
        ),
        {"family_id": family_id, "registry_version_id": registry_version_id},
    ).mappings().first()
    if not prior:
        return
    session.execute(
        text(
            """
            update document_version_registry
            set parent_registry_version_id = coalesce(parent_registry_version_id,
                                                      :prior_registry_version_id),
                supersedes_registry_version_id = case
                  when :relationship_type in ('SUPERSEDES', 'REPEALS')
                  then coalesce(supersedes_registry_version_id,
                                :prior_registry_version_id)
                  else supersedes_registry_version_id
                end,
                updated_at = now()
            where registry_version_id = :registry_version_id
            """
        ),
        {
            "registry_version_id": registry_version_id,
            "prior_registry_version_id": prior["registry_version_id"],
            "relationship_type": relationship_type,
        },
    )
    session.execute(
        text(
            """
            insert into document_version_relationships (
              family_id,
              from_registry_version_id,
              to_registry_version_id,
              relationship_type,
              confidence,
              evidence
            )
            values (
              :family_id,
              :from_registry_version_id,
              :to_registry_version_id,
              :relationship_type,
              :confidence,
              :evidence
            )
            on conflict do nothing
            """
        ),
        {
            "family_id": family_id,
            "from_registry_version_id": registry_version_id,
            "to_registry_version_id": prior["registry_version_id"],
            "relationship_type": relationship_type,
            "confidence": confidence,
            "evidence": evidence,
        },
    )


def _detect_document_type(text_value: str, fallback: str | None = None) -> str:
    lower = f" {text_value.lower()} "
    for doc_type, terms in DOCUMENT_TYPE_TERMS.items():
        if any(term in lower for term in terms):
            return doc_type
    return (fallback or "OTHER").upper()


def _extract_metadata(text_value: str, issue_date: date | None) -> dict[str, Any]:
    lower = text_value.lower()
    amendment_number = None
    for label, number in ORDINALS.items():
        if re.search(rf"\b{label}\s+amendment\b", lower):
            amendment_number = number
            break
    if amendment_number is None:
        numeric = re.search(r"\b(\d{1,2})(?:st|nd|rd|th)?\s+amendment\b", lower)
        if numeric:
            amendment_number = int(numeric.group(1))

    notification = re.search(
        r"\b(?:notification|no\.|number)\s*(?:no\.?)?\s*[:\-]?\s*([A-Z0-9./\-() ]{4,80})",
        text_value,
        flags=re.IGNORECASE,
    )
    regulation = re.search(
        r"\b([A-Z]{2,8}/[A-Z0-9./\-]{3,80}|No\.\s*[A-Z0-9./\-]{3,80})",
        text_value,
        flags=re.IGNORECASE,
    )
    gazette = re.search(
        r"\bgazette\s+(?:notification\s+)?(?:no\.?)?\s*[:\-]?\s*([A-Z0-9./\- ]{3,80})",
        text_value,
        flags=re.IGNORECASE,
    )
    effective_date = None
    effective_match = re.search(
        r"(?:come into force|effective from|with effect from|shall come into force)"
        r".{0,120}?(\d{1,2}[-/.]\d{1,2}[-/.]\d{2,4}|\d{1,2}\s+[A-Za-z]+\s+\d{4})",
        text_value,
        flags=re.IGNORECASE,
    )
    if effective_match:
        effective_date = _parse_date(effective_match.group(1))
    return {
        "regulation_number": _clean(regulation.group(1)) if regulation else None,
        "notification_number": _clean(notification.group(1)) if notification else None,
        "gazette_number": _clean(gazette.group(1)) if gazette else None,
        "amendment_number": amendment_number,
        "publication_date": issue_date,
        "effective_date": effective_date,
    }


def _infer_family(title: str, text_value: str, document_type: str) -> tuple[str | None, float, str]:
    title = _clean(title)
    amendment = re.search(
        r"(?P<family>.+?)\s*\((?P<label>first|second|third|fourth|fifth|sixth|"
        r"seventh|eighth|ninth|tenth|\d{1,2}(?:st|nd|rd|th)?)\s+amendment\)"
        r"\s+regulations?",
        title,
        flags=re.IGNORECASE,
    )
    if amendment:
        family = _clean(f"{amendment.group('family')} Regulations")
        return family, 0.86, _clip(amendment.group(0), 300)

    corrigendum = re.search(
        r"\bcorrigendum\s+(?:to|for)\s+(.+?)(?:\s+dated\b|$)",
        title,
        flags=re.IGNORECASE,
    )
    if corrigendum:
        return _clean(corrigendum.group(1)), 0.82, _clip(title, 300)

    quoted = re.search(
        r"([A-Z][A-Za-z ]+(?:Regulations|Rules|Policy|Guidelines|Act),?\s*\d{4})",
        text_value,
    )
    if quoted:
        return _clean(quoted.group(1)), 0.74, _clip(quoted.group(1), 300)

    if document_type in {"REGULATION", "POLICY", "ACT", "TENDER", "CONSULTATION", "ORDER"}:
        return _strip_noise_from_title(title), 0.68, _clip(title, 300)
    return None, 0.32, "No stable family signal found."


def _extract_relationships(
    text_value: str,
    family_name: str | None,
    document_type: str,
) -> list[dict[str, Any]]:
    lower = text_value.lower()
    relationships: list[dict[str, Any]] = []
    for rel_type, terms in RELATIONSHIP_TERMS.items():
        if not any(term in lower for term in terms):
            continue
        evidence = _sentence_with_terms(text_value, terms)
        if not _relationship_is_grounded(rel_type, document_type, evidence):
            continue
        target = _target_from_evidence(evidence) or family_name
        if not target:
            continue
        relationships.append(
            {
                "relationship_type": rel_type,
                "target_entity": target,
                "target_entity_type": "REGULATION",
                "confidence": 0.78 if rel_type in {"AMENDS", "SUPERSEDES"} else 0.64,
                "evidence": evidence,
            }
        )

    references = _referenced_instruments(text_value)
    for reference in references[:8]:
        if family_name and _canonical(reference) == _canonical(family_name):
            continue
        relationships.append(
            {
                "relationship_type": "REFERENCES",
                "target_entity": reference,
                "target_entity_type": _entity_type(reference),
                "confidence": 0.62,
                "evidence": reference,
            }
        )
    return _dedupe_records(relationships, key_fields=("relationship_type", "target_entity"))[:12]


def _extract_stakeholders(text_value: str) -> list[dict[str, Any]]:
    lower = text_value.lower()
    stakeholders: list[dict[str, Any]] = []
    for stakeholder, terms in STAKEHOLDER_PATTERNS.items():
        if any(term in lower for term in terms):
            stakeholders.append(
                {
                    "stakeholder": stakeholder,
                    "confidence": 0.74,
                    "evidence": _sentence_with_terms(text_value, terms),
                }
            )
    return stakeholders[:12]


def _extract_deadlines(text_value: str) -> list[dict[str, Any]]:
    results = []
    for deadline in extract_deadline_intelligence(text_value)[:20]:
        results.append(
            {
                "deadline_type": deadline.deadline_type,
                "deadline_date": deadline.normalized_date,
                "raw_date": deadline.raw_date,
                "confidence": deadline.confidence,
                "evidence": deadline.evidence_snippet,
            }
        )
    return results


def _extract_obligations(
    text_value: str,
    stakeholders: list[dict[str, Any]],
    deadlines: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    sentences = _sentences(text_value)
    obligations: list[dict[str, Any]] = []
    obligation_terms = (
        "shall",
        "must",
        "required to",
        "submit",
        "furnish",
        "file",
        "participate",
        "comply",
    )
    for sentence in sentences:
        lower = sentence.lower()
        if not any(term in lower for term in obligation_terms):
            continue
        affected_party = _affected_party_for_sentence(sentence, stakeholders)
        deadline = _nearest_deadline(sentence, deadlines)
        obligations.append(
            {
                "obligation": _clip(sentence, 260),
                "deadline": deadline.get("deadline_date") if deadline else None,
                "deadline_type": deadline.get("deadline_type") if deadline else None,
                "affected_party": affected_party,
                "confidence": 0.66 if affected_party else 0.56,
                "evidence": _clip(sentence, 320),
            }
        )
        if len(obligations) >= 12:
            break
    return obligations


def _referenced_instruments(text_value: str) -> list[str]:
    patterns = (
        r"([A-Z][A-Za-z ]{4,90}(?:Regulations|Rules|Guidelines|Policy|Act),?\s*\d{4})",
        r"(Electricity Act,?\s*2003)",
        r"(Energy Conservation Act,?\s*2001)",
        r"((?:Central Electricity Regulatory Commission|CERC)[A-Za-z ()-]{4,90}"
        r"(?:Regulations|Rules))",
    )
    results: list[str] = []
    for pattern in patterns:
        for match in re.finditer(pattern, text_value):
            value = _clean(match.group(1))
            if len(value) > 8 and value not in results:
                results.append(value)
    return results


def _target_from_evidence(evidence: str) -> str | None:
    reference = _referenced_instruments(evidence)
    if reference:
        return reference[0]
    quoted = re.search(r"['\"]([^'\"]{12,140})['\"]", evidence)
    if quoted:
        return _clean(quoted.group(1))
    return None


def _sentence_with_terms(text_value: str, terms: tuple[str, ...]) -> str:
    for sentence in _sentences(text_value):
        lower = sentence.lower()
        if any(term in lower for term in terms):
            return _clip(sentence, 360)
    return _clip(text_value, 360)


def _sentences(text_value: str) -> list[str]:
    compact = _clean(text_value)
    parts = re.split(r"(?<=[.;:])\s+|\n+", compact)
    return [part.strip() for part in parts if len(part.strip()) >= 25]


def _affected_party_for_sentence(
    sentence: str,
    stakeholders: list[dict[str, Any]],
) -> str | None:
    lower = sentence.lower()
    for stakeholder in stakeholders:
        label = stakeholder.get("stakeholder")
        if label and any(term in lower for term in STAKEHOLDER_PATTERNS.get(label, ())):
            return label
    return stakeholders[0]["stakeholder"] if stakeholders else None


def _nearest_deadline(
    sentence: str,
    deadlines: list[dict[str, Any]],
) -> dict[str, Any] | None:
    lower = sentence.lower()
    for deadline in deadlines:
        raw = str(deadline.get("raw_date") or "").lower()
        if raw and raw in lower:
            return deadline
    return deadlines[0] if deadlines else None


def _strip_noise_from_title(title: str) -> str:
    cleaned = re.sub(r"^annexure\s+\.{0,3}\s*", "", title, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+-\s+(reg|final|draft)\.?$", "", cleaned, flags=re.IGNORECASE)
    return _clean(cleaned)


def _family_title_is_better(candidate: str, current: str, confidence: float) -> bool:
    if confidence < 0.80:
        return False
    if not current:
        return True
    noisy_terms = ("annexure", "...", "draft central electricity regulatory commission")
    if any(term in current.lower() for term in noisy_terms) and len(candidate) <= len(current):
        return True
    return False


def _is_real_family_name(value: str) -> bool:
    lower = value.lower()
    if len(value) < 12:
        return False
    generic = {"home", "orders", "notification", "notices", "solar", "wind", "recruitments"}
    return lower not in generic


def _entity_type(value: Any) -> str:
    raw = _clean(value).upper()
    if raw in {
        "DOCUMENT",
        "REGULATION",
        "NOTIFICATION",
        "CONSULTATION",
        "TENDER",
        "STAKEHOLDER",
        "OBLIGATION",
        "DEADLINE",
        "POLICY",
        "ORDER",
        "CIRCULAR",
        "ACT",
        "GUIDELINE",
    }:
        return raw
    lower = raw.lower()
    if "tender" in lower or "rfp" in lower:
        return "TENDER"
    if "policy" in lower:
        return "POLICY"
    if "notification" in lower:
        return "NOTIFICATION"
    if "act" in lower:
        return "ACT"
    return "REGULATION" if "regulation" in lower else "OTHER"


def _relationship_type(value: Any) -> str | None:
    raw = _clean(value).upper()
    if raw in {
        "AMENDS",
        "SUPERSEDES",
        "REFERENCES",
        "IMPLEMENTS",
        "REPEALS",
        "EXTENDS",
        "AFFECTS",
        "HAS_DEADLINE",
        "HAS_OBLIGATION",
        "ISSUED_BY",
        "BELONGS_TO_FAMILY",
    }:
        return raw
    if raw in {"NONE", ""}:
        return None
    return "REFERENCES"


def _relationship_is_grounded(
    relationship_type: str,
    document_type: str,
    evidence: Any,
) -> bool:
    lower = _clean(evidence).lower()
    if relationship_type == "AMENDS":
        amendment_reference = re.search(
            r"\b(?:first|second|third|\d{1,2}(?:st|nd|rd|th)?)\s+amendment\b",
            lower,
        )
        return document_type in {"AMENDMENT", "CORRIGENDUM", "ADDENDUM"} or bool(
            amendment_reference
        )
    if relationship_type == "EXTENDS":
        return "extend" in lower and any(
            term in lower
            for term in (
                "last date",
                "deadline",
                "submission",
                "bid due",
                "comment",
                "hearing",
            )
        )
    return True


def _deadline_label(deadline: dict[str, Any]) -> str | None:
    deadline_type = _clean(deadline.get("deadline_type"))
    deadline_date = _clean(deadline.get("deadline_date"))
    raw_date = _clean(deadline.get("raw_date"))
    if not deadline_type and not deadline_date and not raw_date:
        return None
    return _clean(f"{deadline_type or 'DEADLINE'} {deadline_date or raw_date}")


def _deadline_key(document_id: int, deadline: dict[str, Any]) -> str:
    return _canonical(
        f"document:{document_id}:{deadline.get('deadline_type')}:{deadline.get('deadline_date')}:"
        f"{deadline.get('raw_date')}"
    )


def _obligation_key(document_id: int, obligation: str) -> str:
    digest = hashlib.sha1(_canonical(obligation).encode("utf-8")).hexdigest()[:16]
    return f"document:{document_id}:obligation:{digest}"


def _dedupe_records(
    records: list[dict[str, Any]],
    *,
    key_fields: tuple[str, ...],
) -> list[dict[str, Any]]:
    deduped: dict[tuple[str, ...], dict[str, Any]] = {}
    for record in records:
        key = tuple(_canonical(record.get(field)) for field in key_fields)
        if not any(key):
            continue
        current = deduped.get(key)
        if not current or _confidence(record.get("confidence"), 0) > _confidence(
            current.get("confidence"), 0
        ):
            deduped[key] = record
    return list(deduped.values())


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list_of_dicts(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _confidence(value: Any, fallback: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        parsed = fallback
    return max(0.0, min(1.0, parsed))


def _int_or_none(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _parse_date(value: Any) -> date | None:
    if isinstance(value, date):
        return value
    if not value:
        return None
    try:
        return date_parser.parse(str(value), dayfirst=True, fuzzy=True).date()
    except (ValueError, TypeError, OverflowError):
        return None


def _canonical(value: Any) -> str:
    cleaned = _clean(value).lower()
    cleaned = re.sub(r"[^a-z0-9]+", " ", cleaned)
    return " ".join(cleaned.split())


def _clean(value: Any) -> str:
    return " ".join(str(value or "").replace("\x00", " ").split())


def _clip(value: Any, limit: int = 220) -> str:
    cleaned = _clean(value)
    return cleaned if len(cleaned) <= limit else cleaned[:limit].rstrip() + "..."
