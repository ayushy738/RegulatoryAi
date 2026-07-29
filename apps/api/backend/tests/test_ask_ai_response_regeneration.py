from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from backend.api.auth import CurrentUser, current_user
from backend.api.routes import chat_evidence, chat_sessions
from backend.ask.regeneration import (
    RefreshResponseRequest,
    RegenerateResponseRequest,
    ResponseMutationOperation,
    ResponseRegenerationConflict,
    ResponseRegenerationNotEligible,
    ResponseRegenerationNotFound,
    ResponseRegenerationPlan,
    ResponseRegenerationRecord,
    ResponseRegenerationResponse,
    ResponseSourceStrategy,
    ResponseStyleVariant,
)

USER_ID = UUID("11111111-1111-4111-8111-111111111111")
SESSION_ID = UUID("22222222-2222-4222-8222-222222222222")
USER_MESSAGE_ID = UUID("33333333-3333-4333-8333-333333333333")
SOURCE_MESSAGE_ID = UUID("44444444-4444-4444-8444-444444444444")
SOURCE_RUN_ID = UUID("55555555-5555-4555-8555-555555555555")
PARENT_MESSAGE_ID = UUID("66666666-6666-4666-8666-666666666666")
TARGET_MESSAGE_ID = UUID("77777777-7777-4777-8777-777777777777")
TARGET_RUN_ID = UUID("88888888-8888-4888-8888-888888888888")
REQUEST_ID = UUID("99999999-9999-4999-8999-999999999999")
SOURCE_ID = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")


def _record(
    *,
    operation: ResponseMutationOperation = ResponseMutationOperation.REGENERATE,
    source_strategy: ResponseSourceStrategy = ResponseSourceStrategy.SAME_SOURCES,
    style_variant: ResponseStyleVariant = ResponseStyleVariant.DEFAULT,
) -> ResponseRegenerationRecord:
    reused = (SOURCE_ID,) if operation is ResponseMutationOperation.REGENERATE else ()
    refresh_modes: tuple[str, ...] = ()
    if source_strategy is ResponseSourceStrategy.REFRESH_OFFICIAL:
        refresh_modes = ("official",)
    elif source_strategy is ResponseSourceStrategy.INCLUDE_LIVE:
        refresh_modes = ("official", "live")
    return ResponseRegenerationRecord(
        request_id=REQUEST_ID,
        plan=ResponseRegenerationPlan(
            request_id=REQUEST_ID,
            operation=operation,
            source_strategy=source_strategy,
            style_variant=style_variant,
            session_id=SESSION_ID,
            user_id=USER_ID,
            user_message_id=31,
            user_message_public_id=USER_MESSAGE_ID,
            source_run_id=SOURCE_RUN_ID,
            source_response_version=1,
            source_assistant_message_id=SOURCE_MESSAGE_ID,
            source_snapshot_ids=(SOURCE_ID,),
            reused_source_snapshot_ids=reused,
            refresh_knowledge_modes=refresh_modes,
            parent_assistant_message_id=PARENT_MESSAGE_ID,
            parent_response_version=2,
            target_run_id=TARGET_RUN_ID,
            target_assistant_message_id=TARGET_MESSAGE_ID,
            target_response_version=3,
            research_request_artifact_id=f"response-mutation:{REQUEST_ID}",
        ),
    )


class FakeRegenerationService:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.error: Exception | None = None

    def regenerate(self, **kwargs: Any) -> ResponseRegenerationRecord:
        self.calls.append(("regenerate", kwargs))
        if self.error is not None:
            raise self.error
        return _record()

    def refresh(self, **kwargs: Any) -> ResponseRegenerationRecord:
        self.calls.append(("refresh", kwargs))
        if self.error is not None:
            raise self.error
        return _record(
            operation=ResponseMutationOperation.REFRESH,
            source_strategy=ResponseSourceStrategy.INCLUDE_LIVE,
            style_variant=ResponseStyleVariant.LEGAL_DETAIL,
        )


@pytest.fixture
def service() -> FakeRegenerationService:
    return FakeRegenerationService()


@pytest.fixture
def app(service: FakeRegenerationService) -> FastAPI:
    api = FastAPI()
    api.include_router(chat_evidence.router)
    api.dependency_overrides[current_user] = lambda: CurrentUser(
        id=str(USER_ID),
        email="owner@example.test",
    )
    api.dependency_overrides[
        chat_evidence.get_ask_regeneration_service
    ] = lambda: service
    return api


def test_strict_request_contracts_cover_every_frozen_variant() -> None:
    for variant in ResponseStyleVariant:
        request = RegenerateResponseRequest(
            idempotency_key=uuid4(),
            assistant_message_id=uuid4(),
            style_variant=variant,
        )
        assert request.style_variant is variant
    for strategy in (
        ResponseSourceStrategy.REFRESH_OFFICIAL,
        ResponseSourceStrategy.INCLUDE_LIVE,
    ):
        request = RefreshResponseRequest(
            idempotency_key=uuid4(),
            assistant_message_id=uuid4(),
            source_strategy=strategy,
        )
        assert request.source_strategy == strategy

    with pytest.raises(ValidationError):
        RegenerateResponseRequest.model_validate(
            {
                "idempotency_key": str(uuid4()),
                "assistant_message_id": str(uuid4()),
                "source_strategy": "refresh_official",
            }
        )
    with pytest.raises(ValidationError):
        RefreshResponseRequest.model_validate(
            {
                "idempotency_key": str(uuid4()),
                "assistant_message_id": str(uuid4()),
                "source_strategy": "same_sources",
            }
        )


def test_plan_rejects_crossed_reuse_and_refresh_lineage() -> None:
    valid = _record().plan.model_dump()
    valid["reused_source_snapshot_ids"] = []
    with pytest.raises(ValidationError, match="reuse every snapshot"):
        ResponseRegenerationPlan.model_validate(valid)

    refresh = _record(
        operation=ResponseMutationOperation.REFRESH,
        source_strategy=ResponseSourceStrategy.INCLUDE_LIVE,
    ).plan.model_dump()
    refresh["refresh_knowledge_modes"] = ["live"]
    with pytest.raises(ValidationError, match="do not match"):
        ResponseRegenerationPlan.model_validate(refresh)


def test_minimized_response_excludes_owner_and_internal_message_ids() -> None:
    payload = ResponseRegenerationResponse.from_record(_record()).model_dump(
        mode="json"
    )

    assert payload["request_id"] == str(REQUEST_ID)
    assert payload["source_message_id"] == str(SOURCE_MESSAGE_ID)
    assert payload["target_response_version"] == 3
    assert payload["reused_source_ids"] == [str(SOURCE_ID)]
    assert "user_id" not in payload
    assert "user_message_id" not in payload


def test_regenerate_and_refresh_endpoints_forward_exact_owner_and_contract(
    app: FastAPI,
    service: FakeRegenerationService,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(chat_sessions.settings, "ask_ai_v2_api_enabled", True)
    regenerate_body = {
        "schema_version": "1",
        "idempotency_key": str(REQUEST_ID),
        "assistant_message_id": str(TARGET_MESSAGE_ID),
        "style_variant": "default",
    }
    refresh_body = {
        **regenerate_body,
        "source_strategy": "include_live",
        "style_variant": "legal_detail",
    }

    with TestClient(app) as client:
        regenerated = client.post(
            f"/chat/messages/{SOURCE_MESSAGE_ID}/regenerate",
            json=regenerate_body,
        )
        refreshed = client.post(
            f"/chat/messages/{SOURCE_MESSAGE_ID}/refresh",
            json=refresh_body,
        )

    assert regenerated.status_code == refreshed.status_code == 202
    assert regenerated.json()["source_strategy"] == "same_sources"
    assert regenerated.json()["reused_source_ids"] == [str(SOURCE_ID)]
    assert refreshed.json()["source_strategy"] == "include_live"
    assert refreshed.json()["refresh_knowledge_modes"] == ["official", "live"]
    assert service.calls[0][1]["source_message_id"] == SOURCE_MESSAGE_ID
    assert service.calls[0][1]["user_id"] == USER_ID
    assert isinstance(
        service.calls[0][1]["request"],
        RegenerateResponseRequest,
    )
    assert isinstance(service.calls[1][1]["request"], RefreshResponseRequest)


@pytest.mark.parametrize(
    ("error", "status_code", "detail"),
    [
        (ResponseRegenerationNotFound(), 404, "Message not found"),
        (
            ResponseRegenerationNotEligible(),
            409,
            "Message cannot create another response version",
        ),
        (
            ResponseRegenerationConflict(),
            409,
            "Response version conflict",
        ),
    ],
)
def test_endpoint_errors_are_fixed_and_non_disclosing(
    app: FastAPI,
    service: FakeRegenerationService,
    monkeypatch: pytest.MonkeyPatch,
    error: Exception,
    status_code: int,
    detail: str,
) -> None:
    monkeypatch.setattr(chat_sessions.settings, "ask_ai_v2_api_enabled", True)
    service.error = error

    with TestClient(app) as client:
        response = client.post(
            f"/chat/messages/{SOURCE_MESSAGE_ID}/regenerate",
            json={
                "idempotency_key": str(REQUEST_ID),
                "assistant_message_id": str(TARGET_MESSAGE_ID),
            },
        )

    assert response.status_code == status_code
    assert response.json() == {"detail": detail}


def test_flag_off_and_authentication_block_mutations_before_service_access(
    app: FastAPI,
    service: FakeRegenerationService,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(chat_sessions.settings, "ask_ai_v2_api_enabled", False)
    body = {
        "idempotency_key": str(REQUEST_ID),
        "assistant_message_id": str(TARGET_MESSAGE_ID),
    }

    with TestClient(app) as client:
        disabled = client.post(
            f"/chat/messages/{SOURCE_MESSAGE_ID}/regenerate",
            json=body,
        )

    monkeypatch.setattr(chat_sessions.settings, "ask_ai_v2_api_enabled", True)
    unauthenticated = FastAPI()
    unauthenticated.include_router(chat_evidence.router)
    with TestClient(unauthenticated, raise_server_exceptions=False) as client:
        anonymous = client.post(
            f"/chat/messages/{SOURCE_MESSAGE_ID}/regenerate",
            json=body,
        )

    assert disabled.status_code == 404
    assert disabled.json() == {"detail": "Not found"}
    assert anonymous.status_code == 401
    assert service.calls == []


def test_invalid_refresh_contract_never_reaches_service(
    app: FastAPI,
    service: FakeRegenerationService,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(chat_sessions.settings, "ask_ai_v2_api_enabled", True)

    with TestClient(app) as client:
        response = client.post(
            f"/chat/messages/{SOURCE_MESSAGE_ID}/refresh",
            json={
                "idempotency_key": str(REQUEST_ID),
                "assistant_message_id": str(TARGET_MESSAGE_ID),
                "source_strategy": "same_sources",
                "provider_debug": True,
            },
        )

    assert response.status_code == 422
    assert service.calls == []
