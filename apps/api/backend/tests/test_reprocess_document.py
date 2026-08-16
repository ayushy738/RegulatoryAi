"""Focused tests for operator document reprocess (classification + gates + idempotency)."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import replace
from datetime import date
from unittest.mock import MagicMock, patch

import pytest

from backend.core.models import EventIntelligence, RegulatoryChange, SummaryPayload
from backend.core.repository import _DurableDocumentState
from backend.pipeline import reprocess_document as mod
from backend.pipeline.intelligence_gate import assess_event_intelligence
from backend.pipeline.intelligence_gate_verify import build_extracted_doc_for_verify
from backend.tools import reprocess_document as cli


TODAY = date(2026, 8, 16)


def _row(*, document_id: int = 287) -> dict:
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
        "file_hash": "filehash-reprocess-001",
        "content_hash": "contenthash-reprocess-001",
        "raw_file_path": "/tmp/ctuil.html",
        "text_path": "/tmp/ctuil.txt",
        "page_count": 1,
        "needs_ocr": False,
        "http_status": 200,
        "family_id": 10,
        "assignment_type": "PRIMARY",
        "text_content": (
            "Central Transmission Utility of India Limited publishes ISTS scheme "
            "approvals for transmission licensees and renewable developers. "
            "Revised Format for Confirmation by RE developers updated on 25.06.2026 "
            "for stakeholder comments. Rolling Plan Corner Proposals for Stakeholders "
            "Comments and advisory information on GNA transition and tender notices."
        ),
    }


def _intelligence(*, allowed: bool = True) -> EventIntelligence:
    return EventIntelligence(
        event_allowed=allowed,
        rejection_reason=None if allowed else "EXPIRED_OPPORTUNITY",
        freshness="CURRENT",
        freshness_reason="CURRENT_REGULATORY_ACTIVITY",
        significance_score=100,
        significance_category="CRITICAL",
        actionability="INFORMATIONAL",
        title_quality_score=9,
        document_quality_score=8,
        date_confidence_score=8,
        quality_score=89,
        quality_category="EXCELLENT",
    )


def _change(*, material: bool = True) -> RegulatoryChange:
    return RegulatoryChange(
        change_type="NEW_DOCUMENT" if material else "NO_MATERIAL_CHANGE",
        is_material=material,
        confidence=0.76,
        evidence="test",
        why_it_matters="test",
    )


def test_reconstruction_preserves_tender_document_classification() -> None:
    extracted = build_extracted_doc_for_verify(_row(document_id=287))
    assert extracted.classification == "TENDER_DOCUMENT"


def test_informational_old_deadline_is_event_allowed() -> None:
    extracted = build_extracted_doc_for_verify(_row())
    extracted = extracted.model_copy(update={"classification": "TENDER_DOCUMENT"})
    intelligence = assess_event_intelligence(extracted, today=TODAY)
    assert intelligence.actionability == "INFORMATIONAL"
    assert intelligence.rejection_reason != "EXPIRED_OPPORTUNITY"
    assert intelligence.event_allowed is True


def test_actionable_expired_opportunity_still_rejected() -> None:
    from backend.core.models import DeadlineIntelligence
    from backend.pipeline.intelligence_gate import _rejection_reason

    reason = _rejection_reason(
        "TENDER_DOCUMENT",
        False,
        "CURRENT",
        "ACTIONABLE",
        [
            DeadlineIntelligence(
                raw_date="01.05.2026",
                normalized_date=date(2026, 5, 1),
                deadline_type="TENDER_SUBMISSION_DEADLINE",
                confidence=0.9,
                evidence_snippet="bid submission deadline",
            )
        ],
        quality_score=88,
        today=TODAY,
    )
    assert reason == "EXPIRED_OPPORTUNITY"


def test_dry_run_performs_no_downstream_writes() -> None:
    row = _row()
    with (
        patch.object(mod, "_event_count_for_document", return_value=0),
        patch.object(mod, "assess_event_intelligence", return_value=_intelligence(allowed=True)),
        patch.object(
            mod,
            "_evaluate_event_gates",
            return_value={
                "material_change": True,
                "change_type": "NEW_DOCUMENT",
                "would_create_event": True,
                "skip_reason": None,
            },
        ),
        patch.object(mod, "_process_document_downstream") as downstream,
        patch.object(mod, "_notification_count_for_event") as notify_count,
    ):
        result = mod.reprocess_document(287, dry_run=True, today=TODAY, row=row)

    downstream.assert_not_called()
    notify_count.assert_not_called()
    assert result["status"] == "DRY_RUN"
    assert result["event_id"] is None
    assert result["notifications_queued"] == 0
    assert result["notification_enqueue_occurred"] is False
    assert result["existing_event_count"] == 0
    assert result["classification"] is not None
    assert "material_change" in result
    assert "change_type" in result
    assert "event_allowed" in result


def test_dry_run_skips_when_events_already_present() -> None:
    row = _row()
    with (
        patch.object(mod, "_event_count_for_document", return_value=1),
        patch.object(mod, "assess_event_intelligence", return_value=_intelligence(allowed=True)),
        patch.object(
            mod,
            "_evaluate_event_gates",
            return_value={
                "material_change": True,
                "change_type": "NEW_DOCUMENT",
                "would_create_event": False,
                "skip_reason": "events_already_present",
            },
        ),
        patch.object(mod, "_process_document_downstream") as downstream,
    ):
        result = mod.reprocess_document(287, dry_run=True, row=row)

    downstream.assert_not_called()
    assert result["create_events"] is False
    assert result["existing_event_count"] == 1
    assert result["would_create_event"] is False
    assert result["skip_reason"] == "events_already_present"


def test_execute_calls_process_document_downstream() -> None:
    row = _row()
    with (
        patch.object(mod, "_event_count_for_document", return_value=0),
        patch.object(mod, "assess_event_intelligence", return_value=_intelligence(allowed=True)),
        patch.object(mod, "_process_document_downstream", return_value=501) as downstream,
        patch.object(mod, "_notification_count_for_event", return_value=2),
        patch.object(
            mod,
            "_evaluate_event_gates",
            return_value={
                "material_change": True,
                "change_type": "NEW_DOCUMENT",
                "would_create_event": True,
                "skip_reason": None,
            },
        ),
    ):
        result = mod.reprocess_document(287, dry_run=False, row=row)

    downstream.assert_called_once()
    state = downstream.call_args.args[0]
    assert isinstance(state, _DurableDocumentState)
    assert state.document_id == 287
    assert state.create_events is True
    assert state.extracted.classification is not None
    assert result["status"] == "COMPLETED"
    assert result["event_id"] == 501
    assert result["notifications_queued"] == 2
    assert result["notification_enqueue_occurred"] is True


def test_execute_idempotent_when_event_exists() -> None:
    row = _row()
    with (
        patch.object(mod, "_event_count_for_document", return_value=3),
        patch.object(mod, "assess_event_intelligence", return_value=_intelligence(allowed=True)),
        patch.object(mod, "_process_document_downstream", return_value=None) as downstream,
        patch.object(
            mod,
            "_evaluate_event_gates",
            return_value={
                "material_change": True,
                "change_type": "NEW_DOCUMENT",
                "would_create_event": False,
                "skip_reason": "events_already_present",
            },
        ),
    ):
        result = mod.reprocess_document(287, dry_run=False, row=row)

    state = downstream.call_args.args[0]
    assert state.create_events is False
    assert result["event_id"] is None
    assert result["create_events"] is False
    assert result["existing_event_count"] == 3
    assert result["notification_enqueue_occurred"] is False


def test_cli_requires_dry_run_or_execute() -> None:
    with pytest.raises(SystemExit):
        cli.main(["--document-id", "287"])


def test_cli_dry_run_flag_does_not_execute(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, object] = {}

    def fake_reprocess(document_id: int, *, dry_run: bool = False, **_kwargs):
        seen["document_id"] = document_id
        seen["dry_run"] = dry_run
        return {"status": "DRY_RUN", "document_id": document_id, "dry_run": dry_run}

    monkeypatch.setattr(cli, "reprocess_document", fake_reprocess)
    assert cli.main(["--document-id", "287", "--dry-run"]) == 0
    assert seen == {"document_id": 287, "dry_run": True}


def test_cli_execute_flag_sets_dry_run_false(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, object] = {}

    def fake_reprocess(document_id: int, *, dry_run: bool = False, **_kwargs):
        seen["document_id"] = document_id
        seen["dry_run"] = dry_run
        return {"status": "COMPLETED", "document_id": document_id, "event_id": 1}

    monkeypatch.setattr(cli, "reprocess_document", fake_reprocess)
    assert cli.main(["--document-id", "287", "--execute"]) == 0
    assert seen == {"document_id": 287, "dry_run": False}


def test_evaluate_event_gates_mirrors_skip_reasons() -> None:
    extracted = build_extracted_doc_for_verify(_row())
    state = _DurableDocumentState(
        extracted=extracted,
        url=extracted.fetched.discovered.source_url,
        content_hash=extracted.content_hash,
        document_id=287,
        version_id=287,
        source_id=13,
        prior_reference=None,
        family_id=10,
        assignment_type="PRIMARY",
        had_prior_document=False,
        create_events=True,
        topics=["transmission"],
        summary=SummaryPayload(
            plain_english_summary="summary",
            why_it_matters="why",
        ),
        intelligence=_intelligence(allowed=True),
    )
    session = MagicMock()

    @contextmanager
    def fake_scope():
        yield session

    with (
        patch.object(mod, "session_scope", fake_scope),
        patch.object(mod, "_find_family_prior_reference", return_value=None),
        patch.object(mod, "_find_related_prior_reference", return_value=None),
        patch.object(mod, "detect_regulatory_change", return_value=_change(material=True)),
    ):
        decision = mod._evaluate_event_gates(state)

    assert decision["would_create_event"] is True
    assert decision["material_change"] is True

    blocked = replace(state, intelligence=_intelligence(allowed=False))
    with (
        patch.object(mod, "session_scope", fake_scope),
        patch.object(mod, "_find_family_prior_reference", return_value=None),
        patch.object(mod, "_find_related_prior_reference", return_value=None),
        patch.object(mod, "detect_regulatory_change", return_value=_change(material=True)),
    ):
        denied = mod._evaluate_event_gates(blocked)
    assert denied["would_create_event"] is False
    assert denied["skip_reason"] == "EXPIRED_OPPORTUNITY"
