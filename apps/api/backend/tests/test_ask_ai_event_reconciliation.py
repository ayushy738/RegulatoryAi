from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from backend.ask.decision import TimeDimension
from backend.ask.event_reconciliation import (
    ConfidenceEffect,
    ConflictField,
    EventMatchKind,
    EventOriginObservation,
    EventReconciliationRequest,
    EventReconciliationStatus,
    event_reconciliation_result_json,
    reconcile_internal_live_events,
)
from backend.ask.orchestration import ProvenanceClass, TimelineEventPayload
from backend.rag.timeline import TimelineEventRecord

NOW = datetime(2026, 8, 1, 12, tzinfo=UTC)


def _event(
    *,
    event_id: str,
    lane: ProvenanceClass,
    event_key: str = "dsm-consultation",
    label: str = "DSM consultation published",
    event_type: str = "consultation_published",
    date_value: datetime | None = datetime(2026, 8, 1, 9, tzinfo=UTC),
) -> TimelineEventRecord:
    return TimelineEventRecord(
        event_id=(
            "timeline_event_"
            + hashlib.sha256(event_id.encode("utf-8")).hexdigest()[:32]
        ),
        event_key=event_key,
        payload=TimelineEventPayload(
            label=label,
            event_type=event_type,
            date_value=date_value,
            date_semantic=TimeDimension.EVENT,
            date_confidence=0.9,
            inferred_order=date_value is None,
            related_event_ids=(),
        ),
        provenance_class=lane,
        source_ids=(f"source:{event_id}",),
        ancestry=(f"artifact:{event_id}",),
        discovery_only=False,
    )


def _origin(
    *,
    event_id: str,
    lane: ProvenanceClass,
    fingerprint: str = "dsm|consultation|2026-08-01|published",
    description_fingerprint: str = "description:dsm-consultation-published",
    legal_status: str | None = None,
    established: bool = False,
    event_key: str = "dsm-consultation",
    label: str = "DSM consultation published",
    event_type: str = "consultation_published",
    date_value: datetime | None = datetime(2026, 8, 1, 9, tzinfo=UTC),
    retrieved_at: datetime = NOW,
) -> EventOriginObservation:
    return EventOriginObservation(
        event=_event(
            event_id=event_id,
            lane=lane,
            event_key=event_key,
            label=label,
            event_type=event_type,
            date_value=date_value,
        ),
        entity_ids=("regulation.dsm",),
        event_fingerprint=fingerprint,
        description_fingerprint=description_fingerprint,
        published_at=date_value,
        retrieved_at=retrieved_at,
        legal_status=legal_status,
        status_is_established=established,
    )


def _request(*origins: EventOriginObservation) -> EventReconciliationRequest:
    return EventReconciliationRequest(
        question_id="q-latest-dsm",
        section_key="latest-intelligence",
        evidence_input_cutoff_reached=True,
        origins=origins,
    )


def test_exact_internal_live_duplicate_is_one_visual_event_with_both_lanes() -> None:
    official = _origin(
        event_id="official",
        lane=ProvenanceClass.INTERNAL_REGULATORY_CORPUS,
        legal_status="draft consultation",
        established=True,
        retrieved_at=NOW - timedelta(minutes=30),
    )
    live = _origin(
        event_id="live",
        lane=ProvenanceClass.LIVE_WEB_SOURCES,
        legal_status="draft consultation",
    )

    result = reconcile_internal_live_events(_request(live, official))

    assert result.status is EventReconciliationStatus.COMPLETE
    assert len(result.events) == 1
    event = result.events[0]
    assert event.match_kind is EventMatchKind.EXACT_DUPLICATE
    assert tuple(item.event_id for item in event.official_basis) == (
        official.event.event_id,
    )
    assert tuple(item.event_id for item in event.live_coverage) == (
        live.event.event_id,
    )
    assert event.established_legal_status == "draft consultation"
    assert event.live_reported_statuses == ("draft consultation",)
    assert event.official_basis[0].retrieved_at == official.retrieved_at
    assert event.live_coverage[0].retrieved_at == live.retrieved_at
    assert event.all_source_ids == (
        "source:official",
        "source:live",
    )
    assert event.conflicts == ()
    assert event.confidence_effect is ConfidenceEffect.NONE


def test_exact_duplicate_result_is_input_order_independent() -> None:
    official = _origin(
        event_id="official",
        lane=ProvenanceClass.INTERNAL_REGULATORY_CORPUS,
        legal_status="draft consultation",
        established=True,
    )
    live = _origin(
        event_id="live",
        lane=ProvenanceClass.LIVE_WEB_SOURCES,
        legal_status="draft consultation",
    )

    forward = reconcile_internal_live_events(_request(official, live))
    reverse = reconcile_internal_live_events(_request(live, official))

    assert event_reconciliation_result_json(forward) == (
        event_reconciliation_result_json(reverse)
    )


def test_live_status_conflict_remains_visible_and_official_controls_status() -> None:
    official = _origin(
        event_id="official",
        lane=ProvenanceClass.INTERNAL_REGULATORY_CORPUS,
        legal_status="draft consultation",
        established=True,
    )
    live = _origin(
        event_id="live",
        lane=ProvenanceClass.LIVE_WEB_SOURCES,
        legal_status="binding regulation",
    )

    result = reconcile_internal_live_events(_request(official, live))

    event = result.events[0]
    assert result.status is EventReconciliationStatus.PARTIAL
    assert event.match_kind is EventMatchKind.CONFLICT
    assert event.established_legal_status == "draft consultation"
    assert event.live_reported_statuses == ("binding regulation",)
    assert {conflict.field for conflict in event.conflicts} == {
        ConflictField.LEGAL_STATUS
    }
    assert event.confidence_effect is (
        ConfidenceEffect.CONTRADICTION_PENALTY_REQUIRED
    )
    assert event.high_confidence_allowed is False


def test_conflicting_dates_are_not_silently_selected() -> None:
    official = _origin(
        event_id="official",
        lane=ProvenanceClass.INTERNAL_REGULATORY_CORPUS,
        legal_status="draft consultation",
        established=True,
    )
    live = _origin(
        event_id="live",
        lane=ProvenanceClass.LIVE_WEB_SOURCES,
        legal_status="draft consultation",
        date_value=datetime(2026, 8, 2, 9, tzinfo=UTC),
    )

    result = reconcile_internal_live_events(_request(official, live))

    event = result.events[0]
    assert event.match_kind is EventMatchKind.CONFLICT
    assert event.date_value is None
    assert {conflict.field for conflict in event.conflicts} == {
        ConflictField.DATE
    }
    assert len(event.official_basis) == len(event.live_coverage) == 1


def test_fingerprint_collision_cannot_merge_different_event_identity() -> None:
    official = _origin(
        event_id="official",
        lane=ProvenanceClass.INTERNAL_REGULATORY_CORPUS,
        event_key="dsm-consultation",
    )
    live = _origin(
        event_id="live",
        lane=ProvenanceClass.LIVE_WEB_SOURCES,
        event_key="tariff-order",
    )

    result = reconcile_internal_live_events(_request(official, live))

    event = result.events[0]
    assert event.match_kind is EventMatchKind.CONFLICT
    assert {conflict.field for conflict in event.conflicts} == {
        ConflictField.EVENT_IDENTITY
    }
    assert tuple(
        observation.value
        for observation in event.conflicts[0].observations
    ) == (
        "dsm-consultation — regulation.dsm",
        "tariff-order — regulation.dsm",
    )


def test_near_duplicates_stay_individually_inspectable_in_one_cluster() -> None:
    official = _origin(
        event_id="official",
        lane=ProvenanceClass.INTERNAL_REGULATORY_CORPUS,
        fingerprint="dsm|consultation|official-publication",
    )
    live = _origin(
        event_id="live",
        lane=ProvenanceClass.LIVE_WEB_SOURCES,
        fingerprint="dsm|consultation|press-coverage",
        description_fingerprint="description:press-coverage",
        label="Press reports DSM consultation",
    )

    result = reconcile_internal_live_events(_request(live, official))

    assert len(result.events) == 2
    assert all(
        event.match_kind is EventMatchKind.NEAR_DUPLICATE
        for event in result.events
    )
    group_ids = {event.near_duplicate_group_id for event in result.events}
    assert len(group_ids) == 1
    assert None not in group_ids
    assert {item.event_id for event in result.events for item in (
        *event.official_basis,
        *event.live_coverage,
    )} == {official.event.event_id, live.event.event_id}


def test_different_event_keys_are_standalone_and_chronological() -> None:
    later = _origin(
        event_id="later",
        lane=ProvenanceClass.LIVE_WEB_SOURCES,
        fingerprint="dsm|deadline|2026-08-10",
        event_key="dsm-deadline",
        event_type="consultation_deadline",
        date_value=datetime(2026, 8, 10, 9, tzinfo=UTC),
    )
    earlier = _origin(
        event_id="earlier",
        lane=ProvenanceClass.INTERNAL_REGULATORY_CORPUS,
        fingerprint="dsm|published|2026-08-01",
    )

    result = reconcile_internal_live_events(_request(later, earlier))

    assert tuple(event.event_key for event in result.events) == (
        "dsm-consultation",
        "dsm-deadline",
    )
    assert all(
        event.match_kind is EventMatchKind.STANDALONE
        for event in result.events
    )


def test_conflicting_official_statuses_remain_unresolved() -> None:
    draft = _origin(
        event_id="draft",
        lane=ProvenanceClass.INTERNAL_REGULATORY_CORPUS,
        legal_status="draft consultation",
        established=True,
    )
    final = _origin(
        event_id="final",
        lane=ProvenanceClass.INTERNAL_REGULATORY_CORPUS,
        legal_status="final regulation",
        established=True,
    )

    result = reconcile_internal_live_events(_request(draft, final))

    event = result.events[0]
    assert event.established_legal_status is None
    assert event.match_kind is EventMatchKind.CONFLICT
    assert event.high_confidence_allowed is False


def test_empty_input_is_truthful_and_cutoff_is_required() -> None:
    empty = reconcile_internal_live_events(_request())
    assert empty.status is EventReconciliationStatus.NO_EVENTS
    assert empty.events == ()

    with pytest.raises(ValueError, match="cutoff"):
        reconcile_internal_live_events(
            _request(
                _origin(
                    event_id="official",
                    lane=ProvenanceClass.INTERNAL_REGULATORY_CORPUS,
                )
            ).model_copy(update={"evidence_input_cutoff_reached": False})
        )


def test_contract_rejects_general_ai_lane_live_authority_and_duplicate_ids() -> None:
    with pytest.raises(ValidationError, match="General AI"):
        _origin(
            event_id="general",
            lane=ProvenanceClass.GENERAL_AI_KNOWLEDGE,
        )
    with pytest.raises(ValidationError, match="cannot establish"):
        _origin(
            event_id="live",
            lane=ProvenanceClass.LIVE_WEB_SOURCES,
            legal_status="binding regulation",
            established=True,
        )
    origin = _origin(
        event_id="official",
        lane=ProvenanceClass.INTERNAL_REGULATORY_CORPUS,
    )
    with pytest.raises(ValidationError, match="unique"):
        _request(origin, origin)
