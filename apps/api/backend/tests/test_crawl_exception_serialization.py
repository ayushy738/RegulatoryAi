"""Regression tests for crawl exception serialization (empty httpx messages)."""

from __future__ import annotations

import json

import httpx

from backend.core.repository import page_ids_from_crawl_errors
from backend.pipeline.crawl_exception import serialize_crawl_exception


def test_serialize_normal_exception_keeps_message() -> None:
    payload = serialize_crawl_exception(RuntimeError("connection timed out"))
    assert payload["error"] == "connection timed out"
    assert payload["error_type"] == "RuntimeError"
    assert payload["error_message"] == "connection timed out"
    assert "RuntimeError" in payload["error_repr"]
    assert payload["error_args"] == ["connection timed out"]


def test_serialize_empty_httpx_connect_timeout_uses_type_name() -> None:
    exc = httpx.ConnectTimeout("")
    assert str(exc) == ""
    payload = serialize_crawl_exception(exc)
    assert payload["error"] == "ConnectTimeout"
    assert payload["error_type"] == "ConnectTimeout"
    assert payload["error_message"] == ""
    assert payload["error_repr"] == "ConnectTimeout('')"
    assert payload["error_args"] == [""]


def test_serialize_empty_connect_error_retains_type() -> None:
    payload = serialize_crawl_exception(httpx.ConnectError(""))
    assert payload["error"] == "ConnectError"
    assert payload["error_type"] == "ConnectError"
    assert payload["error"] != ""


def test_crawl_error_consumers_remain_compatible() -> None:
    """Existing telemetry only needs source_page_id; extra fields are additive."""

    errors = [
        {
            "source": "grid_india",
            "source_page_id": 26,
            "source_page": "IEGC & Operating Procedures",
            **serialize_crawl_exception(httpx.ConnectTimeout("")),
        },
        {"source": "pipeline", "error": "boom"},
    ]
    assert page_ids_from_crawl_errors(errors) == {26}
    # Admin UI JSON.stringifies the whole object; must be JSON-serializable.
    encoded = json.dumps(errors)
    assert "ConnectTimeout" in encoded
    assert json.loads(encoded)[0]["error"] == "ConnectTimeout"


def test_page_failure_error_dict_shape_matches_run_once_contract() -> None:
    """Mirror the fields run_once appends for a blank httpx failure."""

    exc = httpx.ConnectTimeout("")
    error_fields = serialize_crawl_exception(exc)
    entry = {
        "source": "grid_india",
        "source_page_id": 26,
        "source_page": "IEGC",
        **error_fields,
    }
    assert entry["error"] == "ConnectTimeout"
    assert entry["error_type"] == "ConnectTimeout"
    assert isinstance(entry["error_args"], list)
