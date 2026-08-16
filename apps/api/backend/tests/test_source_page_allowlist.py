"""Tests for curated source-page allowlist used by crawl selection."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any
from unittest.mock import MagicMock

from backend.core import repository
from backend.core.utils import canonical_url


CTUIL_URLS = (
    "https://ctuil.in/latestnews",
    "https://ctuil.in/advisory",
    "https://ctuil.in/regulation_procedures",
    "https://ctuil.in/format_gna",
    "https://ctuil.in/regenerators",
    "https://ctuil.in/draft_procedures",
)

CERC_URLS = (
    "https://cercind.gov.in/public-notice.html",
    "https://cercind.gov.in/SPN.html",
    "https://cercind.gov.in/notice-letter.html",
)


def test_allowed_source_page_urls_keeps_existing_cerc_entries() -> None:
    for url in CERC_URLS:
        assert canonical_url(url) in repository.ALLOWED_SOURCE_PAGE_URLS


def test_allowed_source_page_urls_includes_ctuil_enabled_pages() -> None:
    for url in CTUIL_URLS:
        assert canonical_url(url) in repository.ALLOWED_SOURCE_PAGE_URLS


def test_allowed_source_page_urls_rejects_unrelated_url() -> None:
    assert (
        canonical_url("https://example.com/not-a-curated-source-page")
        not in repository.ALLOWED_SOURCE_PAGE_URLS
    )


def test_list_enabled_source_pages_returns_ctuil_pages_for_source_13(
    monkeypatch,
) -> None:
    sql_rows = [
        {
            "id": 50 + index,
            "source_id": 13,
            "name": name,
            "url": url,
            "page_type": "listing",
            "priority": (index + 1) * 10,
            "enabled": True,
            "last_crawled_at": None,
            "source_code": "ctuil",
            "source_name": "Central Transmission Utility of India Ltd (CTUIL)",
            "source_url": "https://ctuil.in/",
            "jurisdiction": "central",
            "crawler_type": "agent",
            "allowed_domains": ["ctuil.in"],
            "hint": None,
        }
        for index, (name, url) in enumerate(
            [
                ("Latest News", CTUIL_URLS[0]),
                ("Advisories for Connectivity & GNA", CTUIL_URLS[1]),
                ("Regulations & Procedures under the GNA Regulations", CTUIL_URLS[2]),
                ("Formats under the Detailed Procedure (incl. bank guarantees)", CTUIL_URLS[3]),
                ("Connectivity to be Made Effective (RE generators)", CTUIL_URLS[4]),
                ("Draft Procedures for Stakeholder Consultation", CTUIL_URLS[5]),
            ]
        )
    ]
    # Include an enabled-but-not-allowlisted decoy to prove filter still rejects.
    sql_rows.append(
        {
            "id": 999,
            "source_id": 13,
            "name": "Not allowlisted",
            "url": "https://ctuil.in/unknown-path",
            "page_type": "listing",
            "priority": 99,
            "enabled": True,
            "last_crawled_at": None,
            "source_code": "ctuil",
            "source_name": "Central Transmission Utility of India Ltd (CTUIL)",
            "source_url": "https://ctuil.in/",
            "jurisdiction": "central",
            "crawler_type": "agent",
            "allowed_domains": ["ctuil.in"],
            "hint": None,
        }
    )

    class _Mappings:
        def __init__(self, rows: list[dict[str, Any]]):
            self._rows = rows

        def __iter__(self):
            return iter(self._rows)

    session = MagicMock()
    session.execute.return_value.mappings.return_value = _Mappings(sql_rows)

    @contextmanager
    def fake_scope():
        yield session

    monkeypatch.setattr(repository, "session_scope", fake_scope)

    pages = repository.list_enabled_source_pages(source_id=13)
    assert [page["id"] for page in pages] == [50, 51, 52, 53, 54, 55]
    assert [page["url"] for page in pages] == list(CTUIL_URLS)
    assert all(
        canonical_url(page["url"]) in repository.ALLOWED_SOURCE_PAGE_URLS for page in pages
    )
    assert 999 not in {page["id"] for page in pages}

    sql = str(session.execute.call_args.args[0])
    params = session.execute.call_args.args[1]
    assert "s.enabled = true" in sql
    assert "sp.enabled = true" in sql
    assert "s.id = :source_id" in sql
    assert params["source_id"] == 13
