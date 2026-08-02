from __future__ import annotations

import asyncio
from datetime import timedelta
from typing import Literal, Protocol
from uuid import UUID

from pydantic import Field, field_validator

from backend.ask.compatibility_rendering import (
    CompatibilityRenderRequest,
    render_structured_response_compatibility,
)
from backend.ask.orchestration.durability import DurableRunStatus
from backend.ask.orchestration.execution import RunExecutionResult
from backend.ask.response_contracts import ResponseContractModel
from backend.core.models import ChatResponse

LEGACY_SYNCHRONOUS_SCHEMA_VERSION = "1"
LEGACY_SYNCHRONOUS_POLICY_VERSION = "ask-ai-legacy-synchronous-v1"
MAX_SYNCHRONOUS_WAIT = timedelta(seconds=30)
_SERVABLE_STATUSES = frozenset(
    {DurableRunStatus.COMPLETED, DurableRunStatus.PARTIAL}
)


class LegacySynchronousAdapterError(RuntimeError):
    safe_code = "ASK_UNAVAILABLE"


class LegacySynchronousTimeout(LegacySynchronousAdapterError):
    safe_code = "ASK_TIMEOUT"


class LegacySynchronousCancelled(LegacySynchronousAdapterError):
    safe_code = "ASK_CANCELLED"


class LegacySynchronousUnavailable(LegacySynchronousAdapterError):
    safe_code = "ASK_UNAVAILABLE"


class LegacySynchronousArtifact(ResponseContractModel):
    schema_version: Literal["1"] = LEGACY_SYNCHRONOUS_SCHEMA_VERSION
    policy_version: Literal[
        "ask-ai-legacy-synchronous-v1"
    ] = LEGACY_SYNCHRONOUS_POLICY_VERSION
    run_id: UUID
    session_id: UUID
    user_id: UUID
    response_version: int = Field(gt=0)
    model: str = Field(min_length=1, max_length=500)
    intent: str | None = Field(default=None, max_length=100)
    event_id: int | None = None
    related_questions: tuple[str, ...] = ()
    compatibility: CompatibilityRenderRequest

    @field_validator("model")
    @classmethod
    def normalize_model(cls, value: str) -> str:
        return value.strip()

    @field_validator("intent")
    @classmethod
    def normalize_intent(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("Legacy intent cannot be blank")
        return normalized

    @field_validator("related_questions")
    @classmethod
    def validate_related_questions(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(item.strip() for item in value)
        if any(not item or len(item) > 4_000 for item in normalized):
            raise ValueError("Legacy related questions must be bounded and nonblank")
        if len(set(normalized)) != len(normalized):
            raise ValueError("Legacy related questions must be unique")
        return normalized

class LegacyRunExecutor(Protocol):
    async def execute(
        self,
        *,
        run_id: UUID,
        session_id: UUID,
        user_id: UUID,
        lease_ttl: timedelta,
        max_steps: int = 100,
    ) -> RunExecutionResult: ...


class LegacyTerminalArtifactLoader(Protocol):
    async def load_terminal_artifact(
        self,
        *,
        run_id: UUID,
        session_id: UUID,
        user_id: UUID,
    ) -> LegacySynchronousArtifact | None: ...


class LegacySynchronousRunAdapter:
    def __init__(
        self,
        *,
        executor: LegacyRunExecutor,
        artifact_loader: LegacyTerminalArtifactLoader,
    ) -> None:
        self._executor = executor
        self._artifact_loader = artifact_loader

    async def await_response(
        self,
        *,
        run_id: UUID,
        session_id: UUID,
        user_id: UUID,
        max_wait: timedelta,
        lease_ttl: timedelta,
        max_steps: int = 100,
    ) -> ChatResponse:
        _validate_wait_budget(max_wait=max_wait, lease_ttl=lease_ttl)
        if max_steps < 1 or max_steps > 10_000:
            raise ValueError("Synchronous execution max steps must be between 1 and 10000")
        deadline = asyncio.timeout(max_wait.total_seconds())
        try:
            async with deadline:
                execution = await self._executor.execute(
                    run_id=run_id,
                    session_id=session_id,
                    user_id=user_id,
                    lease_ttl=lease_ttl,
                    max_steps=max_steps,
                )
                snapshot = execution.snapshot
                if (
                    snapshot.run_id != run_id
                    or snapshot.session_id != session_id
                    or snapshot.user_id != user_id
                ):
                    raise LegacySynchronousUnavailable(
                        "The Ask AI response is temporarily unavailable."
                    )
                if snapshot.status is DurableRunStatus.CANCELLED:
                    raise LegacySynchronousCancelled(
                        "The Ask AI request was cancelled."
                    )
                if snapshot.status not in _SERVABLE_STATUSES:
                    raise LegacySynchronousUnavailable(
                        "The Ask AI response is temporarily unavailable."
                    )

                artifact = await self._artifact_loader.load_terminal_artifact(
                    run_id=run_id,
                    session_id=session_id,
                    user_id=user_id,
                )
                if artifact is None:
                    raise LegacySynchronousUnavailable(
                        "The Ask AI response is temporarily unavailable."
                    )
                safe_artifact = LegacySynchronousArtifact.model_validate_json(
                    artifact.model_dump_json()
                )
                if (
                    safe_artifact.run_id != run_id
                    or safe_artifact.session_id != session_id
                    or safe_artifact.user_id != user_id
                ):
                    raise LegacySynchronousUnavailable(
                        "The Ask AI response is temporarily unavailable."
                    )
                rendered = render_structured_response_compatibility(
                    safe_artifact.compatibility
                )
                return ChatResponse(
                    reply=rendered.reply,
                    event_id=safe_artifact.event_id,
                    model=safe_artifact.model,
                    intent=safe_artifact.intent,
                    citations=[
                        item.model_dump(mode="json") for item in rendered.citations
                    ],
                    related_questions=list(safe_artifact.related_questions),
                )
        except asyncio.CancelledError:
            raise
        except TimeoutError as exc:
            if deadline.expired():
                raise LegacySynchronousTimeout(
                    "The Ask AI request did not complete within its synchronous time budget."
                ) from exc
            raise LegacySynchronousUnavailable(
                "The Ask AI response is temporarily unavailable."
            ) from exc
        except LegacySynchronousAdapterError:
            raise
        except Exception as exc:
            raise LegacySynchronousUnavailable(
                "The Ask AI response is temporarily unavailable."
            ) from exc


def _validate_wait_budget(*, max_wait: timedelta, lease_ttl: timedelta) -> None:
    if max_wait <= timedelta(0) or max_wait > MAX_SYNCHRONOUS_WAIT:
        raise ValueError("Synchronous wait must be greater than zero and at most 30 seconds")
    if lease_ttl <= timedelta(0) or lease_ttl > max_wait:
        raise ValueError("Worker lease TTL must be positive and within the wait budget")
