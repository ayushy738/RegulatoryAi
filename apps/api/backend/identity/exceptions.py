from __future__ import annotations


class IdentityConfigurationError(RuntimeError):
    pass


class IdentityAuthenticationError(Exception):
    def __init__(
        self,
        code: str,
        public_message: str,
        *,
        retry_after_seconds: int | None = None,
    ) -> None:
        super().__init__(code)
        self.code = code
        self.public_message = public_message
        self.retry_after_seconds = retry_after_seconds


class InvalidCredentialsError(IdentityAuthenticationError):
    def __init__(self, code: str = "INVALID_CREDENTIALS") -> None:
        super().__init__(code, "Invalid email or password")


class InvalidIdentityTokenError(IdentityAuthenticationError):
    def __init__(self, code: str = "INVALID_ACCESS_TOKEN") -> None:
        super().__init__(code, "Invalid or expired identity token")


class InvalidSessionError(IdentityAuthenticationError):
    def __init__(self, code: str = "INVALID_SESSION") -> None:
        super().__init__(code, "Invalid or expired identity session")


class CsrfValidationError(IdentityAuthenticationError):
    def __init__(self) -> None:
        super().__init__("CSRF_VALIDATION_FAILED", "CSRF validation failed")


class ReconciliationDriftError(IdentityAuthenticationError):
    def __init__(self) -> None:
        super().__init__(
            "RECONCILIATION_DRIFT",
            "Identity synchronization must be reconciled before this operation",
        )


class SessionExchangeReplayError(IdentityAuthenticationError):
    def __init__(self) -> None:
        super().__init__(
            "SESSION_EXCHANGE_REPLAY",
            "This Supabase session has already been exchanged",
        )


class PasswordAlreadyConfiguredError(IdentityAuthenticationError):
    def __init__(self) -> None:
        super().__init__("PASSWORD_ALREADY_CONFIGURED", "Password is already configured")


class PasswordPolicyError(IdentityAuthenticationError):
    def __init__(self, public_message: str) -> None:
        super().__init__("PASSWORD_POLICY_VIOLATION", public_message)


class RateLimitExceededError(IdentityAuthenticationError):
    def __init__(self, retry_after_seconds: int) -> None:
        super().__init__(
            "RATE_LIMITED",
            "Too many authentication attempts",
            retry_after_seconds=max(1, retry_after_seconds),
        )
