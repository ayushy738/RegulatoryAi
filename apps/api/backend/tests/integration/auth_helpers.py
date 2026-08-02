from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

import jwt
from fastapi import FastAPI
from fastapi.testclient import TestClient
from httpx import Response

from backend.api.identity_deps import (
    IDENTITY_ACCESS_COOKIE,
    IDENTITY_CSRF_COOKIE,
    IDENTITY_REFRESH_COOKIE,
)

IDENTITY_USER_ID = UUID("a1000000-0000-4000-8000-000000000001")
_SUPABASE_TEST_SIGNING_KEY = "local-supabase-signing-key-32-bytes"
_SUPABASE_ISSUED_AT = int(datetime(2026, 1, 1, tzinfo=UTC).timestamp())
_SUPABASE_EXPIRES_AT = int(datetime(2035, 1, 1, tzinfo=UTC).timestamp())


def _supabase_token(session_id: str) -> str:
    return jwt.encode(
        {
            "iss": "https://local.supabase.test/auth/v1",
            "aud": "authenticated",
            "sub": str(IDENTITY_USER_ID),
            "session_id": session_id,
            "iat": _SUPABASE_ISSUED_AT,
            "exp": _SUPABASE_EXPIRES_AT,
            "role": "authenticated",
        },
        _SUPABASE_TEST_SIGNING_KEY,
        algorithm="HS256",
    )


SUPABASE_TOKEN = _supabase_token("supabase-session-primary")
SECOND_SUPABASE_TOKEN = _supabase_token("supabase-session-secondary")
INVALID_SUPABASE_TOKEN = "invalid-supabase-session"
PASSWORD = "correct horse battery staple"
NEW_PASSWORD = "a newer correct horse battery staple"
SIGNING_KEY = "integration-signing-key-32-bytes!!"
TOKEN_PEPPER = "integration-token-pepper-32-bytes!!!"


@dataclass(frozen=True)
class IdentitySessionCookies:
    access_token: str
    refresh_token: str
    csrf_token: str
    session_id: str


def setup_password(
    client: TestClient,
    *,
    supabase_token: str,
    password: str,
) -> Response:
    return client.post(
        "/identity/password/setup",
        headers={"Authorization": f"Bearer {supabase_token}"},
        json={"new_password": password},
    )


def login_identity(
    client: TestClient,
    *,
    email: str,
    password: str,
    device: str = "integration-test",
) -> tuple[Response, IdentitySessionCookies]:
    response = client.post(
        "/identity/login",
        json={"email": email, "password": password, "device": device},
    )
    assert response.status_code == 200, response.text
    return response, current_identity_cookies(client, response.json()["session_id"])


def refresh_identity(
    client: TestClient,
    *,
    csrf_token: str,
) -> tuple[Response, IdentitySessionCookies]:
    response = client.post(
        "/identity/refresh",
        headers={"X-CSRF-Token": csrf_token},
    )
    assert response.status_code == 200, response.text
    return response, current_identity_cookies(client, response.json()["session_id"])


def exchange_supabase_session(
    client: TestClient,
    *,
    supabase_token: str,
    device: str = "integration-exchange",
) -> tuple[Response, IdentitySessionCookies]:
    response = client.post(
        "/identity/session/exchange",
        headers={"Authorization": f"Bearer {supabase_token}"},
        json={"device": device},
    )
    assert response.status_code == 200, response.text
    return response, current_identity_cookies(client, response.json()["session_id"])


def current_identity_cookies(
    client: TestClient,
    session_id: str,
) -> IdentitySessionCookies:
    access_token = client.cookies.get(IDENTITY_ACCESS_COOKIE)
    refresh_token = client.cookies.get(IDENTITY_REFRESH_COOKIE)
    csrf_token = client.cookies.get(IDENTITY_CSRF_COOKIE)
    assert access_token is not None
    assert refresh_token is not None
    assert csrf_token is not None
    return IdentitySessionCookies(
        access_token=access_token,
        refresh_token=refresh_token,
        csrf_token=csrf_token,
        session_id=session_id,
    )


def install_identity_cookies(
    client: TestClient,
    cookies: IdentitySessionCookies,
) -> None:
    client.cookies.set(IDENTITY_ACCESS_COOKIE, cookies.access_token, path="/")
    client.cookies.set(
        IDENTITY_REFRESH_COOKIE,
        cookies.refresh_token,
        path="/identity",
    )
    client.cookies.set(IDENTITY_CSRF_COOKIE, cookies.csrf_token, path="/")


@contextmanager
def isolated_client(
    app: FastAPI,
    *,
    cookies: IdentitySessionCookies | None = None,
) -> Iterator[TestClient]:
    client = TestClient(app)
    if cookies is not None:
        install_identity_cookies(client, cookies)
    try:
        yield client
    finally:
        client.close()
