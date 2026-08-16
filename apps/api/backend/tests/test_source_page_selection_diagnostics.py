"""Focused tests for empty source-selection diagnostics."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any
from unittest.mock import MagicMock

from backend.core import repository


def _mappings(rows: list[dict[str, Any]]):
    class _Mappings:
        def __init__(self, values: list[dict[str, Any]]):
            self._rows = values

        def __iter__(self):
            return iter(self._rows)

        def first(self):
            return self._rows[0] if self._rows else None

    return _Mappings(rows)


def test_explain_empty_selection_for_enabled_derc_style_source(monkeypatch) -> None:
    """When pages are enabled+domain-valid, diagnosis should not claim zero crawlable."""

    rows = [
        {
            "id": 82,
            "source_id": 18,
            "url": "https://www.derc.gov.in/regulations/draft-regulations",
            "page_enabled": True,
            "source_code": "DERC",
            "source_enabled": True,
            "source_url": "https://www.derc.gov.in/",
            "allowed_domains": [],
        }
    ]
    session = MagicMock()
    session.execute.return_value.mappings.return_value = _mappings(rows)

    @contextmanager
    def fake_scope():
        yield session

    monkeypatch.setattr(repository, "session_scope", fake_scope)
    diagnosis = repository.explain_empty_source_page_selection(source_id=18)
    assert diagnosis["source"] == "DERC"
    assert diagnosis["source_id"] == 18
    assert diagnosis["configured_pages"] == 1
    assert diagnosis["enabled_pages"] == 1
    assert diagnosis["crawlable_pages"] == 1
    assert diagnosis["reason"] is None


def test_explain_empty_selection_all_pages_disabled(monkeypatch) -> None:
    rows = [
        {
            "id": 82,
            "source_id": 18,
            "url": "https://www.derc.gov.in/regulations/draft-regulations",
            "page_enabled": False,
            "source_code": "DERC",
            "source_enabled": True,
            "source_url": "https://www.derc.gov.in/",
            "allowed_domains": [],
        }
    ]
    session = MagicMock()
    session.execute.return_value.mappings.return_value = _mappings(rows)

    @contextmanager
    def fake_scope():
        yield session

    monkeypatch.setattr(repository, "session_scope", fake_scope)
    diagnosis = repository.explain_empty_source_page_selection(source_id=18)
    assert diagnosis["configured_pages"] == 1
    assert diagnosis["enabled_pages"] == 0
    assert diagnosis["crawlable_pages"] == 0
    assert diagnosis["reason"] == "all_pages_disabled"


def test_explain_empty_selection_source_with_no_pages(monkeypatch) -> None:
    calls = {"n": 0}

    def fake_execute(statement, params=None):
        calls["n"] += 1
        sql = str(statement).lower()
        result = MagicMock()
        if "from source_pages" in sql:
            result.mappings.return_value = _mappings([])
        else:
            result.mappings.return_value = _mappings(
                [
                    {
                        "id": 18,
                        "code": "DERC",
                        "enabled": True,
                        "url": "https://www.derc.gov.in/",
                        "allowed_domains": [],
                    }
                ]
            )
        return result

    session = MagicMock()
    session.execute.side_effect = fake_execute

    @contextmanager
    def fake_scope():
        yield session

    monkeypatch.setattr(repository, "session_scope", fake_scope)
    diagnosis = repository.explain_empty_source_page_selection(source_id=18)
    assert diagnosis["source"] == "DERC"
    assert diagnosis["configured_pages"] == 0
    assert diagnosis["reason"] == "no_source_pages_configured"
