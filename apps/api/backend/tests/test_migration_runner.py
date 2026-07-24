from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from backend.core import migrations as migration_module
from backend.core.migrations import (
    CREATE_MIGRATION_TABLE_SQL,
    EXISTING_MIGRATION_SPECS,
    LEGACY_BASELINE_MAX_VERSION,
    AppliedMigration,
    MigrationDriftError,
    MigrationFile,
    MigrationPlanError,
    apply_migration,
    baseline_legacy_migrations,
    discover_migrations,
    plan_existing_migrations,
    plan_pending_migrations,
    verify_and_record_existing_migrations,
    verify_existing_migration,
)

MIGRATIONS_DIRECTORY = Path(__file__).parents[1] / "migrations"


def _migration(path: Path, version: str, name: str, sql: str = "select 1;") -> Path:
    migration = path / f"{version}_{name}.sql"
    migration.write_text(sql, encoding="utf-8")
    return migration


def _applied(migration: MigrationFile) -> AppliedMigration:
    return AppliedMigration(
        version=migration.version,
        filename=migration.filename,
        checksum=migration.checksum,
        applied_at=datetime.now(UTC),
    )


def test_discovery_orders_migrations_and_hashes_raw_files(tmp_path: Path) -> None:
    second = _migration(tmp_path, "0002", "second", "select 2;\n")
    first = _migration(tmp_path, "0001", "first", "select 1;\n")

    migrations = discover_migrations(tmp_path)

    assert [migration.version for migration in migrations] == ["0001", "0002"]
    assert migrations[0].path == first
    assert migrations[1].path == second
    assert len(migrations[0].checksum) == 64


def test_discovery_rejects_invalid_names_and_duplicate_versions(
    tmp_path: Path,
) -> None:
    _migration(tmp_path, "0001", "first")
    _migration(tmp_path, "0001", "duplicate")

    with pytest.raises(MigrationPlanError, match="Duplicate migration version"):
        discover_migrations(tmp_path)

    invalid_directory = tmp_path / "invalid"
    invalid_directory.mkdir()
    (invalid_directory / "migration.sql").write_text("select 1;", encoding="utf-8")

    with pytest.raises(MigrationPlanError, match="Invalid migration filename"):
        discover_migrations(invalid_directory)


def test_pending_plan_is_ordered_and_supports_an_explicit_upper_bound(
    tmp_path: Path,
) -> None:
    for version in ("0001", "0002", "0003"):
        _migration(tmp_path, version, f"migration_{version}")
    migrations = discover_migrations(tmp_path)

    pending = plan_pending_migrations(
        migrations,
        [_applied(migrations[0])],
        through="0002",
    )

    assert [migration.version for migration in pending] == ["0002"]


def test_already_applied_migrations_are_not_executed_again(tmp_path: Path) -> None:
    for version in ("0001", "0002"):
        _migration(tmp_path, version, f"migration_{version}")
    migrations = discover_migrations(tmp_path)

    pending = plan_pending_migrations(
        migrations,
        [_applied(migration) for migration in migrations],
    )

    assert pending == ()


def test_modified_applied_migration_is_refused(tmp_path: Path) -> None:
    path = _migration(tmp_path, "0001", "first", "select 1;\n")
    original = discover_migrations(tmp_path)[0]
    applied = _applied(original)
    path.write_text("select 2;\n", encoding="utf-8")
    modified = discover_migrations(tmp_path)

    with pytest.raises(MigrationDriftError, match="checksum changed"):
        plan_pending_migrations(modified, [applied])


def test_renamed_or_missing_applied_migration_is_refused(tmp_path: Path) -> None:
    original_path = _migration(tmp_path, "0001", "first")
    original = discover_migrations(tmp_path)[0]
    applied = _applied(original)
    original_path.rename(tmp_path / "0001_renamed.sql")
    renamed = discover_migrations(tmp_path)

    with pytest.raises(MigrationDriftError, match="filename changed"):
        plan_pending_migrations(renamed, [applied])

    original_path = tmp_path / "0001_renamed.sql"
    original_path.unlink()
    _migration(tmp_path, "0002", "second")
    missing = discover_migrations(tmp_path)

    with pytest.raises(MigrationDriftError, match="missing from the repository"):
        plan_pending_migrations(missing, [applied])


def test_history_gaps_are_refused(tmp_path: Path) -> None:
    for version in ("0001", "0002", "0003"):
        _migration(tmp_path, version, f"migration_{version}")
    migrations = discover_migrations(tmp_path)

    with pytest.raises(MigrationDriftError, match="contiguous prefix"):
        plan_pending_migrations(migrations, [_applied(migrations[1])])


def test_apply_executes_the_complete_sql_before_recording_history(
    tmp_path: Path,
) -> None:
    sql = """
    create function example() returns void language plpgsql as $$
    begin
      perform 1;
    end;
    $$;
    """
    migration = MigrationFile.from_path(_migration(tmp_path, "0001", "function", sql))
    connection = MagicMock()

    apply_migration(connection, migration)

    connection.exec_driver_sql.assert_called_once_with(sql)
    assert connection.method_calls[0][0] == "exec_driver_sql"
    assert connection.method_calls[1][0] == "execute"


def test_ledger_contains_required_columns_and_constraints() -> None:
    normalized = " ".join(CREATE_MIGRATION_TABLE_SQL.lower().split())

    assert "version varchar(64) not null" in normalized
    assert "filename text not null" in normalized
    assert "checksum char(64) not null" in normalized
    assert "applied_at timestamptz not null default now()" in normalized
    assert "schema_migrations_pkey primary key (version)" in normalized
    assert "schema_migrations_filename_key unique (filename)" in normalized
    assert "schema_migrations_checksum_chk" in normalized


def test_legacy_baseline_cannot_include_new_identity_migrations(
    tmp_path: Path,
) -> None:
    _migration(tmp_path, LEGACY_BASELINE_MAX_VERSION, "legacy")
    _migration(tmp_path, "0017", "identity_schema")

    with pytest.raises(MigrationPlanError, match="Baseline cannot pass"):
        baseline_legacy_migrations(
            MagicMock(),
            tmp_path,
            through="0017",
        )


def test_mark_existing_accepts_only_the_pinned_0021_and_0022_suffix() -> None:
    migrations = discover_migrations(MIGRATIONS_DIRECTORY)
    applied = [_applied(migration) for migration in migrations if int(migration.version) <= 20]

    existing = plan_existing_migrations(
        migrations,
        applied,
        through="0022",
    )

    assert [migration.version for migration in existing] == ["0021", "0022"]
    assert existing[0].checksum == EXISTING_MIGRATION_SPECS["0021"].checksum
    assert existing[1].checksum == EXISTING_MIGRATION_SPECS["0022"].checksum


def test_mark_existing_refuses_a_migration_without_a_registered_verifier(
    tmp_path: Path,
) -> None:
    migration = MigrationFile.from_path(_migration(tmp_path, "0020", "unsupported"))

    with pytest.raises(MigrationPlanError, match="no registered schema verifier"):
        plan_existing_migrations(
            [migration],
            [],
            through="0020",
        )


def test_mark_existing_refuses_a_modified_supported_migration(
    tmp_path: Path,
) -> None:
    migration = MigrationFile.from_path(
        _migration(tmp_path, "0021", "identity_authentication", "select 42;\n")
    )

    with pytest.raises(MigrationDriftError, match="checksum approved"):
        plan_existing_migrations(
            [migration],
            [],
            through="0021",
        )


def test_existing_schema_verification_fails_closed_without_recording_history() -> None:
    migration = next(
        migration
        for migration in discover_migrations(MIGRATIONS_DIRECTORY)
        if migration.version == "0021"
    )
    connection = MagicMock()
    connection.execute.return_value.scalar_one_or_none.return_value = False

    with pytest.raises(MigrationDriftError, match="existing-schema verification failed"):
        verify_existing_migration(connection, migration)

    connection.exec_driver_sql.assert_not_called()
    assert all(
        "insert into public.schema_migrations" not in str(call).lower()
        for call in connection.execute.call_args_list
    )


def test_existing_schema_verification_never_executes_migration_sql() -> None:
    migration = next(
        migration
        for migration in discover_migrations(MIGRATIONS_DIRECTORY)
        if migration.version == "0022"
    )
    connection = MagicMock()
    connection.execute.return_value.scalar_one_or_none.return_value = True

    verify_existing_migration(connection, migration)

    connection.exec_driver_sql.assert_not_called()
    assert connection.execute.call_count == len(
        EXISTING_MIGRATION_SPECS["0022"].checks
    )


def test_mark_existing_verifies_the_complete_suffix_before_recording(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    existing = tuple(
        migration
        for migration in discover_migrations(MIGRATIONS_DIRECTORY)
        if migration.version in {"0021", "0022"}
    )
    events: list[str] = []

    def verify(_: MagicMock, migration: MigrationFile) -> None:
        events.append(f"verify:{migration.version}")

    def record(_: MagicMock, migration: MigrationFile) -> None:
        events.append(f"record:{migration.version}")

    monkeypatch.setattr(migration_module, "verify_existing_migration", verify)
    monkeypatch.setattr(migration_module, "record_migration", record)

    verify_and_record_existing_migrations(MagicMock(), existing)

    assert events == [
        "verify:0021",
        "verify:0022",
        "record:0021",
        "record:0022",
    ]


def test_mark_existing_records_nothing_if_any_schema_verifier_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    existing = tuple(
        migration
        for migration in discover_migrations(MIGRATIONS_DIRECTORY)
        if migration.version in {"0021", "0022"}
    )
    record = MagicMock()

    def verify(_: MagicMock, migration: MigrationFile) -> None:
        if migration.version == "0022":
            raise MigrationDriftError("verification failed")

    monkeypatch.setattr(migration_module, "verify_existing_migration", verify)
    monkeypatch.setattr(migration_module, "record_migration", record)

    with pytest.raises(MigrationDriftError, match="verification failed"):
        verify_and_record_existing_migrations(MagicMock(), existing)

    record.assert_not_called()
