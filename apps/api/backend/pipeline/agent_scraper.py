from __future__ import annotations

import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup
from dateutil import parser as date_parser

from backend.core.config import settings
from backend.core.models import DiscoveredDoc
from backend.core.utils import canonical_url, sha256_normalized_text

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
MONTH_YEAR_RE = re.compile(r"for\s+([A-Za-z]+\s+\d{4})\s+month", re.IGNORECASE)
MNRE_ADMIN_RE = re.compile(r"\b(filling up|scientist|deputation|recruitment)\b", re.IGNORECASE)
CERC_PUBLIC_ADMIN_RE = re.compile(
    r"\b(internship|empanelment of consult(?:ing|inq) firm|consulting firm/institutions)\b",
    re.IGNORECASE,
)
SECI_ADMIN_RE = re.compile(
    r"\b("
    r"advocates|law firms|internet leased line|printing contract|it items|"
    r"supply and maintenance of plants|digital systems|independent director|"
    r"corporate brochure|csr|annual report|credit rating"
    r")\b",
    re.IGNORECASE,
)
SECI_ENERGY_RE = re.compile(
    r"\b(rfs|rfp|eoi|tender|bos|solar|wind|renewable|re projects|ists|"
    r"rooftop|resco|fdre|rtc|cfd|green methanol|vppa)\b",
    re.IGNORECASE,
)
MOP_REJECT_RE = re.compile(
    r"\b(selection to the post|selection for the post|appointment of|"
    r"chairman|managing director|director \(projects\)|director commercial|"
    r"recruitment rules|filling up|vacancy|internship)\b",
    re.IGNORECASE,
)
MOP_ACCEPT_RE = re.compile(
    r"\b(electricity|amendment|rules|notification|guideline|policy|scheme|"
    r"draft|comments|consultation|jan vishwas|decriminalisation|"
    r"renewable consumption obligation|rco|section 11)\b",
    re.IGNORECASE,
)
MOP_CMS_HEADERS = {
    "apikey": "4bW5t13453pa",
    "Content-Type": "application/json",
    "Accept": "application/json,text/plain,*/*",
}
SOURCE_PAGE_LIMIT = 8

Parser = Callable[[dict[str, Any]], Awaitable[list[DiscoveredDoc]]]


@dataclass
class CheckpointScan:
    checkpoint_key: str | None
    lookback_count: int = 3
    reached: bool = False
    lookback_seen: int = 0


async def scrape_source(source: dict) -> list[DiscoveredDoc]:
    """Legacy source-level discovery retained for historical tools.

    Active production crawling should use scrape_source_page so discovery starts from
    curated source_pages instead of a source homepage/base URL.
    """

    if not source.get("enabled", True):
        return []
    docs = await _scrape_listing_page(source)
    return _dedupe(docs)[:SOURCE_PAGE_LIMIT]


async def scrape_source_page(source_page: dict) -> list[DiscoveredDoc]:
    """Discover candidate regulatory documents from one curated source page."""

    if not source_page.get("enabled", True):
        return []
    source = _source_from_page(source_page)
    parser = _parser_for_source_page(source)
    docs = await parser(source) if parser else await _scrape_listing_page(source)
    return _dedupe(docs)[:SOURCE_PAGE_LIMIT]


def _parser_for_source_page(source: dict[str, Any]) -> Parser | None:
    code = str(source.get("code") or "").lower()
    page_type = str(source.get("page_type") or "").lower()
    url = str(source.get("url") or "").lower()
    if code == "mnre" and page_type == "notice_listing":
        return _scrape_mnre_current_notices
    if code == "mnre" and page_type == "digest_listing":
        return _scrape_mnre_monthly_updates
    if code == "cerc" and page_type == "public_notice_listing":
        return _scrape_cerc_public_notice
    if code == "cerc" and page_type == "spn_listing":
        return _scrape_cerc_spn
    if code == "cerc" and page_type == "notice_letter_listing":
        return _scrape_cerc_notice_letter
    if code == "seci" and page_type == "tender_listing":
        return _scrape_seci_tenders
    if code == "mop" and (page_type == "whats_new_listing" or "powermin.gov.in/whats-new" in url):
        return _scrape_mop_whats_new
    return None


async def _scrape_mnre_current_notices(source: dict[str, Any]) -> list[DiscoveredDoc]:
    response = await _fetch_response(source["url"])
    soup = BeautifulSoup(response.text, "html.parser")
    docs: list[DiscoveredDoc] = []
    checkpoint = _checkpoint_scan(source)
    for row in soup.select("main div#notice-results-area table.data-table-1 tbody tr"):
        cells = [_clean_text(cell.get_text(" ", strip=True)) for cell in row.select("td")]
        if len(cells) < 6:
            continue
        title, description, start_date, end_date = cells[1], cells[2], cells[3], cells[4]
        if MNRE_ADMIN_RE.search(title):
            continue
        anchor = row.select_one("span.pdf-downloads a.pdf-download-link[href]")
        if not anchor:
            continue
        url = canonical_url(urljoin(str(response.url), anchor["href"]))
        candidate_key = _candidate_key(source, url)
        if not _should_emit_candidate(checkpoint, candidate_key):
            if _candidate_scan_complete(checkpoint):
                break
            continue
        docs.append(
            _doc(
                source,
                title=title,
                url=url,
                issue_date_text=start_date,
                candidate_key=candidate_key,
                source_record_id=_record_id_from_url(url),
                published_at=_extract_datetime(start_date),
                doc_type="pdf",
                raw_summary=(
                    f"{description} Start date: {start_date}. End date: {end_date}. "
                    f"Source page: {source.get('name')}."
                ),
            )
        )
        if _candidate_collection_complete(checkpoint, docs):
            break
    return docs


async def _scrape_mnre_monthly_updates(source: dict[str, Any]) -> list[DiscoveredDoc]:
    response = await _fetch_response(source["url"])
    soup = BeautifulSoup(response.text, "html.parser")
    docs: list[DiscoveredDoc] = []
    checkpoint = _checkpoint_scan(source)
    for item in soup.select(
        "main .wpb_text_column.wpb_content_element .wpb_wrapper ul li"
    ):
        anchor = item.select_one('a[href*="/uploads/"][href$=".pdf"]')
        if not anchor:
            continue
        title = _clean_text(anchor.get_text(" ", strip=True))
        normalized = title.lower().replace("&", "and")
        if "renewable energy policy" not in normalized or "regulatory update" not in normalized:
            continue
        month_text = _extract_month_year(title)
        url = canonical_url(urljoin(str(response.url), anchor["href"]))
        candidate_key = _candidate_key(source, month_text or url)
        if not _should_emit_candidate(checkpoint, candidate_key):
            if _candidate_scan_complete(checkpoint):
                break
            continue
        docs.append(
            _doc(
                source,
                title=title,
                url=url,
                issue_date_text=month_text,
                issue_date_precision="month" if month_text else "unknown",
                candidate_key=candidate_key,
                source_record_id=month_text or _record_id_from_url(url),
                published_at=_extract_datetime(month_text),
                doc_type="pdf",
                raw_summary=(
                    "MNRE monthly renewable energy policy and regulatory digest for "
                    f"{month_text or 'unknown month'}."
                ),
            )
        )
        if _candidate_collection_complete(checkpoint, docs):
            break
    return docs


async def _scrape_cerc_public_notice(source: dict[str, Any]) -> list[DiscoveredDoc]:
    response = await _fetch_cerc_response(source["url"])
    soup = BeautifulSoup(response.text, "html.parser")
    docs: list[DiscoveredDoc] = []
    checkpoint = _checkpoint_scan(source)
    for row in soup.select("section .wrap-md .container.coc-mid table.tbsa tbody#myTable > tr"):
        cells = [_clean_text(cell.get_text(" ", strip=True)) for cell in row.select("td")]
        links = row.select("td.style13 a[href], td a[href]")
        if len(cells) < 3 or not links:
            continue
        title = _clean_text(links[0].get_text(" ", strip=True)) or cells[1]
        if CERC_PUBLIC_ADMIN_RE.search(title):
            continue
        url = canonical_url(urljoin(str(response.url), links[0]["href"]))
        if not _is_pdf_url(url):
            continue
        publication_date = cells[-1]
        candidate_key = _candidate_key(source, url)
        if not _should_emit_candidate(checkpoint, candidate_key):
            if _candidate_scan_complete(checkpoint):
                break
            continue
        docs.append(
            _doc(
                source,
                title=title,
                url=url,
                issue_date_text=publication_date,
                candidate_key=candidate_key,
                source_record_id=_record_id_from_url(url),
                published_at=_extract_datetime(publication_date),
                doc_type="pdf",
                raw_summary=f"CERC public notice. Publication date: {publication_date}.",
            )
        )
        if _candidate_collection_complete(checkpoint, docs):
            break
    return docs


async def _scrape_cerc_spn(source: dict[str, Any]) -> list[DiscoveredDoc]:
    response = await _fetch_cerc_response(source["url"])
    soup = BeautifulSoup(response.text, "html.parser")
    docs: list[DiscoveredDoc] = []
    checkpoint = _checkpoint_scan(source)
    selector = (
        "section .wrap-md .container.coc-mid "
        "table.table.table-bordered.table-striped.tbsa tbody#myTable > tr"
    )
    for row in soup.select(selector):
        cells = [_clean_text(cell.get_text(" ", strip=True)) for cell in row.select("td")]
        if len(cells) < 4:
            continue
        links = row.select("td:nth-of-type(3) a.text[href], td:nth-of-type(3) a[href]")
        primary_url = _preferred_cerc_notice_pdf(links, str(response.url))
        if not primary_url:
            continue
        petition_no, subject, publication_date = cells[0], cells[1], cells[3]
        candidate_key = _candidate_key(source, petition_no or primary_url)
        if not _should_emit_candidate(checkpoint, candidate_key):
            if _candidate_scan_complete(checkpoint):
                break
            continue
        docs.append(
            _doc(
                source,
                title=f"{petition_no} - {subject}" if petition_no else subject,
                url=primary_url,
                issue_date_text=publication_date,
                candidate_key=candidate_key,
                source_record_id=petition_no or _record_id_from_url(primary_url),
                published_at=_extract_datetime(publication_date),
                doc_type="pdf",
                raw_summary=(
                    f"CERC statutory public notice. Petition no: {petition_no}. "
                    f"Subject: {subject}. Publication date: {publication_date}. "
                    f"Alternate notice documents: {len(links)}."
                ),
            )
        )
        if _candidate_collection_complete(checkpoint, docs):
            break
    return docs


async def _scrape_cerc_notice_letter(source: dict[str, Any]) -> list[DiscoveredDoc]:
    response = await _fetch_cerc_response(source["url"])
    soup = BeautifulSoup(response.text, "html.parser")
    docs: list[DiscoveredDoc] = []
    checkpoint = _checkpoint_scan(source)
    for row in soup.select("section .wrap-md .container.coc-mid table.tbsa tbody#myTable > tr"):
        cells = [_clean_text(cell.get_text(" ", strip=True)) for cell in row.select("td")]
        links = row.select("td.style13 a[href], td a[href]")
        if len(cells) < 3 or not links:
            continue
        title = _clean_text(links[0].get_text(" ", strip=True)) or cells[1]
        url = canonical_url(urljoin(str(response.url), links[0]["href"]))
        if not _is_pdf_url(url):
            continue
        publication_date = cells[-1]
        candidate_key = _candidate_key(source, url)
        if not _should_emit_candidate(checkpoint, candidate_key):
            if _candidate_scan_complete(checkpoint):
                break
            continue
        docs.append(
            _doc(
                source,
                title=title,
                url=url,
                issue_date_text=publication_date,
                candidate_key=candidate_key,
                source_record_id=_record_id_from_url(url),
                published_at=_extract_datetime(publication_date),
                doc_type="pdf",
                raw_summary=f"CERC notice/letter. Publication date: {publication_date}.",
            )
        )
        if _candidate_collection_complete(checkpoint, docs):
            break
    return docs


async def _scrape_seci_tenders(source: dict[str, Any]) -> list[DiscoveredDoc]:
    response = await _fetch_response(source["url"])
    soup = BeautifulSoup(response.text, "html.parser")
    docs: list[DiscoveredDoc] = []
    checkpoint = _checkpoint_scan(source)
    for row in soup.select("section.tender-section table#tender-list tbody tr.tender-row"):
        cells = [_clean_text(cell.get_text(" ", strip=True)) for cell in row.select("td")]
        detail_link = row.select_one("a.view-detail[href]")
        if len(cells) < 8 or not detail_link:
            continue
        title = cells[4]
        if SECI_ADMIN_RE.search(title) or not SECI_ENERGY_RE.search(title):
            continue
        detail_url = canonical_url(urljoin(str(response.url), detail_link["href"]))
        tender_id, tender_ref, publication_date, bid_date = cells[1], cells[3], cells[5], cells[6]
        source_record_id = tender_id or tender_ref or detail_url
        candidate_key = _candidate_key(source, source_record_id)
        if not _should_emit_candidate(checkpoint, candidate_key):
            if _candidate_scan_complete(checkpoint):
                break
            continue
        primary_url, detail_summary = await _resolve_seci_primary_document(detail_url)
        if not primary_url:
            continue
        docs.append(
            _doc(
                source,
                title=title,
                url=primary_url,
                issue_date_text=publication_date,
                candidate_key=candidate_key,
                source_record_id=source_record_id,
                published_at=_extract_datetime(publication_date),
                doc_type="pdf",
                raw_summary=(
                    f"SECI tender {tender_id}. Tender reference: {tender_ref}. "
                    f"Publication date: {publication_date}. Bid submission date: {bid_date}. "
                    f"Detail page: {detail_url}. {detail_summary}"
                ),
            )
        )
        if _candidate_collection_complete(checkpoint, docs):
            break
    return docs


async def _scrape_mop_whats_new(source: dict[str, Any]) -> list[DiscoveredDoc]:
    payload = await _fetch_json(
        "https://www.powermin.gov.in/cms/wp-json/post-page/whats_new",
        headers=MOP_CMS_HEADERS,
        verify=False,
    )
    docs: list[DiscoveredDoc] = []
    checkpoint = _checkpoint_scan(source)
    for post in payload.get("posts") or []:
        title = _clean_text(str(post.get("post_title") or ""))
        if not title or MOP_REJECT_RE.search(title) or not MOP_ACCEPT_RE.search(title):
            continue
        source_record_id = str(post.get("ID") or "")
        candidate_key = _candidate_key(source, source_record_id or title)
        if not _should_emit_candidate(checkpoint, candidate_key):
            if _candidate_scan_complete(checkpoint):
                break
            continue
        file_ids = _as_list((post.get("acf_data") or {}).get("file"))
        attachment = await _resolve_mop_attachment(file_ids)
        if not attachment.get("url"):
            continue
        attachment_title = _clean_text(str(attachment.get("title") or "")) or title
        issue_date_text = str(attachment.get("file_date") or post.get("post_date") or "")
        docs.append(
            _doc(
                source,
                title=attachment_title,
                url=canonical_url(str(attachment["url"])),
                issue_date_text=issue_date_text,
                candidate_key=candidate_key,
                source_record_id=source_record_id,
                published_at=_extract_datetime(str(post.get("post_date") or issue_date_text)),
                doc_type="pdf",
                raw_summary=(
                    f"Ministry of Power What's New item. Post ID: {post.get('ID')}. "
                    f"Attachment ID: {attachment.get('attachment_id')}. "
                    f"Published: {post.get('post_date')}. File date: {attachment.get('file_date')}."
                ),
            )
        )
        if _candidate_collection_complete(checkpoint, docs):
            break
    return docs


async def _resolve_seci_primary_document(detail_url: str) -> tuple[str | None, str]:
    response = await _fetch_response(detail_url)
    soup = BeautifulSoup(response.text, "html.parser")
    documents: list[tuple[int, str, str]] = []
    corrigenda = 0
    for anchor in soup.select('section.tender-detail a[href*="/uploads/tenders/"]'):
        url = canonical_url(urljoin(str(response.url), anchor["href"]))
        if not _is_pdf_url(url):
            continue
        text = _clean_text(anchor.get_text(" ", strip=True))
        lower = f"{text} {url}".lower()
        if "/corrigendums/" in lower:
            corrigenda += 1
            continue
        documents.append((_seci_document_score(lower), text, url))
    if not documents:
        return None, "No primary tender PDF found on detail page."
    _, title, url = sorted(documents, key=lambda item: item[0])[0]
    return url, f"Primary detail document: {title}. Corrigendum documents found: {corrigenda}."


async def _resolve_mop_attachment(file_ids: list[Any]) -> dict[str, Any]:
    for file_id in file_ids:
        if not file_id:
            continue
        payload = await _fetch_json(
            f"https://www.powermin.gov.in/cms/wp-json/post-page/post?id={file_id}",
            headers=MOP_CMS_HEADERS,
            verify=False,
        )
        post = payload.get("posts") or {}
        acf = post.get("acf_data") or {}
        url = _find_pdf_url(acf)
        if url:
            return {
                "attachment_id": file_id,
                "title": acf.get("title") or post.get("post_title"),
                "file_date": acf.get("file_date"),
                "url": url,
            }
    return {}


async def _scrape_listing_page(source: dict) -> list[DiscoveredDoc]:
    source_url = source["url"]
    response = await _fetch_response(source_url)
    soup = BeautifulSoup(response.text, "html.parser")
    docs: list[DiscoveredDoc] = []
    checkpoint = _checkpoint_scan(source)
    for anchor in soup.select("a[href]"):
        href = anchor.get("href")
        if not href:
            continue
        url = canonical_url(urljoin(str(response.url), href))
        text = _clean_text(anchor.get_text(" ", strip=True))
        parent_text = (
            _clean_text(anchor.find_parent().get_text(" ", strip=True))
            if anchor.find_parent()
            else ""
        )
        if not _is_allowed_url(url, source):
            continue
        if not _looks_like_primary_document(url, f"{text} {parent_text}", source_url):
            continue
        title = _best_candidate_title(text, parent_text, url)
        issue_date = _extract_date(f"{text} {url}")
        candidate_key = _candidate_key(source, url)
        if not _should_emit_candidate(checkpoint, candidate_key):
            if _candidate_scan_complete(checkpoint):
                break
            continue
        docs.append(
            DiscoveredDoc(
                source_code=source["code"],
                title=title[:500],
                source_url=url,
                issuing_body=source.get("name"),
                issue_date=issue_date,
                issue_date_precision="day" if issue_date else "unknown",
                doc_type="pdf" if _is_pdf_url(url) else "html",
                jurisdiction=source.get("jurisdiction"),
                raw_summary=parent_text[:1200] if parent_text else None,
                candidate_key=candidate_key,
                source_record_id=_record_id_from_url(url),
                published_at=_datetime_from_date(issue_date),
            )
        )
        if _candidate_collection_complete(checkpoint, docs):
            break
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
        issue_date = _parse_iso_date(item.get("publish_date")) or _extract_date(" ".join(excerpts))
        published_at = _extract_datetime(item.get("publish_date")) or _datetime_from_date(
            issue_date
        )
        docs.append(
            DiscoveredDoc(
                source_code=source["code"],
                title=(item.get("title") or _title_from_url(url))[:500],
                source_url=canonical_url(url),
                issuing_body=source.get("name"),
                issue_date=issue_date,
                issue_date_precision="day" if issue_date else "unknown",
                doc_type="pdf" if _is_pdf_url(url) else "html",
                jurisdiction=source.get("jurisdiction"),
                raw_summary=_clean_text(" ".join(excerpts))[:1200] if excerpts else None,
                candidate_key=_candidate_key(source, canonical_url(url)),
                source_record_id=_record_id_from_url(url),
                published_at=published_at,
            )
        )
    return docs


async def _fetch_response(
    url: str,
    *,
    headers: dict[str, str] | None = None,
    verify: bool = True,
    timeout: int = 45,
) -> httpx.Response:
    request_headers = {"User-Agent": settings.crawl_user_agent, **(headers or {})}
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            async with httpx.AsyncClient(
                headers=request_headers,
                follow_redirects=True,
                timeout=timeout,
                verify=verify,
            ) as client:
                response = await client.get(url)
                response.raise_for_status()
                return response
        except Exception as exc:
            last_error = exc
            if attempt == 2:
                raise
    assert last_error is not None
    raise last_error


async def _fetch_cerc_response(url: str) -> httpx.Response:
    variants = [url]
    if url.startswith("https://"):
        variants.append("http://" + url.removeprefix("https://"))
    if "://cercind.gov.in/" in url:
        variants.append(url.replace("://cercind.gov.in/", "://www.cercind.gov.in/"))
    last_error: Exception | None = None
    for variant in variants:
        try:
            return await _fetch_response(
                variant,
                headers={
                    "Accept": (
                        "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
                    )
                },
                verify=False,
            )
        except Exception as exc:
            last_error = exc
    assert last_error is not None
    raise last_error


async def _fetch_json(
    url: str,
    *,
    headers: dict[str, str] | None = None,
    verify: bool = True,
) -> dict[str, Any]:
    response = await _fetch_response(url, headers=headers, verify=verify)
    payload = response.json()
    return payload if isinstance(payload, dict) else {}


def _checkpoint_scan(source: dict[str, Any]) -> CheckpointScan:
    checkpoint = source.get("checkpoint") or {}
    lookback = int(checkpoint.get("lookback_count") or 3)
    return CheckpointScan(
        checkpoint_key=checkpoint.get("checkpoint_key"),
        lookback_count=max(0, lookback),
    )


def _should_emit_candidate(checkpoint: CheckpointScan, candidate_key: str | None) -> bool:
    if not checkpoint.checkpoint_key or not candidate_key:
        return True
    if checkpoint.reached:
        checkpoint.lookback_seen += 1
        return False
    if candidate_key == checkpoint.checkpoint_key:
        checkpoint.reached = True
        return False
    return True


def _candidate_scan_complete(checkpoint: CheckpointScan) -> bool:
    return bool(
        checkpoint.checkpoint_key
        and checkpoint.reached
        and checkpoint.lookback_seen >= checkpoint.lookback_count
    )


def _candidate_collection_complete(
    checkpoint: CheckpointScan,
    docs: list[DiscoveredDoc],
) -> bool:
    return len(docs) >= SOURCE_PAGE_LIMIT or _candidate_scan_complete(checkpoint)


def _candidate_key(source: dict[str, Any], raw_key: str | None) -> str | None:
    cleaned = _clean_text(raw_key or "")
    if not cleaned:
        return None
    return sha256_normalized_text(f"{source.get('id') or ''}:{cleaned}")


def _record_id_from_url(url: str) -> str:
    path = urlparse(url).path.rstrip("/")
    return path.rsplit("/", 1)[-1] or canonical_url(url)


def _source_from_page(source_page: dict) -> dict:
    return {
        "id": source_page.get("id"),
        "code": source_page["source_code"],
        "name": source_page["source_name"],
        "source_page_name": source_page.get("name"),
        "page_type": source_page.get("page_type"),
        "url": source_page["url"],
        "allowed_domains": source_page.get("allowed_domains") or [],
        "jurisdiction": source_page.get("jurisdiction"),
        "enabled": source_page.get("enabled", True),
        "crawler_type": source_page.get("crawler_type", "agent"),
        "hint": source_page.get("hint"),
        "checkpoint": source_page.get("checkpoint"),
    }


def _doc(
    source: dict[str, Any],
    *,
    title: str,
    url: str,
    issue_date_text: str | None = None,
    issue_date_precision: str | None = None,
    candidate_key: str | None = None,
    source_record_id: str | None = None,
    published_at: datetime | None = None,
    doc_type: str | None = None,
    raw_summary: str | None = None,
) -> DiscoveredDoc:
    parsed_date = (
        _extract_month_year_date(issue_date_text or "")
        if issue_date_precision == "month"
        else _extract_date(issue_date_text or "")
    )
    precision = issue_date_precision or ("day" if parsed_date else "unknown")
    return DiscoveredDoc(
        source_code=source["code"],
        title=_clean_text(title)[:500],
        source_url=canonical_url(url),
        issuing_body=source.get("name"),
        issue_date=parsed_date,
        issue_date_precision=precision,  # type: ignore[arg-type]
        doc_type=doc_type or ("pdf" if _is_pdf_url(url) else "html"),
        jurisdiction=source.get("jurisdiction"),
        raw_summary=_clean_text(raw_summary or "")[:1200] or None,
        candidate_key=candidate_key,
        source_record_id=source_record_id,
        published_at=published_at or _datetime_from_date(parsed_date),
    )


def _preferred_cerc_notice_pdf(anchors: list[Any], base_url: str) -> str | None:
    candidates: list[tuple[int, str]] = []
    preferences = ("the hindu", "times of india", "indian express", "hindustan times", "english")
    for index, anchor in enumerate(anchors):
        url = canonical_url(urljoin(base_url, anchor.get("href") or ""))
        if not _is_pdf_url(url):
            continue
        text = _clean_text(anchor.get_text(" ", strip=True)).lower()
        score = 100 + index
        for pref_index, preference in enumerate(preferences):
            if preference in text or preference.replace(" ", "-") in url.lower():
                score = pref_index
                break
        candidates.append((score, url))
    return sorted(candidates)[0][1] if candidates else None


def _seci_document_score(value: str) -> int:
    preferences = (
        "rfs",
        "rfp",
        "nit",
        "draft_rfs",
        "draft rfs",
        "contractual_tender",
        "contractual tender",
        "technical_tender",
        "technical tender",
    )
    for index, term in enumerate(preferences):
        if term in value:
            return index
    if "integrity" in value or "format" in value:
        return 50
    return 20


def _find_pdf_url(value: Any) -> str | None:
    if isinstance(value, dict):
        url = value.get("url")
        if isinstance(url, str) and _is_pdf_url(url):
            return canonical_url(url)
        preferred_keys = (
            "pdf",
            "pdf_both",
            "pdf_english",
            "pdf_hindi",
            "pdf_file",
            "file",
            "document",
            "detailed_documents",
        )
        for key in preferred_keys:
            found = _find_pdf_url(value.get(key))
            if found:
                return found
        for nested in value.values():
            found = _find_pdf_url(nested)
            if found:
                return found
    if isinstance(value, list):
        for item in value:
            found = _find_pdf_url(item)
            if found:
                return found
    return None


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def _looks_like_primary_document(url: str, text: str, listing_url: str) -> bool:
    if canonical_url(url) == canonical_url(listing_url):
        return False
    if _is_disallowed_discovery_link(url, text):
        return False
    if _is_pdf_url(url):
        return True
    haystack = f"{url} {text}".lower()
    return any(keyword in haystack for keyword in DOCUMENT_KEYWORDS)


def _is_disallowed_discovery_link(url: str, text: str) -> bool:
    path = urlparse(url).path.lower()
    haystack = f"{path} {text}".lower()
    if any(marker in haystack for marker in ("/archive", "archive page", "search", "sitemap")):
        return True
    if any(marker in path for marker in ("/category/", "/notice-category/", "/page/")):
        return True
    cleaned = _clean_text(text).lower()
    return cleaned in {
        "",
        "home",
        "back",
        "about us",
        "contact us",
        "skip to main content",
        "screen reader access",
        "view all",
        "read more",
    }


def _best_candidate_title(text: str, parent_text: str, url: str) -> str:
    for value in (text, parent_text, _title_from_url(url)):
        cleaned = _clean_text(value)
        if cleaned and cleaned.lower() not in {"click here", "download", "view", "pdf"}:
            return cleaned
    return _title_from_url(url)


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
    return re.sub(r"\s+", " ", value or "").strip()


def _title_from_url(url: str) -> str:
    path = urlparse(url).path.rstrip("/").rsplit("/", 1)[-1]
    return re.sub(r"[-_]+", " ", path.rsplit(".", 1)[0]).strip().title() or url


def _extract_date(value: str) -> date | None:
    if not value:
        return None
    try:
        return date_parser.parse(value, dayfirst=True, fuzzy=True).date()
    except (ValueError, OverflowError):
        pass
    match = DATE_RE.search(value)
    if not match:
        return None
    try:
        return date_parser.parse(match.group("date"), dayfirst=True, fuzzy=True).date()
    except (ValueError, OverflowError):
        return None


def _extract_month_year(value: str) -> str | None:
    match = MONTH_YEAR_RE.search(value)
    return match.group(1) if match else None


def _extract_month_year_date(value: str) -> date | None:
    if not value:
        return None
    try:
        parsed = date_parser.parse(value, default=datetime(2000, 1, 1))
        return date(parsed.year, parsed.month, 1)
    except (ValueError, OverflowError):
        return None


def _extract_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return date_parser.parse(value, dayfirst=True, fuzzy=True, default=datetime(2000, 1, 1))
    except (ValueError, OverflowError):
        return None


def _datetime_from_date(value: date | None) -> datetime | None:
    return datetime(value.year, value.month, value.day) if value else None


def _parse_iso_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date_parser.parse(value).date()
    except (ValueError, OverflowError):
        return None


def _is_pdf_url(url: str) -> bool:
    return urlparse(url).path.lower().endswith(".pdf")
