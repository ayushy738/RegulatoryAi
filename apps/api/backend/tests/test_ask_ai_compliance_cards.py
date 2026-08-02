from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from backend.ask.response_contracts import ResponseCardEnvelope

FIXTURE = json.loads(
    (
        Path(__file__).parent
        / "fixtures"
        / "ask_response_contract.json"
    ).read_text(encoding="utf-8")
)


def _card(card_type: str) -> dict[str, object]:
    for section in FIXTURE["sections"]:
        for card in section["cards"]:
            if card["card_type"] == card_type:
                return copy.deepcopy(card)
    raise AssertionError(f"Missing card fixture: {card_type}")


def _validate(card: dict[str, object]) -> ResponseCardEnvelope:
    return ResponseCardEnvelope.model_validate_json(json.dumps(card))


@pytest.mark.parametrize("card_type", ["obligation", "deadline", "stakeholder"])
def test_shared_compliance_card_fixture_is_strict(card_type: str) -> None:
    assert _validate(_card(card_type)).card_type == card_type


def test_obligation_requires_complete_cited_fields_and_exact_actions() -> None:
    obligation = _card("obligation")
    parsed = _validate(obligation)
    assert parsed.confidence is not None
    assert parsed.actions[0].target == "citation-1"

    obligation["source_ids"] = ["crossed-source"]
    with pytest.raises(ValidationError, match="envelope references"):
        _validate(obligation)


def test_one_claim_can_have_multiple_distinct_official_sources() -> None:
    obligation = _card("obligation")
    obligation["source_ids"] = ["source-1", "source-2"]
    obligation["payload"]["evidence_references"].append(
        {
            "citation_id": "citation-2",
            "claim_id": "claim-1",
            "source_id": "source-2",
            "marker": "[2]",
            "locator": {"state": "established", "value": "section 8"},
        }
    )

    assert _validate(obligation).source_ids == ("source-1", "source-2")


def test_partial_obligation_names_missing_fields_and_cannot_be_high() -> None:
    obligation = _card("obligation")
    obligation["state"] = "partial"
    obligation["payload"]["trigger_or_scope"] = {
        "state": "not_established",
        "value": None,
    }
    obligation["confidence"] = {
        "score": 70,
        "label": "medium",
        "reasons": ["Scope remains unresolved."],
    }
    assert _validate(obligation).state.value == "partial"

    obligation["confidence"]["label"] = "high"
    with pytest.raises(ValidationError, match="High"):
        _validate(obligation)


def test_deadline_not_established_cannot_claim_date_or_evidence() -> None:
    deadline = _card("deadline")
    assert _validate(deadline).state.value == "not_established"

    deadline["payload"]["date"] = {
        "state": "established",
        "value": "2026-08-31",
    }
    with pytest.raises(ValidationError, match="Not-established"):
        _validate(deadline)


def test_deadline_tracking_must_remain_disabled_in_this_phase() -> None:
    deadline = _card("deadline")
    deadline["actions"][1] = {
        "action": "add_to_tracker",
        "state": "available",
        "target": "deadline-1",
        "disabled_reason_code": None,
    }
    with pytest.raises(ValidationError, match="tracking"):
        _validate(deadline)


def test_stakeholder_requires_coverage_regulations_and_entity_target() -> None:
    stakeholder = _card("stakeholder")
    assert _validate(stakeholder).actions[1].target == "entity-1"

    stakeholder["payload"]["evidence_coverage_percent"] = 0
    with pytest.raises(ValidationError, match="complete"):
        _validate(stakeholder)


def test_compliance_cards_refuse_general_ai_and_unknown_fields() -> None:
    obligation = _card("obligation")
    obligation["knowledge_mode"] = "general_ai"
    obligation["provenance_class"] = "general_ai_knowledge"
    with pytest.raises(ValidationError, match="grounded"):
        _validate(obligation)

    stakeholder = _card("stakeholder")
    stakeholder["payload"]["invented"] = True
    with pytest.raises(ValidationError, match="Invalid stakeholder"):
        _validate(stakeholder)
