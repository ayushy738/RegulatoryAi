from __future__ import annotations

import hmac
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Annotated, Literal
from uuid import UUID

import jwt
from fastapi import Cookie, Depends, Header, HTTPException, Request, status
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from supabase import create_client

from backend.api.auth_observability import record_authentication_observation
from backend.api.identity_deps import (
    IDENTITY_ACCESS_COOKIE,
    build_authentication_service,
    identity_error_to_http,
    require_cookie_csrf,
)
from backend.core.config import settings
from backend.core.db import session_scope
from backend.identity.exceptions import (
    IdentityAuthenticationError,
    IdentityConfigurationError,
)

AuthenticationSource = Literal["supabase", "identity"]


@dataclass(frozen=True)
class CurrentUser:
    id: str
    email: str | None
    role: str = "user"
    source: AuthenticationSource = "supabase"
    session_id: str | None = None
    auth_version: int | None = None
    authenticated_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True)
class SupabaseCredential:
    user: CurrentUser
    source_session_reference: str
    expires_at: datetime | None


def _bearer_token(authorization: str | None) -> str | None:
    if authorization is None:
        return None
    scheme, separator, credential = authorization.partition(" ")
    if not separator or scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authorization header",
        )
    token = credential.strip()
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    return token


def _unverified_claims(token: str) -> dict[str, object]:
    try:
        claims = jwt.decode(
            token,
            options={
                "verify_signature": False,
                "verify_aud": False,
                "verify_exp": False,
            },
        )
    except jwt.InvalidTokenError:
        return {}
    return claims if isinstance(claims, dict) else {}


def _claim_datetime(claims: dict[str, object], name: str) -> datetime | None:
    value = claims.get(name)
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    try:
        return datetime.fromtimestamp(value, tz=UTC)
    except (OverflowError, OSError, ValueError):
        return None


def _looks_like_identity_token(token: str) -> bool:
    claims = _unverified_claims(token)
    return (
        claims.get("iss") == settings.identity_jwt_issuer
        and claims.get("typ") == "access"
        and isinstance(claims.get("sid"), str)
    )


def _role_for_user(user_id: str) -> str:
    role = "user"
    try:
        with session_scope() as session:
            row = session.execute(
                text("select role::text as role from profiles where id = :user_id"),
                {"user_id": user_id},
            ).first()
            if row:
                role = row.role
    except SQLAlchemyError:
        role = "user"
    return role


def _validate_token(token: str) -> CurrentUser:
    if not settings.supabase_project_url or not settings.supabase_anon_key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    try:
        client = create_client(settings.supabase_project_url, settings.supabase_anon_key)
        response = client.auth.get_user(token)
        user = response.user
        if not user:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
        claims = _unverified_claims(token)
        token_subject = claims.get("sub")
        if token_subject is not None and token_subject != user.id:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
        source_session_id = claims.get("session_id")
        if not isinstance(source_session_id, str) or not source_session_id:
            source_session_id = None
        return CurrentUser(
            id=user.id,
            email=user.email,
            role=_role_for_user(user.id),
            source="supabase",
            session_id=source_session_id,
            authenticated_at=_claim_datetime(claims, "iat") or datetime.now(UTC),
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
        ) from exc


def _validate_identity_token(token: str) -> CurrentUser:
    try:
        with session_scope() as session:
            principal = build_authentication_service(session).authenticate_access_token(token)
    except IdentityAuthenticationError as exc:
        record_authentication_observation(
            source="identity",
            outcome="failure",
            reason_code=exc.code,
        )
        raise identity_error_to_http(exc) from exc
    except IdentityConfigurationError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="First-party authentication is not configured",
        ) from exc
    return CurrentUser(
        id=str(principal.user_id),
        email=principal.email,
        role=_role_for_user(str(principal.user_id)),
        source="identity",
        session_id=str(principal.session_id),
        auth_version=principal.auth_version,
        authenticated_at=principal.authenticated_at,
    )


async def current_user(
    request: Request,
    authorization: str | None = Header(default=None),
    access_cookie: str | None = Cookie(default=None, alias=IDENTITY_ACCESS_COOKIE),
) -> CurrentUser:
    try:
        bearer = _bearer_token(authorization)
    except HTTPException:
        record_authentication_observation(
            source="unknown",
            outcome="failure",
            reason_code="INVALID_AUTHORIZATION_HEADER",
        )
        raise

    if bearer is not None:
        if _looks_like_identity_token(bearer):
            user = _validate_identity_token(bearer)
        else:
            try:
                user = _validate_token(bearer)
            except HTTPException:
                record_authentication_observation(
                    source="supabase",
                    outcome="failure",
                    reason_code="INVALID_SUPABASE_TOKEN",
                )
                raise
    elif access_cookie:
        user = _validate_identity_token(access_cookie)
        if request.method.upper() not in {"GET", "HEAD", "OPTIONS"}:
            assert user.session_id is not None
            require_cookie_csrf(request, session_id=UUID(user.session_id))
    else:
        record_authentication_observation(
            source="unknown",
            outcome="failure",
            reason_code="MISSING_CREDENTIALS",
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing bearer token",
        )

    record_authentication_observation(
        source=user.source,
        outcome="success",
    )
    return user


async def supabase_credential(
    authorization: str | None = Header(default=None),
) -> SupabaseCredential:
    try:
        token = _bearer_token(authorization)
    except HTTPException:
        record_authentication_observation(
            source="supabase",
            outcome="failure",
            reason_code="INVALID_AUTHORIZATION_HEADER",
        )
        raise
    if token is None or _looks_like_identity_token(token):
        record_authentication_observation(
            source="supabase",
            outcome="failure",
            reason_code="SUPABASE_TOKEN_REQUIRED",
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Supabase bearer token required",
        )
    try:
        user = _validate_token(token)
    except HTTPException:
        record_authentication_observation(
            source="supabase",
            outcome="failure",
            reason_code="INVALID_SUPABASE_TOKEN",
        )
        raise
    claims = _unverified_claims(token)
    source_session = user.session_id
    if not isinstance(source_session, str) or not source_session:
        source_session = claims.get("jti")
    if not isinstance(source_session, str) or not source_session:
        source_session = token
    record_authentication_observation(
        source="supabase",
        outcome="success",
    )
    return SupabaseCredential(
        user=user,
        source_session_reference=source_session,
        expires_at=_claim_datetime(claims, "exp"),
    )


def require_admin(user: CurrentUser) -> CurrentUser:
    if user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return user


async def admin_user(user: Annotated[CurrentUser, Depends(current_user)]) -> CurrentUser:
    return require_admin(user)


def _configured_rag_worker_token() -> str | None:
    secret = settings.rag_worker_token
    if secret is None:
        return None
    value = secret.get_secret_value().strip()
    return value or None


def rag_worker_token_matches(
    authorization: str | None = None,
    x_rag_worker_token: str | None = None,
) -> bool:
    """Return True when a configured RAG_WORKER_TOKEN matches the request."""
    expected = _configured_rag_worker_token()
    if expected is None:
        return False
    candidates: list[str] = []
    if x_rag_worker_token and x_rag_worker_token.strip():
        candidates.append(x_rag_worker_token.strip())
    if authorization:
        scheme, separator, credential = authorization.partition(" ")
        if separator and scheme.lower() == "bearer" and credential.strip():
            candidates.append(credential.strip())
    for candidate in candidates:
        # compare_digest requires equal length; mismatched lengths are not a match.
        if len(candidate) != len(expected):
            continue
        if hmac.compare_digest(candidate, expected):
            return True
    return False


async def rag_process_user(
    request: Request,
    authorization: str | None = Header(default=None),
    x_rag_worker_token: str | None = Header(default=None, alias="X-RAG-Worker-Token"),
    access_cookie: str | None = Cookie(default=None, alias=IDENTITY_ACCESS_COOKIE),
) -> CurrentUser:
    """Authorize POST /admin/rag/process via admin JWT or scoped worker token."""
    if rag_worker_token_matches(authorization, x_rag_worker_token):
        record_authentication_observation(
            source="unknown",
            outcome="success",
            reason_code="RAG_WORKER_TOKEN",
        )
        return CurrentUser(
            id="rag-worker",
            email=None,
            role="admin",
            source="supabase",
        )
    user = await current_user(request, authorization, access_cookie)
    return require_admin(user)


SupabaseCredentialDep = Annotated[SupabaseCredential, Depends(supabase_credential)]
