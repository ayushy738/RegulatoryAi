from __future__ import annotations

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from backend.identity.models import AuthenticationRateLimitModel


class AuthenticationRateLimitsRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def lock_subject(self, subject_hash: bytes) -> None:
        if self._session.bind is None or self._session.bind.dialect.name != "postgresql":
            return
        lock_key = int.from_bytes(subject_hash[:8], byteorder="big", signed=True)
        self._session.execute(
            text("select pg_advisory_xact_lock(:lock_key)"),
            {"lock_key": lock_key},
        )

    def get_for_update(
        self,
        scope: str,
        subject_hash: bytes,
    ) -> AuthenticationRateLimitModel | None:
        statement = (
            select(AuthenticationRateLimitModel)
            .where(
                AuthenticationRateLimitModel.scope == scope,
                AuthenticationRateLimitModel.subject_hash == subject_hash,
            )
            .with_for_update()
        )
        return self._session.execute(statement).scalar_one_or_none()

    def add(
        self,
        rate_limit: AuthenticationRateLimitModel,
    ) -> AuthenticationRateLimitModel:
        self._session.add(rate_limit)
        self._session.flush()
        return rate_limit

    def save(
        self,
        rate_limit: AuthenticationRateLimitModel,
    ) -> AuthenticationRateLimitModel:
        persisted = self._session.merge(rate_limit)
        self._session.flush()
        return persisted
