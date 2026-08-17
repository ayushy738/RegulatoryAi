"""Classify TLS / certificate verification failures for crawl diagnostics.

Production crawlers must keep TLS verification enabled. This module only
interprets OpenSSL/httpx errors into structured, operator-safe fields.
"""

from __future__ import annotations

import re
import ssl
from typing import Any

# Stable reasons surfaced to Admin UI / crawl_runs.errors.
TLS_REASON_CERTIFICATE_VERIFICATION_FAILED = "certificate_verification_failed"
TLS_REASON_UNABLE_TO_GET_LOCAL_ISSUER = "unable_to_get_local_issuer"
TLS_REASON_SELF_SIGNED_IN_CHAIN = "self_signed_certificate_in_chain"
TLS_REASON_HOSTNAME_MISMATCH = "hostname_verification_failed"
TLS_REASON_EXPIRED = "expired_certificate"
TLS_REASON_NOT_YET_VALID = "certificate_not_yet_valid"

TLS_ERROR_TYPE = "tls_certificate_error"

_REASON_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        TLS_REASON_UNABLE_TO_GET_LOCAL_ISSUER,
        re.compile(r"unable to get local issuer certificate", re.I),
    ),
    (
        TLS_REASON_SELF_SIGNED_IN_CHAIN,
        re.compile(r"self[- ]signed certificate in certificate chain", re.I),
    ),
    (
        TLS_REASON_HOSTNAME_MISMATCH,
        re.compile(
            r"hostname mismatch|doesn't match|certificate is not valid for|"
            r"IP address mismatch|CERTIFICATE_VERIFY_FAILED.*hostname",
            re.I,
        ),
    ),
    (
        TLS_REASON_EXPIRED,
        re.compile(r"certificate has expired|cert has expired", re.I),
    ),
    (
        TLS_REASON_NOT_YET_VALID,
        re.compile(r"certificate is not yet valid|not yet valid", re.I),
    ),
    (
        TLS_REASON_CERTIFICATE_VERIFICATION_FAILED,
        re.compile(
            r"CERTIFICATE_VERIFY_FAILED|certificate verify failed|SSLCertVerificationError",
            re.I,
        ),
    ),
)

_OPERATOR_LABELS: dict[str, str] = {
    TLS_REASON_UNABLE_TO_GET_LOCAL_ISSUER: "unable to get local issuer certificate",
    TLS_REASON_SELF_SIGNED_IN_CHAIN: "self-signed certificate in certificate chain",
    TLS_REASON_HOSTNAME_MISMATCH: "hostname verification failed",
    TLS_REASON_EXPIRED: "expired certificate",
    TLS_REASON_NOT_YET_VALID: "certificate not yet valid",
    TLS_REASON_CERTIFICATE_VERIFICATION_FAILED: "certificate verification failed",
}


def is_tls_certificate_error(exc: BaseException) -> bool:
    """True when the exception (or its cause chain) is a TLS cert verification failure."""

    return classify_tls_exception(exc) is not None


def classify_tls_exception(exc: BaseException) -> dict[str, Any] | None:
    """Return structured TLS fields, or None when the failure is not cert-related.

    Returned keys:
      error_type   -> always ``tls_certificate_error``
      tls_reason   -> stable machine reason
      error        -> operator-facing sentence
      cause_type   -> original exception class name (e.g. ConnectError)
    """

    haystack = _exception_haystack(exc)
    if not haystack:
        return None
    if not _looks_like_tls_certificate_failure(exc, haystack):
        return None

    reason = TLS_REASON_CERTIFICATE_VERIFICATION_FAILED
    for candidate, pattern in _REASON_PATTERNS:
        if pattern.search(haystack):
            reason = candidate
            break

    label = _OPERATOR_LABELS.get(reason, "certificate verification failed")
    return {
        "error_type": TLS_ERROR_TYPE,
        "tls_reason": reason,
        "error": f"TLS certificate verification failed: {label}",
        "cause_type": type(exc).__name__,
    }


def _looks_like_tls_certificate_failure(exc: BaseException, haystack: str) -> bool:
    if isinstance(exc, ssl.SSLCertVerificationError):
        return True
    for node in _walk_exceptions(exc):
        if isinstance(node, ssl.SSLCertVerificationError):
            return True
        if isinstance(node, ssl.SSLError) and "CERTIFICATE_VERIFY_FAILED" in repr(node):
            return True
    return bool(
        re.search(
            r"CERTIFICATE_VERIFY_FAILED|SSLCertVerificationError|"
            r"certificate verify failed|self[- ]signed certificate|"
            r"unable to get local issuer certificate",
            haystack,
            re.I,
        )
    )


def _exception_haystack(exc: BaseException) -> str:
    parts: list[str] = []
    for node in _walk_exceptions(exc):
        parts.append(type(node).__name__)
        parts.append(str(node))
        parts.append(repr(node))
    return " ".join(parts)


def _walk_exceptions(exc: BaseException) -> list[BaseException]:
    seen: set[int] = set()
    ordered: list[BaseException] = []
    stack: list[BaseException | None] = [exc]
    while stack:
        current = stack.pop()
        if current is None:
            continue
        identity = id(current)
        if identity in seen:
            continue
        seen.add(identity)
        ordered.append(current)
        stack.append(current.__cause__)
        stack.append(current.__context__)
    return ordered
