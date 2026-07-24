from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    MetaData,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy import (
    Enum as SqlEnum,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from backend.identity.enums import AuditOutcome, IdentityUserStatus

IDENTITY_SCHEMA = "identity"
JSON_DOCUMENT = JSON().with_variant(JSONB(), "postgresql")

USER_STATUS_ENUM = SqlEnum(
    IdentityUserStatus,
    name="identity_user_status_t",
    schema=IDENTITY_SCHEMA,
    values_callable=lambda enum: [member.value for member in enum],
    validate_strings=True,
)

AUDIT_OUTCOME_ENUM = SqlEnum(
    AuditOutcome,
    name="audit_outcome_t",
    schema=IDENTITY_SCHEMA,
    values_callable=lambda enum: [member.value for member in enum],
    validate_strings=True,
)


class IdentityBase(DeclarativeBase):
    metadata = MetaData(
        schema=IDENTITY_SCHEMA,
        naming_convention={
            "ix": "ix_%(table_name)s_%(column_0_name)s",
            "uq": "uq_%(table_name)s_%(column_0_name)s",
            "ck": "ck_%(table_name)s_%(constraint_name)s",
            "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
            "pk": "pk_%(table_name)s",
        },
    )


class IdentityUserModel(IdentityBase):
    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("email_normalized", name="identity_users_email_normalized_key"),
        CheckConstraint(
            "length(trim(email)) > 0",
            name="identity_users_email_not_blank",
        ),
        CheckConstraint(
            "length(email_normalized) > 0",
            name="identity_users_email_normalized_not_blank",
        ),
        CheckConstraint("auth_version > 0", name="identity_users_auth_version"),
        CheckConstraint(
            "failed_login_count >= 0",
            name="identity_users_failed_login_count",
        ),
        Index("identity_users_status_idx", "status"),
        Index("identity_users_created_at_idx", text("created_at DESC")),
        Index(
            "identity_users_locked_until_idx",
            "locked_until",
            postgresql_where=text("locked_until IS NOT NULL"),
            sqlite_where=text("locked_until IS NOT NULL"),
        ),
        Index(
            "identity_users_deleted_at_idx",
            "deleted_at",
            postgresql_where=text("deleted_at IS NOT NULL"),
            sqlite_where=text("deleted_at IS NOT NULL"),
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    email: Mapped[str] = mapped_column(Text, nullable=False)
    email_normalized: Mapped[str] = mapped_column(Text, nullable=False)
    password_hash: Mapped[str | None] = mapped_column(Text)
    status: Mapped[IdentityUserStatus] = mapped_column(
        USER_STATUS_ENUM,
        nullable=False,
        default=IdentityUserStatus.PENDING_VERIFICATION,
        server_default=IdentityUserStatus.PENDING_VERIFICATION.value,
    )
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    auth_version: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        default=1,
        server_default=text("1"),
    )
    failed_login_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    password_changed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    profile: Mapped[IdentityProfileModel | None] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        uselist=False,
    )
    role_assignments: Mapped[list[UserRoleAssignmentModel]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        foreign_keys="UserRoleAssignmentModel.user_id",
    )
    sessions: Mapped[list[AuthSessionModel]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )


class IdentityProfileModel(IdentityBase):
    __tablename__ = "user_profiles"
    __table_args__ = (
        CheckConstraint(
            "display_name IS NULL OR length(display_name) <= 200",
            name="identity_user_profiles_display_name",
        ),
        CheckConstraint(
            "organization IS NULL OR length(organization) <= 255",
            name="identity_user_profiles_organization",
        ),
        CheckConstraint(
            "avatar_url IS NULL OR length(avatar_url) <= 2048",
            name="identity_user_profiles_avatar_url",
        ),
        CheckConstraint(
            "bio IS NULL OR length(bio) <= 2000",
            name="identity_user_profiles_bio",
        ),
    )

    user_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("identity.users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    display_name: Mapped[str | None] = mapped_column(Text)
    organization: Mapped[str | None] = mapped_column(Text)
    avatar_url: Mapped[str | None] = mapped_column(Text)
    preferences: Mapped[dict[str, Any]] = mapped_column(
        JSON_DOCUMENT,
        nullable=False,
        default=dict,
        server_default=text("'{}'"),
    )
    bio: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    user: Mapped[IdentityUserModel] = relationship(back_populates="profile")


class RoleModel(IdentityBase):
    __tablename__ = "roles"
    __table_args__ = (
        UniqueConstraint("code", name="identity_roles_code_key"),
        CheckConstraint(
            "length(trim(name)) BETWEEN 1 AND 100",
            name="identity_roles_name",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    is_system: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=text("true"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    permissions: Mapped[list[RolePermissionModel]] = relationship(
        back_populates="role",
        cascade="all, delete-orphan",
    )
    assignments: Mapped[list[UserRoleAssignmentModel]] = relationship(
        back_populates="role",
    )


class PermissionModel(IdentityBase):
    __tablename__ = "permissions"
    __table_args__ = (UniqueConstraint("code", name="identity_permissions_code_key"),)

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    code: Mapped[str] = mapped_column(String(129), nullable=False)
    resource: Mapped[str] = mapped_column(String(64), nullable=False)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    roles: Mapped[list[RolePermissionModel]] = relationship(
        back_populates="permission",
        cascade="all, delete-orphan",
    )


class RolePermissionModel(IdentityBase):
    __tablename__ = "role_permissions"
    __table_args__ = (
        Index(
            "identity_role_permissions_permission_idx",
            "permission_id",
            "role_id",
        ),
    )

    role_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("identity.roles.id", ondelete="CASCADE"),
        primary_key=True,
    )
    permission_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("identity.permissions.id", ondelete="CASCADE"),
        primary_key=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    role: Mapped[RoleModel] = relationship(back_populates="permissions")
    permission: Mapped[PermissionModel] = relationship(back_populates="roles")


class UserRoleAssignmentModel(IdentityBase):
    __tablename__ = "user_role_assignments"
    __table_args__ = (
        CheckConstraint(
            "revoked_at IS NULL OR revoked_at >= granted_at",
            name="identity_user_role_assignments_revoked_at",
        ),
        CheckConstraint(
            "reason IS NULL OR length(reason) <= 500",
            name="identity_user_role_assignments_reason",
        ),
        Index(
            "identity_user_role_assignments_active_user_idx",
            "user_id",
            unique=True,
            postgresql_where=text("revoked_at IS NULL"),
            sqlite_where=text("revoked_at IS NULL"),
        ),
        Index(
            "identity_user_role_assignments_role_idx",
            "role_id",
            postgresql_where=text("revoked_at IS NULL"),
            sqlite_where=text("revoked_at IS NULL"),
        ),
        Index(
            "identity_user_role_assignments_history_idx",
            "user_id",
            text("granted_at DESC"),
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("identity.users.id", ondelete="CASCADE"),
        nullable=False,
    )
    role_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("identity.roles.id", ondelete="RESTRICT"),
        nullable=False,
    )
    granted_by: Mapped[UUID | None] = mapped_column(
        Uuid,
        ForeignKey("identity.users.id", ondelete="SET NULL"),
    )
    granted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reason: Mapped[str | None] = mapped_column(Text)

    user: Mapped[IdentityUserModel] = relationship(
        back_populates="role_assignments",
        foreign_keys=[user_id],
    )
    role: Mapped[RoleModel] = relationship(back_populates="assignments")
    grantor: Mapped[IdentityUserModel | None] = relationship(foreign_keys=[granted_by])


class PasswordResetTokenModel(IdentityBase):
    __tablename__ = "password_reset_tokens"
    __table_args__ = (
        UniqueConstraint("token_hash", name="identity_password_reset_tokens_hash_key"),
        CheckConstraint(
            "expires_at > created_at",
            name="identity_password_reset_tokens_expiry",
        ),
        Index(
            "identity_password_reset_tokens_active_user_idx",
            "user_id",
            "expires_at",
            postgresql_where=text("consumed_at IS NULL AND invalidated_at IS NULL"),
            sqlite_where=text("consumed_at IS NULL AND invalidated_at IS NULL"),
        ),
        Index("identity_password_reset_tokens_expires_at_idx", "expires_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("identity.users.id", ondelete="CASCADE"),
        nullable=False,
    )
    token_hash: Mapped[bytes] = mapped_column(LargeBinary(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    invalidated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class EmailVerificationTokenModel(IdentityBase):
    __tablename__ = "email_verification_tokens"
    __table_args__ = (
        UniqueConstraint(
            "token_hash",
            name="identity_email_verification_tokens_hash_key",
        ),
        CheckConstraint(
            "expires_at > created_at",
            name="identity_email_verification_tokens_expiry",
        ),
        Index(
            "identity_email_verification_tokens_active_user_idx",
            "user_id",
            "expires_at",
            postgresql_where=text("consumed_at IS NULL AND invalidated_at IS NULL"),
            sqlite_where=text("consumed_at IS NULL AND invalidated_at IS NULL"),
        ),
        Index("identity_email_verification_tokens_expires_at_idx", "expires_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("identity.users.id", ondelete="CASCADE"),
        nullable=False,
    )
    email_normalized: Mapped[str] = mapped_column(Text, nullable=False)
    token_hash: Mapped[bytes] = mapped_column(LargeBinary(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    invalidated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AuthSessionModel(IdentityBase):
    __tablename__ = "auth_sessions"
    __table_args__ = (
        CheckConstraint("auth_version > 0", name="identity_auth_sessions_auth_version"),
        CheckConstraint(
            "expires_at > created_at",
            name="identity_auth_sessions_expiry",
        ),
        CheckConstraint(
            "revoked_at IS NULL OR revoked_at >= created_at",
            name="identity_auth_sessions_revoked_at",
        ),
        CheckConstraint(
            "refresh_token_hash IS NULL OR length(refresh_token_hash) = 32",
            name="identity_auth_sessions_refresh_token_hash_length",
        ),
        CheckConstraint(
            "refresh_generation >= 0",
            name="identity_auth_sessions_refresh_generation",
        ),
        Index(
            "identity_auth_sessions_active_user_idx",
            "user_id",
            "expires_at",
            postgresql_where=text("revoked_at IS NULL"),
            sqlite_where=text("revoked_at IS NULL"),
        ),
        Index("identity_auth_sessions_expires_at_idx", "expires_at"),
        Index(
            "identity_auth_sessions_revoked_at_idx",
            "revoked_at",
            postgresql_where=text("revoked_at IS NOT NULL"),
            sqlite_where=text("revoked_at IS NOT NULL"),
        ),
        Index(
            "identity_auth_sessions_refresh_token_hash_idx",
            "refresh_token_hash",
            unique=True,
            postgresql_where=text("refresh_token_hash IS NOT NULL"),
            sqlite_where=text("refresh_token_hash IS NOT NULL"),
        ),
    )

    sid: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("identity.users.id", ondelete="CASCADE"),
        nullable=False,
    )
    auth_version: Mapped[int] = mapped_column(BigInteger, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revocation_reason: Mapped[str | None] = mapped_column(Text)
    device: Mapped[str | None] = mapped_column(String(500))
    ip_hash: Mapped[bytes | None] = mapped_column(LargeBinary(32))
    user_agent_hash: Mapped[bytes | None] = mapped_column(LargeBinary(32))
    refresh_token_hash: Mapped[bytes | None] = mapped_column(LargeBinary(32))
    refresh_generation: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        default=0,
        server_default=text("0"),
    )

    user: Mapped[IdentityUserModel] = relationship(back_populates="sessions")


class AuthenticationRateLimitModel(IdentityBase):
    __tablename__ = "authentication_rate_limits"
    __table_args__ = (
        CheckConstraint(
            "length(scope) BETWEEN 3 AND 100",
            name="identity_authentication_rate_limits_scope",
        ),
        CheckConstraint(
            "length(subject_hash) = 32",
            name="identity_authentication_rate_limits_subject_hash_length",
        ),
        CheckConstraint(
            "attempts >= 0",
            name="identity_authentication_rate_limits_attempts",
        ),
        CheckConstraint(
            "blocked_until IS NULL OR blocked_until >= window_started_at",
            name="identity_authentication_rate_limits_blocked_until",
        ),
        Index(
            "identity_authentication_rate_limits_blocked_until_idx",
            "blocked_until",
            postgresql_where=text("blocked_until IS NOT NULL"),
            sqlite_where=text("blocked_until IS NOT NULL"),
        ),
        Index(
            "identity_authentication_rate_limits_updated_at_idx",
            "updated_at",
        ),
    )

    scope: Mapped[str] = mapped_column(String(100), primary_key=True)
    subject_hash: Mapped[bytes] = mapped_column(LargeBinary(32), primary_key=True)
    window_started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    attempts: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    blocked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class SessionExchangeModel(IdentityBase):
    __tablename__ = "session_exchanges"
    __table_args__ = (
        CheckConstraint(
            "source = 'supabase'",
            name="identity_session_exchanges_source",
        ),
        CheckConstraint(
            "length(source_session_hash) = 32",
            name="identity_session_exchanges_source_session_hash_length",
        ),
        UniqueConstraint(
            "source_session_hash",
            name="identity_session_exchanges_source_session_hash_key",
        ),
        CheckConstraint(
            "source_expires_at IS NULL "
            "OR source_expires_at > source_authenticated_at",
            name="identity_session_exchanges_source_expiry",
        ),
        Index(
            "identity_session_exchanges_user_idx",
            "user_id",
            text("exchanged_at DESC"),
        ),
        Index(
            "identity_session_exchanges_identity_session_idx",
            "identity_session_id",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    source: Mapped[str] = mapped_column(String(20), nullable=False, default="supabase")
    source_session_hash: Mapped[bytes] = mapped_column(LargeBinary(32), nullable=False)
    user_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("identity.users.id", ondelete="CASCADE"),
        nullable=False,
    )
    identity_session_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("identity.auth_sessions.sid", ondelete="CASCADE"),
        nullable=False,
    )
    source_authenticated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    source_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    exchanged_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    request_id: Mapped[str | None] = mapped_column(String(200))
    ip_hash: Mapped[bytes | None] = mapped_column(LargeBinary(32))
    user_agent_hash: Mapped[bytes | None] = mapped_column(LargeBinary(32))


class AuthenticationMetricModel(IdentityBase):
    __tablename__ = "authentication_metrics_hourly"
    __table_args__ = (
        CheckConstraint(
            "source IN ('supabase', 'identity', 'unknown')",
            name="identity_authentication_metrics_source",
        ),
        CheckConstraint(
            "outcome IN ('success', 'failure', 'denied')",
            name="identity_authentication_metrics_outcome",
        ),
        CheckConstraint(
            "observation_count > 0",
            name="identity_authentication_metrics_count",
        ),
        Index(
            "identity_authentication_metrics_updated_at_idx",
            "updated_at",
        ),
    )

    bucket_started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        primary_key=True,
    )
    source: Mapped[str] = mapped_column(String(20), primary_key=True)
    outcome: Mapped[str] = mapped_column(String(20), primary_key=True)
    reason_code: Mapped[str] = mapped_column(
        String(100),
        primary_key=True,
        default="",
        server_default=text("''"),
    )
    observation_count: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        default=1,
        server_default=text("1"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class AuditEventModel(IdentityBase):
    __tablename__ = "audit_events"
    __table_args__ = (
        CheckConstraint(
            "length(action) BETWEEN 3 AND 100",
            name="identity_audit_events_action",
        ),
        Index("identity_audit_events_occurred_at_idx", text("occurred_at DESC")),
        Index(
            "identity_audit_events_actor_idx",
            "actor_user_id",
            text("occurred_at DESC"),
            postgresql_where=text("actor_user_id IS NOT NULL"),
            sqlite_where=text("actor_user_id IS NOT NULL"),
        ),
        Index(
            "identity_audit_events_target_idx",
            "target_user_id",
            text("occurred_at DESC"),
            postgresql_where=text("target_user_id IS NOT NULL"),
            sqlite_where=text("target_user_id IS NOT NULL"),
        ),
        Index(
            "identity_audit_events_action_idx",
            "action",
            text("occurred_at DESC"),
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    actor_user_id: Mapped[UUID | None] = mapped_column(
        Uuid,
        ForeignKey("identity.users.id", ondelete="SET NULL"),
    )
    target_user_id: Mapped[UUID | None] = mapped_column(
        Uuid,
        ForeignKey("identity.users.id", ondelete="SET NULL"),
    )
    session_id: Mapped[UUID | None] = mapped_column(
        Uuid,
        ForeignKey("identity.auth_sessions.sid", ondelete="SET NULL"),
    )
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    outcome: Mapped[AuditOutcome] = mapped_column(AUDIT_OUTCOME_ENUM, nullable=False)
    reason_code: Mapped[str | None] = mapped_column(String(100))
    request_id: Mapped[str | None] = mapped_column(String(200))
    ip_hash: Mapped[bytes | None] = mapped_column(LargeBinary(32))
    user_agent_hash: Mapped[bytes | None] = mapped_column(LargeBinary(32))
    event_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        JSON_DOCUMENT,
        nullable=False,
        default=dict,
        server_default=text("'{}'"),
    )


class CoexistenceRunModel(IdentityBase):
    __tablename__ = "coexistence_runs"
    __table_args__ = (
        CheckConstraint(
            "run_type IN ('backfill', 'reconciliation', 'trigger')",
            name="identity_coexistence_runs_type",
        ),
        CheckConstraint(
            "status IN ('running', 'succeeded', 'failed')",
            name="identity_coexistence_runs_status",
        ),
        CheckConstraint(
            "users_seen >= 0 AND users_changed >= 0 "
            "AND profiles_seen >= 0 AND profiles_changed >= 0 "
            "AND roles_changed >= 0 "
            "AND (drift_count IS NULL OR drift_count >= 0)",
            name="identity_coexistence_runs_counts",
        ),
        CheckConstraint(
            "(status = 'running' AND finished_at IS NULL) "
            "OR (status <> 'running' AND finished_at IS NOT NULL)",
            name="identity_coexistence_runs_finished_at",
        ),
        CheckConstraint(
            "(status = 'failed' AND error_code IS NOT NULL) "
            "OR (status <> 'failed' AND error_code IS NULL AND error_message IS NULL)",
            name="identity_coexistence_runs_error",
        ),
        Index("identity_coexistence_runs_started_at_idx", text("started_at DESC")),
        Index(
            "identity_coexistence_runs_type_status_idx",
            "run_type",
            "status",
            text("started_at DESC"),
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    run_type: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    users_seen: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    users_changed: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    profiles_seen: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    profiles_changed: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    roles_changed: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    drift_count: Mapped[int | None] = mapped_column(Integer)
    error_code: Mapped[str | None] = mapped_column(Text)
    error_message: Mapped[str | None] = mapped_column(Text)
    run_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        JSON_DOCUMENT,
        nullable=False,
        default=dict,
        server_default=text("'{}'"),
    )
