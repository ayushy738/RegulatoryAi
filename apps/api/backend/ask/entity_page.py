from __future__ import annotations

from enum import StrEnum
from typing import Literal, Self

from pydantic import Field, model_validator

from backend.ask.decision.models import KnowledgeMode, ResponseStrategy
from backend.ask.orchestration.contracts import SectionTerminalState
from backend.ask.response_contracts import (
    ResponseCardType,
    ResponseContractModel,
    StructuredResponseEnvelope,
    StructuredResponseSection,
)

ENTITY_CORE_PAGE_SCHEMA_VERSION = "1"
ENTITY_CORE_PAGE_POLICY_VERSION = "ask-ai-entity-core-page-v1"


class EntityCoreSectionKind(StrEnum):
    OVERVIEW = "overview"
    DEFINITION = "definition"
    OFFICIAL_REGULATIONS = "official_regulations"
    OFFICIAL_DOCUMENTS = "official_documents"
    CONFIDENCE = "confidence"


ENTITY_CORE_SECTION_ORDER = tuple(EntityCoreSectionKind)

_SECTION_TITLES = {
    EntityCoreSectionKind.OVERVIEW: "Overview",
    EntityCoreSectionKind.DEFINITION: "Definition",
    EntityCoreSectionKind.OFFICIAL_REGULATIONS: "Official Regulations",
    EntityCoreSectionKind.OFFICIAL_DOCUMENTS: "Official Documents",
    EntityCoreSectionKind.CONFIDENCE: "Confidence",
}
_SECTION_STRATEGIES = {
    EntityCoreSectionKind.OVERVIEW: ResponseStrategy.ENTITY_INTELLIGENCE_PAGE,
    EntityCoreSectionKind.DEFINITION: ResponseStrategy.DEFINITION_CARD,
    EntityCoreSectionKind.OFFICIAL_REGULATIONS: (
        ResponseStrategy.OFFICIAL_DOCUMENTS_OVERVIEW
    ),
    EntityCoreSectionKind.OFFICIAL_DOCUMENTS: (
        ResponseStrategy.OFFICIAL_DOCUMENTS_OVERVIEW
    ),
    EntityCoreSectionKind.CONFIDENCE: (
        ResponseStrategy.ENTITY_INTELLIGENCE_PAGE
    ),
}
_SECTION_CARD_TYPES = {
    EntityCoreSectionKind.OVERVIEW: ResponseCardType.ANSWER_SUMMARY,
    EntityCoreSectionKind.DEFINITION: ResponseCardType.DEFINITION,
    EntityCoreSectionKind.OFFICIAL_REGULATIONS: (
        ResponseCardType.OFFICIAL_SOURCE
    ),
    EntityCoreSectionKind.OFFICIAL_DOCUMENTS: ResponseCardType.OFFICIAL_SOURCE,
    EntityCoreSectionKind.CONFIDENCE: ResponseCardType.CONFIDENCE_COVERAGE,
}
_CONTENT_STATES = {
    SectionTerminalState.READY,
    SectionTerminalState.READY_WITHOUT_SYNTHESIS,
}
_EMPTY_STATES = {
    SectionTerminalState.EMPTY_BY_EVIDENCE,
    SectionTerminalState.OMITTED,
    SectionTerminalState.NEEDS_CLARIFICATION,
    SectionTerminalState.CANCELLED,
}


class EntityCorePageProjection(ResponseContractModel):
    schema_version: Literal["1"] = ENTITY_CORE_PAGE_SCHEMA_VERSION
    policy_version: Literal["ask-ai-entity-core-page-v1"] = (
        ENTITY_CORE_PAGE_POLICY_VERSION
    )
    canonical_id: str = Field(pattern=r"^[a-z0-9][a-z0-9._:-]{0,199}$")
    response: StructuredResponseEnvelope

    @model_validator(mode="after")
    def validate_page(self) -> Self:
        if (
            self.response.response_strategy
            is not ResponseStrategy.ENTITY_INTELLIGENCE_PAGE
        ):
            raise ValueError(
                "Entity core page requires the entity intelligence strategy"
            )
        actual_order = tuple(
            section.section_key for section in self.response.sections
        )
        if actual_order != tuple(item.value for item in ENTITY_CORE_SECTION_ORDER):
            raise ValueError(
                "Entity core sections require the canonical five-slot order"
            )
        for kind, section in zip(
            ENTITY_CORE_SECTION_ORDER,
            self.response.sections,
            strict=True,
        ):
            _validate_core_section(kind, section)
        return self


def _validate_core_section(
    kind: EntityCoreSectionKind,
    section: StructuredResponseSection,
) -> None:
    if section.title != _SECTION_TITLES[kind]:
        raise ValueError("Entity core section title does not match its slot")
    if section.strategy is not _SECTION_STRATEGIES[kind]:
        raise ValueError("Entity core section strategy does not match its slot")
    if section.knowledge_mode is KnowledgeMode.LIVE_INTELLIGENCE:
        raise ValueError("Entity core sections cannot introduce live provenance")

    expected_card_type = _SECTION_CARD_TYPES[kind]
    if any(card.known_type is not expected_card_type for card in section.cards):
        raise ValueError("Entity core card does not belong to its section")

    if section.state in _CONTENT_STATES and not section.cards:
        raise ValueError("Ready entity core sections require content")
    if section.state in _EMPTY_STATES and section.cards:
        raise ValueError("Non-content entity core sections cannot contain cards")
    if kind in {
        EntityCoreSectionKind.OVERVIEW,
        EntityCoreSectionKind.DEFINITION,
        EntityCoreSectionKind.CONFIDENCE,
    } and len(section.cards) > 1:
        raise ValueError("Singleton entity core sections permit at most one card")
