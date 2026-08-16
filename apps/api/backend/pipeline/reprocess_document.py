"""Operator-only reprocess of one durable document through Session B event path.

Reconstructs acquisition classification, reassesses intelligence, and reuses
``_process_document_downstream`` for material-change gates, event insert, and
notification enqueue. Does not alter crawl, checkpoints, or retry-document.
"""

from __future__ import annotations

from datetime import date
from typing import Any, Mapping

from sqlalchemy import text

from backend.core.db import session_scope
from backend.core.logging import log_event
from backend.core.repository import (
    _DurableDocumentState,
    _find_family_prior_reference,
    _find_related_prior_reference,
    _process_document_downstream,
    _summary_from_extracted,
    _topic_tags,
)
from backend.pipeline.change_detector import detect_regulatory_change
from backend.pipeline.intelligence_gate import (
    assess_event_intelligence,
    attach_intelligence_to_summary,
)
from backend.pipeline.intelligence_gate_verify import (
    build_extracted_doc_for_verify,
    load_document_row_for_verify,
)


def reprocess_document(
    document_id: int,
    *,
    dry_run: bool = False,
    today: date | None = None,
    row: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Re-run event generation for one stored document.

    Live mode calls ``_process_document_downstream`` (graph skip_completed, RAG
    enqueue idempotent, event insert + notification enqueue). Dry-run evaluates
    the same gates without writing audits, events, RAG jobs, or notifications.
    """

    loaded = dict(row) if row is not None else _load_reprocess_row(document_id)
    if loaded is None:
        result = {
            "document_id": document_id,
            "version_id": None,
            "status": "NOT_FOUND",
            "dry_run": dry_run,
            "error": "Document/version/text could not be loaded.",
            "classification": None,
            "actionability": None,
            "freshness": None,
            "quality_score": None,
            "rejection_reason": None,
            "event_allowed": None,
            "create_events": False,
            "existing_event_count": None,
            "material_change": None,
            "change_type": None,
            "event_id": None,
            "notifications_queued": 0,
            "notification_enqueue_occurred": False,
            "would_create_event": False,
        }
        log_event("document_reprocess_finished", **result)
        return result

    extracted = build_extracted_doc_for_verify(loaded)
    topics = _topic_tags(f"{extracted.fetched.discovered.title}\n{extracted.text}")
    summary = _summary_from_extracted(extracted)
    intelligence = assess_event_intelligence(
        extracted,
        topics=topics,
        summary=summary,
        today=today,
    )
    summary = attach_intelligence_to_summary(summary, intelligence)

    existing_events = _event_count_for_document(int(loaded["document_id"]))
    # Same idempotency rule as incomplete-downstream retry: never insert a second
    # event for a document that already has one.
    create_events = existing_events == 0

    state = _DurableDocumentState(
        extracted=extracted,
        url=str(loaded["source_url"]),
        content_hash=str(loaded["content_hash"]),
        document_id=int(loaded["document_id"]),
        version_id=int(loaded["version_id"]) if loaded.get("version_id") is not None else None,
        source_id=int(loaded["source_id"]) if loaded.get("source_id") is not None else None,
        prior_reference=None,
        family_id=int(loaded["family_id"]) if loaded.get("family_id") is not None else None,
        assignment_type=loaded.get("assignment_type"),
        # First event for this document should be NEW (document never evented).
        had_prior_document=False,
        create_events=create_events,
        topics=topics,
        summary=summary,
        intelligence=intelligence,
    )

    base = {
        "document_id": state.document_id,
        "version_id": state.version_id,
        "source_id": state.source_id,
        "source_url": state.url,
        "title": extracted.fetched.discovered.title,
        "dry_run": dry_run,
        "classification": extracted.classification,
        "actionability": intelligence.actionability,
        "freshness": intelligence.freshness,
        "quality_score": intelligence.quality_score,
        "rejection_reason": intelligence.rejection_reason,
        "event_allowed": intelligence.event_allowed,
        "create_events": create_events,
        "existing_event_count": existing_events,
        "events_already_present": existing_events,
    }

    if dry_run:
        decision = _evaluate_event_gates(state)
        result = {
            **base,
            "status": "DRY_RUN",
            "material_change": decision["material_change"],
            "change_type": decision["change_type"],
            "event_id": None,
            "notifications_queued": 0,
            "notification_enqueue_occurred": False,
            "would_create_event": decision["would_create_event"],
            "skip_reason": decision["skip_reason"],
            "error": None,
        }
        log_event("document_reprocess_finished", **result)
        return result

    try:
        event_id = _process_document_downstream(state)
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
        result = {
            **base,
            "status": "FAILED",
            "material_change": None,
            "change_type": None,
            "event_id": None,
            "notifications_queued": 0,
            "notification_enqueue_occurred": False,
            "would_create_event": False,
            "skip_reason": None,
            "error": error,
        }
        log_event("document_reprocess_finished", **result)
        return result

    notifications_queued = (
        _notification_count_for_event(event_id) if event_id is not None else 0
    )
    # Recompute gate outcome for structured operator output (live path already applied).
    decision = _evaluate_event_gates(state)
    result = {
        **base,
        "status": "COMPLETED",
        "material_change": decision["material_change"],
        "change_type": decision["change_type"],
        "event_id": event_id,
        "notifications_queued": notifications_queued,
        "notification_enqueue_occurred": bool(event_id is not None and notifications_queued > 0),
        "would_create_event": event_id is not None,
        "skip_reason": None if event_id is not None else decision["skip_reason"],
        "error": None,
    }
    log_event("document_reprocess_finished", **result)
    return result


def _load_reprocess_row(document_id: int) -> dict[str, Any] | None:
    base = load_document_row_for_verify(document_id)
    if base is None:
        return None
    with session_scope() as session:
        family = session.execute(
            text(
                """
                select family_id, assignment_type
                from document_family_assignments
                where document_id = :document_id
                limit 1
                """
            ),
            {"document_id": document_id},
        ).mappings().first()
    if family:
        base["family_id"] = family["family_id"]
        base["assignment_type"] = family["assignment_type"]
    else:
        base["family_id"] = None
        base["assignment_type"] = None
    return base


def _evaluate_event_gates(state: _DurableDocumentState) -> dict[str, Any]:
    """Mirror ``_process_document_downstream`` event gates without writing."""

    with session_scope() as session:
        prior_reference = state.prior_reference
        if state.create_events and state.version_id is not None:
            if not prior_reference:
                prior_reference = _find_family_prior_reference(
                    session,
                    family_id=state.family_id,
                    current_version_id=state.version_id,
                )
            if not prior_reference:
                prior_reference = _find_related_prior_reference(
                    session,
                    extracted=state.extracted,
                    current_document_id=state.document_id,
                    source_id=state.source_id,
                )
        change = detect_regulatory_change(state.extracted, prior=prior_reference)

    material = bool(change.is_material and change.change_type != "NO_MATERIAL_CHANGE")
    skip_reason: str | None = None
    if not state.create_events:
        skip_reason = "events_already_present"
    elif not material:
        skip_reason = "no_material_change"
    elif not state.intelligence.event_allowed:
        skip_reason = state.intelligence.rejection_reason or "event_not_allowed"

    would_create = skip_reason is None
    return {
        "material_change": material,
        "change_type": change.change_type,
        "would_create_event": would_create,
        "skip_reason": skip_reason,
    }


def _event_count_for_document(document_id: int) -> int:
    with session_scope() as session:
        return int(
            session.execute(
                text("select count(*) from events where document_id = :id"),
                {"id": document_id},
            ).scalar()
            or 0
        )


def _notification_count_for_event(event_id: int) -> int:
    with session_scope() as session:
        return int(
            session.execute(
                text("select count(*) from notifications_log where event_id = :id"),
                {"id": event_id},
            ).scalar()
            or 0
        )
