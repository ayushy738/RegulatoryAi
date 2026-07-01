from __future__ import annotations

import re

from backend.rag.models import Intent, IntentName, RetrievalSource

INTENT_RULES: list[tuple[IntentName, tuple[str, ...], tuple[RetrievalSource, ...]]] = [
    (
        "deadline",
        ("deadline", "due date", "last date", "hearing date", "timeline"),
        ("graph", "keyword", "vector"),
    ),
    (
        "stakeholder",
        ("who is affected", "stakeholder", "affected party", "impact on"),
        ("graph", "keyword", "vector"),
    ),
    (
        "obligation",
        ("obligation", "comply", "compliance", "shall", "must", "required"),
        ("graph", "keyword", "vector"),
    ),
    (
        "consultation",
        ("consultation", "comments", "public hearing", "feedback"),
        ("graph", "keyword", "summary", "vector"),
    ),
    ("tender", ("tender", "rfs", "rfp", "bid", "procurement"), ("keyword", "vector", "graph")),
    (
        "amendment",
        ("amendment", "amended", "change", "changed", "corrigendum"),
        ("version", "family", "graph", "keyword"),
    ),
    (
        "comparison",
        ("compare", "difference", "versus", "vs", "before and after"),
        ("version", "family", "vector", "keyword"),
    ),
    (
        "summary",
        ("summarize", "summary", "explain", "what is"),
        ("summary", "vector", "keyword", "graph"),
    ),
    (
        "regulation_lookup",
        ("regulation", "rules", "act", "notification", "order"),
        ("keyword", "graph", "vector", "family"),
    ),
    (
        "semantic_search",
        ("find", "search", "show me", "related to"),
        ("vector", "keyword", "graph"),
    ),
]


def detect_intent(query: str) -> Intent:
    normalized = _normalize(query)
    for intent, markers, sources in INTENT_RULES:
        if any(marker in normalized for marker in markers):
            return Intent(name=intent, query=query, confidence=0.82, dominant_sources=sources)
    return Intent(
        name="general",
        query=query,
        confidence=0.55,
        dominant_sources=("vector", "keyword", "graph", "summary"),
    )


def _normalize(value: str) -> str:
    return re.sub(r"\s+", " ", value.lower()).strip()
