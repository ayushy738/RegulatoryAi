"""Unit coverage for the admin console pagination/filter query builders.

These assert the SQL fragments and paging arithmetic without a live database;
integration behaviour is covered by the integration suite.
"""

from __future__ import annotations

import pytest

from backend.core import admin_queries


def test_paging_is_clamped_into_a_safe_range() -> None:
    assert admin_queries._normalize_paging(1, 20) == (1, 20, 0)
    assert admin_queries._normalize_paging(3, 20) == (3, 20, 40)
    # Page and size below 1 fall back to the first page / smallest window.
    assert admin_queries._normalize_paging(0, 0) == (1, admin_queries.DEFAULT_PAGE_SIZE, 0)
    assert admin_queries._normalize_paging(-5, -5) == (
        1,
        admin_queries.DEFAULT_PAGE_SIZE,
        0,
    )
    # An oversized page_size cannot be used to pull the whole table.
    _, size, _ = admin_queries._normalize_paging(1, 10_000)
    assert size == admin_queries.MAX_PAGE_SIZE


def test_envelope_reports_total_pages() -> None:
    envelope = admin_queries._envelope([{"id": 1}], total=41, page=2, page_size=20)

    assert envelope["items"] == [{"id": 1}]
    assert envelope["total"] == 41
    assert envelope["page"] == 2
    assert envelope["page_size"] == 20
    assert envelope["total_pages"] == 3


def test_search_term_is_lowercased_and_wrapped() -> None:
    assert admin_queries._search_term("  GeRc ") == "%gerc%"
    assert admin_queries._search_term("") is None
    assert admin_queries._search_term(None) is None


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        ("all", None),
        ("enabled", "s.enabled"),
        ("disabled", "not s.enabled"),
        ("error", "coalesce(s.consecutive_failures, 0) > 0"),
    ],
)
def test_source_status_filter_clauses(status: str, expected: str | None) -> None:
    clauses, _ = admin_queries._source_filter_sql(None, None, status, "all")

    if expected is None:
        assert clauses == []
    else:
        assert expected in clauses


@pytest.mark.parametrize(
    ("last_run", "fragment"),
    [
        ("never", "s.last_checked_at is null"),
        ("24h", "interval '24 hours'"),
        ("7d", "interval '7 days'"),
        ("30d", "interval '30 days'"),
        ("older", "< now() - interval '30 days'"),
    ],
)
def test_source_last_run_filter_clauses(last_run: str, fragment: str) -> None:
    clauses, _ = admin_queries._source_filter_sql(None, None, "all", last_run)

    assert any(fragment in clause for clause in clauses)


def test_source_search_binds_a_single_parameter() -> None:
    clauses, params = admin_queries._source_filter_sql("%gerc%", None, "all", "all")

    assert params == {"search": "%gerc%"}
    assert "lower(s.code) like :search" in clauses[0]
    assert "lower(s.name) like :search" in clauses[0]
    assert "lower(s.url) like :search" in clauses[0]


def test_run_filters_bind_status_source_and_date() -> None:
    clauses, params = admin_queries._run_filter_sql(
        "%gerc%", "GERC", "partial", "today"
    )

    assert params["search"] == "%gerc%"
    assert params["source_code"] == "gerc"
    assert params["status"] == "partial"
    assert any("date_trunc('day', now())" in clause for clause in clauses)


def test_run_page_row_classifies_status_from_available_evidence() -> None:
    failed = admin_queries._run_page_row(
        {
            "page_key": "7",
            "page_id": 7,
            "page_name": "Draft Regulations",
            "documents_discovered": 0,
            "errors": [{"error": "TLS handshake failed"}],
        }
    )
    assert failed["status"] == "failed"

    succeeded = admin_queries._run_page_row(
        {
            "page_key": "8",
            "page_id": 8,
            "page_name": "Orders",
            "documents_discovered": 4,
            "errors": [],
        }
    )
    assert succeeded["status"] == "success"

    empty = admin_queries._run_page_row(
        {
            "page_key": "9",
            "page_id": 9,
            "page_name": "Tenders",
            "documents_discovered": 0,
            "errors": [],
        }
    )
    assert empty["status"] == "no_documents"


def test_run_page_row_recovers_page_id_from_the_audit_key() -> None:
    row = admin_queries._run_page_row(
        {
            "page_key": "12",
            "page_id": None,
            "page_name": None,
            "documents_discovered": 0,
            "errors": [],
        }
    )

    assert row["page_id"] == 12
    assert row["page_name"] == "Unresolved page"


def test_run_page_row_tolerates_a_non_numeric_audit_key() -> None:
    row = admin_queries._run_page_row(
        {
            "page_key": "not-an-id",
            "page_id": None,
            "page_name": None,
            "documents_discovered": 0,
            "errors": "not-a-list",
        }
    )

    assert row["page_id"] is None
    assert row["errors"] == []
