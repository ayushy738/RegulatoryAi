from __future__ import annotations

from datetime import date

from backend.rag.models import Intent, RetrievalHit

SOURCE_AUTHORITY = {
    "cerc": 1.0,
    "mnre": 0.92,
    "mop": 0.95,
    "seci": 0.86,
}


def rank_hits(hits: list[RetrievalHit], intent: Intent, *, limit: int) -> list[RetrievalHit]:
    deduped = _dedupe(hits)
    for hit in deduped:
        hit.freshness_score = _freshness(hit.issue_date)
        hit.authority_score = _authority(hit.source_url)
        hit.version_score = 1.0 if hit.metadata.get("latest_version") else 0.6
        hit.quality_score = float(hit.metadata.get("quality_score") or 0.65)
        dominant_boost = 0.12 if hit.source in intent.dominant_sources else 0.0
        hit.final_score = min(
            1.0,
            (
                hit.vector_score * 0.32
                + hit.keyword_score * 0.22
                + hit.graph_score * 0.18
                + hit.freshness_score * 0.10
                + hit.authority_score * 0.08
                + hit.version_score * 0.06
                + hit.quality_score * 0.04
                + dominant_boost
            ),
        )
    return sorted(deduped, key=lambda item: item.final_score, reverse=True)[:limit]


def _dedupe(hits: list[RetrievalHit]) -> list[RetrievalHit]:
    by_key: dict[tuple[int, int | None, str], RetrievalHit] = {}
    for hit in hits:
        key = (hit.document_id, hit.chunk_id, hit.source)
        current = by_key.get(key)
        if current is None:
            by_key[key] = hit
            continue
        current.vector_score = max(current.vector_score, hit.vector_score)
        current.keyword_score = max(current.keyword_score, hit.keyword_score)
        current.graph_score = max(current.graph_score, hit.graph_score)
        if len(hit.text) > len(current.text):
            current.text = hit.text
    return list(by_key.values())


def _freshness(issue_date: date | None) -> float:
    if issue_date is None:
        return 0.35
    days = max(0, (date.today() - issue_date).days)
    if days <= 90:
        return 1.0
    if days <= 365:
        return 0.82
    if days <= 730:
        return 0.62
    return 0.42


def _authority(source_url: str) -> float:
    lower = source_url.lower()
    for marker, score in SOURCE_AUTHORITY.items():
        if marker in lower:
            return score
    return 0.72
