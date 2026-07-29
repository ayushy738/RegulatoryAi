from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Literal, Protocol
from uuid import UUID

from pydantic import Field, model_validator
from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.ask.orchestration.contracts import ContractModel
from backend.ask.orchestration.durability import (
    MAX_RUN_EVENT_PAGE_SIZE,
    DurabilityError,
    DurableRunEventPage,
    DurableRunEventReadModel,
    DurableRunNotFound,
    DurableRunRepository,
    DurableRunStatus,
    RunEventCursorError,
    decode_run_event_cursor,
    encode_run_event_cursor,
)
from backend.core.db import session_scope

RUN_EVENT_STREAM_SCHEMA_VERSION = "1"
RUN_EVENT_STREAM_POLICY_VERSION = "ask-ai-run-stream-v1"
RUN_EVENT_STREAM_PAGE_SIZE = 100
RUN_EVENT_STREAM_POLL_SECONDS = 0.5
RUN_EVENT_STREAM_HEARTBEAT_SECONDS = 15.0
RUN_EVENT_STREAM_SAFE_ERROR_CODE = "ASK_STREAM_UNAVAILABLE"
logger = logging.getLogger(__name__)

TERMINAL_DURABLE_RUN_STATUSES = frozenset(
    {
        DurableRunStatus.COMPLETED,
        DurableRunStatus.PARTIAL,
        DurableRunStatus.FAILED,
        DurableRunStatus.CANCELLED,
    }
)


class RunEventStreamError(RuntimeError):
    pass


class RunEventStreamNotFound(RunEventStreamError):
    pass


class RunEventStreamCursorError(RunEventStreamError):
    pass


class RunEventStreamControl(ContractModel):
    schema_version: Literal["1"] = RUN_EVENT_STREAM_SCHEMA_VERSION
    policy_version: str = Field(
        default=RUN_EVENT_STREAM_POLICY_VERSION,
        min_length=1,
    )
    event: Literal["heartbeat", "complete", "stream_error"]
    run_id: UUID
    resume_cursor: str | None = Field(default=None, max_length=512)
    status: DurableRunStatus | None = None
    code: Literal["ASK_STREAM_UNAVAILABLE"] | None = None

    @model_validator(mode="after")
    def validate_control(self) -> RunEventStreamControl:
        if self.event == "heartbeat":
            valid = self.status is None and self.code is None
        elif self.event == "complete":
            valid = (
                self.status in TERMINAL_DURABLE_RUN_STATUSES
                and self.code is None
            )
        else:
            valid = (
                self.status is None
                and self.code == RUN_EVENT_STREAM_SAFE_ERROR_CODE
            )
        if not valid:
            raise ValueError("Invalid run event stream control frame")
        return self


@dataclass(frozen=True)
class RunEventStreamBatch:
    page: DurableRunEventPage
    run_status: DurableRunStatus

    @property
    def terminal(self) -> bool:
        return self.run_status in TERMINAL_DURABLE_RUN_STATUSES


@dataclass(frozen=True)
class RunEventStreamSubscription:
    run_id: UUID
    session_id: UUID
    user_id: UUID
    cursor: str | None
    limit: int
    initial_batch: RunEventStreamBatch


class RunEventStreamStore(Protocol):
    def resolve_owned_session(
        self,
        *,
        run_id: UUID,
        user_id: UUID,
    ) -> UUID | None: ...

    def read_batch(
        self,
        *,
        run_id: UUID,
        session_id: UUID,
        user_id: UUID,
        cursor: str | None,
        limit: int,
    ) -> RunEventStreamBatch: ...


class PostgresRunEventStreamStore:
    def __init__(
        self,
        session_scope_factory: Callable[
            [], AbstractContextManager[Session]
        ] = session_scope,
    ) -> None:
        self._session_scope_factory = session_scope_factory

    def resolve_owned_session(
        self,
        *,
        run_id: UUID,
        user_id: UUID,
    ) -> UUID | None:
        with self._session_scope_factory() as database_session:
            row = database_session.execute(
                text(
                    """
                    select ar.session_id
                    from public.ask_runs ar
                    join public.chat_sessions cs
                      on cs.id = ar.session_id
                     and cs.user_id = ar.user_id
                    where ar.id = :run_id
                      and ar.user_id = :user_id
                      and cs.deleted_at is null
                    """
                ),
                {"run_id": run_id, "user_id": user_id},
            ).mappings().one_or_none()
            return row["session_id"] if row is not None else None

    def read_batch(
        self,
        *,
        run_id: UUID,
        session_id: UUID,
        user_id: UUID,
        cursor: str | None,
        limit: int,
    ) -> RunEventStreamBatch:
        with self._session_scope_factory() as database_session:
            database_session.execute(
                text("set transaction isolation level repeatable read")
            )
            repository = DurableRunRepository(database_session)
            page = repository.load_event_page(
                run_id=run_id,
                session_id=session_id,
                user_id=user_id,
                cursor=cursor,
                limit=limit,
            )
            snapshot = repository.load_snapshot(
                run_id=run_id,
                session_id=session_id,
                user_id=user_id,
            )
            return RunEventStreamBatch(
                page=page,
                run_status=snapshot.status,
            )


DisconnectCheck = Callable[[], Awaitable[bool]]
Sleep = Callable[[float], Awaitable[None]]
Monotonic = Callable[[], float]


class RunEventStreamService:
    def __init__(
        self,
        store: RunEventStreamStore | None = None,
        *,
        sleep: Sleep = asyncio.sleep,
        monotonic: Monotonic = time.monotonic,
        poll_seconds: float = RUN_EVENT_STREAM_POLL_SECONDS,
        heartbeat_seconds: float = RUN_EVENT_STREAM_HEARTBEAT_SECONDS,
    ) -> None:
        if poll_seconds <= 0:
            raise ValueError("Stream poll interval must be positive")
        if heartbeat_seconds < poll_seconds:
            raise ValueError("Stream heartbeat must not precede polling")
        self._store = store or PostgresRunEventStreamStore()
        self._sleep = sleep
        self._monotonic = monotonic
        self._poll_seconds = poll_seconds
        self._heartbeat_seconds = heartbeat_seconds

    async def prepare(
        self,
        *,
        run_id: UUID,
        user_id: UUID,
        cursor: str | None,
        limit: int = RUN_EVENT_STREAM_PAGE_SIZE,
    ) -> RunEventStreamSubscription:
        if isinstance(limit, bool) or not isinstance(limit, int):
            raise TypeError("Stream page size must be an integer")
        if limit < 1 or limit > MAX_RUN_EVENT_PAGE_SIZE:
            raise ValueError(
                f"Stream page size must be between 1 and "
                f"{MAX_RUN_EVENT_PAGE_SIZE}"
            )
        if cursor is not None:
            try:
                decoded = decode_run_event_cursor(cursor)
            except RunEventCursorError as exc:
                raise RunEventStreamCursorError(
                    "Invalid event stream cursor"
                ) from exc
            if decoded.run_id != run_id:
                raise RunEventStreamCursorError(
                    "Event stream cursor belongs to another run"
                )
        try:
            session_id = await asyncio.to_thread(
                self._store.resolve_owned_session,
                run_id=run_id,
                user_id=user_id,
            )
        except Exception as exc:
            _record_store_failure(run_id)
            raise RunEventStreamError(
                "Durable event stream is unavailable"
            ) from exc
        if session_id is None:
            raise RunEventStreamNotFound("Run is inaccessible")
        try:
            initial_batch = await asyncio.to_thread(
                self._store.read_batch,
                run_id=run_id,
                session_id=session_id,
                user_id=user_id,
                cursor=cursor,
                limit=limit,
            )
        except DurableRunNotFound as exc:
            raise RunEventStreamNotFound("Run is inaccessible") from exc
        except RunEventCursorError as exc:
            raise RunEventStreamCursorError(
                "Invalid event stream cursor"
            ) from exc
        except DurabilityError as exc:
            raise RunEventStreamError(
                "Durable event stream is unavailable"
            ) from exc
        except Exception as exc:
            _record_store_failure(run_id)
            raise RunEventStreamError(
                "Durable event stream is unavailable"
            ) from exc
        return RunEventStreamSubscription(
            run_id=run_id,
            session_id=session_id,
            user_id=user_id,
            cursor=cursor,
            limit=limit,
            initial_batch=initial_batch,
        )

    async def frames(
        self,
        subscription: RunEventStreamSubscription,
        *,
        disconnected: DisconnectCheck,
    ) -> AsyncIterator[str]:
        cursor = subscription.cursor
        expected_sequence = (
            decode_run_event_cursor(cursor).sequence + 1
            if cursor is not None
            else 0
        )
        batch = subscription.initial_batch
        last_heartbeat = self._monotonic()
        seen_event_ids: set[UUID] = set()

        while True:
            if await disconnected():
                return
            valid, next_sequence = _validate_stream_items(
                batch.page.items,
                run_id=subscription.run_id,
                expected_sequence=expected_sequence,
                seen_event_ids=seen_event_ids,
            )
            if not valid:
                yield _control_frame(
                    "stream_error",
                    run_id=subscription.run_id,
                    cursor=cursor,
                    code=RUN_EVENT_STREAM_SAFE_ERROR_CODE,
                )
                return
            for item in batch.page.items:
                if await disconnected():
                    return
                cursor = encode_run_event_cursor(item)
                yield _event_frame(item, cursor)
            expected_sequence = next_sequence

            if batch.terminal and not batch.page.has_more:
                yield _control_frame(
                    "complete",
                    run_id=subscription.run_id,
                    cursor=cursor,
                    status=batch.run_status.value,
                )
                return

            if batch.page.has_more:
                cursor = batch.page.resume_cursor
            else:
                await self._sleep(self._poll_seconds)
                if await disconnected():
                    return
                now = self._monotonic()
                if now - last_heartbeat >= self._heartbeat_seconds:
                    yield _control_frame(
                        "heartbeat",
                        run_id=subscription.run_id,
                        cursor=cursor,
                    )
                    last_heartbeat = now

            try:
                batch = await asyncio.to_thread(
                    self._store.read_batch,
                    run_id=subscription.run_id,
                    session_id=subscription.session_id,
                    user_id=subscription.user_id,
                    cursor=cursor,
                    limit=subscription.limit,
                )
            except (DurableRunNotFound, RunEventCursorError, DurabilityError):
                yield _control_frame(
                    "stream_error",
                    run_id=subscription.run_id,
                    cursor=cursor,
                    code=RUN_EVENT_STREAM_SAFE_ERROR_CODE,
                )
                return
            except Exception:
                _record_store_failure(subscription.run_id)
                yield _control_frame(
                    "stream_error",
                    run_id=subscription.run_id,
                    cursor=cursor,
                    code=RUN_EVENT_STREAM_SAFE_ERROR_CODE,
                )
                return


def _validate_stream_items(
    items: tuple[DurableRunEventReadModel, ...],
    *,
    run_id: UUID,
    expected_sequence: int,
    seen_event_ids: set[UUID],
) -> tuple[bool, int]:
    next_sequence = expected_sequence
    for item in items:
        if (
            item.run_id != run_id
            or item.sequence != next_sequence
            or item.execution_version != item.sequence + 1
            or item.event_id in seen_event_ids
        ):
            return False, expected_sequence
        seen_event_ids.add(item.event_id)
        next_sequence += 1
    return True, next_sequence


def _record_store_failure(run_id: UUID) -> None:
    logger.error(
        "ask_run_event_stream_store_failure",
        extra={"run_id": str(run_id)},
    )


def _event_frame(item: DurableRunEventReadModel, cursor: str) -> str:
    return _sse_frame(
        event="run_event",
        data=item.model_dump(mode="json"),
        event_id=cursor,
    )


def _control_frame(
    event: Literal["heartbeat", "complete", "stream_error"],
    *,
    run_id: UUID,
    cursor: str | None,
    status: str | None = None,
    code: str | None = None,
) -> str:
    control = RunEventStreamControl(
        event=event,
        run_id=run_id,
        resume_cursor=cursor,
        status=status,
        code=code,
    )
    data = control.model_dump(mode="json")
    data.pop("event")
    if data["status"] is None:
        data.pop("status")
    if data["code"] is None:
        data.pop("code")
    return _sse_frame(event=event, data=data)


def _sse_frame(
    *,
    event: str,
    data: dict[str, object],
    event_id: str | None = None,
) -> str:
    lines = []
    if event_id is not None:
        lines.append(f"id: {event_id}")
    lines.extend(
        (
            f"event: {event}",
            "data: "
            + json.dumps(
                data,
                separators=(",", ":"),
                sort_keys=True,
            ),
            "",
            "",
        )
    )
    return "\n".join(lines)
