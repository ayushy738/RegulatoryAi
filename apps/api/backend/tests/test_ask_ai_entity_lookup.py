from __future__ import annotations

from uuid import UUID

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from backend.api.auth import CurrentUser, current_user
from backend.api.routes import chat_entities, chat_sessions
from backend.ask.decision.models import EntityClass
from backend.ask.entity_lookup import (
    EntityLookupCandidate,
    EntityLookupRequest,
    EntityLookupResponse,
    EntityLookupUnavailable,
    entity_intelligence_route,
)

USER_ID = UUID("11111111-1111-4111-8111-111111111111")


def _candidate(
    *,
    canonical_id: str = "in.central.dsm",
    canonical_name: str = "Deviation Settlement Mechanism",
) -> EntityLookupCandidate:
    return EntityLookupCandidate(
        canonical_id=canonical_id,
        canonical_name=canonical_name,
        entity_class=EntityClass.REGULATORY_CONCEPT,
        jurisdiction="India/Central",
        aliases=("DSM",),
        confidence=0.95,
        assumed=False,
        match_reason="Matched an approved alias.",
        entity_route=entity_intelligence_route(canonical_id),
    )


class FakeEntityLookupService:
    def __init__(self) -> None:
        self.calls: list[EntityLookupRequest] = []
        self.error = False

    def resolve(self, request: EntityLookupRequest) -> EntityLookupResponse:
        self.calls.append(request)
        if self.error:
            raise EntityLookupUnavailable()
        return EntityLookupResponse(
            status="resolved",
            mention=request.mention,
            match_rule="exact_alias",
            selected=_candidate(),
            surface="entity_intelligence_page",
        )


@pytest.fixture
def service() -> FakeEntityLookupService:
    return FakeEntityLookupService()


@pytest.fixture
def app(service: FakeEntityLookupService) -> FastAPI:
    api = FastAPI()
    api.include_router(chat_entities.router)
    api.dependency_overrides[current_user] = lambda: CurrentUser(
        id=str(USER_ID),
        email="entity-owner@example.test",
    )
    api.dependency_overrides[
        chat_entities.get_entity_lookup_service
    ] = lambda: service
    return api


def test_request_and_response_contracts_are_strict_and_route_canonical() -> None:
    request = EntityLookupRequest(
        mention="  DSM  ",
        active_jurisdiction=" India/Central ",
    )
    assert request.mention == "DSM"
    assert request.active_jurisdiction == "India/Central"
    assert entity_intelligence_route("in.central.dsm") == (
        "/ask?entity=in.central.dsm"
    )

    with pytest.raises(ValidationError):
        EntityLookupRequest.model_validate(
            {"mention": "DSM", "raw_sql": "select *"}
        )
    with pytest.raises(ValidationError, match="canonical identity"):
        _candidate().model_copy(
            update={"entity_route": "/ask?entity=other"}
        ).model_validate(
            {
                **_candidate().model_dump(),
                "entity_route": "/ask?entity=other",
            }
        )


def test_response_refuses_crossed_terminal_shapes_and_duplicate_candidates() -> None:
    with pytest.raises(ValidationError, match="outcome shape"):
        EntityLookupResponse(
            status="resolved",
            mention="DSM",
            match_rule="exact_alias",
        )
    candidate = _candidate()
    with pytest.raises(ValidationError, match="must be unique"):
        EntityLookupResponse(
            status="ambiguous",
            mention="ARC",
            match_rule="clarification",
            candidates=(candidate, candidate),
            clarification_question="Which ARC?",
        )


def test_resolve_endpoint_is_authenticated_flagged_and_minimized(
    app: FastAPI,
    service: FakeEntityLookupService,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(chat_sessions.settings, "ask_ai_v2_api_enabled", True)

    with TestClient(app) as client:
        response = client.post(
            "/chat/entities/resolve",
            json={
                "mention": " DSM ",
                "active_jurisdiction": "India/Central",
            },
        )

    assert response.status_code == 200
    assert response.json() == {
        "schema_version": "1",
        "policy_version": "ask-ai-decision-v1",
        "status": "resolved",
        "mention": "DSM",
        "match_rule": "exact_alias",
        "selected": {
            "canonical_id": "in.central.dsm",
            "canonical_name": "Deviation Settlement Mechanism",
            "entity_class": "regulatory_concept",
            "jurisdiction": "India/Central",
            "aliases": ["DSM"],
            "confidence": 0.95,
            "assumed": False,
            "match_reason": "Matched an approved alias.",
            "entity_route": "/ask?entity=in.central.dsm",
        },
        "candidates": [],
        "clarification_question": None,
        "surface": "entity_intelligence_page",
    }
    assert service.calls == [
        EntityLookupRequest(
            mention="DSM",
            active_jurisdiction="India/Central",
        )
    ]
    assert "provenance_ref" not in response.text
    assert "metadata" not in response.text


def test_flag_off_and_authentication_stop_lookup_before_service(
    app: FastAPI,
    service: FakeEntityLookupService,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(chat_sessions.settings, "ask_ai_v2_api_enabled", False)
    with TestClient(app) as client:
        disabled = client.post(
            "/chat/entities/resolve",
            json={"mention": "DSM"},
        )

    monkeypatch.setattr(chat_sessions.settings, "ask_ai_v2_api_enabled", True)
    unauthenticated = FastAPI()
    unauthenticated.include_router(chat_entities.router)
    with TestClient(unauthenticated, raise_server_exceptions=False) as client:
        anonymous = client.post(
            "/chat/entities/resolve",
            json={"mention": "DSM"},
        )

    assert disabled.status_code == 404
    assert disabled.json() == {"detail": "Not found"}
    assert anonymous.status_code == 401
    assert service.calls == []


def test_unavailable_and_invalid_inputs_are_safe(
    app: FastAPI,
    service: FakeEntityLookupService,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(chat_sessions.settings, "ask_ai_v2_api_enabled", True)
    service.error = True

    with TestClient(app) as client:
        unavailable = client.post(
            "/chat/entities/resolve",
            json={"mention": "DSM"},
        )
        invalid = client.post(
            "/chat/entities/resolve",
            json={"mention": " ", "debug_provider": True},
        )

    assert unavailable.status_code == 503
    assert unavailable.json() == {
        "detail": "Entity lookup is temporarily unavailable"
    }
    assert invalid.status_code == 422
    assert service.calls == [EntityLookupRequest(mention="DSM")]
