from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from supabase import create_client

from backend.core.config import settings
from backend.core.db import session_scope
from backend.core.repository import DEMO_USER_ID


@dataclass(frozen=True)
class CurrentUser:
    id: str
    email: str | None
    role: str = "user"


async def current_user(authorization: str | None = Header(default=None)) -> CurrentUser:
    if not authorization or not authorization.startswith("Bearer "):
        if not settings.auth_required:
            return CurrentUser(id=DEMO_USER_ID, email="demo@regulatory.ai", role="admin")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token")
    token = authorization.removeprefix("Bearer ").strip()
    if not settings.supabase_project_url or not settings.supabase_anon_key:
        raise HTTPException(status_code=500, detail="Supabase Auth is not configured")
    try:
        client = create_client(settings.supabase_project_url, settings.supabase_anon_key)
        response = client.auth.get_user(token)
        user = response.user
        if not user:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
        role = "user"
        try:
            with session_scope() as session:
                row = session.execute(
                    text("select role::text as role from profiles where id = :user_id"),
                    {"user_id": user.id},
                ).first()
                if row:
                    role = row.role
        except SQLAlchemyError:
            role = "user"
        return CurrentUser(id=user.id, email=user.email, role=role)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
        ) from exc


def require_admin(user: CurrentUser) -> CurrentUser:
    if user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return user


async def admin_user(user: Annotated[CurrentUser, Depends(current_user)]) -> CurrentUser:
    return require_admin(user)
