from __future__ import annotations

import calendar
import re
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from backend.ask.decision.models import Intent, TimeDimension, TimeInterpretation

RECENT_DAYS = 90
NEWS_DEFAULT_DAYS = 30
BREAKING_HOURS = 72

_YEAR = re.compile(r"^(?P<year>\d{4})$")
_ABSOLUTE_DATE = re.compile(r"^(?P<date>\d{4}-\d{2}-\d{2})$")
_DATE_RANGE = re.compile(
    r"^(?P<start>\d{4}-\d{2}-\d{2})\s+(?:to|through)\s+"
    r"(?P<end>\d{4}-\d{2}-\d{2})$"
)
_YEAR_BOUND = re.compile(r"^(?P<operator>before|after|since)\s+(?P<year>\d{4})$")


def normalize_time(
    expression: str | None,
    *,
    now: datetime,
    user_timezone: str,
    intent: Intent | None = None,
) -> TimeInterpretation:
    local_now, zone = _localized_now(now, user_timezone)
    normalized = " ".join(expression.lower().split()) if expression else ""
    if not normalized:
        return _intent_default(
            intent=intent,
            local_now=local_now,
            user_timezone=user_timezone,
        )

    if normalized in {"latest draft", "draft latest"}:
        return _interpretation(
            dimension=TimeDimension.DOCUMENT_VERSION,
            start_at=None,
            end_at=local_now,
            user_timezone=user_timezone,
            source_expression=normalized,
            status_filters=("latest", "current_validity_check", "draft"),
            precedence_rule="current_status",
            freshness_requirements=("newest_relevant", "current_status_validation"),
            live_eligible=True,
        )

    range_match = _DATE_RANGE.fullmatch(normalized)
    if range_match is not None:
        start_date = date.fromisoformat(range_match["start"])
        end_date = date.fromisoformat(range_match["end"])
        if end_date < start_date:
            raise ValueError("The explicit date range is reversed")
        return _interpretation(
            dimension=_dimension_for_intent(intent),
            start_at=_midnight(start_date, zone),
            end_at=_midnight(end_date + timedelta(days=1), zone),
            user_timezone=user_timezone,
            source_expression=normalized,
            precedence_rule="explicit_range",
        )

    absolute_match = _ABSOLUTE_DATE.fullmatch(normalized)
    if absolute_match is not None:
        selected_date = date.fromisoformat(absolute_match["date"])
        return _interpretation(
            dimension=_dimension_for_intent(intent),
            start_at=_midnight(selected_date, zone),
            end_at=_midnight(selected_date + timedelta(days=1), zone),
            user_timezone=user_timezone,
            source_expression=normalized,
            precedence_rule="explicit_absolute",
        )

    year_match = _YEAR.fullmatch(normalized)
    if year_match is not None:
        year = int(year_match["year"])
        return _interpretation(
            dimension=_dimension_for_intent(intent),
            start_at=_midnight(date(year, 1, 1), zone),
            end_at=_midnight(date(year + 1, 1, 1), zone),
            user_timezone=user_timezone,
            source_expression=normalized,
            precedence_rule="explicit_absolute",
        )

    bound_match = _YEAR_BOUND.fullmatch(normalized)
    if bound_match is not None:
        year = int(bound_match["year"])
        operator = bound_match["operator"]
        start_at = None
        end_at = None
        if operator == "before":
            end_at = _midnight(date(year, 1, 1), zone)
        elif operator == "after":
            start_at = _midnight(date(year + 1, 1, 1), zone)
        else:
            start_at = _midnight(date(year, 1, 1), zone)
        return _interpretation(
            dimension=_dimension_for_intent(intent),
            start_at=start_at,
            end_at=end_at,
            user_timezone=user_timezone,
            source_expression=normalized,
            precedence_rule="explicit_range",
        )

    if normalized == "today":
        start_date = local_now.date()
        return _interpretation(
            dimension=_dimension_for_intent(intent),
            start_at=_midnight(start_date, zone),
            end_at=_midnight(start_date + timedelta(days=1), zone),
            user_timezone=user_timezone,
            source_expression=normalized,
            precedence_rule="relative_period",
        )
    if normalized == "this week":
        start_date = local_now.date() - timedelta(days=local_now.weekday())
        return _interpretation(
            dimension=_dimension_for_intent(intent),
            start_at=_midnight(start_date, zone),
            end_at=_midnight(start_date + timedelta(days=7), zone),
            user_timezone=user_timezone,
            source_expression=normalized,
            precedence_rule="relative_period",
            freshness_requirements=("iso_local_calendar_week",),
        )
    if normalized == "this month":
        start_date = local_now.date().replace(day=1)
        _, last_day = calendar.monthrange(start_date.year, start_date.month)
        end_date = start_date.replace(day=last_day) + timedelta(days=1)
        return _interpretation(
            dimension=_dimension_for_intent(intent),
            start_at=_midnight(start_date, zone),
            end_at=_midnight(end_date, zone),
            user_timezone=user_timezone,
            source_expression=normalized,
            precedence_rule="relative_period",
        )
    if normalized == "recent":
        return _interpretation(
            dimension=_dimension_for_intent(intent),
            start_at=_elapsed_start(local_now, timedelta(days=RECENT_DAYS)),
            end_at=local_now,
            user_timezone=user_timezone,
            source_expression=normalized,
            precedence_rule="relative_period",
            freshness_requirements=("rolling_90_days",),
        )
    if normalized == "breaking":
        return _interpretation(
            dimension=TimeDimension.EVENT,
            start_at=_elapsed_start(local_now, timedelta(hours=BREAKING_HOURS)),
            end_at=local_now,
            user_timezone=user_timezone,
            source_expression=normalized,
            precedence_rule="current_status",
            freshness_requirements=("breaking_72_hours",),
            live_eligible=True,
        )
    if normalized == "latest":
        return _interpretation(
            dimension=_dimension_for_intent(intent),
            start_at=None,
            end_at=local_now,
            user_timezone=user_timezone,
            source_expression=normalized,
            status_filters=("latest", "current_validity_check"),
            precedence_rule="current_status",
            freshness_requirements=("newest_relevant", "current_status_validation"),
            live_eligible=True,
        )
    if normalized == "current":
        return _interpretation(
            dimension=TimeDimension.VALIDITY_PERIOD,
            start_at=None,
            end_at=local_now,
            user_timezone=user_timezone,
            source_expression=normalized,
            status_filters=("in_force", "operative"),
            precedence_rule="current_status",
            freshness_requirements=("current_status_validation",),
        )
    if normalized == "draft":
        return _interpretation(
            dimension=TimeDimension.DOCUMENT_VERSION,
            start_at=None,
            end_at=None,
            user_timezone=user_timezone,
            source_expression=normalized,
            status_filters=("draft",),
            precedence_rule="document_status",
        )
    if normalized == "consultation":
        return _interpretation(
            dimension=TimeDimension.CONSULTATION,
            start_at=_elapsed_start(local_now, timedelta(days=RECENT_DAYS)),
            end_at=local_now,
            user_timezone=user_timezone,
            source_expression=normalized,
            status_filters=("open", "current", "recent_closed"),
            precedence_rule="document_status",
            freshness_requirements=("open_first", "closed_within_90_days"),
            live_eligible=True,
        )
    raise ValueError(f"Unsupported time expression: {expression}")


def _intent_default(
    *,
    intent: Intent | None,
    local_now: datetime,
    user_timezone: str,
) -> TimeInterpretation:
    if intent == Intent.DEFINITION:
        return _interpretation(
            dimension=TimeDimension.VALIDITY_PERIOD,
            start_at=None,
            end_at=local_now,
            user_timezone=user_timezone,
            source_expression=None,
            status_filters=("current",),
            precedence_rule="intent_default",
            freshness_requirements=("note_material_superseded_meaning",),
            assumed=True,
        )
    if intent == Intent.ENTITY_LOOKUP:
        return _interpretation(
            dimension=TimeDimension.VALIDITY_PERIOD,
            start_at=None,
            end_at=local_now,
            user_timezone=user_timezone,
            source_expression=None,
            status_filters=("current",),
            precedence_rule="intent_default",
            freshness_requirements=("bounded_recent_update_section",),
            assumed=True,
        )
    if intent == Intent.REGULATION_LOOKUP:
        return _interpretation(
            dimension=TimeDimension.VALIDITY_PERIOD,
            start_at=None,
            end_at=local_now,
            user_timezone=user_timezone,
            source_expression=None,
            status_filters=("current", "in_force"),
            precedence_rule="intent_default",
            freshness_requirements=("historical_versions_available",),
            assumed=True,
        )
    if intent == Intent.DEADLINE:
        return _interpretation(
            dimension=TimeDimension.COMPLIANCE_DEADLINE,
            start_at=local_now,
            end_at=None,
            user_timezone=user_timezone,
            source_expression=None,
            status_filters=("active", "upcoming"),
            precedence_rule="intent_default",
            freshness_requirements=(
                "validate_extensions_withdrawals_supersession",
                "elapsed_when_relevant",
            ),
            assumed=True,
        )
    if intent == Intent.COMPLIANCE_QUESTION:
        return _interpretation(
            dimension=TimeDimension.VALIDITY_PERIOD,
            start_at=None,
            end_at=local_now,
            user_timezone=user_timezone,
            source_expression=None,
            status_filters=("current", "in_force"),
            precedence_rule="intent_default",
            freshness_requirements=("current_as_of_answer_time",),
            assumed=True,
        )
    if intent == Intent.AMENDMENT:
        return _interpretation(
            dimension=TimeDimension.EFFECTIVE,
            start_at=None,
            end_at=local_now,
            user_timezone=user_timezone,
            source_expression=None,
            status_filters=("most_recent_effective",),
            precedence_rule="intent_default",
            assumed=True,
        )
    if intent == Intent.TIMELINE:
        return _interpretation(
            dimension=TimeDimension.EVENT,
            start_at=None,
            end_at=local_now,
            user_timezone=user_timezone,
            source_expression=None,
            status_filters=("full_known_range",),
            precedence_rule="intent_default",
            assumed=True,
        )
    if intent == Intent.NEWS:
        return _interpretation(
            dimension=TimeDimension.EVENT,
            start_at=_elapsed_start(local_now, timedelta(days=NEWS_DEFAULT_DAYS)),
            end_at=local_now,
            user_timezone=user_timezone,
            source_expression=None,
            precedence_rule="intent_default",
            freshness_requirements=("rolling_30_days",),
            live_eligible=True,
            assumed=True,
        )
    if intent == Intent.CONSULTATION:
        return _interpretation(
            dimension=TimeDimension.CONSULTATION,
            start_at=_elapsed_start(local_now, timedelta(days=RECENT_DAYS)),
            end_at=local_now,
            user_timezone=user_timezone,
            source_expression=None,
            status_filters=("open", "recent_closed"),
            precedence_rule="intent_default",
            freshness_requirements=("open_first", "closed_within_90_days"),
            live_eligible=True,
            assumed=True,
        )
    if intent == Intent.SUMMARIZATION:
        return _interpretation(
            dimension=None,
            start_at=None,
            end_at=None,
            user_timezone=user_timezone,
            source_expression=None,
            status_filters=("selected_source_context",),
            precedence_rule="intent_default",
            assumed=True,
        )
    return _interpretation(
        dimension=None,
        start_at=None,
        end_at=None,
        user_timezone=user_timezone,
        source_expression=None,
        precedence_rule="no_time_filter",
        assumed=False,
    )


def _localized_now(now: datetime, user_timezone: str) -> tuple[datetime, ZoneInfo]:
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("The injected clock must be timezone-aware")
    try:
        zone = ZoneInfo(user_timezone)
    except ZoneInfoNotFoundError as exc:
        raise ValueError(f"Unknown IANA time zone: {user_timezone}") from exc
    return now.astimezone(zone), zone


def _midnight(selected_date: date, zone: ZoneInfo) -> datetime:
    return datetime.combine(selected_date, time.min, tzinfo=zone)


def _elapsed_start(local_now: datetime, delta: timedelta) -> datetime:
    return (local_now.astimezone(UTC) - delta).astimezone(local_now.tzinfo)


def _dimension_for_intent(intent: Intent | None) -> TimeDimension:
    if intent == Intent.DEADLINE:
        return TimeDimension.COMPLIANCE_DEADLINE
    if intent == Intent.CONSULTATION:
        return TimeDimension.CONSULTATION
    if intent == Intent.AMENDMENT:
        return TimeDimension.EFFECTIVE
    if intent in {Intent.NEWS, Intent.TIMELINE}:
        return TimeDimension.EVENT
    return TimeDimension.PUBLICATION_OR_ISSUE


def _interpretation(
    *,
    dimension: TimeDimension | None,
    start_at: datetime | None,
    end_at: datetime | None,
    user_timezone: str,
    source_expression: str | None,
    status_filters: tuple[str, ...] = (),
    precedence_rule: str,
    freshness_requirements: tuple[str, ...] = (),
    live_eligible: bool = False,
    assumed: bool = False,
) -> TimeInterpretation:
    return TimeInterpretation(
        dimension=dimension,
        start_at=start_at,
        end_at=end_at,
        status_filters=status_filters,
        user_timezone=user_timezone,
        source_expression=source_expression,
        assumed=assumed,
        end_exclusive=True,
        precedence_rule=precedence_rule,
        freshness_requirements=freshness_requirements,
        live_eligible=live_eligible,
    )
