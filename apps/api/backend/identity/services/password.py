from functools import lru_cache

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from argon2.low_level import Type


def _default_hasher() -> PasswordHasher:
    return PasswordHasher(
        time_cost=3,
        memory_cost=65_536,
        parallelism=4,
        hash_len=32,
        salt_len=16,
        type=Type.ID,
    )


@lru_cache(maxsize=1)
def _dummy_password_hash() -> str:
    return _default_hasher().hash("identity-dummy-verification-value")


class PasswordService:
    """Argon2id password hashing and timing-normalized verification."""

    def __init__(self, hasher: PasswordHasher | None = None) -> None:
        self._hasher = hasher or _default_hasher()

    def hash_password(self, password: str) -> str:
        return self._hasher.hash(password)

    def verify_password(self, password_hash: str, password: str) -> bool:
        try:
            return self._hasher.verify(password_hash, password)
        except (VerificationError, VerifyMismatchError):
            return False
        except InvalidHashError:
            self._perform_dummy_verification(password)
            return False

    def verify_password_or_dummy(self, password_hash: str | None, password: str) -> bool:
        if password_hash is None:
            self._perform_dummy_verification(password)
            return False
        return self.verify_password(password_hash, password)

    def _perform_dummy_verification(self, password: str) -> None:
        try:
            self._hasher.verify(_dummy_password_hash(), password)
        except (VerificationError, VerifyMismatchError):
            pass

    def needs_rehash(self, password_hash: str) -> bool:
        try:
            return self._hasher.check_needs_rehash(password_hash)
        except InvalidHashError:
            return True
