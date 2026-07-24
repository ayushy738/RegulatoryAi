from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from argon2 import PasswordHasher
from argon2.low_level import Type
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from backend.api import identity_deps
from backend.api.auth import (
    CurrentUser,
    SupabaseCredential,
    supabase_credential,
)
from backend.api.routes import identity_auth
from backend.core.config import settings
from backend.identity.enums import IdentityUserStatus
from backend.identity.models import AuditEventModel, IdentityBase, IdentityUserModel
from backend.identity.repositories import SessionsRepository, UsersRepository
from backend.identity.services.password import PasswordService

PASSWORD = "correct horse battery staple"
NEW_PASSWORD = "a newer correct horse battery staple"


@pytest.fixture
def identity_api(
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[tuple[TestClient, Session, IdentityUserModel]]:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    connection = engine.connect()
    connection.exec_driver_sql("ATTACH DATABASE ':memory:' AS identity")
    connection.exec_driver_sql("PRAGMA foreign_keys = ON")
    IdentityBase.metadata.create_all(connection)
    connection.exec_driver_sql(
        "CREATE TABLE identity.test_coexistence_drift (user_id TEXT NOT NULL)"
    )
    connection.exec_driver_sql(
        "CREATE VIEW identity.coexistence_drift AS "
        "SELECT user_id FROM identity.test_coexistence_drift"
    )
    session = Session(bind=connection, expire_on_commit=False)
    user = UsersRepository(session).add(
        IdentityUserModel(
            email="user@example.com",
            email_normalized="user@example.com",
            status=IdentityUserStatus.ACTIVE,
            email_verified_at=datetime.now(UTC),
        )
    )
    session.commit()

    @contextmanager
    def test_session_scope() -> Iterator[Session]:
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise

    fast_passwords = PasswordService(
        PasswordHasher(
            time_cost=1,
            memory_cost=8192,
            parallelism=1,
            hash_len=16,
            salt_len=8,
            type=Type.ID,
        )
    )
    monkeypatch.setattr(identity_auth, "session_scope", test_session_scope)
    monkeypatch.setattr(identity_deps, "session_scope", test_session_scope)
    monkeypatch.setattr(identity_deps, "PasswordService", lambda: fast_passwords)
    monkeypatch.setattr(settings, "identity_jwt_signing_key", SecretStr("s" * 32))
    monkeypatch.setattr(settings, "identity_token_pepper", SecretStr("p" * 32))
    monkeypatch.setattr(settings, "identity_jwt_key_id", "test-key")
    monkeypatch.setattr(settings, "identity_jwt_issuer", "test-issuer")
    monkeypatch.setattr(settings, "identity_jwt_audience", "test-audience")
    monkeypatch.setattr(settings, "identity_cookie_secure", False)

    app = FastAPI()
    app.include_router(identity_auth.router)
    app.dependency_overrides[supabase_credential] = lambda: SupabaseCredential(
        user=CurrentUser(
            id=str(user.id),
            email=user.email,
            authenticated_at=datetime.now(UTC),
        ),
        source_session_reference="test-supabase-session",
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    with TestClient(app) as client:
        yield client, session, user
    session.close()
    connection.close()
    engine.dispose()


def test_identity_endpoints_complete_isolated_session_lifecycle(
    identity_api: tuple[TestClient, Session, IdentityUserModel],
) -> None:
    client, session, user = identity_api

    setup = client.post(
        "/identity/password/setup",
        headers={"Authorization": "Bearer existing-supabase-token"},
        json={"new_password": PASSWORD},
    )
    assert setup.status_code == 200
    assert setup.json() == {"user_id": str(user.id), "password_configured": True}

    login = client.post(
        "/identity/login",
        json={
            "email": user.email,
            "password": PASSWORD,
            "device": "integration-test",
        },
    )
    assert login.status_code == 200
    assert "access_token" not in login.json()
    assert "refresh_token" not in login.json()
    assert "HttpOnly" in login.headers.get("set-cookie", "")
    first_csrf = login.json()["csrf_token"]
    session_id = login.json()["session_id"]

    refreshed = client.post(
        "/identity/refresh",
        headers={"X-CSRF-Token": first_csrf},
    )
    assert refreshed.status_code == 200
    assert refreshed.json()["session_id"] == session_id
    second_csrf = refreshed.json()["csrf_token"]
    assert second_csrf != first_csrf

    changed = client.post(
        "/identity/password/change",
        headers={"X-CSRF-Token": second_csrf},
        json={
            "current_password": PASSWORD,
            "new_password": NEW_PASSWORD,
        },
    )
    assert changed.status_code == 200
    third_csrf = changed.json()["csrf_token"]

    logged_out = client.post(
        "/identity/logout",
        headers={"X-CSRF-Token": third_csrf},
    )
    assert logged_out.status_code == 204
    assert SessionsRepository(session).get_for_update(UUID(session_id)).revoked_at is not None
    actions = set(session.execute(select(AuditEventModel.action)).scalars())
    assert {
        "password.setup",
        "authentication.login",
        "authentication.refresh",
        "password.change",
        "authentication.logout",
    }.issubset(actions)


def test_identity_login_rejects_user_without_password(
    identity_api: tuple[TestClient, Session, IdentityUserModel],
) -> None:
    client, _, user = identity_api

    response = client.post(
        "/identity/login",
        json={"email": user.email, "password": PASSWORD},
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid email or password"


def test_cookie_authenticated_password_change_requires_csrf(
    identity_api: tuple[TestClient, Session, IdentityUserModel],
) -> None:
    client, _, user = identity_api
    client.post(
        "/identity/password/setup",
        json={"new_password": PASSWORD},
    )
    login = client.post(
        "/identity/login",
        json={"email": user.email, "password": PASSWORD},
    )
    assert login.status_code == 200

    response = client.post(
        "/identity/password/change",
        json={"current_password": PASSWORD, "new_password": NEW_PASSWORD},
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "CSRF validation failed"


def test_supabase_session_exchange_issues_identity_session_and_rejects_replay(
    identity_api: tuple[TestClient, Session, IdentityUserModel],
) -> None:
    client, session, user = identity_api

    exchanged = client.post(
        "/identity/session/exchange",
        json={"device": "exchange-browser"},
    )

    assert exchanged.status_code == 200
    assert exchanged.json()["user_id"] == str(user.id)
    assert "HttpOnly" in exchanged.headers.get("set-cookie", "")
    assert len(SessionsRepository(session).list_for_user(user.id)) == 1

    replay = client.post(
        "/identity/session/exchange",
        json={"device": "exchange-browser"},
    )
    assert replay.status_code == 409
    assert replay.json()["detail"] == "This Supabase session has already been exchanged"
    assert len(SessionsRepository(session).list_for_user(user.id)) == 1


def test_session_exchange_rejects_reconciliation_drift(
    identity_api: tuple[TestClient, Session, IdentityUserModel],
) -> None:
    client, session, user = identity_api
    session.connection().exec_driver_sql(
        "INSERT INTO identity.test_coexistence_drift (user_id) VALUES (?)",
        (str(user.id),),
    )

    response = client.post("/identity/session/exchange", json={})

    assert response.status_code == 409
    assert "reconciled" in response.json()["detail"]
    assert SessionsRepository(session).list_for_user(user.id) == []


def test_session_exchange_requires_supabase_authentication() -> None:
    app = FastAPI()
    app.include_router(identity_auth.router)

    with TestClient(app) as client:
        response = client.post("/identity/session/exchange", json={})

    assert response.status_code == 401
