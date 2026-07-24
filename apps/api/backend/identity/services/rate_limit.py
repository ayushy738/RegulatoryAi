from __future__ import annotations

import hashlib
import math
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
        window_seconds = window.total_seconds()
        if limit <= 0 or window_seconds <= 0:
            raise ValueError("Rate-limit values must be positive")

        bucket_epoch = int(
            math.floor(observed_at.timestamp() / window_seconds) * window_seconds
        )
        bucket_started_at = datetime.fromtimestamp(bucket_epoch, tz=UTC)
        elapsed = (observed_at - bucket_started_at).total_seconds()
        previous_weight = max(0.0, (window_seconds - elapsed) / window_seconds)
        current_subject_hash = self._bucket_hash(subject_hash, bucket_epoch)
        previous_subject_hash = self._bucket_hash(
            subject_hash,
            bucket_epoch - int(window_seconds),
        )

        self._repository.lock_subject(subject_hash)
        current = self._repository.get_for_update(scope, current_subject_hash)
        previous = self._repository.get_for_update(scope, previous_subject_hash)

        blocked_until = (
            _as_utc(current.blocked_until)
            if current is not None and current.blocked_until is not None
            else None
        )
        if blocked_until is not None and blocked_until > observed_at:
            retry_after = int((blocked_until - observed_at).total_seconds()) + 1
            raise RateLimitExceededError(retry_after)

        current_attempts = current.attempts if current is not None else 0
        previous_attempts = previous.attempts if previous is not None else 0
        estimated_attempts = current_attempts + previous_attempts * previous_weight
        if estimated_attempts + 1 > limit:
            if current is None:
                current = self._repository.add(
                    AuthenticationRateLimitModel(
                        scope=scope,
                        subject_hash=current_subject_hash,
                        window_started_at=bucket_started_at,
                        attempts=0,
                        updated_at=observed_at,
                    )
                )
            current.blocked_until = observed_at + window
            current.updated_at = observed_at
            self._repository.save(current)
            raise RateLimitExceededError(int(window.total_seconds()))

        if current is None:
            self._repository.add(
                AuthenticationRateLimitModel(
                    scope=scope,
                    subject_hash=current_subject_hash,
                    window_started_at=bucket_started_at,
                    attempts=1,
                    updated_at=observed_at,
                )
            )
            return
        current.attempts += 1
        current.blocked_until = None
        current.updated_at = observed_at
        self._repository.save(current)

    @staticmethod
    def _bucket_hash(subject_hash: bytes, bucket_epoch: int) -> bytes:
        return hashlib.sha256(
            b"sliding-rate-limit\x00"
            + subject_hash
            + bucket_epoch.to_bytes(8, byteorder="big", signed=True)
        ).digest()
