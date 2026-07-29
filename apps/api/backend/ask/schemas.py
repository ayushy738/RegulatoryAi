from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from backend.ask.models import (
    AskFeedback,
    AskResponseVersion,
    AskRun,
    AskSavedItem,
    ChatMessage,
    ChatSession,
    ChatSessionExport,
    ChatTurn,
)


class AskSessionCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_id: int | None = Field(default=None, ge=1)
    title: str | None = Field(default=None, max_length=200)
    primary_entity: str | None = Field(default=None, max_length=200)
    primary_topic: str | None = Field(default=None, max_length=200)
    scope_snapshot: dict[str, Any] = Field(default_factory=dict)

    @field_validator("title", "primary_entity", "primary_topic")
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None


class AskSessionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1"] = "1"
    id: UUID
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

    @classmethod
    def from_domain(cls, session: ChatSession) -> Self:
        return cls(
            id=session.id,
            event_id=session.event_id,
            title=session.title,
            status=session.status,
            primary_entity=session.primary_entity,
            primary_topic=session.primary_topic,
            scope_snapshot=session.scope_snapshot,
            knowledge_mode_summary=session.knowledge_mode_summary,
            freshness_state=session.freshness_state,
            is_pinned=session.is_pinned,
            archived_at=session.archived_at,
            deleted_at=session.deleted_at,
            created_at=session.created_at,
            updated_at=session.updated_at,
            last_message_at=session.last_message_at,
        )


class AskSessionListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1"] = "1"
    items: list[AskSessionResponse]
    next_cursor: str | None


class AskSessionPatchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, max_length=200)
    is_pinned: bool | None = None

    @field_validator("title")
    @classmethod
    def normalize_title(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("title cannot be blank")
        return normalized

    @model_validator(mode="after")
    def require_change(self) -> AskSessionPatchRequest:
        if not self.model_fields_set:
            raise ValueError("At least one session change is required")
        if "title" in self.model_fields_set and self.title is None:
            raise ValueError("title cannot be null")
        if "is_pinned" in self.model_fields_set and self.is_pinned is None:
            raise ValueError("is_pinned cannot be null")
        return self


class AskMessageResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1"] = "1"
    id: UUID
    event_id: int | None
    role: Literal["user", "assistant"]
    content: str
    created_at: datetime

    @classmethod
    def from_domain(cls, message: ChatMessage) -> Self:
        return cls(
            id=message.public_id,
            event_id=message.event_id,
            role=message.role,
            content=message.content,
            created_at=message.created_at,
        )


class AskSectionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

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


class AskSourceResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

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


class AskClaimResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

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


class AskCitationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

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


class AskFollowupResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: UUID
    ordinal: int
    label: str
    question: str
    action_type: str
    payload: dict[str, Any]
    created_at: datetime


class AskRunResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    schema_version: Literal["1"] = "1"
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
    sections: list[AskSectionResponse]
    sources: list[AskSourceResponse]
    claims: list[AskClaimResponse]
    citations: list[AskCitationResponse]
    followups: list[AskFollowupResponse]

    @classmethod
    def from_domain(cls, run: AskRun) -> Self:
        return cls.model_validate(run)


class AskTurnResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1"] = "1"
    id: UUID
    user_message: AskMessageResponse | None
    assistant_message: AskMessageResponse | None
    run: AskRunResponse | None

    @classmethod
    def from_domain(cls, turn: ChatTurn) -> Self:
        anchor = turn.user_message or turn.assistant_message
        if anchor is None:
            raise ValueError("A persisted turn must contain at least one message")
        return cls(
            id=anchor.public_id,
            user_message=(
                AskMessageResponse.from_domain(turn.user_message)
                if turn.user_message is not None
                else None
            ),
            assistant_message=(
                AskMessageResponse.from_domain(turn.assistant_message)
                if turn.assistant_message is not None
                else None
            ),
            run=AskRunResponse.from_domain(turn.run) if turn.run is not None else None,
        )


class AskTurnListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1"] = "1"
    items: list[AskTurnResponse]
    next_cursor: str | None


AskFeedbackReason = Literal[
    "missing_source",
    "source_does_not_support_claim",
    "outdated",
    "too_general",
    "wrong_entity",
    "incorrect_interpretation",
]


class AskFeedbackRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: Literal["helpful", "not_helpful"]
    reason_code: AskFeedbackReason | None = None
    comment: str | None = Field(default=None, max_length=2000)

    @field_validator("comment")
    @classmethod
    def normalize_comment(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None


class AskFeedbackResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1"] = "1"
    id: UUID
    message_id: UUID
    run_id: UUID
    response_version: int
    value: Literal["helpful", "not_helpful"]
    reason_code: str | None
    comment: str | None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_domain(
        cls,
        feedback: AskFeedback,
        *,
        message_id: UUID,
    ) -> Self:
        return cls(
            id=feedback.id,
            message_id=message_id,
            run_id=feedback.run_id,
            response_version=feedback.response_version,
            value=feedback.value,
            reason_code=feedback.reason_code,
            comment=feedback.comment,
            created_at=feedback.created_at,
            updated_at=feedback.updated_at,
        )


class AskMessageEvidenceResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1"] = "1"
    message: AskMessageResponse
    response_version: int
    run: AskRunResponse
    feedback: AskFeedbackResponse | None

    @classmethod
    def from_domain(cls, version: AskResponseVersion) -> Self:
        message_id = version.assistant_message.public_id
        return cls(
            message=AskMessageResponse.from_domain(version.assistant_message),
            response_version=version.response_version,
            run=AskRunResponse.from_domain(version.run),
            feedback=(
                AskFeedbackResponse.from_domain(
                    version.feedback,
                    message_id=message_id,
                )
                if version.feedback is not None
                else None
            ),
        )


class AskMessageSourcesResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1"] = "1"
    message_id: UUID
    response_version: int
    sections: list[AskSectionResponse]
    sources: list[AskSourceResponse]
    claims: list[AskClaimResponse]
    citations: list[AskCitationResponse]

    @classmethod
    def from_domain(cls, version: AskResponseVersion) -> Self:
        return cls(
            message_id=version.assistant_message.public_id,
            response_version=version.response_version,
            sections=[AskSectionResponse.model_validate(item) for item in version.run.sections],
            sources=[AskSourceResponse.model_validate(item) for item in version.run.sources],
            claims=[AskClaimResponse.model_validate(item) for item in version.run.claims],
            citations=[
                AskCitationResponse.model_validate(item) for item in version.run.citations
            ],
        )


class AskSavedItemCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    item_type: Literal["source", "citation", "card", "entity", "document"]
    target_id: str = Field(min_length=1, max_length=200)

    @field_validator("target_id")
    @classmethod
    def normalize_target_id(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("target_id cannot be blank")
        return normalized


class AskSavedItemResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1"] = "1"
    id: UUID
    session_id: UUID
    item_type: Literal["source", "citation", "card", "entity", "document"]
    target_id: str
    run_id: UUID | None
    response_version: int | None
    label: str
    metadata: dict[str, Any]
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_domain(cls, item: AskSavedItem) -> Self:
        return cls(
            id=item.id,
            session_id=item.session_id,
            item_type=item.item_type,
            target_id=item.target_key,
            run_id=item.run_id,
            response_version=item.response_version,
            label=item.label_snapshot,
            metadata=item.metadata,
            created_at=item.created_at,
            updated_at=item.updated_at,
        )


class AskSavedItemListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1"] = "1"
    items: list[AskSavedItemResponse]


class AskSessionExportResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1"] = "1"
    session: AskSessionResponse
    turns: list[AskTurnResponse]
    saved_items: list[AskSavedItemResponse]

    @classmethod
    def from_domain(cls, exported: ChatSessionExport) -> Self:
        return cls(
            session=AskSessionResponse.from_domain(exported.session),
            turns=[AskTurnResponse.from_domain(turn) for turn in exported.turns],
            saved_items=[
                AskSavedItemResponse.from_domain(item)
                for item in exported.saved_items
            ],
        )
