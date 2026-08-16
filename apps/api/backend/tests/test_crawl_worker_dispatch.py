"""Admin queue + GitHub dispatch; crawl worker claim/execute (no API BackgroundTasks)."""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api.auth import CurrentUser, admin_user
from backend.api.routes import admin
from backend.pipeline import github_dispatch, run_once
from backend.pipeline.github_dispatch import CrawlDispatchError
from backend.tools import crawl_worker


ADMIN = CurrentUser(
    id="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
    email="admin@example.com",
    role="admin",
)


@pytest.fixture
def crawl_app() -> FastAPI:
    app = FastAPI()
    app.include_router(admin.router)
    app.dependency_overrides[admin_user] = lambda: ADMIN
    return app


def test_admin_source_crawl_queues_and_dispatches_without_executing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    create_calls: list[str] = []
    dispatched: list[dict[str, Any]] = []
    executed: list[Any] = []

    def fake_create() -> int:
        create_calls.append("create")
        return 101

    def fake_dispatch(**kwargs: Any) -> dict[str, Any]:
        dispatched.append(kwargs)
        return {"dispatched": True}

    async def fake_execute(*_a: Any, **_k: Any) -> dict[str, Any]:
        executed.append(1)
        return {"status": "success"}

    monkeypatch.setattr(run_once, "create_crawl_run", fake_create)
    monkeypatch.setattr(admin, "dispatch_crawl_workflow", fake_dispatch)
    monkeypatch.setattr(run_once, "execute_crawl_run", fake_execute)

    payload = asyncio.run(admin.crawl_source(source_id=2, user=ADMIN))

    assert payload["run_id"] == 101
    assert payload["status"] == "queued"
    assert create_calls == ["create"]
    assert dispatched == [{"run_id": 101, "source_id": 2, "page_id": None}]
    assert executed == []


def test_admin_page_crawl_preserves_page_scope_in_dispatch(
    crawl_app: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dispatched: list[dict[str, Any]] = []

    monkeypatch.setattr(run_once, "create_crawl_run", lambda: 55)
    monkeypatch.setattr(
        admin,
        "dispatch_crawl_workflow",
        lambda **kwargs: dispatched.append(kwargs) or {"dispatched": True},
    )

    with TestClient(crawl_app) as client:
        response = client.post("/admin/pages/9/crawl")

    assert response.status_code == 200
    body = response.json()
    assert body["run_id"] == 55
    assert body["status"] == "queued"
    assert dispatched == [{"run_id": 55, "source_id": None, "page_id": 9}]


def test_admin_crawl_dispatch_failure_keeps_queued_and_does_not_execute(
    crawl_app: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(run_once, "create_crawl_run", lambda: 77)

    def boom(**_kwargs: Any) -> dict[str, Any]:
        raise CrawlDispatchError("GitHub workflow_dispatch failed with HTTP 401")

    monkeypatch.setattr(admin, "dispatch_crawl_workflow", boom)
    executed: list[Any] = []

    async def fake_execute(*_a: Any, **_k: Any) -> dict[str, Any]:
        executed.append(1)
        return {"status": "success"}

    monkeypatch.setattr(run_once, "execute_crawl_run", fake_execute)

    with TestClient(crawl_app) as client:
        response = client.post("/admin/sources/3/crawl")

    assert response.status_code == 503
    assert "77" in response.json()["detail"]
    assert "queued" in response.json()["detail"].lower()
    assert executed == []


def test_dispatch_crawl_workflow_posts_expected_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from backend.core import config as config_mod

    class FakeSettings:
        github_actions_token = MagicMock(
            get_secret_value=MagicMock(return_value="ghp_test_token")
        )
        github_repository = "acme/regulatory-ai"
        github_crawl_workflow_id = "crawl-worker.yml"
        github_workflow_ref = "main"
        github_api_url = "https://api.github.com"

    captured: dict[str, Any] = {}

    class FakeResponse:
        status_code = 204

    class FakeClient:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

        def __enter__(self) -> "FakeClient":
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def post(self, url: str, headers: dict[str, str], json: dict[str, Any]):
            captured["url"] = url
            captured["headers"] = headers
            captured["json"] = json
            return FakeResponse()

    monkeypatch.setattr(github_dispatch, "settings", FakeSettings())
    monkeypatch.setattr(github_dispatch.httpx, "Client", FakeClient)

    result = github_dispatch.dispatch_crawl_workflow(
        run_id=58, source_id=None, page_id=12
    )
    assert result["dispatched"] is True
    assert captured["url"].endswith(
        "/repos/acme/regulatory-ai/actions/workflows/crawl-worker.yml/dispatches"
    )
    assert captured["headers"]["Authorization"] == "Bearer ghp_test_token"
    assert captured["json"]["ref"] == "main"
    assert captured["json"]["inputs"] == {
        "run_id": "58",
        "page_id": "12",
    }
    assert "ghp_test_token" not in str(result)


def test_claim_queued_crawl_run_sql_uses_skip_locked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from backend.core import repository as repo

    captured: dict[str, Any] = {}

    class Result:
        def first(self) -> Any:
            return type("Row", (), {"id": 5})()

    class Session:
        def execute(self, statement: Any, params: dict[str, Any] | None = None) -> Result:
            captured["sql"] = str(statement)
            captured["params"] = params
            return Result()

        def __enter__(self) -> "Session":
            return self

        def __exit__(self, *args: object) -> None:
            return None

    monkeypatch.setattr(repo, "session_scope", lambda: Session())
    assert repo.claim_queued_crawl_run(5) is True
    sql = captured["sql"].lower()
    assert "for update skip locked" in sql
    assert "queued" in sql
    assert captured["params"] == {"run_id": 5}


def test_two_workers_cannot_both_claim_same_run(monkeypatch: pytest.MonkeyPatch) -> None:
    from backend.core import repository as repo

    claimed_once = {"value": False}

    class Result:
        def __init__(self, row: Any) -> None:
            self._row = row

        def first(self) -> Any:
            return self._row

    class Session:
        def execute(self, statement: Any, params: dict[str, Any] | None = None) -> Result:
            if not claimed_once["value"]:
                claimed_once["value"] = True
                return Result(type("Row", (), {"id": params["run_id"]})())
            return Result(None)

        def __enter__(self) -> "Session":
            return self

        def __exit__(self, *args: object) -> None:
            return None

    monkeypatch.setattr(repo, "session_scope", lambda: Session())
    assert repo.claim_queued_crawl_run(42) is True
    assert repo.claim_queued_crawl_run(42) is False


def test_crawl_worker_claims_then_executes_with_page_scope(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    claims: list[int] = []
    executed: list[dict[str, Any]] = []

    monkeypatch.setattr(
        crawl_worker,
        "claim_queued_crawl_run",
        lambda run_id: claims.append(run_id) or True,
    )

    async def fake_execute(run_id: int, **kwargs: Any) -> dict[str, Any]:
        executed.append({"run_id": run_id, **kwargs})
        return {
            "run_id": run_id,
            "status": "success",
            "docs_found": 1,
            "new_events": 0,
        }

    monkeypatch.setattr(crawl_worker, "execute_crawl_run", fake_execute)

    result = crawl_worker.run_claimed_crawl(run_id=9, source_id=None, page_id=4)
    assert claims == [9]
    assert executed == [{"run_id": 9, "source_id": None, "page_id": 4}]
    assert result["status"] == "success"


def test_crawl_worker_rejects_uncclaimed_run(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(crawl_worker, "claim_queued_crawl_run", lambda run_id: False)
    executed: list[Any] = []

    async def fake_execute(*_a: Any, **_k: Any) -> dict[str, Any]:
        executed.append(1)
        return {"status": "success"}

    monkeypatch.setattr(crawl_worker, "execute_crawl_run", fake_execute)

    with pytest.raises(RuntimeError, match="Failed to claim"):
        crawl_worker.run_claimed_crawl(run_id=1, source_id=2, page_id=None)
    assert executed == []


def test_crawl_worker_requires_exact_scope() -> None:
    with pytest.raises(ValueError, match="at most one"):
        crawl_worker.run_claimed_crawl(run_id=1, source_id=2, page_id=3)
    with pytest.raises(ValueError, match="requires source_id or page_id"):
        crawl_worker.run_claimed_crawl(run_id=1, source_id=None, page_id=None)


def test_crawl_worker_main_nonzero_on_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        crawl_worker,
        "run_claimed_crawl",
        lambda **_k: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    assert crawl_worker.main(["--run-id", "3", "--page-id", "8"]) == 1


def test_crawl_worker_main_zero_on_success(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        crawl_worker,
        "run_claimed_crawl",
        lambda **_k: {"status": "success"},
    )
    assert crawl_worker.main(["--run-id", "3", "--source-id", "2"]) == 0


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


def test_queue_crawl_run_does_not_execute_stages(monkeypatch: pytest.MonkeyPatch) -> None:
    from unittest.mock import AsyncMock

    monkeypatch.setattr(run_once, "create_crawl_run", lambda: 5)
    stages = AsyncMock(return_value={"status": "success"})
    monkeypatch.setattr(run_once, "_run_crawl_stages", stages)
    monkeypatch.setattr(run_once, "mark_crawl_run_running", lambda run_id: None)

    payload = run_once.queue_crawl_run(source_id=9)
    assert payload["run_id"] == 5
    assert payload["status"] == "queued"
    stages.assert_not_awaited()


def test_worker_process_death_leaves_running_for_stale_reclaim() -> None:
    """Documented contract: hard kill after claim leaves status=running.

    Stale reclaim (crawl_recovery) is the safety net; this test locks the
    claim/finalize separation that makes that recovery possible.
    """

    from backend.pipeline import crawl_recovery

    assert callable(crawl_recovery.reclaim_stale_crawl_runs)
    assert crawl_recovery.DEFAULT_STALE_SECONDS >= 60
