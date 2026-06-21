import json
import logging
from datetime import date
from typing import Any

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from backend.core.db import session_scope
from backend.core.models import DigestResponse, EventSummary, SubscriptionSettings, SummaryPayload
from backend.core.system_docs import SYSTEM_DOCUMENTS
from backend.core.utils import canonical_url, sha256_normalized_text

logger = logging.getLogger(__name__)

DEMO_USER_ID = "00000000-0000-4000-8000-000000000001"
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
    user_id: str = DEMO_USER_ID,
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


def get_event(event_id: int, user_id: str = DEMO_USER_ID) -> EventSummary | None:
    query = f"{EVENT_SELECT} where e.id = :event_id"
    try:
        with session_scope() as session:
            row = session.execute(text(query), {"event_id": event_id, "user_id": user_id}).first()
            if row:
                return _event_from_row(row)
    except SQLAlchemyError as exc:
        logger.warning("get_event(%s) failed: %s", event_id, exc)
    return None


def latest_digest(user_id: str = DEMO_USER_ID) -> DigestResponse:
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


def digest_by_date(digest_date: date, user_id: str = DEMO_USER_ID) -> DigestResponse:
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
                           crawler_type::text as crawler_type, allowed_domains, enabled,
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


def list_crawl_runs(limit: int = 25) -> list[dict[str, Any]]:
    try:
        with session_scope() as session:
            rows = session.execute(
                text(
                    """
                    select id, started_at, finished_at, status::text as status,
                           sources_attempted, sources_succeeded, docs_found,
                           new_events, errors
                    from crawl_runs
                    order by started_at desc
                    limit :limit
                    """
                ),
                {"limit": limit},
            ).mappings()
            return [dict(row) for row in rows]
    except SQLAlchemyError:
        return []


def create_crawl_run() -> int | None:
    try:
        with session_scope() as session:
            row = session.execute(
                text("insert into crawl_runs default values returning id")
            ).first()
            return row.id if row else None
    except SQLAlchemyError:
        return None


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


def persist_discovered_documents(discovered_docs: list[Any]) -> list[int]:
    event_ids: list[int] = []
    for discovered in discovered_docs:
        event_id = _persist_discovered_document(discovered)
        if event_id:
            event_ids.append(event_id)
    return event_ids


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
    return latest_digest()


def _persist_discovered_document(discovered: Any) -> int | None:
    url = canonical_url(discovered.source_url)
    url_hash = sha256_normalized_text(url)
    content_basis = "\n".join(
        [
            discovered.title,
            discovered.raw_summary or "",
            discovered.issue_date.isoformat() if discovered.issue_date else "",
            url,
        ]
    )
    content_hash = sha256_normalized_text(content_basis)
    file_hash = content_hash
    topics = _topic_tags(content_basis)
    summary = _summary_from_discovered(discovered)
    try:
        with session_scope() as session:
            source = session.execute(
                text("select id from sources where code = :source_code"),
                {"source_code": discovered.source_code},
            ).first()
            latest = session.execute(
                text(
                    """
                    select dv.id, dv.file_hash, dv.content_hash
                    from document_versions dv
                    join documents d on d.id = dv.document_id
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
            version = session.execute(
                text(
                    """
                    insert into document_versions
                      (document_id, file_hash, content_hash, raw_file_path, text_path,
                       page_count, needs_ocr, http_status)
                    values
                      (:document_id, :file_hash, :content_hash, :raw_file_path, :text_path,
                       0, false, 200)
                    on conflict (document_id, file_hash) do nothing
                    returning id
                    """
                ),
                {
                    "document_id": document.id,
                    "file_hash": file_hash,
                    "content_hash": content_hash,
                    "raw_file_path": url,
                    "text_path": None,
                },
            ).first()
            if not version:
                return None
            if latest and latest.content_hash == content_hash:
                return None
            event_type = "CHANGED" if latest else "NEW"
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
                    "document_id": document.id,
                    "version_id": version.id,
                    "event_type": event_type,
                    "digest_origin": discovered.source_code,
                    "raw_summary": discovered.raw_summary,
                    "topic_tags": topics,
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
            return event.id
    except SQLAlchemyError:
        return None


def _summary_from_discovered(discovered: Any) -> SummaryPayload:
    summary_text = discovered.raw_summary or discovered.title
    return SummaryPayload(
        plain_english_summary=summary_text[:700],
        why_it_matters=(
            "This is an official regulatory-source update. Review the primary link "
            "to confirm obligations, timelines, and affected entities before acting."
        ),
        affected_segments=_topic_tags(f"{discovered.title} {summary_text}"),
        important_dates=[discovered.issue_date.isoformat()] if discovered.issue_date else [],
        action_required="monitor",
        confidence="medium" if discovered.raw_summary else "low",
        evidence_quotes=[{"quote": summary_text[:300], "source_url": discovered.source_url}],
    )


def _topic_tags(value: str) -> list[str]:
    haystack = value.lower()
    return [
        topic
        for topic, keywords in TOPIC_KEYWORDS.items()
        if any(keyword in haystack for keyword in keywords)
    ] or ["general"]


def mark_event_state(user_id: str, event_id: int, *, is_read: bool | None = None,
                     is_bookmarked: bool | None = None) -> dict[str, bool | int]:
    if user_id == DEMO_USER_ID:
        return {
            "event_id": event_id,
            "is_read": bool(is_read),
            "is_bookmarked": bool(is_bookmarked),
        }
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


DEFAULT_SUBSCRIPTION = SubscriptionSettings(
    jurisdictions=["central"],
    topics=["solar", "tariff", "open access", "RPO/REC", "storage", "transmission"],
    email_enabled=True,
    frequency="daily",
)


def get_subscription(user_id: str) -> SubscriptionSettings:
    if user_id == DEMO_USER_ID:
        return DEFAULT_SUBSCRIPTION
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
    if user_id == DEMO_USER_ID:
        return payload
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


def save_chat_message(user_id: str, role: str, content: str, event_id: int | None = None) -> None:
    if user_id == DEMO_USER_ID:
        return
    try:
        with session_scope() as session:
            session.execute(
                text(
                    """
                    insert into chat_messages (user_id, event_id, role, content)
                    values (:user_id, :event_id, :role, :content)
                    """
                ),
                {"user_id": user_id, "event_id": event_id, "role": role, "content": content},
            )
    except SQLAlchemyError:
        return


def chat_history(user_id: str, event_id: int | None = None) -> list[dict[str, Any]]:
    if user_id == DEMO_USER_ID:
        return []
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


def record_export(user_id: str, export_type: str, export_format: str, row_count: int) -> None:
    if user_id == DEMO_USER_ID:
        return
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
