from datetime import date

from fastapi import APIRouter, HTTPException, Query

from backend.api.deps import UserDep
from backend.core.models import EventSummary
from backend.core.repository import get_event as find_event
from backend.core.repository import list_events as find_events
from backend.core.repository import mark_event_state

router = APIRouter(prefix="/events", tags=["events"])


@router.get("", response_model=list[EventSummary])
async def list_events(
    user: UserDep,
    q: str | None = None,
    jurisdiction: str | None = None,
    source: str | None = None,
    topic: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    bookmarked: bool | None = None,
    page: int = Query(default=1, ge=1),
) -> list[EventSummary]:
    return find_events(
        user_id=user.id,
        query=q,
        jurisdiction=jurisdiction,
        source=source,
        topic=topic,
        date_from=date_from,
        date_to=date_to,
        bookmarked=bookmarked,
        page=page,
    )


@router.get("/{event_id}", response_model=EventSummary)
async def get_event(event_id: int, user: UserDep) -> EventSummary:
    event = find_event(event_id, user.id)
    if event:
        return event
    raise HTTPException(status_code=404, detail="Event not found")


@router.post("/{event_id}/read")
async def mark_read(event_id: int, user: UserDep) -> dict[str, bool | int]:
    return mark_event_state(user.id, event_id, is_read=True)


@router.post("/{event_id}/bookmark")
async def bookmark(event_id: int, user: UserDep) -> dict[str, bool | int]:
    current = find_event(event_id, user.id)
    is_bookmarked = not (current and current.is_bookmarked)
    return mark_event_state(user.id, event_id, is_bookmarked=is_bookmarked)
