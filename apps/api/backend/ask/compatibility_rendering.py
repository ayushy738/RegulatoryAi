from __future__ import annotations

import re
from datetime import date
from typing import Literal, Self

from pydantic import Field, field_validator, model_validator

from backend.ask.decision.models import KnowledgeMode
from backend.ask.orchestration.contracts import SectionTerminalState
from backend.ask.response_contracts import (
    CardRendering,
    ResponseCardType,
    ResponseContractModel,
    StructuredResponseEnvelope,
)

COMPATIBILITY_RENDER_SCHEMA_VERSION = "1"
COMPATIBILITY_RENDER_POLICY_VERSION = "ask-ai-compatibility-render-v1"
_SUPPORTED_STATUSES = frozenset({"supported", "verified"})
_CONTROL_CHARACTERS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


class CompatibilityCitationSnapshot(ResponseContractModel):
    citation_id: str = Field(min_length=1, max_length=200)
    claim_id: str = Field(min_length=1, max_length=200)
    source_id: str = Field(min_length=1, max_length=200)
    ordinal: int = Field(ge=0)
    source_class: Literal["official"] = "official"
    verification_status: Literal[
        "supported",
        "verified",
        "partially_supported",
        "contradictory",
        "unverifiable",
        "pending",
    ]
    document_id: int = Field(ge=1)
    title: str = Field(min_length=1, max_length=1_000)
    issuer: str | None = Field(default=None, max_length=1_000)
    issue_date: date | None = None
    source_url: str = Field(min_length=1, max_length=4_000)
    chunk_id: int | None = Field(default=None, ge=1)
    page_number: int | None = Field(default=None, ge=1)
    section_title: str | None = Field(default=None, max_length=1_000)
    evidence: str | None = Field(default=None, max_length=50_000)

    @field_validator(
        "citation_id",
        "claim_id",
        "source_id",
        "title",
        "source_url",
    )
    @classmethod
    def validate_required_text(cls, value: str) -> str:
        if _CONTROL_CHARACTERS.search(value):
            raise ValueError("Compatibility citation text cannot contain control characters")
        return value.strip()

    @field_validator("issuer", "section_title", "evidence")
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            return None
        if _CONTROL_CHARACTERS.search(normalized):
            raise ValueError("Compatibility citation text cannot contain control characters")
        return normalized

    @model_validator(mode="after")
    def validate_supported_evidence(self) -> Self:
        if self.verification_status in _SUPPORTED_STATUSES and self.evidence is None:
            raise ValueError("Verified compatibility citations require evidence")
        return self


class LegacyFlatCitation(ResponseContractModel):
    document_id: int
    title: str
    issuer: str | None = None
    issue_date: str | None = None
    source_url: str
    chunk_id: int | None = None
    page_number: int | None = None
    section_title: str | None = None
    evidence: str | None = None


class CompatibilityRenderRequest(ResponseContractModel):
    schema_version: Literal["1"] = COMPATIBILITY_RENDER_SCHEMA_VERSION
    policy_version: Literal[
        "ask-ai-compatibility-render-v1"
    ] = COMPATIBILITY_RENDER_POLICY_VERSION
    response: StructuredResponseEnvelope
    citation_snapshots: tuple[CompatibilityCitationSnapshot, ...] = ()

    @model_validator(mode="after")
    def validate_citation_identity(self) -> Self:
        citation_ids = tuple(item.citation_id for item in self.citation_snapshots)
        if len(citation_ids) != len(set(citation_ids)):
            raise ValueError("Compatibility citation IDs must be unique")

        modes_by_source: dict[str, set[KnowledgeMode]] = {}
        for section in self.response.sections:
            for source_id in section.source_ids:
                modes_by_source.setdefault(source_id, set()).add(section.knowledge_mode)
        if any(len(modes) != 1 for modes in modes_by_source.values()):
            raise ValueError("A source identity cannot cross compatibility provenance lanes")

        official_sources = {
            source_id
            for section in self.response.sections
            if section.knowledge_mode is KnowledgeMode.GROUNDED_REGULATORY
            for source_id in section.source_ids
        }
        official_claims = {
            claim_id
            for section in self.response.sections
            if section.knowledge_mode is KnowledgeMode.GROUNDED_REGULATORY
            for claim_id in section.claim_ids
        }
        for citation in self.citation_snapshots:
            if citation.source_id not in official_sources:
                raise ValueError(
                    "Compatibility citations must reference an official response source"
                )
            if citation.claim_id not in official_claims:
                raise ValueError(
                    "Compatibility citations must reference an official response claim"
                )

        identity_by_source: dict[str, tuple[object, ...]] = {}
        for citation in self.citation_snapshots:
            identity = _source_identity(citation)
            prior = identity_by_source.setdefault(citation.source_id, identity)
            if prior != identity:
                raise ValueError("Compatibility source identity cannot change across citations")
        return self


class CompatibilityRenderResult(ResponseContractModel):
    schema_version: Literal["1"] = COMPATIBILITY_RENDER_SCHEMA_VERSION
    policy_version: Literal[
        "ask-ai-compatibility-render-v1"
    ] = COMPATIBILITY_RENDER_POLICY_VERSION
    reply: str = Field(min_length=1, max_length=100_000)
    citations: tuple[LegacyFlatCitation, ...] = ()


def render_structured_response_compatibility(
    request: CompatibilityRenderRequest,
) -> CompatibilityRenderResult:
    safe = CompatibilityRenderRequest.model_validate_json(request.model_dump_json())
    citations = _flat_citations(safe)
    blocks = [safe.response.compatibility_summary]

    live_lines = _live_source_lines(safe.response)
    if live_lines:
        blocks.append(
            "Live Intelligence - not official regulatory evidence:\n"
            + "\n".join(f"- {line}" for line in live_lines)
        )
    if any(
        section.knowledge_mode is KnowledgeMode.GENERAL_AI
        for section in safe.response.sections
    ):
        blocks.append(
            "General AI Knowledge - educational context only; not official "
            "regulatory evidence."
        )

    limitations = _limitation_lines(safe.response)
    if limitations:
        blocks.append(
            "Coverage limitations:\n"
            + "\n".join(f"- {line}" for line in limitations)
        )
    if citations:
        blocks.append(
            "Citations:\n"
            + "\n".join(
                _citation_markdown(index, citation)
                for index, citation in enumerate(citations, start=1)
            )
        )

    return CompatibilityRenderResult(
        reply="\n\n".join(blocks),
        citations=citations,
    )


def _flat_citations(
    request: CompatibilityRenderRequest,
) -> tuple[LegacyFlatCitation, ...]:
    source_rank: dict[str, int] = {}
    for section in request.response.sections:
        if section.knowledge_mode is not KnowledgeMode.GROUNDED_REGULATORY:
            continue
        for source_id in section.source_ids:
            source_rank.setdefault(source_id, len(source_rank))

    ordered = sorted(
        (
            item
            for item in request.citation_snapshots
            if item.verification_status in _SUPPORTED_STATUSES
        ),
        key=lambda item: (source_rank[item.source_id], item.ordinal, item.citation_id),
    )
    output: list[LegacyFlatCitation] = []
    seen_sources: set[str] = set()
    for item in ordered:
        if item.source_id in seen_sources:
            continue
        seen_sources.add(item.source_id)
        output.append(
            LegacyFlatCitation(
                document_id=item.document_id,
                title=item.title,
                issuer=item.issuer,
                issue_date=item.issue_date.isoformat() if item.issue_date else None,
                source_url=item.source_url,
                chunk_id=item.chunk_id,
                page_number=item.page_number,
                section_title=item.section_title,
                evidence=item.evidence,
            )
        )
    return tuple(output)


def _live_source_lines(response: StructuredResponseEnvelope) -> tuple[str, ...]:
    output: list[str] = []
    for section in response.sections:
        if section.knowledge_mode is not KnowledgeMode.LIVE_INTELLIGENCE:
            continue
        for card in section.cards:
            if card.known_type is not ResponseCardType.LIVE_NEWS:
                continue
            live_source = card.payload["live_source"]
            assert isinstance(live_source, dict)
            headline = _single_line(card.payload["headline"])
            publisher = _single_line(live_source["publisher"])
            publication_at = _single_line(live_source["publication_at"])
            retrieved_at = _single_line(live_source["retrieved_at"])
            url = _single_line(live_source["url"])
            output.append(
                f"{headline} | {publisher} | published={publication_at} | "
                f"retrieved={retrieved_at} | {url}"
            )
    return tuple(output)


def _limitation_lines(response: StructuredResponseEnvelope) -> tuple[str, ...]:
    output: list[str] = []
    for section in response.sections:
        if section.state not in {
            SectionTerminalState.READY,
            SectionTerminalState.READY_WITHOUT_SYNTHESIS,
        }:
            detail = " ".join(_single_line(gap) for gap in section.gaps)
            suffix = f" {detail}" if detail else ""
            output.append(
                f"{_single_line(section.title)}: "
                f"{section.state.value.replace('_', ' ').capitalize()}.{suffix}"
            )
        for card in section.cards:
            if card.rendering is CardRendering.UNKNOWN_FALLBACK:
                output.append(
                    f"{_single_line(section.title)}: "
                    f"{_single_line(card.fallback_title or card.title)} is unavailable "
                    "in the legacy view."
                )
    return tuple(output)


def _citation_markdown(index: int, citation: LegacyFlatCitation) -> str:
    issuer = _single_line(citation.issuer or "Unknown issuer")
    issue_date = citation.issue_date or "Unknown date"
    chunk = citation.chunk_id if citation.chunk_id is not None else "graph"
    page = citation.page_number if citation.page_number is not None else "unknown"
    return (
        f"{index}. {_single_line(citation.title)} | {issuer} | {issue_date} | "
        f"{_single_line(citation.source_url)} | chunk={chunk}, page={page}"
    )


def _single_line(value: object) -> str:
    return " ".join(str(value).split())


def _source_identity(citation: CompatibilityCitationSnapshot) -> tuple[object, ...]:
    return (
        citation.document_id,
        citation.title,
        citation.issuer,
        citation.issue_date,
        citation.source_url,
        citation.chunk_id,
        citation.page_number,
        citation.section_title,
    )
