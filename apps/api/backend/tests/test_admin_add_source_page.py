"""Tests for adding monitored pages to an existing source (Admin path)."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any
from unittest.mock import MagicMock

import pytest

from backend.core import repository
from backend.core.models import SourcePagePayload
from backend.core.source_page_policy import SourcePageConflictError, SourcePagePolicyError
from backend.core.utils import canonical_url


GERC_SOURCE_URL = "https://gercin.org/"
GERC_EXISTING = "https://gercin.org/orders/orders_renewable_energy"
GERC_TARIFF = "https://gercin.org/orders/tariff_orders"
GERC_DRAFT = "https://gercin.org/regulations/draft_regulations"


def _mappings(rows: list[dict[str, Any]]):
    class _Mappings:
        def __init__(self, values: list[dict[str, Any]]):
            self._rows = values

        def __iter__(self):
            return iter(self._rows)

        def first(self):
            return self._rows[0] if self._rows else None

    return _Mappings(rows)


def test_add_page_to_existing_gerc_source(monkeypatch) -> None:
    stored: list[dict[str, Any]] = []

    class _Result:
        def __init__(self, rows: list[dict[str, Any]]):
            self._rows = rows

        def mappings(self):
            return _mappings(self._rows)

    def fake_execute(statement, params=None):
        sql = str(statement).lower()
        if "from sources" in sql and "where id" in sql:
            return _Result(
                [
                    {
                        "id": 42,
                        "url": GERC_SOURCE_URL,
                        "allowed_domains": ["gercin.org", "www.gercin.org"],
                    }
                ]
            )
        if "from source_pages" in sql and "select id, url" in sql:
            return _Result(
                [
                    {"id": 1, "url": GERC_EXISTING, "deleted_at": None},
                    {"id": 2, "url": GERC_TARIFF, "deleted_at": None},
                ]
            )
        if "insert into source_pages" in sql:
            assert params is not None
            assert params["url"] == canonical_url(GERC_DRAFT)
            assert params["priority"] == 30
            assert params["enabled"] is True
            row = {
                "id": 3,
                "source_id": 42,
                "name": params["name"],
                "url": params["url"],
                "page_type": params["page_type"],
                "priority": params["priority"],
                "enabled": params["enabled"],
                "last_crawled_at": None,
                "created_at": None,
                "updated_at": None,
                "deleted_at": None,
                "deleted_by": None,
            }
            stored.append(row)
            return _Result([row])
        raise AssertionError(f"Unexpected SQL: {sql}")

    session = MagicMock()
    session.execute.side_effect = fake_execute

    @contextmanager
    def fake_scope():
        yield session

    monkeypatch.setattr(repository, "session_scope", fake_scope)
    page = repository.create_source_page(
        42,
        SourcePagePayload(
            name="Draft Regulations",
            url=GERC_DRAFT,
            page_type="listing",
            priority=30,
            enabled=True,
        ),
    )
    assert page["id"] == 3
    assert page["url"] == GERC_DRAFT
    assert stored[0]["name"] == "Draft Regulations"


def test_duplicate_canonical_url_rejected(monkeypatch) -> None:
    class _Result:
        def __init__(self, rows: list[dict[str, Any]]):
            self._rows = rows

        def mappings(self):
            return _mappings(self._rows)

    def fake_execute(statement, params=None):
        sql = str(statement).lower()
        if "from sources" in sql:
            return _Result(
                [{"id": 42, "url": GERC_SOURCE_URL, "allowed_domains": ["gercin.org"]}]
            )
        if "from source_pages" in sql:
            return _Result([{"id": 1, "url": GERC_EXISTING, "deleted_at": None}])
        raise AssertionError("insert must not run for duplicate")

    session = MagicMock()
    session.execute.side_effect = fake_execute

    @contextmanager
    def fake_scope():
        yield session

    monkeypatch.setattr(repository, "session_scope", fake_scope)
    with pytest.raises(SourcePageConflictError, match="Source page already exists"):
        repository.create_source_page(
            42,
            SourcePagePayload(
                name="Orders Renewable Energy",
                url="HTTPS://GERCIN.ORG/orders/orders_renewable_energy",
                page_type="listing",
                priority=10,
                enabled=True,
            ),
        )


def test_add_page_rejects_external_domain(monkeypatch) -> None:
    class _Result:
        def __init__(self, rows: list[dict[str, Any]]):
            self._rows = rows

        def mappings(self):
            return _mappings(self._rows)

    session = MagicMock()
    session.execute.return_value = _Result(
        [{"id": 42, "url": GERC_SOURCE_URL, "allowed_domains": ["gercin.org"]}]
    )

    @contextmanager
    def fake_scope():
        yield session

    monkeypatch.setattr(repository, "session_scope", fake_scope)
    with pytest.raises(SourcePagePolicyError, match="outside source allowed domains"):
        repository.create_source_page(
            42,
            SourcePagePayload(
                name="External",
                url="https://evil.example/regulations",
                page_type="listing",
                priority=30,
                enabled=True,
            ),
        )


def test_add_page_accepts_allowed_domains_cdn_host(monkeypatch) -> None:
    class _Result:
        def __init__(self, rows: list[dict[str, Any]]):
            self._rows = rows

        def mappings(self):
            return _mappings(self._rows)

    def fake_execute(statement, params=None):
        sql = str(statement).lower()
        if "from sources" in sql:
            return _Result(
                [
                    {
                        "id": 1,
                        "url": "https://mnre.gov.in/en/monthly-updates/",
                        "allowed_domains": ["mnre.gov.in", "cdnbbsr.s3waas.gov.in"],
                    }
                ]
            )
        if "from source_pages" in sql and "select id, url" in sql:
            return _Result([])
        if "insert into source_pages" in sql:
            return _Result(
                [
                    {
                        "id": 11,
                        "source_id": 1,
                        "name": params["name"],
                        "url": params["url"],
                        "page_type": params["page_type"],
                        "priority": params["priority"],
                        "enabled": params["enabled"],
                        "last_crawled_at": None,
                        "created_at": None,
                        "updated_at": None,
                        "deleted_at": None,
                        "deleted_by": None,
                    }
                ]
            )
        raise AssertionError(sql)

    session = MagicMock()
    session.execute.side_effect = fake_execute

    @contextmanager
    def fake_scope():
        yield session

    monkeypatch.setattr(repository, "session_scope", fake_scope)
    page = repository.create_source_page(
        1,
        SourcePagePayload(
            name="CDN Listing",
            url="https://cdnbbsr.s3waas.gov.in/s3docs/index.html",
            page_type="listing",
            priority=40,
            enabled=True,
        ),
    )
    assert "cdnbbsr.s3waas.gov.in" in page["url"]


def test_new_gerc_page_appears_in_enabled_selection(monkeypatch) -> None:
    sql_rows = [
        {
            "id": 1,
            "source_id": 42,
            "name": "Orders on Renewable Energy",
            "url": GERC_EXISTING,
            "page_type": "listing",
            "priority": 10,
            "enabled": True,
            "last_crawled_at": None,
            "source_code": "GERC",
            "source_name": "Gujarat Electricity Regulatory Commission",
            "source_url": GERC_SOURCE_URL,
            "jurisdiction": "state",
            "crawler_type": "agent",
            "allowed_domains": ["gercin.org"],
            "hint": None,
        },
        {
            "id": 2,
            "source_id": 42,
            "name": "Tariff Orders",
            "url": GERC_TARIFF,
            "page_type": "listing",
            "priority": 20,
            "enabled": True,
            "last_crawled_at": None,
            "source_code": "GERC",
            "source_name": "Gujarat Electricity Regulatory Commission",
            "source_url": GERC_SOURCE_URL,
            "jurisdiction": "state",
            "crawler_type": "agent",
            "allowed_domains": ["gercin.org"],
            "hint": None,
        },
        {
            "id": 3,
            "source_id": 42,
            "name": "Draft Regulations",
            "url": GERC_DRAFT,
            "page_type": "listing",
            "priority": 30,
            "enabled": True,
            "last_crawled_at": None,
            "source_code": "GERC",
            "source_name": "Gujarat Electricity Regulatory Commission",
            "source_url": GERC_SOURCE_URL,
            "jurisdiction": "state",
            "crawler_type": "agent",
            "allowed_domains": ["gercin.org"],
            "hint": None,
        },
    ]
    session = MagicMock()
    session.execute.return_value.mappings.return_value = _mappings(sql_rows)

    @contextmanager
    def fake_scope():
        yield session

    monkeypatch.setattr(repository, "session_scope", fake_scope)
    pages = repository.list_enabled_source_pages(source_id=42)
    assert [page["id"] for page in pages] == [1, 2, 3]
    assert pages[2]["url"] == GERC_DRAFT
    assert pages[0]["priority"] <= pages[1]["priority"] <= pages[2]["priority"]
    sql = str(session.execute.call_args.args[0])
    assert "ALLOWED_SOURCE_PAGE_URLS" not in sql
    assert "s.enabled = true" in sql
    assert "sp.enabled = true" in sql


def test_disabled_new_page_excluded_from_enabled_selection(monkeypatch) -> None:
    # SQL filter returns only enabled rows; empty result proves exclusion path.
    session = MagicMock()
    session.execute.return_value.mappings.return_value = _mappings([])

    @contextmanager
    def fake_scope():
        yield session

    monkeypatch.setattr(repository, "session_scope", fake_scope)
    assert repository.list_enabled_source_pages(source_id=42) == []
    assert "sp.enabled = true" in str(session.execute.call_args.args[0])


def test_no_hardcoded_allowlist_in_create_path() -> None:
    assert not hasattr(repository, "ALLOWED_SOURCE_PAGE_URLS")
