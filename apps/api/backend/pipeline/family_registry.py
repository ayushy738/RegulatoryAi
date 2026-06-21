from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from typing import Any
from urllib.parse import urlparse

from dateutil import parser as date_parser
from sqlalchemy import text

from backend.pipeline.intelligence_gate import extract_deadline_intelligence

AssignmentType = str

GENERIC_TITLES = {
    "",
    "home",
    "ministry of power",
    "ministry of power: home",
    "central electricity regulatory commission",
    "cercind",
    "orders",
    "notices",
    "notification",
    "recruitments",
    "solar",
    "wind",
    "solar thermal",
    "circular",
}
LISTING_PATH_MARKERS = (
    "recent_orders",
    "orders.html",
    "regulations.html",
    "current_reg",
    "monthly-updates",
    "notice-category",
    "common-table-data",
    "content/orders",
    "important-orders-guidelines-notifications-reports",
)
ORDINALS = {
    "first": 1,
    "second": 2,
    "third": 3,
    "fourth": 4,
    "fifth": 5,
    "sixth": 6,
    "seventh": 7,
    "eighth": 8,
    "ninth": 9,
    "tenth": 10,
}
DOCUMENT_TYPE_TERMS = {
    "TENDER": ("tender", "rfp", "bid"),
    "CONSULTATION": ("consultation", "comments", "suggestions", "public hearing"),
    "CORRIGENDUM": ("corrigendum",),
    "ADDENDUM": ("addendum",),
    "AMENDMENT": ("amendment",),
    "REGULATION": ("regulation", "regulations"),
    "NOTIFICATION": ("notification", "gazette"),
    "ORDER": ("order", "petition"),
    "POLICY": ("policy", "scheme", "trajectory"),
    "ACT": ("act,", " act "),
    "GUIDELINE": ("guideline", "guidelines", "procedure"),
}


@dataclass(frozen=True)
class RegistryInput:
    document_id: int
    document_version_id: int | None
    title: str
    issuer: str | None
    source_url: str
    document_type: str | None
    issue_date: date | None
    content_hash: str | None
    text_content: str | None = None
    content_length: int = 0
    first_seen_at: Any = None
    fetched_at: Any = None


@dataclass(frozen=True)
class FamilyCandidate:
    canonical_title: str | None
    document_type: str | None
    assignment_type: AssignmentType
    confidence: float
    evidence: str
    version_number: int | None = None
    version_label: str | None = None
    amendment_number: int | None = None
    amendment_label: str | None = None
    referenced_instrument: str | None = None
    referenced_notification: str | None = None
    publication_date: date | None = None
    effective_date: date | None = None
    relationship_type: str | None = None


@dataclass(frozen=True)
class RegistryResult:
    document_id: int
    family_id: int | None
    registry_version_id: int | None
    assignment_type: AssignmentType
    confidence: float
    canonical_title: str | None
    evidence: str
    deadline_count: int
    amendment_number: int | None
    relationship_type: str | None


def register_document_version_family(session: Any, item: RegistryInput) -> RegistryResult:
    candidate = derive_family_candidate(item)
    if candidate.assignment_type == "UNKNOWN_FAMILY" or not candidate.canonical_title:
        _upsert_assignment(
            session,
            document_id=item.document_id,
            family_id=None,
            assignment_type="UNKNOWN_FAMILY",
            confidence=candidate.confidence,
            evidence=candidate.evidence,
        )
        return RegistryResult(
            document_id=item.document_id,
            family_id=None,
            registry_version_id=None,
            assignment_type="UNKNOWN_FAMILY",
            confidence=candidate.confidence,
            canonical_title=candidate.canonical_title,
            evidence=candidate.evidence,
            deadline_count=0,
            amendment_number=candidate.amendment_number,
            relationship_type=candidate.relationship_type,
        )

    family_id, assignment_type, confidence = _find_or_create_family(session, item, candidate)
    _upsert_assignment(
        session,
        document_id=item.document_id,
        family_id=family_id,
        assignment_type=assignment_type,
        confidence=confidence,
        evidence=candidate.evidence,
    )
    registry_version_id = None
    deadline_count = 0
    if item.document_version_id:
        registry_version_id = _upsert_registry_version(session, item, candidate, family_id)
        deadline_count = _upsert_deadlines(session, item, family_id, registry_version_id)
        _refresh_latest_version(session, family_id)
    return RegistryResult(
        document_id=item.document_id,
        family_id=family_id,
        registry_version_id=registry_version_id,
        assignment_type=assignment_type,
        confidence=confidence,
        canonical_title=candidate.canonical_title,
        evidence=candidate.evidence,
        deadline_count=deadline_count,
        amendment_number=candidate.amendment_number,
        relationship_type=candidate.relationship_type,
    )


def derive_family_candidate(item: RegistryInput) -> FamilyCandidate:
    title = _clean(item.title)
    text = _clean(item.text_content or "")
    haystack = f"{title}\n{text[:8000]}"
    lower = haystack.lower()
    primary_text = item.content_length >= 250
    path = urlparse(item.source_url).path.lower()

    amendment = _amendment_info(haystack)
    if amendment:
        canonical, ordinal_label, ordinal, evidence = amendment
        return FamilyCandidate(
            canonical_title=canonical,
            document_type="REGULATION",
            assignment_type="NEW_FAMILY",
            confidence=0.86 if primary_text else 0.62,
            evidence=evidence,
            version_number=ordinal + 1 if ordinal else None,
            version_label=f"{ordinal_label.title()} Amendment" if ordinal_label else "Amendment",
            amendment_number=ordinal,
            amendment_label=ordinal_label.title() if ordinal_label else "Amendment",
            referenced_instrument=canonical,
            publication_date=item.issue_date or _first_date(haystack),
            relationship_type="AMENDS",
        )

    corrigendum_title = _corrigendum_title(title)
    if corrigendum_title:
        return FamilyCandidate(
            canonical_title=corrigendum_title,
            document_type=_document_type(lower),
            assignment_type="NEW_FAMILY",
            confidence=0.78 if primary_text else 0.58,
            evidence=title,
            version_label="Corrigendum",
            referenced_instrument=corrigendum_title,
            publication_date=item.issue_date or _first_date(haystack),
            relationship_type="CORRIGENDUM_TO",
        )

    if _is_index_or_catalog(title, lower):
        return FamilyCandidate(
            canonical_title=None,
            document_type=_document_type(lower),
            assignment_type="UNKNOWN_FAMILY",
            confidence=0.16,
            evidence="Index/catalog page detected, not a single regulatory instrument.",
        )

    if _is_generic_or_listing(title, path):
        return FamilyCandidate(
            canonical_title=None,
            document_type=_document_type(lower),
            assignment_type="UNKNOWN_FAMILY",
            confidence=0.18,
            evidence="Generic navigation/listing title without a resolvable instrument.",
        )

    if not primary_text and not _strong_family_signal(title.lower()):
        return FamilyCandidate(
            canonical_title=None,
            document_type=_document_type(lower),
            assignment_type="UNKNOWN_FAMILY",
            confidence=0.22,
            evidence="No primary text and no strong family signal in title.",
        )

    canonical = _canonical_title(title, haystack)
    if not canonical:
        return FamilyCandidate(
            canonical_title=None,
            document_type=_document_type(lower),
            assignment_type="UNKNOWN_FAMILY",
            confidence=0.22,
            evidence="Unable to derive stable canonical title.",
        )

    return FamilyCandidate(
        canonical_title=canonical,
        document_type=_document_type(lower),
        assignment_type="NEW_FAMILY",
        confidence=_base_confidence(primary_text, title, lower),
        evidence=_candidate_evidence(title, text),
        version_number=1,
        version_label="Original or standalone document",
        publication_date=item.issue_date or _first_date(haystack),
        effective_date=_effective_date(haystack),
    )


def _find_or_create_family(
    session: Any,
    item: RegistryInput,
    candidate: FamilyCandidate,
) -> tuple[int, AssignmentType, float]:
    exact = session.execute(
        text(
            """
            select family_id
            from document_families
            where lower(coalesce(issuer, '')) = lower(coalesce(:issuer, ''))
              and lower(canonical_title) = lower(:canonical_title)
              and lower(coalesce(document_type, '')) = lower(coalesce(:document_type, ''))
            limit 1
            """
        ),
        {
            "issuer": item.issuer,
            "canonical_title": candidate.canonical_title,
            "document_type": candidate.document_type,
        },
    ).first()
    if exact:
        return int(exact.family_id), "EXACT_FAMILY_MATCH", max(candidate.confidence, 0.94)

    likely = _find_likely_family(session, item, candidate)
    if likely:
        family_id, score = likely
        return family_id, "LIKELY_FAMILY_MATCH", max(candidate.confidence * score, 0.72)

    family = session.execute(
        text(
            """
            insert into document_families
              (canonical_title, issuer, document_type, first_seen_at)
            values
              (:canonical_title, :issuer, :document_type, coalesce(:first_seen_at, now()))
            returning family_id
            """
        ),
        {
            "canonical_title": candidate.canonical_title,
            "issuer": item.issuer,
            "document_type": candidate.document_type,
            "first_seen_at": item.first_seen_at,
        },
    ).first()
    return int(family.family_id), "NEW_FAMILY", candidate.confidence


def _find_likely_family(
    session: Any,
    item: RegistryInput,
    candidate: FamilyCandidate,
) -> tuple[int, float] | None:
    rows = session.execute(
        text(
            """
            select family_id, canonical_title
            from document_families
            where lower(coalesce(issuer, '')) = lower(coalesce(:issuer, ''))
              and lower(coalesce(document_type, '')) = lower(coalesce(:document_type, ''))
            """
        ),
        {"issuer": item.issuer, "document_type": candidate.document_type},
    ).mappings()
    best: tuple[int, float] | None = None
    for row in rows:
        score = _title_similarity(candidate.canonical_title or "", row["canonical_title"])
        if score >= 0.86 and (best is None or score > best[1]):
            best = (int(row["family_id"]), score)
    return best


def _upsert_assignment(
    session: Any,
    *,
    document_id: int,
    family_id: int | None,
    assignment_type: str,
    confidence: float,
    evidence: str,
) -> None:
    session.execute(
        text(
            """
            insert into document_family_assignments
              (document_id, family_id, assignment_type, confidence, evidence, updated_at)
            values
              (:document_id, :family_id, :assignment_type, :confidence, :evidence, now())
            on conflict (document_id) do update set
              family_id = excluded.family_id,
              assignment_type = excluded.assignment_type,
              confidence = excluded.confidence,
              evidence = excluded.evidence,
              updated_at = now()
            """
        ),
        {
            "document_id": document_id,
            "family_id": family_id,
            "assignment_type": assignment_type,
            "confidence": confidence,
            "evidence": evidence[:1200],
        },
    )


def _upsert_registry_version(
    session: Any,
    item: RegistryInput,
    candidate: FamilyCandidate,
    family_id: int,
) -> int:
    parent_id = _parent_registry_version(session, family_id, candidate)
    row = session.execute(
        text(
            """
            insert into document_version_registry
              (family_id, document_id, document_version_id, version_number, version_label,
               publication_date, issue_date, effective_date, content_hash,
               parent_registry_version_id, amendment_number, amendment_label,
               referenced_instrument, referenced_notification, updated_at)
            values
              (:family_id, :document_id, :document_version_id, :version_number, :version_label,
               :publication_date, :issue_date, :effective_date, :content_hash,
               :parent_registry_version_id, :amendment_number, :amendment_label,
               :referenced_instrument, :referenced_notification, now())
            on conflict (document_version_id) do update set
              family_id = excluded.family_id,
              version_number = excluded.version_number,
              version_label = excluded.version_label,
              publication_date = excluded.publication_date,
              issue_date = excluded.issue_date,
              effective_date = excluded.effective_date,
              content_hash = excluded.content_hash,
              parent_registry_version_id = excluded.parent_registry_version_id,
              amendment_number = excluded.amendment_number,
              amendment_label = excluded.amendment_label,
              referenced_instrument = excluded.referenced_instrument,
              referenced_notification = excluded.referenced_notification,
              updated_at = now()
            returning registry_version_id
            """
        ),
        {
            "family_id": family_id,
            "document_id": item.document_id,
            "document_version_id": item.document_version_id,
            "version_number": candidate.version_number,
            "version_label": candidate.version_label,
            "publication_date": candidate.publication_date,
            "issue_date": item.issue_date,
            "effective_date": candidate.effective_date,
            "content_hash": item.content_hash,
            "parent_registry_version_id": parent_id,
            "amendment_number": candidate.amendment_number,
            "amendment_label": candidate.amendment_label,
            "referenced_instrument": candidate.referenced_instrument,
            "referenced_notification": candidate.referenced_notification,
        },
    ).first()
    registry_version_id = int(row.registry_version_id)
    if parent_id and candidate.relationship_type:
        _upsert_relationship(
            session,
            family_id=family_id,
            from_registry_version_id=registry_version_id,
            to_registry_version_id=parent_id,
            relationship_type=candidate.relationship_type,
            confidence=candidate.confidence,
            evidence=candidate.evidence,
        )
    return registry_version_id


def _parent_registry_version(
    session: Any,
    family_id: int,
    candidate: FamilyCandidate,
) -> int | None:
    if not candidate.version_number or candidate.version_number <= 1:
        return None
    row = session.execute(
        text(
            """
            select registry_version_id
            from document_version_registry
            where family_id = :family_id
              and version_number is not null
              and version_number < :version_number
            order by version_number desc, registry_version_id desc
            limit 1
            """
        ),
        {"family_id": family_id, "version_number": candidate.version_number},
    ).first()
    return int(row.registry_version_id) if row else None


def _upsert_relationship(
    session: Any,
    *,
    family_id: int,
    from_registry_version_id: int,
    to_registry_version_id: int,
    relationship_type: str,
    confidence: float,
    evidence: str,
) -> None:
    session.execute(
        text(
            """
            insert into document_version_relationships
              (family_id, from_registry_version_id, to_registry_version_id,
               relationship_type, confidence, evidence)
            values
              (:family_id, :from_registry_version_id, :to_registry_version_id,
               :relationship_type, :confidence, :evidence)
            on conflict (from_registry_version_id, to_registry_version_id, relationship_type)
            do update set
              confidence = excluded.confidence,
              evidence = excluded.evidence
            """
        ),
        {
            "family_id": family_id,
            "from_registry_version_id": from_registry_version_id,
            "to_registry_version_id": to_registry_version_id,
            "relationship_type": relationship_type,
            "confidence": confidence,
            "evidence": evidence[:1200],
        },
    )


def _upsert_deadlines(
    session: Any,
    item: RegistryInput,
    family_id: int,
    registry_version_id: int,
) -> int:
    text_value = item.text_content or ""
    if not text_value.strip():
        return 0
    inserted = 0
    for deadline in extract_deadline_intelligence(text_value):
        session.execute(
            text(
                """
                insert into deadline_history
                  (family_id, registry_version_id, document_id, document_version_id,
                   deadline_type, deadline_date, raw_date, extracted_from, confidence)
                values
                  (:family_id, :registry_version_id, :document_id, :document_version_id,
                   :deadline_type, :deadline_date, :raw_date, :extracted_from, :confidence)
                on conflict do nothing
                """
            ),
            {
                "family_id": family_id,
                "registry_version_id": registry_version_id,
                "document_id": item.document_id,
                "document_version_id": item.document_version_id,
                "deadline_type": deadline.deadline_type,
                "deadline_date": deadline.normalized_date,
                "raw_date": deadline.raw_date,
                "extracted_from": deadline.evidence_snippet,
                "confidence": deadline.confidence,
            },
        )
        inserted += 1
    return inserted


def _refresh_latest_version(session: Any, family_id: int) -> None:
    latest = session.execute(
        text(
            """
            select document_version_id
            from document_version_registry
            where family_id = :family_id
            order by
              coalesce(publication_date, issue_date, date '0001-01-01') desc,
              coalesce(version_number, 0) desc,
              registry_version_id desc
            limit 1
            """
        ),
        {"family_id": family_id},
    ).first()
    if not latest:
        return
    session.execute(
        text(
            """
            update document_families
            set latest_version_id = :latest_version_id,
                updated_at = now()
            where family_id = :family_id
            """
        ),
        {"family_id": family_id, "latest_version_id": latest.document_version_id},
    )


def _amendment_info(value: str) -> tuple[str, str, int | None, str] | None:
    pattern = re.compile(
        r"(?P<prefix>(?:[A-Z][A-Za-z&., -]+\s+)?)"
        r"\((?P<subject>[^()]{8,180})\)\s*"
        r"\((?P<ordinal>first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth)"
        r"\s+amendment\)\s*"
        r"(?P<kind>regulations?|rules?|order|guidelines?)",
        flags=re.IGNORECASE,
    )
    match = pattern.search(value)
    if match:
        prefix = _clean(match.group("prefix"))
        subject = _clean(match.group("subject"))
        kind = _clean(match.group("kind")).title()
        ordinal_label = match.group("ordinal").lower()
        canonical = _clean(f"{prefix} {subject} {kind}")
        return canonical, ordinal_label, ORDINALS.get(ordinal_label), match.group(0)

    simple = re.search(
        r"(?P<base>[A-Z][A-Za-z0-9(),/& -]{12,220}?)\s+"
        r"\((?P<ordinal>first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth)"
        r"\s+amendment\)",
        value,
        flags=re.IGNORECASE,
    )
    if simple:
        base = _clean(simple.group("base"))
        ordinal_label = simple.group("ordinal").lower()
        return base, ordinal_label, ORDINALS.get(ordinal_label), simple.group(0)
    return None


def _corrigendum_title(title: str) -> str | None:
    lower = title.lower()
    if "corrigendum" not in lower:
        return None
    cleaned = re.sub(r"^corrigendum\s+(?:to|for)\s+", "", title, flags=re.IGNORECASE)
    cleaned = re.split(r"\border\s+dated\b", cleaned, flags=re.IGNORECASE)[0]
    cleaned = re.split(r"\|", cleaned, maxsplit=1)[0]
    return _clean(cleaned)


def _canonical_title(title: str, haystack: str) -> str | None:
    title = re.split(r"\|", title, maxsplit=1)[0]
    title = re.sub(r"\s*[-–—]\s*reg\.?$", "", title, flags=re.IGNORECASE)
    title = _clean(title)
    if title.lower() in GENERIC_TITLES or len(title) < 8:
        regulation = re.search(
            r"([A-Z][A-Za-z &,()/-]{12,220}?(?:Regulations|Rules|Guidelines|Act),?\s*\d{4})",
            haystack,
        )
        if regulation:
            return _clean(regulation.group(1))
        return None
    return title[:500]


def _document_type(value: str) -> str | None:
    lower = value.lower()
    for doc_type, terms in DOCUMENT_TYPE_TERMS.items():
        if any(term in lower for term in terms):
            return doc_type
    return None


def _base_confidence(primary_text: bool, title: str, lower: str) -> float:
    if primary_text and _strong_family_signal(lower):
        return 0.82
    if primary_text:
        return 0.72
    if _strong_family_signal(f"{title}\n{lower}"):
        return 0.56
    return 0.38


def _candidate_evidence(title: str, text: str) -> str:
    if text:
        return text[:600]
    return title


def _strong_family_signal(value: str) -> bool:
    return any(
        marker in value
        for marker in (
            "regulation",
            "rules",
            "act,",
            " act ",
            "policy",
            "rfp",
            "tender",
            "corrigendum",
            "amendment",
            "notification",
            "guideline",
            "order dated",
        )
    )


def _is_generic_or_listing(title: str, path: str) -> bool:
    lower_title = title.lower().strip()
    return (
        lower_title in GENERIC_TITLES
        or ":::" in lower_title
        or path in {"", "/", "/index.html", "/index-en.html"}
        or any(marker in path for marker in LISTING_PATH_MARKERS)
    )


def _is_index_or_catalog(title: str, lower: str) -> bool:
    title_lower = title.lower().strip()
    return (
        "rules by notification" in lower
        or "s.no. date description attachments" in lower
        or "date description attachments" in lower
        or (
            title_lower in {"notification", "notifications", "orders", "notices"}
            and lower.count("notification") >= 4
        )
    )


def _first_date(value: str) -> date | None:
    match = re.search(
        r"\b(?:\d{1,2}[-/.]\d{1,2}[-/.]\d{2,4}|\d{4}[-/.]\d{1,2}[-/.]\d{1,2})\b",
        value,
    )
    if not match:
        return None
    try:
        return date_parser.parse(match.group(0), dayfirst=True, fuzzy=True).date()
    except (ValueError, OverflowError):
        return None


def _effective_date(value: str) -> date | None:
    match = re.search(
        r"(?:effective|come into force|implementation)[^.:\n]{0,80}"
        r"(\d{1,2}[-/.]\d{1,2}[-/.]\d{2,4})",
        value,
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    try:
        return date_parser.parse(match.group(1), dayfirst=True, fuzzy=True).date()
    except (ValueError, OverflowError):
        return None


def _title_similarity(left: str, right: str) -> float:
    left_tokens = _token_set(left)
    right_tokens = _token_set(right)
    if not left_tokens or not right_tokens:
        return 0.0
    overlap = len(left_tokens & right_tokens) / len(left_tokens | right_tokens)
    length_ratio = min(len(left), len(right)) / max(len(left), len(right), 1)
    return (overlap * 0.75) + (length_ratio * 0.25)


def _token_set(value: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9]+", value.lower())
        if token
        not in {
            "the",
            "and",
            "of",
            "for",
            "to",
            "in",
            "reg",
            "draft",
            "final",
            "notification",
        }
    }


def _clean(value: str | None) -> str:
    return re.sub(r"\s+", " ", value or "").strip()
