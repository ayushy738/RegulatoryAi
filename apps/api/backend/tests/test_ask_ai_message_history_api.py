from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api.auth import CurrentUser, current_user
from backend.api.routes import chat_sessions
from backend.ask.models import (
    AskCitation,
    AskClaim,
    AskFollowup,
    AskRun,
    AskSection,
    AskSource,
    ChatMessage,
    ChatTurn,
    ChatTurnPage,
)

USER_ID = UUID("11111111-1111-4111-8111-111111111111")
SESSION_ID = UUID("22222222-2222-4222-8222-222222222222")
USER_MESSAGE_ID = UUID("33333333-3333-4333-8333-333333333333")
ASSISTANT_MESSAGE_ID = UUID("44444444-4444-4444-8444-444444444444")
CONTRACT_PATH = Path(__file__).parent / "fixtures" / "ask_turn_contract.json"


def _at(second: int) -> datetime:
    return datetime(2026, 7, 27, 9, 0, second, tzinfo=UTC)


def _turn() -> ChatTurn:
    section_id = UUID("66666666-6666-4666-8666-666666666666")
    source_id = UUID("77777777-7777-4777-8777-777777777777")
    claim_id = UUID("88888888-8888-4888-8888-888888888888")
    return ChatTurn(
        anchor_id=101,
        anchor_created_at=_at(0),
        user_message=ChatMessage(
            id=101,
            public_id=USER_MESSAGE_ID,
            session_id=SESSION_ID,
            user_id=USER_ID,
            event_id=41,
            role="user",
            content="What changed?",
            created_at=_at(0),
        ),
        assistant_message=ChatMessage(
            id=102,
            public_id=ASSISTANT_MESSAGE_ID,
            session_id=SESSION_ID,
            user_id=USER_ID,
            event_id=41,
            role="assistant",
            content="The consultation deadline changed.",
            created_at=_at(1),
        ),
        run=AskRun(
            id=UUID("55555555-5555-4555-8555-555555555555"),
            status="completed",
            knowledge_mode_summary={"live": True},
            model="contract-model",
            policy_version="policy-1",
            prompt_version="prompt-1",
            general_ai_disclosure=None,
            safe_error_code=None,
            safe_error_message=None,
            started_at=_at(0),
            completed_at=_at(2),
            created_at=_at(0),
            updated_at=_at(2),
            sections=(
                AskSection(
                    id=section_id,
                    response_version=1,
                    ordinal=0,
                    section_type="latest_update",
                    status="completed",
                    knowledge_mode="live",
                    provenance_label="Live Web Sources",
                    title="Latest update",
                    plain_text="The deadline moved to 31 August.",
                    content={"deadline": "2026-08-31"},
                    card_schema_version="1",
                    model="contract-model",
                    policy_version="policy-1",
                    prompt_version="prompt-1",
                    required_disclosure=None,
                    created_at=_at(1),
                    updated_at=_at(2),
                ),
            ),
            sources=(
                AskSource(
                    id=source_id,
                    ordinal=0,
                    source_key="live:consultation",
                    source_class="live",
                    source_type="news",
                    document_id=None,
                    document_version_id=None,
                    chunk_id=None,
                    graph_reference=None,
                    title_snapshot="Consultation update",
                    url_snapshot="https://example.test/consultation",
                    issuer_snapshot=None,
                    publisher_snapshot="Regulatory Bulletin",
                    jurisdiction_snapshot="central",
                    published_at=datetime(2026, 7, 27, 8, 30, tzinfo=UTC),
                    retrieved_at=_at(0),
                    evidence_snapshot="Responses are due by 31 August.",
                    locator_snapshot="paragraph 4",
                    content_hash="sha256:contract",
                    metadata={"language": "en"},
                    created_at=_at(1),
                ),
            ),
            claims=(
                AskClaim(
                    id=claim_id,
                    section_id=section_id,
                    ordinal=0,
                    knowledge_mode="live",
                    claim_text="The deadline moved to 31 August.",
                    is_material=True,
                    support_status="supported",
                    support_score=0.98,
                    model="contract-model",
                    policy_version="policy-1",
                    prompt_version="prompt-1",
                    required_disclosure=None,
                    verifier_model="verifier-model",
                    verifier_policy_version="verify-1",
                    created_at=_at(1),
                ),
            ),
            citations=(
                AskCitation(
                    id=UUID("99999999-9999-4999-8999-999999999999"),
                    claim_id=claim_id,
                    source_id=source_id,
                    ordinal=0,
                    claim_knowledge_mode="live",
                    source_class="live",
                    citation_kind="live_source_link",
                    marker="[Live 1]",
                    evidence_snapshot="Responses are due by 31 August.",
                    locator_snapshot="paragraph 4",
                    support_score=0.98,
                    verification_status="verified",
                    verifier_model="verifier-model",
                    verifier_policy_version="verify-1",
                    created_at=_at(1),
                ),
            ),
            followups=(
                AskFollowup(
                    id=UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"),
                    ordinal=0,
                    label="Check applicability",
                    question="Who must respond?",
                    action_type="ask",
                    payload={"entity": "CERC"},
                    created_at=_at(2),
                ),
            ),
        ),
    )


class FakeSessionService:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.page: ChatTurnPage | None = ChatTurnPage(items=(_turn(),), has_more=False)

    def list_turns(self, **kwargs: Any) -> ChatTurnPage | None:
        self.calls.append(kwargs)
        return self.page


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
        email="history-owner@example.test",
    )
    api.dependency_overrides[chat_sessions.get_ask_session_service] = lambda: service
    return api


def test_history_matches_complete_turn_contract(
    app: FastAPI,
    service: FakeSessionService,
    contracts: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(chat_sessions.settings, "ask_ai_v2_api_enabled", True)

    with TestClient(app) as client:
        response = client.get(f"/chat/sessions/{SESSION_ID}/messages")

    assert response.status_code == 200
    assert response.json() == contracts["turn_list_response"]
    assert service.calls == [
        {
            "session_id": SESSION_ID,
            "user_id": USER_ID,
            "limit": 20,
            "cursor_created_at": None,
            "cursor_id": None,
        }
    ]


def test_history_cursor_is_opaque_and_decoded_for_next_page(
    app: FastAPI,
    service: FakeSessionService,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(chat_sessions.settings, "ask_ai_v2_api_enabled", True)
    service.page = ChatTurnPage(items=(_turn(),), has_more=True)

    with TestClient(app) as client:
        first = client.get(
            f"/chat/sessions/{SESSION_ID}/messages",
            params={"limit": 1},
        )
        cursor = first.json()["next_cursor"]
        second = client.get(
            f"/chat/sessions/{SESSION_ID}/messages",
            params={"limit": 1, "cursor": cursor},
        )

    assert first.status_code == second.status_code == 200
    assert cursor is not None
    assert service.calls[-1]["cursor_created_at"] == _at(0)
    assert service.calls[-1]["cursor_id"] == 101


def test_history_flag_off_is_non_disclosing(
    app: FastAPI,
    service: FakeSessionService,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(chat_sessions.settings, "ask_ai_v2_api_enabled", False)

    with TestClient(app) as client:
        response = client.get(f"/chat/sessions/{SESSION_ID}/messages")

    assert response.status_code == 404
    assert response.json() == {"detail": "Not found"}
    assert service.calls == []


def test_history_flag_on_requires_authentication(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(chat_sessions.settings, "ask_ai_v2_api_enabled", True)
    api = FastAPI()
    api.include_router(chat_sessions.router)

    with TestClient(api, raise_server_exceptions=False) as client:
        response = client.get(f"/chat/sessions/{SESSION_ID}/messages")

    assert response.status_code == 401


def test_history_missing_and_cross_owner_share_one_response(
    app: FastAPI,
    service: FakeSessionService,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(chat_sessions.settings, "ask_ai_v2_api_enabled", True)
    service.page = None

    with TestClient(app) as client:
        missing = client.get(f"/chat/sessions/{SESSION_ID}/messages")
        inaccessible = client.get(
            "/chat/sessions/ffffffff-ffff-4fff-8fff-ffffffffffff/messages"
        )

    assert missing.status_code == inaccessible.status_code == 404
    assert missing.json() == inaccessible.json() == {"detail": "Session not found"}
    assert all(call["user_id"] == USER_ID for call in service.calls)


def test_history_rejects_invalid_cursor_before_service_access(
    app: FastAPI,
    service: FakeSessionService,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(chat_sessions.settings, "ask_ai_v2_api_enabled", True)

    with TestClient(app) as client:
        response = client.get(
            f"/chat/sessions/{SESSION_ID}/messages",
            params={"cursor": "not-a-message-cursor"},
        )

    assert response.status_code == 422
    assert response.json() == {"detail": "Invalid cursor"}
    assert service.calls == []
