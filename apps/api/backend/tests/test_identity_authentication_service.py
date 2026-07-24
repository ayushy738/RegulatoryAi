from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import jwt
import pytest
from argon2 import PasswordHasher
from argon2.low_level import Type
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from backend.identity.enums import AuditOutcome, IdentityUserStatus
from backend.identity.exceptions import (
    InvalidCredentialsError,
    InvalidIdentityTokenError,
    InvalidSessionError,
    RateLimitExceededError,
    ReconciliationDriftError,
    SessionExchangeReplayError,
)
from backend.identity.models import (
    AuditEventModel,
    IdentityBase,
    IdentityUserModel,
)
from backend.identity.repositories import (
    AuditRepository,
    AuthenticationRateLimitsRepository,
    RoleAssignmentsRepository,
    SessionExchangesRepository,
    SessionsRepository,
    UsersRepository,
)
from backend.identity.services.authentication import (
    AuthenticationService,
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

SIGNING_KEY = "s" * 32
TOKEN_PEPPER = "p" * 32
PASSWORD = "correct horse battery staple"
NEW_PASSWORD = "a newer correct horse battery staple"


@dataclass
class AuthHarness:
    session: Session
    service: AuthenticationService
    users: UsersRepository
    sessions: SessionsRepository
    jwt: JwtService
    context: RequestSecurityContext
    reconciliation: ReconciliationState

    def add_user(
        self,
        *,
        email: str = "user@example.com",
        password_hash: str | None = None,
    ) -> IdentityUserModel:
        return self.users.add(
            IdentityUserModel(
                email=email,
                email_normalized=email.lower(),
                password_hash=password_hash,
                status=IdentityUserStatus.ACTIVE,
                email_verified_at=datetime.now(UTC),
            )
        )


@dataclass
class ReconciliationState:
    drifted_user_ids: set[UUID] = field(default_factory=set)

    def has_drift(self, user_id: UUID) -> bool:
        return user_id in self.drifted_user_ids


@pytest.fixture
def auth_harness() -> Iterator[AuthHarness]:
    engine = create_engine("sqlite:///:memory:")
    connection = engine.connect()
    connection.exec_driver_sql("ATTACH DATABASE ':memory:' AS identity")
    connection.exec_driver_sql("PRAGMA foreign_keys = ON")
    IdentityBase.metadata.create_all(connection)
    session = Session(bind=connection)
    users = UsersRepository(session)
    sessions = SessionsRepository(session)
    password_service = PasswordService(
        PasswordHasher(
            time_cost=1,
            memory_cost=8192,
            parallelism=1,
            hash_len=16,
            salt_len=8,
            type=Type.ID,
        )
    )
    jwt_service = JwtService(
        signing_key=SIGNING_KEY,
        key_id="test-key",
        issuer="test-issuer",
        audience="test-audience",
        access_ttl=timedelta(minutes=5),
        clock_skew=timedelta(0),
    )
    reconciliation = ReconciliationState()
    service = AuthenticationService(
        users=users,
        sessions=SessionService(sessions),
        audit=AuditRepository(session),
        passwords=password_service,
        jwt_tokens=jwt_service,
        refresh_tokens=RefreshTokenService(TOKEN_PEPPER),
        csrf_tokens=CsrfTokenService(TOKEN_PEPPER),
        metadata_hasher=SecurityMetadataHasher(TOKEN_PEPPER),
        rate_limits=AuthenticationRateLimitService(
            AuthenticationRateLimitsRepository(session)
        ),
        reconciliation=reconciliation,
        role_assignments=RoleAssignmentsRepository(session),
        exchanges=SessionExchangesRepository(session),
        session_ttl=timedelta(days=30),
        password_min_length=12,
        password_max_length=128,
        failed_login_limit=3,
        account_lock_duration=timedelta(minutes=15),
        login_account_rate_limit=100,
        login_ip_rate_limit=100,
        login_rate_window=timedelta(minutes=15),
        refresh_rate_limit=100,
        refresh_rate_window=timedelta(minutes=1),
        password_rate_limit=100,
        password_rate_window=timedelta(minutes=15),
        exchange_rate_limit=100,
        exchange_rate_window=timedelta(hours=1),
    )
    context = RequestSecurityContext(
        ip_hash=b"i" * 32,
        user_agent_hash=b"u" * 32,
        ip_rate_limit_hash=b"r" * 32,
        request_id="test-request",
    )
    try:
        yield AuthHarness(
            session,
            service,
            users,
            sessions,
            jwt_service,
            context,
            reconciliation,
        )
    finally:
        session.close()
        connection.close()
        engine.dispose()


def test_verified_password_setup_enables_first_party_login(
    auth_harness: AuthHarness,
) -> None:
    user = auth_harness.add_user()

    configured_user_id = auth_harness.service.setup_password(
        user_id=user.id,
        new_password=PASSWORD,
        context=auth_harness.context,
    )
    issued = auth_harness.service.login(
        email=user.email,
        password=PASSWORD,
        device="test-browser",
        context=auth_harness.context,
    )
    principal = auth_harness.service.authenticate_access_token(issued.access_token)

    assert configured_user_id == user.id
    assert user.password_hash is not None
    assert user.auth_version == 2
    assert principal.user_id == user.id
    assert principal.session_id == issued.session_id


def test_user_without_password_and_wrong_password_cannot_login(
    auth_harness: AuthHarness,
) -> None:
    user = auth_harness.add_user()

    with pytest.raises(InvalidCredentialsError) as no_password:
        auth_harness.service.login(
            email=user.email,
            password=PASSWORD,
            device=None,
            context=auth_harness.context,
        )
    assert no_password.value.public_message == "Invalid email or password"

    auth_harness.service.setup_password(
        user_id=user.id,
        new_password=PASSWORD,
        context=auth_harness.context,
    )
    with pytest.raises(InvalidCredentialsError):
        auth_harness.service.login(
            email=user.email,
            password="this password is incorrect",
            device=None,
            context=auth_harness.context,
        )
    assert user.failed_login_count == 1


def test_repeated_failures_lock_account_and_correct_password_stays_denied(
    auth_harness: AuthHarness,
) -> None:
    password_service = PasswordService(
        PasswordHasher(
            time_cost=1,
            memory_cost=8192,
            parallelism=1,
            hash_len=16,
            salt_len=8,
            type=Type.ID,
        )
    )
    user = auth_harness.add_user(
        password_hash=password_service.hash_password(PASSWORD)
    )
    for _ in range(3):
        with pytest.raises(InvalidCredentialsError):
            auth_harness.service.login(
                email=user.email,
                password="this password is incorrect",
                device=None,
                context=auth_harness.context,
            )

    assert user.locked_until is not None
    with pytest.raises(InvalidCredentialsError):
        auth_harness.service.login(
            email=user.email,
            password=PASSWORD,
            device=None,
            context=auth_harness.context,
        )
    actions = list(
        auth_harness.session.execute(select(AuditEventModel.action)).scalars()
    )
    assert actions.count("authentication.account_locked") == 1


@pytest.mark.parametrize(
    ("status", "reason_code"),
    [
        (IdentityUserStatus.DISABLED, "ACCOUNT_UNAVAILABLE"),
        (IdentityUserStatus.LOCKED, "ACCOUNT_LOCKED"),
    ],
)
def test_disabled_and_locked_accounts_cannot_login(
    auth_harness: AuthHarness,
    status: IdentityUserStatus,
    reason_code: str,
) -> None:
    password_hash = PasswordService(
        PasswordHasher(
            time_cost=1,
            memory_cost=8192,
            parallelism=1,
            hash_len=16,
            salt_len=8,
            type=Type.ID,
        )
    ).hash_password(PASSWORD)
    user = auth_harness.add_user(
        email=f"{status.value}@example.com",
        password_hash=password_hash,
    )
    user.status = status

    with pytest.raises(InvalidCredentialsError):
        auth_harness.service.login(
            email=user.email,
            password=PASSWORD,
            device=None,
            context=auth_harness.context,
        )

    event = auth_harness.session.execute(
        select(AuditEventModel)
        .where(AuditEventModel.action == "authentication.login")
        .order_by(AuditEventModel.occurred_at.desc())
    ).scalars().first()
    assert event is not None
    assert event.outcome == AuditOutcome.FAILURE
    assert event.reason_code == reason_code


def test_refresh_rotates_token_and_replay_revokes_session(
    auth_harness: AuthHarness,
) -> None:
    user = auth_harness.add_user()
    auth_harness.service.setup_password(
        user_id=user.id,
        new_password=PASSWORD,
        context=auth_harness.context,
    )
    original = auth_harness.service.login(
        email=user.email,
        password=PASSWORD,
        device=None,
        context=auth_harness.context,
    )

    rotated = auth_harness.service.refresh(
        refresh_token=original.refresh_token,
        expected_session_id=original.session_id,
        context=auth_harness.context,
    )

    assert rotated.refresh_token != original.refresh_token
    assert rotated.session_id == original.session_id
    assert auth_harness.sessions.get(original.session_id).refresh_generation == 1

    with pytest.raises(InvalidSessionError):
        auth_harness.service.refresh(
            refresh_token=original.refresh_token,
            expected_session_id=original.session_id,
            context=auth_harness.context,
        )
    assert auth_harness.sessions.get(original.session_id).revoked_at is not None
    actions = set(
        auth_harness.session.execute(select(AuditEventModel.action)).scalars()
    )
    assert "authentication.token_replay" in actions
    assert "authentication.session_revoked" in actions


def test_logout_revokes_only_the_presented_session(auth_harness: AuthHarness) -> None:
    user = auth_harness.add_user()
    auth_harness.service.setup_password(
        user_id=user.id,
        new_password=PASSWORD,
        context=auth_harness.context,
    )
    first = auth_harness.service.login(
        email=user.email,
        password=PASSWORD,
        device="first",
        context=auth_harness.context,
    )
    second = auth_harness.service.login(
        email=user.email,
        password=PASSWORD,
        device="second",
        context=auth_harness.context,
    )

    auth_harness.service.logout(
        refresh_token=first.refresh_token,
        expected_session_id=first.session_id,
        context=auth_harness.context,
    )

    assert auth_harness.sessions.get(first.session_id).revoked_at is not None
    assert auth_harness.sessions.get(second.session_id).revoked_at is None
    assert len(auth_harness.sessions.list_for_user(user.id)) == 2


def test_jwt_validation_rejects_expired_tokens() -> None:
    jwt_service = JwtService(
        signing_key=SIGNING_KEY,
        key_id="test-key",
        issuer="test-issuer",
        audience="test-audience",
        access_ttl=timedelta(minutes=5),
        clock_skew=timedelta(0),
    )
    token, _ = jwt_service.issue_access_token(
        user_id=uuid4(),
        session_id=uuid4(),
        auth_version=1,
        role="user",
        now=datetime.now(UTC) - timedelta(hours=1),
    )

    with pytest.raises(InvalidIdentityTokenError):
        jwt_service.verify_access_token(token)


def test_jwt_contains_and_validates_required_identity_claims() -> None:
    jwt_service = JwtService(
        signing_key=SIGNING_KEY,
        key_id="test-key",
        issuer="test-issuer",
        audience="test-audience",
        access_ttl=timedelta(minutes=5),
        clock_skew=timedelta(0),
    )
    user_id = uuid4()
    session_id = uuid4()

    token, expected = jwt_service.issue_access_token(
        user_id=user_id,
        session_id=session_id,
        auth_version=7,
        role="admin",
    )
    header = jwt.get_unverified_header(token)
    payload = jwt.decode(
        token,
        options={
            "verify_signature": False,
            "verify_aud": False,
            "verify_exp": False,
        },
    )
    verified = jwt_service.verify_access_token(token)

    assert header["kid"] == "test-key"
    assert payload["iss"] == "test-issuer"
    assert payload["aud"] == "test-audience"
    assert payload["sub"] == str(user_id)
    assert payload["session_id"] == str(session_id)
    assert payload["auth_version"] == 7
    assert payload["role"] == "admin"
    assert payload["nbf"] == payload["iat"]
    assert payload["exp"] > payload["iat"]
    assert verified.user_id == expected.user_id
    assert verified.session_id == expected.session_id
    assert verified.auth_version == expected.auth_version
    assert verified.role == expected.role
    assert verified.token_id == expected.token_id


def test_database_rate_limiter_blocks_and_recovers_after_window(
    auth_harness: AuthHarness,
) -> None:
    limiter = AuthenticationRateLimitService(
        AuthenticationRateLimitsRepository(auth_harness.session)
    )
    observed_at = datetime.now(UTC)
    subject_hash = b"z" * 32

    limiter.consume(
        scope="test.login",
        subject_hash=subject_hash,
        limit=2,
        window=timedelta(minutes=1),
        now=observed_at,
    )
    limiter.consume(
        scope="test.login",
        subject_hash=subject_hash,
        limit=2,
        window=timedelta(minutes=1),
        now=observed_at,
    )
    with pytest.raises(RateLimitExceededError):
        limiter.consume(
            scope="test.login",
            subject_hash=subject_hash,
            limit=2,
            window=timedelta(minutes=1),
            now=observed_at,
        )

    limiter.consume(
        scope="test.login",
        subject_hash=subject_hash,
        limit=2,
        window=timedelta(minutes=1),
        now=observed_at + timedelta(minutes=2),
    )


def test_database_rate_limiter_prevents_fixed_window_boundary_burst(
    auth_harness: AuthHarness,
) -> None:
    limiter = AuthenticationRateLimitService(
        AuthenticationRateLimitsRepository(auth_harness.session)
    )
    end_of_bucket = datetime(2030, 1, 1, 0, 0, 59, tzinfo=UTC)
    subject_hash = b"y" * 32

    for _ in range(2):
        limiter.consume(
            scope="test.sliding-login",
            subject_hash=subject_hash,
            limit=2,
            window=timedelta(minutes=1),
            now=end_of_bucket,
        )

    with pytest.raises(RateLimitExceededError):
        limiter.consume(
            scope="test.sliding-login",
            subject_hash=subject_hash,
            limit=2,
            window=timedelta(minutes=1),
            now=end_of_bucket + timedelta(seconds=2),
        )


def test_jwt_verification_key_ring_supports_zero_downtime_rotation() -> None:
    old_key = "o" * 32
    new_key = "n" * 32
    old_service = JwtService(
        signing_key=old_key,
        key_id="old-key",
        issuer="test-issuer",
        audience="test-audience",
        access_ttl=timedelta(minutes=5),
    )
    token, expected = old_service.issue_access_token(
        user_id=uuid4(),
        session_id=uuid4(),
        auth_version=1,
        role="admin",
    )
    rotated_service = JwtService(
        signing_key=new_key,
        key_id="new-key",
        verification_keys={"old-key": old_key},
        issuer="test-issuer",
        audience="test-audience",
        access_ttl=timedelta(minutes=5),
    )

    assert rotated_service.verify_access_token(token).token_id == expected.token_id


def test_auth_version_change_invalidates_existing_access_token(
    auth_harness: AuthHarness,
) -> None:
    user = auth_harness.add_user()
    auth_harness.service.setup_password(
        user_id=user.id,
        new_password=PASSWORD,
        context=auth_harness.context,
    )
    issued = auth_harness.service.login(
        email=user.email,
        password=PASSWORD,
        device=None,
        context=auth_harness.context,
    )
    user.auth_version += 1

    with pytest.raises(InvalidIdentityTokenError):
        auth_harness.service.authenticate_access_token(issued.access_token)


def test_password_change_rotates_current_session_and_revokes_other_sessions(
    auth_harness: AuthHarness,
) -> None:
    user = auth_harness.add_user()
    auth_harness.service.setup_password(
        user_id=user.id,
        new_password=PASSWORD,
        context=auth_harness.context,
    )
    current = auth_harness.service.login(
        email=user.email,
        password=PASSWORD,
        device="current",
        context=auth_harness.context,
    )
    other = auth_harness.service.login(
        email=user.email,
        password=PASSWORD,
        device="other",
        context=auth_harness.context,
    )
    principal = auth_harness.service.authenticate_access_token(current.access_token)

    changed = auth_harness.service.change_password(
        principal=principal,
        current_password=PASSWORD,
        new_password=NEW_PASSWORD,
        context=auth_harness.context,
    )

    assert changed.refresh_token != current.refresh_token
    assert auth_harness.sessions.get(current.session_id).revoked_at is None
    assert auth_harness.sessions.get(other.session_id).revoked_at is not None
    assert auth_harness.service.authenticate_access_token(changed.access_token).user_id == user.id
    with pytest.raises(InvalidIdentityTokenError):
        auth_harness.service.authenticate_access_token(current.access_token)


def test_supabase_session_exchange_is_single_use_and_supports_password_change(
    auth_harness: AuthHarness,
) -> None:
    password_service = PasswordService(
        PasswordHasher(
            time_cost=1,
            memory_cost=8192,
            parallelism=1,
            hash_len=16,
            salt_len=8,
            type=Type.ID,
        )
    )
    user = auth_harness.add_user(
        password_hash=password_service.hash_password(PASSWORD)
    )
    source_hash = b"x" * 32
    issued = auth_harness.service.exchange_supabase_session(
        user_id=user.id,
        source_session_hash=source_hash,
        source_authenticated_at=datetime.now(UTC) - timedelta(minutes=1),
        source_expires_at=datetime.now(UTC) + timedelta(hours=1),
        device="exchange-test",
        context=auth_harness.context,
    )
    principal = auth_harness.service.authenticate_access_token(issued.access_token)

    assert principal.user_id == user.id
    with pytest.raises(SessionExchangeReplayError):
        auth_harness.service.exchange_supabase_session(
            user_id=user.id,
            source_session_hash=source_hash,
            source_authenticated_at=datetime.now(UTC) - timedelta(minutes=1),
            source_expires_at=datetime.now(UTC) + timedelta(hours=1),
            device="replay",
            context=auth_harness.context,
        )

    changed = auth_harness.service.change_password(
        principal=principal,
        current_password=PASSWORD,
        new_password=NEW_PASSWORD,
        context=auth_harness.context,
    )
    assert auth_harness.service.authenticate_access_token(changed.access_token).user_id == user.id


def test_drift_rejects_exchange_and_existing_identity_session(
    auth_harness: AuthHarness,
) -> None:
    user = auth_harness.add_user(
        password_hash=PasswordService(
            PasswordHasher(
                time_cost=1,
                memory_cost=8192,
                parallelism=1,
                hash_len=16,
                salt_len=8,
                type=Type.ID,
            )
        ).hash_password(PASSWORD)
    )
    issued = auth_harness.service.login(
        email=user.email,
        password=PASSWORD,
        device=None,
        context=auth_harness.context,
    )
    auth_harness.reconciliation.drifted_user_ids.add(user.id)

    with pytest.raises(InvalidIdentityTokenError) as token_error:
        auth_harness.service.authenticate_access_token(issued.access_token)
    assert token_error.value.code == "RECONCILIATION_DRIFT"

    with pytest.raises(ReconciliationDriftError):
        auth_harness.service.exchange_supabase_session(
            user_id=user.id,
            source_session_hash=b"d" * 32,
            source_authenticated_at=datetime.now(UTC) - timedelta(minutes=1),
            source_expires_at=datetime.now(UTC) + timedelta(hours=1),
            device=None,
            context=auth_harness.context,
        )


def test_authentication_actions_append_success_and_failure_audit_events(
    auth_harness: AuthHarness,
) -> None:
    user = auth_harness.add_user(
        password_hash=PasswordService(
            PasswordHasher(
                time_cost=1,
                memory_cost=8192,
                parallelism=1,
                hash_len=16,
                salt_len=8,
                type=Type.ID,
            )
        ).hash_password(PASSWORD)
    )

    with pytest.raises(InvalidCredentialsError):
        auth_harness.service.login(
            email=user.email,
            password="this password is incorrect",
            device=None,
            context=auth_harness.context,
        )
    auth_harness.service.login(
        email=user.email,
        password=PASSWORD,
        device=None,
        context=auth_harness.context,
    )

    events = list(
        auth_harness.session.execute(
            select(AuditEventModel).where(
                AuditEventModel.action == "authentication.login"
            )
        ).scalars()
    )
    assert {event.outcome for event in events} == {
        AuditOutcome.FAILURE,
        AuditOutcome.SUCCESS,
    }
    assert all(event.ip_hash == b"i" * 32 for event in events)
