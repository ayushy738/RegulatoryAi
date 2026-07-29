from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING
from uuid import UUID

import pytest
from sqlalchemy import select

from backend.api.identity_deps import (
    IDENTITY_ACCESS_COOKIE,
    IDENTITY_CSRF_COOKIE,
    IDENTITY_REFRESH_COOKIE,
)
from backend.identity.enums import AuditOutcome
from backend.identity.models import AuditEventModel
from backend.identity.repositories import SessionsRepository
from backend.identity.services.tokens import JwtService

from .auth_helpers import (
    INVALID_SUPABASE_TOKEN,
    NEW_PASSWORD,
    PASSWORD,
    SECOND_SUPABASE_TOKEN,
    SIGNING_KEY,
    SUPABASE_TOKEN,
    IdentitySessionCookies,
    exchange_supabase_session,
    isolated_client,
    login_identity,
    refresh_identity,
    setup_password,
)

if TYPE_CHECKING:
    from .conftest import DualAuthHarness


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _assert_unauthorized(response) -> None:
    assert response.status_code == 401, response.text
    assert response.headers.get("www-authenticate") == "Bearer"


def _tamper(token: str) -> str:
    header, payload, signature = token.split(".")
    replacement = "A" if signature[0] != "A" else "B"
    return f"{header}.{payload}.{replacement}{signature[1:]}"


def test_supabase_bearer_authentication_valid_invalid_and_missing(
    dual_auth_harness: DualAuthHarness,
) -> None:
    client = dual_auth_harness.client

    valid = client.get("/identity/me", headers=_bearer(SUPABASE_TOKEN))
    invalid = client.get(
        "/identity/me",
        headers=_bearer(INVALID_SUPABASE_TOKEN),
    )
    missing = client.get("/identity/me")

    assert valid.status_code == 200
    assert valid.json()["user_id"] == str(dual_auth_harness.user.id)
    assert valid.json()["source"] == "supabase"
    assert valid.json()["session_id"] == "supabase-session-primary"
    assert invalid.status_code == 401
    assert invalid.json()["detail"] == "Invalid token"
    assert missing.status_code == 401
    assert missing.json()["detail"] == "Missing bearer token"


def test_password_enrollment_persists_hash_version_and_audit_and_is_single_use(
    dual_auth_harness: DualAuthHarness,
) -> None:
    harness = dual_auth_harness
    initial_auth_version = harness.user.auth_version

    enrolled = setup_password(
        harness.client,
        supabase_token=SUPABASE_TOKEN,
        password=PASSWORD,
    )
    duplicate = setup_password(
        harness.client,
        supabase_token=SUPABASE_TOKEN,
        password=NEW_PASSWORD,
    )

    harness.session.refresh(harness.user)
    events = list(
        harness.session.execute(
            select(AuditEventModel).where(
                AuditEventModel.action == "password.setup",
                AuditEventModel.target_user_id == harness.user.id,
            )
        ).scalars()
    )
    assert enrolled.status_code == 200
    assert enrolled.json()["password_configured"] is True
    assert harness.user.password_hash is not None
    assert harness.passwords.verify_password(harness.user.password_hash, PASSWORD)
    assert harness.user.auth_version == initial_auth_version + 1
    assert any(event.outcome == AuditOutcome.SUCCESS for event in events)
    assert duplicate.status_code == 409
    assert duplicate.json()["detail"] == "Password is already configured"


def test_identity_login_success_and_safe_failure_modes(
    dual_auth_harness: DualAuthHarness,
) -> None:
    harness = dual_auth_harness
    assert setup_password(
        harness.client,
        supabase_token=SUPABASE_TOKEN,
        password=PASSWORD,
    ).status_code == 200

    success, cookies = login_identity(
        harness.client,
        email=harness.user.email,
        password=PASSWORD,
    )
    wrong_password = harness.client.post(
        "/identity/login",
        json={"email": harness.user.email, "password": "wrong password value"},
    )
    unknown_user = harness.client.post(
        "/identity/login",
        json={"email": "unknown@example.invalid", "password": PASSWORD},
    )
    harness.user.locked_until = datetime.now(UTC) + timedelta(minutes=10)
    harness.session.commit()
    locked_account = harness.client.post(
        "/identity/login",
        json={"email": harness.user.email, "password": PASSWORD},
    )

    assert success.status_code == 200
    assert success.json()["session_id"] == cookies.session_id
    assert success.json().keys().isdisjoint({"access_token", "refresh_token"})
    for rejected in (wrong_password, unknown_user, locked_account):
        assert rejected.status_code == 401
        assert rejected.json()["detail"] == "Invalid email or password"


def test_me_reports_supabase_and_identity_sources_for_the_same_user(
    dual_auth_harness: DualAuthHarness,
) -> None:
    harness = dual_auth_harness
    setup_password(
        harness.client,
        supabase_token=SUPABASE_TOKEN,
        password=PASSWORD,
    )
    _, identity = login_identity(
        harness.client,
        email=harness.user.email,
        password=PASSWORD,
    )

    supabase_me = harness.client.get(
        "/identity/me",
        headers=_bearer(SUPABASE_TOKEN),
    )
    identity_me = harness.client.get(
        "/identity/me",
        headers=_bearer(identity.access_token),
    )
    supabase_after_identity_login = harness.client.get(
        "/identity/me",
        headers=_bearer(SECOND_SUPABASE_TOKEN),
    )

    assert supabase_me.status_code == 200
    assert identity_me.status_code == 200
    assert supabase_after_identity_login.status_code == 200
    assert supabase_me.json()["user_id"] == identity_me.json()["user_id"]
    assert supabase_me.json()["source"] == "supabase"
    assert identity_me.json()["source"] == "identity"
    assert identity_me.json()["session_id"] == identity.session_id
    assert supabase_after_identity_login.json()["source"] == "supabase"


def test_refresh_rotates_token_and_replay_revokes_the_session(
    dual_auth_harness: DualAuthHarness,
) -> None:
    harness = dual_auth_harness
    setup_password(
        harness.client,
        supabase_token=SUPABASE_TOKEN,
        password=PASSWORD,
    )
    _, original = login_identity(
        harness.client,
        email=harness.user.email,
        password=PASSWORD,
    )
    _, rotated = refresh_identity(
        harness.client,
        csrf_token=original.csrf_token,
    )

    harness.session.expire_all()
    auth_session = SessionsRepository(harness.session).get(UUID(original.session_id))
    assert auth_session is not None
    assert rotated.refresh_token != original.refresh_token
    assert rotated.access_token != original.access_token
    assert rotated.csrf_token != original.csrf_token
    assert auth_session.refresh_generation == 1

    with isolated_client(harness.app, cookies=original) as replay_client:
        replay = replay_client.post(
            "/identity/refresh",
            headers={"X-CSRF-Token": original.csrf_token},
        )
    _assert_unauthorized(replay)

    harness.session.expire_all()
    auth_session = SessionsRepository(harness.session).get(UUID(original.session_id))
    assert auth_session is not None
    assert auth_session.revoked_at is not None

    with isolated_client(harness.app, cookies=rotated) as successor_client:
        successor = successor_client.post(
            "/identity/refresh",
            headers={"X-CSRF-Token": rotated.csrf_token},
        )
    _assert_unauthorized(successor)


def test_logout_revokes_session_clears_cookies_and_blocks_refresh(
    dual_auth_harness: DualAuthHarness,
) -> None:
    harness = dual_auth_harness
    setup_password(
        harness.client,
        supabase_token=SUPABASE_TOKEN,
        password=PASSWORD,
    )
    _, identity = login_identity(
        harness.client,
        email=harness.user.email,
        password=PASSWORD,
    )

    logout = harness.client.post(
        "/identity/logout",
        headers={"X-CSRF-Token": identity.csrf_token},
    )
    set_cookie_headers = logout.headers.get_list("set-cookie")

    harness.session.expire_all()
    auth_session = SessionsRepository(harness.session).get(UUID(identity.session_id))
    assert logout.status_code == 204
    assert auth_session is not None
    assert auth_session.revoked_at is not None
    assert harness.client.cookies.get(IDENTITY_ACCESS_COOKIE) is None
    assert harness.client.cookies.get(IDENTITY_REFRESH_COOKIE) is None
    assert harness.client.cookies.get(IDENTITY_CSRF_COOKIE) is None
    assert any(
        header.startswith(f"{IDENTITY_REFRESH_COOKIE}=") and "Max-Age=0" in header
        for header in set_cookie_headers
    )

    with isolated_client(harness.app, cookies=identity) as stale_client:
        rejected = stale_client.post(
            "/identity/refresh",
            headers={"X-CSRF-Token": identity.csrf_token},
        )
    _assert_unauthorized(rejected)


def test_password_change_requires_current_password_and_invalidates_old_access(
    dual_auth_harness: DualAuthHarness,
) -> None:
    harness = dual_auth_harness
    setup_password(
        harness.client,
        supabase_token=SUPABASE_TOKEN,
        password=PASSWORD,
    )
    _, first_session = login_identity(
        harness.client,
        email=harness.user.email,
        password=PASSWORD,
        device="first-session",
    )
    _, current_session = login_identity(
        harness.client,
        email=harness.user.email,
        password=PASSWORD,
        device="current-session",
    )
    previous_auth_version = harness.user.auth_version

    missing_current_password = harness.client.post(
        "/identity/password/change",
        headers={"X-CSRF-Token": current_session.csrf_token},
        json={"new_password": NEW_PASSWORD},
    )
    wrong_current_password = harness.client.post(
        "/identity/password/change",
        headers={"X-CSRF-Token": current_session.csrf_token},
        json={
            "current_password": "wrong current password",
            "new_password": NEW_PASSWORD,
        },
    )
    changed = harness.client.post(
        "/identity/password/change",
        headers={"X-CSRF-Token": current_session.csrf_token},
        json={"current_password": PASSWORD, "new_password": NEW_PASSWORD},
    )
    changed_cookies = IdentitySessionCookies(
        access_token=harness.client.cookies.get(IDENTITY_ACCESS_COOKIE) or "",
        refresh_token=harness.client.cookies.get(IDENTITY_REFRESH_COOKIE) or "",
        csrf_token=harness.client.cookies.get(IDENTITY_CSRF_COOKIE) or "",
        session_id=changed.json()["session_id"],
    )

    harness.session.refresh(harness.user)
    harness.session.expire_all()
    first_record = SessionsRepository(harness.session).get(UUID(first_session.session_id))
    current_record = SessionsRepository(harness.session).get(
        UUID(current_session.session_id)
    )
    assert missing_current_password.status_code == 422
    assert wrong_current_password.status_code == 401
    assert changed.status_code == 200
    assert harness.user.auth_version == previous_auth_version + 1
    assert first_record is not None and first_record.revoked_at is not None
    assert current_record is not None and current_record.revoked_at is None

    with isolated_client(harness.app) as verifier:
        new_access = verifier.get(
            "/identity/me",
            headers=_bearer(changed_cookies.access_token),
        )
        previous_current_access = verifier.get(
            "/identity/me",
            headers=_bearer(current_session.access_token),
        )
        previous_other_access = verifier.get(
            "/identity/me",
            headers=_bearer(first_session.access_token),
        )
    assert new_access.status_code == 200, new_access.text
    assert new_access.json()["auth_version"] == harness.user.auth_version
    _assert_unauthorized(previous_current_access)
    _assert_unauthorized(previous_other_access)


def test_supabase_session_exchange_creates_identity_authenticated_session(
    dual_auth_harness: DualAuthHarness,
) -> None:
    harness = dual_auth_harness
    exchanged, identity = exchange_supabase_session(
        harness.client,
        supabase_token=SUPABASE_TOKEN,
    )

    identity_me = harness.client.get(
        "/identity/me",
        headers=_bearer(identity.access_token),
    )
    supabase_me = harness.client.get(
        "/identity/me",
        headers=_bearer(SUPABASE_TOKEN),
    )
    replay = harness.client.post(
        "/identity/session/exchange",
        headers=_bearer(SUPABASE_TOKEN),
        json={"device": "replayed-exchange"},
    )

    assert exchanged.status_code == 200
    assert identity_me.status_code == 200
    assert identity_me.json()["source"] == "identity"
    assert identity_me.json()["session_id"] == identity.session_id
    assert supabase_me.status_code == 200
    assert supabase_me.json()["source"] == "supabase"
    assert replay.status_code == 409
    assert replay.json()["detail"] == (
        "This Supabase session has already been exchanged"
    )


def test_session_listing_revokes_one_session_while_the_other_survives(
    dual_auth_harness: DualAuthHarness,
) -> None:
    harness = dual_auth_harness
    setup_password(
        harness.client,
        supabase_token=SUPABASE_TOKEN,
        password=PASSWORD,
    )
    _, first_session = login_identity(
        harness.client,
        email=harness.user.email,
        password=PASSWORD,
        device="first-device",
    )
    _, second_session = login_identity(
        harness.client,
        email=harness.user.email,
        password=PASSWORD,
        device="second-device",
    )

    listed = harness.client.get(
        "/identity/sessions",
        headers=_bearer(second_session.access_token),
    )
    revoked = harness.client.delete(
        f"/identity/sessions/{first_session.session_id}",
        headers=_bearer(second_session.access_token),
    )
    listed_after = harness.client.get(
        "/identity/sessions",
        headers=_bearer(second_session.access_token),
    )

    assert listed.status_code == 200
    assert {item["session_id"] for item in listed.json()} == {
        first_session.session_id,
        second_session.session_id,
    }
    assert revoked.status_code == 204
    session_states = {
        item["session_id"]: item["revoked_at"] for item in listed_after.json()
    }
    assert session_states[first_session.session_id] is not None
    assert session_states[second_session.session_id] is None

    with isolated_client(harness.app) as verifier:
        second_me = verifier.get(
            "/identity/me",
            headers=_bearer(second_session.access_token),
        )
        first_me = verifier.get(
            "/identity/me",
            headers=_bearer(first_session.access_token),
        )
    assert second_me.status_code == 200, second_me.text
    _assert_unauthorized(first_me)


def test_expired_and_tampered_identity_jwts_are_rejected(
    dual_auth_harness: DualAuthHarness,
) -> None:
    harness = dual_auth_harness
    setup_password(
        harness.client,
        supabase_token=SUPABASE_TOKEN,
        password=PASSWORD,
    )
    _, identity = login_identity(
        harness.client,
        email=harness.user.email,
        password=PASSWORD,
    )
    expired_issuer = JwtService(
        signing_key=SIGNING_KEY,
        key_id="integration-key",
        issuer="integration-issuer",
        audience="integration-audience",
        access_ttl=timedelta(minutes=1),
        clock_skew=timedelta(0),
    )
    expired_token, _ = expired_issuer.issue_access_token(
        user_id=harness.user.id,
        session_id=UUID(identity.session_id),
        auth_version=harness.user.auth_version,
        role="user",
        now=datetime.now(UTC) - timedelta(minutes=10),
    )

    with isolated_client(harness.app) as verifier:
        expired = verifier.get("/identity/me", headers=_bearer(expired_token))
        tampered = verifier.get(
            "/identity/me",
            headers=_bearer(_tamper(identity.access_token)),
        )
    _assert_unauthorized(expired)
    _assert_unauthorized(tampered)


def test_authentication_boundaries_and_csrf_fail_closed(
    dual_auth_harness: DualAuthHarness,
) -> None:
    harness = dual_auth_harness
    setup_password(
        harness.client,
        supabase_token=SUPABASE_TOKEN,
        password=PASSWORD,
    )
    _, identity = login_identity(
        harness.client,
        email=harness.user.email,
        password=PASSWORD,
    )

    identity_on_supabase_only = harness.client.post(
        "/identity/password/setup",
        headers=_bearer(identity.access_token),
        json={"new_password": NEW_PASSWORD},
    )
    supabase_on_identity_only = harness.client.get(
        "/identity/sessions",
        headers=_bearer(SUPABASE_TOKEN),
    )
    with isolated_client(harness.app) as anonymous:
        missing_bearer = anonymous.get("/identity/me")
    refresh_without_csrf = harness.client.post("/identity/refresh")
    refresh_with_mismatched_csrf = harness.client.post(
        "/identity/refresh",
        headers={"X-CSRF-Token": "not-the-cookie-value"},
    )

    assert identity_on_supabase_only.status_code == 401
    assert identity_on_supabase_only.json()["detail"] == (
        "Supabase bearer token required"
    )
    _assert_unauthorized(supabase_on_identity_only)
    assert missing_bearer.status_code == 401
    assert missing_bearer.json()["detail"] == "Missing bearer token"
    for rejected in (refresh_without_csrf, refresh_with_mismatched_csrf):
        assert rejected.status_code == 403
        assert rejected.json()["detail"] == "CSRF validation failed"


@pytest.mark.parametrize(
    "supabase_token",
    [SUPABASE_TOKEN, SECOND_SUPABASE_TOKEN],
    ids=["primary-supabase-session", "secondary-supabase-session"],
)
def test_supabase_and_identity_authentication_continue_to_coexist(
    dual_auth_harness: DualAuthHarness,
    supabase_token: str,
) -> None:
    harness = dual_auth_harness
    setup = setup_password(
        harness.client,
        supabase_token=SUPABASE_TOKEN,
        password=PASSWORD,
    )
    if setup.status_code == 409:
        assert setup.json()["detail"] == "Password is already configured"
    else:
        assert setup.status_code == 200
    _, identity = login_identity(
        harness.client,
        email=harness.user.email,
        password=PASSWORD,
    )

    supabase_request = harness.client.get(
        "/identity/me",
        headers=_bearer(supabase_token),
    )
    identity_request = harness.client.get(
        "/identity/me",
        headers=_bearer(identity.access_token),
    )

    assert supabase_request.status_code == 200
    assert identity_request.status_code == 200
    assert supabase_request.json()["user_id"] == identity_request.json()["user_id"]
    assert {
        supabase_request.json()["source"],
        identity_request.json()["source"],
    } == {"supabase", "identity"}
