import logging
from dataclasses import dataclass
from uuid import uuid4

from backend.core.config import settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class EmailResult:
    message_id: str
    provider: str


def send_email(to: str, subject: str, html: str, text: str) -> EmailResult:
    if settings.email_provider == "offline" or not settings.email_api_key:
        return EmailResult(message_id=f"offline-{uuid4()}", provider="offline")
    # TODO: Implement resend/postmark/ses providers when needed
    logger.warning(
        "Email provider '%s' is configured but not yet implemented. "
        "Message to %s was not sent. Falling back to offline mode.",
        settings.email_provider,
        to,
    )
    return EmailResult(message_id=f"offline-{uuid4()}", provider="offline")
