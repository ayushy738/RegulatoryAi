from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Annotated

import jwt
import pytest
from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from backend.api import auth
from backend.api.auth import CurrentUser, admin_user, current_user
from backend.api.routes import (
    admin,
    chat,
    digests,
    events,
    exports,
    intelligence,
    subscriptions,
)


@pytest.fixture
def client() -> TestClient:
    app = FastAPI()
    app.include_router(admin.router)
    app.include_router(chat.router)
    app.include_router(events.router)
    app.include_router(subscriptions.router)
    return TestClient(app)


def _token_validator(user: CurrentUser) -> Callable[[str], CurrentUser]:
    def validate(token: str) -> CurrentUser:
        assert token
        return user

    return validate


def test_anonymous_user_cannot_access_admin_endpoint(client: TestClient) -> None:
    response = client.get("/admin/sources")

    assert response.status_code == status.HTTP_401_UNAUTHORIZED


def test_anonymous_user_cannot_access_chat_endpoint(client: TestClient) -> None:
    response = client.post("/chat", json={"message": "What changed?"})

    assert response.status_code == status.HTTP_401_UNAUTHORIZED


def test_anonymous_user_cannot_modify_subscriptions(client: TestClient) -> None:
    response = client.put("/subscriptions", json={})

    assert response.status_code == status.HTTP_401_UNAUTHORIZED


def test_normal_user_receives_forbidden_on_admin_endpoint(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        auth,
        "_validate_token",
        _token_validator(
            CurrentUser(id="11111111-1111-4111-8111-111111111111", email="user@example.com")
        ),
    )

    response = client.get("/admin/sources", headers={"Authorization": "Bearer user-token"})

    assert response.status_code == status.HTTP_403_FORBIDDEN


def test_missing_authorization_header_returns_unauthorized(client: TestClient) -> None:
    response = client.get("/events")

    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert response.json()["detail"] == "Missing bearer token"


def test_invalid_token_returns_unauthorized(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def reject_token(token: str) -> CurrentUser:
        assert token
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
        )

    monkeypatch.setattr(auth, "_validate_token", reject_token)

    response = client.get("/events", headers={"Authorization": "Bearer invalid-token"})

    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert response.json()["detail"] == "Invalid token"


def test_valid_admin_still_succeeds(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        auth,
        "_validate_token",
        _token_validator(
            CurrentUser(
                id="22222222-2222-4222-8222-222222222222",
                email="admin@example.com",
                role="admin",
            )
        ),
    )
    monkeypatch.setattr(admin, "list_sources", lambda: [{"id": 1, "name": "MNRE"}])

    response = client.get("/admin/sources", headers={"Authorization": "Bearer admin-token"})

    assert response.status_code == status.HTTP_200_OK
    assert response.json() == [{"id": 1, "name": "MNRE"}]


def test_every_admin_route_requires_the_admin_dependency() -> None:
    from backend.api.auth import rag_process_user

    allowed_admin_deps = {admin_user, rag_process_user}
    unprotected_routes = []
    for route in admin.router.routes:
        if not isinstance(route, APIRoute):
            continue
        dependency_calls = {dependency.call for dependency in route.dependant.dependencies}
        if dependency_calls.isdisjoint(allowed_admin_deps):
            unprotected_routes.append(f"{','.join(sorted(route.methods))} {route.path}")

    assert unprotected_routes == []


def test_rag_process_accepts_scoped_worker_token(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from pydantic import SecretStr

    monkeypatch.setattr(
        auth.settings,
        "rag_worker_token",
        SecretStr("test-rag-worker-token"),
    )
    monkeypatch.setattr(auth, "record_authentication_observation", lambda **_: None)
    monkeypatch.setattr(
        admin,
        "process_pending_rag_jobs",
        lambda limit, include_processing: {
            "processed": 1,
            "limit": limit,
            "include_processing": include_processing,
        },
    )

    response = client.post(
        "/admin/rag/process?limit=50",
        headers={"Authorization": "Bearer test-rag-worker-token"},
    )

    assert response.status_code == status.HTTP_200_OK
    assert response.json()["processed"] == 1


def test_rag_process_rejects_wrong_worker_token(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from pydantic import SecretStr

    monkeypatch.setattr(
        auth.settings,
        "rag_worker_token",
        SecretStr("test-rag-worker-token"),
    )
    monkeypatch.setattr(auth, "record_authentication_observation", lambda **_: None)

    def reject_token(token: str) -> CurrentUser:
        assert token
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
        )

    monkeypatch.setattr(auth, "_validate_token", reject_token)

    response = client.post(
        "/admin/rag/process?limit=50",
        headers={"Authorization": "Bearer wrong-token"},
    )

    assert response.status_code == status.HTTP_401_UNAUTHORIZED


def test_rag_process_still_allows_admin_jwt(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(auth.settings, "rag_worker_token", None)
    monkeypatch.setattr(auth, "record_authentication_observation", lambda **_: None)
    monkeypatch.setattr(
        auth,
        "_validate_token",
        _token_validator(
            CurrentUser(
                id="22222222-2222-4222-8222-222222222222",
                email="admin@example.com",
                role="admin",
            )
        ),
    )
    monkeypatch.setattr(
        admin,
        "process_pending_rag_jobs",
        lambda limit, include_processing: {"processed": 2, "limit": limit},
    )

    response = client.post(
        "/admin/rag/process?limit=25",
        headers={"Authorization": "Bearer admin-token"},
    )

    assert response.status_code == status.HTTP_200_OK
    assert response.json()["processed"] == 2


def test_every_product_route_requires_an_authenticated_user() -> None:
    unprotected_routes = []
    product_routers = (
        chat.router,
        digests.router,
        events.router,
        exports.router,
        intelligence.router,
        subscriptions.router,
    )
    for router in product_routers:
        for route in router.routes:
            if not isinstance(route, APIRoute):
                continue
            if current_user not in {dependency.call for dependency in route.dependant.dependencies}:
                unprotected_routes.append(f"{','.join(sorted(route.methods))} {route.path}")

    assert unprotected_routes == []


def test_profile_role_is_not_user_editable() -> None:
    migration_path = (
        Path(__file__).resolve().parents[1] / "migrations" / "0016_lock_profile_role.sql"
    )
    migration = migration_path.read_text(encoding="utf-8").lower()

    assert (
        "revoke insert, delete, update on table public.profiles "
        "from public, anon, authenticated"
    ) in migration
    assert "grant update (full_name) on table public.profiles to authenticated" in migration


def test_supabase_principal_records_validated_source_session_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user_id = "77777777-7777-4777-8777-777777777777"
    session_id = "88888888-8888-4888-8888-888888888888"
    issued_at = datetime(2026, 7, 24, 10, 0, tzinfo=UTC)
    token = jwt.encode(
        {
            "sub": user_id,
            "session_id": session_id,
            "iat": int(issued_at.timestamp()),
        },
        "test-only-key-with-at-least-32-bytes",
        algorithm="HS256",
    )
    client = SimpleNamespace(
        auth=SimpleNamespace(
            get_user=lambda _: SimpleNamespace(
                user=SimpleNamespace(id=user_id, email="user@example.com")
            )
        )
    )
    monkeypatch.setattr(auth.settings, "supabase_url", "https://example.supabase.co")
    monkeypatch.setattr(auth.settings, "supabase_anon_key", "test-anon-key")
    monkeypatch.setattr(auth, "create_client", lambda *_: client)
    monkeypatch.setattr(auth, "_role_for_user", lambda _: "user")

    principal = auth._validate_token(token)

    assert principal.id == user_id
    assert principal.source == "supabase"
    assert principal.session_id == session_id
    assert principal.authenticated_at == issued_at


def test_unified_dependency_accepts_supabase_and_identity_for_the_same_uuid(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user_id = "33333333-3333-4333-8333-333333333333"
    app = FastAPI()

    @app.get("/whoami")
    async def whoami(
        user: Annotated[CurrentUser, Depends(current_user)],
    ) -> dict[str, str | None]:
        return {
            "id": user.id,
            "source": user.source,
            "session_id": user.session_id,
        }

    monkeypatch.setattr(auth, "record_authentication_observation", lambda **_: None)
    monkeypatch.setattr(
        auth,
        "_validate_token",
        lambda _: CurrentUser(id=user_id, email="user@example.com", source="supabase"),
    )
    monkeypatch.setattr(
        auth,
        "_validate_identity_token",
        lambda _: CurrentUser(
            id=user_id,
            email="user@example.com",
            source="identity",
            session_id="44444444-4444-4444-8444-444444444444",
            auth_version=2,
        ),
    )

    with TestClient(app) as dual_client:
        monkeypatch.setattr(auth, "_looks_like_identity_token", lambda _: False)
        supabase_response = dual_client.get(
            "/whoami",
            headers={"Authorization": "Bearer supabase-token"},
        )
        monkeypatch.setattr(auth, "_looks_like_identity_token", lambda _: True)
        identity_response = dual_client.get(
            "/whoami",
            headers={"Authorization": "Bearer identity-token"},
        )

    assert supabase_response.json() == {
        "id": user_id,
        "source": "supabase",
        "session_id": None,
    }
    assert identity_response.json() == {
        "id": user_id,
        "source": "identity",
        "session_id": "44444444-4444-4444-8444-444444444444",
    }


def test_authorization_header_precedes_identity_cookie(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = FastAPI()

    @app.get("/source")
    async def source(user: Annotated[CurrentUser, Depends(current_user)]) -> dict[str, str]:
        return {"source": user.source}

    monkeypatch.setattr(auth, "record_authentication_observation", lambda **_: None)
    monkeypatch.setattr(auth, "_looks_like_identity_token", lambda _: False)
    monkeypatch.setattr(
        auth,
        "_validate_token",
        lambda _: CurrentUser(id="1", email=None, source="supabase"),
    )

    def identity_must_not_run(_: str) -> CurrentUser:
        raise AssertionError("identity cookie must not override Authorization")

    monkeypatch.setattr(auth, "_validate_identity_token", identity_must_not_run)

    with TestClient(app) as dual_client:
        dual_client.cookies.set("resolven_identity_access", "identity-cookie")
        response = dual_client.get(
            "/source",
            headers={"Authorization": "Bearer supabase-token"},
        )

    assert response.status_code == 200
    assert response.json() == {"source": "supabase"}


def test_unsafe_identity_cookie_request_requires_csrf(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = FastAPI()

    @app.post("/write")
    async def write(user: Annotated[CurrentUser, Depends(current_user)]) -> dict[str, str]:
        return {"id": user.id}

    monkeypatch.setattr(auth, "record_authentication_observation", lambda **_: None)
    monkeypatch.setattr(
        auth,
        "_validate_identity_token",
        lambda _: CurrentUser(
            id="55555555-5555-4555-8555-555555555555",
            email=None,
            source="identity",
            session_id="66666666-6666-4666-8666-666666666666",
            auth_version=1,
        ),
    )

    with TestClient(app) as dual_client:
        dual_client.cookies.set("resolven_identity_access", "identity-cookie")
        response = dual_client.post("/write")

    assert response.status_code == 403
    assert response.json()["detail"] == "CSRF validation failed"
