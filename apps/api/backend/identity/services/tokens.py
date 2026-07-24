from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import jwt
from jwt import InvalidTokenError

from backend.identity.exceptions import InvalidIdentityTokenError, InvalidSessionError

JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_TYPE = "access"
REFRESH_TOKEN_BYTES = 32
REFRESH_TOKEN_PAYLOAD_BYTES = 16 + REFRESH_TOKEN_BYTES
CSRF_RANDOM_BYTES = 32
CSRF_SIGNATURE_BYTES = 32
CSRF_TOKEN_PAYLOAD_BYTES = 16 + CSRF_RANDOM_BYTES + CSRF_SIGNATURE_BYTES


@dataclass(frozen=True)
class AccessTokenClaims:
    user_id: UUID
    session_id: UUID
    auth_version: int
    issued_at: datetime
    expires_at: datetime
    token_id: UUID


class JwtService:
    def __init__(
        self,
        *,
        signing_key: str,
        key_id: str,
        issuer: str,
        audience: str,
        access_ttl: timedelta,
        verification_keys: Mapping[str, str] | None = None,
        clock_skew: timedelta = timedelta(seconds=30),
    ) -> None:
        if len(signing_key.encode("utf-8")) < 32:
            raise ValueError("JWT signing keys must contain at least 32 bytes")
        if not key_id.strip() or len(key_id) > 100:
            raise ValueError("JWT key_id must contain between 1 and 100 characters")
        if access_ttl <= timedelta(0):
            raise ValueError("JWT access_ttl must be positive")
        self._signing_key = signing_key
        self._key_id = key_id
        self._verification_keys = dict(verification_keys or {})
        existing_active_key = self._verification_keys.get(key_id)
        if existing_active_key is not None and existing_active_key != signing_key:
            raise ValueError("The active JWT key ID has conflicting key material")
        self._verification_keys[key_id] = signing_key
        if any(len(key.encode("utf-8")) < 32 for key in self._verification_keys.values()):
            raise ValueError("JWT verification keys must contain at least 32 bytes")
        self._issuer = issuer
        self._audience = audience
        self._access_ttl = access_ttl
        self._clock_skew = clock_skew

    def issue_access_token(
        self,
        *,
        user_id: UUID,
        session_id: UUID,
        auth_version: int,
        now: datetime | None = None,
    ) -> tuple[str, AccessTokenClaims]:
        issued_at = (now or datetime.now(UTC)).astimezone(UTC)
        expires_at = issued_at + self._access_ttl
        token_id = uuid4()
        payload: dict[str, Any] = {
            "iss": self._issuer,
            "aud": self._audience,
            "sub": str(user_id),
            "sid": str(session_id),
            "av": auth_version,
            "iat": issued_at,
            "exp": expires_at,
            "jti": str(token_id),
            "typ": ACCESS_TOKEN_TYPE,
            "user_id": str(user_id),
            "session_id": str(session_id),
            "auth_version": auth_version,
            "issued_at": int(issued_at.timestamp()),
            "expiry": int(expires_at.timestamp()),
        }
        token = jwt.encode(
            payload,
            self._signing_key,
            algorithm=JWT_ALGORITHM,
            headers={"kid": self._key_id, "typ": "JWT"},
        )
        return token, AccessTokenClaims(
            user_id=user_id,
            session_id=session_id,
            auth_version=auth_version,
            issued_at=issued_at,
            expires_at=expires_at,
            token_id=token_id,
        )

    def verify_access_token(self, token: str) -> AccessTokenClaims:
        try:
            header = jwt.get_unverified_header(token)
            key_id = header.get("kid")
            if header.get("alg") != JWT_ALGORITHM or header.get("typ") != "JWT":
                raise InvalidIdentityTokenError()
            if not isinstance(key_id, str) or key_id not in self._verification_keys:
                raise InvalidIdentityTokenError()
            payload = jwt.decode(
                token,
                self._verification_keys[key_id],
                algorithms=[JWT_ALGORITHM],
                audience=self._audience,
                issuer=self._issuer,
                leeway=self._clock_skew,
                options={
                    "require": [
                        "iss",
                        "aud",
                        "sub",
                        "sid",
                        "av",
                        "iat",
                        "exp",
                        "jti",
                        "typ",
                        "user_id",
                        "session_id",
                        "auth_version",
                        "issued_at",
                        "expiry",
                    ]
                },
            )
            if payload["typ"] != ACCESS_TOKEN_TYPE:
                raise InvalidIdentityTokenError()
            auth_version = payload["av"]
            issued_at = payload["iat"]
            expires_at = payload["exp"]
            if (
                isinstance(auth_version, bool)
                or not isinstance(auth_version, int)
                or auth_version <= 0
                or isinstance(issued_at, bool)
                or not isinstance(issued_at, int | float)
                or isinstance(expires_at, bool)
                or not isinstance(expires_at, int | float)
            ):
                raise InvalidIdentityTokenError()
            if (
                not isinstance(payload["user_id"], str)
                or not isinstance(payload["session_id"], str)
                or isinstance(payload["auth_version"], bool)
                or not isinstance(payload["auth_version"], int)
                or isinstance(payload["issued_at"], bool)
                or not isinstance(payload["issued_at"], int | float)
                or isinstance(payload["expiry"], bool)
                or not isinstance(payload["expiry"], int | float)
            ):
                raise InvalidIdentityTokenError()
            if (
                payload["sub"] != payload["user_id"]
                or payload["sid"] != payload["session_id"]
                or auth_version != payload["auth_version"]
                or issued_at != payload["issued_at"]
                or expires_at != payload["expiry"]
            ):
                raise InvalidIdentityTokenError()
            return AccessTokenClaims(
                user_id=UUID(payload["sub"]),
                session_id=UUID(payload["sid"]),
                auth_version=auth_version,
                issued_at=datetime.fromtimestamp(issued_at, tz=UTC),
                expires_at=datetime.fromtimestamp(expires_at, tz=UTC),
                token_id=UUID(payload["jti"]),
            )
        except InvalidIdentityTokenError:
            raise
        except (InvalidTokenError, KeyError, TypeError, ValueError) as exc:
            raise InvalidIdentityTokenError() from exc


class RefreshTokenService:
    def __init__(self, pepper: str) -> None:
        if len(pepper.encode("utf-8")) < 32:
            raise ValueError("Refresh-token peppers must contain at least 32 bytes")
        self._pepper = pepper.encode("utf-8")

    def issue(self, session_id: UUID) -> str:
        payload = session_id.bytes + secrets.token_bytes(REFRESH_TOKEN_BYTES)
        return base64.urlsafe_b64encode(payload).rstrip(b"=").decode("ascii")

    def session_id(self, token: str) -> UUID:
        try:
            encoded = token.encode("ascii")
            padding = b"=" * (-len(encoded) % 4)
            payload = base64.b64decode(encoded + padding, altchars=b"-_", validate=True)
        except (UnicodeEncodeError, ValueError) as exc:
            raise InvalidSessionError() from exc
        if len(payload) != REFRESH_TOKEN_PAYLOAD_BYTES:
            raise InvalidSessionError()
        return UUID(bytes=payload[:16])

    def digest(self, token: str) -> bytes:
        return hmac.new(
            self._pepper,
            b"refresh-token\x00" + token.encode("utf-8"),
            hashlib.sha256,
        ).digest()

    def matches(self, expected_digest: bytes | None, token: str) -> bool:
        candidate = self.digest(token)
        expected = expected_digest if expected_digest is not None else bytes(32)
        return hmac.compare_digest(expected, candidate)


class CsrfTokenService:
    def __init__(self, pepper: str) -> None:
        if len(pepper.encode("utf-8")) < 32:
            raise ValueError("CSRF-token peppers must contain at least 32 bytes")
        self._pepper = pepper.encode("utf-8")

    def issue(self, session_id: UUID) -> str:
        value = session_id.bytes + secrets.token_bytes(CSRF_RANDOM_BYTES)
        signature = hmac.new(
            self._pepper,
            b"csrf-token\x00" + value,
            hashlib.sha256,
        ).digest()
        return base64.urlsafe_b64encode(value + signature).rstrip(b"=").decode("ascii")

    def validate(self, token: str, session_id: UUID) -> bool:
        bound_session_id = self.bound_session_id(token)
        return bound_session_id is not None and hmac.compare_digest(
            bound_session_id.bytes,
            session_id.bytes,
        )

    def bound_session_id(self, token: str) -> UUID | None:
        try:
            encoded = token.encode("ascii")
            padding = b"=" * (-len(encoded) % 4)
            payload = base64.b64decode(encoded + padding, altchars=b"-_", validate=True)
        except (UnicodeEncodeError, ValueError):
            return False
        if len(payload) != CSRF_TOKEN_PAYLOAD_BYTES:
            return False
        value = payload[:-CSRF_SIGNATURE_BYTES]
        signature = payload[-CSRF_SIGNATURE_BYTES:]
        expected_signature = hmac.new(
            self._pepper,
            b"csrf-token\x00" + value,
            hashlib.sha256,
        ).digest()
        if not hmac.compare_digest(signature, expected_signature):
            return None
        return UUID(bytes=value[:16])


class SecurityMetadataHasher:
    def __init__(self, pepper: str) -> None:
        if len(pepper.encode("utf-8")) < 32:
            raise ValueError("Metadata peppers must contain at least 32 bytes")
        self._pepper = pepper.encode("utf-8")

    def hash_value(self, purpose: str, value: str) -> bytes:
        normalized = value.strip()
        return hmac.new(
            self._pepper,
            purpose.encode("ascii") + b"\x00" + normalized.encode("utf-8"),
            hashlib.sha256,
        ).digest()
