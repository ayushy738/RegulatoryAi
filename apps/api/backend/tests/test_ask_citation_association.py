"""Ask restoration binds citations and knowledge basis to the exact answer.

Before message binding, restoration matched an assistant answer to its sources
by user question text, so two conversations asking the same question could
render each other's citations. These tests freeze the message-bound behaviour,
the deliberately narrow legacy fallback, and knowledge-basis reproduction.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from datetime import UTC, date, datetime
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api.ask_errors import AskCorrelationMiddleware
from backend.api.auth import CurrentUser, current_user
from backend.api.ratelimit import limit_chat
from backend.api.routes import chat
from backend.core import repository
from backend.rag.models import HybridRetrievalResult, Intent, RetrievalHit

USER_ID = "11111111-1111-4111-8111-111111111111"
SESSION_A = "22222222-2222-4222-8222-222222222222"
SESSION_B = "33333333-3333-4333-8333-333333333333"
SAME_QUESTION = "What is DSM?"

CITATION_A = {
    "document_id": 17,
    "title": "Sources A",
    "issuer": "KERC",
    "issue_date": "2026-03-10",
    "source_url": "https://example.gov.in/a",
}
CITATION_B = {
    "document_id": 18,
    "title": "Sources B",
    "issuer": "CERC",
    "issue_date": "2026-04-11",
    "source_url": "https://example.gov.in/b",
}


@pytest.fixture
def authenticated_client() -> Iterator[TestClient]:
    app = FastAPI()
    app.add_middleware(AskCorrelationMiddleware)
    app.include_router(chat.router)
    app.dependency_overrides[current_user] = lambda: CurrentUser(
        id=USER_ID,
        email="association-user@example.com",
    )
    app.dependency_overrides[limit_chat] = lambda: None
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client


def _message(
    message_id: int,
    role: str,
    content: str,
    *,
    knowledge_basis: str | None = None,
) -> dict[str, Any]:
    return {
        "id": message_id,
        "role": role,
        "content": content,
        "created_at": datetime(2026, 8, 15, 10, message_id, tzinfo=UTC),
        "knowledge_basis": knowledge_basis,
        "session_id": SESSION_A,
    }


def _install_conversations(
    monkeypatch: pytest.MonkeyPatch,
    *,
    conversations: dict[str, list[dict[str, Any]]],
    bound_citations: dict[int, list[dict[str, Any]]],
    legacy_by_question: dict[str, list[dict[str, Any]]] | None = None,
) -> dict[str, list[Any]]:
    calls: dict[str, list[Any]] = {"bound": [], "legacy": []}

    def messages(user_id: str, session_id: str) -> list[dict[str, Any]] | None:
        assert user_id == USER_ID
        return conversations.get(session_id)

    def bound(user_id: str, ids: Sequence[int]) -> dict[int, list[dict[str, Any]]]:
        calls["bound"].append(list(ids))
        return {
            message_id: bound_citations[message_id]
            for message_id in ids
            if message_id in bound_citations
        }

    def legacy(user_id: str, question: str) -> list[dict[str, Any]]:
        calls["legacy"].append(question)
        return (legacy_by_question or {}).get(question, [])

    monkeypatch.setattr(chat, "get_chat_conversation_messages", messages)
    monkeypatch.setattr(chat, "citations_for_assistant_messages", bound)
    monkeypatch.setattr(chat, "citations_for_question", legacy)
    return calls


def _citation_titles(payload: dict[str, Any], message_id: int) -> list[str]:
    for message in payload["messages"]:
        if message["id"] == message_id:
            return [citation["title"] for citation in message["citations"]]
    raise AssertionError(f"message {message_id} missing from {payload}")


def test_identical_questions_in_two_conversations_keep_their_own_citations(
    authenticated_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_conversations(
        monkeypatch,
        conversations={
            SESSION_A: [
                _message(1, "user", SAME_QUESTION),
                _message(2, "assistant", "Answer A", knowledge_basis="official"),
            ],
            SESSION_B: [
                _message(3, "user", SAME_QUESTION),
                _message(4, "assistant", "Answer B", knowledge_basis="official"),
            ],
        },
        bound_citations={2: [CITATION_A], 4: [CITATION_B]},
    )

    first = authenticated_client.get(f"/chat/conversations/{SESSION_A}")
    second = authenticated_client.get(f"/chat/conversations/{SESSION_B}")

    assert first.status_code == second.status_code == 200
    assert _citation_titles(first.json(), 2) == ["Sources A"]
    assert _citation_titles(second.json(), 4) == ["Sources B"]


def test_same_question_twice_in_one_conversation_keeps_separate_citations(
    authenticated_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_conversations(
        monkeypatch,
        conversations={
            SESSION_A: [
                _message(1, "user", SAME_QUESTION),
                _message(2, "assistant", "First answer", knowledge_basis="official"),
                _message(3, "user", SAME_QUESTION),
                _message(4, "assistant", "Second answer", knowledge_basis="official"),
            ]
        },
        bound_citations={2: [CITATION_A], 4: [CITATION_B]},
    )

    payload = authenticated_client.get(f"/chat/conversations/{SESSION_A}").json()

    assert _citation_titles(payload, 2) == ["Sources A"]
    assert _citation_titles(payload, 4) == ["Sources B"]


def test_interleaved_history_navigation_never_crosses_citations(
    authenticated_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = _install_conversations(
        monkeypatch,
        conversations={
            SESSION_A: [
                _message(1, "user", SAME_QUESTION),
                _message(2, "assistant", "Answer A", knowledge_basis="official"),
            ],
            SESSION_B: [
                _message(3, "user", SAME_QUESTION),
                _message(4, "assistant", "Answer B", knowledge_basis="official"),
            ],
        },
        bound_citations={2: [CITATION_A], 4: [CITATION_B]},
    )

    visits = [SESSION_A, SESSION_B, SESSION_A, SESSION_B, SESSION_A]
    payloads = [
        authenticated_client.get(f"/chat/conversations/{session}").json()
        for session in visits
    ]

    for session, payload in zip(visits, payloads, strict=True):
        expected = ["Sources A"] if session == SESSION_A else ["Sources B"]
        message_id = 2 if session == SESSION_A else 4
        assert _citation_titles(payload, message_id) == expected
    assert calls["legacy"] == []


def test_refreshing_a_conversation_returns_identical_persisted_state(
    authenticated_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_conversations(
        monkeypatch,
        conversations={
            SESSION_A: [
                _message(1, "user", SAME_QUESTION),
                _message(2, "assistant", "Answer A", knowledge_basis="official"),
            ]
        },
        bound_citations={2: [CITATION_A]},
    )
    monkeypatch.setattr(
        chat,
        "get_llm_client",
        lambda: pytest.fail("restoring a conversation must not call the model"),
    )

    first = authenticated_client.get(f"/chat/conversations/{SESSION_A}").json()
    second = authenticated_client.get(f"/chat/conversations/{SESSION_A}").json()

    assert first == second
    assert _citation_titles(second, 2) == ["Sources A"]


@pytest.mark.parametrize("basis", ["official", "general", "none"])
def test_restored_conversation_reports_the_persisted_knowledge_basis(
    authenticated_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    basis: str,
) -> None:
    _install_conversations(
        monkeypatch,
        conversations={
            SESSION_A: [
                _message(1, "user", SAME_QUESTION),
                _message(2, "assistant", "Answer", knowledge_basis=basis),
            ]
        },
        bound_citations={2: [CITATION_A]} if basis == "official" else {},
    )

    payload = authenticated_client.get(f"/chat/conversations/{SESSION_A}").json()

    assert payload["messages"][1]["knowledge_basis"] == basis


def test_legacy_answers_without_basis_may_use_the_question_fallback(
    authenticated_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = _install_conversations(
        monkeypatch,
        conversations={
            SESSION_A: [
                _message(1, "user", SAME_QUESTION),
                _message(2, "assistant", "Historical answer"),
            ]
        },
        bound_citations={},
        legacy_by_question={SAME_QUESTION: [CITATION_A]},
    )

    payload = authenticated_client.get(f"/chat/conversations/{SESSION_A}").json()

    assert _citation_titles(payload, 2) == ["Sources A"]
    assert calls["legacy"] == [SAME_QUESTION]
    assert payload["messages"][1]["knowledge_basis"] is None


def test_message_bound_answers_never_fall_back_to_question_matching(
    authenticated_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = _install_conversations(
        monkeypatch,
        conversations={
            SESSION_A: [
                _message(1, "user", SAME_QUESTION),
                _message(2, "assistant", "Answer", knowledge_basis="general"),
            ]
        },
        bound_citations={},
        legacy_by_question={SAME_QUESTION: [CITATION_B]},
    )

    payload = authenticated_client.get(f"/chat/conversations/{SESSION_A}").json()

    assert _citation_titles(payload, 2) == []
    assert calls["legacy"] == []


def test_grounded_answer_binds_its_audit_to_the_new_assistant_message(
    authenticated_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    saved: list[dict[str, Any]] = []
    audits: list[dict[str, Any]] = []

    def save_message(
        user_id: str,
        role: str,
        content: str,
        event_id: int | None = None,
        **kwargs: Any,
    ) -> int:
        saved.append({"role": role, "kwargs": kwargs})
        return 900 + len(saved)

    hit = RetrievalHit(
        source="vector",
        document_id=17,
        title="Electricity Rules",
        source_url="https://example.test/rules",
        issuer="Ministry of Power",
        issue_date=date(2026, 7, 1),
        chunk_id=501,
        page_number=7,
        section_title="Applicability",
        text="The rules apply to licensed distribution entities.",
    )
    retrieval = HybridRetrievalResult(
        query=SAME_QUESTION,
        intent=Intent(
            name="regulation_lookup",
            query=SAME_QUESTION,
            confidence=0.9,
            dominant_sources=("vector",),
        ),
        hits=[hit],
        citations=[],
        related_questions=[],
        retrieval_latency_ms=12,
    )

    monkeypatch.setattr(chat, "_resolve_session_id", lambda *_a, **_k: SESSION_A)
    monkeypatch.setattr(chat, "get_chat_conversation_messages", lambda *_a, **_k: [])
    monkeypatch.setattr(chat, "get_chat_history", lambda *_a, **_k: [])
    monkeypatch.setattr(chat, "save_chat_message", save_message)
    monkeypatch.setattr(chat.settings, "llm_model_chat", "contract-model")
    monkeypatch.setattr(
        chat.RetrievalProviderFactory,
        "get_provider",
        lambda: SimpleNamespace(
            provider_name="contract-provider",
            hybrid_search=lambda *_a, **_k: retrieval,
        ),
    )
    monkeypatch.setattr(
        chat,
        "get_llm_client",
        lambda: SimpleNamespace(complete_text=lambda **_: "Grounded answer."),
    )
    monkeypatch.setattr(
        chat,
        "record_chat_retrieval_audit",
        lambda **kwargs: audits.append(kwargs),
    )

    response = authenticated_client.post("/chat", json={"message": SAME_QUESTION})

    assert response.status_code == 200
    assert response.json()["knowledge_basis"] == "official"
    assert [item["role"] for item in saved] == ["user", "assistant"]
    assert saved[1]["kwargs"]["knowledge_basis"] == "official"
    assert saved[1]["kwargs"]["session_id"] == SESSION_A
    assert len(audits) == 1
    assert audits[0]["assistant_message_id"] == 902


def test_suppressed_assistant_persistence_records_no_message_binding(
    authenticated_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    audits: list[dict[str, Any]] = []

    monkeypatch.setattr(chat, "_resolve_session_id", lambda *_a, **_k: SESSION_A)
    monkeypatch.setattr(chat, "get_chat_conversation_messages", lambda *_a, **_k: [])
    monkeypatch.setattr(chat, "get_chat_history", lambda *_a, **_k: [])
    monkeypatch.setattr(chat, "save_chat_message", lambda *_a, **_k: False)
    monkeypatch.setattr(chat.settings, "llm_model_chat", "contract-model")
    monkeypatch.setattr(chat.settings, "ask_ai_general_mode_enabled", False)
    monkeypatch.setattr(
        chat.RetrievalProviderFactory,
        "get_provider",
        lambda: SimpleNamespace(
            provider_name="contract-provider",
            hybrid_search=lambda *_a, **_k: HybridRetrievalResult(
                query=SAME_QUESTION,
                intent=Intent(
                    name="general",
                    query=SAME_QUESTION,
                    confidence=0.4,
                    dominant_sources=(),
                ),
                hits=[],
                citations=[],
                related_questions=[],
                retrieval_latency_ms=5,
            ),
        ),
    )
    monkeypatch.setattr(
        chat,
        "record_chat_retrieval_audit",
        lambda **kwargs: audits.append(kwargs),
    )

    response = authenticated_client.post("/chat", json={"message": SAME_QUESTION})

    assert response.status_code == 200
    assert response.json()["knowledge_basis"] == "none"
    assert audits[0]["assistant_message_id"] is None


def test_persisted_message_id_ignores_legacy_boolean_results() -> None:
    assert chat._persisted_message_id(901) == 901
    assert chat._persisted_message_id(True) is None
    assert chat._persisted_message_id(False) is None
    assert chat._persisted_message_id(None) is None


def test_question_fallback_query_excludes_message_bound_audits(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    executed: list[tuple[str, dict[str, Any]]] = []

    class Result:
        def first(self) -> None:
            return None

    class Session:
        def execute(self, statement: Any, params: dict[str, Any]) -> Result:
            executed.append((str(statement), params))
            return Result()

    @contextmanager
    def session_scope() -> Iterator[Session]:
        yield Session()

    monkeypatch.setattr(repository, "session_scope", session_scope)

    assert repository.citations_for_question(USER_ID, SAME_QUESTION) == []
    sql = " ".join(executed[0][0].lower().split())
    assert "assistant_message_id is null" in sql


def test_bound_citation_query_selects_latest_audit_per_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    executed: list[tuple[str, dict[str, Any]]] = []
    rows = [
        {"assistant_message_id": 2, "citations": [CITATION_A]},
        {"assistant_message_id": 4, "citations": [CITATION_B]},
    ]

    class Result:
        def mappings(self) -> list[dict[str, Any]]:
            return rows

    class Session:
        def execute(self, statement: Any, params: dict[str, Any]) -> Result:
            executed.append((str(statement), params))
            return Result()

    @contextmanager
    def session_scope() -> Iterator[Session]:
        yield Session()

    monkeypatch.setattr(repository, "session_scope", session_scope)

    result = repository.citations_for_assistant_messages(USER_ID, [2, 4])

    assert result == {2: [CITATION_A], 4: [CITATION_B]}
    sql = " ".join(executed[0][0].lower().split())
    assert "distinct on (assistant_message_id)" in sql
    assert executed[0][1] == {"user_id": USER_ID, "ids": [2, 4]}


def test_bound_citation_query_is_skipped_without_assistant_messages(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_scope() -> Iterator[Any]:
        raise AssertionError("no query should run for an empty id list")

    monkeypatch.setattr(repository, "session_scope", fail_scope)

    assert repository.citations_for_assistant_messages(USER_ID, []) == {}
