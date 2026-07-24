from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from backend.identity.enums import AuditOutcome, IdentityUserStatus
from backend.identity.exceptions import (
    CsrfValidationError,
    InvalidCredentialsError,
    InvalidIdentityTokenError,
    InvalidSessionError,
    PasswordAlreadyConfiguredError,
    PasswordPolicyError,
    RateLimitExceededError,
    ReconciliationDriftError,
    SessionExchangeReplayError,
    SessionNotFoundError,
)
from backend.identity.models import (
    AuditEventModel,
    AuthSessionModel,
    IdentityUserModel,
    SessionExchangeModel,
)
from backend.identity.repositories.audit import AuditRepository
from backend.identity.repositories.reconciliation import IdentityReconciliationRepository
from backend.identity.repositories.role_assignments import RoleAssignmentsRepository
from backend.identity.repositories.session_exchanges import SessionExchangesRepository
from backend.identity.repositories.users import UsersRepository
from backend.identity.services.password import PasswordService
from backend.identity.services.rate_limit import AuthenticationRateLimitService
from backend.identity.services.session import SessionService
from backend.identity.services.tokens import (
    AccessTokenClaims,
    CsrfTokenService,
    JwtService,
    RefreshTokenService,
    SecurityMetadataHasher,
)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


@dataclass(frozen=True)
class RequestSecurityContext:
    ip_hash: bytes
    user_agent_hash: bytes
    ip_rate_limit_hash: bytes
    request_id: str | None = None


@dataclass(frozen=True)
class FirstPartyPrincipal:
    user_id: UUID
    session_id: UUID
    auth_version: int
    email: str
    role: str
    authenticated_at: datetime


@dataclass(frozen=True)
class FirstPartySession:
    session_id: UUID
    created_at: datetime
    last_seen_at: datetime
    expires_at: datetime
    revoked_at: datetime | None
    device: str | None
    is_current: bool


@dataclass(frozen=True)
class IssuedIdentitySession:
    user_id: UUID
    session_id: UUID
    access_token: str
    refresh_token: str
    csrf_token: str
    access_expires_at: datetime
    session_expires_at: datetime


class AuthenticationService:
    def __init__(
        self,
        *,
        users: UsersRepository,
        sessions: SessionService,
        audit: AuditRepository,
        passwords: PasswordService,
        jwt_tokens: JwtService,
        refresh_tokens: RefreshTokenService,
        csrf_tokens: CsrfTokenService,
        metadata_hasher: SecurityMetadataHasher,
        rate_limits: AuthenticationRateLimitService,
        reconciliation: IdentityReconciliationRepository,
        role_assignments: RoleAssignmentsRepository,
        exchanges: SessionExchangesRepository,
        session_ttl: timedelta,
        password_min_length: int,
        password_max_length: int,
        failed_login_limit: int,
        account_lock_duration: timedelta,
        login_account_rate_limit: int,
        login_ip_rate_limit: int,
        login_rate_window: timedelta,
        refresh_rate_limit: int,
        refresh_rate_window: timedelta,
        password_rate_limit: int,
        password_rate_window: timedelta,
        exchange_rate_limit: int,
        exchange_rate_window: timedelta,
    ) -> None:
        if password_min_length > password_max_length:
            raise ValueError("Password minimum length cannot exceed maximum length")
        self._users = users
        self._sessions = sessions
        self._audit = audit
        self._passwords = passwords
        self._jwt_tokens = jwt_tokens
        self._refresh_tokens = refresh_tokens
        self._csrf_tokens = csrf_tokens
        self._metadata_hasher = metadata_hasher
        self._rate_limits = rate_limits
        self._reconciliation = reconciliation
        self._role_assignments = role_assignments
        self._exchanges = exchanges
        self._session_ttl = session_ttl
        self._password_min_length = password_min_length
        self._password_max_length = password_max_length
        self._failed_login_limit = failed_login_limit
        self._account_lock_duration = account_lock_duration
        self._login_account_rate_limit = login_account_rate_limit
        self._login_ip_rate_limit = login_ip_rate_limit
        self._login_rate_window = login_rate_window
        self._refresh_rate_limit = refresh_rate_limit
        self._refresh_rate_window = refresh_rate_window
        self._password_rate_limit = password_rate_limit
        self._password_rate_window = password_rate_window
        self._exchange_rate_limit = exchange_rate_limit
        self._exchange_rate_window = exchange_rate_window

    def login(
        self,
        *,
        email: str,
        password: str,
        device: str | None,
        context: RequestSecurityContext,
        now: datetime | None = None,
    ) -> IssuedIdentitySession:
        observed_at = _as_utc(now or datetime.now(UTC))
        email_normalized = email.strip().lower()
        account_rate_hash = self._metadata_hasher.hash_value(
            "rate-limit-login-account",
            email_normalized,
        )
        try:
            self._rate_limits.consume(
                scope="login.account",
                subject_hash=account_rate_hash,
                limit=self._login_account_rate_limit,
                window=self._login_rate_window,
                now=observed_at,
            )
            self._rate_limits.consume(
                scope="login.ip",
                subject_hash=context.ip_rate_limit_hash,
                limit=self._login_ip_rate_limit,
                window=self._login_rate_window,
                now=observed_at,
            )
        except RateLimitExceededError:
            self._append_audit(
                action="authentication.login",
                outcome=AuditOutcome.DENIED,
                reason_code="RATE_LIMITED",
                context=context,
            )
            raise

        user = self._users.get_by_normalized_email_for_update(email_normalized)
        password_matches = self._passwords.verify_password_or_dummy(
            user.password_hash if user is not None else None,
            password,
        )
        if (
            user is not None
            and user.locked_until is not None
            and _as_utc(user.locked_until) <= observed_at
        ):
            user.failed_login_count = 0
            user.locked_until = None
        reason_code = self._login_rejection_reason(user, password_matches, observed_at)
        if reason_code is not None:
            if (
                user is not None
                and user.password_hash is not None
                and user.status == IdentityUserStatus.ACTIVE
                and not self._is_locked(user, observed_at)
                and not password_matches
            ):
                account_locked = self._record_failed_login(user, observed_at)
                if account_locked:
                    self._append_audit(
                        action="authentication.account_locked",
                        outcome=AuditOutcome.DENIED,
                        reason_code="FAILED_LOGIN_LIMIT_REACHED",
                        context=context,
                        target_user_id=user.id,
                    )
            self._append_audit(
                action="authentication.login",
                outcome=AuditOutcome.FAILURE,
                reason_code=reason_code,
                context=context,
                target_user_id=user.id if user is not None else None,
            )
            raise InvalidCredentialsError(reason_code)

        assert user is not None
        assert user.password_hash is not None
        if self._reconciliation.has_drift(user.id):
            self._append_audit(
                action="authentication.login",
                outcome=AuditOutcome.DENIED,
                reason_code="RECONCILIATION_DRIFT",
                context=context,
                target_user_id=user.id,
            )
            raise InvalidCredentialsError("RECONCILIATION_DRIFT")
        if self._passwords.needs_rehash(user.password_hash):
            user.password_hash = self._passwords.hash_password(password)
        user.failed_login_count = 0
        user.locked_until = None
        user.last_login_at = observed_at

        issued = self._create_session(
            user=user,
            device=device,
            context=context,
            observed_at=observed_at,
        )
        self._append_audit(
            action="authentication.login",
            outcome=AuditOutcome.SUCCESS,
            context=context,
            actor_user_id=user.id,
            target_user_id=user.id,
            session_id=issued.session_id,
        )
        return issued

    def authenticate_access_token(
        self,
        token: str,
        *,
        now: datetime | None = None,
    ) -> FirstPartyPrincipal:
        observed_at = _as_utc(now or datetime.now(UTC))
        claims = self._jwt_tokens.verify_access_token(token)
        auth_session = self._sessions.get(claims.session_id)
        user = self._users.get(claims.user_id)
        self._validate_access_state(
            claims=claims,
            auth_session=auth_session,
            user=user,
            observed_at=observed_at,
        )
        assert user is not None
        return FirstPartyPrincipal(
            user_id=user.id,
            session_id=claims.session_id,
            auth_version=user.auth_version,
            email=user.email,
            role=claims.role,
            authenticated_at=claims.issued_at,
        )

    def exchange_supabase_session(
        self,
        *,
        user_id: UUID,
        source_session_hash: bytes,
        source_authenticated_at: datetime,
        source_expires_at: datetime | None,
        device: str | None,
        context: RequestSecurityContext,
        now: datetime | None = None,
    ) -> IssuedIdentitySession:
        observed_at = _as_utc(now or datetime.now(UTC))
        authenticated_at = _as_utc(source_authenticated_at)
        expires_at = _as_utc(source_expires_at) if source_expires_at is not None else None
        if expires_at is not None and (
            expires_at <= observed_at or expires_at <= authenticated_at
        ):
            self._append_audit(
                action="authentication.exchange",
                outcome=AuditOutcome.FAILURE,
                reason_code="SOURCE_SESSION_EXPIRED",
                context=context,
                target_user_id=user_id,
            )
            raise InvalidCredentialsError("SOURCE_SESSION_EXPIRED")
        try:
            self._rate_limits.consume(
                scope="session.exchange",
                subject_hash=source_session_hash,
                limit=self._exchange_rate_limit,
                window=self._exchange_rate_window,
                now=observed_at,
            )
        except RateLimitExceededError:
            self._append_audit(
                action="authentication.exchange",
                outcome=AuditOutcome.DENIED,
                reason_code="RATE_LIMITED",
                context=context,
                target_user_id=user_id,
            )
            raise

        self._exchanges.lock_source_session(source_session_hash)
        if self._exchanges.get_by_source_session_hash(source_session_hash) is not None:
            self._append_audit(
                action="authentication.exchange",
                outcome=AuditOutcome.DENIED,
                reason_code="SESSION_EXCHANGE_REPLAY",
                context=context,
                target_user_id=user_id,
            )
            raise SessionExchangeReplayError()
        if self._reconciliation.has_drift(user_id):
            self._append_audit(
                action="authentication.exchange",
                outcome=AuditOutcome.DENIED,
                reason_code="RECONCILIATION_DRIFT",
                context=context,
                target_user_id=user_id,
            )
            raise ReconciliationDriftError()

        user = self._users.get_for_update(user_id)
        if (
            user is None
            or user.status != IdentityUserStatus.ACTIVE
            or user.deleted_at is not None
        ):
            self._append_audit(
                action="authentication.exchange",
                outcome=AuditOutcome.DENIED,
                reason_code="ACCOUNT_UNAVAILABLE",
                context=context,
                target_user_id=user_id if user is not None else None,
            )
            raise InvalidCredentialsError("ACCOUNT_UNAVAILABLE")

        issued = self._create_session(
            user=user,
            device=device,
            context=context,
            observed_at=observed_at,
        )
        self._exchanges.add(
            SessionExchangeModel(
                source="supabase",
                source_session_hash=source_session_hash,
                user_id=user.id,
                identity_session_id=issued.session_id,
                source_authenticated_at=authenticated_at,
                source_expires_at=expires_at,
                exchanged_at=observed_at,
                request_id=context.request_id,
                ip_hash=context.ip_hash,
                user_agent_hash=context.user_agent_hash,
            )
        )
        self._append_audit(
            action="authentication.exchange",
            outcome=AuditOutcome.SUCCESS,
            context=context,
            actor_user_id=user.id,
            target_user_id=user.id,
            session_id=issued.session_id,
            metadata={"source": "supabase"},
        )
        return issued

    def refresh(
        self,
        *,
        refresh_token: str,
        expected_session_id: UUID,
        context: RequestSecurityContext,
        now: datetime | None = None,
    ) -> IssuedIdentitySession:
        observed_at = _as_utc(now or datetime.now(UTC))
        try:
            self._rate_limits.consume(
                scope="session.refresh",
                subject_hash=context.ip_rate_limit_hash,
                limit=self._refresh_rate_limit,
                window=self._refresh_rate_window,
                now=observed_at,
            )
            session_id = self._refresh_tokens.session_id(refresh_token)
        except RateLimitExceededError:
            self._append_audit(
                action="authentication.refresh",
                outcome=AuditOutcome.DENIED,
                reason_code="RATE_LIMITED",
                context=context,
            )
            raise
        except InvalidSessionError:
            self._append_audit(
                action="authentication.refresh",
                outcome=AuditOutcome.FAILURE,
                reason_code="INVALID_REFRESH_TOKEN",
                context=context,
            )
            raise
        if session_id != expected_session_id:
            self._append_audit(
                action="authentication.refresh",
                outcome=AuditOutcome.DENIED,
                reason_code="CSRF_VALIDATION_FAILED",
                context=context,
            )
            raise CsrfValidationError()

        observed_session = self._sessions.get(session_id)
        if observed_session is None:
            self._refresh_tokens.matches(None, refresh_token)
            self._append_audit(
                action="authentication.refresh",
                outcome=AuditOutcome.FAILURE,
                reason_code="INVALID_SESSION",
                context=context,
            )
            raise InvalidSessionError()

        user = self._users.get_for_update(observed_session.user_id)
        auth_session = self._sessions.get_for_update(session_id)
        if auth_session is None or not self._refresh_tokens.matches(
            auth_session.refresh_token_hash if auth_session is not None else None,
            refresh_token,
        ):
            session_was_revoked = True
            if auth_session is not None and auth_session.revoked_at is None:
                self._revoke_session(
                    auth_session,
                    observed_at,
                    "Refresh token replay or mismatch",
                )
                session_was_revoked = False
            self._append_audit(
                action="authentication.refresh",
                outcome=AuditOutcome.DENIED,
                reason_code="REFRESH_REPLAY_DETECTED",
                context=context,
                target_user_id=observed_session.user_id,
                session_id=session_id,
            )
            self._append_audit(
                action="authentication.token_replay",
                outcome=AuditOutcome.DENIED,
                reason_code="REFRESH_REPLAY_DETECTED",
                context=context,
                target_user_id=observed_session.user_id,
                session_id=session_id,
            )
            if not session_was_revoked:
                self._append_audit(
                    action="authentication.session_revoked",
                    outcome=AuditOutcome.DENIED,
                    reason_code="REFRESH_REPLAY_DETECTED",
                    context=context,
                    target_user_id=observed_session.user_id,
                    session_id=session_id,
                    metadata={"reason": "Refresh token replay or mismatch"},
                )
            raise InvalidSessionError("REFRESH_REPLAY_DETECTED")

        rejection_reason = self._session_rejection_reason(
            auth_session,
            user,
            observed_at,
        )
        if rejection_reason is not None:
            if auth_session.revoked_at is None:
                self._revoke_session(auth_session, observed_at, rejection_reason)
            self._append_audit(
                action="authentication.refresh",
                outcome=AuditOutcome.DENIED,
                reason_code=rejection_reason,
                context=context,
                target_user_id=auth_session.user_id,
                session_id=session_id,
            )
            raise InvalidSessionError(rejection_reason)

        assert user is not None
        rotated_refresh_token = self._refresh_tokens.issue(session_id)
        auth_session.refresh_token_hash = self._refresh_tokens.digest(rotated_refresh_token)
        auth_session.refresh_generation += 1
        auth_session.last_seen_at = observed_at
        access_token, claims = self._jwt_tokens.issue_access_token(
            user_id=user.id,
            session_id=session_id,
            auth_version=user.auth_version,
            role=self._role_for_user(user.id),
            now=observed_at,
        )
        self._append_audit(
            action="authentication.refresh",
            outcome=AuditOutcome.SUCCESS,
            context=context,
            actor_user_id=user.id,
            target_user_id=user.id,
            session_id=session_id,
            metadata={"refresh_generation": auth_session.refresh_generation},
        )
        return IssuedIdentitySession(
            user_id=user.id,
            session_id=session_id,
            access_token=access_token,
            refresh_token=rotated_refresh_token,
            csrf_token=self._csrf_tokens.issue(session_id),
            access_expires_at=claims.expires_at,
            session_expires_at=_as_utc(auth_session.expires_at),
        )

    def logout(
        self,
        *,
        refresh_token: str | None,
        expected_session_id: UUID | None,
        context: RequestSecurityContext,
        now: datetime | None = None,
    ) -> None:
        if not refresh_token:
            return
        observed_at = _as_utc(now or datetime.now(UTC))
        try:
            session_id = self._refresh_tokens.session_id(refresh_token)
        except InvalidSessionError:
            self._append_audit(
                action="authentication.logout",
                outcome=AuditOutcome.FAILURE,
                reason_code="INVALID_REFRESH_TOKEN",
                context=context,
            )
            return
        if expected_session_id is None or session_id != expected_session_id:
            self._append_audit(
                action="authentication.logout",
                outcome=AuditOutcome.DENIED,
                reason_code="CSRF_VALIDATION_FAILED",
                context=context,
            )
            return
        auth_session = self._sessions.get_for_update(session_id)
        if auth_session is None:
            self._refresh_tokens.matches(None, refresh_token)
            return
        token_matches = self._refresh_tokens.matches(
            auth_session.refresh_token_hash,
            refresh_token,
        )
        was_revoked = auth_session.revoked_at is not None
        if auth_session.revoked_at is None:
            self._revoke_session(
                auth_session,
                observed_at,
                "User logout" if token_matches else "Refresh token mismatch during logout",
            )
        self._append_audit(
            action="authentication.logout",
            outcome=AuditOutcome.SUCCESS if token_matches else AuditOutcome.DENIED,
            reason_code=None if token_matches else "REFRESH_REPLAY_DETECTED",
            context=context,
            actor_user_id=auth_session.user_id if token_matches else None,
            target_user_id=auth_session.user_id,
            session_id=session_id,
        )
        if not was_revoked:
            self._append_audit(
                action="authentication.session_revoked",
                outcome=(
                    AuditOutcome.SUCCESS if token_matches else AuditOutcome.DENIED
                ),
                reason_code=None if token_matches else "REFRESH_REPLAY_DETECTED",
                context=context,
                actor_user_id=auth_session.user_id if token_matches else None,
                target_user_id=auth_session.user_id,
                session_id=session_id,
                metadata={"reason": auth_session.revocation_reason or "unknown"},
            )
        if not token_matches:
            self._append_audit(
                action="authentication.token_replay",
                outcome=AuditOutcome.DENIED,
                reason_code="REFRESH_REPLAY_DETECTED",
                context=context,
                target_user_id=auth_session.user_id,
                session_id=session_id,
            )

    def list_sessions(
        self,
        *,
        principal: FirstPartyPrincipal,
        now: datetime | None = None,
    ) -> list[FirstPartySession]:
        observed_at = _as_utc(now or datetime.now(UTC))
        self._validate_principal_state(principal, observed_at)
        return [
            FirstPartySession(
                session_id=auth_session.sid,
                created_at=_as_utc(auth_session.created_at),
                last_seen_at=_as_utc(auth_session.last_seen_at),
                expires_at=_as_utc(auth_session.expires_at),
                revoked_at=(
                    _as_utc(auth_session.revoked_at)
                    if auth_session.revoked_at is not None
                    else None
                ),
                device=auth_session.device,
                is_current=auth_session.sid == principal.session_id,
            )
            for auth_session in self._sessions.list_for_user(principal.user_id)
        ]

    def revoke_session(
        self,
        *,
        principal: FirstPartyPrincipal,
        session_id: UUID,
        context: RequestSecurityContext,
        now: datetime | None = None,
    ) -> bool:
        observed_at = _as_utc(now or datetime.now(UTC))
        self._validate_principal_state(principal, observed_at)
        auth_session = self._sessions.get_for_update(session_id)
        if auth_session is None or auth_session.user_id != principal.user_id:
            raise SessionNotFoundError()
        was_revoked = auth_session.revoked_at is not None
        if auth_session.revoked_at is None:
            self._revoke_session(auth_session, observed_at, "User session revocation")
        self._append_audit(
            action="authentication.session_revoked",
            outcome=AuditOutcome.SUCCESS,
            context=context,
            actor_user_id=principal.user_id,
            target_user_id=principal.user_id,
            session_id=session_id,
            metadata={
                "current_session": session_id == principal.session_id,
                "already_revoked": was_revoked,
            },
        )
        return session_id == principal.session_id

    def setup_password(
        self,
        *,
        user_id: UUID,
        new_password: str,
        context: RequestSecurityContext,
        now: datetime | None = None,
    ) -> UUID:
        observed_at = _as_utc(now or datetime.now(UTC))
        self._consume_password_rate_limit(user_id, context, observed_at, "password.setup")
        user = self._users.get_for_update(user_id)
        if user is None or user.status != IdentityUserStatus.ACTIVE:
            self._append_audit(
                action="password.setup",
                outcome=AuditOutcome.DENIED,
                reason_code="ACCOUNT_UNAVAILABLE",
                context=context,
                target_user_id=user_id if user is not None else None,
            )
            raise InvalidCredentialsError("ACCOUNT_UNAVAILABLE")
        if self._reconciliation.has_drift(user.id):
            self._append_audit(
                action="password.setup",
                outcome=AuditOutcome.DENIED,
                reason_code="RECONCILIATION_DRIFT",
                context=context,
                target_user_id=user.id,
            )
            raise ReconciliationDriftError()
        if user.password_hash is not None:
            self._append_audit(
                action="password.setup",
                outcome=AuditOutcome.DENIED,
                reason_code="PASSWORD_ALREADY_CONFIGURED",
                context=context,
                actor_user_id=user.id,
                target_user_id=user.id,
            )
            raise PasswordAlreadyConfiguredError()
        try:
            self._validate_new_password(new_password)
        except PasswordPolicyError:
            self._append_audit(
                action="password.setup",
                outcome=AuditOutcome.DENIED,
                reason_code="PASSWORD_POLICY_VIOLATION",
                context=context,
                actor_user_id=user.id,
                target_user_id=user.id,
            )
            raise
        user.password_hash = self._passwords.hash_password(new_password)
        user.password_changed_at = observed_at
        user.auth_version += 1
        user.failed_login_count = 0
        user.locked_until = None
        self._sessions.revoke_active_for_user(
            user.id,
            revoked_at=observed_at,
            reason="Password enrollment",
        )
        self._append_audit(
            action="password.setup",
            outcome=AuditOutcome.SUCCESS,
            context=context,
            actor_user_id=user.id,
            target_user_id=user.id,
        )
        return user.id

    def change_password(
        self,
        *,
        principal: FirstPartyPrincipal,
        current_password: str,
        new_password: str,
        context: RequestSecurityContext,
        now: datetime | None = None,
    ) -> IssuedIdentitySession:
        observed_at = _as_utc(now or datetime.now(UTC))
        self._consume_password_rate_limit(
            principal.user_id,
            context,
            observed_at,
            "password.change",
        )
        user = self._users.get_for_update(principal.user_id)
        auth_session = self._sessions.get_for_update(principal.session_id)
        claims = AccessTokenClaims(
            user_id=principal.user_id,
            session_id=principal.session_id,
            auth_version=principal.auth_version,
            role=principal.role,
            issued_at=observed_at,
            expires_at=observed_at,
            token_id=uuid4(),
        )
        try:
            self._validate_access_state(
                claims=claims,
                auth_session=auth_session,
                user=user,
                observed_at=observed_at,
            )
        except InvalidIdentityTokenError as exc:
            self._append_audit(
                action="password.change",
                outcome=AuditOutcome.DENIED,
                reason_code="INVALID_SESSION",
                context=context,
                target_user_id=principal.user_id,
                session_id=principal.session_id,
            )
            raise InvalidSessionError() from exc

        assert user is not None
        assert auth_session is not None
        if not self._passwords.verify_password_or_dummy(
            user.password_hash,
            current_password,
        ):
            self._append_audit(
                action="password.change",
                outcome=AuditOutcome.FAILURE,
                reason_code="INVALID_CURRENT_PASSWORD",
                context=context,
                actor_user_id=user.id,
                target_user_id=user.id,
                session_id=auth_session.sid,
            )
            raise InvalidCredentialsError("INVALID_CURRENT_PASSWORD")
        try:
            self._validate_new_password(new_password)
            if self._passwords.verify_password(user.password_hash or "", new_password):
                raise PasswordPolicyError("New password must differ from current password")
        except PasswordPolicyError:
            self._append_audit(
                action="password.change",
                outcome=AuditOutcome.DENIED,
                reason_code="PASSWORD_POLICY_VIOLATION",
                context=context,
                actor_user_id=user.id,
                target_user_id=user.id,
                session_id=auth_session.sid,
            )
            raise

        user.password_hash = self._passwords.hash_password(new_password)
        user.password_changed_at = observed_at
        user.auth_version += 1
        user.failed_login_count = 0
        user.locked_until = None
        self._sessions.revoke_active_for_user(
            user.id,
            revoked_at=observed_at,
            reason="Password changed",
            except_sid=auth_session.sid,
        )
        rotated_refresh_token = self._refresh_tokens.issue(auth_session.sid)
        auth_session.auth_version = user.auth_version
        auth_session.refresh_token_hash = self._refresh_tokens.digest(rotated_refresh_token)
        auth_session.refresh_generation += 1
        auth_session.last_seen_at = observed_at
        access_token, new_claims = self._jwt_tokens.issue_access_token(
            user_id=user.id,
            session_id=auth_session.sid,
            auth_version=user.auth_version,
            role=self._role_for_user(user.id),
            now=observed_at,
        )
        self._append_audit(
            action="password.change",
            outcome=AuditOutcome.SUCCESS,
            context=context,
            actor_user_id=user.id,
            target_user_id=user.id,
            session_id=auth_session.sid,
            metadata={"other_sessions_revoked": True},
        )
        return IssuedIdentitySession(
            user_id=user.id,
            session_id=auth_session.sid,
            access_token=access_token,
            refresh_token=rotated_refresh_token,
            csrf_token=self._csrf_tokens.issue(auth_session.sid),
            access_expires_at=new_claims.expires_at,
            session_expires_at=_as_utc(auth_session.expires_at),
        )

    def _create_session(
        self,
        *,
        user: IdentityUserModel,
        device: str | None,
        context: RequestSecurityContext,
        observed_at: datetime,
    ) -> IssuedIdentitySession:
        session_id = uuid4()
        refresh_token = self._refresh_tokens.issue(session_id)
        session_expires_at = observed_at + self._session_ttl
        self._sessions.add(
            AuthSessionModel(
                sid=session_id,
                user_id=user.id,
                auth_version=user.auth_version,
                created_at=observed_at,
                last_seen_at=observed_at,
                expires_at=session_expires_at,
                device=(
                    self._metadata_hasher.hash_value("session-device", device).hex()
                    if device
                    else None
                ),
                ip_hash=context.ip_hash,
                user_agent_hash=context.user_agent_hash,
                refresh_token_hash=self._refresh_tokens.digest(refresh_token),
                refresh_generation=0,
            )
        )
        access_token, claims = self._jwt_tokens.issue_access_token(
            user_id=user.id,
            session_id=session_id,
            auth_version=user.auth_version,
            role=self._role_for_user(user.id),
            now=observed_at,
        )
        return IssuedIdentitySession(
            user_id=user.id,
            session_id=session_id,
            access_token=access_token,
            refresh_token=refresh_token,
            csrf_token=self._csrf_tokens.issue(session_id),
            access_expires_at=claims.expires_at,
            session_expires_at=session_expires_at,
        )

    def _validate_access_state(
        self,
        *,
        claims: AccessTokenClaims,
        auth_session: AuthSessionModel | None,
        user: IdentityUserModel | None,
        observed_at: datetime,
    ) -> None:
        if auth_session is None:
            raise InvalidIdentityTokenError("INVALID_SESSION")
        if user is None:
            raise InvalidIdentityTokenError("ACCOUNT_UNAVAILABLE")
        if (
            auth_session.user_id != claims.user_id
            or auth_session.sid != claims.session_id
            or user.id != claims.user_id
        ):
            raise InvalidIdentityTokenError("INVALID_SESSION")
        if auth_session.revoked_at is not None:
            raise InvalidIdentityTokenError("SESSION_REVOKED")
        if auth_session.refresh_token_hash is None:
            raise InvalidIdentityTokenError("INVALID_SESSION")
        if _as_utc(auth_session.expires_at) <= observed_at:
            raise InvalidIdentityTokenError("SESSION_EXPIRED")
        if (
            auth_session.auth_version != claims.auth_version
            or user.auth_version != claims.auth_version
        ):
            raise InvalidIdentityTokenError("AUTH_VERSION_MISMATCH")
        if self._role_for_user(user.id) != claims.role:
            raise InvalidIdentityTokenError("ROLE_CHANGED")
        if user.status != IdentityUserStatus.ACTIVE or user.deleted_at is not None:
            raise InvalidIdentityTokenError("ACCOUNT_UNAVAILABLE")
        if self._reconciliation.has_drift(user.id):
            raise InvalidIdentityTokenError("RECONCILIATION_DRIFT")

    def _validate_principal_state(
        self,
        principal: FirstPartyPrincipal,
        observed_at: datetime,
    ) -> None:
        auth_session = self._sessions.get(principal.session_id)
        user = self._users.get(principal.user_id)
        claims = AccessTokenClaims(
            user_id=principal.user_id,
            session_id=principal.session_id,
            auth_version=principal.auth_version,
            role=principal.role,
            issued_at=principal.authenticated_at,
            expires_at=observed_at,
            token_id=uuid4(),
        )
        self._validate_access_state(
            claims=claims,
            auth_session=auth_session,
            user=user,
            observed_at=observed_at,
        )

    def _role_for_user(self, user_id: UUID) -> str:
        return self._role_assignments.get_active_role_code(user_id) or "user"

    def _session_rejection_reason(
        self,
        auth_session: AuthSessionModel,
        user: IdentityUserModel | None,
        observed_at: datetime,
    ) -> str | None:
        if auth_session.revoked_at is not None:
            return "SESSION_REVOKED"
        if _as_utc(auth_session.expires_at) <= observed_at:
            return "SESSION_EXPIRED"
        if user is None:
            return "ACCOUNT_UNAVAILABLE"
        if user.status != IdentityUserStatus.ACTIVE or user.deleted_at is not None:
            return "ACCOUNT_UNAVAILABLE"
        if (
            auth_session.auth_version != user.auth_version
            or auth_session.refresh_token_hash is None
        ):
            return "AUTH_VERSION_MISMATCH"
        if self._reconciliation.has_drift(user.id):
            return "RECONCILIATION_DRIFT"
        return None

    def _login_rejection_reason(
        self,
        user: IdentityUserModel | None,
        password_matches: bool,
        observed_at: datetime,
    ) -> str | None:
        if user is None:
            return "INVALID_CREDENTIALS"
        if user.password_hash is None:
            return "PASSWORD_NOT_ENROLLED"
        if user.status == IdentityUserStatus.LOCKED or self._is_locked(
            user,
            observed_at,
        ):
            return "ACCOUNT_LOCKED"
        if user.status != IdentityUserStatus.ACTIVE or user.deleted_at is not None:
            return "ACCOUNT_UNAVAILABLE"
        if not password_matches:
            return "INVALID_CREDENTIALS"
        return None

    def _record_failed_login(
        self,
        user: IdentityUserModel,
        observed_at: datetime,
    ) -> bool:
        user.failed_login_count += 1
        if user.failed_login_count >= self._failed_login_limit:
            user.locked_until = observed_at + self._account_lock_duration
            return True
        return False

    @staticmethod
    def _is_locked(user: IdentityUserModel, observed_at: datetime) -> bool:
        return user.locked_until is not None and _as_utc(user.locked_until) > observed_at

    def _validate_new_password(self, password: str) -> None:
        if len(password) < self._password_min_length:
            raise PasswordPolicyError(
                f"Password must contain at least {self._password_min_length} characters"
            )
        if len(password) > self._password_max_length:
            raise PasswordPolicyError(
                f"Password must contain at most {self._password_max_length} characters"
            )

    def _consume_password_rate_limit(
        self,
        user_id: UUID,
        context: RequestSecurityContext,
        observed_at: datetime,
        action: str,
    ) -> None:
        subject_hash = self._metadata_hasher.hash_value(
            "rate-limit-password-user",
            str(user_id),
        )
        try:
            self._rate_limits.consume(
                scope=action,
                subject_hash=subject_hash,
                limit=self._password_rate_limit,
                window=self._password_rate_window,
                now=observed_at,
            )
        except RateLimitExceededError:
            self._append_audit(
                action=action,
                outcome=AuditOutcome.DENIED,
                reason_code="RATE_LIMITED",
                context=context,
                target_user_id=user_id,
            )
            raise

    @staticmethod
    def _revoke_session(
        auth_session: AuthSessionModel,
        revoked_at: datetime,
        reason: str,
    ) -> None:
        auth_session.revoked_at = revoked_at
        auth_session.revocation_reason = reason[:500]

    def _append_audit(
        self,
        *,
        action: str,
        outcome: AuditOutcome,
        context: RequestSecurityContext,
        reason_code: str | None = None,
        actor_user_id: UUID | None = None,
        target_user_id: UUID | None = None,
        session_id: UUID | None = None,
        metadata: dict[str, object] | None = None,
    ) -> None:
        self._audit.append(
            AuditEventModel(
                actor_user_id=actor_user_id,
                target_user_id=target_user_id,
                session_id=session_id,
                action=action,
                outcome=outcome,
                reason_code=reason_code,
                request_id=context.request_id,
                ip_hash=context.ip_hash,
                user_agent_hash=context.user_agent_hash,
                event_metadata=metadata or {},
            )
        )
