from __future__ import annotations

import re
from datetime import date
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup
from dateutil import parser as date_parser

from backend.core.config import settings
from backend.core.models import DiscoveredDoc
from backend.core.utils import canonical_url

DOCUMENT_KEYWORDS = (
    "regulation",
    "order",
    "notification",
    "circular",
    "guideline",
    "policy",
    "scheme",
    "tariff",
    "petition",
    "corrigendum",
    "amendment",
    "notice",
    "renewable",
    "solar",
    "wind",
    "open access",
    "rpo",
    "rec",
    "transmission",
    "grid",
    "tender",
)
DATE_RE = re.compile(
    r"(?P<date>(?:\d{1,2}[-/.]\d{1,2}[-/.]\d{2,4})|(?:\d{4}[-/.]\d{1,2}[-/.]\d{1,2}))"
)


async def scrape_source(source: dict) -> list[DiscoveredDoc]:
    """Discover candidate regulatory documents from a configured source."""

    if not source.get("enabled", True):
        return []

    fetch_error: Exception | None = None
    try:
        docs = await _scrape_listing_page(source)
    except Exception as exc:
        fetch_error = exc
        docs = []
    if not docs:
        docs = await _parallel_search(source)
    if not docs and fetch_error:
        raise RuntimeError(f"listing fetch failed and fallback found no docs: {fetch_error!r}")
    return _dedupe(docs)[:8]


async def _scrape_listing_page(source: dict) -> list[DiscoveredDoc]:
    source_url = source["url"]
    async with httpx.AsyncClient(
        headers={"User-Agent": settings.crawl_user_agent},
        follow_redirects=True,
        timeout=30,
    ) as client:
        response = await client.get(source_url)
        response.raise_for_status()

    soup = BeautifulSoup(response.text, "lxml")
    docs: list[DiscoveredDoc] = []
    for anchor in soup.select("a[href]"):
        href = anchor.get("href")
        if not href:
            continue
        url = canonical_url(urljoin(str(response.url), href))
        text = _clean_text(anchor.get_text(" ", strip=True))
        if not _is_allowed_url(url, source):
            continue
        if not _looks_like_document(url, text):
            continue
        title = text or _title_from_url(url)
        docs.append(
            DiscoveredDoc(
                source_code=source["code"],
                title=title[:500],
                source_url=url,
                issuing_body=source.get("name"),
                issue_date=_extract_date(f"{text} {url}"),
                issue_date_precision="day" if _extract_date(f"{text} {url}") else "unknown",
                doc_type="pdf" if urlparse(url).path.lower().endswith(".pdf") else "html",
                jurisdiction=source.get("jurisdiction"),
                raw_summary=_clean_text(anchor.find_parent().get_text(" ", strip=True))[:1200]
                if anchor.find_parent()
                else None,
            )
        )
    return docs


async def _parallel_search(source: dict) -> list[DiscoveredDoc]:
    if not settings.parallel_api_key:
        return []

    allowed_domains = _allowed_domains(source)
    objective = (
        f"Find recent official regulatory documents from {source['name']} in India. "
        "Prefer orders, regulations, circulars, notifications, policy updates, tariffs, "
        "renewable energy, power sector, transmission, RPO/REC, open access, or grid documents. "
        "Return only official source pages or PDFs."
    )
    body = {
        "objective": objective,
        "search_queries": [
            f"{source['name']} regulatory order PDF",
            f"{source['name']} notification circular power",
            f"site:{urlparse(source['url']).netloc} order notification PDF",
        ],
        "mode": "basic",
        "max_chars_total": 5000,
        "advanced_settings": {
            "source_policy": {"include_domains": allowed_domains},
            "excerpt_settings": {"max_chars_per_result": 700},
            "max_results": 8,
        },
    }
    async with httpx.AsyncClient(timeout=60) as client:
        response = await client.post(
            f"{settings.parallel_base_url.rstrip('/')}/v1/search",
            headers={"x-api-key": settings.parallel_api_key, "Content-Type": "application/json"},
            json=body,
        )
        response.raise_for_status()
    payload = response.json()
    docs: list[DiscoveredDoc] = []
    for item in payload.get("results", []):
        url = item.get("url")
        if not url or not _is_allowed_url(url, source):
            continue
        excerpts = item.get("excerpts") or []
        docs.append(
            DiscoveredDoc(
                source_code=source["code"],
                title=(item.get("title") or _title_from_url(url))[:500],
                source_url=canonical_url(url),
                issuing_body=source.get("name"),
                issue_date=(
                    _parse_iso_date(item.get("publish_date"))
                    or _extract_date(" ".join(excerpts))
                ),
                issue_date_precision="day" if item.get("publish_date") else "unknown",
                doc_type="pdf" if urlparse(url).path.lower().endswith(".pdf") else "html",
                jurisdiction=source.get("jurisdiction"),
                raw_summary=_clean_text(" ".join(excerpts))[:1200] if excerpts else None,
            )
        )
    return docs


def _looks_like_document(url: str, text: str) -> bool:
    haystack = f"{url} {text}".lower()
    return urlparse(url).path.lower().endswith(".pdf") or any(
        keyword in haystack for keyword in DOCUMENT_KEYWORDS
    )


def _is_allowed_url(url: str, source: dict) -> bool:
    host = urlparse(url).netloc.lower()
    if not host:
        return False
    return any(host == domain or host.endswith(f".{domain}") for domain in _allowed_domains(source))


def _allowed_domains(source: dict) -> list[str]:
    domains = {urlparse(source["url"]).netloc.lower()}
    domains.update(str(domain).lower() for domain in source.get("allowed_domains") or [])
    return sorted(domain for domain in domains if domain)


def _dedupe(docs: list[DiscoveredDoc]) -> list[DiscoveredDoc]:
    seen: set[str] = set()
    deduped: list[DiscoveredDoc] = []
    for doc in docs:
        key = canonical_url(doc.source_url)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(doc)
    return deduped


def _clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _title_from_url(url: str) -> str:
    path = urlparse(url).path.rstrip("/").rsplit("/", 1)[-1]
    return re.sub(r"[-_]+", " ", path.rsplit(".", 1)[0]).strip().title() or url


def _extract_date(value: str) -> date | None:
    match = DATE_RE.search(value)
    if not match:
        return None
    try:
        return date_parser.parse(match.group("date"), dayfirst=True, fuzzy=True).date()
    except (ValueError, OverflowError):
        return None


def _parse_iso_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date_parser.parse(value).date()
    except (ValueError, OverflowError):
        return None
