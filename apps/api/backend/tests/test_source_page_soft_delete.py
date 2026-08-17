"""Soft-delete / restore semantics for monitored source_pages."""

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
from backend.core.models import SourcePagePayload
from backend.core.source_page_policy import SourcePageConflictError


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
RETIRED_URL = "https://gercin.org/regulations/draft_regulations"


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
    def __init__(self, rows: list[dict[str, Any]]):
        self._rows = rows

    def mappings(self):
        return _mappings(self._rows)

    def first(self):
        return self._rows[0] if self._rows else None


def _page(
    *,
    page_id: int = 84,
    source_id: int = 19,
    enabled: bool = True,
    deleted_at: datetime | None = None,
    deleted_by: str | None = None,
    url: str = RETIRED_URL,
) -> dict[str, Any]:
    return {
        "id": page_id,
        "source_id": source_id,
        "name": "Draft Regulations",
        "url": url,
        "page_type": "listing",
        "priority": 30,
        "enabled": enabled,
        "last_crawled_at": None,
        "created_at": NOW,
        "updated_at": NOW,
        "deleted_at": deleted_at,
        "deleted_by": deleted_by,
    }


def test_new_page_has_null_deleted_at(monkeypatch) -> None:
    stored: list[dict[str, Any]] = []

    def fake_execute(statement, params=None):
        sql = str(statement).lower()
        if "from sources" in sql:
            return _Result(
                [{"id": 19, "url": "https://gercin.org/", "allowed_domains": ["gercin.org"]}]
            )
        if "from source_pages" in sql and "select id, url" in sql:
            return _Result([])
        if "insert into source_pages" in sql:
            row = _page(page_id=3, deleted_at=None, deleted_by=None)
            row.update(
                {
                    "name": params["name"],
                    "url": params["url"],
                    "page_type": params["page_type"],
                    "priority": params["priority"],
                    "enabled": params["enabled"],
                }
            )
            stored.append(row)
            return _Result([row])
        raise AssertionError(sql)

    session = MagicMock()
    session.execute.side_effect = fake_execute

    @contextmanager
    def fake_scope():
        yield session

    monkeypatch.setattr(repository, "session_scope", fake_scope)
    page = repository.create_source_page(
        19,
        SourcePagePayload(
            name="Draft Regulations",
            url=RETIRED_URL,
            page_type="listing",
            priority=30,
            enabled=True,
        ),
    )
    assert page["deleted_at"] is None
    assert page["deleted_by"] is None
    assert stored[0]["deleted_at"] is None


def test_list_enabled_requires_deleted_at_null(monkeypatch) -> None:
    session = MagicMock()
    session.execute.return_value.mappings.return_value = _mappings([])

    @contextmanager
    def fake_scope():
        yield session

    monkeypatch.setattr(repository, "session_scope", fake_scope)
    assert repository.list_enabled_source_pages(source_id=19) == []
    sql = str(session.execute.call_args.args[0]).lower()
    assert "sp.deleted_at is null" in sql
    assert "s.enabled = true" in sql
    assert "sp.enabled = true" in sql
    assert "allowed_source_page_urls" not in sql


def test_soft_deleted_page_not_selected_even_if_enabled(monkeypatch) -> None:
    """Selection SQL excludes soft-deleted rows; DB would not return them."""

    session = MagicMock()
    session.execute.return_value.mappings.return_value = _mappings([])

    @contextmanager
    def fake_scope():
        yield session

    monkeypatch.setattr(repository, "session_scope", fake_scope)
    pages = repository.list_enabled_source_pages(page_id=84)
    assert pages == []
    sql = str(session.execute.call_args.args[0]).lower()
    assert "sp.deleted_at is null" in sql


def test_retire_records_deleted_at_and_deleted_by(monkeypatch) -> None:
    events: list[tuple[str, dict[str, Any]]] = []
    retired = _page(deleted_at=NOW, deleted_by=ADMIN.id)

    def fake_execute(statement, params=None):
        sql = str(statement).lower()
        if "select id, source_id, deleted_at" in sql:
            return _Result([{"id": 84, "source_id": 19, "deleted_at": None}])
        if "update source_pages" in sql and "deleted_at = now()" in sql:
            assert params["deleted_by"] == ADMIN.id
            return _Result([retired])
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

    result = repository.retire_source_page(84, deleted_by=ADMIN.id)
    assert result["retired"] is True
    assert result["already_retired"] is False
    assert result["page"]["deleted_at"] == NOW
    assert result["page"]["deleted_by"] == ADMIN.id
    assert events[0][0] == "source_page_retired"
    assert events[0][1]["source_page_id"] == 84
    assert events[0][1]["deleted_by"] == ADMIN.id


def test_retire_is_idempotent(monkeypatch) -> None:
    existing = _page(deleted_at=NOW, deleted_by=ADMIN.id)

    def fake_execute(statement, params=None):
        sql = str(statement).lower()
        if "select id, source_id, deleted_at" in sql:
            return _Result([{"id": 84, "source_id": 19, "deleted_at": NOW}])
        if "from source_pages" in sql and "where id" in sql:
            return _Result([existing])
        raise AssertionError(sql)

    session = MagicMock()
    session.execute.side_effect = fake_execute

    @contextmanager
    def fake_scope():
        yield session

    monkeypatch.setattr(repository, "session_scope", fake_scope)
    result = repository.retire_source_page(84, deleted_by=ADMIN.id)
    assert result["retired"] is True
    assert result["already_retired"] is True
    assert result["page"]["id"] == 84


def test_restore_clears_markers_without_changing_enabled(monkeypatch) -> None:
    events: list[tuple[str, dict[str, Any]]] = []
    restored = _page(enabled=False, deleted_at=None, deleted_by=None)

    def fake_execute(statement, params=None):
        sql = str(statement).lower()
        if "select id, source_id, deleted_at, enabled" in sql:
            return _Result(
                [{"id": 84, "source_id": 19, "deleted_at": NOW, "enabled": False}]
            )
        if "update source_pages" in sql and "deleted_at = null" in sql:
            return _Result([restored])
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

    result = repository.restore_source_page(84)
    assert result["restored"] is True
    assert result["already_active"] is False
    assert result["page"]["enabled"] is False
    assert result["page"]["deleted_at"] is None
    assert result["page"]["deleted_by"] is None
    assert events[0][0] == "source_page_restored"


def test_restore_is_idempotent_when_already_active(monkeypatch) -> None:
    active = _page(deleted_at=None, deleted_by=None)

    def fake_execute(statement, params=None):
        sql = str(statement).lower()
        if "select id, source_id, deleted_at, enabled" in sql:
            return _Result(
                [{"id": 84, "source_id": 19, "deleted_at": None, "enabled": True}]
            )
        if "from source_pages" in sql and "where id" in sql:
            return _Result([active])
        raise AssertionError(sql)

    session = MagicMock()
    session.execute.side_effect = fake_execute

    @contextmanager
    def fake_scope():
        yield session

    monkeypatch.setattr(repository, "session_scope", fake_scope)
    result = repository.restore_source_page(84)
    assert result["restored"] is True
    assert result["already_active"] is True


def test_duplicate_create_against_retired_url_rejected(monkeypatch) -> None:
    def fake_execute(statement, params=None):
        sql = str(statement).lower()
        if "from sources" in sql:
            return _Result(
                [{"id": 19, "url": "https://gercin.org/", "allowed_domains": ["gercin.org"]}]
            )
        if "from source_pages" in sql:
            return _Result(
                [
                    {
                        "id": 84,
                        "url": RETIRED_URL,
                        "deleted_at": NOW,
                    }
                ]
            )
        raise AssertionError("insert must not run for retired duplicate")

    session = MagicMock()
    session.execute.side_effect = fake_execute

    @contextmanager
    def fake_scope():
        yield session

    monkeypatch.setattr(repository, "session_scope", fake_scope)
    with pytest.raises(SourcePageConflictError) as exc_info:
        repository.create_source_page(
            19,
            SourcePagePayload(
                name="Draft Regulations",
                url=RETIRED_URL,
                page_type="listing",
                priority=30,
                enabled=True,
            ),
        )
    assert exc_info.value.retired is True
    assert exc_info.value.page_id == 84
    assert "restore it instead" in str(exc_info.value).lower()


def test_normal_list_excludes_retired(monkeypatch) -> None:
    session = MagicMock()
    session.execute.return_value.mappings.return_value = _mappings([_page()])

    @contextmanager
    def fake_scope():
        yield session

    monkeypatch.setattr(repository, "session_scope", fake_scope)
    repository.list_source_pages(19)
    sql = str(session.execute.call_args.args[0]).lower()
    assert "deleted_at is null" in sql


def test_admin_retired_list_can_include_retired(monkeypatch) -> None:
    session = MagicMock()
    session.execute.return_value.mappings.return_value = _mappings(
        [_page(deleted_at=NOW, deleted_by=ADMIN.id)]
    )

    @contextmanager
    def fake_scope():
        yield session

    monkeypatch.setattr(repository, "session_scope", fake_scope)
    pages = repository.list_source_pages(19, include_retired=True)
    assert pages[0]["deleted_at"] == NOW
    sql = str(session.execute.call_args.args[0]).lower()
    assert "where source_id = :source_id" in sql
    assert "and deleted_at is null" not in sql


def test_delete_wrapper_never_hard_deletes(monkeypatch) -> None:
    calls: list[tuple[int, str]] = []

    def fake_retire(page_id: int, *, deleted_by: str):
        calls.append((page_id, deleted_by))
        return {
            "page_id": page_id,
            "source_id": 19,
            "retired": True,
            "already_retired": False,
            "page": _page(deleted_at=NOW, deleted_by=deleted_by),
        }

    monkeypatch.setattr(repository, "retire_source_page", fake_retire)
    result = repository.delete_source_page(84, deleted_by=ADMIN.id)
    assert calls == [(84, ADMIN.id)]
    assert result["deleted"] is True
    assert result["retired"] is True
    assert "hard" not in str(result).lower()


@pytest.fixture
def soft_delete_app() -> FastAPI:
    app = FastAPI()
    app.include_router(admin.router)
    app.dependency_overrides[admin_user] = lambda: ADMIN
    return app


def test_admin_delete_endpoint_soft_deletes(
    soft_delete_app: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: list[dict[str, Any]] = []

    def fake_delete(page_id: int, *, deleted_by: str):
        seen.append({"page_id": page_id, "deleted_by": deleted_by})
        return {
            "page_id": page_id,
            "source_id": 19,
            "deleted": True,
            "retired": True,
            "already_retired": False,
            "page": _page(deleted_at=NOW, deleted_by=deleted_by),
        }

    monkeypatch.setattr(admin, "delete_source_page", fake_delete)
    with TestClient(soft_delete_app) as client:
        response = client.delete("/admin/pages/84")
    assert response.status_code == 200
    assert seen == [{"page_id": 84, "deleted_by": ADMIN.id}]
    body = response.json()
    assert body["retired"] is True
    assert body["page"]["deleted_by"] == ADMIN.id


def test_admin_restore_endpoint(
    soft_delete_app: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        admin,
        "restore_source_page",
        lambda page_id: {
            "page_id": page_id,
            "source_id": 19,
            "restored": True,
            "already_active": False,
            "page": _page(deleted_at=None, deleted_by=None),
        },
    )
    with TestClient(soft_delete_app) as client:
        response = client.post("/admin/pages/84/restore")
    assert response.status_code == 200
    assert response.json()["restored"] is True


def test_non_admin_cannot_retire_or_restore() -> None:
    app = FastAPI()
    app.include_router(admin.router)
    app.dependency_overrides[current_user] = lambda: USER
    with TestClient(app) as client:
        delete_response = client.delete("/admin/pages/84")
        restore_response = client.post("/admin/pages/84/restore")
    assert delete_response.status_code == status.HTTP_403_FORBIDDEN
    assert restore_response.status_code == status.HTTP_403_FORBIDDEN


def test_add_page_conflict_returns_restore_hint(
    soft_delete_app: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def boom(*_a, **_k):
        raise SourcePageConflictError(
            "A removed page with this URL already exists; restore it instead.",
            page_id=84,
            retired=True,
        )

    monkeypatch.setattr(admin, "create_source_page", boom)
    with TestClient(soft_delete_app) as client:
        response = client.post(
            "/admin/sources/19/pages",
            json={
                "name": "Draft Regulations",
                "url": RETIRED_URL,
                "page_type": "listing",
                "priority": 30,
                "enabled": True,
            },
        )
    assert response.status_code == 409
    detail = response.json()["detail"]
    assert detail["retired"] is True
    assert detail["page_id"] == 84
    assert "restore" in detail["message"].lower()
