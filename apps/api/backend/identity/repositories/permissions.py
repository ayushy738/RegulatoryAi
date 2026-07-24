from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.identity.models import PermissionModel, RolePermissionModel


class PermissionsRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, permission: PermissionModel) -> PermissionModel:
        self._session.add(permission)
        self._session.flush()
        return permission

    def get(self, permission_id: UUID) -> PermissionModel | None:
        return self._session.get(PermissionModel, permission_id)

    def get_by_code(self, code: str) -> PermissionModel | None:
        statement = select(PermissionModel).where(PermissionModel.code == code)
        return self._session.execute(statement).scalar_one_or_none()

    def list(self) -> list[PermissionModel]:
        statement = select(PermissionModel).order_by(PermissionModel.code)
        return list(self._session.execute(statement).scalars())

    def add_role_permission(self, mapping: RolePermissionModel) -> RolePermissionModel:
        self._session.add(mapping)
        self._session.flush()
        return mapping

    def list_for_role(self, role_id: UUID) -> list[PermissionModel]:
        statement = (
            select(PermissionModel)
            .join(
                RolePermissionModel,
                RolePermissionModel.permission_id == PermissionModel.id,
            )
            .where(RolePermissionModel.role_id == role_id)
            .order_by(PermissionModel.code)
        )
        return list(self._session.execute(statement).scalars())

    def delete(self, permission: PermissionModel) -> None:
        self._session.delete(permission)
        self._session.flush()
