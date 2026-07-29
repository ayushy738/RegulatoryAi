from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from argon2 import PasswordHasher
from argon2.low_level import Type
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from backend.api import auth, identity_deps
from backend.api.routes import identity_auth
from backend.core.config import settings
from backend.identity.enums import IdentityUserStatus
from backend.identity.models import IdentityBase, IdentityUserModel
from backend.identity.repositories import UsersRepository
from backend.identity.services.password import PasswordService

from .auth_helpers import (
    IDENTITY_USER_ID,
    SECOND_SUPABASE_TOKEN,
    SIGNING_KEY,
    SUPABASE_TOKEN,
    TOKEN_PEPPER,
)


@dataclass
class DualAuthHarness:
    app: FastAPI
    client: TestClient
    session: Session
    user: IdentityUserModel
    passwords: PasswordService


@pytest.fixture
def dual_auth_harness(
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[DualAuthHarness]:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )
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
            id=IDENTITY_USER_ID,
            email="integration-user@example.com",
            email_normalized="integration-user@example.com",
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
    monkeypatch.setattr(auth, "session_scope", test_session_scope)
    monkeypatch.setattr(auth, "_role_for_user", lambda _user_id: "user")
    monkeypatch.setattr(auth, "record_authentication_observation", lambda **_values: None)
    monkeypatch.setattr(identity_deps, "PasswordService", lambda: fast_passwords)
    monkeypatch.setattr(settings, "environment", "test")
    monkeypatch.setattr(settings, "identity_jwt_signing_key", SecretStr(SIGNING_KEY))
    monkeypatch.setattr(settings, "identity_token_pepper", SecretStr(TOKEN_PEPPER))
    monkeypatch.setattr(settings, "identity_jwt_key_id", "integration-key")
    monkeypatch.setattr(settings, "identity_jwt_verification_keys", SecretStr("{}"))
    monkeypatch.setattr(settings, "identity_jwt_issuer", "integration-issuer")
    monkeypatch.setattr(settings, "identity_jwt_audience", "integration-audience")
    monkeypatch.setattr(settings, "identity_cookie_secure", False)
    monkeypatch.setattr(settings, "identity_failed_login_limit", 3)
    monkeypatch.setattr(settings, "identity_login_account_rate_limit", 100)
    monkeypatch.setattr(settings, "identity_login_ip_rate_limit", 100)
    monkeypatch.setattr(settings, "identity_refresh_rate_limit", 100)
    monkeypatch.setattr(settings, "identity_password_rate_limit", 100)
    monkeypatch.setattr(settings, "identity_exchange_rate_limit", 100)
    monkeypatch.setattr(settings, "supabase_url", "https://local.supabase.test")
    monkeypatch.setattr(settings, "supabase_anon_key", "local-anon-key")

    valid_supabase_tokens = {SUPABASE_TOKEN, SECOND_SUPABASE_TOKEN}

    def get_local_supabase_user(token: str) -> SimpleNamespace:
        if token not in valid_supabase_tokens:
            raise ValueError("Invalid local Supabase token")
        return SimpleNamespace(
            user=SimpleNamespace(id=str(user.id), email=user.email)
        )

    local_supabase = SimpleNamespace(
        auth=SimpleNamespace(get_user=get_local_supabase_user)
    )
    monkeypatch.setattr(auth, "create_client", lambda *_args: local_supabase)

    app = FastAPI()
    app.include_router(identity_auth.router)
    client = TestClient(app)
    try:
        yield DualAuthHarness(
            app=app,
            client=client,
            session=session,
            user=user,
            passwords=fast_passwords,
        )
    finally:
        client.close()

    session.close()
    connection.close()
    engine.dispose()
