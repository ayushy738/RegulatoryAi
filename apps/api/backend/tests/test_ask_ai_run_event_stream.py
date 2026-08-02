from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from backend.api.auth import CurrentUser, current_user
from backend.api.routes import chat_runs
from backend.ask.orchestration.durability import (
    DURABILITY_POLICY_VERSION,
    DurableEventType,
    DurableRunEventPage,
    DurableRunEventReadModel,
    DurableRunStatus,
    decode_run_event_cursor,
    encode_run_event_cursor,
)
from backend.ask.orchestration.streaming import (
    RUN_EVENT_STREAM_SAFE_ERROR_CODE,
    RunEventStreamBatch,
    RunEventStreamControl,
    RunEventStreamCursorError,
    RunEventStreamError,
    RunEventStreamNotFound,
    RunEventStreamService,
)
from backend.core.config import settings

NOW = datetime(2026, 7, 27, 12, 0, tzinfo=UTC)
RUN_ID = UUID("11111111-1111-4111-8111-111111111111")
SESSION_ID = UUID("22222222-2222-4222-8222-222222222222")
USER_ID = UUID("33333333-3333-4333-8333-333333333333")


def _read_event(
    sequence: int,
    *,
    event_id: UUID | None = None,
    run_id: UUID = RUN_ID,
) -> DurableRunEventReadModel:
    return DurableRunEventReadModel(
        policy_version=DURABILITY_POLICY_VERSION,
        event_id=event_id
        or UUID(f"44444444-4444-4444-8444-{sequence + 1:012d}"),
        run_id=run_id,
        sequence=sequence,
        execution_version=sequence + 1,
        event_type=DurableEventType.LEASE_ACQUIRED,
        status=DurableRunStatus.RUNNING,
        created_at=NOW,
    )


def _page(
    items: tuple[DurableRunEventReadModel, ...],
    *,
    cursor: str | None,
    has_more: bool = False,
    total: int | None = None,
) -> DurableRunEventPage:
    count = total if total is not None else len(items)
    return DurableRunEventPage(
        run_id=RUN_ID,
        snapshot_execution_version=count,
        snapshot_next_sequence=count,
        items=items,
        resume_cursor=(
            encode_run_event_cursor(items[-1]) if items else cursor
        ),
        has_more=has_more,
    )


class MemoryStreamStore:
    def __init__(
        self,
        events: tuple[DurableRunEventReadModel, ...],
        *,
        status: DurableRunStatus = DurableRunStatus.COMPLETED,
        owner_id: UUID = USER_ID,
    ) -> None:
        self.events = events
        self.status = status
        self.owner_id = owner_id
        self.read_cursors: list[str | None] = []

    def resolve_owned_session(
        self,
        *,
        run_id: UUID,
        user_id: UUID,
    ) -> UUID | None:
        return (
            SESSION_ID
            if run_id == RUN_ID and user_id == self.owner_id
            else None
        )

    def read_batch(
        self,
        *,
        run_id: UUID,
        session_id: UUID,
        user_id: UUID,
        cursor: str | None,
        limit: int,
    ) -> RunEventStreamBatch:
        assert run_id == RUN_ID
        assert session_id == SESSION_ID
        assert user_id == self.owner_id
        self.read_cursors.append(cursor)
        after_sequence = (
            decode_run_event_cursor(cursor).sequence
            if cursor is not None
            else -1
        )
        remaining = tuple(
            event
            for event in self.events
            if event.sequence > after_sequence
        )
        selected = remaining[:limit]
        return RunEventStreamBatch(
            page=_page(
                selected,
                cursor=cursor,
                has_more=len(remaining) > len(selected),
                total=len(self.events),
            ),
            run_status=self.status,
        )


class ScriptedStreamStore(MemoryStreamStore):
    def __init__(self, batches: list[RunEventStreamBatch]) -> None:
        super().__init__((), status=DurableRunStatus.RUNNING)
        self.batches = batches

    def read_batch(self, **kwargs: Any) -> RunEventStreamBatch:
        self.read_cursors.append(kwargs["cursor"])
        return self.batches.pop(0)


async def _never_disconnected() -> bool:
    return False


async def _collect(
    service: RunEventStreamService,
    *,
    cursor: str | None = None,
    limit: int = 100,
) -> list[str]:
    subscription = await service.prepare(
        run_id=RUN_ID,
        user_id=USER_ID,
        cursor=cursor,
        limit=limit,
    )
    return [
        frame
        async for frame in service.frames(
            subscription,
            disconnected=_never_disconnected,
        )
    ]


def _frame_event(frame: str) -> str:
    return next(
        line.removeprefix("event: ")
        for line in frame.splitlines()
        if line.startswith("event: ")
    )


def _frame_data(frame: str) -> dict[str, object]:
    value = next(
        line.removeprefix("data: ")
        for line in frame.splitlines()
        if line.startswith("data: ")
    )
    return json.loads(value)


def _frame_id(frame: str) -> str | None:
    return next(
        (
            line.removeprefix("id: ")
            for line in frame.splitlines()
            if line.startswith("id: ")
        ),
        None,
    )


def test_reconnect_resumes_exactly_after_persisted_cursor_across_service_restart() -> None:
    events = (_read_event(0), _read_event(1), _read_event(2))
    first_frames = asyncio.run(
        _collect(
            RunEventStreamService(MemoryStreamStore(events)),
            limit=1,
        )
    )
    event_frames = [
        frame for frame in first_frames if _frame_event(frame) == "run_event"
    ]
    assert [_frame_data(frame)["sequence"] for frame in event_frames] == [
        0,
        1,
        2,
    ]
    assert _frame_event(first_frames[-1]) == "complete"

    reconnect_cursor = _frame_id(event_frames[0])
    assert reconnect_cursor is not None
    restarted_store = MemoryStreamStore(events)
    resumed_frames = asyncio.run(
        _collect(
            RunEventStreamService(restarted_store),
            cursor=reconnect_cursor,
            limit=2,
        )
    )

    assert [
        _frame_data(frame)["sequence"]
        for frame in resumed_frames
        if _frame_event(frame) == "run_event"
    ] == [1, 2]
    assert restarted_store.read_cursors[0] == reconnect_cursor
    assert _frame_data(resumed_frames[-1])["resume_cursor"] == _frame_id(
        resumed_frames[-2]
    )


def test_out_of_order_or_duplicate_delivery_fails_closed_without_emitting_it() -> None:
    repeated_id = UUID("55555555-5555-4555-8555-555555555555")
    first = _read_event(0, event_id=repeated_id)
    duplicate = _read_event(1, event_id=repeated_id)
    batches = [
        RunEventStreamBatch(
            page=_page((first,), cursor=None, has_more=True, total=2),
            run_status=DurableRunStatus.RUNNING,
        ),
        RunEventStreamBatch(
            page=_page((duplicate,), cursor=encode_run_event_cursor(first), total=2),
            run_status=DurableRunStatus.COMPLETED,
        ),
    ]
    frames = asyncio.run(
        _collect(RunEventStreamService(ScriptedStreamStore(batches)))
    )

    assert [_frame_event(frame) for frame in frames] == [
        "run_event",
        "stream_error",
    ]
    assert _frame_data(frames[-1])["code"] == RUN_EVENT_STREAM_SAFE_ERROR_CODE
    assert "duplicate" not in frames[-1].lower()

    out_of_order = RunEventStreamBatch(
        page=_page((_read_event(1),), cursor=None, total=1),
        run_status=DurableRunStatus.COMPLETED,
    )
    out_of_order_frames = asyncio.run(
        _collect(
            RunEventStreamService(
                ScriptedStreamStore([out_of_order]),
            )
        )
    )
    assert [_frame_event(frame) for frame in out_of_order_frames] == [
        "stream_error"
    ]

    misaligned = _read_event(0).model_copy(
        update={"execution_version": 7},
    )
    misaligned_frames = asyncio.run(
        _collect(
            RunEventStreamService(
                ScriptedStreamStore(
                    [
                        RunEventStreamBatch(
                            page=_page(
                                (),
                                cursor=None,
                                total=1,
                            ).model_copy(
                                update={"items": (misaligned,)},
                            ),
                            run_status=DurableRunStatus.COMPLETED,
                        )
                    ]
                )
            )
        )
    )
    assert [_frame_event(frame) for frame in misaligned_frames] == [
        "stream_error"
    ]


def test_idle_stream_heartbeats_then_closes_when_terminal() -> None:
    clock = {"value": 0.0}

    async def advance(seconds: float) -> None:
        clock["value"] += seconds

    batches = [
        RunEventStreamBatch(
            page=_page((), cursor=None),
            run_status=DurableRunStatus.RUNNING,
        ),
        RunEventStreamBatch(
            page=_page((), cursor=None),
            run_status=DurableRunStatus.COMPLETED,
        ),
    ]
    frames = asyncio.run(
        _collect(
            RunEventStreamService(
                ScriptedStreamStore(batches),
                sleep=advance,
                monotonic=lambda: clock["value"],
                poll_seconds=1,
                heartbeat_seconds=1,
            )
        )
    )

    assert [_frame_event(frame) for frame in frames] == [
        "heartbeat",
        "complete",
    ]
    assert _frame_data(frames[0])["resume_cursor"] is None


def test_disconnect_stops_polling_without_synthetic_completion() -> None:
    store = ScriptedStreamStore(
        [
            RunEventStreamBatch(
                page=_page((_read_event(0),), cursor=None),
                run_status=DurableRunStatus.RUNNING,
            )
        ]
    )
    service = RunEventStreamService(store)

    async def scenario() -> list[str]:
        subscription = await service.prepare(
            run_id=RUN_ID,
            user_id=USER_ID,
            cursor=None,
        )
        checks = 0

        async def disconnected() -> bool:
            nonlocal checks
            checks += 1
            return checks > 2

        return [
            frame
            async for frame in service.frames(
                subscription,
                disconnected=disconnected,
            )
        ]

    frames = asyncio.run(scenario())

    assert [_frame_event(frame) for frame in frames] == ["run_event"]
    assert store.batches == []


def test_prepare_is_owner_scoped_and_rejects_crossed_cursor_before_read() -> None:
    events = (_read_event(0),)
    store = MemoryStreamStore(events)
    service = RunEventStreamService(store)

    with pytest.raises(RunEventStreamNotFound):
        asyncio.run(
            service.prepare(
                run_id=RUN_ID,
                user_id=UUID("99999999-9999-4999-8999-999999999999"),
                cursor=None,
            )
        )

    crossed_cursor = encode_run_event_cursor(
        _read_event(
            0,
            run_id=UUID("77777777-7777-4777-8777-777777777777"),
        )
    )
    with pytest.raises(RunEventStreamCursorError):
        asyncio.run(
            service.prepare(
                run_id=RUN_ID,
                user_id=USER_ID,
                cursor=crossed_cursor,
            )
        )
    assert store.read_cursors == []


def test_stream_contract_and_page_bounds_fail_closed() -> None:
    with pytest.raises(ValidationError):
        RunEventStreamControl(
            event="complete",
            run_id=RUN_ID,
        )
    with pytest.raises(ValidationError):
        RunEventStreamControl(
            event="stream_error",
            run_id=RUN_ID,
        )
    with pytest.raises(ValidationError):
        RunEventStreamControl(
            event="heartbeat",
            run_id=RUN_ID,
            code=RUN_EVENT_STREAM_SAFE_ERROR_CODE,
        )

    store = MemoryStreamStore((_read_event(0),))
    service = RunEventStreamService(store)
    for invalid_limit in (0, 201, True, 1.5):
        with pytest.raises((TypeError, ValueError)):
            asyncio.run(
                service.prepare(
                    run_id=RUN_ID,
                    user_id=USER_ID,
                    cursor=None,
                    limit=invalid_limit,
                )
            )
    assert store.read_cursors == []


class FakeEndpointStreamService:
    def __init__(self, *, prepare_error: Exception | None = None) -> None:
        self.prepare_error = prepare_error
        self.prepare_calls: list[dict[str, object]] = []

    async def prepare(self, **kwargs: object) -> object:
        self.prepare_calls.append(kwargs)
        if self.prepare_error is not None:
            raise self.prepare_error
        return object()

    async def frames(
        self,
        _subscription: object,
        *,
        disconnected: object,
    ):
        del disconnected
        yield (
            "event: complete\n"
            'data: {"schema_version":"1","status":"completed"}\n\n'
        )


def _stream_api(
    service: FakeEndpointStreamService,
    *,
    user_id: UUID = USER_ID,
) -> FastAPI:
    api = FastAPI()
    api.include_router(chat_runs.router)
    api.dependency_overrides[current_user] = lambda: CurrentUser(
        id=str(user_id),
        email="owner@example.com",
    )
    api.dependency_overrides[
        chat_runs.get_run_event_stream_service
    ] = lambda: service
    return api


def test_stream_endpoint_uses_last_event_id_and_safe_sse_headers(
    monkeypatch,
) -> None:
    monkeypatch.setattr(settings, "ask_ai_v2_api_enabled", True)
    monkeypatch.setattr(settings, "ask_ai_streaming_enabled", True)
    service = FakeEndpointStreamService()

    response = TestClient(_stream_api(service)).get(
        f"/chat/runs/{RUN_ID}/events?limit=17",
        headers={"Last-Event-ID": "opaque-resume-cursor"},
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.headers["cache-control"] == "no-cache, no-transform"
    assert response.headers["x-accel-buffering"] == "no"
    assert "event: complete" in response.text
    assert service.prepare_calls == [
        {
            "run_id": RUN_ID,
            "user_id": USER_ID,
            "cursor": "opaque-resume-cursor",
            "limit": 17,
        }
    ]


def test_stream_endpoint_fails_closed_for_flags_conflicts_and_owner_miss(
    monkeypatch,
) -> None:
    service = FakeEndpointStreamService()
    api = _stream_api(service)
    client = TestClient(api)
    monkeypatch.setattr(settings, "ask_ai_v2_api_enabled", True)
    monkeypatch.setattr(settings, "ask_ai_streaming_enabled", False)
    assert client.get(f"/chat/runs/{RUN_ID}/events").status_code == 404

    monkeypatch.setattr(settings, "ask_ai_streaming_enabled", True)
    conflict = client.get(
        f"/chat/runs/{RUN_ID}/events?cursor=one",
        headers={"Last-Event-ID": "two"},
    )
    assert conflict.status_code == 422
    assert "one" not in conflict.text
    assert "two" not in conflict.text

    hidden = FakeEndpointStreamService(
        prepare_error=RunEventStreamNotFound("hidden owner mismatch")
    )
    missing = TestClient(_stream_api(hidden)).get(
        f"/chat/runs/{RUN_ID}/events"
    )
    assert missing.status_code == 404
    assert missing.json() == {"detail": "Run not found"}

    unavailable = FakeEndpointStreamService(
        prepare_error=RunEventStreamError("database DSN detail")
    )
    failed = TestClient(_stream_api(unavailable)).get(
        f"/chat/runs/{RUN_ID}/events"
    )
    assert failed.status_code == 503
    assert failed.json() == {"detail": "Run event stream unavailable"}
    assert "DSN" not in failed.text

    unauthenticated = FastAPI()
    unauthenticated.include_router(chat_runs.router)
    assert (
        TestClient(unauthenticated)
        .get(f"/chat/runs/{RUN_ID}/events")
        .status_code
        == 401
    )
