from __future__ import annotations

import re
from difflib import SequenceMatcher

from backend.core.models import (
    DeadlineChange,
    DeadlineIntelligence,
    ExtractedDoc,
    PriorVersionReference,
    RegulatoryChange,
    SummaryPayload,
)
from backend.pipeline.intelligence_gate import extract_deadline_intelligence

MATERIAL_SIMILARITY_THRESHOLD = 0.985
RELATED_TITLE_THRESHOLD = 0.72

AMENDMENT_TERMS = ("amendment", "amended", "substituted", "inserted", "omitted")
CORRIGENDUM_TERMS = ("corrigendum", "correction", "errata")
ADDENDUM_TERMS = ("addendum", "additional clause", "supplement")
WITHDRAWAL_TERMS = ("withdrawn", "withdrawal", "cancelled", "canceled", "rescinded")
REISSUE_TERMS = ("re-issued", "reissued", "supersedes", "superseded", "replacement")
TENDER_TERMS = ("tender", "rfp", "bid", "bidding", "qualification criteria", "scope of work")
CONSULTATION_TERMS = ("consultation", "comments", "suggestions", "public hearing", "objections")
POLICY_TERMS = ("policy", "scheme", "trajectory", "guidelines")
MATERIAL_TERMS = (
    "deadline",
    "last date",
    "extended",
    "revised",
    "amended",
    "eligibility",
    "qualification",
    "tariff",
    "charges",
    "bid",
    "compliance",
    "shall",
    "must",
    "obligation",
    "withdrawn",
    "supersedes",
    "effective from",
)
AFFECTED_PATTERNS = {
    "transmission developers": ("transmission service provider", "transmission developer"),
    "renewable developers": ("solar", "wind", "renewable", "developer"),
    "bidders": ("bidder", "bid", "rfp", "tender"),
    "distribution licensees": ("distribution licensee", "discom"),
    "generators": ("generating station", "generator"),
    "open access consumers": ("open access consumer", "open access"),
}


def detect_regulatory_change(
    extracted: ExtractedDoc,
    *,
    prior: PriorVersionReference | None = None,
) -> RegulatoryChange:
    current_text = _normalize(extracted.text)
    current_title = _clean(extracted.fetched.discovered.title)
    prior = prior if prior and prior.reference_type != "none" else None

    if prior and prior.content_hash == extracted.content_hash:
        return _change(
            "NO_MATERIAL_CHANGE",
            False,
            0.99,
            "Content hash matches prior version.",
            extracted,
            prior=prior,
            previous_state="Known content hash already stored.",
            new_state="Rediscovered content is unchanged.",
            reasons=["exact_content_hash_match"],
        )

    prior_text = _normalize(prior.text or "") if prior else ""
    similarity = _content_similarity(current_text, prior_text) if prior_text else None
    deadline_changes = _deadline_changes(prior_text, current_text) if prior_text else []
    if deadline_changes:
        primary = _best_deadline_change(deadline_changes)
        return _change(
            "DEADLINE_CHANGE",
            True,
            max(primary.confidence, 0.86),
            primary.evidence,
            extracted,
            prior=prior,
            previous_state=_format_date(primary.old_date),
            new_state=_format_date(primary.new_date),
            deadline_changes=deadline_changes,
            similarity=similarity,
            reasons=[f"deadline_{primary.change.lower()}"],
        )

    signal_change = _signal_change_type(current_title, current_text)
    if signal_change:
        return _change(
            signal_change,
            True,
            _signal_confidence(signal_change, similarity),
            _evidence_for_change(signal_change, current_text),
            extracted,
            prior=prior,
            previous_state=_prior_state(prior),
            new_state=_new_state(signal_change, current_text),
            similarity=similarity,
            reasons=[f"{signal_change.lower()}_signal"],
        )

    if prior_text:
        if similarity is not None and similarity >= MATERIAL_SIMILARITY_THRESHOLD:
            return _change(
                "NO_MATERIAL_CHANGE",
                False,
                0.93,
                "Text is substantially identical to the prior version.",
                extracted,
                prior=prior,
                previous_state="Prior version text is materially the same.",
                new_state="Current version has no detected material regulatory change.",
                similarity=similarity,
                reasons=["high_text_similarity", "no_material_terms"],
            )
        if _has_any(current_text, MATERIAL_TERMS):
            return _change(
                "UPDATED_DOCUMENT",
                True,
                0.72,
                _evidence_for_terms(current_text, MATERIAL_TERMS),
                extracted,
                prior=prior,
                previous_state=_prior_state(prior),
                new_state="Document text changed with material regulatory terms present.",
                similarity=similarity,
                reasons=["text_changed", "material_terms_present"],
            )
        return _change(
            "NO_MATERIAL_CHANGE",
            False,
            0.68,
            "Text changed, but no material regulatory-change signals were detected.",
            extracted,
            prior=prior,
            previous_state="Prior text differs from current text.",
            new_state="No deadline, obligation, tariff, tender, consultation, or amendment signal.",
            similarity=similarity,
            reasons=["text_changed_without_material_signal"],
        )

    if _has_any(current_text, MATERIAL_TERMS) or extracted.classification in {
        "TENDER_DOCUMENT",
        "CONSULTATION_DOCUMENT",
        "AMENDMENT",
        "POLICY_UPDATE",
        "ORDER",
        "NOTIFICATION",
        "CIRCULAR",
    }:
        change_type = signal_change or "NEW_DOCUMENT"
        return _change(
            change_type,
            True,
            0.76 if change_type == "NEW_DOCUMENT" else 0.82,
            _evidence_for_terms(current_text, MATERIAL_TERMS) or _first_evidence(current_text),
            extracted,
            prior=None,
            previous_state="No prior version or related document found.",
            new_state=f"New primary document classified as {extracted.classification}.",
            reasons=["new_primary_document", "material_signal_present"],
        )

    return _change(
        "NO_MATERIAL_CHANGE",
        False,
        0.55,
        "No prior version and no material regulatory-change signal detected.",
        extracted,
        prior=None,
        previous_state="No prior version or related document found.",
        new_state="Document does not contain enough material-change evidence.",
        reasons=["new_document_without_material_signal"],
    )


def title_similarity(left: str, right: str) -> float:
    return SequenceMatcher(None, _title_key(left), _title_key(right)).ratio()


def is_related_title(left: str, right: str) -> bool:
    return title_similarity(left, right) >= RELATED_TITLE_THRESHOLD


def attach_change_to_summary(
    summary: SummaryPayload,
    change: RegulatoryChange,
) -> SummaryPayload:
    if change.change_type == "DEADLINE_CHANGE":
        plain = (
            f"What changed: {change.evidence} Previous: {change.previous_state or 'unknown'}. "
            f"New: {change.new_state or 'unknown'}."
        )
    elif change.change_type == "NEW_DOCUMENT":
        plain = (
            "What changed: New regulatory primary document detected. "
            f"{summary.plain_english_summary}"
        )
    elif change.change_type == "NO_MATERIAL_CHANGE":
        plain = summary.plain_english_summary
    else:
        plain = f"What changed: {change.change_type.replace('_', ' ').title()}. {change.evidence}"
    return summary.model_copy(
        update={
            "plain_english_summary": plain[:900],
            "why_it_matters": change.why_it_matters or summary.why_it_matters,
            "affected_segments": change.affected_parties or summary.affected_segments,
            "change_details": change.model_dump(mode="json"),
        }
    )


def _deadline_changes(previous_text: str, current_text: str) -> list[DeadlineChange]:
    previous = _typed_deadlines(previous_text)
    current = _typed_deadlines(current_text)
    changes: list[DeadlineChange] = []
    for deadline_type in sorted(set(previous) | set(current)):
        old_dates = previous.get(deadline_type, [])
        new_dates = current.get(deadline_type, [])
        old_best = _latest_deadline(old_dates)
        new_best = _latest_deadline(new_dates)
        if old_best == new_best:
            if old_best:
                changes.append(
                    DeadlineChange(
                        deadline_type=deadline_type,  # type: ignore[arg-type]
                        change="UNCHANGED",
                        old_date=old_best.normalized_date,
                        new_date=new_best.normalized_date if new_best else None,
                        confidence=0.45,
                        evidence="Deadline date unchanged.",
                    )
                )
            continue
        if old_best and new_best and old_best.normalized_date and new_best.normalized_date:
            direction = (
                "EXTENDED"
                if new_best.normalized_date > old_best.normalized_date
                else "SHORTENED"
            )
            changes.append(
                DeadlineChange(
                    deadline_type=deadline_type,  # type: ignore[arg-type]
                    change=direction,
                    old_date=old_best.normalized_date,
                    new_date=new_best.normalized_date,
                    confidence=min(old_best.confidence, new_best.confidence, 0.9),
                    evidence=(
                        f"{deadline_type.replace('_', ' ').title()} {direction.lower()} "
                        f"from {_format_date(old_best.normalized_date)} "
                        f"to {_format_date(new_best.normalized_date)}."
                    ),
                )
            )
        elif new_best and new_best.normalized_date:
            changes.append(
                DeadlineChange(
                    deadline_type=deadline_type,  # type: ignore[arg-type]
                    change="ADDED",
                    old_date=None,
                    new_date=new_best.normalized_date,
                    confidence=new_best.confidence,
                    evidence=f"{deadline_type.replace('_', ' ').title()} added.",
                )
            )
        elif old_best and old_best.normalized_date:
            changes.append(
                DeadlineChange(
                    deadline_type=deadline_type,  # type: ignore[arg-type]
                    change="REMOVED",
                    old_date=old_best.normalized_date,
                    new_date=None,
                    confidence=old_best.confidence,
                    evidence=f"{deadline_type.replace('_', ' ').title()} removed.",
                )
            )
    return [change for change in changes if change.change != "UNCHANGED"]


def _latest_deadline(values: list[DeadlineIntelligence]) -> DeadlineIntelligence | None:
    dated = [item for item in values if item.normalized_date]
    if not dated:
        return None
    return max(dated, key=lambda item: item.normalized_date)


def _typed_deadlines(text: str) -> dict[str, list[DeadlineIntelligence]]:
    values: dict[str, list[DeadlineIntelligence]] = {}
    for item in extract_deadline_intelligence(text):
        if not item.normalized_date or item.deadline_type in {"UNKNOWN_DATE", "PUBLICATION_DATE"}:
            continue
        values.setdefault(item.deadline_type, []).append(item)
    return values


def _best_deadline_change(changes: list[DeadlineChange]) -> DeadlineChange:
    ranked = {"EXTENDED": 4, "SHORTENED": 4, "ADDED": 3, "REMOVED": 2}
    return max(changes, key=lambda item: (ranked.get(item.change, 0), item.confidence))


def _signal_change_type(title: str, text: str) -> str | None:
    haystack = f"{title}\n{text[:12000]}".lower()
    if _has_any(haystack, WITHDRAWAL_TERMS):
        return "WITHDRAWAL"
    if _has_any(haystack, CORRIGENDUM_TERMS):
        return "CORRIGENDUM"
    if _has_any(haystack, ADDENDUM_TERMS):
        return "ADDENDUM"
    if _has_any(haystack, AMENDMENT_TERMS):
        return "AMENDMENT"
    if _has_any(haystack, REISSUE_TERMS):
        return "REISSUED_DOCUMENT"
    if _has_any(haystack, TENDER_TERMS):
        return "TENDER_UPDATE"
    if _has_any(haystack, CONSULTATION_TERMS):
        return "CONSULTATION_UPDATE"
    if _has_any(haystack, POLICY_TERMS):
        return "POLICY_UPDATE"
    return None


def _signal_confidence(change_type: str, similarity: float | None) -> float:
    base = {
        "WITHDRAWAL": 0.88,
        "CORRIGENDUM": 0.86,
        "ADDENDUM": 0.84,
        "AMENDMENT": 0.84,
        "REISSUED_DOCUMENT": 0.8,
        "TENDER_UPDATE": 0.78,
        "CONSULTATION_UPDATE": 0.78,
        "POLICY_UPDATE": 0.74,
    }.get(change_type, 0.7)
    if similarity is not None and similarity < 0.85:
        base += 0.04
    return min(base, 0.95)


def _change(
    change_type: str,
    material: bool,
    confidence: float,
    evidence: str,
    extracted: ExtractedDoc,
    *,
    prior: PriorVersionReference | None,
    previous_state: str | None,
    new_state: str | None,
    deadline_changes: list[DeadlineChange] | None = None,
    similarity: float | None = None,
    reasons: list[str] | None = None,
) -> RegulatoryChange:
    return RegulatoryChange(
        change_type=change_type,  # type: ignore[arg-type]
        is_material=material,
        confidence=round(confidence, 4),
        evidence=evidence[:1200],
        prior_version_reference=prior,
        previous_state=previous_state,
        new_state=new_state,
        why_it_matters=_why_it_matters(change_type, extracted),
        affected_parties=_affected_parties(extracted.text),
        deadline_changes=deadline_changes or [],
        similarity_score=similarity,
        reasons=reasons or [],
    )


def _content_similarity(left: str, right: str) -> float:
    if not left or not right:
        return 0.0
    left_sample = _sample_for_similarity(left)
    right_sample = _sample_for_similarity(right)
    return round(SequenceMatcher(None, left_sample, right_sample).ratio(), 5)


def _sample_for_similarity(text: str) -> str:
    if len(text) <= 12000:
        return text
    return text[:5000] + text[len(text) // 2: len(text) // 2 + 4000] + text[-3000:]


def _evidence_for_change(change_type: str, text: str) -> str:
    terms = {
        "WITHDRAWAL": WITHDRAWAL_TERMS,
        "CORRIGENDUM": CORRIGENDUM_TERMS,
        "ADDENDUM": ADDENDUM_TERMS,
        "AMENDMENT": AMENDMENT_TERMS,
        "REISSUED_DOCUMENT": REISSUE_TERMS,
        "TENDER_UPDATE": TENDER_TERMS,
        "CONSULTATION_UPDATE": CONSULTATION_TERMS,
        "POLICY_UPDATE": POLICY_TERMS,
    }.get(change_type, MATERIAL_TERMS)
    return _evidence_for_terms(text, terms) or _first_evidence(text)


def _evidence_for_terms(text: str, terms: tuple[str, ...]) -> str:
    lower = text.lower()
    for term in terms:
        index = lower.find(term)
        if index >= 0:
            start = max(index - 180, 0)
            end = min(index + 420, len(text))
            return text[start:end].strip()
    return ""


def _first_evidence(text: str) -> str:
    return text[:700].strip()


def _prior_state(prior: PriorVersionReference | None) -> str | None:
    if not prior:
        return None
    label = prior.title or prior.source_url or "prior version"
    return f"Compared against {label}."


def _new_state(change_type: str, text: str) -> str:
    return _evidence_for_change(change_type, text)[:600]


def _why_it_matters(change_type: str, extracted: ExtractedDoc) -> str:
    if change_type == "DEADLINE_CHANGE":
        return (
            "A regulatory deadline changed, so affected users may need to update filing, "
            "bid, or compliance timelines."
        )
    if change_type == "TENDER_UPDATE":
        return "This may affect bidding strategy, eligibility, scope, or submission timelines."
    if change_type == "CONSULTATION_UPDATE":
        return "This may affect the window for submitting comments or participating in a hearing."
    if change_type in {"AMENDMENT", "CORRIGENDUM", "ADDENDUM"}:
        return (
            "This changes or clarifies an existing regulatory instrument and may affect "
            "compliance interpretation."
        )
    if change_type == "WITHDRAWAL":
        return "A previous regulatory action may no longer apply."
    if change_type == "REISSUED_DOCUMENT":
        return (
            "A regulatory document appears to have been republished or superseded by a "
            "newer version."
        )
    if change_type == "NEW_DOCUMENT":
        return "A new primary regulatory document was detected and passed material-change checks."
    if extracted.classification:
        return (
            f"This document is classified as {extracted.classification} and should be "
            "reviewed for material impact."
        )
    return "No material regulatory change was detected."


def _affected_parties(text: str) -> list[str]:
    lower = text.lower()
    parties = [
        label
        for label, terms in AFFECTED_PATTERNS.items()
        if any(term in lower for term in terms)
    ]
    return parties[:8]


def _title_key(value: str) -> str:
    value = re.sub(
        r"\b(?:draft|final|corrigendum|amendment|notification|order)\b",
        "",
        value.lower(),
    )
    return re.sub(r"[^a-z0-9]+", " ", value).strip()


def _normalize(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def _clean(value: str | None) -> str:
    return _normalize(value or "")


def _has_any(value: str, terms: tuple[str, ...]) -> bool:
    return any(term in value for term in terms)


def _format_date(value) -> str | None:
    return value.isoformat() if value else None
