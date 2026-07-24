from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class IdentityAuthSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")


class LoginRequest(IdentityAuthSchema):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=1024)
    device: str | None = Field(default=None, max_length=500)

    @field_validator("email")
    @classmethod
    def normalize_email_input(cls, value: str) -> str:
        normalized = value.strip().lower()
        if "@" not in normalized:
            raise ValueError("email must be valid")
        return normalized


class PasswordSetupRequest(IdentityAuthSchema):
    new_password: str = Field(min_length=1, max_length=1024)


class SessionExchangeRequest(IdentityAuthSchema):
    device: str | None = Field(default=None, max_length=500)


class PasswordChangeRequest(IdentityAuthSchema):
    current_password: str = Field(min_length=1, max_length=1024)
    new_password: str = Field(min_length=1, max_length=1024)

    @model_validator(mode="after")
    def passwords_must_differ(self) -> PasswordChangeRequest:
        if self.current_password == self.new_password:
            raise ValueError("new_password must differ from current_password")
        return self


class SessionResponse(IdentityAuthSchema):
    user_id: UUID
    session_id: UUID
    access_expires_at: datetime
    session_expires_at: datetime
    csrf_token: str


class IdentityMeResponse(IdentityAuthSchema):
    user_id: UUID
    email: str | None
    role: str
    source: str
    session_id: str | None = None
    auth_version: int | None = None
    authenticated_at: datetime


class IdentitySessionResponse(IdentityAuthSchema):
    session_id: UUID
    created_at: datetime
    last_seen_at: datetime
    expires_at: datetime
    revoked_at: datetime | None
    device_fingerprint: str | None
    is_current: bool


class PasswordSetupResponse(IdentityAuthSchema):
    user_id: UUID
    password_configured: bool = True


class LogoutResponse(IdentityAuthSchema):
    logged_out: bool = True
