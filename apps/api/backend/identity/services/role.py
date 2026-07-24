from uuid import UUID

from backend.identity.models import (
    PermissionModel,
    RoleModel,
    RolePermissionModel,
    UserRoleAssignmentModel,
)
from backend.identity.repositories.permissions import PermissionsRepository
from backend.identity.repositories.role_assignments import RoleAssignmentsRepository
from backend.identity.repositories.roles import RolesRepository


class RoleService:
    """Persistence facade for the future RBAC implementation.

    Authorization decisions and administrative role-change workflows are
    intentionally outside PR #2A.
    """

    def __init__(
        self,
        roles: RolesRepository,
        permissions: PermissionsRepository,
        assignments: RoleAssignmentsRepository,
    ) -> None:
        self._roles = roles
        self._permissions = permissions
        self._assignments = assignments

    def add_role(self, role: RoleModel) -> RoleModel:
        return self._roles.add(role)

    def get_role(self, role_id: UUID) -> RoleModel | None:
        return self._roles.get(role_id)

    def get_role_by_code(self, code: str) -> RoleModel | None:
        return self._roles.get_by_code(code)

    def add_permission(self, permission: PermissionModel) -> PermissionModel:
        return self._permissions.add(permission)

    def get_permission_by_code(self, code: str) -> PermissionModel | None:
        return self._permissions.get_by_code(code)

    def add_role_permission(
        self,
        mapping: RolePermissionModel,
    ) -> RolePermissionModel:
        return self._permissions.add_role_permission(mapping)

    def list_permissions_for_role(self, role_id: UUID) -> list[PermissionModel]:
        return self._permissions.list_for_role(role_id)

    def add_assignment(
        self,
        assignment: UserRoleAssignmentModel,
    ) -> UserRoleAssignmentModel:
        return self._assignments.add(assignment)

    def get_active_assignment(
        self,
        user_id: UUID,
    ) -> UserRoleAssignmentModel | None:
        return self._assignments.get_active_for_user(user_id)

    def save_assignment(
        self,
        assignment: UserRoleAssignmentModel,
    ) -> UserRoleAssignmentModel:
        return self._assignments.save(assignment)
