from uuid import UUID

from backend.identity.models import AuditEventModel
from backend.identity.repositories.audit import AuditRepository


class AuditService:
    """Append/read facade for immutable authentication audit events."""

    def __init__(self, audit: AuditRepository) -> None:
        self._audit = audit

    def append(self, event: AuditEventModel) -> AuditEventModel:
        return self._audit.append(event)

    def get(self, event_id: UUID) -> AuditEventModel | None:
        return self._audit.get(event_id)

    def list(
        self,
        *,
        action: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[AuditEventModel]:
        return self._audit.list(action=action, limit=limit, offset=offset)
