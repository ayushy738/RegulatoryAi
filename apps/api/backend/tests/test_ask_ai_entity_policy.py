from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from backend.ask.decision import (
    DECISION_POLICY_VERSION,
    ENTITY_ALIAS_CONFIDENCE,
    ENTITY_EXACT_CONFIDENCE,
    ENTITY_FAVORED_CONFIDENCE,
    ENTITY_FUZZY_CONFIDENCE,
    ENTITY_HIGH_RISK_CONFIDENCE,
    ENTITY_REINFORCED_CONFIDENCE,
    ENTITY_RESOLUTION_ORDER,
    ENTITY_UNRESOLVED_CONFIDENCE,
    EntityAlias,
    EntityAliasKind,
    EntityCatalogEntry,
    EntityResolutionRequest,
    EntityResolutionRisk,
    EntityResolutionStatus,
    resolve_entity,
)

CATALOG_PATH = Path(__file__).parent / "fixtures" / "ask_entity_resolution_catalog.json"
NAMED_FIXTURES = {
    "DSM": "in.central.dsm",
    "ABT": "in.central.abt",
    "REC": "in.central.rec",
    "RPO": "in.central.rpo",
    "CERC": "in.central.cerc",
    "MNRE": "in.central.mnre",
    "Green Hydrogen": "in.central.green-hydrogen-mission",
    "Tariff Policy": "in.central.tariff-policy-2016",
    "Electricity Act": "in.central.electricity-act-2003",
}


@pytest.fixture(scope="module")
def raw_catalog() -> dict[str, Any]:
    return json.loads(CATALOG_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def catalog(raw_catalog: dict[str, Any]) -> tuple[EntityCatalogEntry, ...]:
    return tuple(
        EntityCatalogEntry.model_validate(payload)
        for payload in raw_catalog["entities"]
    )


def test_catalog_fixture_is_versioned_and_covers_named_entities(
    raw_catalog: dict[str, Any],
    catalog: tuple[EntityCatalogEntry, ...],
) -> None:
    assert raw_catalog["schema_version"] == "1"
    assert raw_catalog["policy_version"] == DECISION_POLICY_VERSION
    assert tuple(entry.canonical_id for entry in catalog[:9]) == tuple(
        NAMED_FIXTURES.values()
    )
    assert ENTITY_RESOLUTION_ORDER == (
        "exact_canonical",
        "exact_alias",
        "exact_glossary",
        "interaction_context",
        "conversation_scope",
        "jurisdiction_context",
        "fuzzy_assumption",
        "clarification",
    )


@pytest.mark.parametrize(("mention", "canonical_id"), NAMED_FIXTURES.items())
def test_every_named_alias_resolves_with_exact_expansion(
    catalog: tuple[EntityCatalogEntry, ...],
    mention: str,
    canonical_id: str,
) -> None:
    result = resolve_entity(
        EntityResolutionRequest(
            mention=mention,
            active_jurisdiction="India/Central",
        ),
        catalog,
    )

    assert result.status is EntityResolutionStatus.RESOLVED
    assert result.match_rule == "exact_alias"
    assert result.selected is not None
    assert result.selected.canonical_id == canonical_id
    assert result.selected.confidence == ENTITY_ALIAS_CONFIDENCE
    assert result.selected.canonical_name in result.query_expansion
    assert mention in result.query_expansion
    assert result.direct_answer_allowed is True


def test_exact_identifier_and_title_are_certain(
    catalog: tuple[EntityCatalogEntry, ...],
) -> None:
    for mention in ("in.central.dsm", "Deviation Settlement Mechanism"):
        result = resolve_entity(
            EntityResolutionRequest(mention=mention),
            catalog,
        )
        assert result.match_rule == "exact_canonical"
        assert result.selected is not None
        assert result.selected.canonical_id == "in.central.dsm"
        assert result.selected.confidence == ENTITY_EXACT_CONFIDENCE


def test_glossary_requires_and_uses_jurisdiction_or_context_reinforcement(
    catalog: tuple[EntityCatalogEntry, ...],
) -> None:
    reinforced = resolve_entity(
        EntityResolutionRequest(
            mention="deviation settlement",
            active_jurisdiction="India/Central",
        ),
        catalog,
    )
    unreinforced = resolve_entity(
        EntityResolutionRequest(mention="deviation settlement"),
        catalog,
    )

    assert reinforced.match_rule == "exact_glossary"
    assert reinforced.selected is not None
    assert reinforced.selected.confidence == ENTITY_REINFORCED_CONFIDENCE
    assert unreinforced.match_rule == "exact_glossary"
    assert unreinforced.status is EntityResolutionStatus.ASSUMED
    assert unreinforced.selected is not None
    assert unreinforced.selected.confidence == ENTITY_FUZZY_CONFIDENCE


def test_interaction_context_precedes_conversation_scope(
    catalog: tuple[EntityCatalogEntry, ...],
) -> None:
    result = resolve_entity(
        EntityResolutionRequest(
            mention="it",
            interaction_entity_ids=("in.central.cerc",),
            conversation_entity_ids=("in.central.mnre",),
        ),
        catalog,
    )

    assert result.match_rule == "interaction_context"
    assert result.selected is not None
    assert result.selected.canonical_id == "in.central.cerc"
    assert result.selected.confidence == ENTITY_REINFORCED_CONFIDENCE
    assert result.selected.assumed is True


def test_conversation_scope_resolves_when_interaction_context_is_absent(
    catalog: tuple[EntityCatalogEntry, ...],
) -> None:
    result = resolve_entity(
        EntityResolutionRequest(
            mention="that regulator",
            conversation_entity_ids=("in.central.mnre",),
        ),
        catalog,
    )

    assert result.match_rule == "conversation_scope"
    assert result.selected is not None
    assert result.selected.canonical_id == "in.central.mnre"


def test_unique_fuzzy_candidate_is_visible_assumption(
    catalog: tuple[EntityCatalogEntry, ...],
) -> None:
    result = resolve_entity(
        EntityResolutionRequest(
            mention="Electricity Act 203",
            active_jurisdiction="India/Central",
        ),
        catalog,
    )

    assert result.status is EntityResolutionStatus.ASSUMED
    assert result.match_rule == "fuzzy_assumption"
    assert result.selected is not None
    assert result.selected.canonical_id == "in.central.electricity-act-2003"
    assert result.selected.confidence == ENTITY_FUZZY_CONFIDENCE
    assert result.selected.assumed is True


def test_material_acronym_ambiguity_produces_one_focused_clarification(
    catalog: tuple[EntityCatalogEntry, ...],
) -> None:
    result = resolve_entity(
        EntityResolutionRequest(
            mention="ARC",
            active_jurisdiction="India/Central",
        ),
        catalog,
    )

    assert result.status is EntityResolutionStatus.CLARIFICATION_REQUIRED
    assert result.match_rule == "clarification"
    assert result.selected is None
    assert len(result.candidates) == 2
    assert {candidate.confidence for candidate in result.candidates} == {
        ENTITY_UNRESOLVED_CONFIDENCE
    }
    assert result.clarification_question is not None
    assert result.clarification_question.count("?") == 1
    assert result.direct_answer_allowed is False


def test_workspace_dominance_is_bounded_and_visible(
    catalog: tuple[EntityCatalogEntry, ...],
) -> None:
    dominant = tuple(
        entry.model_copy(
            update={"workspace_priority": 80}
            if entry.canonical_id == "test.fixture.arc-alpha"
            else {}
        )
        for entry in catalog
    )
    result = resolve_entity(
        EntityResolutionRequest(
            mention="ARC",
            active_jurisdiction="India/Central",
        ),
        dominant,
    )

    assert result.status is EntityResolutionStatus.ASSUMED
    assert result.selected is not None
    assert result.selected.canonical_id == "test.fixture.arc-alpha"
    assert result.selected.confidence == ENTITY_FAVORED_CONFIDENCE
    assert len(result.candidates) == 2
    assert result.direct_answer_allowed is True


@pytest.mark.parametrize(
    "risk",
    [
        EntityResolutionRisk.OBLIGATION,
        EntityResolutionRisk.DEADLINE,
        EntityResolutionRisk.CURRENT_STATUS,
        EntityResolutionRisk.AMENDMENT,
    ],
)
def test_high_risk_topics_require_at_least_point_eighty_five(
    catalog: tuple[EntityCatalogEntry, ...],
    risk: EntityResolutionRisk,
) -> None:
    fuzzy = resolve_entity(
        EntityResolutionRequest(
            mention="Electricity Act 203",
            active_jurisdiction="India/Central",
            risk=risk,
        ),
        catalog,
    )
    exact = resolve_entity(
        EntityResolutionRequest(
            mention="Electricity Act",
            active_jurisdiction="India/Central",
            risk=risk,
        ),
        catalog,
    )

    assert fuzzy.required_confidence == ENTITY_HIGH_RISK_CONFIDENCE
    assert fuzzy.status is EntityResolutionStatus.CLARIFICATION_REQUIRED
    assert fuzzy.selected is not None
    assert fuzzy.selected.confidence == ENTITY_FUZZY_CONFIDENCE
    assert fuzzy.direct_answer_allowed is False
    assert exact.selected is not None
    assert exact.selected.confidence == ENTITY_ALIAS_CONFIDENCE
    assert exact.direct_answer_allowed is True


def test_incompatible_jurisdiction_fails_closed(
    catalog: tuple[EntityCatalogEntry, ...],
) -> None:
    result = resolve_entity(
        EntityResolutionRequest(
            mention="DSM",
            active_jurisdiction="United States/Federal",
        ),
        catalog,
    )

    assert result.status is EntityResolutionStatus.CLARIFICATION_REQUIRED
    assert result.direct_answer_allowed is False


def test_alias_scope_is_independent_from_parent_entity_scope(
    catalog: tuple[EntityCatalogEntry, ...],
) -> None:
    scoped_entry = catalog[0].model_copy(
        update={
            "aliases": (
                EntityAlias(
                    value="STATEONLY",
                    kind=EntityAliasKind.APPROVED_ALIAS,
                    jurisdiction="India/State",
                ),
            ),
            "jurisdiction": "India",
        }
    )

    incompatible = resolve_entity(
        EntityResolutionRequest(
            mention="STATEONLY",
            active_jurisdiction="India/Central",
        ),
        (scoped_entry,),
    )
    compatible = resolve_entity(
        EntityResolutionRequest(
            mention="STATEONLY",
            active_jurisdiction="India/State",
        ),
        (scoped_entry,),
    )

    assert incompatible.status is EntityResolutionStatus.CLARIFICATION_REQUIRED
    assert compatible.match_rule == "exact_alias"
    assert compatible.selected is not None
    assert compatible.selected.confidence == ENTITY_ALIAS_CONFIDENCE


def test_no_match_asks_for_entity_or_jurisdiction(
    catalog: tuple[EntityCatalogEntry, ...],
) -> None:
    result = resolve_entity(
        EntityResolutionRequest(mention="totally unknown regulatory term"),
        catalog,
    )

    assert result.status is EntityResolutionStatus.CLARIFICATION_REQUIRED
    assert result.candidates == ()
    assert result.clarification_question is not None
    assert "jurisdiction" in result.clarification_question


def test_resolution_is_deterministic_and_catalog_validation_fails_closed(
    catalog: tuple[EntityCatalogEntry, ...],
) -> None:
    request = EntityResolutionRequest(
        mention="DSM",
        active_jurisdiction="India/Central",
    )
    assert resolve_entity(request, catalog) == resolve_entity(request, catalog)
    with pytest.raises(ValueError, match="canonical IDs must be unique"):
        resolve_entity(request, (*catalog, catalog[0]))
    with pytest.raises(ValidationError, match="cannot be blank"):
        EntityResolutionRequest(mention="   ")
    with pytest.raises(ValidationError, match="must be unique"):
        EntityResolutionRequest(
            mention="it",
            interaction_entity_ids=("in.central.dsm", "in.central.dsm"),
        )
