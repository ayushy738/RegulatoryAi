from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from sqlalchemy import text

from backend.core.migrations import apply_pending_migrations, discover_migrations
from backend.tests.ask_ai_postgres import POSTGRES_MARK, insert_auth_user
from backend.tests.test_ask_ai_artifact_migration import _seed_artifact_graph

pytestmark = POSTGRES_MARK

MIGRATIONS_DIR = Path(__file__).parents[1] / "migrations"
SEARCH_MIGRATION = MIGRATIONS_DIR / "0030_ask_ai_session_search.sql"
MIGRATION_README = MIGRATIONS_DIR / "README.md"


def test_0030_is_ordered_additive_and_documents_flag_off_rollback() -> None:
    migrations = discover_migrations(MIGRATIONS_DIR)
    migration = next(item for item in migrations if item.version == "0030")
    sql = " ".join(SEARCH_MIGRATION.read_text(encoding="utf-8").lower().split())
    readme = " ".join(
        MIGRATION_README.read_text(encoding="utf-8").lower().split()
    )

    assert migration.filename == "0030_ask_ai_session_search.sql"
    assert migrations[migrations.index(migration) + 1].version == "0031"
    assert "add column" not in sql
    assert sql.count("using gin") == 3
    assert sql.count("to_tsvector('simple'") >= 3
    assert "rollback is flag-off" in readme
    assert "do not drop search indexes" in readme


def test_0030_applies_from_empty_with_expression_and_filter_indexes(
    postgres_engine,
) -> None:
    applied = apply_pending_migrations(
        postgres_engine,
        MIGRATIONS_DIR,
        through="0030",
    )

    assert applied[-1].version == "0030"
    with postgres_engine.connect() as connection:
        search_columns = {
            (row["table_name"], row["column_name"])
            for row in connection.execute(
                text(
                    """
                    select table_name, column_name, is_generated
                    from information_schema.columns
                    where table_schema = 'public'
                      and table_name in (
                        'chat_sessions',
                        'chat_messages',
                        'ask_sources'
                      )
                      and column_name = 'search_vector'
                    """
                )
            ).mappings()
        }
        indexes = {
            row["indexname"]
            for row in connection.execute(
                text(
                    """
                    select indexname
                    from pg_indexes
                    where schemaname = 'public'
                    """
                )
            ).mappings()
        }

    assert search_columns == set()
    assert {
        "chat_sessions_search_vector_idx",
        "chat_messages_search_vector_idx",
        "ask_sources_search_vector_idx",
        "ask_sections_session_mode_search_idx",
        "chat_sessions_entity_search_idx",
        "chat_sessions_active_search_cursor_idx",
        "chat_sessions_archived_search_cursor_idx",
    } <= indexes


def test_0030_populated_upgrade_preserves_content_and_builds_search_vectors(
    postgres_engine,
) -> None:
    apply_pending_migrations(postgres_engine, MIGRATIONS_DIR, through="0026")
    user_id = uuid4()
    with postgres_engine.begin() as connection:
        insert_auth_user(connection, user_id)
        graph = _seed_artifact_graph(connection, user_id=user_id)
        connection.execute(
            text(
                """
                update public.chat_sessions
                set title = 'Balancing reform', primary_entity = 'CERC'
                where id = :session_id
                """
            ),
            {"session_id": graph["session_id"]},
        )
        connection.execute(
            text(
                """
                update public.chat_messages
                set content = 'Explain deviation settlement'
                where session_id = :session_id and role = 'user'
                """
            ),
            {"session_id": graph["session_id"]},
        )
        connection.execute(
            text(
                """
                update public.ask_sources
                set title_snapshot = 'Grid Code Amendment'
                where id = :source_id
                """
            ),
            {"source_id": graph["official_source_id"]},
        )
    apply_pending_migrations(postgres_engine, MIGRATIONS_DIR, through="0029")

    apply_pending_migrations(postgres_engine, MIGRATIONS_DIR, through="0030")

    with postgres_engine.connect() as connection:
        retained = connection.execute(
            text(
                """
                select
                  cs.title,
                  cm.content,
                  src.title_snapshot,
                  (
                    setweight(to_tsvector('simple', coalesce(cs.title, '')), 'A')
                    || setweight(
                      to_tsvector('simple', coalesce(cs.primary_entity, '')),
                      'B'
                    )
                    || setweight(
                      to_tsvector('simple', coalesce(cs.primary_topic, '')),
                      'C'
                    )
                  ) @@ plainto_tsquery('simple', 'balancing') as title_match,
                  to_tsvector(
                    'simple',
                    coalesce(cm.content, '')
                  ) @@ plainto_tsquery('simple', 'deviation') as message_match,
                  (
                    setweight(
                      to_tsvector('simple', coalesce(src.title_snapshot, '')),
                      'A'
                    )
                    || setweight(
                      to_tsvector('simple', coalesce(src.issuer_snapshot, '')),
                      'B'
                    )
                    || setweight(
                      to_tsvector('simple', coalesce(src.publisher_snapshot, '')),
                      'B'
                    )
                    || setweight(
                      to_tsvector('simple', coalesce(src.evidence_snapshot, '')),
                      'C'
                    )
                    || setweight(
                      to_tsvector('simple', coalesce(src.locator_snapshot, '')),
                      'D'
                    )
                  ) @@ plainto_tsquery('simple', 'amendment') as source_match
                from public.chat_sessions cs
                join public.chat_messages cm
                  on cm.session_id = cs.id and cm.role = 'user'
                join public.ask_sources src on src.id = :source_id
                where cs.id = :session_id
                """
            ),
            {
                "session_id": graph["session_id"],
                "source_id": graph["official_source_id"],
            },
        ).mappings().one()

    assert retained["title"] == "Balancing reform"
    assert retained["content"] == "Explain deviation settlement"
    assert retained["title_snapshot"] == "Grid Code Amendment"
    assert retained["title_match"] is True
    assert retained["message_match"] is True
    assert retained["source_match"] is True


def test_0030_representative_full_text_plans_use_each_gin_index(
    postgres_engine,
) -> None:
    apply_pending_migrations(postgres_engine, MIGRATIONS_DIR, through="0030")
    statements = {
        "chat_sessions_search_vector_idx": """
          explain (costs off)
          select id from public.chat_sessions
          where (
            setweight(to_tsvector('simple', coalesce(title, '')), 'A')
            || setweight(
              to_tsvector('simple', coalesce(primary_entity, '')),
              'B'
            )
            || setweight(
              to_tsvector('simple', coalesce(primary_topic, '')),
              'C'
            )
          ) @@ plainto_tsquery('simple', 'grid')
        """,
        "chat_messages_search_vector_idx": """
          explain (costs off)
          select id from public.chat_messages
          where session_id is not null
            and to_tsvector(
              'simple',
              coalesce(content, '')
            ) @@ plainto_tsquery('simple', 'grid')
        """,
        "ask_sources_search_vector_idx": """
          explain (costs off)
          select id from public.ask_sources
          where (
            setweight(
              to_tsvector('simple', coalesce(title_snapshot, '')),
              'A'
            )
            || setweight(
              to_tsvector('simple', coalesce(issuer_snapshot, '')),
              'B'
            )
            || setweight(
              to_tsvector('simple', coalesce(publisher_snapshot, '')),
              'B'
            )
            || setweight(
              to_tsvector('simple', coalesce(evidence_snapshot, '')),
              'C'
            )
            || setweight(
              to_tsvector('simple', coalesce(locator_snapshot, '')),
              'D'
            )
          ) @@ plainto_tsquery('simple', 'grid')
        """,
    }

    with postgres_engine.begin() as connection:
        connection.execute(text("set local enable_seqscan = off"))
        plans = {
            index_name: "\n".join(
                str(row[0])
                for row in connection.execute(text(statement))
            )
            for index_name, statement in statements.items()
        }

    for index_name, plan in plans.items():
        assert index_name in plan
