from __future__ import annotations

import re
from datetime import date
from urllib.parse import urlparse

from dateutil import parser as date_parser

from backend.core.models import (
    DeadlineIntelligence,
    EventIntelligence,
    ExtractedDoc,
    SummaryPayload,
)

QUALITY_THRESHOLD = 65
CURRENT_DAYS = 45
RECENT_DAYS = 180

GENERIC_TITLES = {
    "",
    "home",
    "orders",
    "order",
    "notification",
    "notifications",
    "rules by notification",
    "circular",
    "circulars",
    "central electricity regulatory commission",
    "ministry of power",
    "cercind",
}

INDEX_TITLE_TERMS = (
    "rules by notification",
    "orders archive",
    "circular list",
    "notification list",
    "order list",
    "document archive",
    "existing regulations",
    "archive",
)
INDEX_TEXT_PATTERNS = (
    r"s\.?\s*no\.?\s+date\s+description\s+attachments?",
    r"date\s+subject\s+download",
    r"order\s+date\s+case\s+number",
    r"notification\s+\d+\s+\d{1,2}[-/.]\d{1,2}[-/.]\d{2,4}",
)

DATE_PATTERNS = (
    r"\b\d{1,2}[-/.]\d{1,2}[-/.]\d{2,4}\b",
    r"\b\d{4}[-/.]\d{1,2}[-/.]\d{1,2}\b",
    r"\b\d{1,2}(?:st|nd|rd|th)?\s+"
    r"(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|"
    r"jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|"
    r"nov(?:ember)?|dec(?:ember)?)\s+\d{4}\b",
    r"\b(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|"
    r"jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|"
    r"nov(?:ember)?|dec(?:ember)?)\s+\d{1,2},?\s+\d{4}\b",
)

CONSULTATION_TERMS = ("comment", "comments", "suggestion", "objection", "consultation")
HEARING_TERMS = ("hearing", "public hearing")
TENDER_TERMS = ("bid", "bidding", "tender", "rfp", "auction", "submission")
COMPLIANCE_TERMS = ("comply", "compliance", "obligation", "shall submit", "required to")
IMPLEMENTATION_TERMS = ("effective", "implemented", "implementation", "come into force")
PUBLICATION_TERMS = ("dated", "published", "gazette", "notification", "issued")
MONETARY_TERMS = ("rs.", "inr", "crore", "lakh", "tariff", "charges", "fee", "payment")
SECTOR_TERMS = (
    "solar",
    "wind",
    "renewable",
    "transmission",
    "distribution",
    "open access",
    "rpo",
    "rec",
    "storage",
    "thermal",
    "tariff",
)
AFFECTED_PATTERNS = {
    "generators": ("generator", "generating company", "developer"),
    "distribution licensees": ("distribution licensee", "discom"),
    "transmission licensees": ("transmission licensee", "transmission service provider"),
    "renewable developers": ("solar", "wind", "renewable", "developer"),
    "consumers": ("consumer", "open access consumer"),
    "bidders": ("bidder", "tender", "rfp"),
}


def assess_event_intelligence(
    extracted: ExtractedDoc,
    *,
    topics: list[str] | None = None,
    summary: SummaryPayload | None = None,
    today: date | None = None,
) -> EventIntelligence:
    """Decide whether an extracted primary document deserves a user-facing event."""

    today = today or date.today()
    discovered = extracted.fetched.discovered
    title = _clean(discovered.title)
    text = _clean(extracted.text)
    classification = extracted.classification or "REGULATORY_DOCUMENT"
    deadlines = extract_deadline_intelligence(text, today=today)
    is_index = _is_index_document(title, text, discovered.doc_type)
    freshness, freshness_reason = _classify_freshness(
        extracted,
        deadlines,
        is_index_document=is_index,
        today=today,
    )
    affected = _affected_parties(text, topics or [])
    significance_score, significance_category, significance_reasons = _score_significance(
        classification,
        text,
        deadlines,
        topics or [],
        today,
    )
    actionability, required_action, action_deadline = _classify_actionability(
        classification,
        freshness,
        deadlines,
        today,
    )
    title_quality = _title_quality(title)
    document_quality = _document_quality(extracted, is_index)
    date_confidence = _date_confidence(extracted, deadlines)
    quality_score = _quality_score(
        freshness,
        significance_score,
        actionability,
        title_quality,
        document_quality,
        date_confidence,
    )
    quality_category = _quality_category(quality_score)
    reasons = [freshness_reason, *significance_reasons]
    rejection_reason = _rejection_reason(
        classification,
        is_index,
        freshness,
        actionability,
        deadlines,
        quality_score,
        today,
    )
    return EventIntelligence(
        event_allowed=rejection_reason is None,
        rejection_reason=rejection_reason,
        freshness=freshness,
        freshness_reason=freshness_reason,
        is_index_document=is_index,
        significance_score=significance_score,
        significance_category=significance_category,
        actionability=actionability,
        affected_parties=affected,
        required_action=required_action,
        action_deadline=action_deadline,
        consequence_if_ignored=_consequence(text),
        deadlines=deadlines,
        title_quality_score=title_quality,
        document_quality_score=document_quality,
        date_confidence_score=date_confidence,
        quality_score=quality_score,
        quality_category=quality_category,
        reasons=reasons,
    )


def extract_deadline_intelligence(
    text: str,
    *,
    today: date | None = None,
) -> list[DeadlineIntelligence]:
    today = today or date.today()
    del today
    cleaned = _clean(text)
    results: list[DeadlineIntelligence] = []
    seen: set[tuple[str, str]] = set()
    for pattern in DATE_PATTERNS:
        for match in re.finditer(pattern, cleaned, flags=re.IGNORECASE):
            raw = match.group(0)
            start = max(match.start() - 110, 0)
            end = min(match.end() + 110, len(cleaned))
            evidence = cleaned[start:end].strip()
            parsed = _parse_date(raw)
            deadline_type, confidence = _deadline_type(evidence)
            key = (raw.lower(), deadline_type)
            if key in seen:
                continue
            seen.add(key)
            results.append(
                DeadlineIntelligence(
                    raw_date=raw,
                    normalized_date=parsed,
                    deadline_type=deadline_type,
                    confidence=confidence,
                    evidence_snippet=evidence[:350],
                )
            )
            if len(results) >= 30:
                return results
    return results


def attach_intelligence_to_summary(
    summary: SummaryPayload,
    intelligence: EventIntelligence,
) -> SummaryPayload:
    important_dates = [
        item.raw_date
        for item in intelligence.deadlines
        if item.deadline_type != "UNKNOWN_DATE"
    ][:8]
    return summary.model_copy(
        update={
            "important_dates": important_dates or summary.important_dates,
            "action_required": "urgent"
            if intelligence.actionability == "ACTIONABLE"
            else ("monitor" if intelligence.actionability == "INFORMATIONAL" else "none"),
            "confidence": "high"
            if intelligence.quality_score >= 80
            else ("medium" if intelligence.quality_score >= 55 else "low"),
            "deadline_details": [
                item.model_dump(mode="json")
                for item in intelligence.deadlines[:12]
            ],
            "intelligence": intelligence.model_dump(mode="json", exclude={"deadlines"}),
        }
    )


def _classify_freshness(
    extracted: ExtractedDoc,
    deadlines: list[DeadlineIntelligence],
    *,
    is_index_document: bool,
    today: date,
) -> tuple[str, str]:
    if is_index_document:
        return "ARCHIVAL", "INDEX_OR_COMPILATION_DOCUMENT"

    active_dates = [
        item.normalized_date
        for item in deadlines
        if item.normalized_date
        and item.deadline_type
        in {
            "CONSULTATION_DEADLINE",
            "HEARING_DATE",
            "TENDER_SUBMISSION_DEADLINE",
            "COMPLIANCE_DEADLINE",
        }
        and item.normalized_date >= today
    ]
    if active_dates:
        return "CURRENT", "ACTIVE_DEADLINE_OR_OPPORTUNITY"

    activity_date = _activity_date(extracted, deadlines)
    if not activity_date:
        return "HISTORICAL", "NO_RELIABLE_PUBLICATION_DATE"
    age_days = (today - activity_date).days
    if age_days < 0:
        return "CURRENT", "FUTURE_DATED_REGULATORY_ACTIVITY"
    if age_days <= CURRENT_DAYS:
        return "CURRENT", "CURRENT_REGULATORY_ACTIVITY"
    if age_days <= RECENT_DAYS:
        return "RECENT", "RECENT_REGULATORY_ACTIVITY"
    return "HISTORICAL", "HISTORICAL_DOCUMENT"


def _activity_date(
    extracted: ExtractedDoc,
    deadlines: list[DeadlineIntelligence],
) -> date | None:
    discovered = extracted.fetched.discovered
    candidates: list[date] = []
    if discovered.issue_date:
        candidates.append(discovered.issue_date)
    url_date = _date_from_url(discovered.source_url)
    if url_date:
        candidates.append(url_date)
    candidates.extend(
        item.normalized_date
        for item in deadlines
        if item.normalized_date
        and item.deadline_type in {"PUBLICATION_DATE", "IMPLEMENTATION_DATE"}
    )
    if not candidates:
        return None
    return max(candidates)


def _is_index_document(title: str, text: str, doc_type: str | None) -> bool:
    lower_title = title.lower()
    lower_text = text[:12000].lower()
    if any(term in lower_title for term in INDEX_TITLE_TERMS):
        return True
    if doc_type == "html":
        if any(re.search(pattern, lower_text) for pattern in INDEX_TEXT_PATTERNS):
            return True
        date_rows = len(re.findall(r"\b\d{1,2}[-/.]\d{1,2}[-/.]\d{2,4}\b", lower_text))
        repeated_downloads = lower_text.count("download") + lower_text.count("attachment")
        repeated_notifications = lower_text.count("notification")
        if date_rows >= 8 and (repeated_downloads >= 3 or repeated_notifications >= 6):
            return True
    return False


def _score_significance(
    classification: str,
    text: str,
    deadlines: list[DeadlineIntelligence],
    topics: list[str],
    today: date,
) -> tuple[int, str, list[str]]:
    lower = text.lower()
    score = {
        "CONSULTATION_DOCUMENT": 35,
        "TENDER_DOCUMENT": 35,
        "AMENDMENT": 32,
        "POLICY_UPDATE": 28,
        "ORDER": 24,
        "NOTIFICATION": 22,
        "CIRCULAR": 20,
        "GUIDELINE": 20,
        "REGULATORY_DOCUMENT": 16,
    }.get(classification, 10)
    reasons = [f"base:{classification}"]
    if any(term in lower for term in ("amendment", "corrigendum", "substituted")):
        score += 15
        reasons.append("amendment_detected")
    if any(term in lower for term in ("draft", "consultation", "comments", "suggestions")):
        score += 18
        reasons.append("consultation_or_public_comment")
    if any(term in lower for term in ("shall", "must", "required to", "compliance")):
        score += 16
        reasons.append("compliance_language")
    if any(term in lower for term in TENDER_TERMS):
        score += 15
        reasons.append("tender_or_procurement")
    if any(term in lower for term in MONETARY_TERMS):
        score += 10
        reasons.append("monetary_or_tariff_impact")
    if any(term in lower for term in IMPLEMENTATION_TERMS):
        score += 8
        reasons.append("implementation_date_signal")
    if topics:
        score += min(12, len(set(topics)) * 3)
        reasons.append("sector_impact")
    action_dates = [
        item.normalized_date
        for item in deadlines
        if item.normalized_date and item.normalized_date >= today
        and item.deadline_type != "PUBLICATION_DATE"
    ]
    if action_dates:
        score += 15
        reasons.append("active_deadline")
    score = min(score, 100)
    if score >= 80:
        category = "CRITICAL"
    elif score >= 60:
        category = "HIGH"
    elif score >= 35:
        category = "MEDIUM"
    else:
        category = "LOW"
    return score, category, reasons


def _classify_actionability(
    classification: str,
    freshness: str,
    deadlines: list[DeadlineIntelligence],
    today: date,
) -> tuple[str, str | None, str | None]:
    if freshness in {"HISTORICAL", "ARCHIVAL"}:
        return "REFERENCE_ONLY", None, None
    actionable = [
        item
        for item in deadlines
        if item.normalized_date
        and item.normalized_date >= today
        and item.deadline_type
        in {
            "CONSULTATION_DEADLINE",
            "HEARING_DATE",
            "TENDER_SUBMISSION_DEADLINE",
            "COMPLIANCE_DEADLINE",
        }
    ]
    if actionable:
        chosen = min(actionable, key=lambda item: item.normalized_date or today)
        return "ACTIONABLE", _required_action(chosen.deadline_type), chosen.raw_date
    if classification in {"CONSULTATION_DOCUMENT", "TENDER_DOCUMENT"}:
        return (
            "INFORMATIONAL",
            "Review opportunity status and confirm whether the window is active",
            None,
        )
    return "INFORMATIONAL", None, None


def _deadline_type(evidence: str) -> tuple[str, float]:
    lower = evidence.lower()
    if any(term in lower for term in CONSULTATION_TERMS):
        return "CONSULTATION_DEADLINE", 0.88
    if any(term in lower for term in HEARING_TERMS):
        return "HEARING_DATE", 0.86
    if any(term in lower for term in TENDER_TERMS):
        return "TENDER_SUBMISSION_DEADLINE", 0.84
    if any(term in lower for term in COMPLIANCE_TERMS):
        return "COMPLIANCE_DEADLINE", 0.78
    if any(term in lower for term in IMPLEMENTATION_TERMS):
        return "IMPLEMENTATION_DATE", 0.72
    if any(term in lower for term in PUBLICATION_TERMS):
        return "PUBLICATION_DATE", 0.68
    return "UNKNOWN_DATE", 0.35


def _required_action(deadline_type: str) -> str:
    if deadline_type == "CONSULTATION_DEADLINE":
        return "Submit comments or objections before the deadline"
    if deadline_type == "HEARING_DATE":
        return "Track or attend the hearing"
    if deadline_type == "TENDER_SUBMISSION_DEADLINE":
        return "Submit bid or tender response before the deadline"
    if deadline_type == "COMPLIANCE_DEADLINE":
        return "Complete required compliance action before the deadline"
    return "Review the dated regulatory action"


def _quality_score(
    freshness: str,
    significance_score: int,
    actionability: str,
    title_quality: int,
    document_quality: int,
    date_confidence: int,
) -> int:
    freshness_points = {
        "CURRENT": 30,
        "RECENT": 22,
        "HISTORICAL": 0,
        "ARCHIVAL": 0,
    }[freshness]
    action_points = {
        "ACTIONABLE": 20,
        "INFORMATIONAL": 10,
        "REFERENCE_ONLY": 0,
    }[actionability]
    return min(
        100,
        freshness_points
        + round(significance_score * 0.25)
        + action_points
        + title_quality
        + document_quality
        + date_confidence,
    )


def _quality_category(score: int) -> str:
    if score < 55:
        return "REJECT"
    if score < 70:
        return "WEAK"
    if score < 85:
        return "GOOD"
    return "EXCELLENT"


def _rejection_reason(
    classification: str,
    is_index: bool,
    freshness: str,
    actionability: str,
    deadlines: list[DeadlineIntelligence],
    quality_score: int,
    today: date,
) -> str | None:
    if is_index:
        return "INDEX_PAGE_DETECTED"
    if freshness == "ARCHIVAL":
        return "ARCHIVAL_REFERENCE"
    if freshness == "HISTORICAL":
        return "HISTORICAL_DOCUMENT"
    if classification in {"TENDER_DOCUMENT", "CONSULTATION_DOCUMENT"}:
        action_deadlines = [
            item.normalized_date
            for item in deadlines
            if item.normalized_date
            and item.deadline_type
            in {"TENDER_SUBMISSION_DEADLINE", "CONSULTATION_DEADLINE"}
        ]
        if action_deadlines and max(action_deadlines) < today:
            return "EXPIRED_OPPORTUNITY"
    if actionability == "REFERENCE_ONLY":
        return "REFERENCE_ONLY_DOCUMENT"
    if quality_score < QUALITY_THRESHOLD:
        return "LOW_EVENT_QUALITY"
    return None


def _title_quality(title: str) -> int:
    lower = title.lower()
    if lower in GENERIC_TITLES:
        return 2
    if len(title) < 16:
        return 4
    if len(title) > 220:
        return 5
    score = 7
    if any(term in lower for term in ("amendment", "order", "notification", "tender", "rfp")):
        score += 1
    if any(term in lower for term in SECTOR_TERMS):
        score += 1
    return min(score, 10)


def _document_quality(extracted: ExtractedDoc, is_index: bool) -> int:
    length = len(extracted.text.strip())
    if length < 250:
        return 0
    if is_index:
        return 4
    if length < 750:
        return 5
    if length < 2000:
        return 7
    score = 8
    if extracted.fetched.discovered.doc_type == "pdf":
        score += 1
    if extracted.page_count and extracted.page_count > 1:
        score += 1
    return min(score, 10)


def _date_confidence(extracted: ExtractedDoc, deadlines: list[DeadlineIntelligence]) -> int:
    best = max((item.confidence for item in deadlines), default=0)
    if extracted.fetched.discovered.issue_date:
        best = max(best, 0.7)
    if _date_from_url(extracted.fetched.discovered.source_url):
        best = max(best, 0.55)
    return round(best * 10)


def _affected_parties(text: str, topics: list[str]) -> list[str]:
    lower = text.lower()
    parties = [
        label
        for label, terms in AFFECTED_PATTERNS.items()
        if any(term in lower for term in terms)
    ]
    for topic in topics:
        if topic not in {"general"} and topic not in parties:
            parties.append(topic)
    return parties[:8]


def _consequence(text: str) -> str | None:
    lower = text.lower()
    for marker in ("penalty", "liable", "non-compliance", "failure to comply"):
        index = lower.find(marker)
        if index >= 0:
            return text[max(index - 80, 0): index + 180].strip()
    return None


def _date_from_url(url: str) -> date | None:
    path = urlparse(url).path
    match = re.search(r"/(20\d{2})/(\d{1,2})(?:/(\d{1,2}))?/", path)
    if not match:
        return None
    year = int(match.group(1))
    month = int(match.group(2))
    day = int(match.group(3) or 1)
    try:
        return date(year, month, day)
    except ValueError:
        return None


def _parse_date(raw: str) -> date | None:
    try:
        return date_parser.parse(raw, dayfirst=True, fuzzy=True).date()
    except (ValueError, OverflowError):
        return None


def _clean(value: str | None) -> str:
    return re.sub(r"\s+", " ", value or "").strip()
