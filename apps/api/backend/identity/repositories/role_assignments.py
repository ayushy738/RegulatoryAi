from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.identity.models import UserRoleAssignmentModel


class RoleAssignmentsRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, assignment: UserRoleAssignmentModel) -> UserRoleAssignmentModel:
        self._session.add(assignment)
        self._session.flush()
        return assignment

    def get(self, assignment_id: UUID) -> UserRoleAssignmentModel | None:
        return self._session.get(UserRoleAssignmentModel, assignment_id)

    def get_active_for_user(self, user_id: UUID) -> UserRoleAssignmentModel | None:
        statement = select(UserRoleAssignmentModel).where(
            UserRoleAssignmentModel.user_id == user_id,
            UserRoleAssignmentModel.revoked_at.is_(None),
        )
        return self._session.execute(statement).scalar_one_or_none()

    def list_for_user(self, user_id: UUID) -> list[UserRoleAssignmentModel]:
        statement = (
            select(UserRoleAssignmentModel)
            .where(UserRoleAssignmentModel.user_id == user_id)
            .order_by(UserRoleAssignmentModel.granted_at.desc())
        )
        return list(self._session.execute(statement).scalars())

    def save(self, assignment: UserRoleAssignmentModel) -> UserRoleAssignmentModel:
        persisted = self._session.merge(assignment)
        self._session.flush()
        return persisted

    def delete(self, assignment: UserRoleAssignmentModel) -> None:
        self._session.delete(assignment)
        self._session.flush()
