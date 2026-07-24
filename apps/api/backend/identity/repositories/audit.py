from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.identity.models import AuditEventModel


class AuditRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def append(self, event: AuditEventModel) -> AuditEventModel:
        self._session.add(event)
        self._session.flush()
        return event

    def get(self, event_id: UUID) -> AuditEventModel | None:
        return self._session.get(AuditEventModel, event_id)

    def list(
        self,
        *,
        action: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[AuditEventModel]:
        statement = select(AuditEventModel)
        if action is not None:
            statement = statement.where(AuditEventModel.action == action)
        statement = (
            statement.order_by(AuditEventModel.occurred_at.desc()).limit(limit).offset(offset)
        )
        return list(self._session.execute(statement).scalars())
