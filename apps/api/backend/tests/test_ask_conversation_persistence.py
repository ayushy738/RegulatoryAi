"""Conversation persistence helpers for Ask chat."""

from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException

from backend.api.routes import chat
from backend.core.models import ChatRequest


def test_conversation_title_truncates_long_questions() -> None:
    title = chat._conversation_title(
        "What are the current DSM obligations for Indian DISCOMs today?"
    )
    assert "DSM" in title
    assert len(title) <= 72


def test_resolve_session_creates_new_conversation(monkeypatch: pytest.MonkeyPatch) -> None:
    created_id = uuid4()

    class FakeService:
        def get_session(self, **_: object) -> None:
            return None

        def create_session(self, **_: object) -> SimpleNamespace:
            return SimpleNamespace(id=created_id)

    monkeypatch.setattr(chat, "AskPersistenceService", FakeService)
    session_id = chat._resolve_session_id(
        "11111111-1111-4111-8111-111111111111",
        ChatRequest(message="What is DSM in India?"),
    )
    assert session_id == str(created_id)


def test_resolve_session_rejects_foreign_conversation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeService:
        def get_session(self, **_: object) -> None:
            return None

    monkeypatch.setattr(chat, "AskPersistenceService", FakeService)
    with pytest.raises(HTTPException) as exc:
        chat._resolve_session_id(
            "11111111-1111-4111-8111-111111111111",
            ChatRequest(message="hi", session_id=str(uuid4())),
        )
    assert exc.value.status_code == 404


def test_ensure_citation_text_hides_chunk_ids() -> None:
    from datetime import date

    from backend.rag.models import BuiltContext, Citation

    context = BuiltContext(
        prompt_context="ctx",
        citations=[
            Citation(
                document_id=1,
                title="DSM Framework",
                issuer="KERC",
                issue_date=date(2026, 3, 10),
                source_url="https://example.gov.in/dsm",
                chunk_id=3852,
                page_number=12,
            )
        ],
        graph_facts=[],
        related_questions=[],
        estimated_tokens=10,
    )
    text = chat._ensure_citation_text("Answer body.", context)
    assert "chunk=" not in text
    assert "3852" not in text
    assert "DSM Framework" in text


def test_friendly_conversation_title_hides_legacy_label() -> None:
    from backend.core.repository import _friendly_conversation_title

    assert _friendly_conversation_title("Legacy Ask history") == "Untitled chat"
    assert (
        _friendly_conversation_title(
            "What are the current DSM obligations for Indian DISCOMs?"
        )
        == "Current DSM obligations for Indian DISCOMs"
    )
