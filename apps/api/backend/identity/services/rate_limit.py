from __future__ import annotations

from datetime import UTC, datetime, timedelta

from backend.identity.exceptions import RateLimitExceededError
from backend.identity.models import AuthenticationRateLimitModel
from backend.identity.repositories.rate_limits import AuthenticationRateLimitsRepository


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


class AuthenticationRateLimitService:
    def __init__(self, repository: AuthenticationRateLimitsRepository) -> None:
        self._repository = repository

    def consume(
        self,
        *,
        scope: str,
        subject_hash: bytes,
        limit: int,
        window: timedelta,
        now: datetime | None = None,
    ) -> None:
        observed_at = _as_utc(now or datetime.now(UTC))
        self._repository.lock_subject(subject_hash)
        record = self._repository.get_for_update(scope, subject_hash)
        if record is None:
            self._repository.add(
                AuthenticationRateLimitModel(
                    scope=scope,
                    subject_hash=subject_hash,
                    window_started_at=observed_at,
                    attempts=1,
                    updated_at=observed_at,
                )
            )
            return

        blocked_until = (
            _as_utc(record.blocked_until) if record.blocked_until is not None else None
        )
        window_started_at = _as_utc(record.window_started_at)
        if blocked_until is not None and blocked_until > observed_at:
            retry_after = int((blocked_until - observed_at).total_seconds()) + 1
            raise RateLimitExceededError(retry_after)

        if observed_at >= window_started_at + window:
            record.window_started_at = observed_at
            record.attempts = 1
            record.blocked_until = None
            record.updated_at = observed_at
            self._repository.save(record)
            return

        if record.attempts >= limit:
            record.blocked_until = observed_at + window
            record.updated_at = observed_at
            self._repository.save(record)
            raise RateLimitExceededError(int(window.total_seconds()))

        record.attempts += 1
        record.updated_at = observed_at
        self._repository.save(record)
