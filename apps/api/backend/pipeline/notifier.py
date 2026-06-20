from backend.core.email import EmailResult, send_email
from backend.core.models import EventSummary


def enqueue_notifications(new_event_ids: list[int]) -> int:
    return len(new_event_ids)


def send_pending_notifications(events: list[EventSummary] | None = None) -> EmailResult:
    count = len(events or [])
    return send_email(
        to="demo@regulatory.ai",
        subject=f"Regulatory AI digest: {count} updates",
        html=f"<p>{count} regulatory updates are ready.</p>",
        text=f"{count} regulatory updates are ready.",
    )
