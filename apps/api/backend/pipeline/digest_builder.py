from datetime import date

from backend.core.models import DigestResponse
from backend.core.repository import create_digest_for_events


def build_digest(
    run_date: date | None = None,
    event_ids: list[int] | None = None,
) -> DigestResponse:
    digest_date = run_date or date.today()
    return create_digest_for_events(digest_date, event_ids or [])
