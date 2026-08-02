from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api.auth import CurrentUser, current_user
from backend.api.routes import chat_evidence, chat_sessions
from backend.ask.citation_persistence import CurrentSourceStatus, PersistedCitationDetail
from backend.ask.models import (
    AskFeedback,
    AskResponseVersion,
    AskRun,
    AskSavedItem,
    AskSource,
    ChatMessage,
)

USER_ID = UUID("11111111-1111-4111-8111-111111111111")
SESSION_ID = UUID("22222222-2222-4222-8222-222222222222")
MESSAGE_ID = UUID("33333333-3333-4333-8333-333333333333")
RUN_ID = UUID("44444444-4444-4444-8444-444444444444")
FEEDBACK_ID = UUID("55555555-5555-4555-8555-555555555555")
SOURCE_ID = UUID("66666666-6666-4666-8666-666666666666")
SAVED_ITEM_ID = UUID("77777777-7777-4777-8777-777777777777")
CITATION_ID = UUID("88888888-8888-4888-8888-888888888888")
CLAIM_ID = UUID("99999999-9999-4999-8999-999999999999")
CONTRACT_PATH = Path(__file__).parent / "fixtures" / "ask_evidence_contract.json"


def _version() -> AskResponseVersion:
    created = datetime(2026, 7, 27, 9, tzinfo=UTC)
    message = ChatMessage(
        id=31,
        public_id=MESSAGE_ID,
        session_id=SESSION_ID,
        user_id=USER_ID,
        event_id=41,
        role="assistant",
        content="The consultation deadline changed.",
        created_at=created,
        status="completed",
        response_version=2,
        reply_to_message_id=29,
        parent_message_id=30,
    )
    run = AskRun(
        id=RUN_ID,
        status="completed",
        knowledge_mode_summary={"live": True},
        model="contract-model",
        policy_version="policy-1",
        prompt_version="prompt-1",
        general_ai_disclosure=None,
        safe_error_code=None,
        safe_error_message=None,
        started_at=datetime(2026, 7, 27, 8, 59, 58, tzinfo=UTC),
        completed_at=created,
        created_at=datetime(2026, 7, 27, 8, 59, 58, tzinfo=UTC),
        updated_at=created,
        sections=(),
        sources=(),
        claims=(),
        citations=(),
        followups=(),
        response_version=2,
    )
    feedback = AskFeedback(
        id=FEEDBACK_ID,
        run_id=RUN_ID,
        session_id=SESSION_ID,
        user_id=USER_ID,
        response_version=2,
        value="not_helpful",
        reason_code="missing_source",
        comment="Add the official notice.",
        created_at=datetime(2026, 7, 27, 9, 1, tzinfo=UTC),
        updated_at=datetime(2026, 7, 27, 9, 2, tzinfo=UTC),
    )
    return AskResponseVersion(
        response_version=2,
        assistant_message=message,
        run=run,
        feedback=feedback,
    )


def _saved_item() -> AskSavedItem:
    created = datetime(2026, 7, 27, 9, 3, tzinfo=UTC)
    return AskSavedItem(
        id=SAVED_ITEM_ID,
        session_id=SESSION_ID,
        user_id=USER_ID,
        item_type="source",
        target_key=str(SOURCE_ID),
        run_id=RUN_ID,
        response_version=2,
        source_id=SOURCE_ID,
        citation_id=None,
        section_id=None,
        entity_id=None,
        document_id=None,
        label_snapshot="Consultation update",
        metadata={"source_class": "live"},
        created_at=created,
        updated_at=created,
    )


def _citation_detail() -> PersistedCitationDetail:
    created = datetime(2026, 7, 27, 9, 4, tzinfo=UTC)
    source = AskSource(
        id=SOURCE_ID,
        ordinal=0,
        source_key="official:consultation",
        source_class="official",
        source_type="regulation",
        document_id=91,
        document_version_id=92,
        chunk_id=93,
        graph_reference=None,
        title_snapshot="Consultation regulation",
        url_snapshot="https://official.example.test/consultation",
        issuer_snapshot="Regulator",
        publisher_snapshot=None,
        jurisdiction_snapshot="central",
        published_at=datetime(2026, 7, 27, 8, 30, tzinfo=UTC),
        retrieved_at=created,
        evidence_snapshot="Responses are due by 31 August.",
        locator_snapshot="paragraph 4",
        content_hash="sha256:contract",
        metadata={"language": "en"},
        created_at=created,
    )
    return PersistedCitationDetail(
        message_id=MESSAGE_ID,
        response_version=2,
        claim_id=CLAIM_ID,
        claim_key="claim-1",
        claim_ordinal=0,
        claim_text="Responses are due by 31 August.",
        support_status="supported",
        support_score=0.98,
        citation_id=CITATION_ID,
        evidence_key="evidence-1",
        citation_ordinal=0,
        marker="[1]",
        verification_status="supported",
        verifier_provider="contract-verifier",
        verifier_version="verifier-1",
        verifier_model="model-1",
        verifier_prompt_version="prompt-1",
        verifier_policy_version="ask-ai-claim-verifier-v1",
        verification_latency_ms=125,
        verifier_result=None,
        provenance={"knowledge_mode": "grounded_regulatory"},
        confidence_result={"score": 0.98},
        source=source,
        current_source_status=CurrentSourceStatus.CURRENT,
    )


class FakeEvidenceService:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.version: AskResponseVersion | None = _version()
        self.feedback: AskFeedback | None = _version().feedback
        self.saved_items: tuple[AskSavedItem, ...] | None = (_saved_item(),)
        self.saved_item: AskSavedItem | None = _saved_item()
        self.citation_detail: PersistedCitationDetail | None = _citation_detail()
        self.deleted = True

    def get_response_version(self, **kwargs: Any) -> AskResponseVersion | None:
        self.calls.append(("get_version", kwargs))
        return self.version

    def record_message_feedback(self, **kwargs: Any) -> AskFeedback | None:
        self.calls.append(("feedback", kwargs))
        return self.feedback

    def list_saved_items(self, **kwargs: Any) -> tuple[AskSavedItem, ...] | None:
        self.calls.append(("list_saved", kwargs))
        return self.saved_items

    def save_item(self, **kwargs: Any) -> AskSavedItem | None:
        self.calls.append(("save", kwargs))
        return self.saved_item

    def delete_saved_item(self, **kwargs: Any) -> bool:
        self.calls.append(("delete", kwargs))
        return self.deleted

    def get_citation_detail(self, **kwargs: Any) -> PersistedCitationDetail | None:
        self.calls.append(("get_citation", kwargs))
        return self.citation_detail


@pytest.fixture(scope="module")
def contracts() -> dict[str, Any]:
    return json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))


@pytest.fixture
def service() -> FakeEvidenceService:
    return FakeEvidenceService()


@pytest.fixture
def app(service: FakeEvidenceService) -> FastAPI:
    api = FastAPI()
    api.include_router(chat_evidence.router)
    api.include_router(chat_evidence.saved_items_router)
    api.dependency_overrides[current_user] = lambda: CurrentUser(
        id=str(USER_ID),
        email="evidence-owner@example.test",
    )
    api.dependency_overrides[chat_evidence.get_ask_evidence_service] = lambda: service
    return api


def test_flag_off_is_non_disclosing_for_evidence_and_saved_items(
    app: FastAPI,
    service: FakeEvidenceService,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(chat_sessions.settings, "ask_ai_v2_api_enabled", False)

    with TestClient(app) as client:
        evidence = client.get(f"/chat/messages/{MESSAGE_ID}")
        citation = client.get(
            f"/chat/messages/{MESSAGE_ID}/citations/{CITATION_ID}"
        )
        saved = client.get(f"/chat/sessions/{SESSION_ID}/saved-items")

    assert evidence.status_code == citation.status_code == saved.status_code == 404
    assert evidence.json() == citation.json() == saved.json() == {"detail": "Not found"}
    assert service.calls == []


def test_flag_on_still_requires_authentication(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(chat_sessions.settings, "ask_ai_v2_api_enabled", True)
    api = FastAPI()
    api.include_router(chat_evidence.router)
    api.include_router(chat_evidence.saved_items_router)

    with TestClient(api, raise_server_exceptions=False) as client:
        evidence = client.get(f"/chat/messages/{MESSAGE_ID}")
        citation = client.get(
            f"/chat/messages/{MESSAGE_ID}/citations/{CITATION_ID}"
        )
        saved = client.get(f"/chat/sessions/{SESSION_ID}/saved-items")

    assert evidence.status_code == citation.status_code == saved.status_code == 401


def test_message_and_sources_match_versioned_contract(
    app: FastAPI,
    service: FakeEvidenceService,
    contracts: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(chat_sessions.settings, "ask_ai_v2_api_enabled", True)

    with TestClient(app) as client:
        message = client.get(f"/chat/messages/{MESSAGE_ID}")
        sources = client.get(f"/chat/messages/{MESSAGE_ID}/sources")

    assert message.status_code == sources.status_code == 200
    assert message.json() == contracts["message_response"]
    assert sources.json() == contracts["sources_response"]
    assert all(call[1]["user_id"] == USER_ID for call in service.calls)


def test_inaccessible_message_uses_one_not_found_contract(
    app: FastAPI,
    service: FakeEvidenceService,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(chat_sessions.settings, "ask_ai_v2_api_enabled", True)
    service.version = None

    with TestClient(app) as client:
        message = client.get(f"/chat/messages/{uuid4()}")
        sources = client.get(f"/chat/messages/{uuid4()}/sources")

    assert message.status_code == sources.status_code == 404
    assert message.json() == sources.json() == {"detail": "Message not found"}


def test_citation_detail_is_owner_scoped_and_non_disclosing(
    app: FastAPI,
    service: FakeEvidenceService,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(chat_sessions.settings, "ask_ai_v2_api_enabled", True)

    with TestClient(app) as client:
        found = client.get(f"/chat/messages/{MESSAGE_ID}/citations/{CITATION_ID}")
        service.citation_detail = None
        missing = client.get(f"/chat/messages/{MESSAGE_ID}/citations/{uuid4()}")

    assert found.status_code == 200
    assert found.json()["claim_key"] == "claim-1"
    assert found.json()["evidence_key"] == "evidence-1"
    assert found.json()["source"]["evidence_snapshot"] == (
        "Responses are due by 31 August."
    )
    assert "verifier_provider" in found.json()
    assert missing.status_code == 404
    assert missing.json() == {"detail": "Citation not found"}
    assert service.calls[-2][1] == {
        "assistant_message_public_id": MESSAGE_ID,
        "citation_id": CITATION_ID,
        "user_id": USER_ID,
    }


def test_feedback_matches_contract_and_forwards_exact_message_owner(
    app: FastAPI,
    service: FakeEvidenceService,
    contracts: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(chat_sessions.settings, "ask_ai_v2_api_enabled", True)

    with TestClient(app) as client:
        response = client.post(
            f"/chat/messages/{MESSAGE_ID}/feedback",
            json=contracts["feedback_request"],
        )

    assert response.status_code == 200
    assert response.json() == contracts["feedback_response"]
    assert service.calls[-1] == (
        "feedback",
        {
            "assistant_message_public_id": MESSAGE_ID,
            "user_id": USER_ID,
            "value": "not_helpful",
            "reason_code": "missing_source",
            "comment": "Add the official notice.",
        },
    )


def test_saved_item_list_create_delete_match_contract(
    app: FastAPI,
    service: FakeEvidenceService,
    contracts: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(chat_sessions.settings, "ask_ai_v2_api_enabled", True)

    with TestClient(app) as client:
        listed = client.get(f"/chat/sessions/{SESSION_ID}/saved-items")
        created = client.post(
            f"/chat/sessions/{SESSION_ID}/saved-items",
            json=contracts["saved_item_request"],
        )
        deleted = client.delete(
            f"/chat/sessions/{SESSION_ID}/saved-items/{SAVED_ITEM_ID}"
        )

    assert listed.status_code == 200
    assert listed.json() == {
        "schema_version": "1",
        "items": [contracts["saved_item_response"]],
    }
    assert created.status_code == 201
    assert created.json() == contracts["saved_item_response"]
    assert deleted.status_code == 204
    assert service.calls[-2] == (
        "save",
        {
            "session_id": SESSION_ID,
            "user_id": USER_ID,
            "item_type": "source",
            "target_key": str(SOURCE_ID),
        },
    )
    assert service.calls[-1] == (
        "delete",
        {
            "saved_item_id": SAVED_ITEM_ID,
            "session_id": SESSION_ID,
            "user_id": USER_ID,
        },
    )


def test_saved_item_inaccessible_results_do_not_leak_target_or_owner(
    app: FastAPI,
    service: FakeEvidenceService,
    contracts: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(chat_sessions.settings, "ask_ai_v2_api_enabled", True)
    service.saved_items = None
    service.saved_item = None
    service.deleted = False

    with TestClient(app) as client:
        listed = client.get(f"/chat/sessions/{SESSION_ID}/saved-items")
        created = client.post(
            f"/chat/sessions/{SESSION_ID}/saved-items",
            json=contracts["saved_item_request"],
        )
        deleted = client.delete(
            f"/chat/sessions/{SESSION_ID}/saved-items/{SAVED_ITEM_ID}"
        )

    assert listed.status_code == created.status_code == deleted.status_code == 404
    assert listed.json() == {"detail": "Session not found"}
    assert created.json() == {"detail": "Saved item target not found"}
    assert deleted.json() == {"detail": "Saved item not found"}


def test_feedback_rejects_unknown_reason_before_service_access(
    app: FastAPI,
    service: FakeEvidenceService,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(chat_sessions.settings, "ask_ai_v2_api_enabled", True)

    with TestClient(app) as client:
        response = client.post(
            f"/chat/messages/{MESSAGE_ID}/feedback",
            json={"value": "not_helpful", "reason_code": "raw_provider_error"},
        )

    assert response.status_code == 422
    assert service.calls == []
