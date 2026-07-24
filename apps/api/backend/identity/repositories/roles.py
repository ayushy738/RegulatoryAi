from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.identity.models import RoleModel


class RolesRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, role: RoleModel) -> RoleModel:
        self._session.add(role)
        self._session.flush()
        return role

    def get(self, role_id: UUID) -> RoleModel | None:
        return self._session.get(RoleModel, role_id)

    def get_by_code(self, code: str) -> RoleModel | None:
        statement = select(RoleModel).where(RoleModel.code == code)
        return self._session.execute(statement).scalar_one_or_none()

    def list(self) -> list[RoleModel]:
        statement = select(RoleModel).order_by(RoleModel.code)
        return list(self._session.execute(statement).scalars())

    def save(self, role: RoleModel) -> RoleModel:
        persisted = self._session.merge(role)
        self._session.flush()
        return persisted

    def delete(self, role: RoleModel) -> None:
        self._session.delete(role)
        self._session.flush()
