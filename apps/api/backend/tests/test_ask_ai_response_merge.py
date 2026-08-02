from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from backend.ask.response_contracts import (
    StructuredResponseEnvelope,
    StructuredResponseSection,
)
from backend.ask.response_merge import (
    MergeConflictKind,
    SectionMergeContribution,
    SectionMergeRequest,
    merge_response_sections,
)

FIXTURE_DIR = Path(__file__).parent / "fixtures"
RESPONSE = StructuredResponseEnvelope.model_validate_json(
    (FIXTURE_DIR / "ask_response_contract.json").read_text(encoding="utf-8")
)


def _contribution(
    section_index: int,
    *,
    contribution_id: str | None = None,
    question_id: str | None = None,
    question_order: int | None = None,
    blueprint_order: int | None = None,
) -> SectionMergeContribution:
    section = RESPONSE.sections[section_index]
    return SectionMergeContribution(
        contribution_id=contribution_id or f"contribution-{section_index}",
        atomic_question_id=question_id or f"question-{section_index}",
        atomic_question_order=(section_index if question_order is None else question_order),
        blueprint_order=(section.order if blueprint_order is None else blueprint_order),
        section=section,
    )


def _request(
    contributions: tuple[SectionMergeContribution, ...],
) -> SectionMergeRequest:
    return SectionMergeRequest(
        response_id="merged-response",
        response_strategy=RESPONSE.response_strategy,
        compatibility_summary=RESPONSE.compatibility_summary,
        overall_confidence=RESPONSE.overall_confidence,
        assumptions=RESPONSE.assumptions,
        gaps=RESPONSE.gaps,
        contributions=contributions,
    )


def _projection(result: object) -> dict[str, object]:
    response = result.response  # type: ignore[attr-defined]
    return {
        "section_keys": [item.section_key for item in response.sections],
        "section_modes": [item.knowledge_mode.value for item in response.sections],
        "section_states": [item.state.value for item in response.sections],
        "card_types": [
            [card.card_type for card in section.cards]
            for section in response.sections
        ],
        "card_counts": [len(section.cards) for section in response.sections],
        "exact_duplicate_count": result.exact_duplicate_count,  # type: ignore[attr-defined]
        "conflict_count": result.conflict_count,  # type: ignore[attr-defined]
        "conflict_kinds": [item.value for item in result.conflict_kinds],  # type: ignore[attr-defined]
    }


def test_merge_matches_recorded_golden_and_is_input_order_independent() -> None:
    contributions = tuple(_contribution(index) for index in range(3))
    forward = merge_response_sections(_request(contributions))
    reverse = merge_response_sections(_request(tuple(reversed(contributions))))
    golden = json.loads(
        (FIXTURE_DIR / "ask_response_merge_golden.json").read_text(encoding="utf-8")
    )

    assert _projection(forward) == golden
    assert forward.model_dump_json() == reverse.model_dump_json()


def test_exact_duplicate_cards_collapse_without_losing_section_references() -> None:
    first = _contribution(0, contribution_id="official-a", question_order=0)
    duplicate = _contribution(0, contribution_id="official-b", question_order=0)

    result = merge_response_sections(_request((duplicate, first)))

    assert len(result.response.sections) == 1
    assert len(result.response.sections[0].cards) == len(RESPONSE.sections[0].cards)
    assert result.exact_duplicate_count == len(RESPONSE.sections[0].cards)
    assert result.response.sections[0].claim_ids == RESPONSE.sections[0].claim_ids


def test_conflicting_card_identity_retains_both_variants_and_gap() -> None:
    first = _contribution(0, contribution_id="official-a", question_order=0)
    changed = RESPONSE.sections[0].model_dump(mode="json")
    changed["cards"][0]["title"] = "Conflicting summary title"
    second = SectionMergeContribution(
        contribution_id="official-b",
        atomic_question_id="question-0",
        atomic_question_order=0,
        blueprint_order=0,
        section=StructuredResponseSection.model_validate_json(json.dumps(changed)),
    )

    result = merge_response_sections(_request((first, second)))
    section = result.response.sections[0]

    assert len(section.cards) == len(RESPONSE.sections[0].cards) + 1
    assert len({item.card_id for item in section.cards}) == len(section.cards)
    assert MergeConflictKind.CARD_IDENTITY in result.conflict_kinds
    assert any("Conflicting card identities" in gap for gap in section.gaps)


def test_title_and_strategy_conflicts_are_explicit_and_weakest_state_wins() -> None:
    first = _contribution(0, contribution_id="official-a", question_order=0)
    changed = RESPONSE.sections[0].model_dump(mode="json")
    changed["title"] = "Alternative official findings"
    changed["strategy"] = "executive_summary"
    changed["state"] = "degraded"
    changed["confidence"] = {
        "score": 55,
        "label": "low",
        "reasons": ["One contribution is degraded."],
    }
    second = SectionMergeContribution(
        contribution_id="official-b",
        atomic_question_id="question-0",
        atomic_question_order=0,
        blueprint_order=0,
        section=StructuredResponseSection.model_validate_json(json.dumps(changed)),
    )

    result = merge_response_sections(_request((first, second)))
    section = result.response.sections[0]

    assert section.state.value == "degraded"
    assert section.confidence.label.value == "low"
    assert result.conflict_count == 2
    assert any("Conflicting section titles" in gap for gap in section.gaps)
    assert any("Conflicting section strategies" in gap for gap in section.gaps)


def test_multi_part_same_section_key_remains_independently_recoverable() -> None:
    first = _contribution(0, contribution_id="part-a", question_id="question-a", question_order=0)
    second = _contribution(0, contribution_id="part-b", question_id="question-b", question_order=1)

    result = merge_response_sections(_request((second, first)))

    assert len(result.response.sections) == 2
    assert len({item.section_key for item in result.response.sections}) == 2
    assert len({item.section_id for item in result.response.sections}) == 2
    assert all(
        item.section_key.startswith("official_findings--")
        for item in result.response.sections
    )


def test_same_logical_key_in_different_modes_remains_provenance_pure() -> None:
    official = _contribution(
        0,
        contribution_id="official",
        question_id="question",
        question_order=0,
    )
    live_data = RESPONSE.sections[1].model_dump(mode="json")
    live_data["section_key"] = "official_findings"
    live = SectionMergeContribution(
        contribution_id="live",
        atomic_question_id="question",
        atomic_question_order=0,
        blueprint_order=1,
        section=StructuredResponseSection.model_validate_json(json.dumps(live_data)),
    )

    result = merge_response_sections(_request((live, official)))

    assert [item.knowledge_mode.value for item in result.response.sections] == [
        "grounded_regulatory",
        "live_intelligence",
    ]
    assert all(
        all(card.provenance_class is section.provenance_class for card in section.cards)
        for section in result.response.sections
    )


def test_degraded_supporting_section_does_not_block_ready_section() -> None:
    official = _contribution(0, question_order=0)
    live = _contribution(1, question_order=1)

    result = merge_response_sections(_request((live, official)))

    assert result.response.sections[0].state.value == "ready"
    assert result.response.sections[1].state.value == "degraded"


def test_cancelled_same_section_support_preserves_ready_content_as_degraded() -> None:
    ready = _contribution(0, contribution_id="ready", question_order=0)
    cancelled_data = RESPONSE.sections[0].model_dump(mode="json")
    cancelled_data["state"] = "cancelled"
    cancelled = SectionMergeContribution(
        contribution_id="cancelled",
        atomic_question_id="question-0",
        atomic_question_order=0,
        blueprint_order=1,
        section=StructuredResponseSection.model_validate_json(
            json.dumps(cancelled_data)
        ),
    )

    result = merge_response_sections(_request((cancelled, ready)))
    section = result.response.sections[0]

    assert section.state.value == "degraded"
    assert len(section.cards) == len(RESPONSE.sections[0].cards)
    assert any("ready content was preserved" in gap for gap in section.gaps)


def test_identity_only_local_action_targets_do_not_defeat_exact_dedup() -> None:
    first = _contribution(0, contribution_id="first", question_order=0)
    changed = RESPONSE.sections[0].model_dump(mode="json")
    changed["section_id"] = "alternate-section-id"
    confidence = next(
        item for item in changed["cards"]
        if item["card_type"] == "confidence_coverage"
    )
    confidence["actions"][0]["target"] = "alternate-section-id"
    second = SectionMergeContribution(
        contribution_id="second",
        atomic_question_id="question-0",
        atomic_question_order=0,
        blueprint_order=0,
        section=StructuredResponseSection.model_validate_json(json.dumps(changed)),
    )

    result = merge_response_sections(_request((second, first)))

    assert result.exact_duplicate_count == len(RESPONSE.sections[0].cards)
    assert len(result.response.sections[0].cards) == len(RESPONSE.sections[0].cards)


def test_section_target_actions_are_rebound_to_stable_output_identity() -> None:
    result = merge_response_sections(_request((_contribution(0, question_order=0),)))
    section = result.response.sections[0]
    confidence_card = next(
        item for item in section.cards if item.card_type == "confidence_coverage"
    )

    assert confidence_card.actions[0].target == section.section_id


def test_duplicate_contribution_and_unstable_question_order_fail_closed() -> None:
    duplicate = _contribution(0, contribution_id="same", question_order=0)
    with pytest.raises(ValidationError, match="contribution IDs"):
        _request((duplicate, duplicate))

    first = _contribution(0, question_id="a", question_order=0)
    second = _contribution(1, question_id="b", question_order=2)
    with pytest.raises(ValidationError, match="contiguous"):
        _request((first, second))


def test_unknown_future_cards_survive_merge_through_fallback_contract() -> None:
    result = merge_response_sections(_request((_contribution(0, question_order=0),)))
    future = next(
        item for item in result.response.sections[0].cards
        if item.card_type == "regulatory_heatmap"
    )

    assert future.rendering.value == "unknown_fallback"
    assert future.payload == {"regions": ["north", "south"]}
