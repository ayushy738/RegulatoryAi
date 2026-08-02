from __future__ import annotations

from pathlib import Path

from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.ask.entity_lookup import (
    EntityLookupRequest,
    EntityLookupService,
)
from backend.core.migrations import apply_pending_migrations
from backend.tests.ask_ai_postgres import POSTGRES_MARK

pytestmark = POSTGRES_MARK

MIGRATIONS_DIR = Path(__file__).parents[1] / "migrations"


def _seed_catalog(engine) -> None:
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                insert into public.regulatory_entity_catalog (
                  canonical_id,
                  canonical_name,
                  entity_class,
                  jurisdiction,
                  workspace_priority,
                  provenance_kind,
                  provenance_ref,
                  metadata
                )
                values
                  (
                    'in.central.dsm',
                    'Deviation Settlement Mechanism',
                    'regulatory_concept',
                    'India/Central',
                    90,
                    'curated_catalog',
                    'fixture:dsm',
                    '{"internal_note": "must not leak"}'::jsonb
                  ),
                  (
                    'test.arc-alpha',
                    'Alpha Regulatory Code',
                    'regulation_family',
                    'India/Central',
                    50,
                    'curated_catalog',
                    'fixture:arc-alpha',
                    '{}'::jsonb
                  ),
                  (
                    'test.arc-beta',
                    'Alternate Reliability Charge',
                    'market_or_commodity',
                    'India/Central',
                    50,
                    'curated_catalog',
                    'fixture:arc-beta',
                    '{}'::jsonb
                  )
                """
            )
        )
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
                values
                  (
                    'in.central.dsm', 'DSM', 'acronym', 'India/Central',
                    'curated_catalog', 'fixture:dsm'
                  ),
                  (
                    'in.central.dsm', 'Deviation Settlement',
                    'approved_alias', 'India/Central',
                    'curated_catalog', 'fixture:dsm'
                  ),
                  (
                    'test.arc-alpha', 'ARC', 'acronym', 'India/Central',
                    'curated_catalog', 'fixture:arc-alpha'
                  ),
                  (
                    'test.arc-beta', 'ARC', 'acronym', 'India/Central',
                    'curated_catalog', 'fixture:arc-beta'
                  )
                """
            )
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
                  'in.central.dsm',
                  'deviation settlement',
                  'A settlement mechanism.',
                  'India/Central',
                  'curated_catalog',
                  'fixture:dsm'
                )
                """
            )
        )


def _service(engine) -> EntityLookupService:
    return EntityLookupService(
        session_scope_factory=lambda: Session(engine),
    )


def test_catalog_lookup_resolves_dsm_and_exposes_only_public_read_model(
    postgres_engine,
) -> None:
    apply_pending_migrations(postgres_engine, MIGRATIONS_DIR, through="0032")
    _seed_catalog(postgres_engine)

    result = _service(postgres_engine).resolve(
        EntityLookupRequest(
            mention="DSM",
            active_jurisdiction="India/Central",
        )
    )

    assert result.status == "resolved"
    assert result.surface == "entity_intelligence_page"
    assert result.match_rule == "exact_alias"
    assert result.selected is not None
    assert result.selected.canonical_id == "in.central.dsm"
    assert result.selected.canonical_name == "Deviation Settlement Mechanism"
    assert result.selected.aliases == ("DSM", "Deviation Settlement")
    assert result.selected.confidence == 0.95
    assert result.selected.entity_route == "/ask?entity=in.central.dsm"
    payload = result.model_dump(mode="json")
    assert "provenance_ref" not in payload["selected"]
    assert "metadata" not in payload["selected"]


def test_material_alias_ambiguity_is_deterministic_and_requires_choice(
    postgres_engine,
) -> None:
    apply_pending_migrations(postgres_engine, MIGRATIONS_DIR, through="0032")
    _seed_catalog(postgres_engine)
    service = _service(postgres_engine)

    first = service.resolve(
        EntityLookupRequest(
            mention="ARC",
            active_jurisdiction="India/Central",
        )
    )
    second = service.resolve(
        EntityLookupRequest(
            mention="ARC",
            active_jurisdiction="India/Central",
        )
    )

    assert first == second
    assert first.status == "ambiguous"
    assert first.selected is None
    assert first.surface is None
    assert tuple(item.canonical_id for item in first.candidates) == (
        "test.arc-alpha",
        "test.arc-beta",
    )
    assert {item.confidence for item in first.candidates} == {0.49}
    assert first.clarification_question is not None
    assert first.clarification_question.count("?") == 1


def test_canonical_choice_resolves_exactly_and_unknown_is_no_match(
    postgres_engine,
) -> None:
    apply_pending_migrations(postgres_engine, MIGRATIONS_DIR, through="0032")
    _seed_catalog(postgres_engine)
    service = _service(postgres_engine)

    selected = service.resolve(
        EntityLookupRequest(mention="test.arc-beta")
    )
    unknown = service.resolve(
        EntityLookupRequest(mention="unknown regulatory object")
    )

    assert selected.status == "resolved"
    assert selected.selected is not None
    assert selected.selected.canonical_id == "test.arc-beta"
    assert selected.selected.confidence == 1.0
    assert unknown.status == "no_match"
    assert unknown.selected is None
    assert unknown.candidates == ()
    assert unknown.clarification_question is not None
    assert "jurisdiction" in unknown.clarification_question
