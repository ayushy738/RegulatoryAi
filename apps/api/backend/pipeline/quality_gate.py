from __future__ import annotations

import re
from urllib.parse import urlparse

from backend.core.models import CandidateQuality, DiscoveredDoc

VALID_CLASSIFICATIONS = {
    "REGULATORY_DOCUMENT",
    "TENDER_DOCUMENT",
    "CONSULTATION_DOCUMENT",
    "ORDER",
    "NOTIFICATION",
    "CIRCULAR",
    "POLICY_UPDATE",
    "GUIDELINE",
    "AMENDMENT",
}

DISCOVERY_CLASSIFICATIONS = {
    "HOMEPAGE",
    "LISTING_PAGE",
    "ARCHIVE_PAGE",
    "CATEGORY_PAGE",
    "SEARCH_PAGE",
    "NAVIGATION_PAGE",
}

GENERIC_TITLES = {
    "",
    "home",
    "homepage",
    "ministry of power",
    "ministry of power: home",
    "central electricity regulatory commission",
    "cercind",
    "orders",
    "order",
    "notices",
    "notice",
    "circular",
    "circulars",
    "recruitments",
    "recruitment",
    "solar",
    "wind",
    "solar thermal",
}

LISTING_PATH_PATTERNS = (
    r"/recent[_-]?orders",
    r"/orders\.html$",
    r"/orders/?$",
    r"/regulations\.html",
    r"/current[_-]?reg",
    r"/monthly-updates/?$",
    r"/notice-category/",
    r"/content/orders/?$",
    r"/content/important-orders-guidelines-notifications-reports/?$",
)

ARCHIVE_TERMS = ("archive", "archives", "old-orders", "previous")
SEARCH_TERMS = ("search", "query", "keyword", "common-table-data")
NAVIGATION_TERMS = ("career", "recruitment", "about", "contact", "sitemap", "login")

CONSULTATION_TERMS = ("consultation", "comments", "suggestions", "public hearing")
TENDER_TERMS = ("tender", "rfp", "bid", "auction", "eoi")
AMENDMENT_TERMS = ("amendment", "corrigendum", "addendum")
ORDER_TERMS = ("order", "petition", "suo motu")
NOTIFICATION_TERMS = ("notification", "gazette")
CIRCULAR_TERMS = ("circular", "office memorandum")
POLICY_TERMS = ("policy", "scheme", "trajectory")
GUIDELINE_TERMS = ("guideline", "procedure", "framework", "manual")
REGULATORY_TERMS = (
    "regulation",
    "regulatory",
    "rules",
    "tariff",
    "open access",
    "rpo",
    "rec",
    "renewable purchase obligation",
    "deviation settlement",
    "power market",
    "connectivity",
    "transmission",
)


def classify_candidate(
    candidate: DiscoveredDoc,
    *,
    content_text: str | None = None,
) -> CandidateQuality:
    """Classify a discovered URL before it is allowed to become an event."""

    parsed = urlparse(candidate.source_url)
    path = parsed.path.lower().rstrip("/")
    query = parsed.query.lower()
    title = _normalize(candidate.title)
    summary = _normalize(candidate.raw_summary or "")
    content = _normalize(content_text or "")
    haystack = " ".join(part for part in [title, path, query, summary, content[:5000]] if part)

    if _is_standalone_cerc_electricity_act_nav_pdf(path, title):
        return _quality(
            "NAVIGATION_PAGE",
            False,
            0.99,
            "NAVIGATION_PAGE_DETECTED",
            "Standalone CERC Electricity Act navigation PDF, not a current petition row.",
        )
    if _is_homepage(path, title):
        return _quality("HOMEPAGE", False, 0.97, "HOMEPAGE_DETECTED", "Root/index page.")
    if any(term in path or term in query for term in SEARCH_TERMS):
        return _quality(
            "SEARCH_PAGE",
            False,
            0.92,
            "SEARCH_PAGE_DETECTED",
            "Search/table endpoint.",
        )
    if any(term in path for term in ARCHIVE_TERMS):
        return _quality("ARCHIVE_PAGE", False, 0.9, "ARCHIVE_PAGE_DETECTED", "Archive page.")
    if any(re.search(pattern, path) for pattern in LISTING_PATH_PATTERNS):
        return _quality("LISTING_PAGE", False, 0.94, "LISTING_PAGE_DETECTED", "Listing page.")
    if _is_category_page(path, title):
        return _quality("CATEGORY_PAGE", False, 0.93, "CATEGORY_PAGE_DETECTED", "Category page.")
    if _is_navigation_page(path, title, haystack):
        return _quality(
            "NAVIGATION_PAGE",
            False,
            0.88,
            "NAVIGATION_PAGE_DETECTED",
            "Navigation or non-regulatory page.",
        )

    if _has_any(haystack, TENDER_TERMS):
        return _quality("TENDER_DOCUMENT", True, 0.86, "VALID_PRIMARY_DOCUMENT", "Tender terms.")
    if _has_any(haystack, CONSULTATION_TERMS):
        return _quality(
            "CONSULTATION_DOCUMENT",
            True,
            0.86,
            "VALID_PRIMARY_DOCUMENT",
            "Consultation terms.",
        )
    if _has_any(haystack, AMENDMENT_TERMS):
        return _quality("AMENDMENT", True, 0.88, "VALID_PRIMARY_DOCUMENT", "Amendment terms.")
    if _has_any(haystack, NOTIFICATION_TERMS):
        return _quality("NOTIFICATION", True, 0.84, "VALID_PRIMARY_DOCUMENT", "Notification terms.")
    if _has_any(haystack, CIRCULAR_TERMS):
        return _quality("CIRCULAR", True, 0.82, "VALID_PRIMARY_DOCUMENT", "Circular terms.")
    if _has_any(haystack, ORDER_TERMS):
        return _quality("ORDER", True, 0.82, "VALID_PRIMARY_DOCUMENT", "Order terms.")
    if _has_any(haystack, POLICY_TERMS):
        return _quality("POLICY_UPDATE", True, 0.78, "VALID_PRIMARY_DOCUMENT", "Policy terms.")
    if _has_any(haystack, GUIDELINE_TERMS):
        return _quality("GUIDELINE", True, 0.78, "VALID_PRIMARY_DOCUMENT", "Guideline terms.")
    if path.endswith(".pdf") and _has_any(haystack, REGULATORY_TERMS):
        return _quality(
            "REGULATORY_DOCUMENT",
            True,
            0.8,
            "VALID_PRIMARY_DOCUMENT",
            "PDF with regulatory terms.",
        )

    if path.endswith(".pdf"):
        return _quality(
            "REGULATORY_DOCUMENT",
            True,
            0.62,
            "LOW_CONFIDENCE_PRIMARY_DOCUMENT",
            "PDF without strong regulatory terms.",
        )

    return _quality(
        "NAVIGATION_PAGE",
        False,
        0.62,
        "NO_PRIMARY_DOCUMENT",
        "No strong regulatory primary-document signal.",
    )


def is_valid_classification(classification: str) -> bool:
    return classification in VALID_CLASSIFICATIONS


def _quality(
    classification: str,
    valid: bool,
    confidence: float,
    reason: str,
    explanation: str,
) -> CandidateQuality:
    return CandidateQuality(
        classification=classification,  # type: ignore[arg-type]
        is_valid_event_source=valid,
        confidence=confidence,
        reason_code=reason,
        explanation=explanation,
    )


def _normalize(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip().lower()


def _is_homepage(path: str, title: str) -> bool:
    return path in {"", "/", "/index-en.html", "/index.html"} or title in {
        "home",
        "homepage",
        "ministry of power: home",
    }


def _is_standalone_cerc_electricity_act_nav_pdf(path: str, title: str) -> bool:
    return path.endswith("/act-with-amendment.pdf") and title == "electricity act 2003"


def _is_category_page(path: str, title: str) -> bool:
    return (
        "/category/" in path
        or "/notice-category/" in path
        or title in {"solar", "wind", "solar thermal", "recruitments", "notices"}
    )


def _is_navigation_page(path: str, title: str, haystack: str) -> bool:
    if title in GENERIC_TITLES and not path.endswith(".pdf"):
        return True
    if any(term in path for term in NAVIGATION_TERMS):
        return True
    boilerplate = ("best viewed", "hosted by national informatics centre", "stqc certification")
    return _has_any(haystack, boilerplate) and not _has_any(
        haystack,
        REGULATORY_TERMS
        + AMENDMENT_TERMS
        + CONSULTATION_TERMS
        + TENDER_TERMS
        + NOTIFICATION_TERMS,
    )


def _has_any(value: str, terms: tuple[str, ...]) -> bool:
    return any(term in value for term in terms)
