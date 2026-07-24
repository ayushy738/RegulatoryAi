from __future__ import annotations

from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session


class IdentityReconciliationRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def has_drift(self, user_id: UUID) -> bool:
        statement = text(
            """
            select exists (
              select 1
              from identity.coexistence_drift
              where user_id = :user_id
            )
            """
        )
        parameter = (
            str(user_id)
            if self._session.bind is not None
            and self._session.bind.dialect.name == "sqlite"
            else user_id
        )
        return bool(self._session.execute(statement, {"user_id": parameter}).scalar_one())
