from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from backend.ask.response_contracts import ResponseCardEnvelope

FIXTURE = json.loads(
    (Path(__file__).parent / "fixtures" / "ask_response_contract.json").read_text(
        encoding="utf-8"
    )
)


def _card(card_type: str) -> dict[str, object]:
    for section in FIXTURE["sections"]:
        for card in section["cards"]:
            if card["card_type"] == card_type:
                return copy.deepcopy(card)
    raise AssertionError(f"Missing card fixture: {card_type}")


def _validate(card: dict[str, object]) -> ResponseCardEnvelope:
    return ResponseCardEnvelope.model_validate_json(json.dumps(card))


@pytest.mark.parametrize(
    "card_type",
    ["timeline_event", "amendment", "comparison", "live_news", "related_regulation"],
)
def test_shared_change_card_fixture_is_strict(card_type: str) -> None:
    assert _validate(_card(card_type)).card_type == card_type


def test_timeline_event_requires_exact_origin_lane_and_evidence() -> None:
    timeline = _card("timeline_event")
    timeline["knowledge_mode"] = "live_intelligence"
    timeline["provenance_class"] = "live_web_sources"
    with pytest.raises(ValidationError, match="source lane"):
        _validate(timeline)

    timeline = _card("timeline_event")
    timeline["payload"]["official_evidence_references"] = []
    with pytest.raises(ValidationError, match="Invalid timeline_event"):
        _validate(timeline)


def test_live_timeline_event_uses_live_source_lane_and_action() -> None:
    timeline = _card("timeline_event")
    live = _card("live_news")
    timeline["knowledge_mode"] = "live_intelligence"
    timeline["provenance_class"] = "live_web_sources"
    timeline["claim_ids"] = ["claim-live"]
    timeline["source_ids"] = ["source-live"]
    timeline["actions"] = [
        {
            "action": "open_source",
            "state": "available",
            "target": live["payload"]["live_source"]["url"],
            "disabled_reason_code": None,
        }
    ]
    timeline["payload"]["origin"] = "live"
    timeline["payload"]["source_label"] = {
        "state": "established",
        "value": "Regulator Newsroom",
    }
    timeline["payload"]["official_evidence_references"] = []
    timeline["payload"]["live_source"] = copy.deepcopy(
        live["payload"]["live_source"]
    )

    assert _validate(timeline).provenance_class.value == "live_web_sources"


def test_amendment_partial_state_names_gap_and_retains_compare_identity() -> None:
    amendment = _card("amendment")
    parsed = _validate(amendment)
    assert parsed.state.value == "partial"
    assert parsed.actions[1].target == "source-1:source-2"

    amendment["confidence"]["label"] = "high"
    with pytest.raises(ValidationError, match="High"):
        _validate(amendment)


def test_comparison_sides_require_independent_citations() -> None:
    comparison = _card("comparison")
    assert _validate(comparison).state.value == "partial"

    dimension = comparison["payload"]["dimensions"][0]
    dimension["side_b"] = {"state": "established", "value": "Annual"}
    with pytest.raises(ValidationError, match="Invalid comparison"):
        _validate(comparison)

    comparison = _card("comparison")
    dimension = comparison["payload"]["dimensions"][0]
    dimension["side_b"] = {"state": "established", "value": "Annual"}
    dimension["side_b_evidence_references"] = copy.deepcopy(
        dimension["side_a_evidence_references"]
    )
    with pytest.raises(ValidationError, match="Invalid comparison"):
        _validate(comparison)


def test_live_news_requires_https_times_and_live_lane() -> None:
    live = _card("live_news")
    assert _validate(live).knowledge_mode.value == "live_intelligence"

    live["payload"]["live_source"]["url"] = "http://unsafe.example/item"
    with pytest.raises(ValidationError, match="Invalid live_news"):
        _validate(live)

    live = _card("live_news")
    live["knowledge_mode"] = "grounded_regulatory"
    live["provenance_class"] = "internal_regulatory_corpus"
    with pytest.raises(ValidationError, match="source lane"):
        _validate(live)


def test_related_regulation_requires_exact_entity_action_and_evidence() -> None:
    related = _card("related_regulation")
    assert _validate(related).actions[1].target == "entity-2"

    related["actions"][1]["target"] = "crossed-entity"
    with pytest.raises(ValidationError, match="evidence target"):
        _validate(related)


def test_change_cards_refuse_crossed_envelope_and_unknown_fields() -> None:
    timeline = _card("timeline_event")
    timeline["source_ids"] = ["crossed-source"]
    with pytest.raises(ValidationError, match="envelope references"):
        _validate(timeline)

    live = _card("live_news")
    live["payload"]["invented"] = True
    with pytest.raises(ValidationError, match="Invalid live_news"):
        _validate(live)
