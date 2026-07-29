from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from backend.ask.models import AskResponseVersion, ChatMessage, ChatTurn
from backend.core.models import ChatResponse

LEGACY_INTENT_MAP = {
    "definition": "general",
    "entity_lookup": "semantic_search",
    "regulation_lookup": "regulation_lookup",
    "deadline": "deadline",
    "stakeholder": "stakeholder",
    "comparison": "comparison",
    "news": "semantic_search",
    "timeline": "semantic_search",
    "compliance_question": "obligation",
    "amendment": "amendment",
    "consultation": "consultation",
    "summarization": "summary",
    "document_explanation": "semantic_search",
    "general_question": "general",
    "multi_part_question": "semantic_search",
}


class LegacyCompatibilityError(ValueError):
    """The persisted v2 state cannot be represented by the legacy contract."""


def response_version_to_legacy(version: AskResponseVersion) -> ChatResponse:
    message = version.assistant_message
    run = version.run
    if message.role != "assistant" or message.status != "completed":
        raise LegacyCompatibilityError("Only completed assistant messages are compatible")
    if run.status != "completed":
        raise LegacyCompatibilityError("Only completed Ask runs are compatible")
    if message.response_version != version.response_version:
        raise LegacyCompatibilityError("Message and response versions do not match")
    if run.response_version != version.response_version:
        raise LegacyCompatibilityError("Run and response versions do not match")
    if not message.content.strip():
        raise LegacyCompatibilityError("A legacy reply cannot be blank")
    if not run.model or not run.model.strip():
        raise LegacyCompatibilityError("A legacy response requires a model")

    intent = _legacy_intent(run.decision_record)
    _validate_legacy_provenance(version)
    citations = _legacy_citations(version)
    related_questions = [
        followup.question
        for followup in run.followups
        if followup.action_type == "ask"
    ]
    return ChatResponse(
        reply=message.content,
        event_id=message.event_id,
        model=run.model,
        intent=intent,
        citations=citations,
        related_questions=related_questions,
    )


def turns_to_legacy_history(
    turns: Sequence[ChatTurn],
    *,
    event_id: int | None,
    limit: int = 20,
) -> list[dict[str, Any]]:
    if limit < 1:
        raise ValueError("Legacy history limit must be positive")
    messages: list[ChatMessage] = []
    seen_ids: set[int] = set()
    for turn in turns:
        for message in (turn.user_message, turn.assistant_message):
            if message is None or message.event_id != event_id:
                continue
            if message.id in seen_ids:
                raise LegacyCompatibilityError("Legacy history message IDs must be unique")
            seen_ids.add(message.id)
            messages.append(message)
    messages.sort(key=lambda message: (message.created_at, message.id), reverse=True)
    return [
        {
            "id": message.id,
            "event_id": message.event_id,
            "role": message.role,
            "content": message.content,
            "created_at": message.created_at,
        }
        for message in messages[:limit]
    ]


def _legacy_intent(decision_record: dict[str, Any]) -> str:
    intent_record = decision_record.get("intent")
    if not isinstance(intent_record, dict):
        raise LegacyCompatibilityError("A legacy response requires a persisted intent")
    primary = intent_record.get("primary")
    if not isinstance(primary, str) or primary not in LEGACY_INTENT_MAP:
        raise LegacyCompatibilityError("The persisted intent is not legacy-compatible")
    return LEGACY_INTENT_MAP[primary]


def _validate_legacy_provenance(version: AskResponseVersion) -> None:
    unsupported_sections = [
        section.knowledge_mode
        for section in version.run.sections
        if section.knowledge_mode not in {"official", "system"}
    ]
    if unsupported_sections:
        raise LegacyCompatibilityError(
            "The legacy response cannot preserve General AI or live provenance"
        )
    if any(source.source_class != "official" for source in version.run.sources):
        raise LegacyCompatibilityError(
            "The legacy response cannot preserve live-source provenance"
        )


def _legacy_citations(version: AskResponseVersion) -> list[dict[str, Any]]:
    source_by_id = {source.id: source for source in version.run.sources}
    source_order = {source.id: source.ordinal for source in version.run.sources}
    ordered = sorted(
        version.run.citations,
        key=lambda citation: (source_order.get(citation.source_id, 2**31), citation.ordinal),
    )
    citations: list[dict[str, Any]] = []
    seen_sources = set()
    for citation in ordered:
        source = source_by_id.get(citation.source_id)
        if source is None:
            raise LegacyCompatibilityError("A citation is missing its persisted source")
        if source.source_class != "official" or citation.source_class != "official":
            raise LegacyCompatibilityError("Only official citations are legacy-compatible")
        if source.document_id is None:
            raise LegacyCompatibilityError("An official citation requires a document ID")
        if source.id in seen_sources:
            continue
        seen_sources.add(source.id)
        page_number = source.metadata.get("page_number")
        section_title = source.metadata.get("section_title")
        citations.append(
            {
                "document_id": source.document_id,
                "title": source.title_snapshot,
                "issuer": source.issuer_snapshot,
                "issue_date": (
                    source.published_at.date().isoformat()
                    if source.published_at is not None
                    else None
                ),
                "source_url": source.url_snapshot,
                "chunk_id": source.chunk_id,
                "page_number": page_number if isinstance(page_number, int) else None,
                "section_title": (
                    section_title if isinstance(section_title, str) else None
                ),
                "evidence": citation.evidence_snapshot,
            }
        )
    return citations
