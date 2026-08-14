"""Phase 2: crawl-run telemetry must be run-scoped, never global DB totals."""

from __future__ import annotations

from backend.core.repository import (
    _CRAWL_RUN_SELECT,
    assemble_crawl_run_telemetry,
    page_ids_from_crawl_errors,
)


def test_page_ids_from_crawl_errors_extracts_ints() -> None:
    assert page_ids_from_crawl_errors(
        [
            {"source_page_id": 3, "error": "timeout"},
            {"source": "pipeline", "error": "boom"},
            {"source_page_id": "7"},
            {"source_page_id": "bad"},
        ]
    ) == {3, 7}


def test_assemble_keeps_run_a_and_run_b_metrics_isolated() -> None:
    run_a = assemble_crawl_run_telemetry(
        {
            "id": 1,
            "started_at": "2026-01-01T00:00:00Z",
            "finished_at": "2026-01-01T00:01:00Z",
            "status": "success",
            "sources_attempted": 1,
            "sources_succeeded": 1,
            "docs_found": 2,
            "new_events": 1,
            "errors": [],
            "audit_pages": 1,
            "audit_with_content": 2,
            "derived_pages_attempted": 1,
        }
    )
    run_b = assemble_crawl_run_telemetry(
        {
            "id": 2,
            "started_at": "2026-01-02T00:00:00Z",
            "finished_at": "2026-01-02T00:01:00Z",
            "status": "success",
            "sources_attempted": 2,
            "sources_succeeded": 2,
            "docs_found": 0,
            "new_events": 0,
            "errors": [],
            "audit_pages": 2,
            "audit_with_content": 0,
            "derived_pages_attempted": 2,
        }
    )

    assert run_a["documents_discovered"] == 2
    assert run_a["events_created"] == 1
    assert run_a["pages_attempted"] == 1
    assert run_b["documents_discovered"] == 0
    assert run_b["events_created"] == 0
    assert run_b["pages_attempted"] == 2
    # Global totals must not appear on either run.
    assert run_a["versions_created"] is None
    assert run_b["versions_created"] is None
    assert run_a["rag_indexed"] is None
    assert run_b["rag_indexed"] is None
    assert run_a["families_touched"] is None
    assert run_a["graph_extractions"] is None
    assert run_a["rag_jobs_enqueued"] is None


def test_zero_document_run_stays_zero_not_global() -> None:
    payload = assemble_crawl_run_telemetry(
        {
            "id": 9,
            "status": "success",
            "sources_attempted": 1,
            "sources_succeeded": 1,
            "docs_found": 0,
            "new_events": 0,
            "errors": [],
            "audit_pages": 1,
            "audit_with_content": 0,
            "derived_pages_attempted": 1,
        }
    )
    assert payload["documents_discovered"] == 0
    assert payload["documents_with_content"] == 0
    assert payload["events_created"] == 0
    assert payload["rag_indexed"] is None


def test_unavailable_metrics_are_null_not_zero() -> None:
    payload = assemble_crawl_run_telemetry(
        {
            "id": 3,
            "status": "partial",
            "sources_attempted": 1,
            "sources_succeeded": 0,
            "docs_found": 0,
            "new_events": 0,
            "errors": [{"source": "cerc", "error": "tls"}],
            "audit_pages": 0,
            "audit_with_content": 0,
            "derived_pages_attempted": 0,
        }
    )
    # sources attempted but no recoverable page ids => unavailable pages
    assert payload["pages_attempted"] is None
    assert payload["pages_succeeded"] is None
    assert payload["versions_created"] is None
    assert payload["families_touched"] is None
    assert payload["graph_extractions"] is None
    assert payload["rag_jobs_enqueued"] is None
    assert payload["rag_indexed"] is None


def test_failed_page_errors_count_toward_pages_attempted() -> None:
    payload = assemble_crawl_run_telemetry(
        {
            "id": 4,
            "status": "partial",
            "sources_attempted": 1,
            "sources_succeeded": 1,
            "docs_found": 1,
            "new_events": 0,
            "errors": [{"source_page_id": 12, "error": "timeout"}],
            "audit_pages": 1,
            "audit_page_ids": [10],
            "audit_with_content": 1,
        }
    )
    assert payload["pages_attempted"] == 2
    assert payload["pages_succeeded"] == 1


def test_historical_run_shape_remains_readable() -> None:
    payload = assemble_crawl_run_telemetry(
        {
            "id": 100,
            "started_at": "2025-06-01T00:00:00Z",
            "finished_at": "2025-06-01T00:10:00Z",
            "status": "success",
            "sources_attempted": 3,
            "sources_succeeded": 3,
            "docs_found": 45,
            "new_events": 20,
            "errors": [],
            "audit_pages": 7,
            "audit_with_content": 39,
            "derived_pages_attempted": 7,
        }
    )
    assert payload["id"] == 100
    assert payload["status"] == "success"
    assert payload["documents_discovered"] == 45
    assert payload["events_created"] == 20
    assert payload["pages_attempted"] == 7
    assert "errors" in payload


def test_crawl_run_select_scopes_discovery_audit_by_run_id() -> None:
    sql = " ".join(_CRAWL_RUN_SELECT.split())
    assert "from crawl_runs cr" in sql
    assert "where da.run_id = cr.id" in sql
    assert "from discovery_audit da" in sql
    # Guard against accidental unscoped discovery_audit aggregates.
    assert "count(*) from discovery_audit)" not in sql.replace(" ", "")
