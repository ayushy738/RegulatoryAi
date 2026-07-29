from __future__ import annotations

import copy
import json
from collections.abc import Callable
from pathlib import Path

import pytest
from pydantic import ValidationError

from backend.ask.entity_page import EntityCorePageProjection

FIXTURE = (
    Path(__file__).parent / "fixtures" / "ask_response_contract.json"
)


def _card(card_type: str) -> dict[str, object]:
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    cards = fixture["sections"][0]["cards"]
    return copy.deepcopy(
        next(card for card in cards if card["card_type"] == card_type)
    )


def _source_card(
    *,
    card_id: str,
    source_id: str,
    title: str,
) -> dict[str, object]:
    card = _card("official_source")
    card["card_id"] = card_id
    card["title"] = title
    card["source_ids"] = [source_id]
    card["payload"]["source_id"] = source_id
    card["payload"]["document_title"] = title
    for action in card["actions"]:
        if action["action"] in {"open_source", "save"}:
            action["target"] = source_id
    return card


def _section(
    *,
    section_id: str,
    key: str,
    order: int,
    strategy: str,
    title: str,
    card: dict[str, object],
) -> dict[str, object]:
    card["order"] = 0
    return {
        "schema_version": "1",
        "section_id": section_id,
        "section_key": key,
        "order": order,
        "strategy": strategy,
        "title": title,
        "state": "ready",
        "knowledge_mode": card["knowledge_mode"],
        "provenance_class": card["provenance_class"],
        "confidence": {
            "score": 88,
            "label": "high",
            "reasons": ["Current official evidence supports this section."],
        },
        "claim_ids": card["claim_ids"],
        "source_ids": card["source_ids"],
        "assumptions": [],
        "gaps": [],
        "cards": [card],
    }


def _projection_payload() -> dict[str, object]:
    overview = _card("answer_summary")
    definition = _card("definition")
    regulation = _source_card(
        card_id="card-regulation",
        source_id="source-regulation",
        title="DSM Regulations",
    )
    document = _source_card(
        card_id="card-document",
        source_id="source-document",
        title="DSM Official Order",
    )
    confidence = _card("confidence_coverage")
    sections = [
        _section(
            section_id="entity-overview",
            key="overview",
            order=0,
            strategy="entity_intelligence_page",
            title="Overview",
            card=overview,
        ),
        _section(
            section_id="entity-definition",
            key="definition",
            order=1,
            strategy="definition_card",
            title="Definition",
            card=definition,
        ),
        _section(
            section_id="entity-regulations",
            key="official_regulations",
            order=2,
            strategy="official_documents_overview",
            title="Official Regulations",
            card=regulation,
        ),
        _section(
            section_id="entity-documents",
            key="official_documents",
            order=3,
            strategy="official_documents_overview",
            title="Official Documents",
            card=document,
        ),
        _section(
            section_id="entity-confidence",
            key="confidence",
            order=4,
            strategy="entity_intelligence_page",
            title="Confidence",
            card=confidence,
        ),
    ]
    return {
        "schema_version": "1",
        "policy_version": "ask-ai-entity-core-page-v1",
        "canonical_id": "dsm",
        "response": {
            "schema_version": "1",
            "policy_version": "ask-ai-response-contract-v1",
            "response_id": "entity-response-1",
            "response_strategy": "entity_intelligence_page",
            "sections": sections,
            "overall_confidence": {
                "score": 88,
                "label": "high",
                "reasons": ["Core entity evidence is strongly grounded."],
            },
            "compatibility_summary": "DSM core entity page.",
            "assumptions": [],
            "gaps": [],
        },
    }


def test_entity_core_projection_accepts_exact_five_slot_page() -> None:
    payload = _projection_payload()

    projection = EntityCorePageProjection.model_validate_json(
        json.dumps(payload)
    )

    assert projection.canonical_id == "dsm"
    assert tuple(
        section.section_key for section in projection.response.sections
    ) == (
        "overview",
        "definition",
        "official_regulations",
        "official_documents",
        "confidence",
    )


def test_entity_core_projection_allows_independent_partial_section() -> None:
    payload = _projection_payload()
    documents = payload["response"]["sections"][3]
    documents.update(
        {
            "state": "empty_by_evidence",
            "claim_ids": [],
            "source_ids": [],
            "gaps": ["Official documents were not established."],
            "cards": [],
        }
    )

    projection = EntityCorePageProjection.model_validate_json(
        json.dumps(payload)
    )

    assert projection.response.sections[3].state == "empty_by_evidence"
    assert projection.response.sections[2].state == "ready"


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (
            lambda payload: payload["response"].update(
                {"response_strategy": "research_report"}
            ),
            "entity intelligence strategy",
        ),
            (
                lambda payload: payload["response"]["sections"][1].update(
                    {"section_key": "entity_definition"}
                ),
                "canonical five-slot order",
            ),
        (
            lambda payload: payload["response"]["sections"][0]["cards"][0].update(
                {
                    "card_type": "definition",
                    "known_type": "definition",
                    "payload": _card("definition")["payload"],
                }
            ),
            "does not belong",
        ),
        (
            lambda payload: payload["response"]["sections"][0].update(
                {"cards": []}
            ),
            "require content",
        ),
        (
            lambda payload: payload["response"]["sections"][4].update(
                {
                    "knowledge_mode": "live_intelligence",
                    "provenance_class": "live_web_sources",
                    "cards": [],
                    "state": "degraded",
                }
            ),
            "live provenance",
        ),
    ],
)
def test_entity_core_projection_refuses_invalid_page_shapes(
    mutate: Callable[[dict[str, object]], object],
    message: str,
) -> None:
    payload = _projection_payload()
    mutate(payload)

    with pytest.raises(ValidationError, match=message):
        EntityCorePageProjection.model_validate_json(json.dumps(payload))


def test_entity_core_projection_is_strict() -> None:
    payload = _projection_payload()
    payload["unexpected"] = True

    with pytest.raises(ValidationError):
        EntityCorePageProjection.model_validate_json(json.dumps(payload))
