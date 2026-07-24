from __future__ import annotations

from fastapi import Response

from backend.api.identity_deps import (
    IDENTITY_ACCESS_COOKIE,
    IDENTITY_CSRF_COOKIE,
    IDENTITY_REFRESH_COOKIE,
)
from backend.core.config import settings
from backend.identity.services.authentication import IssuedIdentitySession


class IdentityCookieManager:
    def set_session(self, response: Response, issued: IssuedIdentitySession) -> None:
        domain = settings.identity_cookie_domain or None
        common = {
            "domain": domain,
            "secure": settings.effective_identity_cookie_secure,
            "samesite": settings.identity_cookie_samesite,
        }
        response.set_cookie(
            key=IDENTITY_ACCESS_COOKIE,
            value=issued.access_token,
            max_age=settings.identity_access_token_ttl_seconds,
            path="/",
            httponly=True,
            **common,
        )
        response.set_cookie(
            key=IDENTITY_REFRESH_COOKIE,
            value=issued.refresh_token,
            max_age=settings.identity_session_ttl_seconds,
            path="/identity",
            httponly=True,
            **common,
        )
        response.set_cookie(
            key=IDENTITY_CSRF_COOKIE,
            value=issued.csrf_token,
            max_age=settings.identity_session_ttl_seconds,
            path="/",
            httponly=False,
            **common,
        )
        response.headers["Cache-Control"] = "no-store"
        response.headers["Pragma"] = "no-cache"

    def clear_session(self, response: Response) -> None:
        domain = settings.identity_cookie_domain or None
        common = {
            "domain": domain,
            "secure": settings.effective_identity_cookie_secure,
            "samesite": settings.identity_cookie_samesite,
        }
        response.delete_cookie(
            key=IDENTITY_ACCESS_COOKIE,
            path="/",
            httponly=True,
            **common,
        )
        response.delete_cookie(
            key=IDENTITY_REFRESH_COOKIE,
            path="/identity",
            httponly=True,
            **common,
        )
        response.delete_cookie(
            key=IDENTITY_CSRF_COOKIE,
            path="/",
            httponly=False,
            **common,
        )
        response.headers["Cache-Control"] = "no-store"
        response.headers["Pragma"] = "no-cache"
