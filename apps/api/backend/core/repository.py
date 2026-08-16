import json
import logging
import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from typing import Any

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from backend.core.db import session_scope
from backend.core.logging import log_event
from backend.core.models import (
    DigestResponse,
    DiscoveredDoc,
    DiscoveryAuditRecord,
    EventIntelligence,
    EventSummary,
    ExtractedDoc,
    PriorVersionReference,
    RegulatoryChange,
    SourcePagePayload,
    SourcePageUpdatePayload,
    SourcePayload,
    SourceUpdatePayload,
    SubscriptionSettings,
    SummaryPayload,
    UserUpdatePayload,
)
from backend.core.system_docs import SYSTEM_DOCUMENTS
from backend.core.source_page_policy import (
    SourcePagePolicyError,
    diagnose_source_page_selection,
    page_url_permitted_for_source,
    validate_public_http_url,
    validate_source_page_url,
)
from backend.core.utils import canonical_url, sha256_normalized_text
from backend.pipeline.change_detector import (
    attach_change_to_summary,
    detect_regulatory_change,
    is_related_title,
    title_similarity,
)
from backend.pipeline.family_registry import (
    RegistryInput,
    RegistryResult,
    register_document_version_family,
)
from backend.pipeline.intelligence_gate import (
    assess_event_intelligence,
    attach_intelligence_to_summary,
)
from backend.pipeline.regulatory_knowledge_graph import (
    GraphInput,
    analyze_and_persist_regulatory_graph,
)
from backend.rag.indexing import enqueue_rag_index_job

logger = logging.getLogger(__name__)

SUMMARY_MODEL = "non-ai-v1"
TOPIC_KEYWORDS = {
    "solar": ["solar", "photovoltaic", "pv"],
    "wind": ["wind"],
    "tariff": ["tariff", "charges", "fee"],
    "open access": ["open access", "green energy open access"],
    "RPO/REC": ["rpo", "rec", "renewable purchase obligation", "renewable energy certificate"],
    "storage": ["storage", "battery", "bess"],
    "transmission": ["transmission", "grid", "ctu", "stu", "connectivity"],
    "thermal": ["thermal", "coal", "gas"],
    "tender": ["tender", "bid", "rfp"],
}
def _summary_payload(value: Any) -> SummaryPayload | None:
    if not value:
        return None
    if isinstance(value, SummaryPayload):
        return value
    return SummaryPayload.model_validate(value)


def _event_from_row(row: Any) -> EventSummary:
    data = row._mapping
    return EventSummary(
        id=data["id"],
        title=data["title"],
        issuing_body=data["issuing_body"],
        jurisdiction=data["jurisdiction"],
        issue_date=data["issue_date"],
        event_type=data["event_type"],
        topic_tags=list(data["topic_tags"] or []),
        raw_summary=data["raw_summary"],
        source_url=data["source_url"],
        detected_at=data["detected_at"],
        summary=_summary_payload(data["summary_json"]),
        is_read=bool(data["is_read"]),
        is_bookmarked=bool(data["is_bookmarked"]),
    )


EVENT_SELECT = """
select
  e.id,
  d.title,
  d.issuing_body,
  coalesce(d.jurisdiction::text, s.jurisdiction::text) as jurisdiction,
  d.issue_date,
  e.event_type::text as event_type,
  e.topic_tags,
  e.raw_summary,
  d.source_url,
  e.detected_at,
  sm.summary_json,
  coalesce(ues.is_read, false) as is_read,
  coalesce(ues.is_bookmarked, false) as is_bookmarked
from events e
join documents d on d.id = e.document_id
left join sources s on s.id = d.source_id
left join lateral (
  select summary_json
  from summaries
  where event_id = e.id
  order by created_at desc
  limit 1
) sm on true
left join user_event_state ues on ues.event_id = e.id and ues.user_id = :user_id
"""


def list_events(
    user_id: str | None,
    query: str | None = None,
    jurisdiction: str | None = None,
    source: str | None = None,
    topic: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    bookmarked: bool | None = None,
    page: int = 1,
    page_size: int = 50,
) -> list[EventSummary]:
    clauses = ["e.suppressed = false"]
    params: dict[str, Any] = {
        "user_id": user_id,
        "limit": page_size,
        "offset": (page - 1) * page_size,
    }
    if query:
        clauses.append(
            """
            (
              d.title ilike :query_like
              or d.issuing_body ilike :query_like
              or e.raw_summary ilike :query_like
              or :query = any(e.topic_tags)
            )
            """
        )
        params["query"] = query
        params["query_like"] = f"%{query}%"
    if jurisdiction:
        clauses.append("coalesce(d.jurisdiction::text, s.jurisdiction::text) = :jurisdiction")
        params["jurisdiction"] = jurisdiction
    if source:
        clauses.append("(s.code = :source or s.name ilike :source_like)")
        params["source"] = source
        params["source_like"] = f"%{source}%"
    if topic:
        clauses.append(":topic = any(e.topic_tags)")
        params["topic"] = topic
    if date_from:
        clauses.append("d.issue_date >= :date_from")
        params["date_from"] = date_from
    if date_to:
        clauses.append("d.issue_date <= :date_to")
        params["date_to"] = date_to
    if bookmarked is not None:
        clauses.append("coalesce(ues.is_bookmarked, false) = :bookmarked")
        params["bookmarked"] = bookmarked

    query = f"""
    {EVENT_SELECT}
    where {" and ".join(clauses)}
    order by e.detected_at desc
    limit :limit offset :offset
    """
    try:
        with session_scope() as session:
            rows = session.execute(text(query), params).all()
            return [_event_from_row(row) for row in rows]
    except SQLAlchemyError as exc:
        logger.warning("list_events failed: %s", exc)
        return []


def get_event(event_id: int, user_id: str | None) -> EventSummary | None:
    query = f"{EVENT_SELECT} where e.id = :event_id"
    try:
        with session_scope() as session:
            row = session.execute(text(query), {"event_id": event_id, "user_id": user_id}).first()
            if row:
                return _event_from_row(row)
    except SQLAlchemyError as exc:
        logger.warning("get_event(%s) failed: %s", event_id, exc)
    return None


def latest_digest(user_id: str | None) -> DigestResponse:
    try:
        with session_scope() as session:
            digest = session.execute(
                text(
                    """
                    select id, digest_date, event_count
                    from digests
                    order by digest_date desc
                    limit 1
                    """
                )
            ).first()
            if not digest:
                events = list_events(user_id=user_id)
                return DigestResponse(
                    digest_date=date.today(),
                    event_count=len(events),
                    events=events,
                )
            rows = session.execute(
                text(
                    f"""
                    {EVENT_SELECT}
                    join digest_events de on de.event_id = e.id
                    where de.digest_id = :digest_id and e.suppressed = false
                    order by e.detected_at desc
                    """
                ),
                {"digest_id": digest.id, "user_id": user_id},
            ).all()
            events = [_event_from_row(row) for row in rows]
            return DigestResponse(
                digest_date=digest.digest_date,
                event_count=len(events),
                events=events,
            )
    except SQLAlchemyError as exc:
        logger.warning("latest_digest failed: %s", exc)
        return DigestResponse(digest_date=date.today(), event_count=0, events=[])


def digest_by_date(digest_date: date, user_id: str | None) -> DigestResponse:
    try:
        with session_scope() as session:
            digest = session.execute(
                text("select id, digest_date from digests where digest_date = :digest_date"),
                {"digest_date": digest_date},
            ).first()
            if not digest:
                return latest_digest(user_id)
            rows = session.execute(
                text(
                    f"""
                    {EVENT_SELECT}
                    join digest_events de on de.event_id = e.id
                    where de.digest_id = :digest_id and e.suppressed = false
                    order by e.detected_at desc
                    """
                ),
                {"digest_id": digest.id, "user_id": user_id},
            ).all()
            events = [_event_from_row(row) for row in rows]
            return DigestResponse(
                digest_date=digest.digest_date,
                event_count=len(events),
                events=events,
            )
    except SQLAlchemyError as exc:
        logger.warning("digest_by_date(%s) failed: %s", digest_date, exc)
        return DigestResponse(digest_date=digest_date, event_count=0, events=[])


def list_sources() -> list[dict[str, Any]]:
    try:
        with session_scope() as session:
            rows = session.execute(
                text(
                    """
                    select id, code, name, jurisdiction::text as jurisdiction, url,
                           crawler_type::text as crawler_type, allowed_domains, hint, enabled,
                           last_checked_at, last_status, consecutive_failures
                    from sources
                    order by id
                    """
                )
            ).mappings()
            return [dict(row) for row in rows]
    except SQLAlchemyError as exc:
        logger.warning("list_sources failed: %s", exc)
        return []


def list_admin_users() -> list[dict[str, Any]]:
    try:
        with session_scope() as session:
            rows = session.execute(
                text(
                    """
                    select
                      p.id::text as id,
                      p.email,
                      p.full_name,
                      p.role::text as role,
                      p.created_at,
                      s.email_enabled,
                      s.frequency,
                      coalesce(s.topics, '{}') as topics
                    from profiles p
                    left join subscriptions s on s.user_id = p.id
                    order by p.created_at desc
                    """
                )
            ).mappings()
            return [dict(row) for row in rows]
    except SQLAlchemyError as exc:
        logger.warning("list_admin_users failed: %s", exc)
        return []


def update_admin_user(user_id: str, payload: UserUpdatePayload) -> dict[str, Any]:
    with session_scope() as session:
        row = session.execute(
            text(
                """
                update profiles
                set role = cast(:role as user_role_t)
                where id = cast(:user_id as uuid)
                returning id::text as id, email, full_name, role::text as role, created_at
                """
            ),
            {"user_id": user_id, "role": payload.role},
        ).mappings().first()
    return dict(row) if row else {}


def create_source(payload: SourcePayload) -> dict[str, Any]:
    values = payload.model_dump()
    values["url"] = validate_public_http_url(values["url"], field="source url")
    # Prefer explicit CDN/mirror domains from the admin; always keep website host
    # available via crawl_domains_for_source (source.url) even if this list is empty.
    values["allowed_domains"] = [
        str(domain).strip().lower().lstrip(".")
        for domain in (values.get("allowed_domains") or [])
        if str(domain).strip()
    ]
    with session_scope() as session:
        row = session.execute(
            text(
                """
                insert into sources
                  (code, name, jurisdiction, url, crawler_type, allowed_domains, hint, enabled)
                values
                  (:code, :name, cast(:jurisdiction as jurisdiction_t), :url,
                   cast(:crawler_type as crawler_t), :allowed_domains, :hint, :enabled)
                returning id, code, name, jurisdiction::text as jurisdiction, url,
                          crawler_type::text as crawler_type, allowed_domains, hint, enabled,
                          last_checked_at, last_status, consecutive_failures
                """
            ),
            values,
        ).mappings().first()
    return dict(row) if row else {}


def update_source(source_id: int, payload: SourceUpdatePayload) -> dict[str, Any]:
    values = payload.model_dump()
    values["source_id"] = source_id
    if values.get("url") is not None:
        values["url"] = validate_public_http_url(values["url"], field="source url")
    if values.get("allowed_domains") is not None:
        values["allowed_domains"] = [
            str(domain).strip().lower().lstrip(".")
            for domain in values["allowed_domains"]
            if str(domain).strip()
        ]
    with session_scope() as session:
        current = session.execute(
            text(
                """
                select id, url, allowed_domains, enabled
                from sources
                where id = :source_id
                """
            ),
            {"source_id": source_id},
        ).mappings().first()
        if not current:
            return {}

        next_url = values["url"] if values.get("url") is not None else current["url"]
        next_domains = (
            values["allowed_domains"]
            if values.get("allowed_domains") is not None
            else list(current["allowed_domains"] or [])
        )
        if values.get("url") is not None or values.get("allowed_domains") is not None:
            enabled_pages = session.execute(
                text(
                    """
                    select id, url
                    from source_pages
                    where source_id = :source_id and enabled = true
                    order by id
                    """
                ),
                {"source_id": source_id},
            ).mappings()
            for page in enabled_pages:
                validate_source_page_url(
                    page_url=str(page["url"]),
                    source_url=str(next_url),
                    allowed_domains=next_domains,
                )

        row = session.execute(
            text(
                """
                update sources
                set code = coalesce(:code, code),
                    name = coalesce(:name, name),
                    jurisdiction = coalesce(cast(:jurisdiction as jurisdiction_t), jurisdiction),
                    url = coalesce(:url, url),
                    crawler_type = coalesce(cast(:crawler_type as crawler_t), crawler_type),
                    allowed_domains = coalesce(cast(:allowed_domains as text[]), allowed_domains),
                    hint = coalesce(:hint, hint),
                    enabled = coalesce(:enabled, enabled),
                    updated_at = now()
                where id = :source_id
                returning id, code, name, jurisdiction::text as jurisdiction, url,
                          crawler_type::text as crawler_type, allowed_domains, hint, enabled,
                          last_checked_at, last_status, consecutive_failures
                """
            ),
            values,
        ).mappings().first()
    return dict(row) if row else {}


def delete_source(source_id: int) -> dict[str, Any]:
    with session_scope() as session:
        row = session.execute(
            text("delete from sources where id = :source_id returning id"),
            {"source_id": source_id},
        ).first()
    return {"source_id": source_id, "deleted": bool(row)}


def list_source_pages(source_id: int) -> list[dict[str, Any]]:
    try:
        with session_scope() as session:
            rows = session.execute(
                text(
                    """
                    select id, source_id, name, url, page_type, priority, enabled,
                           last_crawled_at, created_at, updated_at
                    from source_pages
                    where source_id = :source_id
                    order by priority, id
                    """
                ),
                {"source_id": source_id},
            ).mappings()
            return [dict(row) for row in rows]
    except SQLAlchemyError as exc:
        logger.warning("list_source_pages failed: %s", exc)
        return []


def list_enabled_source_pages(
    *,
    source_id: int | None = None,
    page_id: int | None = None,
) -> list[dict[str, Any]]:
    """Return crawlable pages from DB configuration (single source of truth).

    A page is crawlable when ``sources.enabled`` and ``source_pages.enabled`` are
    both true. Domain safety is enforced at Admin create/update time via
    ``source_page_policy``; this function does not apply a second hardcoded URL
    allowlist.
    """

    clauses = ["s.enabled = true", "sp.enabled = true"]
    params: dict[str, Any] = {}
    if source_id is not None:
        clauses.append("s.id = :source_id")
        params["source_id"] = source_id
    if page_id is not None:
        clauses.append("sp.id = :page_id")
        params["page_id"] = page_id
    try:
        with session_scope() as session:
            rows = session.execute(
                text(
                    f"""
                    select
                      sp.id,
                      sp.source_id,
                      sp.name,
                      sp.url,
                      sp.page_type,
                      sp.priority,
                      sp.enabled,
                      sp.last_crawled_at,
                      s.code as source_code,
                      s.name as source_name,
                      s.url as source_url,
                      s.jurisdiction::text as jurisdiction,
                      s.crawler_type::text as crawler_type,
                      s.allowed_domains,
                      s.hint
                    from source_pages sp
                    join sources s on s.id = sp.source_id
                    where {" and ".join(clauses)}
                    order by s.id, sp.priority, sp.id
                    """
                ),
                params,
            ).mappings()
            return [dict(row) for row in rows]
    except SQLAlchemyError as exc:
        logger.warning("list_enabled_source_pages failed: %s", exc)
        return []


def explain_empty_source_page_selection(
    *,
    source_id: int | None = None,
    page_id: int | None = None,
) -> dict[str, Any]:
    """Diagnostics when crawl selection returns zero pages for a scope."""

    configured: list[dict[str, Any]] = []
    enabled: list[dict[str, Any]] = []
    try:
        with session_scope() as session:
            clauses = ["1=1"]
            params: dict[str, Any] = {}
            if source_id is not None:
                clauses.append("s.id = :source_id")
                params["source_id"] = source_id
            if page_id is not None:
                clauses.append("sp.id = :page_id")
                params["page_id"] = page_id
            rows = session.execute(
                text(
                    f"""
                    select
                      sp.id,
                      sp.source_id,
                      sp.url,
                      sp.enabled as page_enabled,
                      s.code as source_code,
                      s.enabled as source_enabled,
                      s.url as source_url,
                      s.allowed_domains
                    from source_pages sp
                    join sources s on s.id = sp.source_id
                    where {" and ".join(clauses)}
                    order by sp.id
                    """
                ),
                params,
            ).mappings()
            configured = [dict(row) for row in rows]
    except SQLAlchemyError as exc:
        logger.warning("explain_empty_source_page_selection failed: %s", exc)
        return diagnose_source_page_selection(
            source_id=source_id,
            page_id=page_id,
            configured_pages=[],
            enabled_pages=[],
            crawlable_pages=[],
        )

    if source_id is not None and not configured and page_id is None:
        # Source may exist with zero pages, or source may be missing.
        try:
            with session_scope() as session:
                source = session.execute(
                    text(
                        """
                        select id, code, enabled, url, allowed_domains
                        from sources
                        where id = :source_id
                        """
                    ),
                    {"source_id": source_id},
                ).mappings().first()
            if source:
                configured = [
                    {
                        "source_id": source["id"],
                        "source_code": source["code"],
                        "source_enabled": source["enabled"],
                        "source_url": source["url"],
                        "allowed_domains": source["allowed_domains"],
                        "page_enabled": False,
                    }
                ]
                # Fake zero pages: configured_pages length should reflect pages.
                # Use empty configured for page count but preserve source metadata.
                diagnosis = diagnose_source_page_selection(
                    source_id=source_id,
                    page_id=page_id,
                    configured_pages=[],
                    enabled_pages=[],
                    crawlable_pages=[],
                )
                diagnosis["source"] = source["code"]
                diagnosis["source_enabled"] = bool(source["enabled"])
                if not source["enabled"]:
                    diagnosis["reason"] = "source_disabled"
                else:
                    diagnosis["reason"] = "no_source_pages_configured"
                return diagnosis
        except SQLAlchemyError as exc:
            logger.warning("explain_empty_source_page_selection source lookup failed: %s", exc)

    enabled = [
        row
        for row in configured
        if row.get("page_enabled") and row.get("source_enabled")
    ]
    crawlable = [
        row
        for row in enabled
        if page_url_permitted_for_source(
            page_url=str(row["url"]),
            source_url=str(row["source_url"]),
            allowed_domains=row.get("allowed_domains") or [],
        )
    ]
    # For diagnose counts, configured = all joined page rows (not the synthetic).
    page_rows = [row for row in configured if row.get("id") is not None]
    diagnosis = diagnose_source_page_selection(
        source_id=source_id,
        page_id=page_id,
        configured_pages=page_rows,
        enabled_pages=enabled,
        crawlable_pages=crawlable if crawlable else [],
    )
    # Prefer crawl selection truth: if enabled pages exist they are crawlable under
    # the new policy (domain was write-time). If somehow domain-invalid, say so.
    if enabled and not crawlable:
        diagnosis["reason"] = "invalid_source_domain_configuration"
        diagnosis["crawlable_pages"] = 0
    elif enabled:
        diagnosis["crawlable_pages"] = len(enabled)
        diagnosis["reason"] = None
    if page_rows:
        diagnosis["source"] = page_rows[0].get("source_code")
        diagnosis["source_enabled"] = page_rows[0].get("source_enabled")
    return diagnosis


def get_source_page(page_id: int) -> dict[str, Any] | None:
    pages = list_enabled_source_pages(page_id=page_id)
    return pages[0] if pages else None


def create_source_page(source_id: int, payload: SourcePagePayload) -> dict[str, Any]:
    values = payload.model_dump()
    values["source_id"] = source_id
    with session_scope() as session:
        source = session.execute(
            text(
                """
                select id, url, allowed_domains
                from sources
                where id = :source_id
                """
            ),
            {"source_id": source_id},
        ).mappings().first()
        if not source:
            raise SourcePagePolicyError(f"source_id {source_id} not found")
        values["url"] = validate_source_page_url(
            page_url=str(values["url"]),
            source_url=str(source["url"]),
            allowed_domains=list(source["allowed_domains"] or []),
        )
        row = session.execute(
            text(
                """
                insert into source_pages (source_id, name, url, page_type, priority, enabled)
                values (:source_id, :name, :url, :page_type, :priority, :enabled)
                returning id, source_id, name, url, page_type, priority, enabled,
                          last_crawled_at, created_at, updated_at
                """
            ),
            values,
        ).mappings().first()
    return dict(row) if row else {}


def update_source_page(page_id: int, payload: SourcePageUpdatePayload) -> dict[str, Any]:
    values = payload.model_dump()
    values["page_id"] = page_id
    with session_scope() as session:
        current = session.execute(
            text(
                """
                select
                  sp.id,
                  sp.source_id,
                  sp.url,
                  sp.enabled,
                  s.url as source_url,
                  s.allowed_domains
                from source_pages sp
                join sources s on s.id = sp.source_id
                where sp.id = :page_id
                """
            ),
            {"page_id": page_id},
        ).mappings().first()
        if not current:
            return {}

        next_url = values["url"] if values.get("url") is not None else current["url"]
        next_enabled = (
            values["enabled"] if values.get("enabled") is not None else current["enabled"]
        )
        if values.get("url") is not None or bool(next_enabled):
            canonical = validate_source_page_url(
                page_url=str(next_url),
                source_url=str(current["source_url"]),
                allowed_domains=list(current["allowed_domains"] or []),
            )
            if values.get("url") is not None:
                values["url"] = canonical

        row = session.execute(
            text(
                """
                update source_pages
                set name = coalesce(:name, name),
                    url = coalesce(:url, url),
                    page_type = coalesce(:page_type, page_type),
                    priority = coalesce(:priority, priority),
                    enabled = coalesce(:enabled, enabled),
                    updated_at = now()
                where id = :page_id
                returning id, source_id, name, url, page_type, priority, enabled,
                          last_crawled_at, created_at, updated_at
                """
            ),
            values,
        ).mappings().first()
    return dict(row) if row else {}


def delete_source_page(page_id: int) -> dict[str, Any]:
    with session_scope() as session:
        row = session.execute(
            text("delete from source_pages where id = :page_id returning id, source_id"),
            {"page_id": page_id},
        ).first()
    return {
        "page_id": page_id,
        "source_id": int(row.source_id) if row else None,
        "deleted": bool(row),
    }


def mark_source_page_crawled(page_id: int) -> None:
    try:
        with session_scope() as session:
            session.execute(
                text(
                    """
                    update source_pages
                    set last_crawled_at = now(), updated_at = now()
                    where id = :page_id
                    """
                ),
                {"page_id": page_id},
            )
    except SQLAlchemyError:
        return


def load_checkpoint(page_id: int) -> dict[str, Any] | None:
    try:
        with session_scope() as session:
            row = session.execute(
                text(
                    """
                    select
                      source_page_id,
                      checkpoint_key,
                      checkpoint_url,
                      checkpoint_title,
                      checkpoint_issue_date,
                      checkpoint_published_at,
                      checkpoint_source_record_id,
                      checkpoint_content_hash,
                      checkpoint_payload,
                      lookback_count,
                      last_successful_run_id,
                      last_successful_at,
                      updated_at
                    from source_page_checkpoints
                    where source_page_id = :page_id
                    """
                ),
                {"page_id": page_id},
            ).mappings().first()
            return dict(row) if row else None
    except SQLAlchemyError as exc:
        logger.warning("load_checkpoint(%s) failed: %s", page_id, exc)
        return None


def save_checkpoint(
    page_id: int,
    candidate: DiscoveredDoc,
    *,
    run_id: int | None = None,
) -> None:
    if not candidate.candidate_key:
        return
    payload = {
        "source_code": candidate.source_code,
        "issue_date_precision": candidate.issue_date_precision,
        "doc_type": candidate.doc_type,
    }
    try:
        with session_scope() as session:
            session.execute(
                text(
                    """
                    insert into source_page_checkpoints
                      (source_page_id, checkpoint_key, checkpoint_url, checkpoint_title,
                       checkpoint_issue_date, checkpoint_published_at,
                       checkpoint_source_record_id, checkpoint_payload,
                       last_successful_run_id, last_successful_at)
                    values
                      (:source_page_id, :checkpoint_key, :checkpoint_url,
                       :checkpoint_title, :checkpoint_issue_date,
                       :checkpoint_published_at, :checkpoint_source_record_id,
                       cast(:checkpoint_payload as jsonb), :run_id, now())
                    on conflict (source_page_id) do update set
                      checkpoint_key = excluded.checkpoint_key,
                      checkpoint_url = excluded.checkpoint_url,
                      checkpoint_title = excluded.checkpoint_title,
                      checkpoint_issue_date = excluded.checkpoint_issue_date,
                      checkpoint_published_at = excluded.checkpoint_published_at,
                      checkpoint_source_record_id = excluded.checkpoint_source_record_id,
                      checkpoint_payload = excluded.checkpoint_payload,
                      last_successful_run_id = excluded.last_successful_run_id,
                      last_successful_at = now(),
                      updated_at = now()
                    """
                ),
                {
                    "source_page_id": page_id,
                    "checkpoint_key": candidate.candidate_key,
                    "checkpoint_url": canonical_url(candidate.source_url),
                    "checkpoint_title": candidate.title,
                    "checkpoint_issue_date": candidate.issue_date,
                    "checkpoint_published_at": candidate.published_at,
                    "checkpoint_source_record_id": candidate.source_record_id,
                    "checkpoint_payload": json.dumps(payload),
                    "run_id": run_id,
                },
            )
    except SQLAlchemyError as exc:
        logger.warning("save_checkpoint(%s) failed: %s", page_id, exc)


def record_source_check(source_code: str, *, status: int | None, ok: bool) -> None:
    try:
        with session_scope() as session:
            session.execute(
                text(
                    """
                    update sources
                    set last_checked_at = now(),
                        last_status = :status,
                        consecutive_failures = case
                          when :ok then 0 else consecutive_failures + 1
                        end,
                        updated_at = now()
                    where code = :source_code
                    """
                ),
                {"source_code": source_code, "status": status, "ok": ok},
            )
    except SQLAlchemyError:
        return


def toggle_source(source_id: int) -> dict[str, Any]:
    with session_scope() as session:
        row = session.execute(
            text(
                """
                update sources
                set enabled = not enabled, updated_at = now()
                where id = :source_id
                returning id, enabled
                """
            ),
            {"source_id": source_id},
        ).first()
    return {"source_id": source_id, "enabled": bool(row.enabled) if row else False}


_CRAWL_RUN_SELECT = """
select
  cr.id,
  cr.started_at,
  cr.finished_at,
  cr.status::text as status,
  cr.sources_attempted,
  cr.sources_succeeded,
  cr.docs_found,
  cr.new_events,
  cr.errors,
  coalesce(audit.audit_candidates, 0) as audit_candidates,
  coalesce(audit.audit_accepted, 0) as audit_accepted,
  coalesce(audit.audit_with_content, 0) as audit_with_content,
  coalesce(audit.audit_pages, 0) as audit_pages,
  coalesce(pages.pages_attempted, 0) as derived_pages_attempted,
  linked.documents_persisted,
  linked.versions_created,
  linked.families_touched,
  linked.graph_extractions,
  linked.entities_extracted,
  linked.obligations_extracted,
  linked.stakeholders_extracted,
  linked.events_linked,
  linked.rag_jobs_enqueued,
  linked.rag_jobs_completed,
  linked.rag_jobs_failed,
  linked.rag_ready_documents,
  linked.chunks_indexed
from crawl_runs cr
left join lateral (
  select
    count(*)::int as audit_candidates,
    count(*) filter (where da.is_valid_event_source)::int as audit_accepted,
    count(*) filter (where da.content_hash is not null)::int as audit_with_content,
    count(
      distinct nullif(da.metadata->>'source_page_id', '')
    )::int as audit_pages
  from discovery_audit da
  where da.run_id = cr.id
) audit on true
left join lateral (
  select count(distinct page_id)::int as pages_attempted
  from (
    select nullif(da.metadata->>'source_page_id', '') as page_id
    from discovery_audit da
    where da.run_id = cr.id
    union
    select nullif(err.item->>'source_page_id', '') as page_id
    from jsonb_array_elements(coalesce(cr.errors, '[]'::jsonb)) as err(item)
  ) page_ids
  where page_id is not null
) pages on true
left join lateral (
  select
    count(distinct dv.document_id)::int as documents_persisted,
    count(distinct dv.id)::int as versions_created,
    count(distinct a.family_id)::int as families_touched,
    count(distinct g.document_id) filter (
      where g.status = 'COMPLETED'
    )::int as graph_extractions,
    count(distinct gde.entity_id)::int as entities_extracted,
    count(distinct go.obligation_id)::int as obligations_extracted,
    count(distinct gs.stakeholder_id)::int as stakeholders_extracted,
    count(distinct e.id)::int as events_linked,
    count(distinct rj.job_id)::int as rag_jobs_enqueued,
    count(distinct rj.job_id) filter (
      where rj.status = 'COMPLETED'
    )::int as rag_jobs_completed,
    count(distinct rj.job_id) filter (
      where rj.status = 'FAILED'
    )::int as rag_jobs_failed,
    count(distinct drs.document_id) filter (
      where drs.status = 'RAG_READY'
    )::int as rag_ready_documents,
    coalesce(sum(drs.chunk_count) filter (
      where drs.status = 'RAG_READY'
    ), 0)::int as chunks_indexed
  from discovery_audit da
  join document_versions dv on dv.content_hash = da.content_hash
  left join document_family_assignments a on a.document_id = dv.document_id
  left join regulatory_graph_extractions g on g.document_id = dv.document_id
  left join regulatory_graph_document_entities gde
    on gde.document_id = dv.document_id
  left join regulatory_graph_obligations go on go.document_id = dv.document_id
  left join regulatory_graph_stakeholders gs on gs.document_id = dv.document_id
  left join events e on e.document_id = dv.document_id
  left join rag_index_jobs rj on rj.document_id = dv.document_id
  left join document_rag_status drs on drs.document_id = dv.document_id
  where da.run_id = cr.id
    and da.content_hash is not null
) linked on true
"""


def list_crawl_runs(limit: int = 25) -> list[dict[str, Any]]:
    try:
        with session_scope() as session:
            rows = session.execute(
                text(
                    f"""
                    {_CRAWL_RUN_SELECT}
                    order by cr.started_at desc
                    limit :limit
                    """
                ),
                {"limit": limit},
            ).mappings()
            return [assemble_crawl_run_telemetry(dict(row)) for row in rows]
    except SQLAlchemyError:
        return []


def get_crawl_run(run_id: int) -> dict[str, Any] | None:
    try:
        with session_scope() as session:
            row = session.execute(
                text(
                    f"""
                    {_CRAWL_RUN_SELECT}
                    where cr.id = :run_id
                    """
                ),
                {"run_id": run_id},
            ).mappings().first()
            return assemble_crawl_run_telemetry(dict(row)) if row else None
    except SQLAlchemyError:
        return None


def page_ids_from_crawl_errors(errors: Any) -> set[int]:
    """Extract source_page_id values recorded on crawl_runs.errors JSON."""

    page_ids: set[int] = set()
    if not isinstance(errors, list):
        return page_ids
    for item in errors:
        if not isinstance(item, dict):
            continue
        raw = item.get("source_page_id")
        if raw is None:
            continue
        try:
            page_ids.add(int(raw))
        except (TypeError, ValueError):
            continue
    return page_ids


def assemble_crawl_run_telemetry(row: dict[str, Any]) -> dict[str, Any]:
    """Build an explicitly run-scoped crawl-run read model.

    Unavailable metrics are returned as null so clients can distinguish them
    from genuine zeros. Never substitutes global database totals.
    """

    errors = row.get("errors") or []
    if isinstance(errors, str):
        try:
            errors = json.loads(errors)
        except json.JSONDecodeError:
            errors = []
    if not isinstance(errors, list):
        errors = []

    docs_found = int(row.get("docs_found") or 0)
    new_events = int(row.get("new_events") or 0)
    audit_pages = int(row.get("audit_pages") or 0)
    audit_with_content = int(row.get("audit_with_content") or 0)
    audit_candidates = int(row.get("audit_candidates") or 0)
    if "derived_pages_attempted" in row:
        pages_attempted = int(row.get("derived_pages_attempted") or 0)
    else:
        # Unit-test path without SQL lateral aggregates.
        audit_ids = {
            int(value)
            for value in (row.get("audit_page_ids") or [])
            if value is not None
        }
        pages_attempted = len(audit_ids | page_ids_from_crawl_errors(errors))
        if not audit_ids and not page_ids_from_crawl_errors(errors):
            pages_attempted = audit_pages

    sources_attempted = int(row.get("sources_attempted") or 0)
    if pages_attempted == 0 and sources_attempted > 0:
        pages_attempted_value: int | None = None
        pages_succeeded_value: int | None = None
    else:
        pages_attempted_value = pages_attempted
        pages_succeeded_value = audit_pages

    # Prefer authoritative discovery_audit / linked-document counts when the
    # crawl_runs counters were never finalized (abandoned running rows).
    documents_discovered = max(docs_found, audit_candidates)
    events_linked = row.get("events_linked")
    events_created = max(
        new_events,
        int(events_linked) if events_linked is not None else 0,
    )

    def _linked_int(key: str) -> int | None:
        if key not in row:
            # Unit-test fixtures without linked lateral → unavailable.
            return None
        value = row.get(key)
        return int(value or 0)

    return {
        "id": row["id"],
        "started_at": row.get("started_at"),
        "finished_at": row.get("finished_at"),
        "status": row.get("status"),
        "sources_attempted": sources_attempted,
        "sources_succeeded": int(row.get("sources_succeeded") or 0),
        # Legacy field names retained for compatibility; values are run-scoped.
        "docs_found": documents_discovered,
        "new_events": events_created,
        "errors": errors,
        # Explicit run-scoped metrics for admin run cards.
        "pages_attempted": pages_attempted_value,
        "pages_succeeded": pages_succeeded_value,
        "documents_discovered": documents_discovered,
        "documents_with_content": audit_with_content,
        "documents_persisted": _linked_int("documents_persisted"),
        "events_created": events_created,
        "versions_created": _linked_int("versions_created"),
        "families_touched": _linked_int("families_touched"),
        "graph_extractions": _linked_int("graph_extractions"),
        "entities_extracted": _linked_int("entities_extracted"),
        "obligations_extracted": _linked_int("obligations_extracted"),
        "stakeholders_extracted": _linked_int("stakeholders_extracted"),
        "rag_jobs_enqueued": _linked_int("rag_jobs_enqueued"),
        "rag_jobs_completed": _linked_int("rag_jobs_completed"),
        "rag_jobs_failed": _linked_int("rag_jobs_failed"),
        "rag_ready_documents": _linked_int("rag_ready_documents"),
        "chunks_indexed": _linked_int("chunks_indexed"),
        "rag_indexed": _linked_int("rag_ready_documents"),
    }


def get_source_analytics(source_id: int) -> dict[str, Any]:
    try:
        with session_scope() as session:
            source = session.execute(
                text(
                    """
                    select id, code, name, jurisdiction::text as jurisdiction, url,
                           crawler_type::text as crawler_type, allowed_domains, hint, enabled,
                           last_checked_at, last_status, consecutive_failures
                    from sources
                    where id = :source_id
                    """
                ),
                {"source_id": source_id},
            ).mappings().first()
            if not source:
                return {}
            source_dict = dict(source)
            counts = session.execute(
                text(
                    """
                    select
                      (select count(*)
                       from source_pages
                       where source_id = :source_id) as pages_total,
                      (select count(*) from source_pages
                       where source_id = :source_id and enabled = true) as pages_enabled,
                      (select count(*)
                       from documents
                       where source_id = :source_id) as documents_total,
                      (select count(*)
                       from events e
                       join documents d on d.id = e.document_id
                       where d.source_id = :source_id) as events_total,
                      (select count(*) from discovery_audit
                       where source_code = :source_code) as discovery_candidates,
                      (select count(*) from discovery_audit
                       where source_code = :source_code and is_valid_event_source = true)
                       as discovery_accepted,
                      (select count(*) from discovery_audit
                       where source_code = :source_code and is_valid_event_source = false)
                       as discovery_rejected
                    """
                ),
                {"source_id": source_id, "source_code": source_dict["code"]},
            ).mappings().first()
            reason_rows = list(session.execute(
                text(
                    """
                    select reason_code, count(*) as count
                    from discovery_audit
                    where source_code = :source_code
                    group by reason_code
                    order by count desc, reason_code
                    """
                ),
                {"source_code": source_dict["code"]},
            ).mappings())
            classification_rows = list(session.execute(
                text(
                    """
                    select classification, count(*) as count
                    from discovery_audit
                    where source_code = :source_code
                    group by classification
                    order by count desc, classification
                    """
                ),
                {"source_code": source_dict["code"]},
            ).mappings())
            latest_run = session.execute(
                text(
                    """
                    select cr.id, cr.started_at, cr.finished_at, cr.status::text as status,
                           cr.sources_attempted, cr.sources_succeeded, cr.docs_found,
                           cr.new_events, cr.errors
                    from crawl_runs cr
                    join discovery_audit da on da.run_id = cr.id
                    where da.source_code = :source_code
                    order by cr.started_at desc
                    limit 1
                    """
                ),
                {"source_code": source_dict["code"]},
            ).mappings().first()
        count_dict = dict(counts) if counts else {}
        return {
            "source": source_dict,
            "pages_total": int(count_dict.get("pages_total") or 0),
            "pages_enabled": int(count_dict.get("pages_enabled") or 0),
            "documents_total": int(count_dict.get("documents_total") or 0),
            "events_total": int(count_dict.get("events_total") or 0),
            "discovery_candidates": int(count_dict.get("discovery_candidates") or 0),
            "discovery_accepted": int(count_dict.get("discovery_accepted") or 0),
            "discovery_rejected": int(count_dict.get("discovery_rejected") or 0),
            "rejection_reasons": {
                str(row["reason_code"]): int(row["count"]) for row in reason_rows
            },
            "classifications": {
                str(row["classification"]): int(row["count"]) for row in classification_rows
            },
            "latest_run": dict(latest_run) if latest_run else None,
        }
    except SQLAlchemyError as exc:
        logger.warning("get_source_analytics(%s) failed: %s", source_id, exc)
        return {}


def list_all_source_pages() -> list[dict[str, Any]]:
    try:
        with session_scope() as session:
            rows = session.execute(
                text(
                    """
                    select sp.id, sp.source_id, s.code as source_code, s.name as source_name,
                           sp.name, sp.url, sp.page_type, sp.priority, sp.enabled,
                           sp.last_crawled_at, sp.created_at, sp.updated_at
                    from source_pages sp
                    join sources s on s.id = sp.source_id
                    order by s.code, sp.priority, sp.id
                    """
                )
            ).mappings()
            return [dict(row) for row in rows]
    except SQLAlchemyError as exc:
        logger.warning("list_all_source_pages failed: %s", exc)
        return []


def list_source_page_checkpoints() -> list[dict[str, Any]]:
    try:
        with session_scope() as session:
            rows = session.execute(
                text(
                    """
                    select sp.id as source_page_id, s.code as source_code,
                           s.name as source_name, sp.name as source_page,
                           sp.url as source_page_url, c.checkpoint_title,
                           c.checkpoint_url, c.checkpoint_source_record_id,
                           c.checkpoint_issue_date, c.checkpoint_published_at,
                           c.lookback_count, c.last_successful_run_id,
                           c.last_successful_at, c.updated_at
                    from source_pages sp
                    join sources s on s.id = sp.source_id
                    left join source_page_checkpoints c on c.source_page_id = sp.id
                    order by s.code, sp.priority, sp.id
                    """
                )
            ).mappings()
            return [dict(row) for row in rows]
    except SQLAlchemyError as exc:
        logger.warning("list_source_page_checkpoints failed: %s", exc)
        return []


def list_admin_documents(limit: int = 100) -> list[dict[str, Any]]:
    try:
        with session_scope() as session:
            rows = session.execute(
                text(
                    """
                    select d.id, d.title, d.source_url, d.issuing_body,
                           d.jurisdiction::text as jurisdiction, d.issue_date,
                           d.issue_date_precision::text as issue_date_precision,
                           d.doc_type, d.first_seen_at, d.last_seen_at,
                           s.code as source_code, s.name as source_name,
                           dv.id as latest_version_id, dv.file_hash, dv.content_hash,
                           dv.fetched_at,
                           a.family_id, f.canonical_title as family_title
                    from documents d
                    left join sources s on s.id = d.source_id
                    left join lateral (
                      select *
                      from document_versions
                      where document_id = d.id
                      order by fetched_at desc
                      limit 1
                    ) dv on true
                    left join document_family_assignments a on a.document_id = d.id
                    left join document_families f on f.family_id = a.family_id
                    order by d.last_seen_at desc
                    limit :limit
                    """
                ),
                {"limit": limit},
            ).mappings()
            return [dict(row) for row in rows]
    except SQLAlchemyError as exc:
        logger.warning("list_admin_documents failed: %s", exc)
        return []


def list_admin_events(limit: int = 100) -> list[dict[str, Any]]:
    try:
        with session_scope() as session:
            rows = session.execute(
                text(
                    """
                    select e.id, e.event_type::text as event_type, e.detected_at,
                           e.suppressed, e.raw_summary, e.topic_tags,
                           d.id as document_id, d.title, d.source_url,
                           d.issuing_body, d.issue_date,
                           s.code as source_code,
                           eia.quality_score, eia.quality_category,
                           eia.significance_score, eia.significance_category,
                           eia.actionability, eia.rejection_reason
                    from events e
                    join documents d on d.id = e.document_id
                    left join sources s on s.id = d.source_id
                    left join event_intelligence_audit eia on eia.event_id = e.id
                    order by e.detected_at desc
                    limit :limit
                    """
                ),
                {"limit": limit},
            ).mappings()
            return [dict(row) for row in rows]
    except SQLAlchemyError as exc:
        logger.warning("list_admin_events failed: %s", exc)
        return []


def list_admin_families(limit: int = 100) -> list[dict[str, Any]]:
    try:
        with session_scope() as session:
            rows = session.execute(
                text(
                    """
                    select f.family_id, f.canonical_title, f.issuer, f.document_type,
                           f.first_seen_at, f.latest_version_id, f.created_at, f.updated_at,
                           count(distinct a.document_id) as document_count,
                           count(distinct v.registry_version_id) as version_count,
                           count(distinct dh.id) as deadline_count
                    from document_families f
                    left join document_family_assignments a on a.family_id = f.family_id
                    left join document_version_registry v on v.family_id = f.family_id
                    left join deadline_history dh on dh.family_id = f.family_id
                    group by f.family_id
                    order by f.updated_at desc
                    limit :limit
                    """
                ),
                {"limit": limit},
            ).mappings()
            return [dict(row) for row in rows]
    except SQLAlchemyError as exc:
        logger.warning("list_admin_families failed: %s", exc)
        return []


def get_admin_analytics() -> dict[str, Any]:
    try:
        with session_scope() as session:
            counts = session.execute(
                text(
                    """
                    select
                      (select count(*) from sources) as sources,
                      (select count(*) from source_pages) as pages,
                      (select count(*) from events) as events,
                      (select count(*) from documents) as documents,
                      (select count(*) from document_families) as families,
                      (select count(*) from source_page_checkpoints) as checkpoints,
                      (select count(*) from discovery_audit) as candidates,
                      (select count(*) from discovery_audit where is_valid_event_source)
                        as accepted_candidates,
                      (select count(*) from discovery_audit where not is_valid_event_source)
                        as rejected_candidates
                    """
                )
            ).mappings().first()
            latest_runs = list(
                session.execute(
                    text(
                        """
                        select id, started_at, finished_at, status::text as status,
                               docs_found, new_events, errors,
                               extract(epoch from (finished_at - started_at)) as runtime_seconds,
                               (
                                 select count(*)
                                 from discovery_audit da
                                 where da.run_id = crawl_runs.id
                                   and da.content_hash is not null
                               ) as downloads
                        from crawl_runs
                        order by id desc
                        limit 5
                        """
                    )
                ).mappings()
            )
            rejection_rows = list(
                session.execute(
                    text(
                        """
                        select reason_code, count(*) as count
                        from discovery_audit
                        where not is_valid_event_source
                        group by reason_code
                        order by count desc, reason_code
                        limit 10
                        """
                    )
                ).mappings()
            )
        latest = [dict(row) for row in latest_runs]
        runtime_reduction = None
        download_reduction = None
        if len(latest) >= 2:
            newer = latest[0]
            older = latest[1]
            old_runtime = float(older.get("runtime_seconds") or 0)
            new_runtime = float(newer.get("runtime_seconds") or 0)
            old_downloads = int(older.get("downloads") or 0)
            new_downloads = int(newer.get("downloads") or 0)
            if old_runtime:
                runtime_reduction = round((old_runtime - new_runtime) / old_runtime * 100, 1)
            if old_downloads:
                download_reduction = round((old_downloads - new_downloads) / old_downloads * 100, 1)
        count_dict = dict(counts) if counts else {}
        candidates = int(count_dict.get("candidates") or 0)
        accepted = int(count_dict.get("accepted_candidates") or 0)
        return {
            **count_dict,
            "acceptance_rate": round(accepted / candidates * 100, 1) if candidates else 0,
            "runtime_reduction": runtime_reduction,
            "download_reduction": download_reduction,
            "latest_runs": latest,
            "rejected_reasons": [dict(row) for row in rejection_rows],
        }
    except SQLAlchemyError as exc:
        logger.warning("get_admin_analytics failed: %s", exc)
        return {}


def create_crawl_run() -> int | None:
    """Insert a crawl_runs row in queued status. One trigger must create one run."""

    try:
        with session_scope() as session:
            row = session.execute(
                text(
                    """
                    insert into crawl_runs (status)
                    values (cast('queued' as run_status_t))
                    returning id
                    """
                )
            ).first()
            return int(row.id) if row else None
    except SQLAlchemyError:
        return None


def mark_crawl_run_running(run_id: int) -> None:
    """Transition a queued crawl run to running (CLI / non-claim path).

    Prefer ``claim_queued_crawl_run`` for workers: it uses FOR UPDATE SKIP LOCKED
    so concurrent workers cannot both own the same queued row.
    """

    claim_queued_crawl_run(run_id)


def claim_queued_crawl_run(run_id: int) -> bool:
    """Atomically claim one queued crawl_run (queued → running).

    Returns True if this caller won the claim. Uses FOR UPDATE SKIP LOCKED so a
    second concurrent claimer gets False without blocking.
    """

    with session_scope() as session:
        row = session.execute(
            text(
                """
                update crawl_runs
                set status = cast('running' as run_status_t),
                    started_at = now(),
                    finished_at = null
                where id = (
                  select id
                  from crawl_runs
                  where id = cast(:run_id as bigint)
                    and status = cast('queued' as run_status_t)
                  for update skip locked
                )
                returning id
                """
            ),
            {"run_id": run_id},
        ).first()
        return row is not None


def finalize_crawl_run(
    run_id: int | None,
    *,
    status: str,
    sources_attempted: int,
    sources_succeeded: int,
    docs_found: int,
    new_events: int,
    errors: list[dict[str, Any]],
) -> None:
    if run_id is None:
        return
    with session_scope() as session:
        session.execute(
            text(
                """
                update crawl_runs
                set finished_at = now(),
                    status = cast(:status as run_status_t),
                    sources_attempted = :sources_attempted,
                    sources_succeeded = :sources_succeeded,
                    docs_found = :docs_found,
                    new_events = :new_events,
                    errors = cast(:errors as jsonb)
                where id = :run_id
                """
            ),
            {
                "run_id": run_id,
                "status": status,
                "sources_attempted": sources_attempted,
                "sources_succeeded": sources_succeeded,
                "docs_found": docs_found,
                "new_events": new_events,
                "errors": json.dumps(errors),
            },
        )
    log_event(
        "crawl_finalized",
        run_id=run_id,
        status=status,
        sources_attempted=sources_attempted,
        sources_succeeded=sources_succeeded,
        docs_found=docs_found,
        new_events=new_events,
        error_count=len(errors),
    )


def record_discovery_audits(run_id: int | None, audits: list[DiscoveryAuditRecord]) -> None:
    if not audits:
        return
    try:
        with session_scope() as session:
            for audit in audits:
                payload = audit.model_dump(mode="json")
                session.execute(
                    text(
                        """
                        insert into discovery_audit
                          (run_id, source_code, source_url, title, classification,
                           is_valid_event_source, confidence, reason_code, primary_url,
                           content_length, content_hash, metadata)
                        values
                          (:run_id, :source_code, :source_url, :title, :classification,
                           :is_valid_event_source, :confidence, :reason_code, :primary_url,
                           :content_length, :content_hash, cast(:metadata as jsonb))
                        """
                    ),
                    {
                        **payload,
                        "run_id": run_id,
                        "metadata": json.dumps(payload.get("metadata") or {}),
                    },
                )
    except SQLAlchemyError as exc:
        logger.warning("record_discovery_audits failed: %s", exc)


def persist_discovered_documents(discovered_docs: list[Any]) -> list[int]:
    """Legacy path intentionally disabled.

    Step 13 requires events to be generated only from extracted primary content.
    Use persist_extracted_documents instead.
    """

    if discovered_docs:
        logger.warning("Blocked legacy discovered-document event insertion for %s candidates",
                       len(discovered_docs))
    return []


def persist_extracted_documents(extracted_docs: list[ExtractedDoc]) -> list[int]:
    event_ids: list[int] = []
    for extracted in extracted_docs:
        event_id = _persist_extracted_document(extracted)
        if event_id:
            event_ids.append(event_id)
    return event_ids


def record_event_intelligence_audit(
    *,
    event_id: int | None,
    document_id: int | None,
    version_id: int | None,
    source_url: str,
    content_hash: str | None,
    title: str | None,
    intelligence: EventIntelligence,
) -> None:
    try:
        with session_scope() as session:
            _record_event_intelligence_audit(
                session,
                event_id=event_id,
                document_id=document_id,
                version_id=version_id,
                source_url=source_url,
                content_hash=content_hash,
                title=title,
                intelligence=intelligence,
            )
    except SQLAlchemyError as exc:
        logger.warning("record_event_intelligence_audit failed: %s", exc)


def record_regulatory_change_audit(
    *,
    event_id: int | None,
    document_id: int | None,
    version_id: int | None,
    source_url: str,
    content_hash: str | None,
    title: str | None,
    change: RegulatoryChange,
) -> None:
    try:
        with session_scope() as session:
            _record_regulatory_change_audit(
                session,
                event_id=event_id,
                document_id=document_id,
                version_id=version_id,
                source_url=source_url,
                content_hash=content_hash,
                title=title,
                change=change,
            )
    except SQLAlchemyError as exc:
        logger.warning("record_regulatory_change_audit failed: %s", exc)


def create_digest_for_events(run_date: date, event_ids: list[int]) -> DigestResponse:
    try:
        with session_scope() as session:
            digest = session.execute(
                text(
                    """
                    insert into digests (digest_date, event_count)
                    values (:digest_date, 0)
                    on conflict (digest_date) do update set digest_date = excluded.digest_date
                    returning id
                    """
                ),
                {"digest_date": run_date},
            ).first()
            digest_id = digest.id
            for event_id in event_ids:
                session.execute(
                    text(
                        """
                        insert into digest_events (digest_id, event_id)
                        values (:digest_id, :event_id)
                        on conflict do nothing
                        """
                    ),
                    {"digest_id": digest_id, "event_id": event_id},
                )
            session.execute(
                text(
                    """
                    update digests d
                    set event_count = (
                      select count(*)
                      from digest_events de
                      join events e on e.id = de.event_id
                      where de.digest_id = d.id and e.suppressed = false
                    )
                    where d.id = :digest_id
                    """
                ),
                {"digest_id": digest_id},
            )
    except SQLAlchemyError as exc:
        logger.warning("create_digest_for_events failed: %s", exc)
        return DigestResponse(digest_date=run_date, event_count=0, events=[])
    return latest_digest(user_id=None)


def _persist_extracted_document(extracted: ExtractedDoc) -> int | None:
    """Persist one document durably, then run downstream intelligence in a new session.

    Session A commits documents/texts/versions/family before any LLM/graph/RAG work.
    Session B failures cannot roll back Session A.
    """

    discovered = extracted.fetched.discovered
    topics = _topic_tags(f"{discovered.title}\n{extracted.text}")
    summary = _summary_from_extracted(extracted)
    intelligence = assess_event_intelligence(extracted, topics=topics, summary=summary)
    summary = attach_intelligence_to_summary(summary, intelligence)

    durable = _persist_document_durable(
        extracted,
        topics=topics,
        summary=summary,
        intelligence=intelligence,
    )
    if durable is None:
        return None

    try:
        return _process_document_downstream(durable)
    except Exception as exc:
        # Document/version/family already committed in Session A.
        logger.warning(
            "downstream intelligence failed after durable persist for %s "
            "(document_id=%s version_id=%s): %s: %s",
            durable.url,
            durable.document_id,
            durable.version_id,
            type(exc).__name__,
            exc,
        )
        log_event(
            "document_downstream_failed",
            document_id=durable.document_id,
            document_version_id=durable.version_id,
            error=f"{type(exc).__name__}: {exc}",
        )
        return None


@dataclass(frozen=True)
class _DurableDocumentState:
    """Committed document/version/family state used by post-commit downstream work."""

    extracted: ExtractedDoc
    url: str
    content_hash: str
    document_id: int
    version_id: int | None
    source_id: int | None
    prior_reference: PriorVersionReference | None
    family_id: int | None
    assignment_type: str | None
    had_prior_document: bool
    create_events: bool
    topics: list[str]
    summary: SummaryPayload
    intelligence: EventIntelligence


def _persist_document_durable(
    extracted: ExtractedDoc,
    *,
    topics: list[str],
    summary: SummaryPayload,
    intelligence: EventIntelligence,
) -> _DurableDocumentState | None:
    """Session A: write durable document rows and required family linkage, then commit."""

    discovered = extracted.fetched.discovered
    url = canonical_url(discovered.source_url)
    url_hash = sha256_normalized_text(url)
    content_hash = extracted.content_hash
    file_hash = extracted.fetched.file_hash
    try:
        with session_scope() as session:
            source = session.execute(
                text("select id from sources where code = :source_code"),
                {"source_code": discovered.source_code},
            ).first()
            latest = session.execute(
                text(
                    """
                    select
                      d.id as document_id,
                      d.title,
                      d.source_url,
                      dv.id as version_id,
                      dv.file_hash,
                      dv.content_hash,
                      dt.text_content
                    from document_versions dv
                    join documents d on d.id = dv.document_id
                    left join document_texts dt on dt.content_hash = dv.content_hash
                    where d.url_hash = :url_hash
                    order by dv.fetched_at desc
                    limit 1
                    """
                ),
                {"url_hash": url_hash},
            ).first()
            document = session.execute(
                text(
                    """
                    insert into documents
                      (source_id, url_hash, source_url, title, issuing_body, jurisdiction,
                       issue_date, issue_date_precision, doc_type, last_seen_at)
                    values
                      (:source_id, :url_hash, :source_url, :title, :issuing_body,
                       cast(:jurisdiction as jurisdiction_t), :issue_date,
                       cast(:issue_date_precision as date_precision_t), :doc_type, now())
                    on conflict (url_hash) do update set
                      last_seen_at = now(),
                      title = excluded.title,
                      issuing_body = coalesce(excluded.issuing_body, documents.issuing_body),
                      issue_date = coalesce(excluded.issue_date, documents.issue_date),
                      issue_date_precision = excluded.issue_date_precision,
                      doc_type = coalesce(excluded.doc_type, documents.doc_type)
                    returning id
                    """
                ),
                {
                    "source_id": source.id if source else None,
                    "url_hash": url_hash,
                    "source_url": url,
                    "title": discovered.title,
                    "issuing_body": discovered.issuing_body,
                    "jurisdiction": discovered.jurisdiction,
                    "issue_date": discovered.issue_date,
                    "issue_date_precision": discovered.issue_date_precision,
                    "doc_type": discovered.doc_type,
                },
            ).first()
            prior_reference = _prior_reference_from_row(latest, "same_url") if latest else None
            session.execute(
                text(
                    """
                    insert into document_texts (content_hash, text_content, content_length)
                    values (:content_hash, :text_content, :content_length)
                    on conflict (content_hash) do update set
                      text_content = excluded.text_content,
                      content_length = excluded.content_length
                    """
                ),
                {
                    "content_hash": content_hash,
                    "text_content": extracted.text,
                    "content_length": len(extracted.text),
                },
            )
            version = session.execute(
                text(
                    """
                    insert into document_versions
                      (document_id, file_hash, content_hash, raw_file_path, text_path,
                       page_count, needs_ocr, http_status)
                    values
                      (:document_id, :file_hash, :content_hash, :raw_file_path, :text_path,
                       :page_count, :needs_ocr, :http_status)
                    on conflict (document_id, file_hash) do nothing
                    returning id
                    """
                ),
                {
                    "document_id": document.id,
                    "file_hash": file_hash,
                    "content_hash": content_hash,
                    "raw_file_path": extracted.fetched.raw_file_path,
                    "text_path": extracted.text_path,
                    "page_count": extracted.page_count,
                    "needs_ocr": extracted.needs_ocr,
                    "http_status": extracted.fetched.http_status,
                },
            ).first()

            if not version:
                version_id = latest.version_id if latest else None
                registry_result = _register_family_for_graph_extraction(
                    session,
                    document_id=document.id,
                    version_id=version_id,
                    extracted=extracted,
                    source_url=url,
                )
                create_events = False
            elif latest and latest.content_hash == content_hash:
                version_id = version.id
                registry_result = _register_family_for_graph_extraction(
                    session,
                    document_id=document.id,
                    version_id=version_id,
                    extracted=extracted,
                    source_url=url,
                )
                create_events = False
            else:
                version_id = version.id
                registry_result = register_document_version_family(
                    session,
                    RegistryInput(
                        document_id=document.id,
                        document_version_id=version_id,
                        title=discovered.title,
                        issuer=discovered.issuing_body,
                        source_url=url,
                        document_type=discovered.doc_type,
                        issue_date=discovered.issue_date,
                        content_hash=content_hash,
                        text_content=extracted.text,
                        content_length=len(extracted.text),
                        first_seen_at=None,
                    ),
                )
                create_events = True

            state = _DurableDocumentState(
                extracted=extracted,
                url=url,
                content_hash=content_hash,
                document_id=int(document.id),
                version_id=int(version_id) if version_id is not None else None,
                source_id=int(source.id) if source else None,
                prior_reference=prior_reference,
                family_id=registry_result.family_id,
                assignment_type=registry_result.assignment_type,
                had_prior_document=bool(latest),
                create_events=create_events,
                topics=topics,
                summary=summary,
                intelligence=intelligence,
            )
            log_event(
                "document_durable_persisted",
                document_id=state.document_id,
                document_version_id=state.version_id,
                create_events=state.create_events,
            )
            return state
    except SQLAlchemyError as exc:
        logger.warning(
            "persist_extracted_document failed for %s: %s",
            discovered.source_url,
            exc,
        )
        return None


def _process_document_downstream(state: _DurableDocumentState) -> int | None:
    """Session B: graph/RAG/change/event work after durable document commit."""

    extracted = state.extracted
    discovered = extracted.fetched.discovered
    with session_scope() as session:
        _run_graph_extraction_for_document(
            session,
            document_id=state.document_id,
            version_id=state.version_id,
            extracted=extracted,
            source_url=state.url,
            family_id=state.family_id,
            assignment_type=state.assignment_type,
        )
        _enqueue_rag_indexing_for_document(
            session,
            document_id=state.document_id,
            version_id=state.version_id,
        )

        prior_reference = state.prior_reference
        if state.create_events and state.version_id is not None:
            if not prior_reference:
                prior_reference = _find_family_prior_reference(
                    session,
                    family_id=state.family_id,
                    current_version_id=state.version_id,
                )
            if not prior_reference:
                prior_reference = _find_related_prior_reference(
                    session,
                    extracted=extracted,
                    current_document_id=state.document_id,
                    source_id=state.source_id,
                )

        change = detect_regulatory_change(extracted, prior=prior_reference)
        _record_regulatory_change_audit(
            session,
            event_id=None,
            document_id=state.document_id,
            version_id=state.version_id,
            source_url=state.url,
            content_hash=state.content_hash,
            title=discovered.title,
            change=change,
        )

        if not state.create_events:
            return None
        if not change.is_material or change.change_type == "NO_MATERIAL_CHANGE":
            return None
        if not state.intelligence.event_allowed:
            _record_event_intelligence_audit(
                session,
                event_id=None,
                document_id=state.document_id,
                version_id=state.version_id,
                source_url=state.url,
                content_hash=state.content_hash,
                title=discovered.title,
                intelligence=state.intelligence,
            )
            return None

        summary = attach_change_to_summary(state.summary, change)
        event_type = "CHANGED" if state.had_prior_document else "NEW"
        event = session.execute(
            text(
                """
                insert into events
                  (document_id, version_id, event_type, digest_origin, raw_summary,
                   topic_tags, suppressed)
                values
                  (:document_id, :version_id, cast(:event_type as event_t),
                   :digest_origin, :raw_summary, :topic_tags, false)
                returning id
                """
            ),
            {
                "document_id": state.document_id,
                "version_id": state.version_id,
                "event_type": event_type,
                "digest_origin": discovered.source_code,
                "raw_summary": summary.plain_english_summary,
                "topic_tags": state.topics,
            },
        ).first()
        session.execute(
            text(
                """
                insert into summaries (event_id, model, summary_json, key_points)
                values (:event_id, :model, cast(:summary_json as jsonb), :key_points)
                on conflict (event_id, model) do update set
                  summary_json = excluded.summary_json,
                  key_points = excluded.key_points,
                  created_at = now()
                """
            ),
            {
                "event_id": event.id,
                "model": SUMMARY_MODEL,
                "summary_json": summary.model_dump_json(),
                "key_points": [summary.plain_english_summary],
            },
        )
        _record_regulatory_change_audit(
            session,
            event_id=event.id,
            document_id=state.document_id,
            version_id=state.version_id,
            source_url=state.url,
            content_hash=state.content_hash,
            title=discovered.title,
            change=change,
        )
        _record_event_intelligence_audit(
            session,
            event_id=event.id,
            document_id=state.document_id,
            version_id=state.version_id,
            source_url=state.url,
            content_hash=state.content_hash,
            title=discovered.title,
            intelligence=state.intelligence,
        )
        event_id = int(event.id)
        try:
            from backend.notifications.service import enqueue_notifications_for_event

            enqueue_notifications_for_event(event_id=event_id, session=session)
        except Exception as notify_exc:  # noqa: BLE001 — never roll back event commit path
            logger.warning(
                "notification enqueue failed after event insert event_id=%s: %s: %s",
                event_id,
                type(notify_exc).__name__,
                notify_exc,
            )
            log_event(
                "notification_enqueue_failed",
                event_id=event_id,
                error=f"{type(notify_exc).__name__}: {notify_exc}",
            )
        return event_id



def _register_family_for_graph_extraction(
    session: Any,
    *,
    document_id: int,
    version_id: int | None,
    extracted: ExtractedDoc,
    source_url: str,
) -> RegistryResult:
    discovered = extracted.fetched.discovered
    return register_document_version_family(
        session,
        RegistryInput(
            document_id=document_id,
            document_version_id=version_id,
            title=discovered.title,
            issuer=discovered.issuing_body,
            source_url=source_url,
            document_type=discovered.doc_type,
            issue_date=discovered.issue_date,
            content_hash=extracted.content_hash,
            text_content=extracted.text,
            content_length=len(extracted.text),
            first_seen_at=None,
        ),
    )


def _run_graph_extraction_for_document(
    session: Any,
    *,
    document_id: int,
    version_id: int | None,
    extracted: ExtractedDoc,
    source_url: str,
    family_id: int | None,
    assignment_type: str | None,
) -> None:
    discovered = extracted.fetched.discovered
    item = GraphInput(
        document_id=document_id,
        document_version_id=version_id,
        title=discovered.title,
        issuer=discovered.issuing_body,
        source_url=source_url,
        document_type=discovered.doc_type,
        issue_date=discovered.issue_date,
        content_hash=extracted.content_hash,
        text_content=extracted.text,
        content_length=len(extracted.text),
        family_id=family_id,
        assignment_type=assignment_type,
        jurisdiction=discovered.jurisdiction,
    )
    try:
        with session.begin_nested():
            result = analyze_and_persist_regulatory_graph(
                session,
                item,
                use_ai=True,
                skip_completed=True,
            )
        if result.status == "FAILED":
            logger.warning(
                "graph extraction recorded FAILED for document %s version %s: %s",
                document_id,
                version_id,
                result.error,
            )
    except Exception as exc:
        logger.warning(
            "graph extraction isolated failure for document %s version %s: %s: %s",
            document_id,
            version_id,
            type(exc).__name__,
            exc,
        )


def _enqueue_rag_indexing_for_document(
    session: Any,
    *,
    document_id: int,
    version_id: int | None,
) -> None:
    try:
        with session.begin_nested():
            enqueue_rag_index_job(session, document_id=document_id, version_id=version_id)
    except Exception as exc:
        logger.warning(
            "RAG indexing enqueue failed for document %s version %s: %s: %s",
            document_id,
            version_id,
            type(exc).__name__,
            exc,
        )


def _prior_reference_from_row(row: Any, reference_type: str) -> PriorVersionReference:
    return PriorVersionReference(
        document_id=row.document_id,
        version_id=row.version_id,
        title=row.title,
        source_url=row.source_url,
        content_hash=row.content_hash,
        text=row.text_content,
        reference_type=reference_type,  # type: ignore[arg-type]
    )


def _find_related_prior_reference(
    session: Any,
    *,
    extracted: ExtractedDoc,
    current_document_id: int,
    source_id: int | None,
) -> PriorVersionReference | None:
    discovered = extracted.fetched.discovered
    rows = session.execute(
        text(
            """
            select
              d.id as document_id,
              d.title,
              d.source_url,
              dv.id as version_id,
              dv.content_hash,
              dt.text_content
            from documents d
            join lateral (
              select id, content_hash
              from document_versions
              where document_id = d.id
              order by fetched_at desc
              limit 1
            ) dv on true
            left join document_texts dt on dt.content_hash = dv.content_hash
            where d.id <> :current_document_id
              and (
                (
                  cast(:source_id as bigint) is not null
                  and d.source_id = cast(:source_id as bigint)
                )
                or (
                  cast(:issuing_body as text) is not null
                  and d.issuing_body = cast(:issuing_body as text)
                )
              )
            order by d.last_seen_at desc
            limit 80
            """
        ),
        {
            "current_document_id": current_document_id,
            "source_id": source_id,
            "issuing_body": discovered.issuing_body,
        },
    ).mappings()
    best: PriorVersionReference | None = None
    best_score = 0.0
    for row in rows:
        score = title_similarity(discovered.title, row["title"])
        if score <= best_score or not is_related_title(discovered.title, row["title"]):
            continue
        best_score = score
        best = PriorVersionReference(
            document_id=row["document_id"],
            version_id=row["version_id"],
            title=row["title"],
            source_url=row["source_url"],
            content_hash=row["content_hash"],
            text=row["text_content"],
            similarity_score=score,
            reference_type="related_document",
        )
    return best


def _find_family_prior_reference(
    session: Any,
    *,
    family_id: int | None,
    current_version_id: int,
) -> PriorVersionReference | None:
    if not family_id:
        return None
    row = session.execute(
        text(
            """
            select
              d.id as document_id,
              d.title,
              d.source_url,
              dv.id as version_id,
              dv.content_hash,
              dt.text_content
            from document_version_registry vr
            join document_versions dv on dv.id = vr.document_version_id
            join documents d on d.id = vr.document_id
            left join document_texts dt on dt.content_hash = dv.content_hash
            where vr.family_id = :family_id
              and vr.document_version_id <> :current_version_id
            order by
              coalesce(vr.publication_date, vr.issue_date, date '0001-01-01') desc,
              coalesce(vr.version_number, 0) desc,
              vr.registry_version_id desc
            limit 1
            """
        ),
        {"family_id": family_id, "current_version_id": current_version_id},
    ).mappings().first()
    if not row:
        return None
    return PriorVersionReference(
        document_id=row["document_id"],
        version_id=row["version_id"],
        title=row["title"],
        source_url=row["source_url"],
        content_hash=row["content_hash"],
        text=row["text_content"],
        reference_type="related_document",
    )


def _record_event_intelligence_audit(
    session: Any,
    *,
    event_id: int | None,
    document_id: int | None,
    version_id: int | None,
    source_url: str,
    content_hash: str | None,
    title: str | None,
    intelligence: EventIntelligence,
) -> None:
    payload = intelligence.model_dump(mode="json")
    session.execute(
        text(
            """
            insert into event_intelligence_audit
              (event_id, document_id, version_id, source_url, content_hash, title,
               event_allowed, rejection_reason, freshness, significance_score,
               significance_category, actionability, quality_score, quality_category,
               is_index_document, deadlines, intelligence_json)
            values
              (:event_id, :document_id, :version_id, :source_url, :content_hash, :title,
               :event_allowed, :rejection_reason, :freshness, :significance_score,
               :significance_category, :actionability, :quality_score, :quality_category,
               :is_index_document, cast(:deadlines as jsonb), cast(:intelligence_json as jsonb))
            """
        ),
        {
            "event_id": event_id,
            "document_id": document_id,
            "version_id": version_id,
            "source_url": source_url,
            "content_hash": content_hash,
            "title": title,
            "event_allowed": intelligence.event_allowed,
            "rejection_reason": intelligence.rejection_reason,
            "freshness": intelligence.freshness,
            "significance_score": intelligence.significance_score,
            "significance_category": intelligence.significance_category,
            "actionability": intelligence.actionability,
            "quality_score": intelligence.quality_score,
            "quality_category": intelligence.quality_category,
            "is_index_document": intelligence.is_index_document,
            "deadlines": json.dumps(payload.get("deadlines") or []),
            "intelligence_json": json.dumps(payload),
        },
    )


def _record_regulatory_change_audit(
    session: Any,
    *,
    event_id: int | None,
    document_id: int | None,
    version_id: int | None,
    source_url: str,
    content_hash: str | None,
    title: str | None,
    change: RegulatoryChange,
) -> None:
    payload = change.model_dump(mode="json")
    prior = change.prior_version_reference
    session.execute(
        text(
            """
            insert into regulatory_change_audit
              (event_id, document_id, version_id, prior_document_id, prior_version_id,
               source_url, content_hash, title, change_type, is_material, confidence,
               similarity_score, evidence, prior_version_reference, previous_state,
               new_state, deadline_changes, change_json)
            values
              (:event_id, :document_id, :version_id, :prior_document_id, :prior_version_id,
               :source_url, :content_hash, :title, :change_type, :is_material, :confidence,
               :similarity_score, :evidence, :prior_version_reference, :previous_state,
               :new_state, cast(:deadline_changes as jsonb), cast(:change_json as jsonb))
            """
        ),
        {
            "event_id": event_id,
            "document_id": document_id,
            "version_id": version_id,
            "prior_document_id": prior.document_id if prior else None,
            "prior_version_id": prior.version_id if prior else None,
            "source_url": source_url,
            "content_hash": content_hash,
            "title": title,
            "change_type": change.change_type,
            "is_material": change.is_material,
            "confidence": change.confidence,
            "similarity_score": change.similarity_score,
            "evidence": change.evidence,
            "prior_version_reference": prior.source_url if prior else None,
            "previous_state": change.previous_state,
            "new_state": change.new_state,
            "deadline_changes": json.dumps(payload.get("deadline_changes") or []),
            "change_json": json.dumps(payload),
        },
    )


def _summary_from_extracted(extracted: ExtractedDoc) -> SummaryPayload:
    discovered = extracted.fetched.discovered
    summary_text = (
        _first_sentences(extracted.text, limit=700)
        or discovered.raw_summary
        or discovered.title
    )
    topics = _topic_tags(f"{discovered.title}\n{extracted.text}")
    important_dates = _important_dates(extracted.text)
    classification = extracted.classification or "REGULATORY_DOCUMENT"
    return SummaryPayload(
        plain_english_summary=summary_text[:700],
        why_it_matters=_why_it_matters(classification, topics),
        affected_segments=topics,
        important_dates=important_dates,
        action_required="urgent" if important_dates and classification in {
            "CONSULTATION_DOCUMENT",
            "TENDER_DOCUMENT",
        } else "monitor",
        confidence="high" if extracted.quality_score >= 0.82 else "medium",
        evidence_quotes=_evidence_quotes(extracted.text, discovered.source_url),
    )


def _first_sentences(text_value: str, *, limit: int) -> str:
    cleaned = " ".join(text_value.split())
    sentences = []
    for sentence in cleaned.replace("\n", " ").split(". "):
        value = sentence.strip(" .")
        if not value:
            continue
        if _is_low_value_sentence(value):
            continue
        sentences.append(value)
        if len(". ".join(sentences)) >= limit:
            break
    return ". ".join(sentences)[:limit]


def _is_low_value_sentence(value: str) -> bool:
    lower = value.lower()
    return any(
        marker in lower
        for marker in (
            "best viewed",
            "hosted by",
            "national informatics centre",
            "all rights reserved",
            "screen reader access",
            "skip to main content",
        )
    )


def _important_dates(text_value: str) -> list[str]:
    patterns = [
        r"(?:last date|last date of submission|comments.*?by|suggestions.*?by|due by)"
        r"[^.:\n]*[:\-]?\s*(\d{1,2}[-/.]\d{1,2}[-/.]\d{2,4})",
        r"(?:public hearing|bid submission|opening date|closing date|deadline)"
        r"[^.:\n]*[:\-]?\s*(\d{1,2}[-/.]\d{1,2}[-/.]\d{2,4})",
        r"\b(\d{1,2}[-/.]\d{1,2}[-/.]\d{2,4})\b",
    ]
    dates: list[str] = []
    for pattern in patterns:
        for match in re.finditer(pattern, text_value, flags=re.IGNORECASE):
            raw = match.group(1)
            if raw not in dates:
                dates.append(raw)
            if len(dates) >= 8:
                return dates
    return dates


def _why_it_matters(classification: str, topics: list[str]) -> str:
    topic_text = ", ".join(topics[:4])
    if classification == "CONSULTATION_DOCUMENT":
        return (
            "This opens or updates a consultation window. Affected stakeholders should review "
            "the proposal and track comment or hearing deadlines."
        )
    if classification == "TENDER_DOCUMENT":
        return (
            "This may create a procurement or bidding opportunity. Commercial teams should "
            "check eligibility, submission requirements, and bid deadlines."
        )
    if classification == "AMENDMENT":
        return (
            "This changes an existing regulatory instrument. Compliance and business teams "
            "should compare the amendment against current obligations."
        )
    if classification in {"ORDER", "NOTIFICATION", "CIRCULAR"}:
        return (
            "This is an official regulatory publication that may affect obligations, "
            "permissions, tariffs, or operating procedures."
        )
    if topic_text:
        return f"This official update is relevant to {topic_text} and should be monitored."
    return "This official regulatory document should be reviewed for obligations and timelines."


def _evidence_quotes(text_value: str, source_url: str) -> list[dict[str, Any]]:
    cleaned = " ".join(text_value.split())
    if not cleaned:
        return []
    chunks = [chunk.strip() for chunk in re.split(r"(?<=[.;:])\s+", cleaned) if chunk.strip()]
    useful = [chunk for chunk in chunks if not _is_low_value_sentence(chunk)]
    return [
        {"quote": chunk[:300], "source_url": source_url}
        for chunk in useful[:3]
    ]


def _topic_tags(value: str) -> list[str]:
    haystack = value.lower()
    return [
        topic
        for topic, keywords in TOPIC_KEYWORDS.items()
        if any(keyword in haystack for keyword in keywords)
    ] or ["general"]


def mark_event_state(user_id: str, event_id: int, *, is_read: bool | None = None,
                     is_bookmarked: bool | None = None) -> dict[str, bool | int]:
    values = {"user_id": user_id, "event_id": event_id}
    assignments = []
    if is_read is not None:
        values["is_read"] = is_read
        assignments.append("is_read = excluded.is_read")
    if is_bookmarked is not None:
        values["is_bookmarked"] = is_bookmarked
        assignments.append("is_bookmarked = excluded.is_bookmarked")
    read_at = "now()" if is_read else "null"
    query = f"""
    insert into user_event_state (user_id, event_id, is_read, is_bookmarked, read_at)
    values (
      :user_id, :event_id, coalesce(:is_read, false),
      coalesce(:is_bookmarked, false), {read_at}
    )
    on conflict (user_id, event_id) do update set
      {", ".join(assignments) if assignments else "event_id = excluded.event_id"},
      read_at = case when excluded.is_read then now() else user_event_state.read_at end
    returning is_read, is_bookmarked
    """
    values.setdefault("is_read", None)
    values.setdefault("is_bookmarked", None)
    try:
        with session_scope() as session:
            row = session.execute(text(query), values).first()
    except SQLAlchemyError:
        return {
            "event_id": event_id,
            "is_read": bool(is_read),
            "is_bookmarked": bool(is_bookmarked),
        }
    return {
        "event_id": event_id,
        "is_read": bool(row.is_read) if row else bool(is_read),
        "is_bookmarked": bool(row.is_bookmarked) if row else bool(is_bookmarked),
    }


# Returned only when no subscriptions row exists. Must NOT imply email consent.
DEFAULT_SUBSCRIPTION = SubscriptionSettings(
    jurisdictions=[],
    source_ids=[],
    topics=[],
    email_enabled=False,
    frequency="instant",
)


def list_enabled_source_catalog() -> list[dict[str, Any]]:
    """Enabled sources for user-facing subscription pickers (non-admin)."""

    try:
        with session_scope() as session:
            rows = session.execute(
                text(
                    """
                    select id, code, name, jurisdiction::text as jurisdiction, enabled
                    from sources
                    where enabled = true
                    order by name asc, id asc
                    """
                )
            ).mappings()
            return [dict(row) for row in rows]
    except SQLAlchemyError as exc:
        logger.warning("list_enabled_source_catalog failed: %s", exc)
        return []


def get_subscription(user_id: str) -> SubscriptionSettings:
    try:
        with session_scope() as session:
            row = session.execute(
                text(
                    """
                    select jurisdictions::text[] as jurisdictions, source_ids, topics,
                           email_enabled, frequency
                    from subscriptions
                    where user_id = :user_id
                    """
                ),
                {"user_id": user_id},
            ).first()
            if row:
                return SubscriptionSettings(
                    jurisdictions=list(row.jurisdictions or []),
                    source_ids=list(row.source_ids or []),
                    topics=list(row.topics or []),
                    email_enabled=row.email_enabled,
                    frequency=row.frequency,
                )
    except SQLAlchemyError:
        pass
    return DEFAULT_SUBSCRIPTION


def update_subscription(user_id: str, payload: SubscriptionSettings) -> SubscriptionSettings:
    with session_scope() as session:
        session.execute(
            text(
                """
                insert into subscriptions
                  (user_id, jurisdictions, source_ids, topics, email_enabled, frequency, updated_at)
                values
                  (:user_id, cast(:jurisdictions as jurisdiction_t[]), :source_ids,
                   :topics, :email_enabled, :frequency, now())
                on conflict (user_id) do update set
                  jurisdictions = excluded.jurisdictions,
                  source_ids = excluded.source_ids,
                  topics = excluded.topics,
                  email_enabled = excluded.email_enabled,
                  frequency = excluded.frequency,
                  updated_at = now()
                """
            ),
            {
                "user_id": user_id,
                "jurisdictions": payload.jurisdictions,
                "source_ids": payload.source_ids,
                "topics": payload.topics,
                "email_enabled": payload.email_enabled,
                "frequency": payload.frequency,
            },
        )
    return payload


def save_chat_message(
    user_id: str,
    role: str,
    content: str,
    event_id: int | None = None,
    *,
    session_id: str | None = None,
    knowledge_basis: str | None = None,
) -> int | bool:
    """Persist one chat message.

    Returns the new ``chat_messages.id`` so callers can bind retrieval audits to
    the exact answer, or ``False`` when persistence was suppressed.
    """

    try:
        with session_scope() as session:
            message_id = session.execute(
                text(
                    """
                    insert into chat_messages (
                      user_id,
                      event_id,
                      role,
                      content,
                      session_id,
                      knowledge_basis
                    )
                    values (
                      :user_id,
                      :event_id,
                      :role,
                      :content,
                      cast(:session_id as uuid),
                      :knowledge_basis
                    )
                    returning id
                    """
                ),
                {
                    "user_id": user_id,
                    "event_id": event_id,
                    "role": role,
                    "content": content,
                    "session_id": session_id,
                    "knowledge_basis": knowledge_basis,
                },
            ).scalar_one()
            if session_id:
                session.execute(
                    text(
                        """
                        update chat_sessions
                        set last_message_at = now(),
                            updated_at = now()
                        where id = cast(:session_id as uuid)
                          and user_id = cast(:user_id as uuid)
                          and deleted_at is null
                        """
                    ),
                    {"session_id": session_id, "user_id": user_id},
                )
    except SQLAlchemyError:
        return False
    return int(message_id)


def chat_history(user_id: str, event_id: int | None = None) -> list[dict[str, Any]]:
    clause = "event_id is null" if event_id is None else "event_id = :event_id"
    with session_scope() as session:
        rows = session.execute(
            text(
                f"""
                select id, event_id, role, content, created_at
                from chat_messages
                where user_id = :user_id and {clause}
                order by created_at desc
                limit 20
                """
            ),
            {"user_id": user_id, "event_id": event_id},
        ).mappings()
        return [dict(row) for row in rows]


def list_chat_conversations(user_id: str, *, limit: int = 50) -> list[dict[str, Any]]:
    with session_scope() as session:
        rows = session.execute(
            text(
                """
                select
                  s.id::text as id,
                  coalesce(
                    case
                      when s.title ilike 'Legacy Ask history%' then null
                      else nullif(trim(s.title), '')
                    end,
                    nullif(trim(first_user.content), ''),
                    'Untitled chat'
                  ) as title,
                  s.created_at,
                  s.updated_at,
                  s.last_message_at
                from chat_sessions s
                left join lateral (
                  select m.content
                  from chat_messages m
                  where m.session_id = s.id
                    and m.user_id = cast(:user_id as uuid)
                    and m.role = 'user'
                  order by m.created_at asc, m.id asc
                  limit 1
                ) first_user on true
                where s.user_id = cast(:user_id as uuid)
                  and s.deleted_at is null
                  and s.archived_at is null
                order by coalesce(s.last_message_at, s.updated_at) desc, s.id desc
                limit :limit
                """
            ),
            {"user_id": user_id, "limit": limit},
        ).mappings()
        return [
            {
                **dict(row),
                "title": _friendly_conversation_title(str(row["title"] or "")),
            }
            for row in rows
        ]


def _friendly_conversation_title(raw: str) -> str:
    cleaned = " ".join(str(raw or "").split())
    if not cleaned or cleaned.lower().startswith("legacy ask history"):
        return "Untitled chat"
    lowered = cleaned.lower()
    for prefix in (
        "what are the ",
        "what are ",
        "what is the ",
        "what is ",
        "how does ",
        "how do ",
        "explain ",
        "tell me ",
    ):
        if lowered.startswith(prefix):
            cleaned = cleaned[len(prefix) :].lstrip()
            break
    cleaned = cleaned.rstrip("?").strip()
    if not cleaned:
        return "Untitled chat"
    titled = cleaned[0].upper() + cleaned[1:]
    return titled if len(titled) <= 72 else f"{titled[:69].rstrip()}..."


def get_chat_conversation_messages(
    user_id: str,
    session_id: str,
) -> list[dict[str, Any]] | None:
    with session_scope() as session:
        owned = session.execute(
            text(
                """
                select id::text as id
                from chat_sessions
                where id = cast(:session_id as uuid)
                  and user_id = cast(:user_id as uuid)
                  and deleted_at is null
                """
            ),
            {"session_id": session_id, "user_id": user_id},
        ).first()
        if owned is None:
            return None
        rows = session.execute(
            text(
                """
                select
                  id,
                  role,
                  content,
                  created_at,
                  knowledge_basis,
                  session_id::text as session_id
                from chat_messages
                where user_id = cast(:user_id as uuid)
                  and session_id = cast(:session_id as uuid)
                order by created_at asc, id asc
                """
            ),
            {"user_id": user_id, "session_id": session_id},
        ).mappings()
        return [dict(row) for row in rows]


def citations_for_assistant_messages(
    user_id: str,
    assistant_message_ids: Sequence[int],
) -> dict[int, list[dict[str, Any]]]:
    """Load citations bound to specific assistant messages in one query."""

    ids = [int(item) for item in assistant_message_ids]
    if not ids:
        return {}
    with session_scope() as session:
        rows = session.execute(
            text(
                """
                select distinct on (assistant_message_id)
                  assistant_message_id,
                  citations
                from chat_retrieval_audit
                where user_id = cast(:user_id as uuid)
                  and assistant_message_id = any(cast(:ids as bigint[]))
                order by assistant_message_id, created_at desc, id desc
                """
            ),
            {"user_id": user_id, "ids": ids},
        ).mappings()
        return {
            int(row["assistant_message_id"]): (
                row["citations"] if isinstance(row["citations"], list) else []
            )
            for row in rows
        }


def citations_for_question(user_id: str, question: str) -> list[dict[str, Any]]:
    """Legacy restoration path for audits recorded before message binding.

    Rows that carry an ``assistant_message_id`` are deliberately excluded so a
    message-bound answer can never inherit another answer's citations through
    question-text matching.
    """

    with session_scope() as session:
        row = session.execute(
            text(
                """
                select citations
                from chat_retrieval_audit
                where user_id = cast(:user_id as uuid)
                  and question = :question
                  and assistant_message_id is null
                order by created_at desc
                limit 1
                """
            ),
            {"user_id": user_id, "question": question},
        ).first()
        if row is None or row.citations is None:
            return []
        payload = row.citations
        return payload if isinstance(payload, list) else []


def record_export(user_id: str, export_type: str, export_format: str, row_count: int) -> None:
    try:
        with session_scope() as session:
            session.execute(
                text(
                    """
                    insert into exports_log (user_id, export_type, export_format, row_count)
                    values (:user_id, :export_type, :export_format, :row_count)
                    """
                ),
                {
                    "user_id": user_id,
                    "export_type": export_type,
                    "export_format": export_format,
                    "row_count": row_count,
                },
            )
    except SQLAlchemyError:
        return


def seed_system_documents() -> None:
    try:
        with session_scope() as session:
            for document in SYSTEM_DOCUMENTS:
                session.execute(
                    text(
                        """
                        insert into app_documents (slug, title, category, content_md, updated_at)
                        values (:slug, :title, :category, :content_md, now())
                        on conflict (slug) do update set
                          title = excluded.title,
                          category = excluded.category,
                          content_md = excluded.content_md,
                          updated_at = now()
                        """
                    ),
                    document,
                )
    except SQLAlchemyError:
        return


def list_system_documents() -> list[dict[str, str]]:
    try:
        with session_scope() as session:
            rows = session.execute(
                text(
                    """
                    select slug, title, category
                    from app_documents
                    order by category, title
                    """
                )
            ).mappings()
            documents = [dict(row) for row in rows]
            if documents:
                return documents
    except SQLAlchemyError:
        pass
    return [
        {key: document[key] for key in ("slug", "title", "category")}
        for document in SYSTEM_DOCUMENTS
    ]


def get_system_document(slug: str) -> dict[str, str] | None:
    try:
        with session_scope() as session:
            row = session.execute(
                text(
                    """
                    select slug, title, category, content_md
                    from app_documents
                    where slug = :slug
                    """
                ),
                {"slug": slug},
            ).mappings().first()
            if row:
                return dict(row)
    except SQLAlchemyError:
        pass
    return next((document for document in SYSTEM_DOCUMENTS if document["slug"] == slug), None)
