from argon2 import PasswordHasher
from argon2.low_level import Type

from backend.identity.services.password import PasswordService


def test_argon2id_password_hashing_and_verification() -> None:
    service = PasswordService()

    password_hash = service.hash_password("correct horse battery staple")

    assert password_hash.startswith("$argon2id$")
    assert service.verify_password(password_hash, "correct horse battery staple") is True
    assert service.verify_password(password_hash, "incorrect password") is False
    assert service.needs_rehash(password_hash) is False


def test_password_service_detects_obsolete_and_invalid_hashes() -> None:
    obsolete_hasher = PasswordHasher(
        time_cost=1,
        memory_cost=8192,
        parallelism=1,
        hash_len=16,
        salt_len=8,
        type=Type.ID,
    )
    service = PasswordService()
    obsolete_hash = obsolete_hasher.hash("password")

    assert service.needs_rehash(obsolete_hash) is True
    assert service.verify_password("not-a-password-hash", "password") is False
    assert service.needs_rehash("not-a-password-hash") is True
