from collections.abc import Callable
from pathlib import Path

import pytest
from fastapi import FastAPI, HTTPException, status
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
    unprotected_routes = []
    for route in admin.router.routes:
        if not isinstance(route, APIRoute):
            continue
        if admin_user not in {dependency.call for dependency in route.dependant.dependencies}:
            unprotected_routes.append(f"{','.join(sorted(route.methods))} {route.path}")

    assert unprotected_routes == []


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
