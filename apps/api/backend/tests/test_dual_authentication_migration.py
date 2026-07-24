from pathlib import Path

MIGRATION = (
    Path(__file__).parents[1] / "migrations" / "0022_dual_authentication.sql"
)
ROLLBACK = (
    Path(__file__).parents[1]
    / "migrations"
    / "rollback"
    / "0022_dual_authentication_rollback.sql"
)


def _normalized(path: Path) -> str:
    return " ".join(path.read_text(encoding="utf-8").lower().split())


def test_dual_authentication_migration_is_additive_and_isolated() -> None:
    sql = _normalized(MIGRATION)

    assert "create table identity.session_exchanges" in sql
    assert "create table identity.authentication_metrics_hourly" in sql
    assert "create or replace view identity.dual_authentication_metrics" in sql
    assert "unique (source_session_hash)" in sql
    assert "auth.users" not in sql
    assert "public.profiles" not in sql
    assert "alter table" not in sql
    assert "create trigger" not in sql
    assert "drop trigger" not in sql
    assert "create policy" not in sql
    assert "enable row level security" not in sql


def test_dual_authentication_rollback_does_not_touch_legacy_authentication() -> None:
    sql = _normalized(ROLLBACK)

    assert "identity.session_exchanges" in sql
    assert "identity.authentication_metrics_hourly" in sql
    assert "identity.dual_authentication_metrics" in sql
    assert "auth.users" not in sql
    assert "public.profiles" not in sql
    assert "trigger" not in sql
    assert "policy" not in sql
