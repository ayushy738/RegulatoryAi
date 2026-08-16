"""HTTP reachability diagnostics for crawl source hosts (operator-only).

Does not alter crawler TLS verification or crawl behavior. Safe comparison of
DNS / TCP / HTTP / HTTPS (with optional verify=False diagnostic-only probe).

Examples::

  python -m backend.tools.http_reachability_check --host grid-india.in
  python -m backend.tools.http_reachability_check \\
    --url https://grid-india.in/en/documents/iegc-procedures
"""

from __future__ import annotations

import argparse
import json
import socket
import time
from typing import Any
from urllib.parse import urlparse

import httpx

DEFAULT_HOST = "grid-india.in"
DEFAULT_PATH = "/en/documents/iegc-procedures"


def check_reachability(
    *,
    host: str = DEFAULT_HOST,
    path: str = DEFAULT_PATH,
    timeout: float = 20.0,
) -> dict[str, Any]:
    host = host.strip().lower().removeprefix("https://").removeprefix("http://").split("/")[0]
    path = path if path.startswith("/") else f"/{path}"
    https_url = f"https://{host}{path}"
    http_url = f"http://{host}{path}"

    return {
        "host": host,
        "path": path,
        "environment_hint": "local_or_caller",
        "dns": _dns_lookup(host),
        "tcp_tls_443": _tcp_connect(host, 443, timeout=timeout),
        "http_request": _http_get(http_url, verify=True, timeout=timeout),
        "https_request_verify_true": _http_get(https_url, verify=True, timeout=timeout),
        "https_request_verify_false_diagnostic_only": _http_get(
            https_url, verify=False, timeout=timeout
        ),
        "notes": [
            "https_request_verify_false_diagnostic_only is comparison-only; "
            "production crawler TLS verification is unchanged.",
        ],
    }


def _dns_lookup(host: str) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        infos = socket.getaddrinfo(host, None)
        addresses = sorted({item[4][0] for item in infos if item and item[4]})
        return {
            "ok": True,
            "addresses": addresses,
            "elapsed_ms": int((time.perf_counter() - started) * 1000),
            "error_type": None,
            "error_repr": None,
        }
    except OSError as exc:
        return {
            "ok": False,
            "addresses": [],
            "elapsed_ms": int((time.perf_counter() - started) * 1000),
            "error_type": type(exc).__name__,
            "error_repr": repr(exc),
        }


def _tcp_connect(host: str, port: int, *, timeout: float) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return {
                "ok": True,
                "port": port,
                "elapsed_ms": int((time.perf_counter() - started) * 1000),
                "error_type": None,
                "error_repr": None,
            }
    except OSError as exc:
        return {
            "ok": False,
            "port": port,
            "elapsed_ms": int((time.perf_counter() - started) * 1000),
            "error_type": type(exc).__name__,
            "error_repr": repr(exc),
        }


def _http_get(url: str, *, verify: bool, timeout: float) -> dict[str, Any]:
    started = time.perf_counter()
    parsed = urlparse(url)
    try:
        with httpx.Client(
            follow_redirects=True,
            timeout=timeout,
            verify=verify,
        ) as client:
            response = client.get(url)
        return {
            "ok": True,
            "url": url,
            "hostname": parsed.hostname,
            "http_method": "GET",
            "verify": verify,
            "status_code": response.status_code,
            "final_url": str(response.url),
            "elapsed_ms": int((time.perf_counter() - started) * 1000),
            "error_type": None,
            "error_repr": None,
            "error_message": None,
        }
    except Exception as exc:
        return {
            "ok": False,
            "url": url,
            "hostname": parsed.hostname,
            "http_method": "GET",
            "verify": verify,
            "status_code": None,
            "final_url": None,
            "elapsed_ms": int((time.perf_counter() - started) * 1000),
            "error_type": type(exc).__name__,
            "error_repr": repr(exc),
            "error_message": str(exc),
        }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--path", default=DEFAULT_PATH)
    parser.add_argument(
        "--url",
        default=None,
        help="Optional full URL; overrides --host/--path for path derivation.",
    )
    parser.add_argument("--timeout", type=float, default=20.0)
    args = parser.parse_args()
    host = args.host
    path = args.path
    if args.url:
        parsed = urlparse(args.url)
        if parsed.hostname:
            host = parsed.hostname
        if parsed.path:
            path = parsed.path
    result = check_reachability(host=host, path=path, timeout=args.timeout)
    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
