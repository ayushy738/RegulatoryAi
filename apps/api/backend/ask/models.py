from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal
from uuid import UUID

ChatMessageRole = Literal["user", "assistant"]
ChatMessageStatus = Literal["pending", "completed", "failed", "cancelled"]
AskFeedbackValue = Literal["helpful", "not_helpful"]
AskSavedItemType = Literal["source", "citation", "card", "entity", "document"]


@dataclass(frozen=True, slots=True)
class ChatSession:
    id: UUID
    user_id: UUID
    event_id: int | None
    title: str | None
    status: str
    primary_entity: str | None
    primary_topic: str | None
    scope_snapshot: dict[str, Any]
    knowledge_mode_summary: dict[str, Any]
    freshness_state: str | None
    is_pinned: bool
    archived_at: datetime | None
    deleted_at: datetime | None
    created_at: datetime
    updated_at: datetime
    last_message_at: datetime | None


@dataclass(frozen=True, slots=True)
class ChatMessage:
    id: int
    public_id: UUID
    session_id: UUID
    user_id: UUID
    event_id: int | None
    role: ChatMessageRole
    content: str
    created_at: datetime
    status: ChatMessageStatus = "completed"
    response_version: int | None = None
    reply_to_message_id: int | None = None
    parent_message_id: int | None = None


@dataclass(frozen=True, slots=True)
class TurnPlaceholder:
    session: ChatSession
    user_message: ChatMessage
    assistant_message: ChatMessage


@dataclass(frozen=True, slots=True)
class ChatSessionPage:
    items: tuple[ChatSession, ...]
    has_more: bool
    relevances: tuple[int, ...] = ()

    def __post_init__(self) -> None:
        if self.relevances and len(self.relevances) != len(self.items):
            raise ValueError("Session relevance values must align with items")


@dataclass(frozen=True, slots=True)
class AskSection:
    id: UUID
    response_version: int
    ordinal: int
    section_type: str
    status: str
    knowledge_mode: str
    provenance_label: str | None
    title: str | None
    plain_text: str | None
    content: dict[str, Any]
    card_schema_version: str
    model: str | None
    policy_version: str | None
    prompt_version: str | None
    required_disclosure: str | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class AskSource:
    id: UUID
    ordinal: int
    source_key: str
    source_class: str
    source_type: str
    document_id: int | None
    document_version_id: int | None
    chunk_id: int | None
    graph_reference: dict[str, Any] | None
    title_snapshot: str
    url_snapshot: str
    issuer_snapshot: str | None
    publisher_snapshot: str | None
    jurisdiction_snapshot: str | None
    published_at: datetime | None
    retrieved_at: datetime
    evidence_snapshot: str
    locator_snapshot: str | None
    content_hash: str | None
    metadata: dict[str, Any]
    created_at: datetime


@dataclass(frozen=True, slots=True)
class AskClaim:
    id: UUID
    section_id: UUID
    ordinal: int
    knowledge_mode: str
    claim_text: str
    is_material: bool
    support_status: str
    support_score: float | None
    model: str | None
    policy_version: str | None
    prompt_version: str | None
    required_disclosure: str | None
    verifier_model: str | None
    verifier_policy_version: str | None
    created_at: datetime


@dataclass(frozen=True, slots=True)
class AskCitation:
    id: UUID
    claim_id: UUID
    source_id: UUID
    ordinal: int
    claim_knowledge_mode: str
    source_class: str
    citation_kind: str
    marker: str | None
    evidence_snapshot: str
    locator_snapshot: str | None
    support_score: float | None
    verification_status: str
    verifier_model: str | None
    verifier_policy_version: str | None
    created_at: datetime


@dataclass(frozen=True, slots=True)
class AskFollowup:
    id: UUID
    ordinal: int
    label: str
    question: str
    action_type: str
    payload: dict[str, Any]
    created_at: datetime


@dataclass(frozen=True, slots=True)
class AskRun:
    id: UUID
    status: str
    knowledge_mode_summary: dict[str, Any]
    model: str | None
    policy_version: str | None
    prompt_version: str | None
    general_ai_disclosure: str | None
    safe_error_code: str | None
    safe_error_message: str | None
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime
    sections: tuple[AskSection, ...]
    sources: tuple[AskSource, ...]
    claims: tuple[AskClaim, ...]
    citations: tuple[AskCitation, ...]
    followups: tuple[AskFollowup, ...]
    response_version: int = 1
    decision_record: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class AskFeedback:
    id: UUID
    run_id: UUID
    session_id: UUID
    user_id: UUID
    response_version: int
    value: AskFeedbackValue
    reason_code: str | None
    comment: str | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class AskResponseVersion:
    response_version: int
    assistant_message: ChatMessage
    run: AskRun
    feedback: AskFeedback | None


@dataclass(frozen=True, slots=True)
class AskResponseLineage:
    user_message: ChatMessage
    versions: tuple[AskResponseVersion, ...]


@dataclass(frozen=True, slots=True)
class AskSavedItem:
    id: UUID
    session_id: UUID
    user_id: UUID
    item_type: AskSavedItemType
    target_key: str
    run_id: UUID | None
    response_version: int | None
    source_id: UUID | None
    citation_id: UUID | None
    section_id: UUID | None
    entity_id: str | None
    document_id: int | None
    label_snapshot: str
    metadata: dict[str, Any]
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class ChatTurn:
    anchor_id: int
    anchor_created_at: datetime
    user_message: ChatMessage | None
    assistant_message: ChatMessage | None
    run: AskRun | None


@dataclass(frozen=True, slots=True)
class ChatTurnPage:
    items: tuple[ChatTurn, ...]
    has_more: bool


@dataclass(frozen=True, slots=True)
class ChatSessionExport:
    session: ChatSession
    turns: tuple[ChatTurn, ...]
    saved_items: tuple[AskSavedItem, ...]
