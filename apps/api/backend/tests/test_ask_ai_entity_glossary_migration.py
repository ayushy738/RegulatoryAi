from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from backend.core.migrations import apply_pending_migrations, discover_migrations
from backend.tests.ask_ai_postgres import POSTGRES_MARK

MIGRATIONS_DIR = Path(__file__).parents[1] / "migrations"
ENTITY_MIGRATION = MIGRATIONS_DIR / "0026_ask_ai_entity_glossary.sql"


def _normalized_sql(path: Path) -> str:
    return " ".join(path.read_text(encoding="utf-8").lower().split())


def _entity_parameters(
    canonical_id: str,
    canonical_name: str,
) -> dict[str, object]:
    return {
        "canonical_id": canonical_id,
        "canonical_name": canonical_name,
        "entity_class": "regulatory_concept",
        "jurisdiction": "India/Central",
        "workspace_priority": 50,
        "provenance_kind": "curated_catalog",
        "provenance_ref": f"agent-os:E3.3:{canonical_id}",
    }


INSERT_ENTITY_SQL = text(
    """
    insert into public.regulatory_entity_catalog (
      canonical_id,
      canonical_name,
      entity_class,
      jurisdiction,
      workspace_priority,
      provenance_kind,
      provenance_ref
    )
    values (
      :canonical_id,
      :canonical_name,
      :entity_class,
      :jurisdiction,
      :workspace_priority,
      :provenance_kind,
      :provenance_ref
    )
    """
)


def test_0026_is_additive_scoped_and_provenance_preserving() -> None:
    migrations = discover_migrations(MIGRATIONS_DIR)
    migration = next(
        candidate for candidate in migrations if candidate.version == "0026"
    )
    sql = _normalized_sql(ENTITY_MIGRATION)

    assert migration.filename == "0026_ask_ai_entity_glossary.sql"
    assert "create table public.regulatory_entity_catalog" in sql
    assert "create table public.regulatory_entity_aliases" in sql
    assert "create table public.regulatory_glossary_terms" in sql
    assert "normalized_alias" in sql
    assert "normalized_jurisdiction" in sql
    assert "provenance_kind" in sql
    assert "provenance_ref" in sql
    assert "enable row level security" in sql
    assert "grant select" in sql
    assert "drop table" not in sql
    assert "delete from" not in sql


@POSTGRES_MARK
def test_0026_applies_from_empty_schema_and_records_ledger(
    postgres_engine: Engine,
) -> None:
    applied = apply_pending_migrations(
        postgres_engine,
        MIGRATIONS_DIR,
        through="0026",
    )

    assert len(applied) == 26
    assert applied[-1].version == "0026"
    with postgres_engine.connect() as connection:
        assert connection.execute(
            text(
                """
                select count(*)
                from public.schema_migrations
                where version = '0026'
                  and filename = '0026_ask_ai_entity_glossary.sql'
                """
            )
        ).scalar_one() == 1
        assert connection.execute(
            text(
                """
                select count(*)
                from pg_class
                where oid in (
                  'public.regulatory_entity_catalog'::regclass,
                  'public.regulatory_entity_aliases'::regclass,
                  'public.regulatory_glossary_terms'::regclass
                )
                  and relrowsecurity
                """
            )
        ).scalar_one() == 3


@POSTGRES_MARK
def test_0026_upgrade_preserves_graph_and_enforces_scoped_aliases(
    postgres_engine: Engine,
) -> None:
    apply_pending_migrations(postgres_engine, MIGRATIONS_DIR, through="0025")
    with postgres_engine.begin() as connection:
        graph_entity_id = connection.execute(
            text(
                """
                insert into public.regulatory_graph_entities (
                  entity_type,
                  name,
                  canonical_name,
                  issuer,
                  confidence,
                  evidence
                )
                values (
                  'concept',
                  'legacy DSM',
                  'Deviation Settlement Mechanism',
                  'CERC',
                  0.900,
                  'legacy graph evidence'
                )
                returning entity_id
                """
            )
        ).scalar_one()

    apply_pending_migrations(postgres_engine, MIGRATIONS_DIR, through="0026")
    with postgres_engine.begin() as connection:
        graph_row = connection.execute(
            text(
                """
                select canonical_name, evidence
                from public.regulatory_graph_entities
                where entity_id = :entity_id
                """
            ),
            {"entity_id": graph_entity_id},
        ).one()
        connection.execute(
            INSERT_ENTITY_SQL,
            _entity_parameters(
                "test.arc.alpha",
                "Fixture Alpha Regulatory Code",
            ),
        )
        connection.execute(
            INSERT_ENTITY_SQL,
            _entity_parameters(
                "test.arc.beta",
                "Fixture Alternative Regulatory Code",
            ),
        )
        for canonical_id in ("test.arc.alpha", "test.arc.beta"):
            connection.execute(
                text(
                    """
                    insert into public.regulatory_entity_aliases (
                      canonical_id,
                      alias,
                      alias_kind,
                      jurisdiction,
                      provenance_kind,
                      provenance_ref
                    )
                    values (
                      :canonical_id,
                      'ARC',
                      'acronym',
                      'India/Central',
                      'curated_catalog',
                      :provenance_ref
                    )
                    """
                ),
                {
                    "canonical_id": canonical_id,
                    "provenance_ref": f"agent-os:E3.3:{canonical_id}",
                },
            )
        connection.execute(
            text(
                """
                insert into public.regulatory_glossary_terms (
                  canonical_id,
                  term,
                  definition,
                  jurisdiction,
                  provenance_kind,
                  provenance_ref
                )
                values (
                  'test.arc.alpha',
                  'Alpha code',
                  'Synthetic ambiguity fixture.',
                  'India/Central',
                  'curated_catalog',
                  'agent-os:E3.3:test.arc.alpha'
                )
                """
            )
        )

    assert graph_row == (
        "Deviation Settlement Mechanism",
        "legacy graph evidence",
    )
    with postgres_engine.connect() as connection:
        aliases = connection.execute(
            text(
                """
                select canonical_id, normalized_alias, normalized_jurisdiction
                from public.regulatory_entity_aliases
                order by canonical_id
                """
            )
        ).all()
        glossary = connection.execute(
            text(
                """
                select normalized_term, normalized_jurisdiction
                from public.regulatory_glossary_terms
                """
            )
        ).one()

    assert aliases == [
        ("test.arc.alpha", "arc", "india central"),
        ("test.arc.beta", "arc", "india central"),
    ]
    assert glossary == ("alpha code", "india central")

    with pytest.raises(IntegrityError):
        with postgres_engine.begin() as connection:
            connection.execute(
                text(
                    """
                    insert into public.regulatory_entity_aliases (
                      canonical_id,
                      alias,
                      alias_kind,
                      jurisdiction,
                      provenance_kind,
                      provenance_ref
                    )
                    values (
                      'test.arc.alpha',
                      '  arc  ',
                      'approved_alias',
                      '  INDIA/CENTRAL ',
                      'curated_catalog',
                      'agent-os:E3.3:duplicate'
                    )
                    """
                )
            )


@POSTGRES_MARK
def test_0026_catalog_is_authenticated_read_only(
    postgres_engine: Engine,
) -> None:
    apply_pending_migrations(postgres_engine, MIGRATIONS_DIR, through="0026")
    with postgres_engine.begin() as connection:
        connection.execute(
            INSERT_ENTITY_SQL,
            _entity_parameters("test.readable", "Readable Fixture Entity"),
        )

    with postgres_engine.begin() as connection:
        connection.exec_driver_sql("set local role authenticated")
        assert connection.execute(
            text("select canonical_id from public.regulatory_entity_catalog")
        ).scalar_one() == "test.readable"

    with pytest.raises(SQLAlchemyError):
        with postgres_engine.begin() as connection:
            connection.exec_driver_sql("set local role authenticated")
            connection.execute(
                INSERT_ENTITY_SQL,
                _entity_parameters("test.forbidden", "Forbidden Fixture Entity"),
            )

    with postgres_engine.connect() as connection:
        privileges = connection.execute(
            text(
                """
                select
                  has_table_privilege(
                    'authenticated',
                    'public.regulatory_entity_catalog',
                    'select'
                  ),
                  has_table_privilege(
                    'authenticated',
                    'public.regulatory_entity_catalog',
                    'insert'
                  ),
                  has_table_privilege(
                    'anon',
                    'public.regulatory_entity_catalog',
                    'select'
                  )
                """
            )
        ).one()
    assert privileges == (True, False, False)
