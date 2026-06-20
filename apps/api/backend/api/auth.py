from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Header, HTTPException, status

from backend.core.config import settings


@dataclass(frozen=True)
class CurrentUser:
    id: str
    email: str | None
    role: str = "user"


async def current_user(authorization: str | None = Header(default=None)) -> CurrentUser:
    if not settings.auth_required:
        return CurrentUser(id="demo-user", email="demo@regulatory.ai", role="admin")
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token")
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Supabase JWT validation is ready to wire once SUPABASE_URL is available.",
    )


def require_admin(user: CurrentUser) -> CurrentUser:
    if user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return user


async def admin_user(user: Annotated[CurrentUser, Depends(current_user)]) -> CurrentUser:
    return require_admin(user)
