"""Crawl exception serialization for operator-visible crawl_runs.errors."""

from __future__ import annotations

from typing import Any


def serialize_crawl_exception(exc: BaseException) -> dict[str, Any]:
    """Build a backward-compatible error dict for crawl_runs.errors entries.

    Always sets ``error`` to a non-empty operator-facing string. When ``str(exc)``
    is blank (common for httpx ConnectTimeout/ConnectError), falls back to the
    exception class name so admin UI does not show ``""``.
    """

    error_type = type(exc).__name__
    error_message = str(exc)
    error_repr = repr(exc)
    error_args = [_json_safe_arg(arg) for arg in exc.args]
    error = error_message.strip() or error_type
    return {
        "error": error,
        "error_type": error_type,
        "error_message": error_message,
        "error_repr": error_repr,
        "error_args": error_args,
    }


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
