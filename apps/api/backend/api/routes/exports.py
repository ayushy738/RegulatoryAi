import csv
import io
import json
from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, HTTPException, Query, Response

from backend.api.deps import UserDep
from backend.core.models import EventSummary
from backend.core.repository import latest_digest, record_export

router = APIRouter(prefix="/exports", tags=["exports"])


@router.get("/latest")
async def export_latest(
    user: UserDep,
    format: Literal["json", "csv", "markdown"] = Query(default="json"),
) -> Response:
    user_id = user.id
    digest = latest_digest(user_id)
    if format == "json":
        body = json.dumps(digest.model_dump(mode="json"), indent=2)
        media_type = "application/json"
        extension = "json"
    elif format == "csv":
        body = _events_csv(digest.events)
        media_type = "text/csv; charset=utf-8"
        extension = "csv"
    elif format == "markdown":
        body = _digest_markdown(digest.digest_date.isoformat(), digest.events)
        media_type = "text/markdown; charset=utf-8"
        extension = "md"
    else:
        raise HTTPException(status_code=400, detail="Unsupported export format")

    record_export(user_id, "latest_digest", format, len(digest.events))
    filename = f"resolven-regulatory-ai-{digest.digest_date}.{extension}"
    return Response(
        content=body,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _events_csv(events: list[EventSummary]) -> str:
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(
        [
            "id",
            "title",
            "issuing_body",
            "jurisdiction",
            "issue_date",
            "event_type",
            "topics",
            "summary",
            "why_it_matters",
            "source_url",
            "detected_at",
        ]
    )
    for event in events:
        writer.writerow(
            [
                event.id,
                event.title,
                event.issuing_body or "",
                event.jurisdiction or "",
                event.issue_date.isoformat() if event.issue_date else "",
                event.event_type,
                "; ".join(event.topic_tags),
                event.summary.plain_english_summary if event.summary else event.raw_summary or "",
                event.summary.why_it_matters if event.summary else "",
                str(event.source_url),
                event.detected_at.isoformat(),
            ]
        )
    return output.getvalue()


def _digest_markdown(digest_date: str, events: list[EventSummary]) -> str:
    lines = [
        f"# Resolven Regulatory AI - Latest News ({digest_date})",
        "",
        f"Exported at {datetime.now(UTC).isoformat()}.",
        "",
    ]
    for event in events:
        summary = event.summary.plain_english_summary if event.summary else event.raw_summary or ""
        why = event.summary.why_it_matters if event.summary else ""
        lines.extend(
            [
                f"## {event.title}",
                "",
                (
                    f"`{(event.jurisdiction or 'unknown').upper()} - "
                    f"{event.issuing_body or 'Unknown body'} - "
                    f"{event.issue_date.isoformat() if event.issue_date else 'date unknown'} - "
                    f"{event.event_type}`"
                ),
                "",
                summary,
                "",
            ]
        )
        if why:
            lines.extend([f"Why it matters: {why}", ""])
        lines.extend([f"Topics: {', '.join(event.topic_tags)}", f"Source: {event.source_url}", ""])
    return "\n".join(line for line in lines if line is not None)
