from dataclasses import dataclass
from uuid import uuid4

from backend.core.config import settings


@dataclass(frozen=True)
class EmailResult:
    message_id: str
    provider: str


def send_email(to: str, subject: str, html: str, text: str) -> EmailResult:
    if settings.email_provider == "offline" or not settings.email_api_key:
        return EmailResult(message_id=f"offline-{uuid4()}", provider="offline")
    raise NotImplementedError(
        f"{settings.email_provider} email transport is configured but not implemented yet."
    )
