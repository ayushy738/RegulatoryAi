from __future__ import annotations

from contextlib import nullcontext
from datetime import UTC, date, datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from backend.api.auth import CurrentUser, current_user
from backend.api.routes import chat_documents, chat_sessions
from backend.ask.manual_document_search import (
    ManualDocumentSearchCursorError,
    ManualDocumentSearchItem,
    ManualDocumentSearchRequest,
    ManualDocumentSearchResponse,
    ManualDocumentSearchService,
    ManualDocumentSearchUnavailable,
    WithinDocumentMatch,
)

NOW = datetime(2026, 7, 27, 12, tzinfo=UTC)


def _item(
    *,
    document_id: int = 10,
    registry_version_id: int | None = 20,
    relevance: int = 900,
    issue_date: date = date(2026, 1, 1),
) -> ManualDocumentSearchItem:
    suffix = (
        f":{registry_version_id}"
        if registry_version_id is not None
        else ""
    )
    return ManualDocumentSearchItem(
        result_id=f"document:{document_id}{suffix}",
        document_id=document_id,
        registry_version_id=registry_version_id,
        document_version_id=30 if registry_version_id is not None else None,
        family_id=40 if registry_version_id is not None else None,
        title="DSM Regulations",
        issuer="CERC",
        document_number="CERC/DSM/2026",
        document_type="REGULATION",
        jurisdiction="central",
        issue_date=issue_date,
        publication_date=issue_date,
        effective_date=date(2026, 2, 1),
        family_title="Deviation Settlement Mechanism Regulations",
        version_label="Version 2",
        status="current",
        metadata_state="complete",
        why_matched="Exact official document metadata phrase matched.",
        relevance=relevance,
        source_url="https://example.test/dsm",
        route=(
            f"/browse?document={document_id}&version={registry_version_id}"
            if registry_version_id is not None
            else f"/browse?document={document_id}"
        ),
        within_document_matches=(
            WithinDocumentMatch(
                chunk_id=50,
                page_number=4,
                section_title="Applicability",
                excerpt="The deviation charge applies to generators.",
            ),
        ),
    )


class FakeRepository:
    calls: list[tuple[ManualDocumentSearchRequest, date, object | None]] = []
    items: tuple[ManualDocumentSearchItem, ...] = (_item(),)
    has_more = True
    error: Exception | None = None

    def __init__(self, _session: object) -> None:
        pass

    def search(
        self,
        *,
        request: ManualDocumentSearchRequest,
        as_of: date,
        cursor: object | None,
    ) -> tuple[tuple[ManualDocumentSearchItem, ...], bool]:
        self.calls.append((request, as_of, cursor))
        if self.error is not None:
            raise self.error
        return self.items, self.has_more


def _service() -> ManualDocumentSearchService:
    FakeRepository.calls = []
    FakeRepository.items = (_item(),)
    FakeRepository.has_more = True
    FakeRepository.error = None
    return ManualDocumentSearchService(
        session_scope_factory=lambda: nullcontext(object()),
        repository_factory=FakeRepository,
        clock=lambda: NOW,
    )


def test_request_normalizes_all_fields_and_rejects_unbounded_search() -> None:
    request = ManualDocumentSearchRequest(
        query="  deviation   charge ",
        exact_phrase=True,
        title=" DSM  Regulations ",
        issuer=" CERC ",
        document_number=" CERC/DSM/2026 ",
        document_type=" regulation ",
        family=" DSM family ",
        version=" Version 2 ",
        status="current",
        issued_from=date(2026, 1, 1),
        effective_to=date(2026, 12, 31),
        within_document=" generators ",
    )

    assert request.model_dump(mode="json") == {
        "schema_version": "1",
        "document_id": None,
        "registry_version_id": None,
        "query": "deviation charge",
        "exact_phrase": True,
        "title": "DSM Regulations",
        "issuer": "CERC",
        "document_number": "CERC/DSM/2026",
        "document_type": "regulation",
        "family": "DSM family",
        "version": "Version 2",
        "status": "current",
        "issued_from": "2026-01-01",
        "issued_to": None,
        "effective_from": None,
        "effective_to": "2026-12-31",
        "within_document": "generators",
        "cursor": None,
        "limit": 20,
    }
    with pytest.raises(ValidationError):
        ManualDocumentSearchRequest()
    with pytest.raises(ValidationError):
        ManualDocumentSearchRequest(title="DSM", exact_phrase=True)
    with pytest.raises(ValidationError):
        ManualDocumentSearchRequest(
            title="DSM",
            issued_from=date(2026, 2, 1),
            issued_to=date(2026, 1, 1),
        )


def test_service_returns_ordered_results_and_filter_bound_cursor() -> None:
    service = _service()
    first = service.search(
        ManualDocumentSearchRequest(query="DSM", limit=1)
    )

    assert first.status == "complete"
    assert first.as_of == date(2026, 7, 27)
    assert first.items[0].within_document_matches[0].page_number == 4
    assert first.next_cursor is not None
    page = service.search(
        ManualDocumentSearchRequest(
            query="DSM",
            cursor=first.next_cursor,
            limit=1,
        )
    )
    assert FakeRepository.calls[-1][2] is not None
    assert page.as_of == first.as_of
    with pytest.raises(ManualDocumentSearchCursorError):
        service.search(
            ManualDocumentSearchRequest(
                query="ABT",
                cursor=first.next_cursor,
            )
        )


def test_service_distinguishes_no_match_and_unavailability() -> None:
    service = _service()
    FakeRepository.items = ()
    FakeRepository.has_more = False

    no_match = service.search(ManualDocumentSearchRequest(title="unknown"))

    assert no_match.status == "no_match"
    assert no_match.items == ()
    assert no_match.next_cursor is None
    FakeRepository.error = RuntimeError("raw database detail")
    with pytest.raises(ManualDocumentSearchUnavailable) as raised:
        service.search(ManualDocumentSearchRequest(title="DSM"))
    assert "raw database detail" not in str(raised.value)

    invalid_clock = ManualDocumentSearchService(
        session_scope_factory=lambda: nullcontext(object()),
        repository_factory=FakeRepository,
        clock=lambda: datetime(2026, 7, 27),
    )
    with pytest.raises(ManualDocumentSearchUnavailable):
        invalid_clock.search(ManualDocumentSearchRequest(title="DSM"))


def test_result_contract_rejects_crossed_identity_order_and_unsafe_urls() -> None:
    with pytest.raises(ValidationError):
        ManualDocumentSearchItem.model_validate(
            {
                **_item().model_dump(mode="json"),
                "result_id": "document:99",
            }
        )
    with pytest.raises(ValidationError):
        ManualDocumentSearchItem.model_validate(
            {
                **_item().model_dump(mode="json"),
                "source_url": "javascript:alert(1)",
            }
        )
    with pytest.raises(ValidationError):
        ManualDocumentSearchResponse(
            status="complete",
            as_of=date(2026, 7, 27),
            items=(
                _item(
                    document_id=9,
                    registry_version_id=None,
                    relevance=700,
                ),
                _item(document_id=10, relevance=900),
            ),
        )


class FakeApiService:
    error: Exception | None = None
    calls: list[ManualDocumentSearchRequest] = []

    def search(
        self,
        request: ManualDocumentSearchRequest,
    ) -> ManualDocumentSearchResponse:
        self.calls.append(request)
        if self.error is not None:
            raise self.error
        return ManualDocumentSearchResponse(
            status="complete",
            as_of=date(2026, 7, 27),
            items=(_item(),),
        )


@pytest.fixture
def api_service() -> FakeApiService:
    service = FakeApiService()
    service.error = None
    service.calls = []
    return service


@pytest.fixture
def app(api_service: FakeApiService) -> FastAPI:
    api = FastAPI()
    api.include_router(chat_documents.router)
    api.dependency_overrides[current_user] = lambda: CurrentUser(
        id="11111111-1111-4111-8111-111111111111",
        email="manual-search@example.test",
    )
    api.dependency_overrides[
        chat_documents.get_manual_document_search_service
    ] = lambda: api_service
    return api


def test_api_is_authenticated_flagged_and_minimized(
    app: FastAPI,
    api_service: FakeApiService,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(chat_sessions.settings, "ask_ai_v2_api_enabled", True)
    with TestClient(app) as client:
        response = client.post(
            "/chat/documents/search",
            json={"query": " DSM ", "exact_phrase": True},
        )

    assert response.status_code == 200
    assert response.json()["items"][0]["title"] == "DSM Regulations"
    assert "raw" not in response.text
    assert api_service.calls[0].query == "DSM"


def test_api_uses_fixed_cursor_storage_auth_and_flag_errors(
    app: FastAPI,
    api_service: FakeApiService,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(chat_sessions.settings, "ask_ai_v2_api_enabled", True)
    with TestClient(app) as client:
        api_service.error = ManualDocumentSearchCursorError()
        bad_cursor = client.post(
            "/chat/documents/search",
            json={"title": "DSM"},
        )
        api_service.error = ManualDocumentSearchUnavailable()
        unavailable = client.post(
            "/chat/documents/search",
            json={"title": "DSM"},
        )
    assert bad_cursor.status_code == 400
    assert bad_cursor.json() == {
        "detail": "Invalid manual document search cursor"
    }
    assert unavailable.status_code == 503
    assert unavailable.json() == {
        "detail": "Manual document search is temporarily unavailable"
    }

    monkeypatch.setattr(chat_sessions.settings, "ask_ai_v2_api_enabled", False)
    with TestClient(app) as client:
        disabled = client.post(
            "/chat/documents/search",
            json={"title": "DSM"},
        )
    assert disabled.status_code == 404

    monkeypatch.setattr(chat_sessions.settings, "ask_ai_v2_api_enabled", True)
    app.dependency_overrides.pop(current_user)
    with TestClient(app) as client:
        unauthenticated = client.post(
            "/chat/documents/search",
            json={"title": "DSM"},
        )
    assert unauthenticated.status_code == 401
