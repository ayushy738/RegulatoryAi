from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from backend.ask.decision.models import KnowledgeMode, ResponseStrategy
from backend.ask.orchestration.contracts import ProvenanceClass
from backend.ask.response_contracts import (
    RESPONSE_CONTRACT_POLICY_VERSION,
    CardActionDescriptor,
    CardActionState,
    CardActionType,
    CardRendering,
    ResponseCardEnvelope,
    ResponseCardType,
    StructuredResponseEnvelope,
)

CONTRACT_PATH = (
    Path(__file__).parent / "fixtures" / "ask_response_contract.json"
)


def _response() -> StructuredResponseEnvelope:
    return StructuredResponseEnvelope.model_validate_json(
        CONTRACT_PATH.read_text(encoding="utf-8")
    )


def test_shared_fixture_round_trips_exactly() -> None:
    raw = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))

    response = _response()

    assert response.model_dump(mode="json") == raw
    assert json.loads(response.model_dump_json()) == raw
    assert response.policy_version == RESPONSE_CONTRACT_POLICY_VERSION


def test_fixture_covers_every_frozen_card_type_and_unknown_fallback() -> None:
    response = _response()
    cards = tuple(card for section in response.sections for card in section.cards)
    known = {card.known_type for card in cards if card.known_type is not None}

    assert known == set(ResponseCardType)
    unknown = next(card for card in cards if card.known_type is None)
    assert unknown.card_type == "regulatory_heatmap"
    assert unknown.rendering is CardRendering.UNKNOWN_FALLBACK
    assert unknown.fallback_title == "Unsupported card"
    assert unknown.payload == {"regions": ["north", "south"]}


def test_frozen_response_strategy_and_action_taxonomies_are_complete() -> None:
    assert {item.value for item in ResponseStrategy} == {
        "definition_card",
        "entity_intelligence_page",
        "official_documents_overview",
        "deadline_cards_timeline",
        "stakeholder_cards",
        "comparison_table",
        "latest_intelligence",
        "timeline",
        "compliance_checklist",
        "executive_summary",
        "document_explanation",
        "amendment_cards",
        "consultation_deadline_cards",
        "conversation",
        "research_report",
    }
    assert {item.value for item in CardActionType} == {
        "inspect_evidence",
        "open_source",
        "save",
        "add_to_workspace",
        "compare",
        "open_entity",
        "ask_follow_up",
        "find_official_basis",
        "check_applicability",
        "add_to_tracker",
    }


@pytest.mark.parametrize("strategy", tuple(ResponseStrategy))
def test_every_response_strategy_has_a_structured_representation(
    strategy: ResponseStrategy,
) -> None:
    response = _response().model_copy(update={"response_strategy": strategy})

    validated = StructuredResponseEnvelope.model_validate(
        response.model_dump(mode="python"),
        strict=True,
    )

    assert validated.response_strategy is strategy


def test_section_and_card_order_are_contiguous_and_stable() -> None:
    response = _response()

    assert tuple(section.order for section in response.sections) == (0, 1, 2)
    assert tuple(card.order for card in response.sections[0].cards) == tuple(
        range(12)
    )
    assert tuple(card.order for card in response.sections[1].cards) == (0,)


@pytest.mark.parametrize(
    "mutation",
    [
        {"known_type": None},
        {"rendering": CardRendering.UNKNOWN_FALLBACK},
        {"fallback_title": "Unexpected fallback"},
    ],
)
def test_known_cards_require_exact_known_rendering_identity(
    mutation: dict[str, object],
) -> None:
    card = _response().sections[0].cards[0].model_copy(update=mutation)

    with pytest.raises(ValidationError):
        ResponseCardEnvelope.model_validate(
            card.model_dump(mode="python"),
            strict=True,
        )


@pytest.mark.parametrize(
    "mutation",
    [
        {"known_type": ResponseCardType.ANSWER_SUMMARY},
        {"rendering": CardRendering.KNOWN},
        {"fallback_title": None},
    ],
)
def test_unknown_cards_require_explicit_safe_fallback_identity(
    mutation: dict[str, object],
) -> None:
    card = _response().sections[0].cards[-1].model_copy(update=mutation)

    with pytest.raises(ValidationError):
        ResponseCardEnvelope.model_validate(
            card.model_dump(mode="python"),
            strict=True,
        )


def test_cards_cannot_cross_section_mode_provenance_or_references() -> None:
    response = _response()
    section = response.sections[0]
    first = section.cards[0]
    mutations = (
        first.model_copy(
            update={"knowledge_mode": KnowledgeMode.LIVE_INTELLIGENCE}
        ),
        first.model_copy(
            update={"provenance_class": ProvenanceClass.LIVE_WEB_SOURCES}
        ),
        first.model_copy(update={"claim_ids": ("unknown-claim",)}),
        first.model_copy(update={"source_ids": ("unknown-source",)}),
    )

    for card in mutations:
        changed = section.model_copy(
            update={"cards": (card, *section.cards[1:])}
        )
        invalid = response.model_copy(
            update={
                "sections": (
                    changed,
                    response.sections[1],
                    response.sections[2],
                )
            }
        )
        with pytest.raises(ValidationError):
            StructuredResponseEnvelope.model_validate(
                invalid.model_dump(mode="python"),
                strict=True,
            )


@pytest.mark.parametrize(
    "mutation",
    [
        {"state": CardActionState.AVAILABLE, "target": None},
        {
            "state": CardActionState.AVAILABLE,
            "target": "source-1",
            "disabled_reason_code": "DISABLED",
        },
        {
            "state": CardActionState.DISABLED,
            "target": "source-1",
            "disabled_reason_code": "DISABLED",
        },
        {
            "state": CardActionState.DISABLED,
            "target": None,
            "disabled_reason_code": "unsafe detail",
        },
    ],
)
def test_action_availability_never_implies_missing_functionality(
    mutation: dict[str, object],
) -> None:
    base = CardActionDescriptor(
        action=CardActionType.OPEN_SOURCE,
        state=CardActionState.AVAILABLE,
        target="source-1",
    )

    with pytest.raises(ValidationError):
        CardActionDescriptor.model_validate(
            base.model_copy(update=mutation).model_dump(mode="python"),
            strict=True,
        )


def test_duplicate_or_gapped_section_and_card_identity_is_refused() -> None:
    response = _response()
    official, live, general = response.sections
    duplicate_section = live.model_copy(
        update={"section_id": official.section_id}
    )
    duplicate_card = live.cards[0].model_copy(
        update={"card_id": official.cards[0].card_id}
    )
    bad_responses = (
        response.model_copy(
            update={
                "sections": (
                    official,
                    live.model_copy(update={"order": 3}),
                    general,
                )
            }
        ),
        response.model_copy(
            update={"sections": (official, duplicate_section, general)}
        ),
        response.model_copy(
            update={
                "sections": (
                    official,
                    live.model_copy(update={"cards": (duplicate_card,)}),
                    general,
                )
            }
        ),
        response.model_copy(
            update={
                "sections": (
                    official.model_copy(
                        update={
                            "cards": (
                                official.cards[0],
                                official.cards[1].model_copy(update={"order": 4}),
                                *official.cards[2:],
                            )
                        }
                    ),
                    live,
                    general,
                )
            }
        ),
    )

    for invalid in bad_responses:
        with pytest.raises(ValidationError):
            StructuredResponseEnvelope.model_validate(
                invalid.model_dump(mode="python"),
                strict=True,
            )


def test_card_payload_accepts_json_only_and_requires_content() -> None:
    card = _response().sections[0].cards[0]
    for payload in ({}, {"bad": float("nan")}, {"bad": ("tuple",)}):
        with pytest.raises(ValidationError):
            ResponseCardEnvelope.model_validate(
                card.model_copy(update={"payload": payload}).model_dump(
                    mode="python"
                ),
                strict=True,
            )


def test_contracts_reject_future_schema_extra_fields_and_mutation() -> None:
    raw = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    with pytest.raises(ValidationError):
        StructuredResponseEnvelope.model_validate(
            {**raw, "schema_version": "2"}
        )
    with pytest.raises(ValidationError):
        StructuredResponseEnvelope.model_validate(
            {**raw, "unexpected": True}
        )
    response = _response()
    with pytest.raises(ValidationError):
        response.compatibility_summary = "changed"


def test_compatibility_summary_is_present_without_legacy_rendering_behavior() -> None:
    response = _response()

    assert response.compatibility_summary == (
        "The filing obligation is in force. A related consultation is live, "
        "but official confirmation is pending."
    )
    assert not hasattr(response, "reply")
    assert not hasattr(response, "citations")
