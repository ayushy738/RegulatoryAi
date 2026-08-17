"""Crawl exception serialization for operator-visible crawl_runs.errors."""

from __future__ import annotations

from typing import Any

from backend.pipeline.tls_errors import classify_tls_exception


def serialize_crawl_exception(exc: BaseException) -> dict[str, Any]:
    """Build a backward-compatible error dict for crawl_runs.errors entries.

    Always sets ``error`` to a non-empty operator-facing string. When ``str(exc)``
    is blank (common for httpx ConnectTimeout/ConnectError), falls back to the
    exception class name so admin UI does not show ``""``.

    TLS certificate verification failures are reclassified as
    ``error_type=tls_certificate_error`` with a stable ``tls_reason`` while still
    preserving the original exception message/repr for diagnostics.
    """

    error_type = type(exc).__name__
    error_message = str(exc)
    error_repr = repr(exc)
    error_args = [_json_safe_arg(arg) for arg in exc.args]
    error = error_message.strip() or error_type
    payload: dict[str, Any] = {
        "error": error,
        "error_type": error_type,
        "error_message": error_message,
        "error_repr": error_repr,
        "error_args": error_args,
    }

    tls = classify_tls_exception(exc)
    if tls is not None:
        payload["error"] = tls["error"]
        payload["error_type"] = tls["error_type"]
        payload["tls_reason"] = tls["tls_reason"]
        payload["cause_type"] = tls["cause_type"]
        # Prefer a non-empty OpenSSL/httpx cause string when the outer
        # ConnectError message is blank (common with httpx).
        if not str(payload["error_message"]).strip():
            for node in (exc.__cause__, exc.__context__):
                if node is None:
                    continue
                detail = str(node).strip()
                if detail:
                    payload["error_message"] = detail
                    break
    return payload


def _json_safe_arg(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, BaseException):
        return {
            "type": type(value).__name__,
            "message": str(value),
            "repr": repr(value),
        }
    try:
        return str(value)
    except Exception:
        return f"<unrepresentable {type(value).__name__}>"
