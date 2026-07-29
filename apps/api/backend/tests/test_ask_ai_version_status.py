from __future__ import annotations

from datetime import UTC, date, datetime

import pytest
from pydantic import ValidationError

from backend.rag.version_status import (
    DocumentLegalStatus,
    OfficialVersionRecord,
    OfficialVersionRelationship,
    ResolvedVersionStatus,
    VersionEvidenceCoverage,
    VersionRelationshipKind,
    VersionStatusDecision,
    VersionStatusHealth,
    VersionStatusMode,
    VersionStatusOutcome,
    VersionStatusRequest,
    resolve_version_status,
)

NOW = datetime(2026, 7, 27, 10, 0, tzinfo=UTC)


def _record(
    registry_id: int,
    *,
    family_id: int = 10,
    available_on: date | None = None,
    status: DocumentLegalStatus = DocumentLegalStatus.IN_FORCE,
    status_effective_on: date | None = None,
    observed_at: datetime = NOW,
) -> OfficialVersionRecord:
    published = available_on or date(2020 + registry_id, 1, 1)
    return OfficialVersionRecord(
        registry_version_id=registry_id,
        family_id=family_id,
        document_id=100 + registry_id,
        document_version_id=200 + registry_id,
        version_number=registry_id,
        version_label=f"Version {registry_id}",
        publication_date=published,
        effective_date=published,
        declared_status=status,
        status_effective_on=status_effective_on or published,
        status_observed_at=observed_at,
        status_source_url=f"https://official.example/status/{registry_id}",
    )


def _edge(
    source: int,
    target: int,
    relationship: VersionRelationshipKind,
    *,
    effective_on: date,
    observed_at: datetime = NOW,
) -> OfficialVersionRelationship:
    return OfficialVersionRelationship(
        from_registry_version_id=source,
        to_registry_version_id=target,
        relationship=relationship,
        effective_on=effective_on,
        observed_at=observed_at,
        source_url=f"https://official.example/lineage/{source}/{target}",
    )


def _request(
    *records: OfficialVersionRecord,
    mode: VersionStatusMode = VersionStatusMode.CURRENT,
    as_of: date | None = None,
    coverage: VersionEvidenceCoverage = VersionEvidenceCoverage.COMPLETE,
    relationships: tuple[OfficialVersionRelationship, ...] = (),
) -> VersionStatusRequest:
    return VersionStatusRequest(
        family_id=10,
        mode=mode,
        evaluated_at=NOW,
        as_of=as_of,
        coverage=coverage,
        records=records,
        relationships=relationships,
    )


def _status(
    decision: VersionStatusDecision,
    registry_id: int,
) -> ResolvedVersionStatus:
    return next(
        item
        for item in decision.resolved_statuses
        if item.registry_version_id == registry_id
    )


def test_current_version_uses_supersession_and_freshest_official_metadata() -> None:
    old = _record(1, available_on=date(2020, 1, 1))
    current = _record(2, available_on=date(2023, 6, 1))
    edge = _edge(
        2,
        1,
        VersionRelationshipKind.SUPERSEDES,
        effective_on=date(2023, 6, 1),
    )

    decision = resolve_version_status(
        _request(old, current, relationships=(edge,))
    )

    assert decision.outcome is VersionStatusOutcome.VALIDATED_CURRENT
    assert decision.health is VersionStatusHealth.HEALTHY
    assert decision.selected_registry_version_ids == (2,)
    assert decision.can_support_current_claim is True
    assert _status(decision, 1).status is DocumentLegalStatus.SUPERSEDED
    assert _status(decision, 2).status is DocumentLegalStatus.IN_FORCE
    assert decision.freshest_official_observation_at == NOW


def test_historical_as_of_excludes_later_version_and_transition() -> None:
    old = _record(1, available_on=date(2020, 1, 1))
    later = _record(2, available_on=date(2023, 6, 1))
    edge = _edge(
        2,
        1,
        VersionRelationshipKind.SUPERSEDES,
        effective_on=date(2023, 6, 1),
    )

    decision = resolve_version_status(
        _request(
            old,
            later,
            mode=VersionStatusMode.AS_OF,
            as_of=date(2022, 12, 31),
            relationships=(edge,),
        )
    )

    assert decision.outcome is VersionStatusOutcome.VALIDATED_HISTORICAL
    assert decision.selected_registry_version_ids == (1,)
    assert _status(decision, 1).status is DocumentLegalStatus.IN_FORCE
    assert decision.can_support_current_claim is False


def test_later_terminal_status_preserves_prior_historical_in_force_state() -> None:
    record = _record(
        1,
        available_on=date(2020, 1, 1),
        status=DocumentLegalStatus.REPEALED,
        status_effective_on=date(2025, 1, 1),
    )

    historical = resolve_version_status(
        _request(
            record,
            mode=VersionStatusMode.AS_OF,
            as_of=date(2024, 1, 1),
        )
    )
    current = resolve_version_status(_request(record))

    assert historical.outcome is VersionStatusOutcome.VALIDATED_HISTORICAL
    assert _status(historical, 1).status is DocumentLegalStatus.IN_FORCE
    assert current.outcome is VersionStatusOutcome.VALIDATED_CURRENT
    assert _status(current, 1).status is DocumentLegalStatus.REPEALED
    assert current.can_support_current_claim is True


def test_repeal_relationship_marks_target_without_erasing_repeal_notice() -> None:
    regulation = _record(1, available_on=date(2020, 1, 1))
    notice = _record(2, available_on=date(2025, 2, 1))
    edge = _edge(
        2,
        1,
        VersionRelationshipKind.REPEALS,
        effective_on=date(2025, 2, 1),
    )

    decision = resolve_version_status(
        _request(regulation, notice, relationships=(edge,))
    )

    assert decision.selected_registry_version_ids == (2,)
    assert _status(decision, 1).status is DocumentLegalStatus.REPEALED
    assert _status(decision, 1).supporting_relationships == (
        VersionRelationshipKind.REPEALS,
    )


def test_draft_mode_selects_newest_draft_or_consultation_only() -> None:
    in_force = _record(1, available_on=date(2024, 1, 1))
    draft = _record(
        2,
        available_on=date(2025, 1, 1),
        status=DocumentLegalStatus.DRAFT,
    )
    consultation = _record(
        3,
        available_on=date(2026, 1, 1),
        status=DocumentLegalStatus.CONSULTATION,
    )

    decision = resolve_version_status(
        _request(
            in_force,
            draft,
            consultation,
            mode=VersionStatusMode.DRAFT,
        )
    )

    assert decision.outcome is VersionStatusOutcome.VALIDATED_DRAFT
    assert decision.selected_registry_version_ids == (3,)
    assert decision.can_support_current_claim is False


def test_published_draft_remains_available_before_future_effective_date() -> None:
    draft = OfficialVersionRecord(
        registry_version_id=1,
        family_id=10,
        document_id=101,
        document_version_id=201,
        version_number=1,
        version_label="Draft",
        publication_date=date(2026, 1, 1),
        effective_date=date(2027, 1, 1),
        declared_status=DocumentLegalStatus.DRAFT,
        status_effective_on=date(2026, 1, 1),
        status_observed_at=NOW,
        status_source_url="https://official.example/draft",
    )

    decision = resolve_version_status(
        _request(draft, mode=VersionStatusMode.DRAFT)
    )

    assert decision.outcome is VersionStatusOutcome.VALIDATED_DRAFT
    assert decision.selected_registry_version_ids == (1,)


def test_healthy_draft_absence_is_no_match() -> None:
    decision = resolve_version_status(
        _request(
            _record(1),
            mode=VersionStatusMode.DRAFT,
        )
    )

    assert decision.outcome is VersionStatusOutcome.NO_MATCH
    assert decision.health is VersionStatusHealth.HEALTHY
    assert decision.safe_code is None


@pytest.mark.parametrize(
    ("coverage", "safe_code"),
    (
        (
            VersionEvidenceCoverage.PARTIAL,
            "VERSION_LINEAGE_PARTIAL",
        ),
        (
            VersionEvidenceCoverage.UNAVAILABLE,
            "VERSION_LINEAGE_UNAVAILABLE",
        ),
    ),
)
def test_incomplete_lineage_never_supports_current_claim(
    coverage: VersionEvidenceCoverage,
    safe_code: str,
) -> None:
    decision = resolve_version_status(
        _request(_record(1), coverage=coverage)
    )

    assert decision.outcome is VersionStatusOutcome.UNKNOWN
    assert decision.health is VersionStatusHealth.DEGRADED
    assert decision.can_support_current_claim is False
    assert decision.safe_code == safe_code


def test_newer_unknown_status_blocks_older_current_claim() -> None:
    known = _record(1, available_on=date(2020, 1, 1))
    unknown = _record(
        2,
        available_on=date(2025, 1, 1),
        status=DocumentLegalStatus.UNKNOWN,
    )

    decision = resolve_version_status(_request(known, unknown))

    assert decision.outcome is VersionStatusOutcome.UNKNOWN
    assert decision.safe_code == "VERSION_STATUS_UNKNOWN"
    assert decision.selected_registry_version_ids == ()


def test_same_date_competing_current_versions_are_contradictory() -> None:
    first = _record(1, available_on=date(2025, 1, 1))
    second = _record(2, available_on=date(2025, 1, 1))

    decision = resolve_version_status(_request(first, second))

    assert decision.outcome is VersionStatusOutcome.CONTRADICTORY
    assert decision.health is VersionStatusHealth.FAILED
    assert decision.safe_code == "VERSION_STATUS_CONTRADICTORY"


def test_multiple_in_force_versions_require_lineage_and_return_active_set() -> None:
    base = _record(1, available_on=date(2020, 1, 1))
    amendment = _record(2, available_on=date(2025, 1, 1))
    without_lineage = resolve_version_status(_request(base, amendment))
    with_lineage = resolve_version_status(
        _request(
            base,
            amendment,
            relationships=(
                _edge(
                    2,
                    1,
                    VersionRelationshipKind.AMENDS,
                    effective_on=date(2025, 1, 1),
                ),
            ),
        )
    )

    assert without_lineage.outcome is VersionStatusOutcome.CONTRADICTORY
    assert with_lineage.outcome is VersionStatusOutcome.VALIDATED_CURRENT
    assert with_lineage.selected_registry_version_ids == (2, 1)


def test_conflicting_terminal_relationships_are_contradictory() -> None:
    records = (
        _record(1, available_on=date(2020, 1, 1)),
        _record(2, available_on=date(2025, 1, 1)),
        _record(3, available_on=date(2025, 2, 1)),
    )
    relationships = (
        _edge(
            2,
            1,
            VersionRelationshipKind.SUPERSEDES,
            effective_on=date(2025, 3, 1),
        ),
        _edge(
            3,
            1,
            VersionRelationshipKind.REPEALS,
            effective_on=date(2025, 3, 1),
        ),
    )

    decision = resolve_version_status(
        _request(*records, relationships=relationships)
    )

    assert decision.outcome is VersionStatusOutcome.CONTRADICTORY
    assert decision.safe_code == "VERSION_STATUS_CONTRADICTORY"


def test_direct_status_and_lineage_use_date_precedence_and_ties_conflict() -> None:
    older_status = _record(
        1,
        available_on=date(2020, 1, 1),
        status=DocumentLegalStatus.REPEALED,
        status_effective_on=date(2024, 1, 1),
    )
    newer_notice = _record(2, available_on=date(2025, 1, 1))
    supersedes = _edge(
        2,
        1,
        VersionRelationshipKind.SUPERSEDES,
        effective_on=date(2025, 1, 1),
    )
    later_edge = resolve_version_status(
        _request(older_status, newer_notice, relationships=(supersedes,))
    )

    tied_status = _record(
        1,
        available_on=date(2020, 1, 1),
        status=DocumentLegalStatus.REPEALED,
        status_effective_on=date(2025, 1, 1),
    )
    tied = resolve_version_status(
        _request(tied_status, newer_notice, relationships=(supersedes,))
    )

    assert _status(later_edge, 1).status is DocumentLegalStatus.SUPERSEDED
    assert tied.outcome is VersionStatusOutcome.CONTRADICTORY


def test_cycle_missing_endpoint_and_family_mismatch_fail_closed() -> None:
    first = _record(1)
    second = _record(2)
    cycle = (
        _edge(
            1,
            2,
            VersionRelationshipKind.PARENT,
            effective_on=date(2024, 1, 1),
        ),
        _edge(
            2,
            1,
            VersionRelationshipKind.PARENT,
            effective_on=date(2024, 1, 1),
        ),
    )
    cycle_decision = resolve_version_status(
        _request(first, second, relationships=cycle)
    )
    missing_decision = resolve_version_status(
        _request(
            first,
            relationships=(
                _edge(
                    1,
                    99,
                    VersionRelationshipKind.PARENT,
                    effective_on=date(2024, 1, 1),
                ),
            ),
        )
    )
    family_decision = resolve_version_status(
        _request(first, _record(2, family_id=11))
    )

    assert cycle_decision.safe_code == "VERSION_LINEAGE_CYCLE"
    assert missing_decision.safe_code == "VERSION_LINEAGE_MISSING_ENDPOINT"
    assert family_decision.safe_code == "VERSION_LINEAGE_FAMILY_MISMATCH"
    assert {
        cycle_decision.outcome,
        missing_decision.outcome,
        family_decision.outcome,
    } == {VersionStatusOutcome.INVALID_LINEAGE}


def test_relationship_before_source_availability_is_invalid_lineage() -> None:
    first = _record(1, available_on=date(2020, 1, 1))
    later = _record(2, available_on=date(2025, 1, 1))
    decision = resolve_version_status(
        _request(
            first,
            later,
            relationships=(
                _edge(
                    2,
                    1,
                    VersionRelationshipKind.AMENDS,
                    effective_on=date(2024, 1, 1),
                ),
            ),
        )
    )

    assert decision.outcome is VersionStatusOutcome.INVALID_LINEAGE
    assert decision.safe_code == "VERSION_LINEAGE_INVALID_CHRONOLOGY"


def test_empty_complete_registry_is_healthy_no_match() -> None:
    decision = resolve_version_status(_request())

    assert decision.outcome is VersionStatusOutcome.NO_MATCH
    assert decision.health is VersionStatusHealth.HEALTHY
    assert decision.freshest_official_observation_at is None


def test_version_request_rejects_invalid_time_identity_and_duplicates() -> None:
    with pytest.raises(ValidationError, match="as-of"):
        _request(_record(1), mode=VersionStatusMode.AS_OF)
    with pytest.raises(ValidationError, match="future"):
        _request(
            _record(1),
            mode=VersionStatusMode.AS_OF,
            as_of=date(2027, 1, 1),
        )
    with pytest.raises(ValidationError, match="future"):
        _request(
            _record(
                1,
                observed_at=datetime(2027, 1, 1, tzinfo=UTC),
            )
        )
    with pytest.raises(ValidationError, match="Registry version IDs"):
        _request(_record(1), _record(1))
    with pytest.raises(ValidationError, match="timezone-aware"):
        OfficialVersionRecord(
            **{
                **_record(1).model_dump(),
                "status_observed_at": datetime(2026, 1, 1),
            }
        )
    with pytest.raises(ValidationError, match="self-referential"):
        _edge(
            1,
            1,
            VersionRelationshipKind.PARENT,
            effective_on=date(2025, 1, 1),
        )


def test_decision_contract_rejects_health_safe_code_and_claim_drift() -> None:
    base = resolve_version_status(_request(_record(1)))

    with pytest.raises(ValidationError):
        VersionStatusDecision(
            **{
                **base.model_dump(),
                "health": VersionStatusHealth.FAILED,
            }
        )
    with pytest.raises(ValidationError):
        VersionStatusDecision(
            **{
                **base.model_dump(),
                "safe_code": "SHOULD_NOT_EXIST",
            }
        )
    with pytest.raises(ValidationError):
        VersionStatusDecision(
            **{
                **base.model_dump(),
                "can_support_current_claim": False,
            }
        )


def test_version_status_is_deterministic_strict_and_input_immutable() -> None:
    request = _request(_record(1))
    first = resolve_version_status(request)
    second = resolve_version_status(request)

    assert first == second
    assert first.model_dump_json() == second.model_dump_json()
    assert request.records[0].declared_status is DocumentLegalStatus.IN_FORCE
    with pytest.raises(ValidationError):
        VersionStatusDecision.model_validate(
            {**first.model_dump(), "extra": "forbidden"}
        )


def test_equivalent_snapshot_order_produces_identical_decision() -> None:
    first = _record(1, available_on=date(2020, 1, 1))
    second = _record(2, available_on=date(2023, 1, 1))
    third = _record(3, available_on=date(2025, 1, 1))
    relationships = (
        _edge(
            2,
            1,
            VersionRelationshipKind.AMENDS,
            effective_on=date(2023, 1, 1),
        ),
        _edge(
            3,
            2,
            VersionRelationshipKind.AMENDS,
            effective_on=date(2025, 1, 1),
        ),
    )

    ordered = resolve_version_status(
        _request(first, second, third, relationships=relationships)
    )
    reversed_snapshot = resolve_version_status(
        _request(
            third,
            second,
            first,
            relationships=tuple(reversed(relationships)),
        )
    )

    assert ordered == reversed_snapshot
    assert ordered.selected_registry_version_ids == (3, 2, 1)
