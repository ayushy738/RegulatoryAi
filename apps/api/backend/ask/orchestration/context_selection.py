from __future__ import annotations

import json
from datetime import datetime
from enum import StrEnum
from typing import Literal
from uuid import UUID

from pydantic import Field, field_validator, model_validator

from backend.ask.orchestration.contracts import ContractModel

CONTEXT_SELECTION_SCHEMA_VERSION = "1"
CONTEXT_SELECTION_POLICY_VERSION = "ask-ai-context-selection-v1"


class ContextTurnStatus(StrEnum):
    COMPLETED = "completed"
    INCOMPLETE = "incomplete"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ContextMessageRole(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"


class ConversationContextCandidate(ContractModel):
    schema_version: Literal["1"] = CONTEXT_SELECTION_SCHEMA_VERSION
    turn_id: UUID
    session_id: UUID
    user_id: UUID
    anchor_id: int = Field(gt=0)
    user_created_at: datetime
    assistant_created_at: datetime
    user_content: str = Field(min_length=1)
    assistant_content: str = Field(min_length=1)
    status: ContextTurnStatus = ContextTurnStatus.COMPLETED
    context_keys: tuple[str, ...] = ()
    inheritance_eligible: bool = True

    @field_validator("context_keys")
    @classmethod
    def normalize_context_keys(
        cls,
        values: tuple[str, ...],
    ) -> tuple[str, ...]:
        normalized = tuple(_normalize_key(value) for value in values)
        if any(not value for value in normalized):
            raise ValueError("Context keys cannot be blank")
        if len(set(normalized)) != len(normalized):
            raise ValueError("Context keys must be unique after normalization")
        return normalized

    @model_validator(mode="after")
    def validate_times(self) -> ConversationContextCandidate:
        _require_aware(self.user_created_at)
        _require_aware(self.assistant_created_at)
        if self.assistant_created_at < self.user_created_at:
            raise ValueError("Assistant context cannot precede its user message")
        return self


class ConversationContextRequest(ContractModel):
    schema_version: Literal["1"] = CONTEXT_SELECTION_SCHEMA_VERSION
    policy_version: str = Field(
        default=CONTEXT_SELECTION_POLICY_VERSION,
        min_length=1,
    )
    session_id: UUID
    user_id: UUID
    candidates: tuple[ConversationContextCandidate, ...]
    relevance_keys: tuple[str, ...] = ()
    max_turns: int = Field(default=8, ge=1, le=32)
    requires_immediate_context: bool = False
    reset_context: bool = False

    @field_validator("relevance_keys")
    @classmethod
    def normalize_relevance_keys(
        cls,
        values: tuple[str, ...],
    ) -> tuple[str, ...]:
        normalized = tuple(_normalize_key(value) for value in values)
        if any(not value for value in normalized):
            raise ValueError("Relevance keys cannot be blank")
        if len(set(normalized)) != len(normalized):
            raise ValueError("Relevance keys must be unique after normalization")
        return normalized

    @model_validator(mode="after")
    def validate_candidates(self) -> ConversationContextRequest:
        turn_ids = tuple(candidate.turn_id for candidate in self.candidates)
        if len(set(turn_ids)) != len(turn_ids):
            raise ValueError("Conversation context candidate IDs must be unique")
        owner_anchors = tuple(
            (
                candidate.session_id,
                candidate.user_id,
                candidate.anchor_id,
            )
            for candidate in self.candidates
        )
        if len(set(owner_anchors)) != len(owner_anchors):
            raise ValueError("Conversation context anchors must be unique")
        if self.reset_context and self.requires_immediate_context:
            raise ValueError("A context reset cannot require the prior turn")
        return self


class SelectedContextMessage(ContractModel):
    source_turn_id: UUID
    role: ContextMessageRole
    content: str = Field(min_length=1)
    created_at: datetime

    @model_validator(mode="after")
    def validate_time(self) -> SelectedContextMessage:
        _require_aware(self.created_at)
        return self


class ConversationContextSelection(ContractModel):
    schema_version: Literal["1"] = CONTEXT_SELECTION_SCHEMA_VERSION
    policy_version: str = Field(
        default=CONTEXT_SELECTION_POLICY_VERSION,
        min_length=1,
    )
    session_id: UUID
    user_id: UUID
    selected_turn_ids: tuple[UUID, ...]
    messages: tuple[SelectedContextMessage, ...]
    reset_applied: bool
    fact_authority: Literal["none"] = "none"
    requires_fresh_retrieval: Literal[True] = True
    candidate_count: int = Field(ge=0)
    excluded_wrong_owner_or_session_count: int = Field(ge=0)
    excluded_noncompleted_count: int = Field(ge=0)
    excluded_inheritance_count: int = Field(ge=0)
    excluded_irrelevant_count: int = Field(ge=0)
    truncated_relevant_count: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_selection(self) -> ConversationContextSelection:
        if len(set(self.selected_turn_ids)) != len(self.selected_turn_ids):
            raise ValueError("Selected context turn identities must be unique")
        if len(self.messages) != len(self.selected_turn_ids) * 2:
            raise ValueError("Each selected context turn requires one message pair")
        paired_ids: list[UUID] = []
        previous_time: datetime | None = None
        for index in range(0, len(self.messages), 2):
            user_message, assistant_message = self.messages[index : index + 2]
            if (
                user_message.role is not ContextMessageRole.USER
                or assistant_message.role is not ContextMessageRole.ASSISTANT
                or user_message.source_turn_id != assistant_message.source_turn_id
            ):
                raise ValueError("Selected context messages must be user/assistant pairs")
            if assistant_message.created_at < user_message.created_at:
                raise ValueError("Selected assistant context cannot precede its user")
            if previous_time is not None and user_message.created_at < previous_time:
                raise ValueError("Selected context must remain chronological")
            previous_time = assistant_message.created_at
            paired_ids.append(user_message.source_turn_id)
        if tuple(paired_ids) != self.selected_turn_ids:
            raise ValueError("Selected turn identities must match message pairs")
        if self.reset_applied and self.selected_turn_ids:
            raise ValueError("A reset context cannot retain prior turns")
        accounted_candidates = (
            len(self.selected_turn_ids)
            + self.excluded_wrong_owner_or_session_count
            + self.excluded_noncompleted_count
            + self.excluded_inheritance_count
            + self.excluded_irrelevant_count
            + self.truncated_relevant_count
        )
        if accounted_candidates != self.candidate_count:
            raise ValueError("Context selection candidate accounting must be exact")
        return self


def select_conversation_context(
    request: ConversationContextRequest,
) -> ConversationContextSelection:
    active: list[ConversationContextCandidate] = []
    wrong_owner_or_session = 0
    noncompleted = 0
    excluded_inheritance = 0
    for candidate in request.candidates:
        if (
            candidate.session_id != request.session_id
            or candidate.user_id != request.user_id
        ):
            wrong_owner_or_session += 1
        elif candidate.status is not ContextTurnStatus.COMPLETED:
            noncompleted += 1
        elif not candidate.inheritance_eligible:
            excluded_inheritance += 1
        else:
            active.append(candidate)

    ordered_active = sorted(active, key=_candidate_order)
    if request.reset_context:
        return _selection(
            request,
            selected=(),
            reset_applied=True,
            wrong_owner_or_session=wrong_owner_or_session,
            noncompleted=noncompleted,
            excluded_inheritance=excluded_inheritance,
            irrelevant=len(ordered_active),
            truncated=0,
        )

    relevance_keys = set(request.relevance_keys)
    relevant_ids = {
        candidate.turn_id
        for candidate in ordered_active
        if relevance_keys.intersection(candidate.context_keys)
    }
    if request.requires_immediate_context and ordered_active:
        relevant_ids.add(ordered_active[-1].turn_id)

    relevant_newest_first = [
        candidate
        for candidate in reversed(ordered_active)
        if candidate.turn_id in relevant_ids
    ]
    selected = tuple(
        sorted(
            relevant_newest_first[: request.max_turns],
            key=_candidate_order,
        )
    )
    return _selection(
        request,
        selected=selected,
        reset_applied=False,
        wrong_owner_or_session=wrong_owner_or_session,
        noncompleted=noncompleted,
        excluded_inheritance=excluded_inheritance,
        irrelevant=len(ordered_active) - len(relevant_newest_first),
        truncated=max(0, len(relevant_newest_first) - len(selected)),
    )


def conversation_context_json(selection: ConversationContextSelection) -> str:
    return json.dumps(
        selection.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
    )


def _selection(
    request: ConversationContextRequest,
    *,
    selected: tuple[ConversationContextCandidate, ...],
    reset_applied: bool,
    wrong_owner_or_session: int,
    noncompleted: int,
    excluded_inheritance: int,
    irrelevant: int,
    truncated: int,
) -> ConversationContextSelection:
    messages = tuple(
        message
        for candidate in selected
        for message in (
            SelectedContextMessage(
                source_turn_id=candidate.turn_id,
                role=ContextMessageRole.USER,
                content=candidate.user_content,
                created_at=candidate.user_created_at,
            ),
            SelectedContextMessage(
                source_turn_id=candidate.turn_id,
                role=ContextMessageRole.ASSISTANT,
                content=candidate.assistant_content,
                created_at=candidate.assistant_created_at,
            ),
        )
    )
    return ConversationContextSelection(
        policy_version=request.policy_version,
        session_id=request.session_id,
        user_id=request.user_id,
        selected_turn_ids=tuple(candidate.turn_id for candidate in selected),
        messages=messages,
        reset_applied=reset_applied,
        candidate_count=len(request.candidates),
        excluded_wrong_owner_or_session_count=wrong_owner_or_session,
        excluded_noncompleted_count=noncompleted,
        excluded_inheritance_count=excluded_inheritance,
        excluded_irrelevant_count=irrelevant,
        truncated_relevant_count=truncated,
    )


def _candidate_order(
    candidate: ConversationContextCandidate,
) -> tuple[datetime, int, str]:
    return (
        candidate.user_created_at,
        candidate.anchor_id,
        str(candidate.turn_id),
    )


def _normalize_key(value: str) -> str:
    return " ".join(value.casefold().split())


def _require_aware(value: datetime) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Conversation context timestamps must be timezone-aware")
