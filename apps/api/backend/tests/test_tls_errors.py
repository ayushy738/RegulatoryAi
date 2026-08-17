"""Tests for TLS certificate error classification (mocked exceptions only)."""

from __future__ import annotations

import ssl

import httpx
import pytest

from backend.pipeline.crawl_exception import serialize_crawl_exception
from backend.pipeline.tls_errors import (
    TLS_ERROR_TYPE,
    TLS_REASON_CERTIFICATE_VERIFICATION_FAILED,
    TLS_REASON_SELF_SIGNED_IN_CHAIN,
    TLS_REASON_UNABLE_TO_GET_LOCAL_ISSUER,
    classify_tls_exception,
    is_tls_certificate_error,
)


def test_classify_unable_to_get_local_issuer() -> None:
    exc = ssl.SSLCertVerificationError(
        "[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed: "
        "unable to get local issuer certificate (_ssl.c:1000)"
    )
    result = classify_tls_exception(exc)
    assert result is not None
    assert result["error_type"] == TLS_ERROR_TYPE
    assert result["tls_reason"] == TLS_REASON_UNABLE_TO_GET_LOCAL_ISSUER
    assert "unable to get local issuer certificate" in result["error"]
    assert result["cause_type"] == "SSLCertVerificationError"


def test_classify_self_signed_in_chain() -> None:
    exc = ssl.SSLCertVerificationError(
        "[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed: "
        "self-signed certificate in certificate chain (_ssl.c:1000)"
    )
    result = classify_tls_exception(exc)
    assert result is not None
    assert result["tls_reason"] == TLS_REASON_SELF_SIGNED_IN_CHAIN
    assert "self-signed certificate in certificate chain" in result["error"]


def test_classify_wrapped_httpx_connect_error() -> None:
    cause = ssl.SSLCertVerificationError(
        "certificate verify failed: unable to get local issuer certificate"
    )
    exc = httpx.ConnectError("ConnectError")
    exc.__cause__ = cause
    result = classify_tls_exception(exc)
    assert result is not None
    assert result["error_type"] == TLS_ERROR_TYPE
    assert result["tls_reason"] == TLS_REASON_UNABLE_TO_GET_LOCAL_ISSUER
    assert result["cause_type"] == "ConnectError"
    assert is_tls_certificate_error(exc)


def test_classify_non_tls_connect_error_returns_none() -> None:
    exc = httpx.ConnectError("[Errno 111] Connection refused")
    assert classify_tls_exception(exc) is None
    assert not is_tls_certificate_error(exc)


def test_serialize_promotes_tls_fields_and_preserves_original() -> None:
    cause = ssl.SSLCertVerificationError(
        "certificate verify failed: self-signed certificate in certificate chain"
    )
    exc = httpx.ConnectError("")
    exc.__cause__ = cause
    payload = serialize_crawl_exception(exc)
    assert payload["error_type"] == TLS_ERROR_TYPE
    assert payload["tls_reason"] == TLS_REASON_SELF_SIGNED_IN_CHAIN
    assert payload["cause_type"] == "ConnectError"
    assert payload["error"].startswith("TLS certificate verification failed:")
    # Blank ConnectError message is filled from the SSL cause for diagnostics.
    assert "self-signed certificate in certificate chain" in payload["error_message"]
    assert "ConnectError" in payload["error_repr"]


def test_serialize_generic_ssl_verify_failed_reason() -> None:
    exc = ssl.SSLCertVerificationError("CERTIFICATE_VERIFY_FAILED")
    payload = serialize_crawl_exception(exc)
    assert payload["tls_reason"] == TLS_REASON_CERTIFICATE_VERIFICATION_FAILED


@pytest.mark.parametrize(
    ("message", "reason"),
    [
        ("certificate has expired", "expired_certificate"),
        ("certificate is not yet valid", "certificate_not_yet_valid"),
        ("hostname mismatch", "hostname_verification_failed"),
    ],
)
def test_classify_specific_reasons(message: str, reason: str) -> None:
    exc = ssl.SSLCertVerificationError(message)
    result = classify_tls_exception(exc)
    assert result is not None
    assert result["tls_reason"] == reason
