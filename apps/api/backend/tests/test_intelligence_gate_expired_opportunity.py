"""Regression: EXPIRED_OPPORTUNITY must not fire on INFORMATIONAL listing noise."""

from __future__ import annotations

from datetime import date

from backend.core.models import (
    DeadlineIntelligence,
    DiscoveredDoc,
    ExtractedDoc,
    FetchedFile,
)
from backend.pipeline.intelligence_gate import (
    _rejection_reason,
    assess_event_intelligence,
)


TODAY = date(2026, 8, 16)


def _extracted(
    *,
    title: str,
    text: str,
    classification: str,
    issue_date: date | None = date(2026, 7, 1),
    url: str = "https://ctuil.in/ists-schemes",
) -> ExtractedDoc:
    discovered = DiscoveredDoc(
        source_code="CTUIL",
        title=title,
        source_url=url,
        issuing_body="CTUIL",
        issue_date=issue_date,
        issue_date_precision="day" if issue_date else "unknown",
        doc_type="html",
        jurisdiction="central",
    )
    fetched = FetchedFile(
        discovered=discovered,
        file_hash="filehash-intel-gate-001",
        raw_file_path="/tmp/ctuil-listing.html",
        http_status=200,
    )
    return ExtractedDoc(
        fetched=fetched,
        text=text,
        content_hash="contenthash-intel-gate-001",
        page_count=1,
        needs_ocr=False,
        text_path="/tmp/ctuil-listing.txt",
        classification=classification,  # type: ignore[arg-type]
    )


def _deadline(
    *,
    raw: str,
    normalized: date,
    deadline_type: str,
    confidence: float = 0.88,
) -> DeadlineIntelligence:
    return DeadlineIntelligence(
        raw_date=raw,
        normalized_date=normalized,
        deadline_type=deadline_type,  # type: ignore[arg-type]
        confidence=confidence,
        evidence_snippet=f"comments due by {raw}",
    )


def test_informational_tender_with_old_scraped_deadline_not_expired_opportunity() -> None:
    """CTUIL-style listing: INFORMATIONAL + old scraped date must stay allowed."""

    reason = _rejection_reason(
        "TENDER_DOCUMENT",
        False,
        "CURRENT",
        "INFORMATIONAL",
        [
            _deadline(
                raw="25.06.2026",
                normalized=date(2026, 6, 25),
                deadline_type="CONSULTATION_DEADLINE",
            )
        ],
        quality_score=89,
        today=TODAY,
    )
    assert reason != "EXPIRED_OPPORTUNITY"
    assert reason is None

    extracted = _extracted(
        title="Approval of ISTS Schemes",
        text=(
            "Central Transmission Utility of India Limited publishes ISTS scheme "
            "approvals for transmission licensees and renewable developers. "
            "Revised Format for Confirmation by RE developers updated on 25.06.2026 "
            "for stakeholder comments. Rolling Plan Corner Proposals for Stakeholders "
            "Comments and advisory information on GNA transition."
        ),
        classification="TENDER_DOCUMENT",
        issue_date=date(2026, 7, 20),
    )
    intelligence = assess_event_intelligence(extracted, today=TODAY)
    assert intelligence.actionability == "INFORMATIONAL"
    assert intelligence.rejection_reason != "EXPIRED_OPPORTUNITY"
    assert intelligence.event_allowed is True


def test_actionable_tender_with_genuinely_expired_deadline_still_rejected() -> None:
    """ACTIONABLE tender/consultation with expired opportunity window stays rejected."""

    reason = _rejection_reason(
        "TENDER_DOCUMENT",
        False,
        "CURRENT",
        "ACTIONABLE",
        [
            _deadline(
                raw="01.05.2026",
                normalized=date(2026, 5, 1),
                deadline_type="TENDER_SUBMISSION_DEADLINE",
            ),
            # Future non-tender deadline can make a document ACTIONABLE while the
            # tender/consultation opportunity itself is already closed.
            _deadline(
                raw="30.09.2026",
                normalized=date(2026, 9, 30),
                deadline_type="HEARING_DATE",
                confidence=0.86,
            ),
        ],
        quality_score=88,
        today=TODAY,
    )
    assert reason == "EXPIRED_OPPORTUNITY"

    # End-to-end: keep tender/consultation evidence far from other date cues so
    # deadline typing stays TENDER_SUBMISSION_DEADLINE / HEARING_DATE respectively.
    extracted = _extracted(
        title="Transmission Licence Tender with Closed Bid Window",
        text=(
            "Invitation to tender and RFP auction for a transmission licence under the "
            "regulated tariff mechanism. Bid submission deadline was 01.05.2026 and "
            "bidders were required to complete tender submission before that date. "
            "Solar and wind developers and transmission licensees are affected by the "
            "procurement outcome and monetary tariff impact described in the RFP. "
            + ("Background and annex material. " * 40)
            + "Separately, a public hearing is scheduled on 30.09.2026 for related "
            "petition proceedings. Parties should track or attend that hearing."
        ),
        classification="TENDER_DOCUMENT",
        issue_date=date(2026, 7, 15),
        url="https://example.gov.in/tenders/closed-window.pdf",
    )
    intelligence = assess_event_intelligence(extracted, today=TODAY)
    assert intelligence.actionability == "ACTIONABLE"
    assert any(
        item.deadline_type == "TENDER_SUBMISSION_DEADLINE"
        and item.normalized_date == date(2026, 5, 1)
        for item in intelligence.deadlines
    )
    assert intelligence.rejection_reason == "EXPIRED_OPPORTUNITY"
    assert intelligence.event_allowed is False


def test_actionable_tender_with_future_deadline_remains_allowed() -> None:
    """Current actionable tender/consultation with a future deadline stays allowed."""

    reason = _rejection_reason(
        "CONSULTATION_DOCUMENT",
        False,
        "CURRENT",
        "ACTIONABLE",
        [
            _deadline(
                raw="30.09.2026",
                normalized=date(2026, 9, 30),
                deadline_type="CONSULTATION_DEADLINE",
            )
        ],
        quality_score=90,
        today=TODAY,
    )
    assert reason is None

    extracted = _extracted(
        title="Draft Procedure for Grid Connectivity Consultation",
        text=(
            "Central Electricity Regulatory Commission invites stakeholder comments "
            "on the draft grid connectivity procedure. Consultation deadline for "
            "comments and objections is 30.09.2026. Transmission licensees and "
            "renewable developers must submit responses before the deadline. "
            "Tariff and open access impacts are described in the draft."
        ),
        classification="CONSULTATION_DOCUMENT",
        issue_date=date(2026, 8, 1),
        url="https://example.gov.in/consultations/grid-connectivity.pdf",
    )
    intelligence = assess_event_intelligence(extracted, today=TODAY)
    assert intelligence.actionability == "ACTIONABLE"
    assert intelligence.rejection_reason is None
    assert intelligence.event_allowed is True
