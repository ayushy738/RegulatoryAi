from pathlib import Path

MIGRATIONS_DIR = Path(__file__).parents[1] / "migrations"
SCHEMA_MIGRATION = MIGRATIONS_DIR / "0017_identity_schema.sql"
SEED_MIGRATION = MIGRATIONS_DIR / "0018_identity_seed.sql"

IDENTITY_TABLES = {
    "users",
    "user_profiles",
    "roles",
    "permissions",
    "role_permissions",
    "user_role_assignments",
    "password_reset_tokens",
    "email_verification_tokens",
    "auth_sessions",
    "audit_events",
}


def _normalized_sql(path: Path) -> str:
    return " ".join(path.read_text(encoding="utf-8").lower().split())


def test_identity_schema_migration_creates_all_required_tables() -> None:
    sql = _normalized_sql(SCHEMA_MIGRATION)

    assert "create schema identity" in sql
    for table in IDENTITY_TABLES:
        assert f"create table identity.{table}" in sql


def test_identity_schema_migration_is_additive_and_isolated() -> None:
    sql = _normalized_sql(SCHEMA_MIGRATION)

    assert "auth.users" not in sql
    assert "public.profiles" not in sql
    assert "alter table public." not in sql
    assert "create trigger" not in sql
    assert "create policy" not in sql
    assert "enable row level security" not in sql
    assert "insert into identity." not in sql


def test_identity_schema_migration_contains_security_constraints() -> None:
    sql = _normalized_sql(SCHEMA_MIGRATION)

    assert "password_hash text" in sql
    assert "password_hash text not null" not in sql
    assert "identity_users_email_normalized_key unique (email_normalized)" in sql
    assert "identity_user_role_assignments_active_user_idx" in sql
    assert "where revoked_at is null" in sql
    assert "octet_length(token_hash) = 32" in sql
    assert "revoke update, delete, truncate on identity.audit_events from public" in sql


def test_seed_migration_contains_only_current_roles_and_permissions() -> None:
    sql = _normalized_sql(SEED_MIGRATION)

    assert "insert into identity.roles" in sql
    assert "insert into identity.permissions" in sql
    assert "'user'" in sql
    assert "'admin'" in sql
    assert "'application.access'" in sql
    assert "'admin.access'" in sql
    assert sql.count("on conflict (code) do update") == 2
    assert "on conflict (role_id, permission_id) do nothing" in sql
    assert "super_admin" not in sql
    assert "auth.users" not in sql
    assert "public.profiles" not in sql
    assert "create trigger" not in sql
