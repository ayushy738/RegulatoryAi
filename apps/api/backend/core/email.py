import logging
import re
from dataclasses import dataclass
from email.utils import parseaddr
from uuid import uuid4

import httpx

from backend.core.config import settings

logger = logging.getLogger(__name__)

BREVO_API_URL = "https://api.brevo.com/v3/smtp/email"


@dataclass(frozen=True)
class EmailResult:
    message_id: str
    provider: str


class EmailDeliveryError(RuntimeError):
    """Raised when a configured email provider fails to accept a message."""


def _parse_from_address(value: str) -> tuple[str | None, str]:
    name, email = parseaddr(value)
    if not email or "@" not in email:
        raise EmailDeliveryError(f"Invalid EMAIL_FROM address: {value!r}")
    return (name or None), email


def send_email(to: str, subject: str, html: str, text: str) -> EmailResult:
    provider = (settings.email_provider or "offline").lower()
    if provider == "offline" or not settings.email_api_key:
        return EmailResult(message_id=f"offline-{uuid4()}", provider="offline")

    if provider == "brevo":
        return _send_brevo(to=to, subject=subject, html=html, text=text)

    logger.warning(
        "Email provider '%s' is configured but not implemented. "
        "Message was not sent. Falling back to offline mode.",
        provider,
    )
    return EmailResult(message_id=f"offline-{uuid4()}", provider="offline")


def _send_brevo(*, to: str, subject: str, html: str, text: str) -> EmailResult:
    sender_name, sender_email = _parse_from_address(settings.email_from)
    payload: dict = {
        "sender": {"email": sender_email},
        "to": [{"email": to.strip()}],
        "subject": subject,
        "htmlContent": html,
        "textContent": text,
    }
    if sender_name:
        payload["sender"]["name"] = sender_name

    headers = {
        "accept": "application/json",
        "content-type": "application/json",
        "api-key": settings.email_api_key or "",
    }
    try:
        response = httpx.post(BREVO_API_URL, json=payload, headers=headers, timeout=30.0)
    except httpx.HTTPError as exc:
        raise EmailDeliveryError(f"Brevo request failed: {exc}") from exc

    if response.status_code >= 400:
        detail = _safe_error_detail(response)
        raise EmailDeliveryError(f"Brevo rejected message ({response.status_code}): {detail}")

    message_id = None
    try:
        body = response.json()
        message_id = body.get("messageId") or body.get("message_id")
    except Exception:  # noqa: BLE001
        message_id = None
    if not message_id:
        message_id = f"brevo-{uuid4()}"
    return EmailResult(message_id=str(message_id), provider="brevo")


def _safe_error_detail(response: httpx.Response) -> str:
    raw = (response.text or "").strip()
    # Avoid logging potential PII from provider payloads; keep short/redacted.
    cleaned = re.sub(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", "[redacted-email]", raw, flags=re.I)
    return cleaned[:300]
