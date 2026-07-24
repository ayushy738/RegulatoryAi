from __future__ import annotations

import os
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Connection
from sqlalchemy.exc import IntegrityError

from backend.core.migrations import discover_migrations, verify_existing_migration

TEST_DATABASE_URL = os.getenv("IDENTITY_TEST_DATABASE_URL")
POSTGRES_TESTS_ALLOWED = os.getenv("ALLOW_IDENTITY_POSTGRES_TESTS") == "dedicated-test-database"

pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL or not POSTGRES_TESTS_ALLOWED,
    reason=(
        "Requires IDENTITY_TEST_DATABASE_URL and explicit confirmation that it "
        "targets a disposable dedicated test database"
    ),
)


@pytest.fixture
def connection() -> Iterator[Connection]:
    assert TEST_DATABASE_URL is not None
    database_url = TEST_DATABASE_URL
    if database_url.startswith("postgresql://"):
        database_url = database_url.replace(
            "postgresql://",
            "postgresql+psycopg://",
            1,
        )
    engine = create_engine(database_url)
    with engine.connect() as database_connection:
        if (
            database_connection.execute(
                text("select to_regclass('identity.coexistence_runs') is not null")
            ).scalar_one()
            is not True
        ):
            pytest.fail("PR #2B migrations are not installed in the test database")
        database_connection.rollback()
        transaction = database_connection.begin()
        try:
            yield database_connection
        finally:
            transaction.rollback()
    engine.dispose()


def _insert_auth_user(connection: Connection, user_id: UUID, email: str) -> None:
    connection.execute(
        text(
            """
            insert into auth.users (
              instance_id,
              id,
              aud,
              role,
              email,
              encrypted_password,
              created_at,
              updated_at,
              raw_app_meta_data,
              raw_user_meta_data,
              is_super_admin,
              is_sso_user,
              is_anonymous
            )
            values (
              '00000000-0000-0000-0000-000000000000',
              :id,
              'authenticated',
              'authenticated',
              :email,
              '',
              now(),
              now(),
              '{}'::jsonb,
              '{}'::jsonb,
              false,
              false,
              false
            )
            """
        ),
        {"id": user_id, "email": email},
    )


def _test_engine():
    assert TEST_DATABASE_URL is not None
    database_url = TEST_DATABASE_URL
    if database_url.startswith("postgresql://"):
        database_url = database_url.replace(
            "postgresql://",
            "postgresql+psycopg://",
            1,
        )
    return create_engine(database_url)


def test_signup_update_profile_role_and_audit_sync(
    connection: Connection,
) -> None:
    user_id = uuid4()
    _insert_auth_user(connection, user_id, f"{user_id}@example.invalid")

    signup = connection.execute(
        text(
            """
            select
              identity_user.password_hash,
              identity_user.status::text,
              public_profile.role::text,
              identity_role.code
            from identity.users identity_user
            join public.profiles public_profile
              on public_profile.id = identity_user.id
            join identity.user_role_assignments assignment
              on assignment.user_id = identity_user.id
              and assignment.revoked_at is null
            join identity.roles identity_role on identity_role.id = assignment.role_id
            where identity_user.id = :id
            """
        ),
        {"id": user_id},
    ).one()
    assert signup == (None, "pending_verification", "user", "user")

    connection.execute(
        text(
            """
            update auth.users
            set
              email = :email,
              email_confirmed_at = now(),
              updated_at = now() + interval '1 second'
            where id = :id
            """
        ),
        {"id": user_id, "email": f"updated-{user_id}@example.invalid"},
    )
    connection.execute(
        text(
            """
            update public.profiles
            set full_name = 'Test User', role = 'admin'
            where id = :id
            """
        ),
        {"id": user_id},
    )

    updated = connection.execute(
        text(
            """
            select
              identity_user.status::text,
              identity_profile.display_name,
              identity_role.code
            from identity.users identity_user
            join identity.user_profiles identity_profile
              on identity_profile.user_id = identity_user.id
            join identity.user_role_assignments assignment
              on assignment.user_id = identity_user.id
              and assignment.revoked_at is null
            join identity.roles identity_role on identity_role.id = assignment.role_id
            where identity_user.id = :id
            """
        ),
        {"id": user_id},
    ).one()
    assert updated == ("active", "Test User", "admin")
    assert (
        connection.execute(
            text(
                """
                select count(*)
                from identity.audit_events
                where target_user_id = :id
                """
            ),
            {"id": user_id},
        ).scalar_one()
        >= 7
    )


def test_repeated_backfill_is_idempotent(connection: Connection) -> None:
    user_id = uuid4()
    _insert_auth_user(connection, user_id, f"{user_id}@example.invalid")
    audit_before = connection.execute(
        text("select count(*) from identity.audit_events where target_user_id = :id"),
        {"id": user_id},
    ).scalar_one()

    connection.execute(text("select * from identity.backfill_from_supabase()"))
    connection.execute(text("select * from identity.backfill_from_supabase()"))

    audit_after = connection.execute(
        text("select count(*) from identity.audit_events where target_user_id = :id"),
        {"id": user_id},
    ).scalar_one()
    assert audit_after == audit_before
    assert (
        connection.execute(
            text(
                """
                select count(*)
                from identity.user_role_assignments
                where user_id = :id and revoked_at is null
                """
            ),
            {"id": user_id},
        ).scalar_one()
        == 1
    )


def test_backfill_repairs_users_created_while_triggers_are_disabled(
    connection: Connection,
) -> None:
    user_id = uuid4()
    email = f"{user_id}@example.invalid"
    connection.exec_driver_sql("alter table auth.users disable trigger on_auth_user_created")
    _insert_auth_user(connection, user_id, email)
    connection.exec_driver_sql("alter table auth.users enable trigger on_auth_user_created")
    connection.exec_driver_sql(
        "alter table public.profiles disable trigger on_profile_identity_inserted"
    )
    connection.execute(
        text(
            """
            insert into public.profiles (id, email, full_name, role)
            values (:id, :email, 'Backfilled User', 'admin')
            """
        ),
        {"id": user_id, "email": email},
    )
    connection.exec_driver_sql(
        "alter table public.profiles enable trigger on_profile_identity_inserted"
    )

    result = (
        connection.execute(text("select * from identity.backfill_from_supabase()")).mappings().one()
    )

    assert result["users_changed"] >= 1
    assert result["profiles_changed"] >= 1
    assert result["roles_changed"] >= 1
    assert (
        connection.execute(
            text(
                """
                select role_record.code
                from identity.user_role_assignments assignment
                join identity.roles role_record on role_record.id = assignment.role_id
                where assignment.user_id = :id and assignment.revoked_at is null
                """
            ),
            {"id": user_id},
        ).scalar_one()
        == "admin"
    )


def test_reconciliation_detects_and_reports_drift(
    connection: Connection,
) -> None:
    user_id = uuid4()
    _insert_auth_user(connection, user_id, f"{user_id}@example.invalid")
    connection.execute(
        text("delete from identity.user_profiles where user_id = :id"),
        {"id": user_id},
    )

    drifts = connection.execute(
        text(
            """
            select drift_type
            from identity.coexistence_drift
            where user_id = :id
            """
        ),
        {"id": user_id},
    ).scalars()
    assert "missing_identity_profile" in set(drifts)


def test_failed_signup_rolls_back_every_mirror_write(
    connection: Connection,
) -> None:
    first_user_id = uuid4()
    second_user_id = uuid4()
    email = f"{first_user_id}@example.invalid"
    _insert_auth_user(connection, first_user_id, email)
    savepoint = connection.begin_nested()

    with pytest.raises(IntegrityError):
        _insert_auth_user(connection, second_user_id, email)
    savepoint.rollback()

    assert (
        connection.execute(
            text("select count(*) from identity.users where id = :id"),
            {"id": second_user_id},
        ).scalar_one()
        == 0
    )


def test_rollback_script_restores_legacy_trigger(
    connection: Connection,
) -> None:
    rollback_path = (
        Path(__file__).parents[1]
        / "migrations"
        / "rollback"
        / "0019_identity_coexistence_rollback.sql"
    )
    connection.exec_driver_sql(rollback_path.read_text(encoding="utf-8"))

    trigger_names = set(
        connection.execute(
            text(
                """
                select tgname
                from pg_trigger
                where not tgisinternal
                  and tgname like '%identity%'
                """
            )
        ).scalars()
    )
    definition = connection.execute(
        text(
            """
            select pg_get_functiondef(
              'public.handle_new_user()'::regprocedure
            )
            """
        )
    ).scalar_one()

    assert trigger_names == set()
    assert "identity." not in definition


def test_concurrent_default_role_assignment_is_serialized() -> None:
    engine = _test_engine()
    user_id = uuid4()
    email = f"{user_id}@example.invalid"
    try:
        with engine.begin() as setup:
            _insert_auth_user(setup, user_id, email)
            setup.execute(
                text(
                    """
                    delete from identity.user_role_assignments
                    where user_id = :id
                    """
                ),
                {"id": user_id},
            )

        def assign_default() -> bool:
            with engine.begin() as connection:
                return bool(
                    connection.execute(
                        text(
                            """
                            select identity.ensure_default_role(
                              :id,
                              'CONCURRENCY_TEST'
                            )
                            """
                        ),
                        {"id": user_id},
                    ).scalar_one()
                )

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(lambda _: assign_default(), range(2)))

        with engine.connect() as verification:
            assignment_count = verification.execute(
                text(
                    """
                    select count(*)
                    from identity.user_role_assignments
                    where user_id = :id and revoked_at is null
                    """
                ),
                {"id": user_id},
            ).scalar_one()

        assert sorted(results) == [False, True]
        assert assignment_count == 1
    finally:
        with engine.begin() as cleanup:
            cleanup.execute(
                text("delete from identity.audit_events where target_user_id = :id"),
                {"id": user_id},
            )
            cleanup.execute(
                text("delete from auth.users where id = :id"),
                {"id": user_id},
            )
            cleanup.execute(
                text("delete from identity.audit_events where target_user_id = :id"),
                {"id": user_id},
            )
            cleanup.execute(
                text("delete from identity.users where id = :id"),
                {"id": user_id},
            )
        engine.dispose()


def test_concurrent_supabase_session_exchange_is_single_use() -> None:
    engine = _test_engine()
    user_id = uuid4()
    email = f"{user_id}@example.invalid"
    source_session_hash = os.urandom(32)
    session_ids: list[UUID] = []
    try:
        with engine.begin() as setup:
            if (
                setup.execute(
                    text("select to_regclass('identity.session_exchanges') is not null")
                ).scalar_one()
                is not True
            ):
                pytest.fail("PR #4 migration 0022 is not installed in the test database")
            _insert_auth_user(setup, user_id, email)
            for _ in range(2):
                session_ids.append(
                    setup.execute(
                        text(
                            """
                            insert into identity.auth_sessions (
                              user_id,
                              auth_version,
                              expires_at
                            )
                            values (:user_id, 1, now() + interval '1 hour')
                            returning sid
                            """
                        ),
                        {"user_id": user_id},
                    ).scalar_one()
                )

        def exchange(identity_session_id: UUID) -> bool:
            lock_key = int.from_bytes(
                source_session_hash[:8],
                byteorder="big",
                signed=True,
            )
            with engine.begin() as database_connection:
                database_connection.execute(
                    text("select pg_advisory_xact_lock(:lock_key)"),
                    {"lock_key": lock_key},
                )
                already_exchanged = database_connection.execute(
                    text(
                        """
                        select exists (
                          select 1
                          from identity.session_exchanges
                          where source_session_hash = :source_session_hash
                        )
                        """
                    ),
                    {"source_session_hash": source_session_hash},
                ).scalar_one()
                if already_exchanged:
                    return False
                database_connection.execute(
                    text(
                        """
                        insert into identity.session_exchanges (
                          source,
                          source_session_hash,
                          user_id,
                          identity_session_id,
                          source_authenticated_at,
                          source_expires_at
                        )
                        values (
                          'supabase',
                          :source_session_hash,
                          :user_id,
                          :identity_session_id,
                          now(),
                          now() + interval '1 hour'
                        )
                        """
                    ),
                    {
                        "source_session_hash": source_session_hash,
                        "user_id": user_id,
                        "identity_session_id": identity_session_id,
                    },
                )
                return True

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(exchange, session_ids))

        with engine.connect() as verification:
            exchange_count = verification.execute(
                text(
                    """
                    select count(*)
                    from identity.session_exchanges
                    where source_session_hash = :source_session_hash
                    """
                ),
                {"source_session_hash": source_session_hash},
            ).scalar_one()

        assert sorted(results) == [False, True]
        assert exchange_count == 1
    finally:
        with engine.begin() as cleanup:
            cleanup.execute(
                text(
                    """
                    delete from identity.session_exchanges
                    where source_session_hash = :source_session_hash
                    """
                ),
                {"source_session_hash": source_session_hash},
            )
            cleanup.execute(
                text("delete from identity.audit_events where target_user_id = :id"),
                {"id": user_id},
            )
            cleanup.execute(
                text("delete from auth.users where id = :id"),
                {"id": user_id},
            )
            cleanup.execute(
                text("delete from identity.audit_events where target_user_id = :id"),
                {"id": user_id},
            )
            cleanup.execute(
                text("delete from identity.users where id = :id"),
                {"id": user_id},
            )
        engine.dispose()


def test_manual_migration_repair_verifiers_accept_the_postgresql_schema(
    connection: Connection,
) -> None:
    migrations_directory = Path(__file__).parents[1] / "migrations"
    migrations = discover_migrations(migrations_directory)

    for migration in migrations:
        if migration.version in {"0021", "0022"}:
            verify_existing_migration(connection, migration)
