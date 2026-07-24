from pathlib import Path

MIGRATIONS_DIR = Path(__file__).parents[1] / "migrations"
COEXISTENCE = MIGRATIONS_DIR / "0019_identity_coexistence.sql"
BACKFILL = MIGRATIONS_DIR / "0020_identity_backfill.sql"
ROLLBACK = MIGRATIONS_DIR / "rollback" / "0019_identity_coexistence_rollback.sql"


def _sql(path: Path) -> str:
    return " ".join(path.read_text(encoding="utf-8").lower().split())


def test_signup_trigger_preserves_name_and_is_fail_closed() -> None:
    sql = _sql(COEXISTENCE)

    assert "create or replace function public.handle_new_user()" in sql
    assert "security definer set search_path = pg_catalog" in sql
    assert "insert into identity.users" in sql
    assert "insert into identity.user_profiles" in sql
    assert "perform identity.ensure_default_role(new.id, 'insert')" in sql
    assert "insert into public.profiles" in sql
    assert "coexistence.signup_synced" in sql
    assert "exception when" not in sql


def test_auth_updates_only_write_supabase_owned_identity_fields() -> None:
    sql = _sql(COEXISTENCE)
    update_clause = sql.split("on conflict (id) do update", maxsplit=1)[1].split(
        "returning true",
        maxsplit=1,
    )[0]

    for field in (
        "email = excluded.email",
        "email_normalized = excluded.email_normalized",
        "status = excluded.status",
        "email_verified_at = excluded.email_verified_at",
        "created_at = excluded.created_at",
        "updated_at = excluded.updated_at",
        "deleted_at = excluded.deleted_at",
    ):
        assert field in update_clause

    for protected_field in (
        "password_hash =",
        "auth_version =",
        "failed_login_count =",
        "locked_until =",
        "password_changed_at =",
        "last_login_at =",
    ):
        assert protected_field not in update_clause


def test_coexistence_triggers_and_reconciliation_objects_are_present() -> None:
    sql = _sql(COEXISTENCE)

    assert "drop trigger if exists on_auth_user_created" not in sql
    for trigger in (
        "on_auth_user_identity_updated",
        "on_auth_user_identity_deleted",
        "on_profile_identity_inserted",
        "on_profile_identity_updated",
    ):
        assert trigger in sql

    assert "create or replace view identity.coexistence_drift" in sql
    assert "create or replace view identity.coexistence_metrics" in sql
    assert "create table identity.coexistence_runs" in sql
    assert "pg_advisory_xact_lock" in sql


def test_backfill_is_ordered_idempotent_and_preserves_passwords() -> None:
    sql = _sql(BACKFILL)

    assert sql.index("insert into identity.roles") < sql.index("insert into identity.permissions")
    assert sql.index("insert into identity.permissions") < sql.index(
        "create or replace function identity.backfill_from_supabase"
    )
    assert "on conflict (code) do update" in sql
    assert "on conflict (role_id, permission_id) do nothing" in sql
    assert "identity.sync_auth_user" in sql
    assert "identity.sync_public_profile" in sql
    assert "password_hash" not in sql


def test_rollback_restores_only_the_legacy_signup_behavior() -> None:
    sql = _sql(ROLLBACK)

    for trigger in (
        "on_auth_user_identity_updated",
        "on_auth_user_identity_deleted",
        "on_profile_identity_inserted",
        "on_profile_identity_updated",
    ):
        assert f"drop trigger if exists {trigger}" in sql

    assert "create or replace function public.handle_new_user()" in sql
    assert "insert into public.profiles" in sql
    assert "insert into identity." not in sql
    assert "drop schema identity" not in sql
    assert "delete from identity." not in sql
