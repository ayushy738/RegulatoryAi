"""Permanent delete lifecycle for retired source_pages only."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI, status
from fastapi.testclient import TestClient

from backend.api.auth import CurrentUser, admin_user, current_user
from backend.api.routes import admin
from backend.core import repository
from backend.core.source_page_policy import (
    SourceDeleteBlockedError,
    SourcePagePermanentDeleteError,
)


ADMIN = CurrentUser(
    id="bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
    email="admin@example.com",
    role="admin",
)
USER = CurrentUser(
    id="cccccccc-cccc-4ccc-8ccc-cccccccccccc",
    email="user@example.com",
    role="user",
)
NOW = datetime(2026, 8, 17, 12, 0, tzinfo=UTC)


def _mappings(rows: list[dict[str, Any]]):
    class _Mappings:
        def __init__(self, values: list[dict[str, Any]]):
            self._rows = values

        def __iter__(self):
            return iter(self._rows)

        def first(self):
            return self._rows[0] if self._rows else None

    return _Mappings(rows)


class _Result:
    def __init__(self, rows: list[dict[str, Any]] | None = None, first_row=None):
        self._rows = rows or []
        self._first = first_row if first_row is not None else (self._rows[0] if self._rows else None)

    def mappings(self):
        return _mappings(self._rows)

    def first(self):
        return self._first


def test_active_page_cannot_be_permanently_deleted(monkeypatch) -> None:
    def fake_execute(statement, params=None):
        sql = str(statement).lower()
        if "from source_pages" in sql and "select id, source_id" in sql:
            return _Result(
                [
                    {
                        "id": 84,
                        "source_id": 19,
                        "name": "Draft",
                        "url": "https://gercin.org/draft",
                        "deleted_at": None,
                    }
                ]
            )
        raise AssertionError("hard delete must not run for active pages")

    session = MagicMock()
    session.execute.side_effect = fake_execute

    @contextmanager
    def fake_scope():
        yield session

    monkeypatch.setattr(repository, "session_scope", fake_scope)
    with pytest.raises(SourcePagePermanentDeleteError, match="Only retired"):
        repository.permanently_delete_source_page(84, actor_id=ADMIN.id)


def test_retired_page_can_be_permanently_deleted(monkeypatch) -> None:
    events: list[tuple[str, dict[str, Any]]] = []
    sql_seen: list[str] = []

    def fake_execute(statement, params=None):
        sql = str(statement).lower()
        sql_seen.append(sql)
        if "from source_pages" in sql and "select id, source_id" in sql:
            return _Result(
                [
                    {
                        "id": 84,
                        "source_id": 19,
                        "name": "Draft",
                        "url": "https://gercin.org/draft",
                        "deleted_at": NOW,
                    }
                ]
            )
        if "delete from source_pages" in sql:
            assert "deleted_at is not null" in sql
            assert params["page_id"] == 84
            return _Result(
                [{"id": 84, "source_id": 19, "name": "Draft", "url": "https://gercin.org/draft"}]
            )
        raise AssertionError(sql)

    session = MagicMock()
    session.execute.side_effect = fake_execute

    @contextmanager
    def fake_scope():
        yield session

    monkeypatch.setattr(repository, "session_scope", fake_scope)
    monkeypatch.setattr(
        repository,
        "log_event",
        lambda name, **kwargs: events.append((name, kwargs)),
    )

    result = repository.permanently_delete_source_page(84, actor_id=ADMIN.id)
    assert result["deleted"] is True
    assert result["page_id"] == 84
    assert any("delete from source_pages" in sql for sql in sql_seen)
    assert not any("delete from documents" in sql for sql in sql_seen)
    assert not any("delete from events" in sql for sql in sql_seen)
    assert not any("delete from document_versions" in sql for sql in sql_seen)
    assert not any("delete from crawl_runs" in sql for sql in sql_seen)
    assert not any("delete from document_chunks" in sql for sql in sql_seen)
    assert events[0][0] == "source_page_permanently_deleted"
    assert events[0][1]["operation"] == "permanent_delete"
    assert events[0][1]["actor_id"] == ADMIN.id
    assert "deleted_by" not in events[0][1]


def test_missing_page_permanent_delete_returns_not_deleted(monkeypatch) -> None:
    session = MagicMock()
    session.execute.return_value = _Result([])

    @contextmanager
    def fake_scope():
        yield session

    monkeypatch.setattr(repository, "session_scope", fake_scope)
    result = repository.permanently_delete_source_page(999, actor_id=ADMIN.id)
    assert result["deleted"] is False
    assert result["page"] is None


def test_delete_source_blocked_when_pages_remain(monkeypatch) -> None:
    def fake_execute(statement, params=None):
        sql = str(statement).lower()
        if "from source_pages" in sql and "count(*)" in sql:
            return _Result([{"active_pages": 1, "retired_pages": 0}])
        raise AssertionError("source hard delete must not run while pages remain")

    session = MagicMock()
    session.execute.side_effect = fake_execute

    @contextmanager
    def fake_scope():
        yield session

    monkeypatch.setattr(repository, "session_scope", fake_scope)
    with pytest.raises(SourceDeleteBlockedError, match="source pages remain"):
        repository.delete_source(19)


def test_delete_source_blocked_when_only_retired_pages_remain(monkeypatch) -> None:
    def fake_execute(statement, params=None):
        sql = str(statement).lower()
        if "from source_pages" in sql and "count(*)" in sql:
            return _Result([{"active_pages": 0, "retired_pages": 2}])
        raise AssertionError("source hard delete must not cascade retired pages")

    session = MagicMock()
    session.execute.side_effect = fake_execute

    @contextmanager
    def fake_scope():
        yield session

    monkeypatch.setattr(repository, "session_scope", fake_scope)
    with pytest.raises(SourceDeleteBlockedError, match="2 retired"):
        repository.delete_source(19)


def test_delete_source_allowed_when_no_pages(monkeypatch) -> None:
    def fake_execute(statement, params=None):
        sql = str(statement).lower()
        if "from source_pages" in sql and "count(*)" in sql:
            return _Result([{"active_pages": 0, "retired_pages": 0}])
        if "delete from sources" in sql:
            return _Result(first_row=(19,))
        raise AssertionError(sql)

    session = MagicMock()
    session.execute.side_effect = fake_execute

    @contextmanager
    def fake_scope():
        yield session

    monkeypatch.setattr(repository, "session_scope", fake_scope)
    assert repository.delete_source(19) == {"source_id": 19, "deleted": True}


def test_fk_restrict_migration_exists() -> None:
    from pathlib import Path

    migration = (
        Path(__file__).resolve().parents[1] / "migrations" / "0052_source_pages_fk_restrict.sql"
    )
    text = migration.read_text(encoding="utf-8").lower()
    assert "on delete restrict" in text
    assert "source_pages_source_id_fkey" in text
    # Ensure the recreated FK is restrict, not cascade.
    assert "on delete cascade" not in text


@pytest.fixture
def permanent_app() -> FastAPI:
    app = FastAPI()
    app.include_router(admin.router)
    app.dependency_overrides[admin_user] = lambda: ADMIN
    return app


def test_admin_permanent_delete_endpoint(
    permanent_app: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: list[dict[str, Any]] = []

    def fake_permanent(page_id: int, *, actor_id: str):
        seen.append({"page_id": page_id, "actor_id": actor_id})
        return {
            "page_id": page_id,
            "source_id": 19,
            "deleted": True,
            "page": {"id": page_id, "source_id": 19, "name": "Draft", "url": "https://x"},
        }

    monkeypatch.setattr(admin, "permanently_delete_source_page", fake_permanent)
    with TestClient(permanent_app) as client:
        response = client.delete("/admin/pages/84/permanent")
    assert response.status_code == 200
    assert seen == [{"page_id": 84, "actor_id": ADMIN.id}]


def test_admin_permanent_delete_rejects_active(
    permanent_app: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def boom(page_id: int, *, actor_id: str):
        raise SourcePagePermanentDeleteError(
            "Only retired source pages can be permanently deleted."
        )

    monkeypatch.setattr(admin, "permanently_delete_source_page", boom)
    with TestClient(permanent_app) as client:
        response = client.delete("/admin/pages/84/permanent")
    assert response.status_code == 409
    assert "Only retired" in response.json()["detail"]


def test_admin_permanent_delete_missing_404(
    permanent_app: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        admin,
        "permanently_delete_source_page",
        lambda page_id, *, actor_id: {
            "page_id": page_id,
            "source_id": None,
            "deleted": False,
            "page": None,
        },
    )
    with TestClient(permanent_app) as client:
        response = client.delete("/admin/pages/999/permanent")
    assert response.status_code == 404


def test_non_admin_cannot_permanently_delete() -> None:
    app = FastAPI()
    app.include_router(admin.router)
    app.dependency_overrides[current_user] = lambda: USER
    with TestClient(app) as client:
        response = client.delete("/admin/pages/84/permanent")
    assert response.status_code == status.HTTP_403_FORBIDDEN


def test_soft_delete_endpoint_unchanged(
    permanent_app: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        admin,
        "delete_source_page",
        lambda page_id, *, deleted_by: {
            "page_id": page_id,
            "source_id": 19,
            "deleted": True,
            "retired": True,
            "already_retired": False,
            "page": {"id": page_id, "deleted_at": NOW.isoformat(), "deleted_by": deleted_by},
        },
    )
    with TestClient(permanent_app) as client:
        response = client.delete("/admin/pages/84")
    assert response.status_code == 200
    assert response.json()["retired"] is True
