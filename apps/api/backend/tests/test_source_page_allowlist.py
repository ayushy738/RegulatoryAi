"""DB-backed source page selection + domain safety policy tests."""

from __future__ import annotations

import inspect
from contextlib import contextmanager
from typing import Any
from unittest.mock import MagicMock

import pytest

from backend.core import repository
from backend.core.models import SourcePagePayload
from backend.core.source_page_policy import (
    SourcePagePolicyError,
    crawl_domains_for_source,
    diagnose_source_page_selection,
    host_permitted,
    page_url_permitted_for_source,
    validate_public_http_url,
    validate_source_page_url,
)
from backend.core.utils import canonical_url


# Former production ALLOWED_SOURCE_PAGE_URLS entries (exact 25).
FORMER_PRODUCTION_ALLOWLIST_CASES: list[tuple[str, str, list[str], str]] = [
    (
        "mnre",
        "https://mnre.gov.in/en/monthly-updates/",
        ["mnre.gov.in", "cdnbbsr.s3waas.gov.in"],
        "https://mnre.gov.in/en/notice-category/current-notices/",
    ),
    (
        "mnre",
        "https://mnre.gov.in/en/monthly-updates/",
        ["mnre.gov.in", "cdnbbsr.s3waas.gov.in"],
        "https://mnre.gov.in/en/monthly-updates/",
    ),
    (
        "cerc",
        "https://cercind.gov.in/",
        ["cercind.gov.in"],
        "https://cercind.gov.in/public-notice.html",
    ),
    (
        "cerc",
        "https://cercind.gov.in/",
        ["cercind.gov.in"],
        "https://cercind.gov.in/SPN.html",
    ),
    (
        "cerc",
        "https://cercind.gov.in/",
        ["cercind.gov.in"],
        "https://cercind.gov.in/notice-letter.html",
    ),
    (
        "seci",
        "https://www.seci.co.in",
        ["seci.co.in", "www.seci.co.in"],
        "https://www.seci.co.in/tenders",
    ),
    (
        "mop",
        "https://powermin.gov.in/en",
        ["powermin.gov.in"],
        "https://www.powermin.gov.in/whats-new",
    ),
    (
        "kerc",
        "https://kerc.karnataka.gov.in/en",
        ["kerc.karnataka.gov.in", "karunadu.karnataka.gov.in"],
        "https://kerc.karnataka.gov.in/events/en",
    ),
    (
        "kerc",
        "https://kerc.karnataka.gov.in/en",
        ["kerc.karnataka.gov.in", "karunadu.karnataka.gov.in"],
        "https://kerc.karnataka.gov.in/27/regulations/en",
    ),
    (
        "kerc",
        "https://kerc.karnataka.gov.in/en",
        ["kerc.karnataka.gov.in", "karunadu.karnataka.gov.in"],
        "https://kerc.karnataka.gov.in/28/draft-regulations/en",
    ),
    (
        "kerc",
        "https://kerc.karnataka.gov.in/en",
        ["kerc.karnataka.gov.in", "karunadu.karnataka.gov.in"],
        "https://kerc.karnataka.gov.in/42/miscellaneous-orders/en",
    ),
    (
        "kerc",
        "https://kerc.karnataka.gov.in/en",
        ["kerc.karnataka.gov.in", "karunadu.karnataka.gov.in"],
        "https://kerc.karnataka.gov.in/73/generic-tariff-orders/en",
    ),
    (
        "kerc",
        "https://kerc.karnataka.gov.in/en",
        ["kerc.karnataka.gov.in", "karunadu.karnataka.gov.in"],
        "https://kerc.karnataka.gov.in/48/discussion-papers/en",
    ),
    (
        "grid_india",
        "https://grid-india.in/en/home",
        ["grid-india.in", "webapi.grid-india.in", "webcdn.grid-india.in"],
        "https://grid-india.in/en/documents/iegc-procedures",
    ),
    (
        "grid_india",
        "https://grid-india.in/en/home",
        ["grid-india.in", "webapi.grid-india.in", "webcdn.grid-india.in"],
        "https://grid-india.in/en/documents/notified-procedures",
    ),
    (
        "grid_india",
        "https://grid-india.in/en/home",
        ["grid-india.in", "webapi.grid-india.in", "webcdn.grid-india.in"],
        "https://grid-india.in/en/documents/connectivity-and-gna-procedure",
    ),
    (
        "grid_india",
        "https://grid-india.in/en/home",
        ["grid-india.in", "webapi.grid-india.in", "webcdn.grid-india.in"],
        "https://grid-india.in/en/documents/other-procedures",
    ),
    (
        "grid_india",
        "https://grid-india.in/en/home",
        ["grid-india.in", "webapi.grid-india.in", "webcdn.grid-india.in"],
        "https://grid-india.in/en/documents/consultation-papers",
    ),
    (
        "grid_india",
        "https://grid-india.in/en/home",
        ["grid-india.in", "webapi.grid-india.in", "webcdn.grid-india.in"],
        "https://grid-india.in/en/announcements/notices",
    ),
    (
        "ctuil",
        "https://ctuil.in/",
        ["ctuil.in", "www.ctuil.in"],
        "https://ctuil.in/latestnews",
    ),
    (
        "ctuil",
        "https://ctuil.in/",
        ["ctuil.in", "www.ctuil.in"],
        "https://ctuil.in/advisory",
    ),
    (
        "ctuil",
        "https://ctuil.in/",
        ["ctuil.in", "www.ctuil.in"],
        "https://ctuil.in/regulation_procedures",
    ),
    (
        "ctuil",
        "https://ctuil.in/",
        ["ctuil.in", "www.ctuil.in"],
        "https://ctuil.in/format_gna",
    ),
    (
        "ctuil",
        "https://ctuil.in/",
        ["ctuil.in", "www.ctuil.in"],
        "https://ctuil.in/regenerators",
    ),
    (
        "ctuil",
        "https://ctuil.in/",
        ["ctuil.in", "www.ctuil.in"],
        "https://ctuil.in/draft_procedures",
    ),
]

DERC_URLS = (
    "https://www.derc.gov.in/regulations/draft-regulations",
    "https://www.derc.gov.in/notices/gazette-notifications",
    "https://www.derc.gov.in/notices/press-release",
)


def _mappings(rows: list[dict[str, Any]]):
    class _Mappings:
        def __init__(self, values: list[dict[str, Any]]):
            self._rows = values

        def __iter__(self):
            return iter(self._rows)

        def first(self):
            return self._rows[0] if self._rows else None

    return _Mappings(rows)


def test_allowed_source_page_urls_cannot_accidentally_come_back() -> None:
    assert not hasattr(repository, "ALLOWED_SOURCE_PAGE_URLS")
    source = inspect.getsource(repository.list_enabled_source_pages)
    assert "ALLOWED_SOURCE_PAGE_URLS" not in source
    assert "canonical_url(str(row" not in source


def test_new_admin_source_page_is_selected_solely_from_db(monkeypatch) -> None:
    """Admin-created enabled page is crawlable with no code allowlist entry."""

    sql_rows = [
        {
            "id": 9001,
            "source_id": 99,
            "name": "Notices",
            "url": "https://new-regulator.example.gov.in/notices",
            "page_type": "listing",
            "priority": 10,
            "enabled": True,
            "last_crawled_at": None,
            "source_code": "NEWREG",
            "source_name": "New Regulator",
            "source_url": "https://new-regulator.example.gov.in/",
            "jurisdiction": "state",
            "crawler_type": "agent",
            "allowed_domains": ["new-regulator.example.gov.in"],
            "hint": None,
        }
    ]
    session = MagicMock()
    session.execute.return_value.mappings.return_value = _mappings(sql_rows)

    @contextmanager
    def fake_scope():
        yield session

    monkeypatch.setattr(repository, "session_scope", fake_scope)
    pages = repository.list_enabled_source_pages(source_id=99)
    assert len(pages) == 1
    assert pages[0]["id"] == 9001
    assert pages[0]["url"] == "https://new-regulator.example.gov.in/notices"
    sql = str(session.execute.call_args.args[0])
    assert "s.enabled = true" in sql
    assert "sp.enabled = true" in sql
    assert "ALLOWED_SOURCE_PAGE_URLS" not in sql


def test_disabled_source_is_excluded(monkeypatch) -> None:
    session = MagicMock()
    session.execute.return_value.mappings.return_value = _mappings([])

    @contextmanager
    def fake_scope():
        yield session

    monkeypatch.setattr(repository, "session_scope", fake_scope)
    assert repository.list_enabled_source_pages(source_id=18) == []
    sql = str(session.execute.call_args.args[0])
    assert "s.enabled = true" in sql


def test_disabled_page_is_excluded(monkeypatch) -> None:
    session = MagicMock()
    session.execute.return_value.mappings.return_value = _mappings([])

    @contextmanager
    def fake_scope():
        yield session

    monkeypatch.setattr(repository, "session_scope", fake_scope)
    assert repository.list_enabled_source_pages(source_id=18) == []
    sql = str(session.execute.call_args.args[0])
    assert "sp.enabled = true" in sql


def test_derc_empty_allowed_domains_accepts_own_host() -> None:
    domains = crawl_domains_for_source(
        source_url="https://www.derc.gov.in/",
        allowed_domains=[],
    )
    assert domains == ["www.derc.gov.in"]
    for url in DERC_URLS:
        validate_source_page_url(
            page_url=url,
            source_url="https://www.derc.gov.in/",
            allowed_domains=[],
        )
        assert page_url_permitted_for_source(
            page_url=url,
            source_url="https://www.derc.gov.in/",
            allowed_domains=[],
        )


def test_configured_subdomains_continue_working() -> None:
    assert page_url_permitted_for_source(
        page_url="https://www.powermin.gov.in/whats-new",
        source_url="https://powermin.gov.in/en",
        allowed_domains=["powermin.gov.in"],
    )
    assert page_url_permitted_for_source(
        page_url="https://www.seci.co.in/tenders",
        source_url="https://www.seci.co.in",
        allowed_domains=["seci.co.in", "www.seci.co.in"],
    )
    assert host_permitted(
        "webcdn.grid-india.in",
        crawl_domains_for_source(
            source_url="https://grid-india.in/en/home",
            allowed_domains=["grid-india.in", "webapi.grid-india.in", "webcdn.grid-india.in"],
        ),
    )
    assert host_permitted(
        "cdnbbsr.s3waas.gov.in",
        crawl_domains_for_source(
            source_url="https://mnre.gov.in/en/monthly-updates/",
            allowed_domains=["mnre.gov.in", "cdnbbsr.s3waas.gov.in"],
        ),
    )


def test_external_domain_is_rejected() -> None:
    with pytest.raises(SourcePagePolicyError, match="outside source allowed domains"):
        validate_source_page_url(
            page_url="https://evil.example/notices",
            source_url="https://www.derc.gov.in/",
            allowed_domains=[],
        )
    assert not page_url_permitted_for_source(
        page_url="https://attacker.example/docs",
        source_url="https://ctuil.in/",
        allowed_domains=["ctuil.in"],
    )


def test_localhost_private_ip_metadata_targets_are_rejected() -> None:
    with pytest.raises(SourcePagePolicyError, match="not allowed"):
        validate_public_http_url("http://localhost/secret")
    with pytest.raises(SourcePagePolicyError, match="not allowed"):
        validate_public_http_url("http://metadata.google.internal/")
    with pytest.raises(SourcePagePolicyError, match="private|link-local"):
        validate_public_http_url("http://127.0.0.1/admin")
    with pytest.raises(SourcePagePolicyError, match="private|link-local"):
        validate_public_http_url("http://10.0.0.5/internal")
    with pytest.raises(SourcePagePolicyError, match="private|link-local"):
        validate_public_http_url("http://169.254.169.254/latest/meta-data")
    with pytest.raises(SourcePagePolicyError, match="http or https"):
        validate_public_http_url("file:///etc/passwd")
    with pytest.raises(SourcePagePolicyError, match="credentials"):
        validate_public_http_url("https://user:pass@www.derc.gov.in/x")


def test_former_25_production_urls_remain_valid() -> None:
    assert len(FORMER_PRODUCTION_ALLOWLIST_CASES) == 25
    for _code, source_url, domains, page_url in FORMER_PRODUCTION_ALLOWLIST_CASES:
        assert page_url_permitted_for_source(
            page_url=page_url,
            source_url=source_url,
            allowed_domains=domains,
        ), page_url


def test_list_enabled_returns_derc_pages_from_db_without_allowlist(monkeypatch) -> None:
    sql_rows = [
        {
            "id": 80 + index,
            "source_id": 18,
            "name": name,
            "url": url,
            "page_type": "listing",
            "priority": (index + 1) * 10,
            "enabled": True,
            "last_crawled_at": None,
            "source_code": "DERC",
            "source_name": "Delhi Electricity Regulatory Commission",
            "source_url": "https://www.derc.gov.in/",
            "jurisdiction": "state",
            "crawler_type": "agent",
            "allowed_domains": [],
            "hint": None,
        }
        for index, (name, url) in enumerate(
            [
                ("Draft Regulations", DERC_URLS[0]),
                ("Gazette Notifications", DERC_URLS[1]),
                ("Press Release", DERC_URLS[2]),
            ]
        )
    ]
    session = MagicMock()
    session.execute.return_value.mappings.return_value = _mappings(sql_rows)

    @contextmanager
    def fake_scope():
        yield session

    monkeypatch.setattr(repository, "session_scope", fake_scope)
    pages = repository.list_enabled_source_pages(source_id=18)
    assert [page["id"] for page in pages] == [80, 81, 82]
    assert [page["url"] for page in pages] == list(DERC_URLS)


def test_list_enabled_source_and_page_scope(monkeypatch) -> None:
    session = MagicMock()
    session.execute.return_value.mappings.return_value = _mappings([])

    @contextmanager
    def fake_scope():
        yield session

    monkeypatch.setattr(repository, "session_scope", fake_scope)
    repository.list_enabled_source_pages(source_id=18)
    assert session.execute.call_args.args[1]["source_id"] == 18
    repository.list_enabled_source_pages(page_id=82)
    assert session.execute.call_args.args[1]["page_id"] == 82


def test_create_source_page_rejects_external_domain(monkeypatch) -> None:
    session = MagicMock()
    session.execute.return_value.mappings.return_value = _mappings(
        [{"id": 18, "url": "https://www.derc.gov.in/", "allowed_domains": []}]
    )

    @contextmanager
    def fake_scope():
        yield session

    monkeypatch.setattr(repository, "session_scope", fake_scope)
    with pytest.raises(SourcePagePolicyError, match="outside source allowed domains"):
        repository.create_source_page(
            18,
            SourcePagePayload(
                name="External",
                url="https://attacker.example/docs",
                page_type="listing",
                priority=10,
                enabled=True,
            ),
        )


def test_create_source_page_accepts_derc_host_with_empty_allowed_domains(
    monkeypatch,
) -> None:
    class _Result:
        def __init__(self, rows: list[dict[str, Any]]):
            self._rows = rows

        def mappings(self):
            return _mappings(self._rows)

    def fake_execute(statement, params=None):
        sql = str(statement).lower()
        if "from sources" in sql:
            return _Result(
                [{"id": 18, "url": "https://www.derc.gov.in/", "allowed_domains": []}]
            )
        return _Result(
            [
                {
                    "id": 90,
                    "source_id": 18,
                    "name": params["name"],
                    "url": params["url"],
                    "page_type": params["page_type"],
                    "priority": params["priority"],
                    "enabled": params["enabled"],
                    "last_crawled_at": None,
                    "created_at": None,
                    "updated_at": None,
                }
            ]
        )

    session = MagicMock()
    session.execute.side_effect = fake_execute

    @contextmanager
    def fake_scope():
        yield session

    monkeypatch.setattr(repository, "session_scope", fake_scope)
    page = repository.create_source_page(
        18,
        SourcePagePayload(
            name="Draft Regulations",
            url="HTTPS://WWW.DERC.GOV.IN/regulations/draft-regulations",
            page_type="listing",
            priority=10,
            enabled=True,
        ),
    )
    assert page["url"] == "https://www.derc.gov.in/regulations/draft-regulations"


def test_canonical_case_normalization_still_permits_valid_pages() -> None:
    assert canonical_url("HTTPS://WWW.DERC.GOV.IN/regulations/draft-regulations") == (
        "https://www.derc.gov.in/regulations/draft-regulations"
    )
    assert page_url_permitted_for_source(
        page_url="HTTPS://WWW.DERC.GOV.IN/regulations/draft-regulations",
        source_url="https://www.derc.gov.in/",
        allowed_domains=[],
    )


def test_diagnose_empty_selection_reasons() -> None:
    ok = diagnose_source_page_selection(
        source_id=18,
        page_id=None,
        configured_pages=[{"source_code": "DERC", "source_enabled": True}],
        enabled_pages=[{"id": 1}],
        crawlable_pages=[{"id": 1}],
    )
    assert ok["reason"] is None

    disabled_pages = diagnose_source_page_selection(
        source_id=18,
        page_id=None,
        configured_pages=[
            {"source_code": "DERC", "source_enabled": True, "id": 1},
            {"source_code": "DERC", "source_enabled": True, "id": 2},
        ],
        enabled_pages=[],
        crawlable_pages=[],
    )
    assert disabled_pages["reason"] == "all_pages_disabled"

    domain = diagnose_source_page_selection(
        source_id=18,
        page_id=None,
        configured_pages=[{"source_code": "DERC", "source_enabled": True, "id": 1}],
        enabled_pages=[{"id": 1}],
        crawlable_pages=[],
    )
    assert domain["reason"] == "invalid_source_domain_configuration"
