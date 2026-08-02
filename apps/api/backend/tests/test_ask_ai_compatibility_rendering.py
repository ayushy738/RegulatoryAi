from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest
from pydantic import ValidationError

from backend.ask.compatibility_rendering import (
    CompatibilityCitationSnapshot,
    CompatibilityRenderRequest,
    render_structured_response_compatibility,
)
from backend.ask.response_contracts import StructuredResponseEnvelope

FIXTURE_DIR = Path(__file__).parent / "fixtures"
RESPONSE = StructuredResponseEnvelope.model_validate_json(
    (FIXTURE_DIR / "ask_response_contract.json").read_text(encoding="utf-8")
)
GOLDEN = json.loads(
    (FIXTURE_DIR / "ask_compatibility_rendering_golden.json").read_text(
        encoding="utf-8"
    )
)


def _citation(
    source_id: str,
    claim_id: str,
    *,
    ordinal: int,
    verification_status: str = "supported",
    citation_id: str | None = None,
) -> CompatibilityCitationSnapshot:
    if source_id == "source-1":
        values = {
            "document_id": 17,
            "title": "Regulatory Filing Instrument",
            "issue_date": date(2026, 6, 15),
            "source_url": "https://regulator.example/filing",
            "chunk_id": 101,
            "page_number": 4,
            "section_title": "Filing obligation",
            "evidence": "Every regulated entity must submit the prescribed filing.",
        }
    else:
        values = {
            "document_id": 18,
            "title": "Amending Filing Instrument",
            "issue_date": date(2026, 6, 1),
            "source_url": "https://regulator.example/amendment",
            "chunk_id": 202,
            "page_number": 2,
            "section_title": "Amending clause",
            "evidence": "Paragraph 4 is amended.",
        }
    return CompatibilityCitationSnapshot(
        citation_id=citation_id or f"citation-{source_id}-{ordinal}",
        claim_id=claim_id,
        source_id=source_id,
        ordinal=ordinal,
        verification_status=verification_status,  # type: ignore[arg-type]
        issuer="Central Regulatory Commission",
        **values,
    )


def _request(
    citations: tuple[CompatibilityCitationSnapshot, ...],
    *,
    response: StructuredResponseEnvelope = RESPONSE,
) -> CompatibilityRenderRequest:
    return CompatibilityRenderRequest(response=response, citation_snapshots=citations)


def test_structured_response_matches_legacy_reply_and_flat_citation_golden() -> None:
    request = _request(
        (
            _citation("source-2", "claim-2", ordinal=0),
            _citation("source-1", "claim-1", ordinal=1),
        )
    )

    result = render_structured_response_compatibility(request)

    assert result.model_dump(mode="json", exclude={"schema_version", "policy_version"}) == GOLDEN


def test_input_order_does_not_change_section_or_source_order() -> None:
    first = _citation("source-1", "claim-1", ordinal=9)
    second = _citation("source-2", "claim-2", ordinal=0)

    forward = render_structured_response_compatibility(_request((first, second)))
    reverse = render_structured_response_compatibility(_request((second, first)))

    assert forward == reverse
    assert [item.document_id for item in forward.citations] == [17, 18]


def test_only_verified_official_citations_enter_the_flat_list() -> None:
    supported = _citation("source-1", "claim-1", ordinal=0)
    pending = _citation(
        "source-2",
        "claim-2",
        ordinal=1,
        verification_status="pending",
    ).model_copy(update={"evidence": None})

    result = render_structured_response_compatibility(_request((pending, supported)))

    assert [item.document_id for item in result.citations] == [17]
    assert "Amending Filing Instrument |" not in result.reply


def test_repeated_verified_claims_deduplicate_by_stable_source_identity() -> None:
    first = _citation("source-1", "claim-1", ordinal=1, citation_id="citation-b")
    second = _citation("source-1", "claim-2", ordinal=0, citation_id="citation-a")

    result = render_structured_response_compatibility(_request((first, second)))

    assert len(result.citations) == 1
    assert result.reply.count("Regulatory Filing Instrument |") == 1


def test_source_identity_conflict_is_rejected_instead_of_silently_merged() -> None:
    first = _citation("source-1", "claim-1", ordinal=0)
    changed = _citation(
        "source-1",
        "claim-2",
        ordinal=1,
        citation_id="citation-conflict",
    ).model_copy(update={"source_url": "https://regulator.example/changed"})

    with pytest.raises(ValidationError, match="source identity cannot change"):
        _request((first, changed))


def test_citation_cannot_reference_a_live_or_unknown_response_identity() -> None:
    live = _citation("source-live", "claim-live", ordinal=0)
    unknown = _citation("source-missing", "claim-1", ordinal=0)

    with pytest.raises(ValidationError, match="official response source"):
        _request((live,))
    with pytest.raises(ValidationError, match="official response source"):
        _request((unknown,))


def test_source_identity_cannot_cross_official_and_live_sections() -> None:
    live = RESPONSE.sections[1].model_copy(
        update={"source_ids": ("source-live", "source-1")}
    )
    crossed = RESPONSE.model_copy(
        update={"sections": (RESPONSE.sections[0], live, RESPONSE.sections[2])}
    )

    with pytest.raises(ValidationError, match="cannot cross.*provenance lanes"):
        _request((_citation("source-1", "claim-1", ordinal=0),), response=crossed)


def test_verified_citation_requires_inspectable_evidence() -> None:
    values = _citation("source-1", "claim-1", ordinal=0).model_dump(mode="python")
    values["evidence"] = None

    with pytest.raises(ValidationError, match="require evidence"):
        CompatibilityCitationSnapshot.model_validate(values)


def test_duplicate_citation_identity_is_rejected() -> None:
    first = _citation("source-1", "claim-1", ordinal=0, citation_id="same")
    second = _citation("source-2", "claim-2", ordinal=1, citation_id="same")

    with pytest.raises(ValidationError, match="IDs must be unique"):
        _request((first, second))


def test_no_verified_citations_produces_no_false_citation_heading() -> None:
    pending = _citation(
        "source-1",
        "claim-1",
        ordinal=0,
        verification_status="pending",
    ).model_copy(update={"evidence": None})

    result = render_structured_response_compatibility(_request((pending,)))

    assert result.citations == ()
    assert "\n\nCitations:" not in result.reply


def test_renderer_does_not_mutate_the_versioned_structured_response() -> None:
    before = RESPONSE.model_dump_json()

    render_structured_response_compatibility(
        _request((_citation("source-1", "claim-1", ordinal=0),))
    )

    assert RESPONSE.model_dump_json() == before


def test_citation_control_characters_are_rejected() -> None:
    values = _citation("source-1", "claim-1", ordinal=0).model_dump(mode="python")
    values["title"] = "Unsafe\x00title"

    with pytest.raises(ValidationError, match="control characters"):
        CompatibilityCitationSnapshot.model_validate(values)
