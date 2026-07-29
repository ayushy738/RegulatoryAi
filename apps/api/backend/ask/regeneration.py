from __future__ import annotations

import json
from collections.abc import Callable
from contextlib import AbstractContextManager
from enum import StrEnum
from typing import Literal
from uuid import UUID, uuid4

from pydantic import Field, model_validator
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.ask.orchestration.contracts import (
    ContractModel,
    ResearchRequestPayload,
)
from backend.ask.orchestration.state_machine import (
    OrchestrationState,
    initialize_orchestration,
)
from backend.core.db import session_scope

REGENERATION_SCHEMA_VERSION = "1"
REGENERATION_POLICY_VERSION = "ask-ai-regeneration-v1"


class ResponseMutationOperation(StrEnum):
    REGENERATE = "regenerate"
    REFRESH = "refresh"


class ResponseSourceStrategy(StrEnum):
    SAME_SOURCES = "same_sources"
    REFRESH_OFFICIAL = "refresh_official"
    INCLUDE_LIVE = "include_live"


class ResponseStyleVariant(StrEnum):
    DEFAULT = "default"
    CONCISE = "concise"
    BEGINNER = "beginner"
    LEGAL_DETAIL = "legal_detail"


class RegenerateResponseRequest(ContractModel):
    schema_version: Literal["1"] = REGENERATION_SCHEMA_VERSION
    idempotency_key: UUID
    assistant_message_id: UUID
    style_variant: ResponseStyleVariant = ResponseStyleVariant.DEFAULT


class RefreshResponseRequest(ContractModel):
    schema_version: Literal["1"] = REGENERATION_SCHEMA_VERSION
    idempotency_key: UUID
    assistant_message_id: UUID
    source_strategy: Literal[
        ResponseSourceStrategy.REFRESH_OFFICIAL,
        ResponseSourceStrategy.INCLUDE_LIVE,
    ]
    style_variant: ResponseStyleVariant = ResponseStyleVariant.DEFAULT


class ResponseRegenerationPlan(ContractModel):
    schema_version: Literal["1"] = REGENERATION_SCHEMA_VERSION
    policy_version: str = Field(
        default=REGENERATION_POLICY_VERSION,
        min_length=1,
    )
    request_id: UUID
    operation: ResponseMutationOperation
    source_strategy: ResponseSourceStrategy
    style_variant: ResponseStyleVariant
    session_id: UUID
    user_id: UUID
    user_message_id: int = Field(gt=0)
    user_message_public_id: UUID
    source_run_id: UUID
    source_response_version: int = Field(gt=0)
    source_assistant_message_id: UUID
    source_snapshot_ids: tuple[UUID, ...]
    reused_source_snapshot_ids: tuple[UUID, ...]
    refresh_knowledge_modes: tuple[Literal["official", "live"], ...]
    parent_assistant_message_id: UUID
    parent_response_version: int = Field(gt=0)
    target_run_id: UUID
    target_assistant_message_id: UUID
    target_response_version: int = Field(gt=1)
    research_request_artifact_id: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_lineage(self) -> ResponseRegenerationPlan:
        if self.target_response_version != self.parent_response_version + 1:
            raise ValueError("Target response must follow the current branch head")
        if self.target_response_version <= self.source_response_version:
            raise ValueError("Target response must append after the selected source")
        if len(set(self.source_snapshot_ids)) != len(self.source_snapshot_ids):
            raise ValueError("Source snapshot identities must be unique")
        if len(set(self.refresh_knowledge_modes)) != len(
            self.refresh_knowledge_modes
        ):
            raise ValueError("Refresh knowledge modes must be unique")
        if self.operation is ResponseMutationOperation.REGENERATE:
            if self.source_strategy is not ResponseSourceStrategy.SAME_SOURCES:
                raise ValueError("Regeneration must reuse the selected sources")
            if self.reused_source_snapshot_ids != self.source_snapshot_ids:
                raise ValueError("Same-source regeneration must reuse every snapshot")
            if self.refresh_knowledge_modes:
                raise ValueError("Same-source regeneration cannot request retrieval")
        else:
            if self.source_strategy is ResponseSourceStrategy.SAME_SOURCES:
                raise ValueError("Refresh must request fresh retrieval")
            if self.reused_source_snapshot_ids:
                raise ValueError("Refresh cannot reuse historical source snapshots")
            expected_modes = (
                ("official",)
                if self.source_strategy
                is ResponseSourceStrategy.REFRESH_OFFICIAL
                else ("official", "live")
            )
            if self.refresh_knowledge_modes != expected_modes:
                raise ValueError("Refresh modes do not match the source strategy")
        identities = {
            self.source_assistant_message_id,
            self.parent_assistant_message_id,
            self.target_assistant_message_id,
        }
        if self.target_assistant_message_id in {
            self.source_assistant_message_id,
            self.parent_assistant_message_id,
        } or len(identities) < 2:
            raise ValueError("Target assistant identity must be new")
        if self.source_run_id == self.target_run_id:
            raise ValueError("Target run identity must be new")
        return self


class ResponseRegenerationRecord(ContractModel):
    schema_version: Literal["1"] = REGENERATION_SCHEMA_VERSION
    request_id: UUID
    plan: ResponseRegenerationPlan
    status: Literal["pending"] = "pending"


class ResponseRegenerationResponse(ContractModel):
    schema_version: Literal["1"] = REGENERATION_SCHEMA_VERSION
    policy_version: str = Field(
        default=REGENERATION_POLICY_VERSION,
        min_length=1,
    )
    request_id: UUID
    operation: ResponseMutationOperation
    source_strategy: ResponseSourceStrategy
    style_variant: ResponseStyleVariant
    status: Literal["pending"]
    source_message_id: UUID
    source_run_id: UUID
    source_response_version: int
    parent_message_id: UUID
    target_message_id: UUID
    target_run_id: UUID
    target_response_version: int
    reused_source_ids: tuple[UUID, ...]
    refresh_knowledge_modes: tuple[Literal["official", "live"], ...]

    @classmethod
    def from_record(
        cls,
        record: ResponseRegenerationRecord,
    ) -> ResponseRegenerationResponse:
        plan = record.plan
        return cls(
            request_id=record.request_id,
            operation=plan.operation,
            source_strategy=plan.source_strategy,
            style_variant=plan.style_variant,
            status=record.status,
            source_message_id=plan.source_assistant_message_id,
            source_run_id=plan.source_run_id,
            source_response_version=plan.source_response_version,
            parent_message_id=plan.parent_assistant_message_id,
            target_message_id=plan.target_assistant_message_id,
            target_run_id=plan.target_run_id,
            target_response_version=plan.target_response_version,
            reused_source_ids=plan.reused_source_snapshot_ids,
            refresh_knowledge_modes=plan.refresh_knowledge_modes,
        )


class ResponseRegenerationError(RuntimeError):
    pass


class ResponseRegenerationNotFound(ResponseRegenerationError):
    pass


class ResponseRegenerationNotEligible(ResponseRegenerationError):
    pass


class ResponseRegenerationConflict(ResponseRegenerationError):
    pass


SessionScopeFactory = Callable[[], AbstractContextManager[Session]]


class ResponseRegenerationService:
    def __init__(
        self,
        session_scope_factory: SessionScopeFactory = session_scope,
        identity_factory: Callable[[], UUID] = uuid4,
    ) -> None:
        self._session_scope_factory = session_scope_factory
        self._identity_factory = identity_factory

    def regenerate(
        self,
        *,
        source_message_id: UUID,
        user_id: UUID,
        request: RegenerateResponseRequest,
    ) -> ResponseRegenerationRecord:
        return self._create(
            source_message_id=source_message_id,
            user_id=user_id,
            idempotency_key=request.idempotency_key,
            target_message_id=request.assistant_message_id,
            operation=ResponseMutationOperation.REGENERATE,
            source_strategy=ResponseSourceStrategy.SAME_SOURCES,
            style_variant=request.style_variant,
        )

    def refresh(
        self,
        *,
        source_message_id: UUID,
        user_id: UUID,
        request: RefreshResponseRequest,
    ) -> ResponseRegenerationRecord:
        return self._create(
            source_message_id=source_message_id,
            user_id=user_id,
            idempotency_key=request.idempotency_key,
            target_message_id=request.assistant_message_id,
            operation=ResponseMutationOperation.REFRESH,
            source_strategy=ResponseSourceStrategy(request.source_strategy),
            style_variant=request.style_variant,
        )

    def _create(
        self,
        *,
        source_message_id: UUID,
        user_id: UUID,
        idempotency_key: UUID,
        target_message_id: UUID,
        operation: ResponseMutationOperation,
        source_strategy: ResponseSourceStrategy,
        style_variant: ResponseStyleVariant,
    ) -> ResponseRegenerationRecord:
        target_run_id = self._identity_factory()
        try:
            with (
                self._session_scope_factory() as database_session,
                database_session.begin(),
            ):
                existing = _load_record(
                    database_session,
                    request_id=idempotency_key,
                )
                if existing is not None:
                    return _require_idempotent_request(
                        existing,
                        user_id=user_id,
                        source_message_id=source_message_id,
                        target_message_id=target_message_id,
                        operation=operation,
                        source_strategy=source_strategy,
                        style_variant=style_variant,
                    )

                source = _load_source(
                    database_session,
                    source_message_id=source_message_id,
                    user_id=user_id,
                )
                if source is None:
                    raise ResponseRegenerationNotFound("Message is inaccessible")
                if source["run_status"] not in {"completed", "partial"}:
                    raise ResponseRegenerationNotEligible(
                        "Only completed answers can create another version"
                    )

                database_session.execute(
                    text(
                        """
                        select id
                        from public.chat_messages
                        where id = :user_message_id
                          and session_id = :session_id
                          and user_id = :user_id
                          and role = 'user'
                        for update
                        """
                    ),
                    {
                        "user_message_id": source["user_message_id"],
                        "session_id": source["session_id"],
                        "user_id": user_id,
                    },
                ).one()

                existing = _load_record(
                    database_session,
                    request_id=idempotency_key,
                )
                if existing is not None:
                    return _require_idempotent_request(
                        existing,
                        user_id=user_id,
                        source_message_id=source_message_id,
                        target_message_id=target_message_id,
                        operation=operation,
                        source_strategy=source_strategy,
                        style_variant=style_variant,
                    )

                if database_session.execute(
                    text(
                        """
                        select 1
                        from public.chat_messages
                        where public_id = :target_message_id
                        """
                    ),
                    {"target_message_id": target_message_id},
                ).first() is not None:
                    raise ResponseRegenerationConflict(
                        "Target message identity is already in use"
                    )

                parent = database_session.execute(
                    text(
                        """
                        select
                          message.id,
                          message.public_id,
                          run.response_version
                        from public.ask_runs run
                        join public.chat_messages message
                          on message.id = run.assistant_message_id
                         and message.reply_to_message_id = run.user_message_id
                         and message.session_id = run.session_id
                         and message.user_id = run.user_id
                         and message.response_version = run.response_version
                        where run.user_message_id = :user_message_id
                          and run.session_id = :session_id
                          and run.user_id = :user_id
                        order by run.response_version desc
                        limit 1
                        """
                    ),
                    {
                        "user_message_id": source["user_message_id"],
                        "session_id": source["session_id"],
                        "user_id": user_id,
                    },
                ).mappings().one()
                target_version = int(parent["response_version"]) + 1
                source_snapshot_ids = tuple(
                    row[0]
                    for row in database_session.execute(
                        text(
                            """
                            select id
                            from public.ask_sources
                            where run_id = :source_run_id
                              and session_id = :session_id
                              and user_id = :user_id
                            order by ordinal, id
                            """
                        ),
                        {
                            "source_run_id": source["source_run_id"],
                            "session_id": source["session_id"],
                            "user_id": user_id,
                        },
                    )
                )
                target_state = _initialize_target_state(
                    source_state=source["orchestration_state"],
                    target_run_id=target_run_id,
                    request_id=idempotency_key,
                    source_strategy=source_strategy,
                    style_variant=style_variant,
                )
                target_message_internal_id = database_session.execute(
                    text(
                        """
                        insert into public.chat_messages (
                          public_id,
                          session_id,
                          user_id,
                          event_id,
                          role,
                          content,
                          status,
                          response_version,
                          reply_to_message_id,
                          parent_message_id
                        )
                        values (
                          :public_id,
                          :session_id,
                          :user_id,
                          :event_id,
                          'assistant',
                          '',
                          'pending',
                          :response_version,
                          :user_message_id,
                          :parent_message_id
                        )
                        returning id
                        """
                    ),
                    {
                        "public_id": target_message_id,
                        "session_id": source["session_id"],
                        "user_id": user_id,
                        "event_id": source["event_id"],
                        "response_version": target_version,
                        "user_message_id": source["user_message_id"],
                        "parent_message_id": parent["id"],
                    },
                ).scalar_one()
                database_session.execute(
                    text(
                        """
                        insert into public.ask_runs (
                          id,
                          session_id,
                          user_id,
                          user_message_id,
                          assistant_message_id,
                          status,
                          orchestration_state,
                          policy_version,
                          response_version
                        )
                        values (
                          :run_id,
                          :session_id,
                          :user_id,
                          :user_message_id,
                          :assistant_message_id,
                          'pending',
                          cast(:orchestration_state as jsonb),
                          :policy_version,
                          :response_version
                        )
                        """
                    ),
                    {
                        "run_id": target_run_id,
                        "session_id": source["session_id"],
                        "user_id": user_id,
                        "user_message_id": source["user_message_id"],
                        "assistant_message_id": target_message_internal_id,
                        "orchestration_state": json.dumps(
                            target_state.model_dump(mode="json")
                        ),
                        "policy_version": REGENERATION_POLICY_VERSION,
                        "response_version": target_version,
                    },
                )
                refresh_modes: tuple[Literal["official", "live"], ...] = ()
                reused_ids: tuple[UUID, ...] = source_snapshot_ids
                if source_strategy is ResponseSourceStrategy.REFRESH_OFFICIAL:
                    refresh_modes = ("official",)
                    reused_ids = ()
                elif source_strategy is ResponseSourceStrategy.INCLUDE_LIVE:
                    refresh_modes = ("official", "live")
                    reused_ids = ()
                plan = ResponseRegenerationPlan(
                    request_id=idempotency_key,
                    operation=operation,
                    source_strategy=source_strategy,
                    style_variant=style_variant,
                    session_id=source["session_id"],
                    user_id=user_id,
                    user_message_id=source["user_message_id"],
                    user_message_public_id=source["user_message_public_id"],
                    source_run_id=source["source_run_id"],
                    source_response_version=source["source_response_version"],
                    source_assistant_message_id=source_message_id,
                    source_snapshot_ids=source_snapshot_ids,
                    reused_source_snapshot_ids=reused_ids,
                    refresh_knowledge_modes=refresh_modes,
                    parent_assistant_message_id=parent["public_id"],
                    parent_response_version=parent["response_version"],
                    target_run_id=target_run_id,
                    target_assistant_message_id=target_message_id,
                    target_response_version=target_version,
                    research_request_artifact_id=(
                        target_state.research_request.artifact_id
                    ),
                )
                database_session.execute(
                    text(
                        """
                        insert into public.ask_response_regenerations (
                          request_id,
                          session_id,
                          user_id,
                          user_message_id,
                          source_run_id,
                          source_response_version,
                          source_assistant_message_id,
                          parent_assistant_message_id,
                          parent_response_version,
                          target_run_id,
                          target_response_version,
                          target_assistant_message_id,
                          operation,
                          source_strategy,
                          style_variant,
                          plan
                        )
                        values (
                          :request_id,
                          :session_id,
                          :user_id,
                          :user_message_id,
                          :source_run_id,
                          :source_response_version,
                          :source_assistant_message_id,
                          :parent_assistant_message_id,
                          :parent_response_version,
                          :target_run_id,
                          :target_response_version,
                          :target_assistant_message_id,
                          :operation,
                          :source_strategy,
                          :style_variant,
                          cast(:plan as jsonb)
                        )
                        """
                    ),
                    {
                        "request_id": idempotency_key,
                        "session_id": source["session_id"],
                        "user_id": user_id,
                        "user_message_id": source["user_message_id"],
                        "source_run_id": source["source_run_id"],
                        "source_response_version": source[
                            "source_response_version"
                        ],
                        "source_assistant_message_id": source[
                            "source_assistant_message_internal_id"
                        ],
                        "parent_assistant_message_id": parent["id"],
                        "parent_response_version": parent["response_version"],
                        "target_run_id": target_run_id,
                        "target_response_version": target_version,
                        "target_assistant_message_id": (
                            target_message_internal_id
                        ),
                        "operation": operation.value,
                        "source_strategy": source_strategy.value,
                        "style_variant": style_variant.value,
                        "plan": json.dumps(plan.model_dump(mode="json")),
                    },
                )
                database_session.execute(
                    text(
                        """
                        update public.chat_sessions
                        set
                          updated_at = greatest(updated_at, now()),
                          last_message_at = greatest(
                            coalesce(last_message_at, '-infinity'::timestamptz),
                            now()
                          )
                        where id = :session_id
                          and user_id = :user_id
                        """
                    ),
                    {
                        "session_id": source["session_id"],
                        "user_id": user_id,
                    },
                )
                return ResponseRegenerationRecord(
                    request_id=idempotency_key,
                    plan=plan,
                )
        except IntegrityError as exc:
            if getattr(exc.orig, "sqlstate", None) == "23505":
                raise ResponseRegenerationConflict(
                    "Response version identity conflicts with existing work"
                ) from None
            raise


def _load_source(
    database_session: Session,
    *,
    source_message_id: UUID,
    user_id: UUID,
):
    return database_session.execute(
        text(
            """
            select
              message.id as source_assistant_message_internal_id,
              message.reply_to_message_id as user_message_id,
              run.id as source_run_id,
              run.response_version as source_response_version,
              run.status as run_status,
              run.orchestration_state,
              user_message.public_id as user_message_public_id,
              chat_session.id as session_id,
              chat_session.event_id
            from public.chat_messages message
            join public.ask_runs run
              on run.assistant_message_id = message.id
             and run.session_id = message.session_id
             and run.user_id = message.user_id
             and run.response_version = message.response_version
            join public.chat_messages user_message
              on user_message.id = run.user_message_id
             and user_message.session_id = run.session_id
             and user_message.user_id = run.user_id
             and user_message.role = 'user'
            join public.chat_sessions chat_session
              on chat_session.id = run.session_id
             and chat_session.user_id = run.user_id
             and chat_session.deleted_at is null
             and chat_session.archived_at is null
            where message.public_id = :source_message_id
              and message.user_id = :user_id
              and message.role = 'assistant'
              and message.status = 'completed'
            """
        ),
        {
            "source_message_id": source_message_id,
            "user_id": user_id,
        },
    ).mappings().one_or_none()


def _load_record(
    database_session: Session,
    *,
    request_id: UUID,
) -> ResponseRegenerationRecord | None:
    row = database_session.execute(
        text(
            """
            select request_id, plan
            from public.ask_response_regenerations
            where request_id = :request_id
            """
        ),
        {"request_id": request_id},
    ).mappings().one_or_none()
    if row is None:
        return None
    return ResponseRegenerationRecord(
        request_id=row["request_id"],
        plan=ResponseRegenerationPlan.model_validate(row["plan"]),
    )


def _require_idempotent_request(
    existing: ResponseRegenerationRecord,
    *,
    user_id: UUID,
    source_message_id: UUID,
    target_message_id: UUID,
    operation: ResponseMutationOperation,
    source_strategy: ResponseSourceStrategy,
    style_variant: ResponseStyleVariant,
) -> ResponseRegenerationRecord:
    plan = existing.plan
    if (
        plan.request_id != existing.request_id
        or plan.source_assistant_message_id != source_message_id
        or plan.target_assistant_message_id != target_message_id
        or plan.operation is not operation
        or plan.source_strategy is not source_strategy
        or plan.style_variant is not style_variant
        or plan.user_id != user_id
    ):
        raise ResponseRegenerationConflict(
            "Idempotency key is bound to a different response mutation"
        )
    return existing


def _initialize_target_state(
    *,
    source_state: object,
    target_run_id: UUID,
    request_id: UUID,
    source_strategy: ResponseSourceStrategy,
    style_variant: ResponseStyleVariant,
) -> OrchestrationState:
    try:
        source = OrchestrationState.model_validate(source_state)
    except Exception as exc:
        raise ResponseRegenerationNotEligible(
            "Source answer has no resumable orchestration request"
        ) from exc
    payload = source.research_request.payload
    if not isinstance(payload, ResearchRequestPayload):
        raise ResponseRegenerationNotEligible(
            "Source answer has no research request"
        )
    mutation_constraints = (
        f"response_source_strategy:{source_strategy.value}",
        f"response_style:{style_variant.value}",
    )
    explicit_constraints = tuple(
        dict.fromkeys((*payload.explicit_constraints, *mutation_constraints))
    )
    target_payload = payload.model_copy(
        update={"explicit_constraints": explicit_constraints},
    )
    target_artifact_id = f"response-mutation:{request_id}"
    target_research_request = source.research_request.model_copy(
        update={
            "artifact_id": target_artifact_id,
            "payload": target_payload,
            "ancestry": tuple(
                dict.fromkeys(
                    (
                        *source.research_request.ancestry,
                        source.research_request.artifact_id,
                    )
                )
            ),
        },
    )
    return initialize_orchestration(
        run_id=target_run_id,
        plan_id=f"response-mutation:{request_id}",
        policy_version=REGENERATION_POLICY_VERSION,
        research_request=target_research_request,
    )
