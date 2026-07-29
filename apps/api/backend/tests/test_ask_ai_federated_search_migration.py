from __future__ import annotations

from pathlib import Path

from sqlalchemy import text

from backend.ask.federated_search import _SEARCH_SQL, SearchGroup
from backend.core.migrations import apply_pending_migrations, discover_migrations
from backend.tests.ask_ai_postgres import POSTGRES_MARK

pytestmark = POSTGRES_MARK

MIGRATIONS_DIR = Path(__file__).parents[1] / "migrations"
MIGRATION = MIGRATIONS_DIR / "0033_ask_ai_federated_search.sql"
README = MIGRATIONS_DIR / "README.md"

EXPECTED_INDEXES = {
    "regulatory_entity_catalog_federated_search_idx",
    "regulatory_entity_aliases_federated_search_idx",
    "documents_federated_search_idx",
    "document_families_federated_search_idx",
    "document_version_registry_federated_search_idx",
    "deadline_history_federated_search_idx",
}


def test_0033_is_ordered_index_only_and_documents_retained_rollback() -> None:
    migrations = discover_migrations(MIGRATIONS_DIR)
    migration = next(item for item in migrations if item.version == "0033")
    sql = " ".join(MIGRATION.read_text(encoding="utf-8").lower().split())
    readme = " ".join(README.read_text(encoding="utf-8").lower().split())

    assert migration.filename == "0033_ask_ai_federated_search.sql"
    assert migrations[migrations.index(migration) + 1].version == "0034"
    assert "create table" not in sql
    assert "add column" not in sql
    assert sql.count("using gin") == 6
    assert sql.count("to_tsvector('simple'") >= 6
    assert "rollback is flag-off" in readme
    assert "duplicate source-of-truth table" in readme


def test_0033_applies_from_populated_0032_without_changing_rows(
    postgres_engine,
) -> None:
    apply_pending_migrations(postgres_engine, MIGRATIONS_DIR, through="0032")
    with postgres_engine.begin() as connection:
        connection.execute(
            text(
                """
                insert into public.regulatory_entity_catalog (
                  canonical_id, canonical_name, entity_class, jurisdiction,
                  workspace_priority, provenance_kind, provenance_ref
                ) values (
                  'fixture.dsm', 'Deviation Settlement Mechanism',
                  'regulatory_concept', 'India/Central', 90,
                  'curated_catalog', 'fixture:dsm'
                )
                """
            )
        )
        document_id = connection.execute(
            text(
                """
                insert into public.documents (
                  url_hash, source_url, title, issuing_body, jurisdiction,
                  issue_date, doc_type
                ) values (
                  'fixture-federated-search', 'https://example.test/dsm',
                  'DSM Regulations', 'CERC', 'central', date '2026-01-01',
                  'REGULATION'
                ) returning id
                """
            )
        ).scalar_one()
        before = connection.execute(
            text(
                """
                select
                  (select count(*) from public.regulatory_entity_catalog)
                    entity_count,
                  (select count(*) from public.documents) document_count
                """
            )
        ).mappings().one()

    applied = apply_pending_migrations(
        postgres_engine,
        MIGRATIONS_DIR,
        through="0033",
    )

    assert applied[-1].version == "0033"
    with postgres_engine.connect() as connection:
        after = connection.execute(
            text(
                """
                select
                  (select count(*) from public.regulatory_entity_catalog)
                    entity_count,
                  (select count(*) from public.documents) document_count
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
                      and indexname like '%_federated_search_idx'
                    """
                )
            )
        }
        retained_title = connection.execute(
            text("select title from public.documents where id = :id"),
            {"id": document_id},
        ).scalar_one()

    assert dict(after) == dict(before)
    assert retained_title == "DSM Regulations"
    assert EXPECTED_INDEXES <= indexes


def test_0033_representative_plans_use_expression_indexes(
    postgres_engine,
) -> None:
    apply_pending_migrations(postgres_engine, MIGRATIONS_DIR, through="0033")
    statements = {
        "regulatory_entity_catalog_federated_search_idx": """
          select canonical_id from public.regulatory_entity_catalog
          where (
            setweight(to_tsvector('simple', coalesce(canonical_name, '')), 'A')
            || setweight(to_tsvector('simple', coalesce(entity_class, '')), 'B')
            || setweight(to_tsvector('simple', coalesce(jurisdiction, '')), 'B')
          ) @@ plainto_tsquery('simple', 'DSM')
        """,
        "documents_federated_search_idx": """
          select id from public.documents
          where (
            setweight(to_tsvector('simple', coalesce(title, '')), 'A')
            || setweight(to_tsvector('simple', coalesce(issuing_body, '')), 'B')
            || setweight(to_tsvector('simple', coalesce(doc_type, '')), 'B')
          ) @@ plainto_tsquery('simple', 'regulation')
        """,
        "deadline_history_federated_search_idx": """
          select deadline_id from public.deadline_history
          where (
            setweight(to_tsvector('simple', coalesce(deadline_type, '')), 'A')
            || setweight(to_tsvector('simple', coalesce(raw_date, '')), 'B')
            || setweight(to_tsvector('simple', coalesce(extracted_from, '')), 'C')
          ) @@ plainto_tsquery('simple', 'deadline')
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


def test_production_search_predicates_match_the_indexed_expressions() -> None:
    normalized_sql = {
        group: " ".join(statement.lower().split())
        for group, statement in _SEARCH_SQL.items()
    }
    expected_fragments = {
        SearchGroup.ENTITIES: (
            "setweight( to_tsvector('simple', "
            "coalesce(entity.canonical_name, '')), 'a' )"
        ),
        SearchGroup.OFFICIAL_REGULATIONS: (
            "setweight( to_tsvector('simple', "
            "coalesce(document.title, '')), 'a' )"
        ),
        SearchGroup.AMENDMENTS: (
            "setweight( to_tsvector('simple', "
            "coalesce(registry.version_label, '')), 'a' )"
        ),
        SearchGroup.DEADLINES: (
            "setweight( to_tsvector('simple', "
            "coalesce(deadline.deadline_type, '')), 'a' )"
        ),
        SearchGroup.PREVIOUS_RESEARCH: (
            "setweight( to_tsvector('simple', "
            "coalesce(session.title, '')), 'a' )"
        ),
    }
    for group, fragment in expected_fragments.items():
        assert fragment in normalized_sql[group]
