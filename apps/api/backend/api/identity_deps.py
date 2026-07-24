from __future__ import annotations

import hmac
import ipaddress
from dataclasses import dataclass
from datetime import timedelta
from typing import Annotated, Literal
from uuid import UUID

from fastapi import Cookie, Depends, Header, HTTPException, Request, status
from sqlalchemy.orm import Session

from backend.core.config import settings
from backend.core.db import session_scope
from backend.identity.exceptions import (
    CsrfValidationError,
    IdentityAuthenticationError,
    IdentityConfigurationError,
    InvalidCredentialsError,
    InvalidIdentityTokenError,
    InvalidSessionError,
    PasswordAlreadyConfiguredError,
    PasswordPolicyError,
    RateLimitExceededError,
    ReconciliationDriftError,
    SessionExchangeReplayError,
)
from backend.identity.repositories import (
    AuditRepository,
    AuthenticationRateLimitsRepository,
    IdentityReconciliationRepository,
    SessionExchangesRepository,
    SessionsRepository,
    UsersRepository,
)
from backend.identity.services.authentication import (
    AuthenticationService,
    FirstPartyPrincipal,
    RequestSecurityContext,
)
from backend.identity.services.password import PasswordService
from backend.identity.services.rate_limit import AuthenticationRateLimitService
from backend.identity.services.session import SessionService
from backend.identity.services.tokens import (
    CsrfTokenService,
    JwtService,
    RefreshTokenService,
    SecurityMetadataHasher,
)

IDENTITY_ACCESS_COOKIE = "resolven_identity_access"
IDENTITY_REFRESH_COOKIE = "resolven_identity_refresh"
IDENTITY_CSRF_COOKIE = "resolven_identity_csrf"


@dataclass(frozen=True)
class IdentityRequestPrincipal:
    principal: FirstPartyPrincipal
    credential_source: Literal["authorization", "cookie"]


def build_authentication_service(session: Session) -> AuthenticationService:
    try:
        signing_key, token_pepper = settings.require_identity_token_secrets()
        verification_keys = settings.identity_jwt_key_ring(signing_key)
    except RuntimeError as exc:
        raise IdentityConfigurationError from exc
    sessions = SessionService(SessionsRepository(session))
    return AuthenticationService(
        users=UsersRepository(session),
        sessions=sessions,
        audit=AuditRepository(session),
        passwords=PasswordService(),
        jwt_tokens=JwtService(
            signing_key=signing_key,
            key_id=settings.identity_jwt_key_id,
            verification_keys=verification_keys,
            issuer=settings.identity_jwt_issuer,
            audience=settings.identity_jwt_audience,
            access_ttl=timedelta(seconds=settings.identity_access_token_ttl_seconds),
        ),
        refresh_tokens=RefreshTokenService(token_pepper),
        csrf_tokens=CsrfTokenService(token_pepper),
        metadata_hasher=SecurityMetadataHasher(token_pepper),
        rate_limits=AuthenticationRateLimitService(
            AuthenticationRateLimitsRepository(session)
        ),
        reconciliation=IdentityReconciliationRepository(session),
        exchanges=SessionExchangesRepository(session),
        session_ttl=timedelta(seconds=settings.identity_session_ttl_seconds),
        password_min_length=settings.identity_password_min_length,
        password_max_length=settings.identity_password_max_length,
        failed_login_limit=settings.identity_failed_login_limit,
        account_lock_duration=timedelta(seconds=settings.identity_account_lock_seconds),
        login_account_rate_limit=settings.identity_login_account_rate_limit,
        login_ip_rate_limit=settings.identity_login_ip_rate_limit,
        login_rate_window=timedelta(seconds=settings.identity_login_rate_window_seconds),
        refresh_rate_limit=settings.identity_refresh_rate_limit,
        refresh_rate_window=timedelta(seconds=settings.identity_refresh_rate_window_seconds),
        password_rate_limit=settings.identity_password_rate_limit,
        password_rate_window=timedelta(seconds=settings.identity_password_rate_window_seconds),
        exchange_rate_limit=settings.identity_exchange_rate_limit,
        exchange_rate_window=timedelta(
            seconds=settings.identity_exchange_rate_window_seconds
        ),
    )


def request_security_context(request: Request) -> RequestSecurityContext:
    _, token_pepper = _identity_secrets_or_503()
    hasher = SecurityMetadataHasher(token_pepper)
    client_ip = _client_ip(request)
    user_agent = request.headers.get("user-agent", "")[:4096]
    request_id = request.headers.get("x-request-id")
    if request_id is not None:
        request_id = request_id.strip()[:200] or None
    return RequestSecurityContext(
        ip_hash=hasher.hash_value("request-ip", client_ip),
        user_agent_hash=hasher.hash_value("request-user-agent", user_agent),
        ip_rate_limit_hash=hasher.hash_value("rate-limit-ip", client_ip),
        request_id=request_id,
    )


def hash_supabase_session_reference(reference: str) -> bytes:
    _, token_pepper = _identity_secrets_or_503()
    return SecurityMetadataHasher(token_pepper).hash_value(
        "supabase-session-exchange",
        reference,
    )


def identity_error_to_http(error: IdentityAuthenticationError) -> HTTPException:
    headers: dict[str, str] = {}
    if isinstance(error, RateLimitExceededError):
        status_code = status.HTTP_429_TOO_MANY_REQUESTS
        headers["Retry-After"] = str(error.retry_after_seconds or 1)
    elif isinstance(error, PasswordAlreadyConfiguredError):
        status_code = status.HTTP_409_CONFLICT
    elif isinstance(error, PasswordPolicyError):
        status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    elif isinstance(error, CsrfValidationError):
        status_code = status.HTTP_403_FORBIDDEN
    elif isinstance(error, (ReconciliationDriftError, SessionExchangeReplayError)):
        status_code = status.HTTP_409_CONFLICT
    elif isinstance(
        error,
        (InvalidCredentialsError, InvalidIdentityTokenError, InvalidSessionError),
    ):
        status_code = status.HTTP_401_UNAUTHORIZED
        headers["WWW-Authenticate"] = "Bearer"
    else:
        status_code = status.HTTP_401_UNAUTHORIZED
    return HTTPException(
        status_code=status_code,
        detail=error.public_message,
        headers=headers or None,
    )


def require_cookie_csrf(
    request: Request,
    *,
    session_id: UUID | None = None,
) -> UUID:
    csrf_cookie = request.cookies.get(IDENTITY_CSRF_COOKIE)
    csrf_header = request.headers.get("x-csrf-token")
    if (
        not csrf_cookie
        or not csrf_header
        or not hmac.compare_digest(csrf_cookie, csrf_header)
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="CSRF validation failed",
        )
    _, token_pepper = _identity_secrets_or_503()
    csrf_service = CsrfTokenService(token_pepper)
    bound_session_id = csrf_service.bound_session_id(csrf_header)
    if bound_session_id is None or (
        session_id is not None and bound_session_id != session_id
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="CSRF validation failed",
        )
    return bound_session_id


def first_party_principal(
    authorization: str | None = Header(default=None),
    access_cookie: str | None = Cookie(default=None, alias=IDENTITY_ACCESS_COOKIE),
) -> IdentityRequestPrincipal:
    token: str | None = None
    source: Literal["authorization", "cookie"]
    if authorization is not None:
        scheme, separator, credential = authorization.partition(" ")
        if not separator or scheme.lower() != "bearer" or not credential.strip():
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid authorization header",
                headers={"WWW-Authenticate": "Bearer"},
            )
        token = credential.strip()
        source = "authorization"
    elif access_cookie:
        token = access_cookie
        source = "cookie"
    else:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing identity access token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        with session_scope() as session:
            principal = build_authentication_service(session).authenticate_access_token(token)
    except IdentityAuthenticationError as exc:
        raise identity_error_to_http(exc) from exc
    except IdentityConfigurationError as exc:
        raise _identity_unavailable() from exc
    return IdentityRequestPrincipal(principal=principal, credential_source=source)


IdentityPrincipalDep = Annotated[IdentityRequestPrincipal, Depends(first_party_principal)]


def _identity_secrets_or_503() -> tuple[str, str]:
    try:
        return settings.require_identity_token_secrets()
    except RuntimeError as exc:
        raise _identity_unavailable() from exc


def _identity_unavailable() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="First-party authentication is not configured",
    )


def _client_ip(request: Request) -> str:
    candidates: list[str] = []
    if settings.identity_trust_forwarded_for:
        forwarded_for = request.headers.get("x-forwarded-for")
        if forwarded_for:
            candidates.append(forwarded_for.split(",", 1)[0].strip())
    if request.client is not None and request.client.host:
        candidates.append(request.client.host)
    for candidate in candidates:
        try:
            return ipaddress.ip_address(candidate).compressed
        except ValueError:
            continue
    return "unknown"
