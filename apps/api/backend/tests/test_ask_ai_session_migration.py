from __future__ import annotations

from pathlib import Path
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.exc import IntegrityError, ProgrammingError

from backend.core.migrations import apply_pending_migrations, discover_migrations
from backend.tests.ask_ai_postgres import (
    POSTGRES_MARK,
    insert_auth_user,
)

MIGRATIONS_DIR = Path(__file__).parents[1] / "migrations"
SESSION_MIGRATION = MIGRATIONS_DIR / "0023_ask_ai_sessions.sql"
MIGRATION_README = MIGRATIONS_DIR / "README.md"

EXPECTED_SESSION_COLUMNS = {
    "id",
    "user_id",
    "event_id",
    "title",
    "status",
    "primary_entity",
    "primary_topic",
    "scope_snapshot",
    "knowledge_mode_summary",
    "freshness_state",
    "is_pinned",
    "archived_at",
    "deleted_at",
    "created_at",
    "updated_at",
    "last_message_at",
}

def _normalized_sql(path: Path) -> str:
    return " ".join(path.read_text(encoding="utf-8").lower().split())


def _insert_auth_user(connection: Connection, user_id: UUID) -> None:
    insert_auth_user(connection, user_id)


def test_0023_is_ordered_expand_only_and_documents_flag_rollback() -> None:
    migrations = discover_migrations(MIGRATIONS_DIR)
    session_migration = next(
        migration for migration in migrations if migration.version == "0023"
    )
    sql = _normalized_sql(SESSION_MIGRATION)
    readme = MIGRATION_README.read_text(encoding="utf-8").lower()

    assert session_migration.filename == "0023_ask_ai_sessions.sql"
    assert "create table public.chat_sessions" in sql
    assert "add column public_id uuid" in sql
    assert "add column session_id uuid" in sql
    assert "public_id uuid not null" not in sql
    assert "session_id uuid not null" not in sql
    assert "update public.chat_messages" not in sql
    assert "delete from public.chat_messages" not in sql
    assert "drop table" not in sql
    assert "drop column" not in sql
    assert "turn off all ask ai v2" in readme
    assert "leave the new table, nullable columns" in readme


@POSTGRES_MARK
def test_0023_applies_from_empty_schema_and_records_ledger(
    postgres_engine: Engine,
) -> None:
    applied = apply_pending_migrations(
        postgres_engine,
        MIGRATIONS_DIR,
        through="0023",
    )

    assert applied[-1].version == "0023"
    assert len(applied) == 23
    with postgres_engine.connect() as connection:
        assert connection.execute(
            text(
                """
                select count(*)
                from public.schema_migrations
                where version = '0023'
                  and filename = '0023_ask_ai_sessions.sql'
                """
            )
        ).scalar_one() == 1
        assert connection.execute(
            text("select to_regclass('public.chat_sessions') is not null")
        ).scalar_one() is True
        session_columns = set(
            connection.execute(
                text(
                    """
                    select column_name
                    from information_schema.columns
                    where table_schema = 'public'
                      and table_name = 'chat_sessions'
                    """
                )
            ).scalars()
        )
        message_expansion = dict(
            connection.execute(
                text(
                    """
                    select column_name, is_nullable
                    from information_schema.columns
                    where table_schema = 'public'
                      and table_name = 'chat_messages'
                      and column_name in ('public_id', 'session_id')
                    """
                )
            ).all()
        )
        session_rls = connection.execute(
            text(
                """
                select relrowsecurity
                from pg_class
                where oid = 'public.chat_sessions'::regclass
                """
            )
        ).scalar_one()
        owner_policy = connection.execute(
            text(
                """
                select count(*)
                from pg_policies
                where schemaname = 'public'
                  and tablename = 'chat_sessions'
                  and policyname = 'own_chat_sessions'
                  and roles = array['authenticated']::name[]
                """
            )
        ).scalar_one()
        session_privileges = connection.execute(
            text(
                """
                select
                  has_table_privilege(
                    'authenticated',
                    'public.chat_sessions',
                    'select,insert,update,delete'
                  ),
                  has_table_privilege('anon', 'public.chat_sessions', 'select'),
                  not exists (
                    select 1
                    from information_schema.table_privileges
                    where table_schema = 'public'
                      and table_name = 'chat_sessions'
                      and grantee = 'PUBLIC'
                  )
                """
            )
        ).one()

    assert session_columns == EXPECTED_SESSION_COLUMNS
    assert message_expansion == {"public_id": "YES", "session_id": "YES"}
    assert session_rls is True
    assert owner_policy == 1
    assert session_privileges == (True, False, True)


@POSTGRES_MARK
def test_0023_upgrades_0022_without_mutating_legacy_rows(
    postgres_engine: Engine,
) -> None:
    applied = apply_pending_migrations(
        postgres_engine,
        MIGRATIONS_DIR,
        through="0022",
    )
    assert applied[-1].version == "0022"

    owner_id = uuid4()
    with postgres_engine.begin() as connection:
        _insert_auth_user(connection, owner_id)
        legacy_id = connection.execute(
            text(
                """
                insert into public.chat_messages (user_id, role, content)
                values (:user_id, 'user', 'legacy question')
                returning id
                """
            ),
            {"user_id": owner_id},
        ).scalar_one()
        before = connection.execute(
            text(
                """
                select id, user_id, event_id, role, content, created_at
                from public.chat_messages
                where id = :message_id
                """
            ),
            {"message_id": legacy_id},
        ).one()

    assert [
        migration.version
        for migration in apply_pending_migrations(
            postgres_engine,
            MIGRATIONS_DIR,
            through="0023",
        )
    ] == ["0023"]

    with postgres_engine.connect() as connection:
        after = connection.execute(
            text(
                """
                select id, user_id, event_id, role, content, created_at
                from public.chat_messages
                where id = :message_id
                """
            ),
            {"message_id": legacy_id},
        ).one()
        expansion = connection.execute(
            text(
                """
                select public_id, session_id
                from public.chat_messages
                where id = :message_id
                """
            ),
            {"message_id": legacy_id},
        ).one()

    assert after == before
    assert expansion.public_id is None
    assert expansion.session_id is None


@POSTGRES_MARK
def test_0023_rls_and_linkage_enforce_session_ownership(
    postgres_engine: Engine,
) -> None:
    apply_pending_migrations(postgres_engine, MIGRATIONS_DIR)
    owner_id = uuid4()
    other_id = uuid4()

    with postgres_engine.begin() as connection:
        _insert_auth_user(connection, owner_id)
        _insert_auth_user(connection, other_id)

    with postgres_engine.begin() as connection:
        connection.execute(text("set local role authenticated"))
        connection.execute(
            text("select set_config('request.jwt.claim.sub', :owner_id, true)"),
            {"owner_id": str(owner_id)},
        )
        session_id = connection.execute(
            text(
                """
                insert into public.chat_sessions (user_id, title)
                values (:owner_id, 'Owner workspace')
                returning id
                """
            ),
            {"owner_id": owner_id},
        ).scalar_one()

    with postgres_engine.begin() as connection:
        connection.execute(text("set local role authenticated"))
        connection.execute(
            text("select set_config('request.jwt.claim.sub', :other_id, true)"),
            {"other_id": str(other_id)},
        )
        assert connection.execute(
            text("select count(*) from public.chat_sessions where id = :session_id"),
            {"session_id": session_id},
        ).scalar_one() == 0

    with postgres_engine.begin() as connection:
        connection.execute(text("set local role authenticated"))
        connection.execute(
            text("select set_config('request.jwt.claim.sub', :other_id, true)"),
            {"other_id": str(other_id)},
        )
        with pytest.raises(ProgrammingError):
            connection.execute(
                text(
                    """
                    insert into public.chat_sessions (user_id, title)
                    values (:owner_id, 'Cross-owner workspace')
                    """
                ),
                {"owner_id": owner_id},
            )

    with postgres_engine.begin() as connection:
        with pytest.raises(IntegrityError):
            connection.execute(
                text(
                    """
                    insert into public.chat_messages (
                      user_id,
                      role,
                      content,
                      session_id
                    )
                    values (:other_id, 'user', 'cross-owner link', :session_id)
                    """
                ),
                {"other_id": other_id, "session_id": session_id},
            )

    public_id = uuid4()
    with postgres_engine.begin() as connection:
        connection.execute(
            text(
                """
                insert into public.chat_messages (
                  public_id,
                  user_id,
                  role,
                  content,
                  session_id
                )
                values (:public_id, :owner_id, 'user', 'owned link', :session_id)
                """
            ),
            {
                "public_id": public_id,
                "owner_id": owner_id,
                "session_id": session_id,
            },
        )

    with postgres_engine.begin() as connection:
        with pytest.raises(IntegrityError):
            connection.execute(
                text(
                    """
                    insert into public.chat_messages (
                      public_id,
                      user_id,
                      role,
                      content
                    )
                    values (:public_id, :owner_id, 'assistant', 'duplicate identity')
                    """
                ),
                {"public_id": public_id, "owner_id": owner_id},
            )
