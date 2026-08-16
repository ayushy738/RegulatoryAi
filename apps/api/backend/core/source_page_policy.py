"""Source-page URL policy: DB configuration is crawlable; domains enforce safety.

Crawl selection must not depend on a hardcoded URL allowlist. Safety is enforced by
requiring monitored page URLs to belong to the source website host and/or
``sources.allowed_domains`` (same host rules as discovery filtering in
``agent_scraper``).
"""

from __future__ import annotations

import ipaddress
from typing import Any, Iterable, Sequence
from urllib.parse import urlsplit

from backend.core.utils import canonical_url

BLOCKED_HOSTNAMES = frozenset(
    {
        "localhost",
        "localhost.localdomain",
        "metadata",
        "metadata.google.internal",
    }
)


class SourcePagePolicyError(ValueError):
    """Raised when a source/page URL violates crawl safety policy."""


def crawl_domains_for_source(
    *,
    source_url: str,
    allowed_domains: Sequence[str] | None = None,
) -> list[str]:
    """Domains permitted for monitored pages and discovered document links.

    Mirrors ``agent_scraper._allowed_domains``: always includes the source website
    host, plus any explicitly configured ``allowed_domains`` (CDN mirrors, etc.).
    """

    domains: set[str] = set()
    host = _hostname(source_url)
    if host:
        domains.add(host)
    for domain in allowed_domains or []:
        cleaned = str(domain).strip().lower().lstrip(".")
        if cleaned:
            domains.add(cleaned)
    return sorted(domains)


def host_permitted(host: str, domains: Iterable[str]) -> bool:
    """True when host equals or is a subdomain of any permitted domain."""

    normalized_host = host.strip().lower().rstrip(".")
    if not normalized_host:
        return False
    for domain in domains:
        normalized_domain = str(domain).strip().lower().lstrip(".").rstrip(".")
        if not normalized_domain:
            continue
        if normalized_host == normalized_domain or normalized_host.endswith(
            f".{normalized_domain}"
        ):
            return True
    return False


def validate_public_http_url(url: str, *, field: str = "url") -> str:
    """Require http(s) public URL; return canonical form. No DNS resolution."""

    raw = (url or "").strip()
    if not raw:
        raise SourcePagePolicyError(f"{field} is required")
    parts = urlsplit(raw)
    scheme = parts.scheme.lower()
    if scheme not in {"http", "https"}:
        raise SourcePagePolicyError(f"{field} must use http or https")
    if parts.username or parts.password:
        raise SourcePagePolicyError(f"{field} must not include credentials")
    host = (parts.hostname or "").lower().rstrip(".")
    if not host:
        raise SourcePagePolicyError(f"{field} must include a hostname")
    if host in BLOCKED_HOSTNAMES or host.endswith(".localhost") or host.endswith(".local"):
        raise SourcePagePolicyError(f"{field} host is not allowed")
    if _is_blocked_ip_literal(host):
        raise SourcePagePolicyError(f"{field} must not target a private or link-local address")
    return canonical_url(raw)


def validate_source_page_url(
    *,
    page_url: str,
    source_url: str,
    allowed_domains: Sequence[str] | None = None,
) -> str:
    """Validate a monitored page URL against the source's permitted domains."""

    canonical_page = validate_public_http_url(page_url, field="page url")
    canonical_source = validate_public_http_url(source_url, field="source url")
    domains = crawl_domains_for_source(
        source_url=canonical_source,
        allowed_domains=allowed_domains,
    )
    page_host = _hostname(canonical_page)
    if not page_host or not host_permitted(page_host, domains):
        allowed = ", ".join(domains) if domains else "(none)"
        raise SourcePagePolicyError(
            f"page url host '{page_host}' is outside source allowed domains [{allowed}]"
        )
    return canonical_page


def page_url_permitted_for_source(
    *,
    page_url: str,
    source_url: str,
    allowed_domains: Sequence[str] | None = None,
) -> bool:
    try:
        validate_source_page_url(
            page_url=page_url,
            source_url=source_url,
            allowed_domains=allowed_domains,
        )
        return True
    except SourcePagePolicyError:
        return False


def diagnose_source_page_selection(
    *,
    source_id: int | None,
    page_id: int | None,
    configured_pages: Sequence[dict[str, Any]],
    enabled_pages: Sequence[dict[str, Any]],
    crawlable_pages: Sequence[dict[str, Any]],
) -> dict[str, Any]:
    """Operator-facing explanation when crawl selection yields zero pages."""

    source_code = None
    source_enabled = None
    if configured_pages:
        source_code = configured_pages[0].get("source_code") or configured_pages[0].get(
            "code"
        )
        source_enabled = configured_pages[0].get("source_enabled")
    elif enabled_pages:
        source_code = enabled_pages[0].get("source_code")
        source_enabled = True

    configured_count = len(configured_pages)
    enabled_count = len(enabled_pages)
    crawlable_count = len(crawlable_pages)

    if crawlable_count > 0:
        reason = None
    elif source_id is not None and configured_count == 0 and page_id is None:
        reason = "no_source_pages_configured"
    elif page_id is not None and configured_count == 0:
        reason = "source_page_not_found"
    elif source_enabled is False:
        reason = "source_disabled"
    elif configured_count > 0 and enabled_count == 0:
        reason = "all_pages_disabled"
    elif enabled_count > 0 and crawlable_count == 0:
        reason = "invalid_source_domain_configuration"
    else:
        reason = "no_enabled_source_pages_configured"

    return {
        "source": source_code,
        "source_id": source_id,
        "page_id": page_id,
        "configured_pages": configured_count,
        "enabled_pages": enabled_count,
        "crawlable_pages": crawlable_count,
        "reason": reason,
        "source_enabled": source_enabled,
    }


def _hostname(url: str) -> str | None:
    host = urlsplit(url).hostname
    if not host:
        return None
    return host.lower().rstrip(".")


def _is_blocked_ip_literal(host: str) -> bool:
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        # Also catch IPv6 in brackets already stripped by urlsplit.hostname
        return False
    return bool(
        address.is_private
        or address.is_loopback
        or address.is_link_local
        or address.is_reserved
        or address.is_multicast
        or address.is_unspecified
    )

