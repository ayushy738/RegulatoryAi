from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.identity.models import PasswordResetTokenModel


class PasswordResetRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, token: PasswordResetTokenModel) -> PasswordResetTokenModel:
        self._session.add(token)
        self._session.flush()
        return token

    def get(self, token_id: UUID) -> PasswordResetTokenModel | None:
        return self._session.get(PasswordResetTokenModel, token_id)

    def get_by_hash(self, token_hash: bytes) -> PasswordResetTokenModel | None:
        statement = select(PasswordResetTokenModel).where(
            PasswordResetTokenModel.token_hash == token_hash
        )
        return self._session.execute(statement).scalar_one_or_none()

    def list_for_user(self, user_id: UUID) -> list[PasswordResetTokenModel]:
        statement = (
            select(PasswordResetTokenModel)
            .where(PasswordResetTokenModel.user_id == user_id)
            .order_by(PasswordResetTokenModel.created_at.desc())
        )
        return list(self._session.execute(statement).scalars())

    def save(self, token: PasswordResetTokenModel) -> PasswordResetTokenModel:
        persisted = self._session.merge(token)
        self._session.flush()
        return persisted

    def delete(self, token: PasswordResetTokenModel) -> None:
        self._session.delete(token)
        self._session.flush()
