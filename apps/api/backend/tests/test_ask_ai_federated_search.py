from __future__ import annotations

from contextlib import nullcontext
from datetime import UTC, datetime
from uuid import UUID

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from backend.api.auth import CurrentUser, current_user
from backend.api.routes import chat_search, chat_sessions
from backend.ask.decision.entity_policy import (
    EntityAlias,
    EntityAliasKind,
    EntityCatalogEntry,
)
from backend.ask.decision.models import EntityClass
from backend.ask.federated_search import (
    FederatedSearchCursorError,
    FederatedSearchRequest,
    FederatedSearchResponse,
    FederatedSearchService,
    FederatedSearchUnavailable,
    SearchFilters,
    SearchGroup,
    SearchPage,
    SearchRow,
)

USER_ID = UUID("11111111-1111-4111-8111-111111111111")
NOW = datetime(2026, 7, 27, tzinfo=UTC)


def _catalog() -> tuple[EntityCatalogEntry, ...]:
    return (
        EntityCatalogEntry(
            canonical_id="in.central.dsm",
            canonical_name="Deviation Settlement Mechanism",
            entity_class=EntityClass.REGULATORY_CONCEPT,
            jurisdiction="India/Central",
            aliases=(
                EntityAlias(
                    value="DSM",
                    kind=EntityAliasKind.ACRONYM,
                    jurisdiction="India/Central",
                ),
            ),
            workspace_priority=90,
            provenance_kind="curated_catalog",
            provenance_ref="fixture:dsm",
        ),
    )


class FakeCatalogRepository:
    def __init__(self, _session: object) -> None:
        pass

    def list_entries(self) -> tuple[EntityCatalogEntry, ...]:
        return _catalog()


class FakeSearchRepository:
    calls: list[tuple[SearchGroup, object | None, str, str]] = []
    fail_group: SearchGroup | None = None

    def __init__(self, _session: object) -> None:
        pass

    def search(self, **kwargs: object) -> SearchPage:
        group = kwargs["group"]
        cursor = kwargs["cursor"]
        query = kwargs["query"]
        original_query = kwargs["original_query"]
        assert isinstance(group, SearchGroup)
        assert isinstance(query, str)
        assert isinstance(original_query, str)
        self.calls.append((group, cursor, query, original_query))
        if group is self.fail_group:
            raise RuntimeError("raw storage detail")
        if group is SearchGroup.ENTITIES:
            return SearchPage(
                items=(
                    SearchRow(
                        stable_id="in.central.dsm",
                        title="Deviation Settlement Mechanism",
                        subtitle="regulatory_concept · India/Central",
                        why_matched="Approved entity alias or acronym matched.",
                        relevance=950,
                        sort_at=NOW,
                    ),
                ),
                has_more=True,
            )
        if group is SearchGroup.PREVIOUS_RESEARCH:
            return SearchPage(
                items=(
                    SearchRow(
                        stable_id="22222222-2222-4222-8222-222222222222",
                        title="DSM changes",
                        subtitle="DSM · Previous Research",
                        why_matched="Your previous research title matched.",
                        relevance=500,
                        sort_at=NOW,
                    ),
                ),
                has_more=False,
            )
        return SearchPage(items=(), has_more=False)


def _service() -> FederatedSearchService:
    FakeSearchRepository.calls = []
    FakeSearchRepository.fail_group = None
    return FederatedSearchService(
        session_scope_factory=lambda: nullcontext(object()),
        repository_factory=FakeSearchRepository,
        catalog_repository_factory=FakeCatalogRepository,
    )


def test_contracts_normalize_and_refuse_invalid_pagination() -> None:
    request = FederatedSearchRequest(
        query="  DSM   amendment ",
        filters=SearchFilters(jurisdiction=" India/Central "),
    )
    assert request.query == "DSM amendment"
    assert request.filters.jurisdiction == "India/Central"

    with pytest.raises(ValidationError):
        FederatedSearchRequest.model_validate(
            {"query": "DSM", "cursor": "opaque"}
        )
    with pytest.raises(ValidationError):
        SearchFilters(
            date_from=datetime(2026, 8, 1).date(),
            date_to=datetime(2026, 7, 1).date(),
        )
    assert SearchFilters(
        provenance="internal_regulatory_corpus",
        status=" NEW ",
        stakeholder=" generator ",
        topic=" settlement ",
        lifecycle="current",
    ).model_dump(mode="json") == {
        "provenance": "internal_regulatory_corpus",
        "jurisdiction": None,
        "regulator": None,
        "document_type": None,
        "entity_class": None,
        "status": "NEW",
        "stakeholder": "generator",
        "topic": "settlement",
        "lifecycle": "current",
        "date_from": None,
        "date_to": None,
    }
    with pytest.raises(ValidationError):
        FederatedSearchRequest.model_validate(
            {"query": "DSM", "raw_sql": "select *"}
        )


def test_service_returns_canonical_groups_best_match_and_reversible_expansion() -> None:
    response = _service().search(
        user_id=USER_ID,
        request=FederatedSearchRequest(query="DSM"),
    )

    assert isinstance(response, FederatedSearchResponse)
    assert tuple(group.group for group in response.groups) == tuple(SearchGroup)
    assert response.groups[0].items[0].result_id == (
        "entity:in.central.dsm"
    )
    assert response.groups[1].next_cursor is not None
    assert response.correction is not None
    assert response.correction.kind == "acronym_expansion"
    assert response.correction.original_query == "DSM"
    assert response.applied_query == "Deviation Settlement Mechanism"
    assert all(
        call[2:] == ("Deviation Settlement Mechanism", "DSM")
        for call in FakeSearchRepository.calls
    )
    previous = response.groups[-1].items[0]
    assert previous.provenance == "owned_research"
    assert previous.route.endswith(
        "22222222-2222-4222-8222-222222222222"
    )


def test_group_cursor_is_filter_bound_and_marks_other_groups_not_requested() -> None:
    service = _service()
    first = service.search(
        user_id=USER_ID,
        request=FederatedSearchRequest(query="DSM"),
    )
    cursor = first.groups[1].next_cursor
    assert cursor is not None

    page = service.search(
        user_id=USER_ID,
        request=FederatedSearchRequest(
            query="DSM",
            group=SearchGroup.ENTITIES,
            cursor=cursor,
        ),
    )

    assert FakeSearchRepository.calls[-1][0] is SearchGroup.ENTITIES
    assert FakeSearchRepository.calls[-1][1] is not None
    assert all(
        group.status == "not_requested"
        for group in page.groups[2:]
    )
    with pytest.raises(FederatedSearchCursorError):
        service.search(
            user_id=USER_ID,
            request=FederatedSearchRequest(
                query="ABT",
                group=SearchGroup.ENTITIES,
                cursor=cursor,
            ),
        )


def test_original_mode_reverses_correction_and_binds_the_cursor() -> None:
    service = _service()
    corrected = service.search(
        user_id=USER_ID,
        request=FederatedSearchRequest(query="DSM"),
    )
    corrected_cursor = corrected.groups[1].next_cursor
    assert corrected_cursor is not None

    original = service.search(
        user_id=USER_ID,
        request=FederatedSearchRequest(
            query="DSM",
            correction_mode="original",
        ),
    )

    assert original.applied_query == "DSM"
    assert original.correction is None
    assert all(
        call[2:] == ("DSM", "DSM")
        for call in FakeSearchRepository.calls[-7:]
    )
    with pytest.raises(FederatedSearchCursorError):
        service.search(
            user_id=USER_ID,
            request=FederatedSearchRequest(
                query="DSM",
                correction_mode="original",
                group=SearchGroup.ENTITIES,
                cursor=corrected_cursor,
            ),
        )


def test_service_exposes_isolated_group_degradation_without_raw_errors() -> None:
    service = _service()
    FakeSearchRepository.fail_group = SearchGroup.AMENDMENTS

    response = service.search(
        user_id=USER_ID,
        request=FederatedSearchRequest(query="DSM"),
    )

    groups = {group.group: group for group in response.groups}
    assert groups[SearchGroup.ENTITIES].status == "complete"
    assert groups[SearchGroup.AMENDMENTS].status == "unavailable"
    assert "raw storage detail" not in response.model_dump_json()


class FakeApiService:
    error: Exception | None = None
    calls: list[tuple[UUID, FederatedSearchRequest]] = []

    def search(
        self,
        *,
        user_id: UUID,
        request: FederatedSearchRequest,
    ) -> FederatedSearchResponse:
        self.calls.append((user_id, request))
        if self.error is not None:
            raise self.error
        return _service().search(user_id=user_id, request=request)


@pytest.fixture
def api_service() -> FakeApiService:
    service = FakeApiService()
    service.error = None
    service.calls = []
    return service


@pytest.fixture
def app(api_service: FakeApiService) -> FastAPI:
    api = FastAPI()
    api.include_router(chat_search.router)
    api.dependency_overrides[current_user] = lambda: CurrentUser(
        id=str(USER_ID),
        email="search-owner@example.test",
    )
    api.dependency_overrides[
        chat_search.get_federated_search_service
    ] = lambda: api_service
    return api


def test_search_api_is_authenticated_flagged_and_minimized(
    app: FastAPI,
    api_service: FakeApiService,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(chat_sessions.settings, "ask_ai_v2_api_enabled", True)
    with TestClient(app) as client:
        response = client.post(
            "/chat/search",
            json={"query": " DSM ", "limit": 5},
        )
    assert response.status_code == 200
    payload = response.json()
    assert payload["original_query"] == "DSM"
    assert payload["groups"][0]["group"] == "best_match"
    assert "provenance_ref" not in response.text
    assert api_service.calls[0][0] == USER_ID


def test_search_api_uses_fixed_cursor_and_storage_errors(
    app: FastAPI,
    api_service: FakeApiService,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(chat_sessions.settings, "ask_ai_v2_api_enabled", True)
    with TestClient(app) as client:
        api_service.error = FederatedSearchCursorError()
        bad_cursor = client.post(
            "/chat/search",
            json={"query": "DSM", "group": "entities", "cursor": "bad"},
        )
        api_service.error = FederatedSearchUnavailable()
        unavailable = client.post("/chat/search", json={"query": "DSM"})
    assert bad_cursor.status_code == 400
    assert bad_cursor.json() == {"detail": "Invalid research search cursor"}
    assert unavailable.status_code == 503
    assert unavailable.json() == {
        "detail": "Research search is temporarily unavailable"
    }


def test_search_api_requires_authentication_and_flag(
    app: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(chat_sessions.settings, "ask_ai_v2_api_enabled", False)
    with TestClient(app) as client:
        disabled = client.post("/chat/search", json={"query": "DSM"})
    assert disabled.status_code == 404

    monkeypatch.setattr(chat_sessions.settings, "ask_ai_v2_api_enabled", True)
    app.dependency_overrides.pop(current_user)
    with TestClient(app) as client:
        unauthenticated = client.post("/chat/search", json={"query": "DSM"})
    assert unauthenticated.status_code == 401
