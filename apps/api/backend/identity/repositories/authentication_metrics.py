from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from backend.identity.models import AuthenticationMetricModel


class AuthenticationMetricsRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def increment(
        self,
        *,
        source: str,
        outcome: str,
        reason_code: str | None = None,
        observed_at: datetime | None = None,
    ) -> None:
        timestamp = observed_at or datetime.now(UTC)
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=UTC)
        bucket = timestamp.astimezone(UTC).replace(minute=0, second=0, microsecond=0)
        values = {
            "bucket_started_at": bucket,
            "source": source,
            "outcome": outcome,
            "reason_code": reason_code or "",
            "observation_count": 1,
            "updated_at": timestamp,
        }
        dialect_name = self._session.bind.dialect.name if self._session.bind else ""
        insert_factory = (
            sqlite_insert if dialect_name == "sqlite" else postgresql_insert
        )
        statement = insert_factory(AuthenticationMetricModel).values(**values)
        statement = statement.on_conflict_do_update(
            index_elements=[
                AuthenticationMetricModel.bucket_started_at,
                AuthenticationMetricModel.source,
                AuthenticationMetricModel.outcome,
                AuthenticationMetricModel.reason_code,
            ],
            set_={
                "observation_count": AuthenticationMetricModel.observation_count + 1,
                "updated_at": timestamp,
            },
        )
        self._session.execute(statement)
        self._session.flush()
