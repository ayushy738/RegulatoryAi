from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.identity.enums import AuditOutcome, IdentityUserStatus
from backend.identity.models import (
    AuditEventModel,
    AuthenticationMetricModel,
    AuthSessionModel,
    EmailVerificationTokenModel,
    IdentityBase,
    IdentityProfileModel,
    IdentityUserModel,
    PasswordResetTokenModel,
    PermissionModel,
    RoleModel,
    RolePermissionModel,
    UserRoleAssignmentModel,
)
from backend.identity.repositories import (
    AuditRepository,
    AuthenticationMetricsRepository,
    PasswordResetRepository,
    PermissionsRepository,
    ProfilesRepository,
    RoleAssignmentsRepository,
    RolesRepository,
    SessionsRepository,
    UsersRepository,
    VerificationRepository,
)


@pytest.fixture
def db_session() -> Iterator[Session]:
    engine = create_engine("sqlite:///:memory:")
    connection = engine.connect()
    connection.exec_driver_sql("ATTACH DATABASE ':memory:' AS identity")
    connection.exec_driver_sql("PRAGMA foreign_keys = ON")
    IdentityBase.metadata.create_all(connection)
    session = Session(bind=connection)
    try:
        yield session
    finally:
        session.close()
        connection.close()
        engine.dispose()


def _user(email: str = "user@example.com") -> IdentityUserModel:
    return IdentityUserModel(
        email=email,
        email_normalized=email.strip().lower(),
        password_hash=None,
        status=IdentityUserStatus.PENDING_VERIFICATION,
    )


def test_authentication_metrics_are_aggregated_by_hour_and_source(
    db_session: Session,
) -> None:
    metrics = AuthenticationMetricsRepository(db_session)
    observed_at = datetime(2026, 7, 24, 12, 30, tzinfo=UTC)

    metrics.increment(
        source="identity",
        outcome="failure",
        reason_code="SESSION_REVOKED",
        observed_at=observed_at,
    )
    metrics.increment(
        source="identity",
        outcome="failure",
        reason_code="SESSION_REVOKED",
        observed_at=observed_at + timedelta(minutes=20),
    )

    observation = db_session.execute(select(AuthenticationMetricModel)).scalar_one()
    assert observation.bucket_started_at.replace(tzinfo=UTC) == observed_at.replace(
        minute=0
    )
    assert observation.source == "identity"
    assert observation.outcome == "failure"
    assert observation.reason_code == "SESSION_REVOKED"
    assert observation.observation_count == 2


def test_user_and_profile_repository_crud(db_session: Session) -> None:
    users = UsersRepository(db_session)
    profiles = ProfilesRepository(db_session)
    user = users.add(_user())

    assert user.password_hash is None
    assert users.get(user.id) is user
    assert users.get_by_normalized_email("user@example.com") is user

    profile = profiles.add(IdentityProfileModel(user_id=user.id, display_name="Original Name"))
    profile.display_name = "Updated Name"
    saved_profile = profiles.save(profile)

    assert profiles.get(user.id) is saved_profile
    assert saved_profile.display_name == "Updated Name"

    profiles.delete(saved_profile)
    assert profiles.get(user.id) is None


def test_identity_user_email_is_unique(db_session: Session) -> None:
    users = UsersRepository(db_session)
    users.add(_user("Unique@Example.com"))

    with pytest.raises(IntegrityError):
        users.add(_user("unique@example.com"))


def test_role_permission_and_assignment_repositories(db_session: Session) -> None:
    users = UsersRepository(db_session)
    roles = RolesRepository(db_session)
    permissions = PermissionsRepository(db_session)
    assignments = RoleAssignmentsRepository(db_session)

    user = users.add(_user())
    role = roles.add(RoleModel(code="user", name="User", is_system=True))
    permission = permissions.add(
        PermissionModel(
            code="application.access",
            resource="application",
            action="access",
        )
    )
    permissions.add_role_permission(
        RolePermissionModel(role_id=role.id, permission_id=permission.id)
    )
    assignment = assignments.add(
        UserRoleAssignmentModel(
            user_id=user.id,
            role_id=role.id,
            reason="Initial assignment",
        )
    )

    assert roles.get_by_code("user") is role
    assert permissions.get_by_code("application.access") is permission
    assert permissions.list_for_role(role.id) == [permission]
    assert assignments.get_active_for_user(user.id) is assignment

    with pytest.raises(IntegrityError):
        assignments.add(
            UserRoleAssignmentModel(
                user_id=user.id,
                role_id=role.id,
                reason="Duplicate active assignment",
            )
        )


def test_token_session_and_audit_repository_crud(db_session: Session) -> None:
    now = datetime.now(UTC)
    user = UsersRepository(db_session).add(_user())
    password_resets = PasswordResetRepository(db_session)
    verifications = VerificationRepository(db_session)
    sessions = SessionsRepository(db_session)
    audit = AuditRepository(db_session)

    reset_token = password_resets.add(
        PasswordResetTokenModel(
            user_id=user.id,
            token_hash=b"r" * 32,
            created_at=now,
            expires_at=now + timedelta(hours=1),
        )
    )
    verification_token = verifications.add(
        EmailVerificationTokenModel(
            user_id=user.id,
            email_normalized=user.email_normalized,
            token_hash=b"v" * 32,
            created_at=now,
            expires_at=now + timedelta(hours=24),
        )
    )
    auth_session = sessions.add(
        AuthSessionModel(
            user_id=user.id,
            auth_version=user.auth_version,
            created_at=now,
            last_seen_at=now,
            expires_at=now + timedelta(days=1),
        )
    )
    event = audit.append(
        AuditEventModel(
            actor_user_id=user.id,
            target_user_id=user.id,
            session_id=auth_session.sid,
            action="identity.created",
            outcome=AuditOutcome.SUCCESS,
            event_metadata={"source": "repository-test"},
        )
    )

    assert password_resets.get_by_hash(b"r" * 32) is reset_token
    assert verifications.get_by_hash(b"v" * 32) is verification_token
    assert sessions.list_for_user(user.id) == [auth_session]
    assert audit.get(event.id) is event
    assert audit.list(action="identity.created") == [event]

    reset_token.consumed_at = now + timedelta(minutes=1)
    assert password_resets.save(reset_token).consumed_at is not None
    verification_token.consumed_at = now + timedelta(minutes=1)
    assert verifications.save(verification_token).consumed_at is not None


def test_repository_delete_operations(db_session: Session) -> None:
    now = datetime.now(UTC)
    users = UsersRepository(db_session)
    roles = RolesRepository(db_session)
    permissions = PermissionsRepository(db_session)
    assignments = RoleAssignmentsRepository(db_session)
    password_resets = PasswordResetRepository(db_session)
    verifications = VerificationRepository(db_session)
    sessions = SessionsRepository(db_session)

    user = users.add(_user("delete@example.com"))
    role = roles.add(RoleModel(code="temporary", name="Temporary"))
    permission = permissions.add(
        PermissionModel(
            code="temporary.access",
            resource="temporary",
            action="access",
        )
    )
    assignment = assignments.add(UserRoleAssignmentModel(user_id=user.id, role_id=role.id))
    reset = password_resets.add(
        PasswordResetTokenModel(
            user_id=user.id,
            token_hash=b"d" * 32,
            created_at=now,
            expires_at=now + timedelta(hours=1),
        )
    )
    verification = verifications.add(
        EmailVerificationTokenModel(
            user_id=user.id,
            email_normalized=user.email_normalized,
            token_hash=b"e" * 32,
            created_at=now,
            expires_at=now + timedelta(hours=1),
        )
    )
    auth_session = sessions.add(
        AuthSessionModel(
            user_id=user.id,
            auth_version=1,
            created_at=now,
            last_seen_at=now,
            expires_at=now + timedelta(hours=1),
        )
    )

    assignments.delete(assignment)
    password_resets.delete(reset)
    verifications.delete(verification)
    sessions.delete(auth_session)
    permissions.delete(permission)
    roles.delete(role)
    users.delete(user)

    assert assignments.get(assignment.id) is None
    assert password_resets.get(reset.id) is None
    assert verifications.get(verification.id) is None
    assert sessions.get(auth_session.sid) is None
    assert permissions.get(permission.id) is None
    assert roles.get(role.id) is None
    assert users.get(user.id) is None
