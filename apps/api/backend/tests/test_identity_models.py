from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from pydantic import ValidationError

from backend.identity.enums import AuditOutcome, IdentityUserStatus
from backend.identity.models import (
    IDENTITY_SCHEMA,
    AuditEventModel,
    IdentityBase,
    IdentityUserModel,
)
from backend.identity.schemas import (
    AuditEvent,
    CoexistenceRun,
    IdentityUser,
    Permission,
    RoleAssignment,
)

EXPECTED_TABLES = {
    "audit_events",
    "authentication_rate_limits",
    "authentication_metrics_hourly",
    "auth_sessions",
    "coexistence_runs",
    "email_verification_tokens",
    "password_reset_tokens",
    "permissions",
    "role_permissions",
    "roles",
    "session_exchanges",
    "user_profiles",
    "user_role_assignments",
    "users",
}


def test_model_metadata_contains_the_complete_identity_schema() -> None:
    assert {table.name for table in IdentityBase.metadata.tables.values()} == EXPECTED_TABLES
    assert {table.schema for table in IdentityBase.metadata.tables.values()} == {IDENTITY_SCHEMA}


def test_identity_user_model_allows_a_null_password_hash() -> None:
    assert IdentityUserModel.__table__.c.password_hash.nullable is True


def test_identity_models_do_not_reference_supabase_or_public_tables() -> None:
    foreign_key_targets = {
        foreign_key.target_fullname
        for table in IdentityBase.metadata.tables.values()
        for foreign_key in table.foreign_keys
    }

    assert foreign_key_targets
    assert all(target.startswith("identity.") for target in foreign_key_targets)


def test_identity_user_schema_validates_normalized_email() -> None:
    now = datetime.now(UTC)
    data = {
        "id": uuid4(),
        "email": " User@Example.com ",
        "email_normalized": "user@example.com",
        "password_hash": None,
        "status": IdentityUserStatus.PENDING_VERIFICATION,
        "auth_version": 1,
        "failed_login_count": 0,
        "created_at": now,
        "updated_at": now,
    }

    assert IdentityUser.model_validate(data).email_normalized == "user@example.com"

    with pytest.raises(ValidationError):
        IdentityUser.model_validate({**data, "email_normalized": "USER@example.com"})


def test_permission_schema_requires_resource_action_consistency() -> None:
    now = datetime.now(UTC)
    valid = {
        "id": uuid4(),
        "code": "admin.access",
        "resource": "admin",
        "action": "access",
        "description": None,
        "created_at": now,
    }

    assert Permission.model_validate(valid).code == "admin.access"

    with pytest.raises(ValidationError):
        Permission.model_validate({**valid, "code": "application.access"})


def test_role_assignment_schema_rejects_backdated_revocation() -> None:
    granted_at = datetime.now(UTC)

    with pytest.raises(ValidationError):
        RoleAssignment.model_validate(
            {
                "id": uuid4(),
                "user_id": uuid4(),
                "role_id": uuid4(),
                "granted_at": granted_at,
                "revoked_at": granted_at - timedelta(seconds=1),
            }
        )


def test_audit_event_schema_reads_the_mapped_metadata_attribute() -> None:
    event = AuditEventModel(
        id=uuid4(),
        occurred_at=datetime.now(UTC),
        action="identity.created",
        outcome=AuditOutcome.SUCCESS,
        event_metadata={"source": "test"},
    )

    assert AuditEvent.model_validate(event).metadata == {"source": "test"}


def test_coexistence_run_schema_enforces_terminal_state() -> None:
    now = datetime.now(UTC)
    data = {
        "id": uuid4(),
        "run_type": "reconciliation",
        "status": "succeeded",
        "started_at": now,
        "finished_at": now,
        "users_seen": 5,
        "users_changed": 0,
        "profiles_seen": 5,
        "profiles_changed": 0,
        "roles_changed": 0,
        "drift_count": 0,
        "metadata": {},
    }

    assert CoexistenceRun.model_validate(data).status == "succeeded"

    with pytest.raises(ValidationError):
        CoexistenceRun.model_validate({**data, "finished_at": None})
