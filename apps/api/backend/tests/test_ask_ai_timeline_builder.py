from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from backend.ask.decision import TimeDimension
from backend.ask.orchestration import ProvenanceClass
from backend.rag.timeline import (
    TimelineBuildRequest,
    TimelineBuildStatus,
    TimelineExclusionReason,
    TimelineInputEvent,
    TimelineInputKind,
    build_timeline,
    timeline_build_result_json,
)


def _input(
    *,
    input_id: str = "official-1",
    event_key: str = "dsm-effective",
    date_value: datetime | None = datetime(2026, 4, 1, tzinfo=UTC),
    semantic: TimeDimension = TimeDimension.EFFECTIVE,
    kind: TimelineInputKind = TimelineInputKind.OFFICIAL_EVIDENCE,
    provenance: ProvenanceClass = (
        ProvenanceClass.INTERNAL_REGULATORY_CORPUS
    ),
    question_ids: tuple[str, ...] = ("q1",),
    section_keys: tuple[str, ...] = ("timeline",),
    entity_ids: tuple[str, ...] = ("regulation.dsm",),
    discovery_only: bool = False,
    related: tuple[str, ...] = (),
) -> TimelineInputEvent:
    return TimelineInputEvent(
        input_artifact_id=input_id,
        input_kind=kind,
        event_key=event_key,
        label="DSM event",
        event_type="effective",
        date_value=date_value,
        date_semantic=semantic,
        date_confidence=0.9,
        critical_source_confidence=0.9,
        provenance_class=provenance,
        source_ids=(f"source:{input_id}",),
        question_ids=question_ids,
        section_keys=section_keys,
        entity_ids=entity_ids,
        related_input_artifact_ids=related,
        discovery_only=discovery_only,
    )


def _request(*inputs: TimelineInputEvent) -> TimelineBuildRequest:
    return TimelineBuildRequest(
        question_id="q1",
        section_key="timeline",
        entity_ids=("regulation.dsm",),
        evidence_input_cutoff_reached=True,
        inputs=inputs,
    )


def test_dates_are_ordered_deterministically_without_semantic_collapse() -> None:
    effective = _input()
    issued = _input(
        input_id="official-issue",
        event_key="dsm-issued",
        date_value=datetime(2026, 3, 1, tzinfo=UTC),
        semantic=TimeDimension.PUBLICATION_OR_ISSUE,
    )

    result = build_timeline(_request(effective, issued))

    assert result.status is TimelineBuildStatus.COMPLETE
    assert tuple(
        event.payload.date_semantic for event in result.events
    ) == (
        TimeDimension.PUBLICATION_OR_ISSUE,
        TimeDimension.EFFECTIVE,
    )
    assert result.conflicts == ()
    serialized = timeline_build_result_json(result)
    assert serialized == timeline_build_result_json(
        type(result).model_validate_json(serialized)
    )


def test_official_and_live_events_share_chronology_but_keep_provenance() -> None:
    official = _input()
    live = _input(
        input_id="live-1",
        event_key="dsm-announcement",
        date_value=datetime(2026, 3, 15, tzinfo=UTC),
        semantic=TimeDimension.EVENT,
        kind=TimelineInputKind.LIVE_EVENT,
        provenance=ProvenanceClass.LIVE_WEB_SOURCES,
    )

    result = build_timeline(_request(official, live))

    assert tuple(event.provenance_class for event in result.events) == (
        ProvenanceClass.LIVE_WEB_SOURCES,
        ProvenanceClass.INTERNAL_REGULATORY_CORPUS,
    )
    assert result.events[0].source_ids == ("source:live-1",)
    assert result.events[1].source_ids == ("source:official-1",)


def test_same_semantic_date_conflict_retains_both_sources() -> None:
    first = _input(input_id="official-1")
    second = _input(
        input_id="official-2",
        date_value=datetime(2026, 4, 2, tzinfo=UTC),
    )

    result = build_timeline(_request(first, second))

    assert result.status is TimelineBuildStatus.PARTIAL
    assert len(result.events) == 2
    assert len(result.conflicts) == 1
    assert set(result.conflicts[0].event_ids) == {
        event.event_id for event in result.events
    }
    assert all(
        event.conflict_group_id == result.conflicts[0].conflict_group_id
        for event in result.events
    )
    assert "date_conflicts_retained" in result.notes
    reversed_result = build_timeline(_request(second, first))
    assert timeline_build_result_json(reversed_result) == (
        timeline_build_result_json(result)
    )


def test_different_date_semantics_are_not_a_conflict() -> None:
    issue = _input(semantic=TimeDimension.PUBLICATION_OR_ISSUE)
    effective = _input(
        input_id="official-2",
        date_value=datetime(2026, 4, 2, tzinfo=UTC),
    )

    result = build_timeline(_request(issue, effective))

    assert result.status is TimelineBuildStatus.COMPLETE
    assert result.conflicts == ()


def test_missing_date_is_not_invented_and_is_sorted_last_as_inferred() -> None:
    undated = _input(input_id="undated", date_value=None)
    dated = _input()

    result = build_timeline(_request(undated, dated))

    assert result.status is TimelineBuildStatus.PARTIAL
    assert result.events[-1].payload.date_value is None
    assert result.events[-1].payload.inferred_order is True
    assert "missing_date" in result.events[-1].warnings
    assert "undated_events_retained" in result.notes


def test_discovery_only_graph_fact_cannot_gain_legal_force() -> None:
    graph = _input(
        input_id="graph-1",
        kind=TimelineInputKind.STRUCTURED_FACT,
        discovery_only=True,
    )

    result = build_timeline(_request(graph))

    assert result.events[0].discovery_only is True
    assert "discovery_only_graph_fact" in result.events[0].warnings


def test_event_relationships_resolve_to_output_ids_and_missing_links_warn() -> None:
    predecessor = _input(input_id="predecessor")
    successor = _input(
        input_id="successor",
        date_value=datetime(2026, 5, 1, tzinfo=UTC),
        related=("predecessor", "excluded"),
    )

    result = build_timeline(_request(successor, predecessor))
    by_ancestry = {event.ancestry[0]: event for event in result.events}

    assert by_ancestry["successor"].payload.related_event_ids == (
        by_ancestry["predecessor"].event_id,
    )
    assert "unresolved_event_relationship" in by_ancestry["successor"].warnings


@pytest.mark.parametrize(
    ("item", "reason"),
    [
        (
            _input(input_id="not-material").model_copy(
                update={"material": False}
            ),
            TimelineExclusionReason.OUTSIDE_MATERIAL_SCOPE,
        ),
        (
            _input(input_id="wrong-question", question_ids=("q2",)),
            TimelineExclusionReason.OUTSIDE_QUESTION_SCOPE,
        ),
        (
            _input(input_id="wrong-section", section_keys=("other",)),
            TimelineExclusionReason.OUTSIDE_SECTION_SCOPE,
        ),
        (
            _input(input_id="wrong-entity", entity_ids=("regulation.other",)),
            TimelineExclusionReason.OUTSIDE_ENTITY_SCOPE,
        ),
    ],
)
def test_out_of_scope_input_is_excluded_without_losing_valid_event(
    item: TimelineInputEvent,
    reason: TimelineExclusionReason,
) -> None:
    result = build_timeline(_request(_input(), item))

    assert result.status is TimelineBuildStatus.PARTIAL
    assert len(result.events) == 1
    assert result.exclusions[0].reason is reason


def test_empty_or_all_excluded_input_returns_no_events_without_false_success() -> None:
    empty = build_timeline(_request())
    excluded = build_timeline(
        _request(_input(question_ids=("q2",)))
    )

    assert empty.status is TimelineBuildStatus.NO_EVENTS
    assert excluded.status is TimelineBuildStatus.NO_EVENTS
    assert excluded.exclusions


def test_builder_refuses_to_finalize_before_evidence_cutoff() -> None:
    request = _request(_input()).model_copy(
        update={"evidence_input_cutoff_reached": False}
    )

    with pytest.raises(ValueError, match="cutoff"):
        build_timeline(request)


def test_contracts_reject_naive_dates_lane_drift_duplicates_and_mutation() -> None:
    with pytest.raises(ValidationError, match="timezone-aware"):
        _input(date_value=datetime(2026, 4, 1))
    with pytest.raises(ValidationError, match="provenance"):
        _input(
            kind=TimelineInputKind.LIVE_EVENT,
            provenance=ProvenanceClass.INTERNAL_REGULATORY_CORPUS,
        )
    with pytest.raises(ValidationError, match="critical source"):
        TimelineInputEvent.model_validate(
            {
                **_input().model_dump(mode="python"),
                "critical_source_confidence": 0.8,
            }
        )
    with pytest.raises(ValidationError, match="unique"):
        TimelineBuildRequest(
            question_id="q1",
            section_key="timeline",
            evidence_input_cutoff_reached=True,
            inputs=(_input(), _input()),
        )
    item = _input()
    with pytest.raises(ValidationError):
        item.label = "changed"  # type: ignore[misc]
