"""Paginated, filterable read models for the admin operations console.

These functions exist alongside the unpaginated ``list_*`` helpers in
``backend.core.repository``: the pipeline and CLI tools still want whole-table
reads, while the admin UI needs server-side search, filtering and paging so it
never has to load an entire registry to render one screen.

Read-only. No crawler, persistence or security behaviour is defined here.
"""

from __future__ import annotations

import logging
from typing import Any, Literal

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from backend.core.db import session_scope
from backend.core.repository import assemble_crawl_run_telemetry

logger = logging.getLogger(__name__)

DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100

SourceStatusFilter = Literal["all", "enabled", "disabled", "error"]
LastRunFilter = Literal["all", "never", "24h", "7d", "30d", "older"]
RunStatusFilter = Literal["all", "queued", "running", "success", "partial", "failed"]
RunDateFilter = Literal["all", "today", "24h", "7d", "30d"]
RoleFilter = Literal["all", "user", "admin"]
NotificationFilter = Literal["all", "email", "in_app"]

_INTERVALS: dict[str, str] = {
    "24h": "24 hours",
    "7d": "7 days",
    "30d": "30 days",
}


def _normalize_paging(page: int, page_size: int) -> tuple[int, int, int]:
    """Clamp caller-supplied paging into a safe range and derive the offset."""

    requested_size = int(page_size or DEFAULT_PAGE_SIZE)
    if requested_size < 1:
        requested_size = DEFAULT_PAGE_SIZE
    safe_size = min(requested_size, MAX_PAGE_SIZE)
    safe_page = max(1, int(page or 1))
    return safe_page, safe_size, (safe_page - 1) * safe_size


def _envelope(
    items: list[dict[str, Any]],
    total: int,
    page: int,
    page_size: int,
    **extra: Any,
) -> dict[str, Any]:
    total_pages = (total + page_size - 1) // page_size if page_size else 0
    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages,
        **extra,
    }


def _empty(page: int, page_size: int, **extra: Any) -> dict[str, Any]:
    return _envelope([], 0, page, page_size, **extra)


def _search_term(q: str | None) -> str | None:
    cleaned = (q or "").strip()
    return f"%{cleaned.lower()}%" if cleaned else None


# --------------------------------------------------------------------------- #
# Sources
# --------------------------------------------------------------------------- #

_SOURCE_COLUMNS = """
  s.id, s.code, s.name, s.jurisdiction::text as jurisdiction, s.url,
  s.crawler_type::text as crawler_type, s.allowed_domains, s.hint, s.enabled,
  s.last_checked_at, s.last_status, s.consecutive_failures,
  coalesce(pages.page_count, 0) as page_count,
  coalesce(pages.enabled_page_count, 0) as enabled_page_count,
  pages.last_page_crawled_at
"""

_SOURCE_PAGE_LATERAL = """
left join lateral (
  select
    count(*)::int as page_count,
    count(*) filter (where sp.enabled)::int as enabled_page_count,
    max(sp.last_crawled_at) as last_page_crawled_at
  from source_pages sp
  where sp.source_id = s.id
    and sp.deleted_at is null
) pages on true
"""


def _source_filter_sql(
    search: str | None,
    jurisdiction: str | None,
    status: str,
    last_run: str,
) -> tuple[list[str], dict[str, Any]]:
    clauses: list[str] = []
    params: dict[str, Any] = {}

    if search:
        clauses.append(
            "(lower(s.code) like :search or lower(s.name) like :search"
            " or lower(s.url) like :search)"
        )
        params["search"] = search

    if jurisdiction and jurisdiction != "all":
        clauses.append("s.jurisdiction::text = :jurisdiction")
        params["jurisdiction"] = jurisdiction

    if status == "enabled":
        clauses.append("s.enabled")
    elif status == "disabled":
        clauses.append("not s.enabled")
    elif status == "error":
        clauses.append("coalesce(s.consecutive_failures, 0) > 0")

    if last_run == "never":
        clauses.append("s.last_checked_at is null")
    elif last_run in _INTERVALS:
        clauses.append(
            f"s.last_checked_at >= now() - interval '{_INTERVALS[last_run]}'"
        )
    elif last_run == "older":
        clauses.append(
            "s.last_checked_at is not null"
            " and s.last_checked_at < now() - interval '30 days'"
        )

    return clauses, params


def list_sources_page(
    *,
    q: str | None = None,
    jurisdiction: str | None = None,
    status: str = "all",
    last_run: str = "all",
    page: int = 1,
    page_size: int = DEFAULT_PAGE_SIZE,
) -> dict[str, Any]:
    """Search, filter and page the monitored source registry."""

    safe_page, safe_size, offset = _normalize_paging(page, page_size)
    clauses, params = _source_filter_sql(
        _search_term(q), jurisdiction, status, last_run
    )
    where = f"where {' and '.join(clauses)}" if clauses else ""

    try:
        with session_scope() as session:
            total = int(
                session.execute(
                    text(f"select count(*)::int from sources s {where}"),
                    params,
                ).scalar()
                or 0
            )
            rows = session.execute(
                text(
                    f"""
                    select {_SOURCE_COLUMNS}
                    from sources s
                    {_SOURCE_PAGE_LATERAL}
                    {where}
                    order by s.enabled desc, s.code asc
                    limit :limit offset :offset
                    """
                ),
                {**params, "limit": safe_size, "offset": offset},
            ).mappings()
            items = [dict(row) for row in rows]
    except SQLAlchemyError as exc:
        logger.warning("list_sources_page failed: %s", exc)
        return _empty(safe_page, safe_size, facets=_empty_source_facets())

    return _envelope(items, total, safe_page, safe_size, facets=source_facets())


def _empty_source_facets() -> dict[str, int]:
    return {"total": 0, "enabled": 0, "disabled": 0, "degraded": 0, "never_crawled": 0}


def source_facets() -> dict[str, int]:
    """Registry-wide source counts, independent of the active filters."""

    try:
        with session_scope() as session:
            row = session.execute(
                text(
                    """
                    select
                      count(*)::int as total,
                      count(*) filter (where enabled)::int as enabled,
                      count(*) filter (where not enabled)::int as disabled,
                      count(*) filter (
                        where coalesce(consecutive_failures, 0) > 0
                      )::int as degraded,
                      count(*) filter (
                        where last_checked_at is null
                      )::int as never_crawled
                    from sources
                    """
                )
            ).mappings().first()
            return dict(row) if row else _empty_source_facets()
    except SQLAlchemyError as exc:
        logger.warning("source_facets failed: %s", exc)
        return _empty_source_facets()


# --------------------------------------------------------------------------- #
# Crawl runs
# --------------------------------------------------------------------------- #

_RUN_SOURCE_LATERAL = """
left join lateral (
  select array_agg(distinct code) as source_codes
  from (
    select da.source_code as code
    from discovery_audit da
    where da.run_id = cr.id and nullif(da.source_code, '') is not null
    union
    select err.item->>'source' as code
    from jsonb_array_elements(coalesce(cr.errors, '[]'::jsonb)) as err(item)
    where nullif(err.item->>'source', '') is not null
  ) codes
  where codes.code is not null
) run_sources on true
"""


def _run_filter_sql(
    search: str | None,
    source_code: str | None,
    status: str,
    date_range: str,
) -> tuple[list[str], dict[str, Any]]:
    clauses: list[str] = []
    params: dict[str, Any] = {}

    if search:
        clauses.append(
            "(cast(cr.id as text) like :search"
            " or exists (select 1 from unnest(coalesce(run_sources.source_codes,"
            " array[]::text[])) as code where lower(code) like :search))"
        )
        params["search"] = search

    if source_code and source_code != "all":
        clauses.append(
            "exists (select 1 from unnest(coalesce(run_sources.source_codes,"
            " array[]::text[])) as code where lower(code) = :source_code)"
        )
        params["source_code"] = source_code.strip().lower()

    if status and status != "all":
        clauses.append("cr.status::text = :status")
        params["status"] = status

    if date_range == "today":
        clauses.append("cr.started_at >= date_trunc('day', now())")
    elif date_range in _INTERVALS:
        clauses.append(
            f"cr.started_at >= now() - interval '{_INTERVALS[date_range]}'"
        )

    return clauses, params


def list_crawl_runs_page(
    *,
    q: str | None = None,
    source_code: str | None = None,
    status: str = "all",
    date_range: str = "all",
    page: int = 1,
    page_size: int = DEFAULT_PAGE_SIZE,
) -> dict[str, Any]:
    """Search, filter and page crawl-run telemetry for the operations console."""

    from backend.core.repository import (  # noqa: PLC0415
        _CRAWL_RUN_COLUMNS,
        _CRAWL_RUN_FROM,
    )

    safe_page, safe_size, offset = _normalize_paging(page, page_size)
    clauses, params = _run_filter_sql(
        _search_term(q), source_code, status, date_range
    )
    where = f"where {' and '.join(clauses)}" if clauses else ""

    try:
        with session_scope() as session:
            total = int(
                session.execute(
                    text(
                        f"""
                        select count(*)::int
                        from crawl_runs cr
                        {_RUN_SOURCE_LATERAL}
                        {where}
                        """
                    ),
                    params,
                ).scalar()
                or 0
            )
            rows = session.execute(
                text(
                    f"""
                    select {_CRAWL_RUN_COLUMNS}, run_sources.source_codes
                    {_CRAWL_RUN_FROM}
                    {_RUN_SOURCE_LATERAL}
                    {where}
                    order by cr.started_at desc
                    limit :limit offset :offset
                    """
                ),
                {**params, "limit": safe_size, "offset": offset},
            ).mappings()
            items = [_run_row(dict(row)) for row in rows]
    except SQLAlchemyError as exc:
        logger.warning("list_crawl_runs_page failed: %s", exc)
        return _empty(safe_page, safe_size, summary=_empty_run_summary())

    return _envelope(items, total, safe_page, safe_size, summary=crawl_run_summary())


def _run_row(row: dict[str, Any]) -> dict[str, Any]:
    source_codes = [code for code in (row.pop("source_codes", None) or []) if code]
    telemetry = assemble_crawl_run_telemetry(row)
    telemetry["source_codes"] = sorted({str(code) for code in source_codes})
    return telemetry


def _empty_run_summary() -> dict[str, int]:
    return {
        "runs_today": 0,
        "queued": 0,
        "running": 0,
        "success": 0,
        "partial": 0,
        "failed": 0,
    }


def crawl_run_summary() -> dict[str, int]:
    """Operational headline counts: today's volume plus live status breakdown."""

    try:
        with session_scope() as session:
            row = session.execute(
                text(
                    """
                    select
                      count(*) filter (
                        where started_at >= date_trunc('day', now())
                      )::int as runs_today,
                      count(*) filter (where status = 'queued')::int as queued,
                      count(*) filter (where status = 'running')::int as running,
                      count(*) filter (
                        where status = 'success'
                          and started_at >= now() - interval '7 days'
                      )::int as success,
                      count(*) filter (
                        where status = 'partial'
                          and started_at >= now() - interval '7 days'
                      )::int as partial,
                      count(*) filter (
                        where status = 'failed'
                          and started_at >= now() - interval '7 days'
                      )::int as failed
                    from crawl_runs
                    """
                )
            ).mappings().first()
            return dict(row) if row else _empty_run_summary()
    except SQLAlchemyError as exc:
        logger.warning("crawl_run_summary failed: %s", exc)
        return _empty_run_summary()


def list_crawl_run_sources() -> list[dict[str, Any]]:
    """Source codes that have participated in at least one crawl run."""

    try:
        with session_scope() as session:
            rows = session.execute(
                text(
                    """
                    select distinct s.code, s.name
                    from sources s
                    where exists (
                      select 1 from discovery_audit da where da.source_code = s.code
                    )
                    order by s.code
                    """
                )
            ).mappings()
            return [dict(row) for row in rows]
    except SQLAlchemyError as exc:
        logger.warning("list_crawl_run_sources failed: %s", exc)
        return []


def get_crawl_run_pages(run_id: int) -> list[dict[str, Any]]:
    """Per-page results for one crawl run.

    Derived entirely from data the pipeline already writes: ``discovery_audit``
    rows carry the ``source_page_id`` they were discovered from, and
    ``crawl_runs.errors`` carries page-scoped failure entries. Pages that were
    attempted but produced neither are still surfaced from the error side, so a
    run that failed before discovery still shows what it tried to crawl.
    """

    try:
        with session_scope() as session:
            rows = session.execute(
                text(
                    """
                    with audit as (
                      select
                        nullif(da.metadata->>'source_page_id', '') as page_key,
                        max(da.source_code) as source_code,
                        count(*)::int as documents_discovered,
                        count(*) filter (
                          where da.is_valid_event_source
                        )::int as documents_accepted,
                        count(*) filter (
                          where da.content_hash is not null
                        )::int as documents_with_content,
                        min(da.created_at) as first_seen_at,
                        max(da.created_at) as last_seen_at
                      from discovery_audit da
                      where da.run_id = :run_id
                      group by 1
                    ),
                    failures as (
                      select
                        nullif(err.item->>'source_page_id', '') as page_key,
                        max(err.item->>'source') as source_code,
                        jsonb_agg(err.item) as errors
                      from crawl_runs cr,
                           jsonb_array_elements(
                             coalesce(cr.errors, '[]'::jsonb)
                           ) as err(item)
                      where cr.id = :run_id
                      group by 1
                    ),
                    keys as (
                      select page_key from audit
                      union
                      select page_key from failures
                    )
                    select
                      k.page_key,
                      sp.id as page_id,
                      sp.name as page_name,
                      sp.url as page_url,
                      sp.page_type,
                      sp.priority,
                      sp.enabled,
                      coalesce(s.code, a.source_code, f.source_code) as source_code,
                      s.name as source_name,
                      coalesce(a.documents_discovered, 0) as documents_discovered,
                      coalesce(a.documents_accepted, 0) as documents_accepted,
                      coalesce(a.documents_with_content, 0)
                        as documents_with_content,
                      a.first_seen_at,
                      a.last_seen_at,
                      coalesce(f.errors, '[]'::jsonb) as errors
                    from keys k
                    left join audit a on a.page_key = k.page_key
                    left join failures f on f.page_key = k.page_key
                    left join source_pages sp on sp.id::text = k.page_key
                    left join sources s on s.id = sp.source_id
                    order by
                      (coalesce(f.errors, '[]'::jsonb) <> '[]'::jsonb) desc,
                      sp.priority nulls last,
                      sp.name nulls last
                    """
                ),
                {"run_id": run_id},
            ).mappings()
            return [_run_page_row(dict(row)) for row in rows]
    except SQLAlchemyError as exc:
        logger.warning("get_crawl_run_pages(%s) failed: %s", run_id, exc)
        return []


def _run_page_row(row: dict[str, Any]) -> dict[str, Any]:
    errors = row.get("errors") or []
    if not isinstance(errors, list):
        errors = []
    page_key = row.pop("page_key", None)
    discovered = int(row.get("documents_discovered") or 0)

    if errors:
        status = "failed"
    elif discovered:
        status = "success"
    else:
        status = "no_documents"

    return {
        **row,
        "page_id": row.get("page_id")
        or (int(page_key) if str(page_key or "").isdigit() else None),
        "page_name": row.get("page_name") or "Unresolved page",
        "errors": errors,
        "status": status,
    }


# --------------------------------------------------------------------------- #
# Users
# --------------------------------------------------------------------------- #


def list_admin_users_page(
    *,
    q: str | None = None,
    role: str = "all",
    notifications: str = "all",
    page: int = 1,
    page_size: int = DEFAULT_PAGE_SIZE,
) -> dict[str, Any]:
    """Search, filter and page user profiles for the admin user console."""

    safe_page, safe_size, offset = _normalize_paging(page, page_size)
    search = _search_term(q)
    clauses: list[str] = []
    params: dict[str, Any] = {}

    if search:
        clauses.append(
            "(lower(coalesce(p.email, '')) like :search"
            " or lower(coalesce(p.full_name, '')) like :search)"
        )
        params["search"] = search
    if role and role != "all":
        clauses.append("p.role::text = :role")
        params["role"] = role
    if notifications == "email":
        clauses.append("coalesce(s.email_enabled, false)")
    elif notifications == "in_app":
        clauses.append("not coalesce(s.email_enabled, false)")

    where = f"where {' and '.join(clauses)}" if clauses else ""
    joins = "left join subscriptions s on s.user_id = p.id"

    try:
        with session_scope() as session:
            total = int(
                session.execute(
                    text(
                        f"select count(*)::int from profiles p {joins} {where}"
                    ),
                    params,
                ).scalar()
                or 0
            )
            rows = session.execute(
                text(
                    f"""
                    select
                      p.id::text as id,
                      p.email,
                      p.full_name,
                      p.role::text as role,
                      p.created_at,
                      s.email_enabled,
                      s.frequency,
                      coalesce(s.topics, '{{}}') as topics
                    from profiles p
                    {joins}
                    {where}
                    order by p.created_at desc
                    limit :limit offset :offset
                    """
                ),
                {**params, "limit": safe_size, "offset": offset},
            ).mappings()
            items = [dict(row) for row in rows]
    except SQLAlchemyError as exc:
        logger.warning("list_admin_users_page failed: %s", exc)
        return _empty(safe_page, safe_size, summary=_empty_user_summary())

    return _envelope(items, total, safe_page, safe_size, summary=user_summary())


def _empty_user_summary() -> dict[str, int]:
    return {"total": 0, "admins": 0, "users": 0, "email_enabled": 0}


def user_summary() -> dict[str, int]:
    """Directory-wide user counts, independent of the active filters."""

    try:
        with session_scope() as session:
            row = session.execute(
                text(
                    """
                    select
                      count(*)::int as total,
                      count(*) filter (where p.role::text = 'admin')::int as admins,
                      count(*) filter (where p.role::text = 'user')::int as users,
                      count(*) filter (
                        where coalesce(s.email_enabled, false)
                      )::int as email_enabled
                    from profiles p
                    left join subscriptions s on s.user_id = p.id
                    """
                )
            ).mappings().first()
            return dict(row) if row else _empty_user_summary()
    except SQLAlchemyError as exc:
        logger.warning("user_summary failed: %s", exc)
        return _empty_user_summary()
