from datetime import datetime
from uuid import UUID

from backend.identity.models import AuthSessionModel
from backend.identity.repositories.sessions import SessionsRepository


class SessionService:
    """Persistence boundary used by the first-party session lifecycle."""

    def __init__(self, sessions: SessionsRepository) -> None:
        self._sessions = sessions

    def add(self, auth_session: AuthSessionModel) -> AuthSessionModel:
        return self._sessions.add(auth_session)

    def get(self, sid: UUID) -> AuthSessionModel | None:
        return self._sessions.get(sid)

    def get_for_update(self, sid: UUID) -> AuthSessionModel | None:
        return self._sessions.get_for_update(sid)

    def list_for_user(self, user_id: UUID) -> list[AuthSessionModel]:
        return self._sessions.list_for_user(user_id)

    def save(self, auth_session: AuthSessionModel) -> AuthSessionModel:
        return self._sessions.save(auth_session)

    def revoke_active_for_user(
        self,
        user_id: UUID,
        *,
        revoked_at: datetime,
        reason: str,
        except_sid: UUID | None = None,
    ) -> int:
        return self._sessions.revoke_active_for_user(
            user_id,
            revoked_at=revoked_at,
            reason=reason,
            except_sid=except_sid,
        )

    def delete(self, auth_session: AuthSessionModel) -> None:
        self._sessions.delete(auth_session)
