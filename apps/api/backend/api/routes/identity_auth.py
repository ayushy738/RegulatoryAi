from __future__ import annotations

from collections.abc import Callable
from typing import TypeVar
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, Response, status

from backend.api.auth import SupabaseCredentialDep
from backend.api.identity_cookies import IdentityCookieManager
from backend.api.identity_deps import (
    IDENTITY_REFRESH_COOKIE,
    IdentityPrincipalDep,
    build_authentication_service,
    hash_supabase_session_reference,
    identity_error_to_http,
    request_security_context,
    require_cookie_csrf,
)
from backend.core.db import session_scope
from backend.identity.auth_schemas import (
    LoginRequest,
    PasswordChangeRequest,
    PasswordSetupRequest,
    PasswordSetupResponse,
    SessionExchangeRequest,
    SessionResponse,
)
from backend.identity.exceptions import IdentityAuthenticationError, IdentityConfigurationError
from backend.identity.services.authentication import AuthenticationService

router = APIRouter(prefix="/identity", tags=["identity"])
cookies = IdentityCookieManager()
T = TypeVar("T")
_MISSING = object()


@router.post("/login", response_model=SessionResponse)
def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
) -> SessionResponse:
    context = request_security_context(request)
    issued = _execute(
        lambda service: service.login(
            email=payload.email,
            password=payload.password,
            device=payload.device,
            context=context,
        )
    )
    cookies.set_session(response, issued)
    return SessionResponse(
        user_id=issued.user_id,
        session_id=issued.session_id,
        access_expires_at=issued.access_expires_at,
        session_expires_at=issued.session_expires_at,
        csrf_token=issued.csrf_token,
    )


@router.post("/refresh", response_model=SessionResponse)
def refresh(request: Request, response: Response) -> SessionResponse:
    refresh_token = request.cookies.get(IDENTITY_REFRESH_COOKIE)
    if not refresh_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing identity refresh token",
        )
    csrf_session_id = require_cookie_csrf(request)
    context = request_security_context(request)
    issued = _execute(
        lambda service: service.refresh(
            refresh_token=refresh_token,
            expected_session_id=csrf_session_id,
            context=context,
        )
    )
    cookies.set_session(response, issued)
    return SessionResponse(
        user_id=issued.user_id,
        session_id=issued.session_id,
        access_expires_at=issued.access_expires_at,
        session_expires_at=issued.session_expires_at,
        csrf_token=issued.csrf_token,
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(request: Request, response: Response) -> None:
    refresh_token = request.cookies.get(IDENTITY_REFRESH_COOKIE)
    if refresh_token:
        csrf_session_id = require_cookie_csrf(request)
        context = request_security_context(request)
        _execute(
            lambda service: service.logout(
                refresh_token=refresh_token,
                expected_session_id=csrf_session_id,
                context=context,
            )
        )
    cookies.clear_session(response)


@router.post("/password/setup", response_model=PasswordSetupResponse)
def setup_password(
    payload: PasswordSetupRequest,
    request: Request,
    supabase: SupabaseCredentialDep,
) -> PasswordSetupResponse:
    try:
        user_id = UUID(supabase.user.id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Supabase identity",
        ) from exc
    context = request_security_context(request)
    configured_user_id = _execute(
        lambda service: service.setup_password(
            user_id=user_id,
            new_password=payload.new_password,
            context=context,
        )
    )
    return PasswordSetupResponse(user_id=configured_user_id)


@router.post("/session/exchange", response_model=SessionResponse)
def exchange_session(
    payload: SessionExchangeRequest,
    request: Request,
    response: Response,
    supabase: SupabaseCredentialDep,
) -> SessionResponse:
    try:
        user_id = UUID(supabase.user.id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Supabase identity",
        ) from exc
    context = request_security_context(request)
    issued = _execute(
        lambda service: service.exchange_supabase_session(
            user_id=user_id,
            source_session_hash=hash_supabase_session_reference(
                supabase.source_session_reference
            ),
            source_authenticated_at=supabase.user.authenticated_at,
            source_expires_at=supabase.expires_at,
            device=payload.device,
            context=context,
        )
    )
    cookies.set_session(response, issued)
    return SessionResponse(
        user_id=issued.user_id,
        session_id=issued.session_id,
        access_expires_at=issued.access_expires_at,
        session_expires_at=issued.session_expires_at,
        csrf_token=issued.csrf_token,
    )


@router.post("/password/change", response_model=SessionResponse)
def change_password(
    payload: PasswordChangeRequest,
    request: Request,
    response: Response,
    identity: IdentityPrincipalDep,
) -> SessionResponse:
    if identity.credential_source == "cookie":
        require_cookie_csrf(request, session_id=identity.principal.session_id)
    context = request_security_context(request)
    issued = _execute(
        lambda service: service.change_password(
            principal=identity.principal,
            current_password=payload.current_password,
            new_password=payload.new_password,
            context=context,
        )
    )
    cookies.set_session(response, issued)
    return SessionResponse(
        user_id=issued.user_id,
        session_id=issued.session_id,
        access_expires_at=issued.access_expires_at,
        session_expires_at=issued.session_expires_at,
        csrf_token=issued.csrf_token,
    )


def _execute(operation: Callable[[AuthenticationService], T]) -> T:
    caught_error: IdentityAuthenticationError | None = None
    result: T | object = _MISSING
    try:
        with session_scope() as session:
            service = build_authentication_service(session)
            try:
                result = operation(service)
            except IdentityAuthenticationError as exc:
                caught_error = exc
    except IdentityConfigurationError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="First-party authentication is not configured",
        ) from exc
    if caught_error is not None:
        raise identity_error_to_http(caught_error)
    assert result is not _MISSING
    return result  # type: ignore[return-value]
