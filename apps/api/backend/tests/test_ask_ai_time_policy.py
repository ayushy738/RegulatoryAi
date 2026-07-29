from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from backend.ask.decision import (
    BREAKING_HOURS,
    NEWS_DEFAULT_DAYS,
    RECENT_DAYS,
    Intent,
    TimeDimension,
    TimeInterpretation,
    normalize_time,
)

NOW = datetime(2026, 7, 27, 20, 30, tzinfo=UTC)


@pytest.mark.parametrize(
    ("expression", "start", "end", "rule"),
    [
        (
            "2026-07-15",
            "2026-07-15T00:00:00+05:30",
            "2026-07-16T00:00:00+05:30",
            "explicit_absolute",
        ),
        (
            "2023",
            "2023-01-01T00:00:00+05:30",
            "2024-01-01T00:00:00+05:30",
            "explicit_absolute",
        ),
        (
            "2026-07-01 to 2026-07-15",
            "2026-07-01T00:00:00+05:30",
            "2026-07-16T00:00:00+05:30",
            "explicit_range",
        ),
        (
            "before 2021",
            None,
            "2021-01-01T00:00:00+05:30",
            "explicit_range",
        ),
        (
            "after 2021",
            "2022-01-01T00:00:00+05:30",
            None,
            "explicit_range",
        ),
        (
            "since 2021",
            "2021-01-01T00:00:00+05:30",
            None,
            "explicit_range",
        ),
        (
            "today",
            "2026-07-28T00:00:00+05:30",
            "2026-07-29T00:00:00+05:30",
            "relative_period",
        ),
        (
            "this week",
            "2026-07-27T00:00:00+05:30",
            "2026-08-03T00:00:00+05:30",
            "relative_period",
        ),
        (
            "this month",
            "2026-07-01T00:00:00+05:30",
            "2026-08-01T00:00:00+05:30",
            "relative_period",
        ),
    ],
)
def test_absolute_relative_and_calendar_ranges_are_half_open(
    expression: str,
    start: str | None,
    end: str | None,
    rule: str,
) -> None:
    result = normalize_time(
        expression,
        now=NOW,
        user_timezone="Asia/Kolkata",
    )

    assert (result.start_at.isoformat() if result.start_at else None) == start
    assert (result.end_at.isoformat() if result.end_at else None) == end
    assert result.precedence_rule == rule
    assert result.end_exclusive is True


def test_time_zone_changes_the_local_calendar_day() -> None:
    kolkata = normalize_time("today", now=NOW, user_timezone="Asia/Kolkata")
    new_york = normalize_time("today", now=NOW, user_timezone="America/New_York")

    assert kolkata.start_at is not None
    assert new_york.start_at is not None
    assert kolkata.start_at.date().isoformat() == "2026-07-28"
    assert new_york.start_at.date().isoformat() == "2026-07-27"


def test_dst_calendar_day_uses_local_zone_boundaries() -> None:
    result = normalize_time(
        "today",
        now=datetime(2026, 3, 8, 16, tzinfo=UTC),
        user_timezone="America/New_York",
    )

    assert result.start_at is not None
    assert result.end_at is not None
    assert result.start_at.isoformat() == "2026-03-08T00:00:00-05:00"
    assert result.end_at.isoformat() == "2026-03-09T00:00:00-04:00"


def test_leap_month_uses_real_calendar_boundary() -> None:
    result = normalize_time(
        "this month",
        now=datetime(2028, 2, 15, tzinfo=UTC),
        user_timezone="UTC",
    )

    assert result.start_at == datetime(2028, 2, 1, tzinfo=UTC)
    assert result.end_at == datetime(2028, 3, 1, tzinfo=UTC)


def test_rolling_recent_and_breaking_windows_end_at_injected_now() -> None:
    recent = normalize_time("recent", now=NOW, user_timezone="Asia/Kolkata")
    breaking = normalize_time("breaking", now=NOW, user_timezone="Asia/Kolkata")

    assert recent.end_at is not None
    assert recent.start_at == recent.end_at - timedelta(days=RECENT_DAYS)
    assert recent.freshness_requirements == ("rolling_90_days",)
    assert breaking.end_at is not None
    assert breaking.start_at == breaking.end_at - timedelta(hours=BREAKING_HOURS)
    assert breaking.live_eligible is True

    dst_breaking = normalize_time(
        "breaking",
        now=datetime(2026, 3, 9, 12, tzinfo=UTC),
        user_timezone="America/New_York",
    )
    assert dst_breaking.start_at is not None
    assert dst_breaking.end_at is not None
    assert (
        dst_breaking.end_at.astimezone(UTC) - dst_breaking.start_at.astimezone(UTC)
        == timedelta(hours=BREAKING_HOURS)
    )


@pytest.mark.parametrize(
    ("expression", "dimension", "statuses", "live", "rule"),
    [
        (
            "latest",
            TimeDimension.PUBLICATION_OR_ISSUE,
            ("latest", "current_validity_check"),
            True,
            "current_status",
        ),
        (
            "current",
            TimeDimension.VALIDITY_PERIOD,
            ("in_force", "operative"),
            False,
            "current_status",
        ),
        (
            "draft",
            TimeDimension.DOCUMENT_VERSION,
            ("draft",),
            False,
            "document_status",
        ),
        (
            "consultation",
            TimeDimension.CONSULTATION,
            ("open", "current", "recent_closed"),
            True,
            "document_status",
        ),
        (
            "latest draft",
            TimeDimension.DOCUMENT_VERSION,
            ("latest", "current_validity_check", "draft"),
            True,
            "current_status",
        ),
    ],
)
def test_current_and_document_status_semantics_are_distinct(
    expression: str,
    dimension: TimeDimension,
    statuses: tuple[str, ...],
    live: bool,
    rule: str,
) -> None:
    result = normalize_time(
        expression,
        now=NOW,
        user_timezone="Asia/Kolkata",
    )

    assert result.dimension == dimension
    assert result.status_filters == statuses
    assert result.live_eligible is live
    assert result.precedence_rule == rule


@pytest.mark.parametrize(
    ("intent", "dimension", "statuses", "days", "live"),
    [
        (
            Intent.DEFINITION,
            TimeDimension.VALIDITY_PERIOD,
            ("current",),
            None,
            False,
        ),
        (
            Intent.ENTITY_LOOKUP,
            TimeDimension.VALIDITY_PERIOD,
            ("current",),
            None,
            False,
        ),
        (
            Intent.REGULATION_LOOKUP,
            TimeDimension.VALIDITY_PERIOD,
            ("current", "in_force"),
            None,
            False,
        ),
        (
            Intent.DEADLINE,
            TimeDimension.COMPLIANCE_DEADLINE,
            ("active", "upcoming"),
            None,
            False,
        ),
        (
            Intent.COMPLIANCE_QUESTION,
            TimeDimension.VALIDITY_PERIOD,
            ("current", "in_force"),
            None,
            False,
        ),
        (
            Intent.AMENDMENT,
            TimeDimension.EFFECTIVE,
            ("most_recent_effective",),
            None,
            False,
        ),
        (
            Intent.TIMELINE,
            TimeDimension.EVENT,
            ("full_known_range",),
            None,
            False,
        ),
        (
            Intent.NEWS,
            TimeDimension.EVENT,
            (),
            NEWS_DEFAULT_DAYS,
            True,
        ),
        (
            Intent.CONSULTATION,
            TimeDimension.CONSULTATION,
            ("open", "recent_closed"),
            RECENT_DAYS,
            True,
        ),
        (
            Intent.SUMMARIZATION,
            None,
            ("selected_source_context",),
            None,
            False,
        ),
    ],
)
def test_intent_defaults_are_visible_and_policy_versionable(
    intent: Intent,
    dimension: TimeDimension | None,
    statuses: tuple[str, ...],
    days: int | None,
    live: bool,
) -> None:
    result = normalize_time(
        None,
        now=NOW,
        user_timezone="Asia/Kolkata",
        intent=intent,
    )

    assert result.dimension == dimension
    assert result.status_filters == statuses
    assert result.assumed is True
    assert result.precedence_rule == "intent_default"
    assert result.live_eligible is live
    if days is not None:
        assert result.start_at is not None
        assert result.end_at is not None
        assert result.start_at == result.end_at - timedelta(days=days)


def test_missing_default_and_invalid_inputs_fail_closed() -> None:
    no_filter = normalize_time(
        None,
        now=NOW,
        user_timezone="Asia/Kolkata",
        intent=Intent.GENERAL_QUESTION,
    )
    assert no_filter.precedence_rule == "no_time_filter"
    assert no_filter.assumed is False

    with pytest.raises(ValueError, match="timezone-aware"):
        normalize_time(
            "today",
            now=datetime(2026, 7, 27),
            user_timezone="Asia/Kolkata",
        )
    with pytest.raises(ValueError, match="Unknown IANA"):
        normalize_time("today", now=NOW, user_timezone="Mars/Olympus")
    with pytest.raises(ValueError, match="Unsupported"):
        normalize_time("sometime soon", now=NOW, user_timezone="Asia/Kolkata")
    with pytest.raises(ValueError, match="reversed"):
        normalize_time(
            "2026-08-01 to 2026-07-01",
            now=NOW,
            user_timezone="Asia/Kolkata",
        )
    with pytest.raises(ValueError, match="timezone-aware"):
        TimeInterpretation(
            start_at=datetime(2026, 7, 27),
            user_timezone="Asia/Kolkata",
        )
