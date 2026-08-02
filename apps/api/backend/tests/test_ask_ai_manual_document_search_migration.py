from __future__ import annotations

from pathlib import Path

from sqlalchemy import text

from backend.ask.manual_document_search import _MANUAL_DOCUMENT_SEARCH_SQL
from backend.core.migrations import apply_pending_migrations, discover_migrations
from backend.tests.ask_ai_postgres import POSTGRES_MARK

pytestmark = POSTGRES_MARK

MIGRATIONS_DIR = Path(__file__).parents[1] / "migrations"
MIGRATION = MIGRATIONS_DIR / "0034_ask_ai_manual_document_search.sql"
README = MIGRATIONS_DIR / "README.md"

EXPECTED_INDEXES = {
    "document_version_registry_manual_effective_status_idx",
    "document_version_registry_manual_document_cursor_idx",
    "document_chunks_manual_document_version_page_idx",
}


def test_0034_is_ordered_index_only_and_retained_rollback() -> None:
    migrations = discover_migrations(MIGRATIONS_DIR)
    sql = " ".join(MIGRATION.read_text(encoding="utf-8").lower().split())
    readme = " ".join(README.read_text(encoding="utf-8").lower().split())

    assert migrations[-1].filename == "0034_ask_ai_manual_document_search.sql"
    assert "create table" not in sql
    assert "add column" not in sql
    assert sql.count("create index") == 3
    assert "rollback is flag-off" in readme
    assert "adds no search projection" in readme


def test_0034_applies_to_populated_0033_without_changing_source_rows(
    postgres_engine,
) -> None:
    apply_pending_migrations(postgres_engine, MIGRATIONS_DIR, through="0033")
    with postgres_engine.begin() as connection:
        document_id = connection.execute(
            text(
                """
                insert into public.documents (
                  url_hash, source_url, title, issuing_body, jurisdiction,
                  issue_date, doc_type
                ) values (
                  'manual-migration', 'https://example.test/manual',
                  'Manual Search Regulation', 'CERC', 'central',
                  date '2026-01-01', 'REGULATION'
                ) returning id
                """
            )
        ).scalar_one()
        version_id = connection.execute(
            text(
                """
                insert into public.document_versions (document_id, file_hash)
                values (:document_id, 'manual-version') returning id
                """
            ),
            {"document_id": document_id},
        ).scalar_one()
        family_id = connection.execute(
            text(
                """
                insert into public.document_families (
                  canonical_title, issuer, document_type
                ) values (
                  'Manual Search Regulation', 'CERC', 'REGULATION'
                ) returning family_id
                """
            )
        ).scalar_one()
        connection.execute(
            text(
                """
                insert into public.document_version_registry (
                  family_id, document_id, document_version_id,
                  publication_date, effective_date, version_label
                ) values (
                  :family_id, :document_id, :version_id,
                  date '2026-01-01', date '2026-02-01', 'Version 1'
                )
                """
            ),
            {
                "family_id": family_id,
                "document_id": document_id,
                "version_id": version_id,
            },
        )
        connection.execute(
            text(
                """
                insert into public.document_chunks (
                  document_id, version_id, family_id, chunk_index, text,
                  page_number, section_title
                ) values (
                  :document_id, :version_id, :family_id, 0,
                  'Manual search exact phrase fixture.', 2, 'Scope'
                )
                """
            ),
            {
                "document_id": document_id,
                "version_id": version_id,
                "family_id": family_id,
            },
        )
        before = connection.execute(
            text(
                """
                select
                  (select count(*) from public.documents) documents,
                  (select count(*) from public.document_version_registry)
                    versions,
                  (select count(*) from public.document_chunks) chunks
                """
            )
        ).mappings().one()

    applied = apply_pending_migrations(
        postgres_engine,
        MIGRATIONS_DIR,
        through="0034",
    )

    assert applied[-1].version == "0034"
    with postgres_engine.connect() as connection:
        after = connection.execute(
            text(
                """
                select
                  (select count(*) from public.documents) documents,
                  (select count(*) from public.document_version_registry)
                    versions,
                  (select count(*) from public.document_chunks) chunks
                """
            )
        ).mappings().one()
        indexes = {
            row[0]
            for row in connection.execute(
                text(
                    """
                    select indexname from pg_indexes
                    where schemaname = 'public'
                      and indexname like '%_manual_%_idx'
                    """
                )
            )
        }
    assert dict(after) == dict(before)
    assert EXPECTED_INDEXES <= indexes


def test_0034_representative_plans_use_manual_search_indexes(
    postgres_engine,
) -> None:
    apply_pending_migrations(postgres_engine, MIGRATIONS_DIR, through="0034")
    statements = {
        "document_version_registry_manual_effective_status_idx": """
          select registry_version_id
          from public.document_version_registry
          where effective_date >= date '2026-01-01'
          order by effective_date desc nulls last,
            superseded_by_registry_version_id,
            registry_version_id desc
        """,
        "document_version_registry_manual_document_cursor_idx": """
          select registry_version_id
          from public.document_version_registry
          where document_id = 1
          order by publication_date desc nulls last,
            registry_version_id desc
        """,
        "document_chunks_manual_document_version_page_idx": """
          select id from public.document_chunks
          where document_id = 1 and version_id = 1
          order by page_number nulls last, chunk_index, id
        """,
    }
    with postgres_engine.begin() as connection:
        connection.execute(text("set local enable_seqscan = off"))
        plans = {
            index: "\n".join(
                str(row[0])
                for row in connection.execute(
                    text(f"explain (costs off) {statement}")
                )
            )
            for index, statement in statements.items()
        }
    for index, plan in plans.items():
        assert index in plan


def test_production_manual_search_uses_canonical_indexed_lanes() -> None:
    sql = " ".join(_MANUAL_DOCUMENT_SEARCH_SQL.lower().split())

    assert (
        "setweight(to_tsvector('simple', "
        "coalesce(document.title, '')), 'a')" in sql
    )
    assert (
        "setweight(to_tsvector('simple', "
        "coalesce(family.canonical_title, '')), 'a')" in sql
    )
    assert (
        "setweight( to_tsvector('simple', "
        "coalesce(registry.version_label, '')), 'a' )" in sql
    )
    assert (
        "chunk.search_vector "
        "@@ websearch_to_tsquery('english', :query)" in sql
    )
    assert (
        "order by chunk.page_number nulls last, "
        "chunk.chunk_index, chunk.id" in sql
    )
