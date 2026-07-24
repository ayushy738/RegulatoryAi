from __future__ import annotations

from uuid import UUID

from sqlalchemy.orm import Session

from backend.identity.models import IdentityProfileModel


class ProfilesRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, profile: IdentityProfileModel) -> IdentityProfileModel:
        self._session.add(profile)
        self._session.flush()
        return profile

    def get(self, user_id: UUID) -> IdentityProfileModel | None:
        return self._session.get(IdentityProfileModel, user_id)

    def save(self, profile: IdentityProfileModel) -> IdentityProfileModel:
        persisted = self._session.merge(profile)
        self._session.flush()
        return persisted

    def delete(self, profile: IdentityProfileModel) -> None:
        self._session.delete(profile)
        self._session.flush()
