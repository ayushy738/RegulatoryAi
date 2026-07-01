from __future__ import annotations

import re
from collections.abc import Iterable

from backend.core.config import settings
from backend.rag.models import DocumentChunk

TOKEN_RE = re.compile(r"[A-Za-z0-9]+(?:[-'][A-Za-z0-9]+)?|[^\sA-Za-z0-9]")
SECTION_RE = re.compile(
    r"^(?:chapter|part|section|regulation|clause|article|schedule|annexure)\b|"
    r"^[A-Z][A-Z0-9 ,./()&-]{8,120}$",
    re.IGNORECASE,
)
LIST_START_RE = re.compile(r"^\s*(?:\d+[.)]|[a-zA-Z][.)]|\([a-zA-Z0-9]+\)|[-*])\s+")


def chunk_document_text(
    *,
    document_id: int,
    version_id: int | None,
    family_id: int | None,
    text: str,
    content_hash: str | None,
) -> list[DocumentChunk]:
    units = list(_semantic_units(text))
    if not units:
        return []

    min_tokens = settings.rag_chunk_min_tokens
    max_tokens = settings.rag_chunk_max_tokens
    overlap_tokens = settings.rag_chunk_overlap_tokens
    chunks: list[DocumentChunk] = []
    current: list[_Unit] = []
    current_tokens = 0
    section_title: str | None = None

    for unit in units:
        if unit.section_title:
            section_title = unit.section_title
        if current and current_tokens + unit.token_count > max_tokens:
            chunks.append(
                _make_chunk(
                    document_id=document_id,
                    version_id=version_id,
                    family_id=family_id,
                    index=len(chunks),
                    units=current,
                    section_title=section_title,
                    content_hash=content_hash,
                )
            )
            current = _overlap_units(current, overlap_tokens)
            current_tokens = sum(item.token_count for item in current)
        current.append(unit)
        current_tokens += unit.token_count
        if current_tokens >= min_tokens and _safe_chunk_boundary(unit.text):
            chunks.append(
                _make_chunk(
                    document_id=document_id,
                    version_id=version_id,
                    family_id=family_id,
                    index=len(chunks),
                    units=current,
                    section_title=section_title,
                    content_hash=content_hash,
                )
            )
            current = _overlap_units(current, overlap_tokens)
            current_tokens = sum(item.token_count for item in current)

    if current:
        text_value = "\n\n".join(unit.text for unit in current).strip()
        if text_value and (not chunks or text_value != chunks[-1].text):
            chunks.append(
                _make_chunk(
                    document_id=document_id,
                    version_id=version_id,
                    family_id=family_id,
                    index=len(chunks),
                    units=current,
                    section_title=section_title,
                    content_hash=content_hash,
                )
            )
    return chunks


class _Unit:
    def __init__(self, text: str, section_title: str | None = None) -> None:
        self.text = _clean(text)
        self.token_count = estimate_tokens(self.text)
        self.section_title = section_title


def estimate_tokens(value: str) -> int:
    return max(1, len(TOKEN_RE.findall(value)))


def _semantic_units(text: str) -> Iterable[_Unit]:
    paragraphs = [_clean(part) for part in re.split(r"\n\s*\n+", text) if _clean(part)]
    section_title: str | None = None
    for paragraph in paragraphs:
        if _is_section_title(paragraph):
            section_title = paragraph[:180]
            yield _Unit(paragraph, section_title=section_title)
            continue
        if _is_list_block(paragraph) or estimate_tokens(paragraph) <= 220:
            yield _Unit(paragraph, section_title=section_title)
            continue
        for sentence_group in _sentence_groups(paragraph):
            yield _Unit(sentence_group, section_title=section_title)


def _sentence_groups(paragraph: str) -> list[str]:
    sentences = [
        item.strip()
        for item in re.split(r"(?<=[.;:!?])\s+(?=[A-Z0-9(])", paragraph)
        if item.strip()
    ]
    groups: list[str] = []
    current: list[str] = []
    current_tokens = 0
    for sentence in sentences:
        tokens = estimate_tokens(sentence)
        if current and current_tokens + tokens > 260:
            groups.append(" ".join(current))
            current = []
            current_tokens = 0
        current.append(sentence)
        current_tokens += tokens
    if current:
        groups.append(" ".join(current))
    return groups or [paragraph]


def _overlap_units(units: list[_Unit], overlap_tokens: int) -> list[_Unit]:
    if overlap_tokens <= 0:
        return []
    selected: list[_Unit] = []
    total = 0
    for unit in reversed(units):
        if total >= overlap_tokens and _safe_chunk_boundary(unit.text):
            break
        selected.append(unit)
        total += unit.token_count
    return list(reversed(selected))


def _make_chunk(
    *,
    document_id: int,
    version_id: int | None,
    family_id: int | None,
    index: int,
    units: list[_Unit],
    section_title: str | None,
    content_hash: str | None,
) -> DocumentChunk:
    text_value = "\n\n".join(unit.text for unit in units).strip()
    return DocumentChunk(
        document_id=document_id,
        version_id=version_id,
        family_id=family_id,
        chunk_index=index,
        text=text_value,
        token_count=estimate_tokens(text_value),
        section_title=section_title,
        content_hash=content_hash,
    )


def _safe_chunk_boundary(value: str) -> bool:
    stripped = value.strip()
    return bool(stripped) and stripped[-1:] in {".", ";", ":", ")", "]", "}"}


def _is_section_title(value: str) -> bool:
    stripped = value.strip()
    if len(stripped) > 160:
        return False
    return bool(SECTION_RE.search(stripped))


def _is_list_block(value: str) -> bool:
    lines = [line for line in value.splitlines() if line.strip()]
    return len(lines) >= 2 and sum(1 for line in lines if LIST_START_RE.match(line)) >= 2


def _clean(value: str) -> str:
    return re.sub(r"[ \t]+", " ", value or "").strip()
