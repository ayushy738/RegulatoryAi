"""Unit tests for read-only intelligence-gate verification reconstruction."""

from __future__ import annotations

from datetime import date
from unittest.mock import patch

from backend.core.models import CandidateQuality
from backend.pipeline.intelligence_gate_verify import (
    build_extracted_doc_for_verify,
    diagnose_document_intelligence,
)


TODAY = date(2026, 8, 16)


def _ctuil_listing_row(*, document_id: int = 287) -> dict:
    return {
        "document_id": document_id,
        "source_id": 13,
        "title": "Approval of ISTS Schemes",
        "source_url": "https://ctuil.in/ists-schemes",
        "issuing_body": "CTUIL",
        "issue_date": date(2026, 6, 25),
        "issue_date_precision": "day",
        "doc_type": "html",
        "jurisdiction": "central",
        "source_code": "CTUIL",
        "version_id": document_id,
        "file_hash": "filehash-verify-001",
        "content_hash": "contenthash-verify-001",
        "raw_file_path": "/tmp/ctuil.html",
        "text_path": "/tmp/ctuil.txt",
        "page_count": 1,
        "needs_ocr": False,
        "http_status": 200,
        "text_content": (
            "Central Transmission Utility of India Limited publishes ISTS scheme "
            "approvals for transmission licensees and renewable developers. "
            "Revised Format for Confirmation by RE developers updated on 25.06.2026 "
            "for stakeholder comments. Rolling Plan Corner Proposals for Stakeholders "
            "Comments and advisory information on GNA transition and tender notices."
        ),
    }


def test_build_extracted_uses_classify_candidate_not_hardcoded_tender() -> None:
    row = _ctuil_listing_row()
    fake = CandidateQuality(
        classification="POLICY_UPDATE",
        is_valid_event_source=True,
        confidence=0.91,
        reason_code="POLICY_SIGNAL",
        explanation="test",
    )
    with patch(
        "backend.pipeline.intelligence_gate_verify.classify_candidate",
        return_value=fake,
    ) as mocked:
        extracted = build_extracted_doc_for_verify(row)

    mocked.assert_called_once()
    kwargs = mocked.call_args.kwargs
    assert "content_text" in kwargs
    assert "tender" in kwargs["content_text"].lower() or "comments" in kwargs["content_text"].lower()
    assert extracted.classification == "POLICY_UPDATE"
    assert extracted.classification != "TENDER_DOCUMENT"


def test_diagnose_informational_listing_not_expired_opportunity() -> None:
    """After ACTIONABLE guard: INFORMATIONAL + old scraped dates must not expire."""

    result = diagnose_document_intelligence(
        287,
        today=TODAY,
        row=_ctuil_listing_row(document_id=287),
    )
    assert result["status"] == "OK"
    assert result["read_only"] is True
    assert result["document_id"] == 287
    assert result["classification"] is not None
    assert result["actionability"] == "INFORMATIONAL"
    assert result["rejection_reason"] != "EXPIRED_OPPORTUNITY"
    assert result["would_reject_as_expired_opportunity"] is False
    assert result["event_allowed"] is True
