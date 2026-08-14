"""Phase 3: durable document persistence commits before downstream intelligence."""

from __future__ import annotations

import asyncio
from contextlib import contextmanager, nullcontext
from typing import Any
from unittest.mock import MagicMock

import pytest
from sqlalchemy.exc import SQLAlchemyError

from backend.core import repository
from backend.core.models import (
    DiscoveredDoc,
    EventIntelligence,
    ExtractedDoc,
    FetchedFile,
    SummaryPayload,
)


def _sample_extracted(*, url: str = "https://example.gov.in/orders/phase3-doc.pdf") -> ExtractedDoc:
    discovered = DiscoveredDoc(
        source_code="CERC",
        title="CERC Order on Grid Connectivity Phase 3 Boundary",
        source_url=url,
        issuing_body="CERC",
        doc_type="order",
        jurisdiction="central",
    )
    fetched = FetchedFile(
        discovered=discovered,
        file_hash="filehash-phase3-001",
        raw_file_path="/tmp/phase3.pdf",
        http_status=200,
    )
    return ExtractedDoc(
        fetched=fetched,
        text=(
            "This Central Electricity Regulatory Commission order establishes "
            "grid connectivity obligations for transmission licensees and "
            "sets a compliance deadline for generators."
        ),
        content_hash="contenthash-phase3-001",
        page_count=2,
        needs_ocr=False,
        text_path="/tmp/phase3.txt",
    )


def _summary() -> SummaryPayload:
    return SummaryPayload(
        plain_english_summary="Grid connectivity obligations updated.",
        why_it_matters="Transmission licensees must comply.",
    )


def _intelligence(*, allowed: bool = True) -> EventIntelligence:
    return EventIntelligence(
        event_allowed=allowed,
        rejection_reason=None if allowed else "test",
        freshness="CURRENT",
        freshness_reason="recent",
        significance_score=80,
        significance_category="HIGH",
        actionability="ACTIONABLE",
        title_quality_score=80,
        document_quality_score=80,
        date_confidence_score=80,
        quality_score=80,
        quality_category="GOOD",
    )


def _durable_state(
    extracted: ExtractedDoc,
    *,
    document_id: int = 42,
    version_id: int = 7,
    create_events: bool = False,
) -> repository._DurableDocumentState:
    return repository._DurableDocumentState(
        extracted=extracted,
        url=extracted.fetched.discovered.source_url,
        content_hash=extracted.content_hash,
        document_id=document_id,
        version_id=version_id,
        source_id=1,
        prior_reference=None,
        family_id=9,
        assignment_type="NEW_FAMILY",
        had_prior_document=False,
        create_events=create_events,
        topics=["grid"],
        summary=_summary(),
        intelligence=_intelligence(),
    )


def test_document_survives_graph_llm_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    extracted = _sample_extracted()
    durable_docs: set[int] = set()
    order: list[str] = []

    def fake_durable(*_a: Any, **_k: Any) -> repository._DurableDocumentState:
        state = _durable_state(extracted, document_id=101)
        durable_docs.add(state.document_id)
        order.append("commit_a")
        return state

    def boom_graph(*_a: Any, **_k: Any) -> None:
        order.append("graph_llm")
        raise RuntimeError("LLM provider unavailable")

    @contextmanager
    def fake_scope() -> Any:
        session = MagicMock()
        session.begin_nested.return_value = nullcontext()
        yield session
        order.append("commit_b")

    monkeypatch.setattr(repository, "_persist_document_durable", fake_durable)
    monkeypatch.setattr(repository, "session_scope", fake_scope)
    monkeypatch.setattr(repository, "_run_graph_extraction_for_document", boom_graph)
    monkeypatch.setattr(
        repository,
        "_enqueue_rag_indexing_for_document",
        lambda *_a, **_k: order.append("rag"),
    )

    # Real _run_graph_extraction swallows; force uncaught path via patched helper.
    # _process_document_downstream calls boom_graph which raises — orchestrator isolates.
    result = repository._persist_extracted_document(extracted)

    assert result is None
    assert 101 in durable_docs
    assert order[0] == "commit_a"
    assert "graph_llm" in order


def test_document_survives_graph_persistence_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    extracted = _sample_extracted()
    durable_docs: set[int] = set()

    def fake_durable(*_a: Any, **_k: Any) -> repository._DurableDocumentState:
        state = _durable_state(extracted, document_id=102)
        durable_docs.add(state.document_id)
        return state

    def boom_downstream(_state: repository._DurableDocumentState) -> int | None:
        raise RuntimeError("graph persistence write failed")

    monkeypatch.setattr(repository, "_persist_document_durable", fake_durable)
    monkeypatch.setattr(repository, "_process_document_downstream", boom_downstream)

    assert repository._persist_extracted_document(extracted) is None
    assert 102 in durable_docs


def test_document_survives_rag_enqueue_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    extracted = _sample_extracted()
    durable_docs: set[int] = set()
    order: list[str] = []

    def fake_durable(*_a: Any, **_k: Any) -> repository._DurableDocumentState:
        state = _durable_state(extracted, document_id=103)
        durable_docs.add(state.document_id)
        order.append("commit_a")
        return state

    @contextmanager
    def fake_scope() -> Any:
        session = MagicMock()
        session.begin_nested.return_value = nullcontext()
        yield session

    def boom_rag(*_a: Any, **_k: Any) -> None:
        order.append("rag")
        raise RuntimeError("rag enqueue failed")

    monkeypatch.setattr(repository, "_persist_document_durable", fake_durable)
    monkeypatch.setattr(repository, "session_scope", fake_scope)
    monkeypatch.setattr(
        repository,
        "_run_graph_extraction_for_document",
        lambda *_a, **_k: order.append("graph"),
    )
    monkeypatch.setattr(repository, "_enqueue_rag_indexing_for_document", boom_rag)

    assert repository._persist_extracted_document(extracted) is None
    assert 103 in durable_docs
    assert order[0] == "commit_a"
    assert "rag" in order


def test_document_survives_downstream_sql_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    extracted = _sample_extracted()
    durable_docs: set[int] = set()

    def fake_durable(*_a: Any, **_k: Any) -> repository._DurableDocumentState:
        state = _durable_state(extracted, document_id=104)
        durable_docs.add(state.document_id)
        return state

    def boom_sql(_state: repository._DurableDocumentState) -> int | None:
        raise SQLAlchemyError("downstream event insert failed")

    monkeypatch.setattr(repository, "_persist_document_durable", fake_durable)
    monkeypatch.setattr(repository, "_process_document_downstream", boom_sql)

    assert repository._persist_extracted_document(extracted) is None
    assert 104 in durable_docs


def test_persistence_commit_happens_before_llm_call(monkeypatch: pytest.MonkeyPatch) -> None:
    extracted = _sample_extracted()
    order: list[str] = []

    def fake_durable(*_a: Any, **_k: Any) -> repository._DurableDocumentState:
        order.append("session_a_commit")
        return _durable_state(extracted, document_id=105, create_events=False)

    @contextmanager
    def fake_scope() -> Any:
        session = MagicMock()
        session.begin_nested.return_value = nullcontext()
        try:
            yield session
            order.append("session_b_commit")
        except Exception:
            order.append("session_b_rollback")
            raise

    def fake_analyze(*_a: Any, **_k: Any) -> Any:
        order.append("llm_call")
        raise RuntimeError("should be isolated by graph helper")

    monkeypatch.setattr(repository, "_persist_document_durable", fake_durable)
    monkeypatch.setattr(repository, "session_scope", fake_scope)
    monkeypatch.setattr(repository, "analyze_and_persist_regulatory_graph", fake_analyze)
    monkeypatch.setattr(
        repository,
        "enqueue_rag_index_job",
        lambda *_a, **_k: order.append("rag_enqueue"),
    )

    repository._persist_extracted_document(extracted)

    assert "session_a_commit" in order
    assert "llm_call" in order
    assert order.index("session_a_commit") < order.index("llm_call")


def test_cancelled_error_after_document_commit_does_not_erase_document(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    extracted = _sample_extracted()
    durable_docs: set[int] = set()

    def fake_durable(*_a: Any, **_k: Any) -> repository._DurableDocumentState:
        state = _durable_state(extracted, document_id=106)
        durable_docs.add(state.document_id)
        return state

    def cancel_downstream(_state: repository._DurableDocumentState) -> int | None:
        raise asyncio.CancelledError()

    monkeypatch.setattr(repository, "_persist_document_durable", fake_durable)
    monkeypatch.setattr(repository, "_process_document_downstream", cancel_downstream)

    with pytest.raises(asyncio.CancelledError):
        repository._persist_extracted_document(extracted)

    assert 106 in durable_docs


def test_durable_session_does_not_invoke_graph_or_rag(monkeypatch: pytest.MonkeyPatch) -> None:
    """Session A must not perform LLM/graph/RAG while its transaction is open."""

    extracted = _sample_extracted()
    calls: list[str] = []

    def forbidden_graph(*_a: Any, **_k: Any) -> None:
        calls.append("graph")
        raise AssertionError("graph must not run during Session A")

    def forbidden_rag(*_a: Any, **_k: Any) -> None:
        calls.append("rag")
        raise AssertionError("rag must not run during Session A")

    class _Row:
        def __init__(self, **kwargs: Any) -> None:
            self.__dict__.update(kwargs)

    class _Result:
        def __init__(self, row: Any = None) -> None:
            self._row = row

        def first(self) -> Any:
            return self._row

    class _Session:
        def execute(self, stmt: Any, params: dict[str, Any] | None = None) -> _Result:
            sql = str(stmt).lower()
            params = params or {}
            if "from sources" in sql:
                return _Result(_Row(id=1))
            if "from document_versions" in sql and "join documents" in sql:
                return _Result(None)
            if "insert into documents" in sql:
                return _Result(_Row(id=501))
            if "insert into document_texts" in sql:
                return _Result(None)
            if "insert into document_versions" in sql:
                return _Result(_Row(id=601))
            return _Result(None)

    @contextmanager
    def fake_scope() -> Any:
        calls.append("session_a_open")
        try:
            yield _Session()
            calls.append("session_a_commit")
        finally:
            calls.append("session_a_closed")

    from backend.pipeline.family_registry import RegistryResult

    monkeypatch.setattr(repository, "session_scope", fake_scope)
    monkeypatch.setattr(repository, "_run_graph_extraction_for_document", forbidden_graph)
    monkeypatch.setattr(repository, "_enqueue_rag_indexing_for_document", forbidden_rag)
    monkeypatch.setattr(
        repository,
        "register_document_version_family",
        lambda *_a, **_k: RegistryResult(
            document_id=501,
            family_id=11,
            registry_version_id=1,
            assignment_type="NEW_FAMILY",
            confidence=1.0,
            canonical_title="CERC Order",
            evidence="test",
            deadline_count=0,
            amendment_number=None,
            relationship_type=None,
        ),
    )

    state = repository._persist_document_durable(
        extracted,
        topics=["grid"],
        summary=_summary(),
        intelligence=_intelligence(),
    )

    assert state is not None
    assert state.document_id == 501
    assert state.version_id == 601
    assert "graph" not in calls
    assert "rag" not in calls
    assert calls == ["session_a_open", "session_a_commit", "session_a_closed"]
