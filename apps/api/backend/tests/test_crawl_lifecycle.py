"""Phase 1 crawl lifecycle: HTTP trigger queues a run; background executor owns it."""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock

import pytest
from fastapi import BackgroundTasks, FastAPI
from fastapi.testclient import TestClient

from backend.api.auth import CurrentUser, admin_user
from backend.api.routes import admin
from backend.pipeline import run_once


ADMIN = CurrentUser(
    id="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
    email="admin@example.com",
    role="admin",
)


class RecordingBackgroundTasks(BackgroundTasks):
    def __init__(self) -> None:
        super().__init__()
        self.recorded: list[tuple[Any, tuple[Any, ...], dict[str, Any]]] = []

    def add_task(self, func: Any, *args: Any, **kwargs: Any) -> None:  # type: ignore[override]
        self.recorded.append((func, args, kwargs))


@pytest.fixture
def crawl_app() -> FastAPI:
    app = FastAPI()
    app.include_router(admin.router)
    app.dependency_overrides[admin_user] = lambda: ADMIN
    return app


def test_admin_source_crawl_creates_one_queued_run_and_schedules_background(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    create_calls: list[str] = []
    recorded = RecordingBackgroundTasks()

    def fake_create() -> int:
        create_calls.append("create")
        return 101

    monkeypatch.setattr(run_once, "create_crawl_run", fake_create)

    payload = asyncio.run(
        admin.crawl_source(
            source_id=2,
            user=ADMIN,
            background_tasks=recorded,
        )
    )

    assert payload["run_id"] == 101
    assert payload["status"] == "queued"
    assert create_calls == ["create"]
    assert len(recorded.recorded) == 1
    func, args, kwargs = recorded.recorded[0]
    assert func is run_once.execute_crawl_run
    assert args == (101,)
    assert kwargs == {"source_id": 2, "page_id": None}


def test_admin_page_crawl_http_returns_queued_without_awaiting_executor(
    crawl_app: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Intercept BackgroundTasks.add_task so TestClient cannot await the crawl."""

    create_calls: list[int] = []
    scheduled: list[tuple[Any, tuple[Any, ...], dict[str, Any]]] = []

    def fake_create() -> int:
        create_calls.append(1)
        return 55

    def capture_add_task(self: BackgroundTasks, func: Any, *args: Any, **kwargs: Any) -> None:
        scheduled.append((func, args, kwargs))

    monkeypatch.setattr(run_once, "create_crawl_run", fake_create)
    monkeypatch.setattr(BackgroundTasks, "add_task", capture_add_task)

    with TestClient(crawl_app) as client:
        response = client.post("/admin/sources/7/crawl")

    assert response.status_code == 200
    body = response.json()
    assert body["run_id"] == 55
    assert body["status"] == "queued"
    assert body["docs_found"] == 0
    assert create_calls == [1]
    assert len(scheduled) == 1
    assert scheduled[0][0] is run_once.execute_crawl_run
    assert scheduled[0][1] == (55,)
    assert scheduled[0][2] == {"source_id": 7, "page_id": None}


def test_execute_crawl_run_transitions_queued_running_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    transitions: list[str] = []

    monkeypatch.setattr(
        run_once,
        "mark_crawl_run_running",
        lambda run_id: transitions.append(f"running:{run_id}"),
    )

    async def fake_stages(run_id: int | None, **kwargs: Any) -> dict:
        transitions.append(f"stages:{run_id}")
        return {
            "run_id": run_id,
            "status": "success",
            "sources_attempted": 1,
            "pages_attempted": 1,
            "sources_succeeded": 1,
            "pages_succeeded": 1,
            "docs_found": 2,
            "primary_docs_found": 2,
            "new_events": 1,
            "checkpoints_advanced": 1,
            "notification_message_id": None,
            "errors": [],
        }

    monkeypatch.setattr(run_once, "_run_crawl_stages", fake_stages)

    result = asyncio.run(run_once.execute_crawl_run(42, source_id=2))
    assert result["status"] == "success"
    assert result["run_id"] == 42
    assert transitions == ["running:42", "stages:42"]


def test_execute_crawl_run_failed_when_stages_fail(monkeypatch: pytest.MonkeyPatch) -> None:
    finalized: list[dict[str, Any]] = []

    monkeypatch.setattr(run_once, "mark_crawl_run_running", lambda run_id: None)

    async def boom(run_id: int | None, **kwargs: Any) -> dict:
        raise RuntimeError("stage exploded")

    def fake_finalize(run_id: int | None, **kwargs: Any) -> None:
        finalized.append({"run_id": run_id, **kwargs})

    monkeypatch.setattr(run_once, "_run_crawl_stages", boom)
    monkeypatch.setattr(run_once, "finalize_crawl_run", fake_finalize)

    with pytest.raises(RuntimeError, match="stage exploded"):
        asyncio.run(run_once.execute_crawl_run(9, page_id=3))

    assert len(finalized) == 1
    assert finalized[0]["run_id"] == 9
    assert finalized[0]["status"] == "failed"


def test_execute_crawl_run_partial_status_preserved(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(run_once, "mark_crawl_run_running", lambda run_id: None)

    async def partial_stages(run_id: int | None, **kwargs: Any) -> dict:
        return {
            "run_id": run_id,
            "status": "partial",
            "sources_attempted": 2,
            "pages_attempted": 2,
            "sources_succeeded": 1,
            "pages_succeeded": 1,
            "docs_found": 1,
            "primary_docs_found": 1,
            "new_events": 0,
            "checkpoints_advanced": 1,
            "notification_message_id": None,
            "errors": [{"source": "cerc", "error": "timeout"}],
        }

    monkeypatch.setattr(run_once, "_run_crawl_stages", partial_stages)
    result = asyncio.run(run_once.execute_crawl_run(11, source_id=1))
    assert result["status"] == "partial"
    assert result["run_id"] == 11


def test_cancelled_error_finalizes_failed_and_reraises(monkeypatch: pytest.MonkeyPatch) -> None:
    finalized: list[dict[str, Any]] = []
    monkeypatch.setattr(run_once, "mark_crawl_run_running", lambda run_id: None)

    async def cancelled(run_id: int | None, **kwargs: Any) -> dict:
        raise asyncio.CancelledError()

    def fake_finalize(run_id: int | None, **kwargs: Any) -> None:
        finalized.append({"run_id": run_id, **kwargs})

    monkeypatch.setattr(run_once, "_run_crawl_stages", cancelled)
    monkeypatch.setattr(run_once, "finalize_crawl_run", fake_finalize)

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(run_once.execute_crawl_run(77))

    assert finalized[0]["run_id"] == 77
    assert finalized[0]["status"] == "failed"
    assert "CancelledError" in finalized[0]["errors"][0]["error"]


def test_http_cancellation_does_not_cancel_background_executor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Caller task cancel must not prevent an independent executor from finishing."""

    states: list[str] = []
    monkeypatch.setattr(
        run_once,
        "mark_crawl_run_running",
        lambda run_id: states.append(f"running:{run_id}"),
    )

    async def slow_success(run_id: int | None, **kwargs: Any) -> dict:
        await asyncio.sleep(0.05)
        states.append(f"done:{run_id}")
        return {
            "run_id": run_id,
            "status": "success",
            "sources_attempted": 1,
            "pages_attempted": 1,
            "sources_succeeded": 1,
            "pages_succeeded": 1,
            "docs_found": 0,
            "primary_docs_found": 0,
            "new_events": 0,
            "checkpoints_advanced": 0,
            "notification_message_id": None,
            "errors": [],
        }

    monkeypatch.setattr(run_once, "_run_crawl_stages", slow_success)

    async def scenario() -> dict:
        run_id = 88
        background = asyncio.create_task(run_once.execute_crawl_run(run_id, source_id=2))

        async def fake_http_handler() -> dict:
            return {"run_id": run_id, "status": "queued"}

        http_task = asyncio.create_task(fake_http_handler())
        payload = await http_task
        http_task.cancel()
        assert payload["status"] == "queued"
        result = await background
        return result

    result = asyncio.run(scenario())
    assert result["status"] == "success"
    assert result["run_id"] == 88
    assert states == ["running:88", "done:88"]


def test_run_crawl_creates_single_run_and_reuses_it(monkeypatch: pytest.MonkeyPatch) -> None:
    create_calls: list[int] = []
    seen_ids: list[int] = []

    def fake_create() -> int:
        create_calls.append(1)
        return 123

    monkeypatch.setattr(run_once, "create_crawl_run", fake_create)
    monkeypatch.setattr(run_once, "mark_crawl_run_running", lambda run_id: seen_ids.append(run_id))

    async def fake_stages(run_id: int | None, **kwargs: Any) -> dict:
        seen_ids.append(int(run_id or 0))
        return {
            "run_id": run_id,
            "status": "success",
            "sources_attempted": 0,
            "pages_attempted": 0,
            "sources_succeeded": 0,
            "pages_succeeded": 0,
            "docs_found": 0,
            "primary_docs_found": 0,
            "new_events": 0,
            "checkpoints_advanced": 0,
            "notification_message_id": None,
            "errors": [],
        }

    monkeypatch.setattr(run_once, "_run_crawl_stages", fake_stages)

    result = asyncio.run(run_once.run_crawl(source_id=1))
    assert result["run_id"] == 123
    assert create_calls == [1]
    assert seen_ids == [123, 123]


def test_queue_crawl_run_does_not_execute_stages(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(run_once, "create_crawl_run", lambda: 5)
    stages = AsyncMock(return_value={"status": "success"})
    monkeypatch.setattr(run_once, "_run_crawl_stages", stages)
    monkeypatch.setattr(run_once, "mark_crawl_run_running", lambda run_id: None)

    payload = run_once.queue_crawl_run(source_id=9)
    assert payload["run_id"] == 5
    assert payload["status"] == "queued"
    stages.assert_not_awaited()


def test_queue_crawl_run_raises_when_create_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(run_once, "create_crawl_run", lambda: None)
    with pytest.raises(RuntimeError, match="Failed to create crawl_run"):
        run_once.queue_crawl_run(source_id=1)
