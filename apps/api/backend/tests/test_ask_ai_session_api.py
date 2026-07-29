from __future__ import annotations

import base64
import json
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api.auth import CurrentUser, current_user
from backend.api.routes import chat_sessions
from backend.ask.models import ChatSession, ChatSessionExport, ChatSessionPage
from backend.ask.persistence import ChatSessionStateConflictError
from backend.ask.schemas import AskSessionResponse

USER_ID = UUID("11111111-1111-4111-8111-111111111111")
SESSION_ID = UUID("22222222-2222-4222-8222-222222222222")
CONTRACT_PATH = Path(__file__).parent / "fixtures" / "ask_session_contract.json"


def _session(
    *,
    session_id: UUID = SESSION_ID,
    user_id: UUID = USER_ID,
    title: str = "CERC tariff research",
    updated_at: datetime | None = None,
) -> ChatSession:
    timestamp = updated_at or datetime(2026, 7, 27, 6, 30, tzinfo=UTC)
    return ChatSession(
        id=session_id,
        user_id=user_id,
        event_id=41,
        title=title,
        status="draft",
        primary_entity="CERC",
        primary_topic="tariff",
        scope_snapshot={"jurisdiction": "central"},
        knowledge_mode_summary={},
        freshness_state=None,
        is_pinned=False,
        archived_at=None,
        deleted_at=None,
        created_at=timestamp,
        updated_at=timestamp,
        last_message_at=None,
    )


class FakeSessionService:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.detail: ChatSession | None = _session()
        self.page = ChatSessionPage(items=(_session(),), has_more=False)

    def create_session(self, **kwargs: Any) -> ChatSession:
        self.calls.append(("create", kwargs))
        return _session(title=kwargs["title"])

    def list_sessions(self, **kwargs: Any) -> ChatSessionPage:
        self.calls.append(("list", kwargs))
        return self.page

    def get_session(self, **kwargs: Any) -> ChatSession | None:
        self.calls.append(("get", kwargs))
        return self.detail

    def patch_session(self, **kwargs: Any) -> ChatSession | None:
        self.calls.append(("patch", kwargs))
        if self.detail is None:
            return None
        return replace(
            self.detail,
            title=kwargs["title"] or self.detail.title,
            is_pinned=(
                kwargs["is_pinned"]
                if kwargs["is_pinned"] is not None
                else self.detail.is_pinned
            ),
        )

    def archive_session(self, **kwargs: Any) -> ChatSession | None:
        self.calls.append(("archive", kwargs))
        return (
            replace(
                self.detail,
                archived_at=datetime(2026, 7, 27, 7, tzinfo=UTC),
                is_pinned=False,
            )
            if self.detail is not None
            else None
        )

    def restore_session(self, **kwargs: Any) -> ChatSession | None:
        self.calls.append(("restore", kwargs))
        return (
            replace(self.detail, archived_at=None)
            if self.detail is not None
            else None
        )

    def duplicate_session(self, **kwargs: Any) -> ChatSession | None:
        self.calls.append(("duplicate", kwargs))
        return (
            replace(self.detail, id=uuid4(), title="CERC tariff research (Copy)")
            if self.detail is not None
            else None
        )

    def export_session(self, **kwargs: Any) -> ChatSessionExport | None:
        self.calls.append(("export", kwargs))
        return (
            ChatSessionExport(session=self.detail, turns=(), saved_items=())
            if self.detail is not None
            else None
        )

    def soft_delete_session(self, **kwargs: Any) -> bool | None:
        self.calls.append(("delete", kwargs))
        return True if self.detail is not None else None


@pytest.fixture(scope="module")
def contracts() -> dict[str, Any]:
    return json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))


@pytest.fixture
def service() -> FakeSessionService:
    return FakeSessionService()


@pytest.fixture
def app(service: FakeSessionService) -> FastAPI:
    api = FastAPI()
    api.include_router(chat_sessions.router)
    api.dependency_overrides[current_user] = lambda: CurrentUser(
        id=str(USER_ID),
        email="session-owner@example.test",
    )
    api.dependency_overrides[chat_sessions.get_ask_session_service] = lambda: service
    return api


def test_flag_off_is_non_disclosing_and_does_not_call_service(
    app: FastAPI,
    service: FakeSessionService,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(chat_sessions.settings, "ask_ai_v2_api_enabled", False)
    monkeypatch.setattr(chat_sessions.settings, "ask_ai_v2_write_enabled", True)

    with TestClient(app) as client:
        response = client.get("/chat/sessions")

    assert response.status_code == 404
    assert response.json() == {"detail": "Not found"}
    assert service.calls == []


def test_flag_on_still_requires_authentication(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(chat_sessions.settings, "ask_ai_v2_api_enabled", True)
    api = FastAPI()
    api.include_router(chat_sessions.router)

    with TestClient(api, raise_server_exceptions=False) as client:
        response = client.get("/chat/sessions")

    assert response.status_code == 401


def test_create_session_matches_shared_contract_and_forwards_owner(
    app: FastAPI,
    service: FakeSessionService,
    contracts: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(chat_sessions.settings, "ask_ai_v2_api_enabled", True)

    with TestClient(app) as client:
        response = client.post(
            "/chat/sessions",
            json=contracts["create_request"],
        )

    assert response.status_code == 201
    assert response.json() == contracts["session_response"]
    call_name, kwargs = service.calls[-1]
    assert call_name == "create"
    assert kwargs["user_id"] == USER_ID
    assert kwargs["scope_snapshot"] == {"jurisdiction": "central"}


def test_create_session_uses_stable_title_fallback(
    app: FastAPI,
    service: FakeSessionService,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(chat_sessions.settings, "ask_ai_v2_api_enabled", True)

    with TestClient(app) as client:
        response = client.post("/chat/sessions", json={"title": "   "})

    assert response.status_code == 201
    assert service.calls[-1][1]["title"] == "New research"


def test_list_matches_contract_and_decodes_opaque_cursor(
    app: FastAPI,
    service: FakeSessionService,
    contracts: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(chat_sessions.settings, "ask_ai_v2_api_enabled", True)
    service.page = ChatSessionPage(items=(_session(),), has_more=True)

    with TestClient(app) as client:
        first_response = client.get("/chat/sessions", params={"limit": 1})
        cursor = first_response.json()["next_cursor"]
        second_response = client.get(
            "/chat/sessions",
            params={"limit": 1, "cursor": cursor},
        )

    assert first_response.status_code == 200
    assert first_response.json() == {
        **contracts["list_response"],
        "next_cursor": cursor,
    }
    assert cursor is not None
    assert second_response.status_code == 200
    _, second_kwargs = service.calls[-1]
    assert second_kwargs == {
        "user_id": USER_ID,
        "limit": 1,
        "query": None,
        "knowledge_mode": None,
        "entity": None,
        "archived": False,
        "pinned": None,
        "cursor_relevance": 0,
        "cursor_updated_at": datetime(2026, 7, 27, 6, 30, tzinfo=UTC),
        "cursor_id": SESSION_ID,
    }


def test_search_normalizes_filters_and_binds_rank_cursor(
    app: FastAPI,
    service: FakeSessionService,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(chat_sessions.settings, "ask_ai_v2_api_enabled", True)
    service.page = ChatSessionPage(
        items=(_session(),),
        has_more=True,
        relevances=(500,),
    )

    params = {
        "q": "  GRID   Code ",
        "knowledge_mode": "official",
        "entity": "  CERC ",
        "archived": "false",
        "pinned": "true",
        "limit": "1",
    }
    with TestClient(app) as client:
        first = client.get("/chat/sessions", params=params)
        cursor = first.json()["next_cursor"]
        second = client.get(
            "/chat/sessions",
            params={**params, "cursor": cursor},
        )

    assert first.status_code == second.status_code == 200
    assert cursor is not None
    assert service.calls[-1] == (
        "list",
        {
            "user_id": USER_ID,
            "limit": 1,
            "query": "grid code",
            "knowledge_mode": "official",
            "entity": "cerc",
            "archived": False,
            "pinned": True,
            "cursor_relevance": 500,
            "cursor_updated_at": datetime(2026, 7, 27, 6, 30, tzinfo=UTC),
            "cursor_id": SESSION_ID,
        },
    )


def test_search_cursor_cannot_be_reused_with_different_filters(
    app: FastAPI,
    service: FakeSessionService,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(chat_sessions.settings, "ask_ai_v2_api_enabled", True)
    service.page = ChatSessionPage(
        items=(_session(),),
        has_more=True,
        relevances=(500,),
    )

    with TestClient(app) as client:
        first = client.get("/chat/sessions", params={"q": "grid", "limit": 1})
        calls_after_first = len(service.calls)
        changed = client.get(
            "/chat/sessions",
            params={
                "q": "tariff",
                "limit": 1,
                "cursor": first.json()["next_cursor"],
            },
        )

    assert changed.status_code == 422
    assert changed.json() == {"detail": "Invalid cursor"}
    assert len(service.calls) == calls_after_first


def test_unfiltered_list_accepts_the_previous_version_one_cursor(
    app: FastAPI,
    service: FakeSessionService,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(chat_sessions.settings, "ask_ai_v2_api_enabled", True)
    legacy_payload = json.dumps(
        {
            "id": str(SESSION_ID),
            "updated_at": "2026-07-27T06:30:00+00:00",
            "version": 1,
        },
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    cursor = base64.urlsafe_b64encode(legacy_payload).decode().rstrip("=")

    with TestClient(app) as client:
        response = client.get("/chat/sessions", params={"cursor": cursor})

    assert response.status_code == 200
    assert service.calls[-1][1]["cursor_relevance"] == 0
    assert service.calls[-1][1]["cursor_id"] == SESSION_ID


@pytest.mark.parametrize("field", ["q", "entity"])
def test_search_rejects_blank_text_filters_before_repository_access(
    field: str,
    app: FastAPI,
    service: FakeSessionService,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(chat_sessions.settings, "ask_ai_v2_api_enabled", True)

    with TestClient(app) as client:
        response = client.get("/chat/sessions", params={field: "   "})

    assert response.status_code == 422
    assert service.calls == []


def test_detail_matches_shared_contract_and_forwards_owner(
    app: FastAPI,
    service: FakeSessionService,
    contracts: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(chat_sessions.settings, "ask_ai_v2_api_enabled", True)

    with TestClient(app) as client:
        response = client.get(f"/chat/sessions/{SESSION_ID}")

    assert response.status_code == 200
    assert response.json() == contracts["session_response"]
    assert service.calls[-1] == (
        "get",
        {"session_id": SESSION_ID, "user_id": USER_ID},
    )


def test_detail_uses_same_not_found_contract_for_every_inaccessible_id(
    app: FastAPI,
    service: FakeSessionService,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(chat_sessions.settings, "ask_ai_v2_api_enabled", True)
    service.detail = None

    with TestClient(app) as client:
        missing = client.get(f"/chat/sessions/{uuid4()}")
        other_owner = client.get(f"/chat/sessions/{uuid4()}")

    assert missing.status_code == other_owner.status_code == 404
    assert missing.json() == other_owner.json() == {"detail": "Session not found"}
    assert all(call[1]["user_id"] == USER_ID for call in service.calls)


def test_invalid_cursor_is_rejected_without_repository_access(
    app: FastAPI,
    service: FakeSessionService,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(chat_sessions.settings, "ask_ai_v2_api_enabled", True)

    with TestClient(app) as client:
        response = client.get("/chat/sessions", params={"cursor": "not-a-cursor"})

    assert response.status_code == 422
    assert response.json() == {"detail": "Invalid cursor"}
    assert service.calls == []


def test_patch_session_normalizes_fields_and_forwards_owner(
    app: FastAPI,
    service: FakeSessionService,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(chat_sessions.settings, "ask_ai_v2_api_enabled", True)

    with TestClient(app) as client:
        response = client.patch(
            f"/chat/sessions/{SESSION_ID}",
            json={"title": "  Renamed research  ", "is_pinned": True},
        )

    assert response.status_code == 200
    assert response.json()["title"] == "Renamed research"
    assert response.json()["is_pinned"] is True
    assert service.calls[-1] == (
        "patch",
        {
            "session_id": SESSION_ID,
            "user_id": USER_ID,
            "title": "Renamed research",
            "is_pinned": True,
        },
    )


@pytest.mark.parametrize(
    "body",
    ({}, {"title": None}, {"title": "   "}, {"is_pinned": None}),
)
def test_patch_session_rejects_empty_changes(
    app: FastAPI,
    service: FakeSessionService,
    monkeypatch: pytest.MonkeyPatch,
    body: dict[str, Any],
) -> None:
    monkeypatch.setattr(chat_sessions.settings, "ask_ai_v2_api_enabled", True)

    with TestClient(app) as client:
        response = client.patch(f"/chat/sessions/{SESSION_ID}", json=body)

    assert response.status_code == 422
    assert service.calls == []


def test_archived_pin_conflict_is_safe(
    app: FastAPI,
    service: FakeSessionService,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(chat_sessions.settings, "ask_ai_v2_api_enabled", True)

    def conflict(**kwargs: Any) -> ChatSession:
        raise ChatSessionStateConflictError("Archived sessions cannot be pinned")

    service.patch_session = conflict  # type: ignore[method-assign]
    with TestClient(app) as client:
        response = client.patch(
            f"/chat/sessions/{SESSION_ID}",
            json={"is_pinned": True},
        )

    assert response.status_code == 409
    assert response.json() == {"detail": "Archived sessions cannot be pinned"}


def test_archive_restore_duplicate_export_and_delete_contracts(
    app: FastAPI,
    service: FakeSessionService,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(chat_sessions.settings, "ask_ai_v2_api_enabled", True)

    with TestClient(app) as client:
        archived = client.post(f"/chat/sessions/{SESSION_ID}/archive")
        restored = client.post(f"/chat/sessions/{SESSION_ID}/restore")
        duplicated = client.post(f"/chat/sessions/{SESSION_ID}/duplicate")
        exported = client.get(f"/chat/sessions/{SESSION_ID}/export")
        deleted = client.delete(f"/chat/sessions/{SESSION_ID}")

    assert archived.status_code == 200
    assert archived.json()["archived_at"] is not None
    assert restored.status_code == 200
    assert restored.json()["archived_at"] is None
    assert duplicated.status_code == 201
    assert duplicated.json()["id"] != str(SESSION_ID)
    assert duplicated.json()["title"].endswith("(Copy)")
    assert exported.status_code == 200
    assert exported.json() == {
        "schema_version": "1",
        "session": AskSessionResponse.from_domain(service.detail).model_dump(
            mode="json"
        ),
        "turns": [],
        "saved_items": [],
    }
    assert deleted.status_code == 204
    assert deleted.content == b""
    assert all(
        kwargs["user_id"] == USER_ID
        for name, kwargs in service.calls
        if name in {"archive", "restore", "duplicate", "export", "delete"}
    )


@pytest.mark.parametrize(
    ("method", "path", "body"),
    (
        ("patch", f"/chat/sessions/{SESSION_ID}", {"is_pinned": True}),
        ("post", f"/chat/sessions/{SESSION_ID}/archive", None),
        ("post", f"/chat/sessions/{SESSION_ID}/restore", None),
        ("post", f"/chat/sessions/{SESSION_ID}/duplicate", None),
        ("get", f"/chat/sessions/{SESSION_ID}/export", None),
        ("delete", f"/chat/sessions/{SESSION_ID}", None),
    ),
)
def test_lifecycle_actions_share_non_disclosing_not_found(
    app: FastAPI,
    service: FakeSessionService,
    monkeypatch: pytest.MonkeyPatch,
    method: str,
    path: str,
    body: dict[str, Any] | None,
) -> None:
    monkeypatch.setattr(chat_sessions.settings, "ask_ai_v2_api_enabled", True)
    service.detail = None

    with TestClient(app) as client:
        response = client.request(method, path, json=body)

    assert response.status_code == 404
    assert response.json() == {"detail": "Session not found"}
