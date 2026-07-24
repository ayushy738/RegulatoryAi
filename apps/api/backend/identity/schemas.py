from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, model_validator

from backend.identity.enums import AuditOutcome, IdentityUserStatus

ROLE_CODE_PATTERN = r"^[a-z][a-z0-9_.-]{0,63}$"
PERMISSION_CODE_PATTERN = r"^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$"
PERMISSION_PART_PATTERN = r"^[a-z][a-z0-9_]*$"
AUDIT_ACTION_PATTERN = PERMISSION_CODE_PATTERN
REASON_CODE_PATTERN = r"^[A-Z][A-Z0-9_]{0,99}$"


class IdentitySchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class IdentityUser(IdentitySchema):
    id: UUID
    email: str = Field(min_length=1)
    email_normalized: str = Field(min_length=1)
    password_hash: str | None = None
    status: IdentityUserStatus
    email_verified_at: datetime | None = None
    auth_version: int = Field(gt=0)
    failed_login_count: int = Field(ge=0)
    locked_until: datetime | None = None
    password_changed_at: datetime | None = None
    last_login_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None = None

    @model_validator(mode="after")
    def validate_normalized_email(self) -> "IdentityUser":
        if self.email_normalized != self.email.strip().lower():
            raise ValueError("email_normalized must equal the trimmed lowercase email")
        return self


class IdentityProfile(IdentitySchema):
    user_id: UUID
    display_name: str | None = Field(default=None, max_length=200)
    organization: str | None = Field(default=None, max_length=255)
    avatar_url: str | None = Field(default=None, max_length=2048)
    preferences: dict[str, Any] = Field(default_factory=dict)
    bio: str | None = Field(default=None, max_length=2000)
    created_at: datetime
    updated_at: datetime


class Role(IdentitySchema):
    id: UUID
    code: str = Field(pattern=ROLE_CODE_PATTERN)
    name: str = Field(min_length=1, max_length=100)
    description: str | None = None
    is_system: bool
    created_at: datetime
    updated_at: datetime


class Permission(IdentitySchema):
    id: UUID
    code: str = Field(pattern=PERMISSION_CODE_PATTERN)
    resource: str = Field(pattern=PERMISSION_PART_PATTERN)
    action: str = Field(pattern=PERMISSION_PART_PATTERN)
    description: str | None = None
    created_at: datetime

    @model_validator(mode="after")
    def validate_permission_code(self) -> "Permission":
        if self.code != f"{self.resource}.{self.action}":
            raise ValueError("permission code must equal resource.action")
        return self


class RoleAssignment(IdentitySchema):
    id: UUID
    user_id: UUID
    role_id: UUID
    granted_by: UUID | None = None
    granted_at: datetime
    revoked_at: datetime | None = None
    reason: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def validate_revocation_time(self) -> "RoleAssignment":
        if self.revoked_at is not None and self.revoked_at < self.granted_at:
            raise ValueError("revoked_at cannot precede granted_at")
        return self


class PasswordResetToken(IdentitySchema):
    id: UUID
    user_id: UUID
    token_hash: bytes = Field(min_length=32, max_length=32)
    created_at: datetime
    expires_at: datetime
    consumed_at: datetime | None = None
    invalidated_at: datetime | None = None


class EmailVerificationToken(IdentitySchema):
    id: UUID
    user_id: UUID
    email_normalized: str = Field(min_length=1)
    token_hash: bytes = Field(min_length=32, max_length=32)
    created_at: datetime
    expires_at: datetime
    consumed_at: datetime | None = None
    invalidated_at: datetime | None = None


class Session(IdentitySchema):
    sid: UUID
    user_id: UUID
    auth_version: int = Field(gt=0)
    created_at: datetime
    last_seen_at: datetime
    expires_at: datetime
    revoked_at: datetime | None = None
    revocation_reason: str | None = Field(default=None, max_length=500)
    device: str | None = Field(default=None, max_length=500)
    ip_hash: bytes | None = Field(default=None, min_length=32, max_length=32)
    user_agent_hash: bytes | None = Field(default=None, min_length=32, max_length=32)
    refresh_token_hash: bytes | None = Field(default=None, min_length=32, max_length=32)
    refresh_generation: int = Field(ge=0)


class AuditEvent(IdentitySchema):
    id: UUID
    occurred_at: datetime
    actor_user_id: UUID | None = None
    target_user_id: UUID | None = None
    session_id: UUID | None = None
    action: str = Field(pattern=AUDIT_ACTION_PATTERN)
    outcome: AuditOutcome
    reason_code: str | None = Field(default=None, pattern=REASON_CODE_PATTERN)
    request_id: str | None = Field(default=None, max_length=200)
    ip_hash: bytes | None = Field(default=None, min_length=32, max_length=32)
    user_agent_hash: bytes | None = Field(default=None, min_length=32, max_length=32)
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        validation_alias=AliasChoices("event_metadata", "metadata"),
    )


class CoexistenceRun(IdentitySchema):
    id: UUID
    run_type: str = Field(pattern=r"^(backfill|reconciliation|trigger)$")
    status: str = Field(pattern=r"^(running|succeeded|failed)$")
    started_at: datetime
    finished_at: datetime | None = None
    users_seen: int = Field(ge=0)
    users_changed: int = Field(ge=0)
    profiles_seen: int = Field(ge=0)
    profiles_changed: int = Field(ge=0)
    roles_changed: int = Field(ge=0)
    drift_count: int | None = Field(default=None, ge=0)
    error_code: str | None = None
    error_message: str | None = None
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        validation_alias=AliasChoices("run_metadata", "metadata"),
    )

    @model_validator(mode="after")
    def validate_run_state(self) -> "CoexistenceRun":
        if self.status == "running" and self.finished_at is not None:
            raise ValueError("running coexistence run cannot have finished_at")
        if self.status != "running" and self.finished_at is None:
            raise ValueError("completed coexistence run requires finished_at")
        if self.status == "failed" and self.error_code is None:
            raise ValueError("failed coexistence run requires error_code")
        if self.status != "failed" and (
            self.error_code is not None or self.error_message is not None
        ):
            raise ValueError("non-failed coexistence run cannot contain an error")
        return self
