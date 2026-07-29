from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from backend.ask.core_cards import (
    AnswerSummaryPayload,
    ConfidenceCoveragePayload,
    DefinitionPayload,
    OfficialSourcePayload,
    StructuredDateField,
    StructuredFieldState,
    StructuredTextField,
)
from backend.ask.response_contracts import ResponseCardEnvelope

CONTRACT_PATH = (
    Path(__file__).parent / "fixtures" / "ask_response_contract.json"
)


def _raw_response() -> dict[str, object]:
    return json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))


def _card(card_type: str, *, section: int = 0) -> dict[str, object]:
    response = _raw_response()
    sections = response["sections"]
    assert isinstance(sections, list)
    cards = sections[section]["cards"]
    return copy.deepcopy(
        next(card for card in cards if card["card_type"] == card_type)
    )


def _validate(card: dict[str, object]) -> ResponseCardEnvelope:
    return ResponseCardEnvelope.model_validate_json(json.dumps(card))


def test_shared_fixture_contains_every_strict_core_payload() -> None:
    models = {
        "answer_summary": AnswerSummaryPayload,
        "definition": DefinitionPayload,
        "official_source": OfficialSourcePayload,
        "confidence_coverage": ConfidenceCoveragePayload,
    }

    for card_type, model in models.items():
        card = _validate(_card(card_type))
        parsed = model.model_validate_json(json.dumps(card.payload))
        assert parsed.schema_version == "1"


@pytest.mark.parametrize(
    "card_type",
    (
        "answer_summary",
        "definition",
        "official_source",
        "confidence_coverage",
    ),
)
def test_core_cards_reject_the_old_generic_payload_shape(
    card_type: str,
) -> None:
    card = _card(card_type)
    card["payload"] = {"content": "Generic JSON is no longer sufficient."}

    with pytest.raises(ValidationError):
        _validate(card)


def test_structured_missing_fields_are_explicit_and_strict() -> None:
    missing_text = StructuredTextField(
        state=StructuredFieldState.NOT_ESTABLISHED,
        value=None,
    )
    missing_date = StructuredDateField(
        state=StructuredFieldState.NOT_ESTABLISHED,
        value=None,
    )

    assert missing_text.model_dump(mode="json") == {
        "state": "not_established",
        "value": None,
    }
    assert missing_date.model_dump(mode="json") == {
        "state": "not_established",
        "value": None,
    }
    for model, value in (
        (
            StructuredTextField,
            {"state": "not_established", "value": "hidden guess"},
        ),
        (
            StructuredTextField,
            {"state": "established", "value": None},
        ),
        (
            StructuredDateField,
            {"state": "established", "value": "2026-02-31"},
        ),
    ):
        with pytest.raises(ValidationError):
            model.model_validate(value, strict=True)


def test_summary_requires_confidence_exact_sources_and_partial_missing_state() -> None:
    valid = _card("answer_summary")
    cases = []

    missing_confidence = copy.deepcopy(valid)
    missing_confidence["confidence"] = None
    cases.append(missing_confidence)

    wrong_count = copy.deepcopy(valid)
    wrong_count["payload"]["source_count"] = 2
    cases.append(wrong_count)

    no_grounded_source = copy.deepcopy(valid)
    no_grounded_source["source_ids"] = []
    no_grounded_source["payload"]["source_count"] = 0
    cases.append(no_grounded_source)

    elevated = copy.deepcopy(valid)
    elevated["confidence"] = {
        "score": 40,
        "label": "high",
        "reasons": [],
    }
    cases.append(elevated)

    crossed_provenance = copy.deepcopy(valid)
    crossed_provenance["provenance_class"] = "general_ai_knowledge"
    cases.append(crossed_provenance)

    hidden_missing = copy.deepcopy(valid)
    hidden_missing["payload"]["why_it_matters"] = {
        "state": "not_established",
        "value": None,
    }
    cases.append(hidden_missing)

    for invalid in cases:
        with pytest.raises(ValidationError):
            _validate(invalid)

    partial = copy.deepcopy(hidden_missing)
    partial["state"] = "partial"
    assert _validate(partial).state.value == "partial"


def test_general_ai_summary_is_source_free() -> None:
    valid = _card("answer_summary", section=2)
    assert _validate(valid).source_ids == ()

    invalid = copy.deepcopy(valid)
    invalid["source_ids"] = ["source-fabricated"]
    invalid["payload"]["source_count"] = 1
    with pytest.raises(ValidationError):
        _validate(invalid)


def test_definition_provenance_matches_official_definition_availability() -> None:
    grounded = _card("definition")
    assert _validate(grounded).knowledge_mode.value == "grounded_regulatory"

    general = copy.deepcopy(grounded)
    general["knowledge_mode"] = "general_ai"
    general["provenance_class"] = "general_ai_knowledge"
    general["source_ids"] = []
    general["payload"]["official_definition"] = {
        "state": "not_established",
        "value": None,
    }
    general["payload"]["official_source_label"] = {
        "state": "not_established",
        "value": None,
    }
    general["confidence"] = {
        "score": 72,
        "label": "medium",
        "reasons": ["General AI is capped at Medium."],
    }
    assert _validate(general).source_ids == ()

    forged = copy.deepcopy(general)
    forged["payload"]["official_definition"] = {
        "state": "established",
        "value": "Unsupported official wording.",
    }
    with pytest.raises(ValidationError):
        _validate(forged)

    live = copy.deepcopy(general)
    live["knowledge_mode"] = "live_intelligence"
    live["provenance_class"] = "live_web_sources"
    with pytest.raises(ValidationError):
        _validate(live)


def test_official_source_requires_exact_lane_source_actions_and_targets() -> None:
    valid = _card("official_source")
    assert _validate(valid).source_ids == ("source-1",)

    wrong_lane = copy.deepcopy(valid)
    wrong_lane["knowledge_mode"] = "general_ai"
    wrong_lane["provenance_class"] = "general_ai_knowledge"

    wrong_source = copy.deepcopy(valid)
    wrong_source["source_ids"] = ["source-2"]

    missing_action = copy.deepcopy(valid)
    missing_action["actions"] = missing_action["actions"][:-1]

    wrong_target = copy.deepcopy(valid)
    wrong_target["actions"][0]["target"] = "source-2"

    for invalid in (wrong_lane, wrong_source, missing_action, wrong_target):
        with pytest.raises(ValidationError):
            _validate(invalid)


def test_official_source_partial_state_matches_missing_metadata() -> None:
    card = _card("official_source")
    card["payload"]["effective_date"] = {
        "state": "not_established",
        "value": None,
    }
    with pytest.raises(ValidationError):
        _validate(card)

    card["state"] = "partial"
    validated = _validate(card)
    assert validated.state.value == "partial"

    complete_but_partial = _card("official_source")
    complete_but_partial["state"] = "partial"
    with pytest.raises(ValidationError):
        _validate(complete_but_partial)


@pytest.mark.parametrize(
    "mutate",
    (
        lambda card: card["payload"].update(
            {"modes_used": ["grounded_regulatory", "live_intelligence"]}
        ),
        lambda card: card["payload"].update(
            {"official_documents_found": 1}
        ),
        lambda card: card["payload"]["reasons"][0].update(
            {"text": "Different explanation."}
        ),
        lambda card: card["confidence"].update(
            {"score": 62, "label": "high"}
        ),
        lambda card: card["payload"]["reasons"][0].update(
            {"text": "My hidden chain of thought supports this."}
        ),
        lambda card: card["actions"].append(
            {
                "action": "save",
                "state": "disabled",
                "target": None,
                "disabled_reason_code": "ACTION_NOT_IMPLEMENTED",
            }
        ),
    ),
)
def test_confidence_card_refuses_flattening_drift_and_introspection(
    mutate: object,
) -> None:
    card = _card("confidence_coverage")
    mutate(card)

    with pytest.raises(ValidationError):
        _validate(card)


def test_general_ai_confidence_has_no_source_or_corpus_claim() -> None:
    card = _card("confidence_coverage")
    card["knowledge_mode"] = "general_ai"
    card["provenance_class"] = "general_ai_knowledge"
    card["source_ids"] = []
    card["confidence"] = {
        "score": 74,
        "label": "medium",
        "reasons": ["General AI has no official evidence."],
    }
    card["payload"].update(
        {
            "modes_used": ["general_ai"],
            "coverage_percent": 0,
            "official_documents_found": 0,
            "reasons": [
                {
                    "kind": "evidence",
                    "text": "General AI has no official evidence.",
                }
            ],
            "corpus_freshness": {
                "state": "not_established",
                "value": None,
            },
        }
    )
    assert _validate(card).source_ids == ()

    card["confidence"]["label"] = "high"
    card["confidence"]["score"] = 90
    with pytest.raises(ValidationError):
        _validate(card)


def test_non_core_known_payload_remains_owned_by_later_e8_tasks() -> None:
    obligation = _card("obligation")
    obligation["payload"] = {"future_e8_3_field": "retained"}

    assert _validate(obligation).payload == {
        "future_e8_3_field": "retained"
    }
