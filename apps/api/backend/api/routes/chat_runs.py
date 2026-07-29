from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse

from backend.api.deps import UserDep
from backend.ask.orchestration.retry import (
    CapabilityRetryConflict,
    CapabilityRetryError,
    CapabilityRetryNotEligible,
    CapabilityRetryNotFound,
    CapabilityRetryRequestBody,
    CapabilityRetryResponse,
    CapabilityRetryService,
    CapabilityRetryStale,
    PostgresCapabilityRetryStore,
)
from backend.ask.orchestration.streaming import (
    RUN_EVENT_STREAM_PAGE_SIZE,
    RunEventStreamCursorError,
    RunEventStreamError,
    RunEventStreamNotFound,
    RunEventStreamService,
)
from backend.core.config import settings


def require_ask_v2_api() -> None:
    if not settings.ask_ai_v2_api_enabled:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Not found",
        )


def require_ask_streaming() -> None:
    if not (
        settings.ask_ai_v2_api_enabled
        and settings.ask_ai_streaming_enabled
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Not found",
        )


def get_run_event_stream_service() -> RunEventStreamService:
    return RunEventStreamService()


def get_capability_retry_service() -> CapabilityRetryService:
    return CapabilityRetryService(PostgresCapabilityRetryStore())


RunEventStreamServiceDep = Annotated[
    RunEventStreamService,
    Depends(get_run_event_stream_service),
]
CapabilityRetryServiceDep = Annotated[
    CapabilityRetryService,
    Depends(get_capability_retry_service),
]

router = APIRouter(
    prefix="/chat/runs",
    tags=["chat-runs"],
)


@router.get(
    "/{run_id}/events",
    dependencies=[Depends(require_ask_streaming)],
)
async def stream_run_events(
    run_id: UUID,
    request: Request,
    user: UserDep,
    service: RunEventStreamServiceDep,
    cursor: Annotated[str | None, Query(max_length=512)] = None,
    last_event_id: Annotated[
        str | None,
        Header(alias="Last-Event-ID", max_length=512),
    ] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = RUN_EVENT_STREAM_PAGE_SIZE,
) -> StreamingResponse:
    if (
        cursor is not None
        and last_event_id is not None
        and cursor != last_event_id
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Conflicting event cursors",
        )
    effective_cursor = cursor if cursor is not None else last_event_id
    try:
        subscription = await service.prepare(
            run_id=run_id,
            user_id=UUID(user.id),
            cursor=effective_cursor,
            limit=limit,
        )
    except RunEventStreamNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Run not found",
        ) from exc
    except RunEventStreamCursorError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Invalid event cursor",
        ) from exc
    except RunEventStreamError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Run event stream unavailable",
        ) from exc

    return StreamingResponse(
        service.frames(
            subscription,
            disconnected=request.is_disconnected,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post(
    "/{run_id}/retry",
    response_model=CapabilityRetryResponse,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(require_ask_v2_api)],
)
async def retry_run_capability(
    run_id: UUID,
    request: CapabilityRetryRequestBody,
    user: UserDep,
    service: CapabilityRetryServiceDep,
) -> CapabilityRetryResponse:
    try:
        record = await service.request(
            run_id=run_id,
            user_id=UUID(user.id),
            node_id=request.node_id,
            idempotency_key=request.idempotency_key,
        )
    except CapabilityRetryNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Run or capability not found",
        ) from exc
    except (
        CapabilityRetryNotEligible,
        CapabilityRetryConflict,
        CapabilityRetryStale,
    ) as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Capability retry is not available",
        ) from exc
    except CapabilityRetryError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Capability retry is unavailable",
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Capability retry is unavailable",
        ) from exc
    return CapabilityRetryResponse.from_record(record)
