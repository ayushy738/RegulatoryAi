from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.identity.models import EmailVerificationTokenModel


class VerificationRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, token: EmailVerificationTokenModel) -> EmailVerificationTokenModel:
        self._session.add(token)
        self._session.flush()
        return token

    def get(self, token_id: UUID) -> EmailVerificationTokenModel | None:
        return self._session.get(EmailVerificationTokenModel, token_id)

    def get_by_hash(self, token_hash: bytes) -> EmailVerificationTokenModel | None:
        statement = select(EmailVerificationTokenModel).where(
            EmailVerificationTokenModel.token_hash == token_hash
        )
        return self._session.execute(statement).scalar_one_or_none()

    def list_for_user(self, user_id: UUID) -> list[EmailVerificationTokenModel]:
        statement = (
            select(EmailVerificationTokenModel)
            .where(EmailVerificationTokenModel.user_id == user_id)
            .order_by(EmailVerificationTokenModel.created_at.desc())
        )
        return list(self._session.execute(statement).scalars())

    def save(self, token: EmailVerificationTokenModel) -> EmailVerificationTokenModel:
        persisted = self._session.merge(token)
        self._session.flush()
        return persisted

    def delete(self, token: EmailVerificationTokenModel) -> None:
        self._session.delete(token)
        self._session.flush()
