from pathlib import Path

MIGRATION = (
    Path(__file__).parents[1] / "migrations" / "0021_identity_authentication.sql"
)


def test_authentication_migration_is_additive_and_does_not_touch_coexistence() -> None:
    sql = " ".join(MIGRATION.read_text(encoding="utf-8").lower().split())

    assert "alter table identity.auth_sessions" in sql
    assert "create table identity.authentication_rate_limits" in sql
    assert "refresh_token_hash bytea" in sql
    assert "octet_length(refresh_token_hash) = 32" in sql
    assert "auth.users" not in sql
    assert "public.profiles" not in sql
    assert "create trigger" not in sql
    assert "drop trigger" not in sql
    assert "create policy" not in sql
