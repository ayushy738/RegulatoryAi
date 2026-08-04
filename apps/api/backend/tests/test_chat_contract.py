from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from uuid import UUID

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api import ask_errors, ask_metrics
from backend.api.ask_errors import AskCorrelationMiddleware
from backend.api.auth import CurrentUser, current_user
from backend.api.ratelimit import limit_chat
from backend.api.routes import chat
from backend.ask.general_ai import (
    GeneralAIExecutionHealth,
    GeneralAIExecutionRequest,
    GeneralAIExecutionResult,
    GeneralAIExecutionState,
    GeneralAIProviderIdentity,
    GeneralKnowledgeUnit,
)
from backend.ask.knowledge_modes import (
    NO_OFFICIAL_DOCUMENTS_DISCLOSURE,
    OFFICIAL_SEARCH_UNAVAILABLE_DISCLOSURE,
    ModeTrigger,
)
from backend.ask.orchestration.contracts import GeneralKnowledgeUnitPayload
from backend.core import repository
from backend.rag.models import HybridRetrievalResult, Intent, RetrievalHit

USER_ID = "11111111-1111-4111-8111-111111111111"
CONTRACT_PATH = Path(__file__).parent / "fixtures" / "ask_chat_contract.json"


@pytest.fixture(scope="module")
def contracts() -> dict[str, Any]:
    return json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))


@pytest.fixture
def authenticated_client() -> Iterator[TestClient]:
    app = FastAPI()
    app.add_middleware(AskCorrelationMiddleware)
    app.include_router(chat.router)
    app.dependency_overrides[current_user] = lambda: CurrentUser(
        id=USER_ID,
        email="contract-user@example.com",
    )
    app.dependency_overrides[limit_chat] = lambda: None
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client


@pytest.fixture(autouse=True)
def general_ai_capability_off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        chat.settings,
        "ask_ai_general_mode_enabled",
        False,
    )


@pytest.fixture
def metric_events(
    monkeypatch: pytest.MonkeyPatch,
) -> list[tuple[str, dict[str, Any]]]:
    events: list[tuple[str, dict[str, Any]]] = []
    monkeypatch.setattr(
        ask_metrics,
        "log_event",
        lambda stage, **fields: events.append((stage, fields)),
    )
    return events


def _retrieval_result(*, with_evidence: bool) -> HybridRetrievalResult:
    hits = (
        [
            RetrievalHit(
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
        ]
        if with_evidence
        else []
    )
    return HybridRetrievalResult(
        query="What applies?",
        intent=Intent(
            name="regulation_lookup" if with_evidence else "general",
            query="What applies?",
            confidence=0.9,
            dominant_sources=("vector",) if with_evidence else (),
        ),
        hits=hits,
        citations=[],
        related_questions=(
            ["Which entities are licensed?"]
            if with_evidence
            else ["Try a named regulation"]
        ),
        retrieval_latency_ms=12,
    )


def _provider(result: HybridRetrievalResult) -> SimpleNamespace:
    calls: list[tuple[str, int, int | None]] = []

    def hybrid_search(message: str, *, limit: int, event_id: int | None) -> Any:
        calls.append((message, limit, event_id))
        return result

    return SimpleNamespace(
        provider_name="contract-provider",
        hybrid_search=hybrid_search,
        calls=calls,
    )


def _satisfied_general_ai(
    request: GeneralAIExecutionRequest,
) -> GeneralAIExecutionResult:
    policy = request.mode_decision.sections[0]
    return GeneralAIExecutionResult(
        state=GeneralAIExecutionState.SATISFIED,
        health=GeneralAIExecutionHealth.HEALTHY,
        units=(
            GeneralKnowledgeUnit(
                section_policy=policy,
                payload=GeneralKnowledgeUnitPayload(
                    content="General background explanation.",
                    assumptions=("The question is general.",),
                    uncertainty_statements=("Scope is uncertain.",),
                    required_disclosure=policy.required_disclosure,
                ),
            ),
        ),
        provider_identity=GeneralAIProviderIdentity(
            provider="parallel",
            model="general-ai-model",
        ),
    )


def _assert_correlation(response: Any) -> None:
    correlation_id = response.headers["x-correlation-id"]
    assert str(UUID(correlation_id)) == correlation_id
    body = response.json()
    if "correlation_id" in body:
        assert body["correlation_id"] == correlation_id


def test_chat_success_freezes_response_citations_history_and_persistence(
    authenticated_client: TestClient,
    contracts: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
    metric_events: list[tuple[str, dict[str, Any]]],
) -> None:
    history = [
        {"role": "assistant" if index % 2 else "user", "content": f"message-{index}"}
        for index in range(10, 0, -1)
    ]
    history_calls: list[tuple[str, int | None]] = []
    saved: list[tuple[str, str, str, int | None]] = []
    audit_calls: list[dict[str, Any]] = []
    llm_calls: list[dict[str, Any]] = []
    provider = _provider(_retrieval_result(with_evidence=True))

    def get_history(user_id: str, event_id: int | None) -> list[dict[str, str]]:
        history_calls.append((user_id, event_id))
        return history

    def save_message(
        user_id: str,
        role: str,
        content: str,
        event_id: int | None,
    ) -> None:
        saved.append((user_id, role, content, event_id))

    def complete_text(**kwargs: Any) -> str:
        llm_calls.append(kwargs)
        return "Grounded answer."

    monkeypatch.setattr(chat.settings, "llm_model_chat", "contract-model")
    monkeypatch.setattr(chat, "get_chat_history", get_history)
    monkeypatch.setattr(chat, "save_chat_message", save_message)
    monkeypatch.setattr(chat.RetrievalProviderFactory, "get_provider", lambda: provider)
    monkeypatch.setattr(
        chat,
        "get_llm_client",
        lambda: SimpleNamespace(complete_text=complete_text),
    )
    monkeypatch.setattr(
        chat,
        "record_chat_retrieval_audit",
        lambda **kwargs: audit_calls.append(kwargs),
    )

    response = authenticated_client.post(
        "/chat",
        json={"message": "What applies?", "event_id": 42},
    )

    assert response.status_code == 200
    _assert_correlation(response)
    assert response.json() == contracts["success"]
    assert history_calls == [(USER_ID, 42)]
    assert provider.calls == [("What applies?", chat.settings.rag_top_k, 42)]
    assert llm_calls[0]["history"] == list(reversed(history[-8:]))
    assert saved == [
        (USER_ID, "user", "What applies?", 42),
        (USER_ID, "assistant", contracts["success"]["reply"], 42),
    ]
    assert len(audit_calls) == 1
    assert audit_calls[0]["user_id"] == USER_ID
    assert audit_calls[0]["retrieval_provider"] == "contract-provider"
    assert [fields["metric_stage"] for _, fields in metric_events] == [
        "auth",
        "user_persistence",
        "retrieval",
        "model",
        "assistant_persistence",
        "request",
    ]
    assert all(stage == "ask_stage_metric" for stage, _ in metric_events)
    assert all(
        set(fields) == {"correlation_id", "metric_stage", "outcome", "duration_ms"}
        and isinstance(fields["duration_ms"], int)
        and fields["duration_ms"] >= 0
        for _, fields in metric_events
    )
    serialized_metrics = json.dumps(metric_events)
    assert "What applies?" not in serialized_metrics
    assert "licensed distribution entities" not in serialized_metrics


def test_chat_no_citations_freezes_fallback_without_model_call(
    authenticated_client: TestClient,
    contracts: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    saved: list[tuple[str, str, str, int | None]] = []
    audit_calls: list[dict[str, Any]] = []
    provider = _provider(_retrieval_result(with_evidence=False))

    monkeypatch.setattr(chat.settings, "llm_model_chat", "contract-model")
    monkeypatch.setattr(chat, "get_chat_history", lambda *_: [])
    monkeypatch.setattr(
        chat,
        "save_chat_message",
        lambda *args: saved.append(args),
    )
    monkeypatch.setattr(chat.RetrievalProviderFactory, "get_provider", lambda: provider)
    monkeypatch.setattr(
        chat,
        "get_llm_client",
        lambda: pytest.fail("the model must not run when citations are empty"),
    )
    monkeypatch.setattr(
        chat,
        "record_chat_retrieval_audit",
        lambda **kwargs: audit_calls.append(kwargs),
    )

    response = authenticated_client.post("/chat", json={"message": "Unknown topic"})

    assert response.status_code == 200
    _assert_correlation(response)
    assert response.json() == contracts["no_citations"]
    assert saved == [
        (USER_ID, "user", "Unknown topic", None),
        (USER_ID, "assistant", contracts["no_citations"]["reply"], None),
    ]
    assert len(audit_calls) == 1


def test_chat_healthy_no_match_answers_from_general_ai_without_citations(
    authenticated_client: TestClient,
    contracts: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    saved: list[tuple[str, str, str, int | None]] = []
    requests: list[GeneralAIExecutionRequest] = []
    provider = _provider(_retrieval_result(with_evidence=False))

    async def execute(
        request: GeneralAIExecutionRequest,
    ) -> GeneralAIExecutionResult:
        requests.append(request)
        return _satisfied_general_ai(request)

    monkeypatch.setattr(chat.settings, "ask_ai_general_mode_enabled", True)
    monkeypatch.setattr(chat.settings, "llm_model_chat", "contract-model")
    monkeypatch.setattr(chat, "get_chat_history", lambda *_: [])
    monkeypatch.setattr(
        chat,
        "save_chat_message",
        lambda *args: saved.append(args),
    )
    monkeypatch.setattr(chat.RetrievalProviderFactory, "get_provider", lambda: provider)
    monkeypatch.setattr(chat, "execute_general_ai", execute)
    monkeypatch.setattr(
        chat,
        "get_llm_client",
        lambda: pytest.fail("grounded generation must not run without citations"),
    )
    monkeypatch.setattr(chat, "record_chat_retrieval_audit", lambda **_: None)

    response = authenticated_client.post("/chat", json={"message": "Unknown topic"})

    assert response.status_code == 200
    body = response.json()
    assert body["citations"] == []
    assert NO_OFFICIAL_DOCUMENTS_DISCLOSURE in body["reply"]
    assert body["reply"] != contracts["no_citations"]["reply"]
    assert body["model"] == "general-ai-model"
    assert body["intent"] == contracts["no_citations"]["intent"]
    assert saved == [
        (USER_ID, "user", "Unknown topic", None),
        (USER_ID, "assistant", body["reply"], None),
    ]
    assert len(requests) == 1
    assert requests[0].query == "Unknown topic"
    assert [section.trigger for section in requests[0].mode_decision.sections] == [
        ModeTrigger.HEALTHY_OFFICIAL_NO_MATCH
    ]


def test_chat_keeps_frozen_fallback_when_general_ai_cannot_answer(
    authenticated_client: TestClient,
    contracts: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = _provider(_retrieval_result(with_evidence=False))

    async def execute(
        _request: GeneralAIExecutionRequest,
    ) -> GeneralAIExecutionResult:
        return GeneralAIExecutionResult(
            state=GeneralAIExecutionState.UNAVAILABLE,
            health=GeneralAIExecutionHealth.FAILED,
            safe_code="GENERAL_AI_PROVIDER_UNAVAILABLE",
        )

    monkeypatch.setattr(chat.settings, "ask_ai_general_mode_enabled", True)
    monkeypatch.setattr(chat.settings, "llm_model_chat", "contract-model")
    monkeypatch.setattr(chat, "get_chat_history", lambda *_: [])
    monkeypatch.setattr(chat, "save_chat_message", lambda *_: None)
    monkeypatch.setattr(chat.RetrievalProviderFactory, "get_provider", lambda: provider)
    monkeypatch.setattr(chat, "execute_general_ai", execute)
    monkeypatch.setattr(chat, "record_chat_retrieval_audit", lambda **_: None)

    response = authenticated_client.post("/chat", json={"message": "Unknown topic"})

    assert response.status_code == 200
    assert response.json() == contracts["no_citations"]


def test_chat_retrieval_outage_answers_with_qualified_general_ai_fallback(
    authenticated_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requests: list[GeneralAIExecutionRequest] = []

    def failing_provider() -> Any:
        def hybrid_search(*_args: Any, **_kwargs: Any) -> Any:
            raise RuntimeError("retrieval backend is down")

        return SimpleNamespace(
            provider_name="contract-provider",
            hybrid_search=hybrid_search,
        )

    async def execute(
        request: GeneralAIExecutionRequest,
    ) -> GeneralAIExecutionResult:
        requests.append(request)
        return _satisfied_general_ai(request)

    monkeypatch.setattr(chat.settings, "ask_ai_general_mode_enabled", True)
    monkeypatch.setattr(chat.settings, "llm_model_chat", "contract-model")
    monkeypatch.setattr(chat, "get_chat_history", lambda *_: [])
    monkeypatch.setattr(chat, "save_chat_message", lambda *_: True)
    monkeypatch.setattr(
        chat.RetrievalProviderFactory,
        "get_provider",
        failing_provider,
    )
    monkeypatch.setattr(chat, "execute_general_ai", execute)

    response = authenticated_client.post("/chat", json={"message": "Unknown topic"})

    assert response.status_code == 200
    body = response.json()
    assert body["citations"] == []
    assert OFFICIAL_SEARCH_UNAVAILABLE_DISCLOSURE in body["reply"]
    assert NO_OFFICIAL_DOCUMENTS_DISCLOSURE not in body["reply"]
    assert [section.trigger for section in requests[0].mode_decision.sections] == [
        ModeTrigger.OFFICIAL_RETRIEVAL_UNAVAILABLE
    ]


def test_chat_retrieval_outage_keeps_safe_500_when_general_ai_is_off(
    authenticated_client: TestClient,
    contracts: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def failing_provider() -> Any:
        def hybrid_search(*_args: Any, **_kwargs: Any) -> Any:
            raise RuntimeError("retrieval backend is down")

        return SimpleNamespace(
            provider_name="contract-provider",
            hybrid_search=hybrid_search,
        )

    monkeypatch.setattr(chat, "get_chat_history", lambda *_: [])
    monkeypatch.setattr(chat, "save_chat_message", lambda *_: True)
    monkeypatch.setattr(
        chat.RetrievalProviderFactory,
        "get_provider",
        failing_provider,
    )

    response = authenticated_client.post("/chat", json={"message": "Unknown topic"})

    assert response.status_code == contracts["retrieval_failure"]["status_code"]
    body = response.json()
    assert body["code"] == contracts["retrieval_failure"]["body"]["code"]
    assert body["detail"] == contracts["retrieval_failure"]["body"]["detail"]
    assert "retrieval backend is down" not in json.dumps(body)


def test_chat_metrics_observe_suppressed_persistence_without_changing_response(
    authenticated_client: TestClient,
    contracts: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
    metric_events: list[tuple[str, dict[str, Any]]],
) -> None:
    provider = _provider(_retrieval_result(with_evidence=False))

    monkeypatch.setattr(chat.settings, "llm_model_chat", "contract-model")
    monkeypatch.setattr(chat, "get_chat_history", lambda *_: [])
    monkeypatch.setattr(chat, "save_chat_message", lambda *_: False)
    monkeypatch.setattr(chat.RetrievalProviderFactory, "get_provider", lambda: provider)
    monkeypatch.setattr(chat, "record_chat_retrieval_audit", lambda **_: None)

    response = authenticated_client.post("/chat", json={"message": "Unknown topic"})

    assert response.status_code == 200
    assert response.json() == contracts["no_citations"]
    persistence = [
        fields
        for _, fields in metric_events
        if fields["metric_stage"] in {"user_persistence", "assistant_persistence"}
    ]
    assert [item["outcome"] for item in persistence] == [
        "suppressed_failure",
        "suppressed_failure",
    ]


def test_chat_model_failure_freezes_legacy_502_and_partial_persistence(
    authenticated_client: TestClient,
    contracts: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
    metric_events: list[tuple[str, dict[str, Any]]],
) -> None:
    saved: list[tuple[str, str, str, int | None]] = []
    error_logs: list[dict[str, Any]] = []
    provider = _provider(_retrieval_result(with_evidence=True))

    def fail_model(**_: Any) -> str:
        raise RuntimeError("parallel unavailable: upstream 503")

    monkeypatch.setattr(chat.settings, "llm_model_chat", "contract-model")
    monkeypatch.setattr(chat, "get_chat_history", lambda *_: [])
    monkeypatch.setattr(chat, "save_chat_message", lambda *args: saved.append(args))
    monkeypatch.setattr(chat.RetrievalProviderFactory, "get_provider", lambda: provider)
    monkeypatch.setattr(
        chat,
        "get_llm_client",
        lambda: SimpleNamespace(complete_text=fail_model),
    )
    monkeypatch.setattr(
        chat,
        "record_chat_retrieval_audit",
        lambda **_: pytest.fail("failed model calls are not audited by the legacy route"),
    )
    monkeypatch.setattr(
        ask_errors,
        "log_event",
        lambda *_, **kwargs: error_logs.append(kwargs),
    )

    response = authenticated_client.post("/chat", json={"message": "What applies?"})

    assert response.status_code == contracts["model_failure"]["status_code"]
    _assert_correlation(response)
    assert {
        key: response.json()[key]
        for key in contracts["model_failure"]["body"]
    } == contracts["model_failure"]["body"]
    assert "parallel unavailable: upstream 503" not in response.text
    assert error_logs[0]["error_detail"] == (
        "RuntimeError: parallel unavailable: upstream 503"
    )
    assert ("model", "unavailable") in [
        (fields["metric_stage"], fields["outcome"])
        for _, fields in metric_events
    ]
    assert metric_events[-1][1]["metric_stage"] == "request"
    assert metric_events[-1][1]["outcome"] == "unavailable"
    assert saved == [(USER_ID, "user", "What applies?", None)]


def test_chat_retrieval_exception_freezes_unhandled_500_and_partial_persistence(
    authenticated_client: TestClient,
    contracts: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
    metric_events: list[tuple[str, dict[str, Any]]],
) -> None:
    saved: list[tuple[str, str, str, int | None]] = []

    def fail_retrieval(*_: Any, **__: Any) -> Any:
        raise RuntimeError("vector database unavailable")

    provider = SimpleNamespace(
        provider_name="contract-provider",
        hybrid_search=fail_retrieval,
    )
    monkeypatch.setattr(chat, "get_chat_history", lambda *_: [])
    monkeypatch.setattr(chat, "save_chat_message", lambda *args: saved.append(args))
    monkeypatch.setattr(chat.RetrievalProviderFactory, "get_provider", lambda: provider)
    monkeypatch.setattr(
        chat,
        "get_llm_client",
        lambda: pytest.fail("the model must not run after retrieval raises"),
    )
    monkeypatch.setattr(
        chat,
        "record_chat_retrieval_audit",
        lambda **_: pytest.fail("unhandled retrieval failures are not audited"),
    )

    response = authenticated_client.post("/chat", json={"message": "What applies?"})

    assert response.status_code == contracts["retrieval_failure"]["status_code"]
    _assert_correlation(response)
    assert {
        key: response.json()[key]
        for key in contracts["retrieval_failure"]["body"]
    } == contracts["retrieval_failure"]["body"]
    assert saved == [(USER_ID, "user", "What applies?", None)]
    assert metric_events[-2][1]["metric_stage"] == "retrieval"
    assert metric_events[-2][1]["outcome"] == "unavailable"
    assert metric_events[-1][1]["metric_stage"] == "request"
    assert metric_events[-1][1]["outcome"] == "unavailable"


def test_chat_history_repository_freezes_descending_shape_limit_and_event_filter(
    contracts: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    executed: list[tuple[str, dict[str, Any]]] = []
    rows = [
        {
            **item,
            "created_at": datetime.fromisoformat(item["created_at"]),
        }
        for item in contracts["history"]
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

    result = repository.chat_history(USER_ID, 77)

    assert result == rows
    assert len(executed) == 1
    sql, params = executed[0]
    assert "event_id = :event_id" in sql
    assert "order by created_at desc" in sql
    assert "limit 20" in sql
    assert params == {"user_id": USER_ID, "event_id": 77}


def test_chat_history_freezes_http_shape(
    authenticated_client: TestClient,
    contracts: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, int | None]] = []

    def get_history(user_id: str, event_id: int | None) -> list[dict[str, Any]]:
        calls.append((user_id, event_id))
        return contracts["history"]

    monkeypatch.setattr(chat, "get_chat_history", get_history)

    response = authenticated_client.get("/chat/history?event_id=77")

    assert response.status_code == 200
    _assert_correlation(response)
    assert response.json() == contracts["history"]
    assert calls == [(USER_ID, 77)]


def test_chat_history_datetime_values_freeze_current_validation_failure(
    authenticated_client: TestClient,
    contracts: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rows = [
        {
            **item,
            "created_at": datetime.fromisoformat(item["created_at"]),
        }
        for item in contracts["history"]
    ]
    monkeypatch.setattr(chat, "get_chat_history", lambda *_: rows)

    response = authenticated_client.get("/chat/history?event_id=77")

    assert response.status_code == contracts["history_datetime_failure"]["status_code"]
    assert response.text == contracts["history_datetime_failure"]["body"]


def test_decision_shadow_flag_and_background_work_never_change_legacy_response(
    authenticated_client: TestClient,
    contracts: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = _provider(_retrieval_result(with_evidence=False))
    shadow_calls: list[dict[str, Any]] = []

    class ShadowService:
        def evaluate_and_record(self, **kwargs: Any) -> None:
            shadow_calls.append(kwargs)

    monkeypatch.setattr(chat.settings, "llm_model_chat", "contract-model")
    monkeypatch.setattr(chat, "get_chat_history", lambda *_: [])
    monkeypatch.setattr(chat, "save_chat_message", lambda *_: True)
    monkeypatch.setattr(chat.RetrievalProviderFactory, "get_provider", lambda: provider)
    monkeypatch.setattr(chat, "record_chat_retrieval_audit", lambda **_: None)
    monkeypatch.setattr(
        chat,
        "get_decision_shadow_service",
        lambda _: ShadowService(),
    )
    monkeypatch.setattr(chat.settings, "ask_ai_decision_engine_enabled", False)

    disabled = authenticated_client.post(
        "/chat",
        json={"message": "What applies?"},
    )
    assert shadow_calls == []

    monkeypatch.setattr(chat.settings, "ask_ai_decision_engine_enabled", True)
    enabled = authenticated_client.post(
        "/chat",
        json={"message": "What applies?"},
    )

    assert disabled.status_code == enabled.status_code == 200
    assert disabled.json() == enabled.json() == contracts["no_citations"]
    assert shadow_calls == [
        {"query": "What applies?", "legacy_intent": "general"}
    ]


def test_decision_shadow_factory_failure_is_suppressed(
    authenticated_client: TestClient,
    contracts: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = _provider(_retrieval_result(with_evidence=False))
    monkeypatch.setattr(chat.settings, "llm_model_chat", "contract-model")
    monkeypatch.setattr(chat.settings, "ask_ai_decision_engine_enabled", True)
    monkeypatch.setattr(chat, "get_chat_history", lambda *_: [])
    monkeypatch.setattr(chat, "save_chat_message", lambda *_: True)
    monkeypatch.setattr(chat.RetrievalProviderFactory, "get_provider", lambda: provider)
    monkeypatch.setattr(chat, "record_chat_retrieval_audit", lambda **_: None)
    monkeypatch.setattr(
        chat,
        "get_decision_shadow_service",
        lambda _: (_ for _ in ()).throw(RuntimeError("unavailable")),
    )

    response = authenticated_client.post(
        "/chat",
        json={"message": "What applies?"},
    )

    assert response.status_code == 200
    assert response.json() == contracts["no_citations"]


def test_chat_and_history_freeze_anonymous_auth_rejection(
    contracts: dict[str, Any],
) -> None:
    app = FastAPI()
    app.add_middleware(AskCorrelationMiddleware)
    app.include_router(chat.router)
    app.dependency_overrides[limit_chat] = lambda: None

    with TestClient(app, raise_server_exceptions=False) as client:
        responses = [
            client.post("/chat", json={"message": "What applies?"}),
            client.get("/chat/history"),
        ]

    for response in responses:
        assert response.status_code == contracts["auth_rejection"]["status_code"]
        assert response.json() == contracts["auth_rejection"]["body"]
        _assert_correlation(response)
