from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from datetime import date
from io import BytesIO
from pathlib import Path
from urllib.parse import urlparse

import httpx
import pdfplumber
from bs4 import BeautifulSoup
from dateutil import parser as date_parser

from backend.core.config import settings
from backend.core.models import (
    DiscoveredDoc,
    DiscoveryAuditRecord,
    ExtractedDoc,
    FetchedFile,
)
from backend.core.storage import storage
from backend.core.utils import canonical_url, sha256_bytes, sha256_normalized_text
from backend.pipeline.quality_gate import classify_candidate

DATE_RE = re.compile(
    r"(?P<date>(?:\d{1,2}[-/.]\d{1,2}[-/.]\d{2,4})|(?:\d{4}[-/.]\d{1,2}[-/.]\d{1,2}))"
)
GENERIC_TITLES = {
    "",
    "home",
    "ministry of power",
    "ministry of power: home",
    "central electricity regulatory commission",
    "cercind",
    "orders",
    "notices",
    "circular",
    "solar",
    "wind",
    "recruitments",
}
MIN_PRIMARY_TEXT_CHARS = 250


@dataclass(frozen=True)
class PrimaryDocumentResult:
    accepted: list[ExtractedDoc]
    audits: list[DiscoveryAuditRecord]


async def acquire_primary_documents(candidates: list[DiscoveredDoc]) -> PrimaryDocumentResult:
    accepted: list[ExtractedDoc] = []
    audits: list[DiscoveryAuditRecord] = []
    for candidate in candidates:
        extracted, audit = await acquire_primary_document(candidate)
        audits.append(audit)
        if extracted:
            accepted.append(extracted)
    return PrimaryDocumentResult(accepted=accepted, audits=audits)


async def acquire_primary_document(
    candidate: DiscoveredDoc,
) -> tuple[ExtractedDoc | None, DiscoveryAuditRecord]:
    pre_quality = classify_candidate(candidate)
    if not pre_quality.is_valid_event_source:
        return None, _audit(candidate, pre_quality)

    try:
        fetched_bytes, final_url, content_type, etag, last_modified, status = await _fetch_bytes(
            candidate.source_url
        )
    except Exception as exc:
        return None, _audit(
            candidate,
            pre_quality,
            reason_code="NO_PRIMARY_DOCUMENT",
            metadata={"error": f"{type(exc).__name__}: {exc}"},
        )

    file_hash = sha256_bytes(fetched_bytes)
    doc_type = _doc_type(final_url, content_type, candidate.doc_type)
    text, page_count, needs_ocr = _extract_text(fetched_bytes, doc_type)
    content_hash = sha256_normalized_text(text)
    content_length = len(text.strip())
    if content_length < MIN_PRIMARY_TEXT_CHARS:
        return None, _audit(
            candidate,
            pre_quality,
            primary_url=final_url,
            content_length=content_length,
            content_hash=content_hash,
            reason_code="INSUFFICIENT_CONTENT",
            metadata={"doc_type": doc_type, "content_type": content_type, "needs_ocr": needs_ocr},
        )

    content_quality = classify_candidate(candidate, content_text=text)
    if not content_quality.is_valid_event_source:
        return None, _audit(
            candidate,
            content_quality,
            primary_url=final_url,
            content_length=content_length,
            content_hash=content_hash,
            metadata={"doc_type": doc_type, "content_type": content_type, "needs_ocr": needs_ocr},
        )

    source_code = candidate.source_code
    raw_path = _store_raw(source_code, file_hash, doc_type, fetched_bytes, content_type)
    text_path = _store_text(source_code, content_hash, text)
    improved = candidate.model_copy(
        update={
            "title": _best_title(candidate.title, text),
            "source_url": canonical_url(final_url),
            "issue_date": candidate.issue_date or _extract_date(text),
            "issue_date_precision": candidate.issue_date_precision
            if candidate.issue_date
            else ("day" if _extract_date(text) else "unknown"),
            "doc_type": doc_type,
            "raw_summary": _excerpt(text),
        }
    )
    fetched = FetchedFile(
        discovered=improved,
        file_hash=file_hash,
        raw_file_path=raw_path,
        http_status=status,
        etag=etag,
        last_modified=last_modified,
        content_type=content_type,
    )
    extracted = ExtractedDoc(
        fetched=fetched,
        text=text,
        content_hash=content_hash,
        page_count=page_count,
        needs_ocr=needs_ocr,
        text_path=text_path,
        classification=content_quality.classification,
        quality_score=content_quality.confidence,
        evidence_excerpt=_excerpt(text, limit=600),
    )
    return extracted, _audit(
        improved,
        content_quality,
        primary_url=final_url,
        content_length=content_length,
        content_hash=content_hash,
        metadata={"doc_type": doc_type, "content_type": content_type, "needs_ocr": needs_ocr},
    )


async def _fetch_bytes(url: str) -> tuple[bytes, str, str | None, str | None, str | None, int]:
    async with httpx.AsyncClient(
        headers={"User-Agent": settings.crawl_user_agent},
        follow_redirects=True,
        timeout=45,
    ) as client:
        response = await client.get(url)
        response.raise_for_status()
        return (
            response.content,
            canonical_url(str(response.url)),
            response.headers.get("content-type"),
            response.headers.get("etag"),
            response.headers.get("last-modified"),
            response.status_code,
        )


def _doc_type(url: str, content_type: str | None, fallback: str | None) -> str:
    value = f"{url} {content_type or ''} {fallback or ''}".lower()
    if ".pdf" in urlparse(url).path.lower() or "pdf" in value:
        return "pdf"
    return "html"


def _extract_text(payload: bytes, doc_type: str) -> tuple[str, int, bool]:
    if doc_type == "pdf":
        return _extract_pdf_text(payload)
    return _extract_html_text(payload), 1, False


def _extract_pdf_text(payload: bytes) -> tuple[str, int, bool]:
    text_parts: list[str] = []
    page_count = 0
    with pdfplumber.open(BytesIO(payload)) as pdf:
        page_count = len(pdf.pages)
        for page in pdf.pages:
            text_parts.append(page.extract_text() or "")
    text = "\n\n".join(part for part in text_parts if part).strip()
    needs_ocr = len(text) < MIN_PRIMARY_TEXT_CHARS
    if needs_ocr:
        ocr_text = _ocr_pdf_bytes(payload)
        if len(ocr_text) > len(text):
            text = ocr_text
    return text, page_count, needs_ocr


def _extract_html_text(payload: bytes) -> str:
    soup = BeautifulSoup(payload, "lxml")
    for selector in ("script", "style", "noscript", "svg", "nav", "header", "footer", "form"):
        for node in soup.select(selector):
            node.decompose()
    main = soup.find("main") or soup.find("article") or soup.body or soup
    return _clean_text(main.get_text("\n", strip=True))


def _ocr_pdf_bytes(payload: bytes) -> str:
    if not shutil.which("pdftoppm") or not shutil.which("tesseract"):
        return ""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        pdf_path = tmp_path / "document.pdf"
        image_prefix = tmp_path / "page"
        pdf_path.write_bytes(payload)
        subprocess.run(
            ["pdftoppm", "-png", "-r", "200", str(pdf_path), str(image_prefix)],
            check=False,
            capture_output=True,
            timeout=60,
        )
        parts: list[str] = []
        for image in sorted(tmp_path.glob("page-*.png"))[:20]:
            result = subprocess.run(
                ["tesseract", str(image), "stdout", "-l", "eng"],
                check=False,
                capture_output=True,
                text=True,
                timeout=45,
            )
            if result.stdout:
                parts.append(result.stdout)
        return _clean_text("\n".join(parts))


def _store_raw(
    source_code: str,
    file_hash: str,
    doc_type: str,
    payload: bytes,
    content_type: str | None,
) -> str:
    extension = "pdf" if doc_type == "pdf" else "html"
    key = f"raw/{source_code}/{file_hash}.{extension}"
    if settings.supabase_service_role_key:
        media_type = content_type or ("application/pdf" if doc_type == "pdf" else "text/html")
        storage.put_bytes(key, payload, media_type)
    return key


def _store_text(source_code: str, content_hash: str, text: str) -> str:
    key = f"text/{source_code}/{content_hash}.txt"
    if settings.supabase_service_role_key:
        storage.put_bytes(key, text.encode("utf-8"), "text/plain; charset=utf-8")
    return key


def _best_title(existing: str, text: str) -> str:
    existing_clean = _clean_text(existing)
    if existing_clean.lower() not in GENERIC_TITLES and len(existing_clean) >= 12:
        return existing_clean[:500]
    for line in text.splitlines():
        line = _clean_text(line)
        if 12 <= len(line) <= 220 and not _is_boilerplate(line):
            return line[:500]
    return existing_clean[:500] or "Untitled regulatory document"


def _excerpt(text: str, *, limit: int = 1200) -> str:
    cleaned = _clean_text(text)
    return cleaned[:limit]


def _extract_date(value: str) -> date | None:
    match = DATE_RE.search(value)
    if not match:
        return None
    try:
        return date_parser.parse(match.group("date"), dayfirst=True, fuzzy=True).date()
    except (ValueError, OverflowError):
        return None


def _audit(
    candidate: DiscoveredDoc,
    quality,
    *,
    primary_url: str | None = None,
    content_length: int = 0,
    content_hash: str | None = None,
    reason_code: str | None = None,
    metadata: dict | None = None,
) -> DiscoveryAuditRecord:
    return DiscoveryAuditRecord(
        source_code=candidate.source_code,
        source_url=candidate.source_url,
        title=candidate.title,
        classification=quality.classification,
        is_valid_event_source=quality.is_valid_event_source and reason_code is None,
        confidence=quality.confidence,
        reason_code=reason_code or quality.reason_code,
        primary_url=primary_url,
        content_length=content_length,
        content_hash=content_hash,
        metadata={"explanation": quality.explanation, **(metadata or {})},
    )


def _clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _is_boilerplate(value: str) -> bool:
    lower = value.lower()
    return any(
        marker in lower
        for marker in (
            "best viewed",
            "hosted by",
            "national informatics centre",
            "skip to main",
            "screen reader access",
        )
    )
