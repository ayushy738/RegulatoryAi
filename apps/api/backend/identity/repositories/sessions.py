from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from backend.identity.models import AuthSessionModel


class SessionsRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, auth_session: AuthSessionModel) -> AuthSessionModel:
        self._session.add(auth_session)
        self._session.flush()
        return auth_session

    def get(self, sid: UUID) -> AuthSessionModel | None:
        return self._session.get(AuthSessionModel, sid)

    def get_for_update(self, sid: UUID) -> AuthSessionModel | None:
        statement = (
            select(AuthSessionModel)
            .where(AuthSessionModel.sid == sid)
            .with_for_update()
        )
        return self._session.execute(statement).scalar_one_or_none()

    def list_for_user(self, user_id: UUID) -> list[AuthSessionModel]:
        statement = (
            select(AuthSessionModel)
            .where(AuthSessionModel.user_id == user_id)
            .order_by(AuthSessionModel.created_at.desc())
        )
        return list(self._session.execute(statement).scalars())

    def save(self, auth_session: AuthSessionModel) -> AuthSessionModel:
        persisted = self._session.merge(auth_session)
        self._session.flush()
        return persisted

    def revoke_active_for_user(
        self,
        user_id: UUID,
        *,
        revoked_at: datetime,
        reason: str,
        except_sid: UUID | None = None,
    ) -> int:
        statement = (
            update(AuthSessionModel)
            .where(
                AuthSessionModel.user_id == user_id,
                AuthSessionModel.revoked_at.is_(None),
            )
            .values(revoked_at=revoked_at, revocation_reason=reason)
        )
        if except_sid is not None:
            statement = statement.where(AuthSessionModel.sid != except_sid)
        result = self._session.execute(statement)
        self._session.flush()
        return int(result.rowcount or 0)

    def delete(self, auth_session: AuthSessionModel) -> None:
        self._session.delete(auth_session)
        self._session.flush()
