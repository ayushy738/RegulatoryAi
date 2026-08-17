"""Read-only TLS certificate-chain diagnostics for crawl source hosts.

Compares verification against the same CA store httpx/OpenSSL uses in the crawl
worker. Diagnostic-only ``verify=False`` is labeled and never used by production
crawl paths.

Examples::

  python -m backend.tools.tls_chain_diagnose --host www.derc.gov.in
  python -m backend.tools.tls_chain_diagnose --host gercin.org --path /orders/tariff_orders
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import ssl
import sys
import time
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlparse

import certifi
import httpx

from backend.pipeline.tls_errors import classify_tls_exception


def diagnose_tls(
    *,
    host: str,
    path: str = "/",
    timeout: float = 25.0,
) -> dict[str, Any]:
    host = host.strip().lower().removeprefix("https://").removeprefix("http://").split("/")[0]
    path = path if path.startswith("/") else f"/{path}"
    https_url = f"https://{host}{path}"

    return {
        "host": host,
        "path": path,
        "https_url": https_url,
        "environment": _environment_snapshot(),
        "dns": _dns_lookup(host),
        "tcp_443": _tcp_connect(host, 443, timeout=timeout),
        "tls_handshake_verify_true": _tls_handshake(host, verify=True, timeout=timeout),
        "tls_handshake_verify_false_diagnostic_only": _tls_handshake(
            host, verify=False, timeout=timeout
        ),
        "https_get_verify_true": _http_get(https_url, verify=True, timeout=timeout),
        "https_get_verify_false_diagnostic_only": _http_get(
            https_url, verify=False, timeout=timeout
        ),
        "notes": [
            "verify_false_* fields are comparison-only diagnostics.",
            "Production crawler TLS verification remains enabled (verify=True).",
            "Do not treat verify=False success as authorization to disable TLS.",
        ],
    }


def _environment_snapshot() -> dict[str, Any]:
    return {
        "python_version": sys.version.split()[0],
        "openssl_version": ssl.OPENSSL_VERSION,
        "httpx_version": getattr(httpx, "__version__", "unknown"),
        "certifi_version": getattr(certifi, "__version__", "unknown"),
        "certifi_ca_bundle": certifi.where(),
        "ssl_default_verify_paths": _safe_verify_paths(),
        "proxy_env_redacted": _redacted_proxy_env(),
        "crawl_worker_env": os.environ.get("CRAWL_WORKER"),
    }


def _safe_verify_paths() -> dict[str, Any]:
    try:
        paths = ssl.get_default_verify_paths()
        return {
            "cafile": paths.cafile,
            "capath": paths.capath,
            "openssl_cafile_env": paths.openssl_cafile_env,
            "openssl_capath_env": paths.openssl_capath_env,
        }
    except Exception as exc:
        return {"error_type": type(exc).__name__, "error_message": str(exc)}


def _redacted_proxy_env() -> dict[str, str | None]:
    keys = (
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "ALL_PROXY",
        "NO_PROXY",
        "http_proxy",
        "https_proxy",
        "all_proxy",
        "no_proxy",
        "SSL_CERT_FILE",
        "REQUESTS_CA_BUNDLE",
        "CURL_CA_BUNDLE",
    )
    out: dict[str, str | None] = {}
    for key in keys:
        value = os.environ.get(key)
        out[key] = _redact_url_credentials(value) if value else None
    return out


def _redact_url_credentials(value: str) -> str:
    if "://" not in value:
        return value
    try:
        parsed = urlparse(value)
        if parsed.password or (parsed.username and "@" in value.split("://", 1)[1]):
            netloc = parsed.hostname or ""
            if parsed.port:
                netloc = f"{netloc}:{parsed.port}"
            return parsed._replace(netloc=netloc).geturl()
    except Exception:
        return "<redacted>"
    return value


def _dns_lookup(host: str) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        infos = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
        addresses = sorted({item[4][0] for item in infos if item and item[4]})
        families = sorted(
            {
                "IPv6" if ":" in item[4][0] else "IPv4"
                for item in infos
                if item and item[4]
            }
        )
        return {
            "ok": True,
            "addresses": addresses,
            "address_families": families,
            "elapsed_ms": int((time.perf_counter() - started) * 1000),
        }
    except OSError as exc:
        return {
            "ok": False,
            "addresses": [],
            "address_families": [],
            "elapsed_ms": int((time.perf_counter() - started) * 1000),
            "error_type": type(exc).__name__,
            "error_message": str(exc),
        }


def _tcp_connect(host: str, port: int, *, timeout: float) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        with socket.create_connection((host, port), timeout=timeout) as sock:
            peer = sock.getpeername()
            return {
                "ok": True,
                "port": port,
                "peer": f"{peer[0]}:{peer[1]}" if peer else None,
                "elapsed_ms": int((time.perf_counter() - started) * 1000),
            }
    except OSError as exc:
        return {
            "ok": False,
            "port": port,
            "peer": None,
            "elapsed_ms": int((time.perf_counter() - started) * 1000),
            "error_type": type(exc).__name__,
            "error_message": str(exc),
        }


def _tls_handshake(host: str, *, verify: bool, timeout: float) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        raw = socket.create_connection((host, 443), timeout=timeout)
        raw.settimeout(timeout)
        if verify:
            context = ssl.create_default_context(cafile=certifi.where())
        else:
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE
        with context.wrap_socket(raw, server_hostname=host) as tls:
            leaf = tls.getpeercert()
            chain_summary = _peer_chain_summary(tls)
            return {
                "ok": True,
                "verify": verify,
                "tls_version": tls.version(),
                "cipher": tls.cipher(),
                "leaf": _summarize_decoded_cert(leaf),
                "chain": chain_summary,
                "elapsed_ms": int((time.perf_counter() - started) * 1000),
                "error_type": None,
                "error_message": None,
                "tls_classification": None,
            }
    except Exception as exc:
        tls = classify_tls_exception(exc)
        return {
            "ok": False,
            "verify": verify,
            "tls_version": None,
            "cipher": None,
            "leaf": None,
            "chain": None,
            "elapsed_ms": int((time.perf_counter() - started) * 1000),
            "error_type": type(exc).__name__,
            "error_message": str(exc),
            "error_repr": repr(exc),
            "tls_classification": tls,
        }


def _peer_chain_summary(tls: ssl.SSLSocket) -> dict[str, Any]:
    """Best-effort peer chain dump (Python 3.13+ unverified_chain when present)."""

    certs: list[dict[str, Any]] = []
    getter = getattr(tls, "get_unverified_chain", None)
    if callable(getter):
        try:
            for index, cert in enumerate(getter() or []):
                certs.append(_summarize_crypto_cert(cert, index=index))
        except Exception as exc:
            return {
                "available": False,
                "error_type": type(exc).__name__,
                "error_message": str(exc),
                "certificates": [],
            }
        return {
            "available": True,
            "length": len(certs),
            "certificates": certs,
        }
    return {
        "available": False,
        "length": None,
        "certificates": [],
        "note": "get_unverified_chain unavailable on this Python/OpenSSL build",
    }


def _summarize_crypto_cert(cert: Any, *, index: int) -> dict[str, Any]:
    try:
        # ssl.Certificate (3.13+) exposes public_bytes / get_info
        info = cert.get_info() if hasattr(cert, "get_info") else None
        if isinstance(info, dict):
            return {
                "index": index,
                "subject": info.get("subject"),
                "issuer": info.get("issuer"),
                "notBefore": info.get("notBefore"),
                "notAfter": info.get("notAfter"),
                "serialNumber": info.get("serialNumber"),
                "subjectAltName": info.get("subjectAltName"),
            }
    except Exception:
        pass
    return {"index": index, "repr": repr(cert)[:500]}


def _summarize_decoded_cert(cert: dict[str, Any] | None) -> dict[str, Any] | None:
    if not cert:
        return None
    subject = _name_dict(cert.get("subject"))
    issuer = _name_dict(cert.get("issuer"))
    sans = [value for typ, value in cert.get("subjectAltName", ()) if typ == "DNS"]
    return {
        "subject": subject,
        "issuer": issuer,
        "notBefore": cert.get("notBefore"),
        "notAfter": cert.get("notAfter"),
        "serialNumber": cert.get("serialNumber"),
        "subjectAltNames": sans,
    }


def _name_dict(name: Any) -> dict[str, str]:
    result: dict[str, str] = {}
    if not name:
        return result
    for rdn in name:
        for key, value in rdn:
            result[str(key)] = str(value)
    return result


def _http_get(url: str, *, verify: bool, timeout: float) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        with httpx.Client(
            follow_redirects=True,
            timeout=timeout,
            verify=certifi.where() if verify else False,
        ) as client:
            response = client.get(url)
        return {
            "ok": True,
            "verify": verify,
            "status_code": response.status_code,
            "final_url": str(response.url),
            "elapsed_ms": int((time.perf_counter() - started) * 1000),
            "error_type": None,
            "error_message": None,
            "tls_classification": None,
        }
    except Exception as exc:
        return {
            "ok": False,
            "verify": verify,
            "status_code": None,
            "final_url": None,
            "elapsed_ms": int((time.perf_counter() - started) * 1000),
            "error_type": type(exc).__name__,
            "error_message": str(exc),
            "error_repr": repr(exc),
            "tls_classification": classify_tls_exception(exc),
        }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", required=True)
    parser.add_argument("--path", default="/")
    parser.add_argument("--timeout", type=float, default=25.0)
    args = parser.parse_args()
    result = diagnose_tls(host=args.host, path=args.path, timeout=args.timeout)
    result["generated_at"] = datetime.now(UTC).isoformat()
    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
