from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.identity.models import IdentityUserModel


class UsersRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, user: IdentityUserModel) -> IdentityUserModel:
        self._session.add(user)
        self._session.flush()
        return user

    def get(self, user_id: UUID) -> IdentityUserModel | None:
        return self._session.get(IdentityUserModel, user_id)

    def get_for_update(self, user_id: UUID) -> IdentityUserModel | None:
        statement = (
            select(IdentityUserModel)
            .where(IdentityUserModel.id == user_id)
            .with_for_update()
        )
        return self._session.execute(statement).scalar_one_or_none()

    def get_by_normalized_email(self, email_normalized: str) -> IdentityUserModel | None:
        statement = select(IdentityUserModel).where(
            IdentityUserModel.email_normalized == email_normalized
        )
        return self._session.execute(statement).scalar_one_or_none()

    def get_by_normalized_email_for_update(
        self,
        email_normalized: str,
    ) -> IdentityUserModel | None:
        statement = (
            select(IdentityUserModel)
            .where(IdentityUserModel.email_normalized == email_normalized)
            .with_for_update()
        )
        return self._session.execute(statement).scalar_one_or_none()

    def list(self, *, limit: int = 100, offset: int = 0) -> list[IdentityUserModel]:
        statement = (
            select(IdentityUserModel)
            .order_by(IdentityUserModel.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(self._session.execute(statement).scalars())

    def save(self, user: IdentityUserModel) -> IdentityUserModel:
        persisted = self._session.merge(user)
        self._session.flush()
        return persisted

    def delete(self, user: IdentityUserModel) -> None:
        self._session.delete(user)
        self._session.flush()
