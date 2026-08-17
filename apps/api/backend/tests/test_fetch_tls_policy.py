"""Regression: production HTTP fetch never disables TLS after cert failures."""

from __future__ import annotations

import asyncio
import inspect
import ssl
from pathlib import Path
from unittest.mock import patch

import httpx
import pytest

from backend.pipeline import agent_scraper
from backend.pipeline.crawl_exception import serialize_crawl_exception
from backend.pipeline.tls_errors import (
    TLS_ERROR_TYPE,
    TLS_REASON_SELF_SIGNED_IN_CHAIN,
    TLS_REASON_UNABLE_TO_GET_LOCAL_ISSUER,
)


PIPELINE_ROOT = Path(__file__).resolve().parents[1] / "pipeline"
TOOLS_ROOT = Path(__file__).resolve().parents[1] / "tools"


def _tls_connect_error(message: str) -> httpx.ConnectError:
    cause = ssl.SSLCertVerificationError(message)
    exc = httpx.ConnectError("")
    exc.__cause__ = cause
    return exc


def test_fetch_response_never_retries_with_verify_false_on_tls_failure() -> None:
    """TLS cert failure must fail closed across all retries (no verify=False fallback)."""

    verify_values: list[object] = []
    failure = _tls_connect_error(
        "certificate verify failed: self-signed certificate in certificate chain"
    )

    class FakeClient:
        def __init__(self, *args: object, **kwargs: object) -> None:
            verify_values.append(kwargs.get("verify"))

        async def __aenter__(self) -> FakeClient:
            return self

        async def __aexit__(self, *args: object) -> bool:
            return False

        async def get(self, url: str) -> httpx.Response:
            raise failure

    with patch("backend.pipeline.agent_scraper.httpx.AsyncClient", FakeClient):
        with pytest.raises(httpx.ConnectError) as raised:
            asyncio.run(
                agent_scraper._fetch_response(
                    "https://www.derc.gov.in/notices/press-release"
                )
            )

    assert verify_values == [True, True, True]
    assert False not in verify_values
    payload = serialize_crawl_exception(raised.value)
    assert payload["error_type"] == TLS_ERROR_TYPE
    assert payload["tls_reason"] == TLS_REASON_SELF_SIGNED_IN_CHAIN
    assert payload["error"] == (
        "TLS certificate verification failed: "
        "self-signed certificate in certificate chain"
    )


def test_fetch_response_gerc_style_unable_to_get_local_issuer() -> None:
    verify_values: list[object] = []
    failure = _tls_connect_error(
        "certificate verify failed: unable to get local issuer certificate"
    )

    class FakeClient:
        def __init__(self, *args: object, **kwargs: object) -> None:
            verify_values.append(kwargs.get("verify"))

        async def __aenter__(self) -> FakeClient:
            return self

        async def __aexit__(self, *args: object) -> bool:
            return False

        async def get(self, url: str) -> httpx.Response:
            raise failure

    with patch("backend.pipeline.agent_scraper.httpx.AsyncClient", FakeClient):
        with pytest.raises(httpx.ConnectError) as raised:
            asyncio.run(
                agent_scraper._fetch_response(
                    "https://gercin.org/orders/tariff_orders"
                )
            )

    assert verify_values == [True, True, True]
    payload = serialize_crawl_exception(raised.value)
    assert payload["tls_reason"] == TLS_REASON_UNABLE_TO_GET_LOCAL_ISSUER
    assert "unable to get local issuer certificate" in payload["error"]


def test_derc_and_gerc_use_generic_listing_parser_not_legacy_bypass() -> None:
    """New regulatory sources must not route through CERC/MoP verify=False parsers."""

    for source in (
        {
            "code": "derc",
            "page_type": "listing",
            "url": "https://www.derc.gov.in/notices/press-release",
        },
        {
            "code": "gerc",
            "page_type": "listing",
            "url": "https://gercin.org/orders/tariff_orders",
        },
        {
            "code": "gerc",
            "page_type": "listing",
            "url": "https://gercin.org/regulations/draft_regulations",
        },
    ):
        assert agent_scraper._parser_for_source_page(source) is None

    listing_source = inspect.getsource(agent_scraper._scrape_listing_page)
    assert "verify=False" not in listing_source
    assert "await _fetch_response(source_url)" in listing_source


def test_crawl_pipeline_does_not_import_diagnostic_tls_tools() -> None:
    """Diagnostic verify=False probes must stay outside production crawl modules."""

    for name in (
        "agent_scraper.py",
        "run_once.py",
        "primary_document.py",
        "crawl_exception.py",
        "tls_errors.py",
    ):
        text = (PIPELINE_ROOT / name).read_text(encoding="utf-8")
        assert "tls_chain_diagnose" not in text
        assert "http_reachability_check" not in text


def test_diagnostic_tls_tool_labels_verify_false_as_comparison_only() -> None:
    text = (TOOLS_ROOT / "tls_chain_diagnose.py").read_text(encoding="utf-8")
    assert "diagnostic" in text.lower()
    assert "verify_false" in text.lower() or "verify=False" in text
    assert "Production crawler TLS verification remains enabled" in text
    # Diagnostic module must not expose a production crawl fetch helper.
    assert "def _fetch_response" not in text
