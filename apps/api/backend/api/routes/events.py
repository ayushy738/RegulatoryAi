from datetime import date

from fastapi import APIRouter, HTTPException, Query

from backend.api.deps import UserDep
from backend.core.models import EventSummary
from backend.core.sample_data import SAMPLE_DIGEST

router = APIRouter(prefix="/events", tags=["events"])


@router.get("", response_model=list[EventSummary])
async def list_events(
    user: UserDep,
    jurisdiction: str | None = None,
    source: str | None = None,
    topic: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    page: int = Query(default=1, ge=1),
) -> list[EventSummary]:
    events = SAMPLE_DIGEST.events
    if jurisdiction:
        events = [event for event in events if event.jurisdiction == jurisdiction]
    if topic:
        events = [event for event in events if topic in event.topic_tags]
    if date_from:
        events = [event for event in events if event.issue_date and event.issue_date >= date_from]
    if date_to:
        events = [event for event in events if event.issue_date and event.issue_date <= date_to]
    if source:
        events = [
            event
            for event in events
            if event.issuing_body and source.lower() in event.issuing_body.lower()
        ]
    return events


@router.get("/{event_id}", response_model=EventSummary)
async def get_event(event_id: int, user: UserDep) -> EventSummary:
    for event in SAMPLE_DIGEST.events:
        if event.id == event_id:
            return event
    raise HTTPException(status_code=404, detail="Event not found")


@router.post("/{event_id}/read")
async def mark_read(event_id: int, user: UserDep) -> dict[str, bool | int]:
    return {"event_id": event_id, "is_read": True}


@router.post("/{event_id}/bookmark")
async def bookmark(event_id: int, user: UserDep) -> dict[str, bool | int]:
    return {"event_id": event_id, "is_bookmarked": True}
