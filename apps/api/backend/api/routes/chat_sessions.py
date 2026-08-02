from __future__ import annotations

import base64
import hashlib
import json
from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from backend.api.deps import UserDep
from backend.ask.models import ChatSession, ChatTurn
from backend.ask.persistence import (
    AskPersistenceService,
    ChatSessionStateConflictError,
)
from backend.ask.schemas import (
    AskSessionCreateRequest,
    AskSessionExportResponse,
    AskSessionListResponse,
    AskSessionPatchRequest,
    AskSessionResponse,
    AskTurnListResponse,
    AskTurnResponse,
)
from backend.core.config import settings


def require_ask_v2_api() -> None:
    if not settings.ask_ai_v2_api_enabled:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")


def get_ask_session_service() -> AskPersistenceService:
    return AskPersistenceService()


AskSessionServiceDep = Annotated[
    AskPersistenceService,
    Depends(get_ask_session_service),
]

router = APIRouter(
    prefix="/chat/sessions",
    tags=["chat-sessions"],
    dependencies=[Depends(require_ask_v2_api)],
)


@router.post(
    "",
    response_model=AskSessionResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_session(
    request: AskSessionCreateRequest,
    user: UserDep,
    service: AskSessionServiceDep,
) -> AskSessionResponse:
    session = service.create_session(
        user_id=UUID(user.id),
        event_id=request.event_id,
        title=request.title or "New research",
        primary_entity=request.primary_entity,
        primary_topic=request.primary_topic,
        scope_snapshot=request.scope_snapshot,
    )
    return AskSessionResponse.from_domain(session)


@router.get("", response_model=AskSessionListResponse)
def list_sessions(
    user: UserDep,
    service: AskSessionServiceDep,
    cursor: str | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    q: Annotated[str | None, Query(max_length=200)] = None,
    knowledge_mode: Literal["official", "general", "live"] | None = None,
    entity: Annotated[str | None, Query(max_length=200)] = None,
    archived: bool = False,
    pinned: bool | None = None,
) -> AskSessionListResponse:
    normalized_query = _normalize_search_text(q, "search query")
    normalized_entity = _normalize_search_text(entity, "entity filter")
    filter_key = _session_filter_key(
        query=normalized_query,
        knowledge_mode=knowledge_mode,
        entity=normalized_entity,
        archived=archived,
        pinned=pinned,
    )
    cursor_relevance, cursor_updated_at, cursor_id = _decode_cursor(
        cursor,
        expected_filter_key=filter_key,
        has_query=normalized_query is not None,
        allow_legacy=(
            normalized_query is None
            and knowledge_mode is None
            and normalized_entity is None
            and not archived
            and pinned is None
        ),
    )
    page = service.list_sessions(
        user_id=UUID(user.id),
        limit=limit,
        query=normalized_query,
        knowledge_mode=knowledge_mode,
        entity=normalized_entity,
        archived=archived,
        pinned=pinned,
        cursor_relevance=cursor_relevance,
        cursor_updated_at=cursor_updated_at,
        cursor_id=cursor_id,
    )
    next_cursor = None
    if page.has_more and page.items:
        relevance = page.relevances[-1] if page.relevances else 0
        next_cursor = _encode_cursor(
            page.items[-1],
            relevance=relevance,
            filter_key=filter_key,
        )
    return AskSessionListResponse(
        items=[AskSessionResponse.from_domain(item) for item in page.items],
        next_cursor=next_cursor,
    )


@router.patch("/{session_id}", response_model=AskSessionResponse)
def patch_session(
    session_id: UUID,
    request: AskSessionPatchRequest,
    user: UserDep,
    service: AskSessionServiceDep,
) -> AskSessionResponse:
    try:
        session = service.patch_session(
            session_id=session_id,
            user_id=UUID(user.id),
            title=request.title,
            is_pinned=request.is_pinned,
        )
    except ChatSessionStateConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    return AskSessionResponse.from_domain(_session_or_404(session))


@router.post("/{session_id}/archive", response_model=AskSessionResponse)
def archive_session(
    session_id: UUID,
    user: UserDep,
    service: AskSessionServiceDep,
) -> AskSessionResponse:
    return AskSessionResponse.from_domain(
        _session_or_404(
            service.archive_session(
                session_id=session_id,
                user_id=UUID(user.id),
            )
        )
    )


@router.post("/{session_id}/restore", response_model=AskSessionResponse)
def restore_session(
    session_id: UUID,
    user: UserDep,
    service: AskSessionServiceDep,
) -> AskSessionResponse:
    return AskSessionResponse.from_domain(
        _session_or_404(
            service.restore_session(
                session_id=session_id,
                user_id=UUID(user.id),
            )
        )
    )


@router.post(
    "/{session_id}/duplicate",
    response_model=AskSessionResponse,
    status_code=status.HTTP_201_CREATED,
)
def duplicate_session(
    session_id: UUID,
    user: UserDep,
    service: AskSessionServiceDep,
) -> AskSessionResponse:
    return AskSessionResponse.from_domain(
        _session_or_404(
            service.duplicate_session(
                session_id=session_id,
                user_id=UUID(user.id),
            )
        )
    )


@router.get("/{session_id}/export", response_model=AskSessionExportResponse)
def export_session(
    session_id: UUID,
    user: UserDep,
    service: AskSessionServiceDep,
) -> AskSessionExportResponse:
    exported = service.export_session(
        session_id=session_id,
        user_id=UUID(user.id),
    )
    if exported is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found",
        )
    return AskSessionExportResponse.from_domain(exported)


@router.delete("/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_session(
    session_id: UUID,
    user: UserDep,
    service: AskSessionServiceDep,
) -> Response:
    deleted = service.soft_delete_session(
        session_id=session_id,
        user_id=UUID(user.id),
    )
    if deleted is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found",
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{session_id}/messages", response_model=AskTurnListResponse)
def list_session_messages(
    session_id: UUID,
    user: UserDep,
    service: AskSessionServiceDep,
    cursor: str | None = None,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
) -> AskTurnListResponse:
    cursor_created_at, cursor_id = _decode_message_cursor(cursor)
    page = service.list_turns(
        session_id=session_id,
        user_id=UUID(user.id),
        limit=limit,
        cursor_created_at=cursor_created_at,
        cursor_id=cursor_id,
    )
    if page is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found",
        )
    next_cursor = None
    if page.has_more and page.items:
        next_cursor = _encode_message_cursor(page.items[-1])
    return AskTurnListResponse(
        items=[AskTurnResponse.from_domain(item) for item in page.items],
        next_cursor=next_cursor,
    )


@router.get("/{session_id}", response_model=AskSessionResponse)
def get_session(
    session_id: UUID,
    user: UserDep,
    service: AskSessionServiceDep,
) -> AskSessionResponse:
    session = service.get_session(
        session_id=session_id,
        user_id=UUID(user.id),
    )
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found",
        )
    return AskSessionResponse.from_domain(session)


def _session_or_404(session: ChatSession | None) -> ChatSession:
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found",
        )
    return session


def _encode_cursor(
    session: ChatSession,
    *,
    relevance: int,
    filter_key: str,
) -> str:
    payload = json.dumps(
        {
            "filter_key": filter_key,
            "id": str(session.id),
            "kind": "sessions",
            "relevance": relevance,
            "updated_at": session.updated_at.isoformat(),
            "version": 2,
        },
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")


def _decode_cursor(
    cursor: str | None,
    *,
    expected_filter_key: str,
    has_query: bool,
    allow_legacy: bool,
) -> tuple[int | None, datetime | None, UUID | None]:
    if cursor is None:
        return None, None, None
    try:
        padding = "=" * (-len(cursor) % 4)
        payload = json.loads(
            base64.b64decode(
                cursor + padding,
                altchars=b"-_",
                validate=True,
            )
        )
        if (
            allow_legacy
            and isinstance(payload, dict)
            and payload.get("version") == 1
            and isinstance(payload.get("updated_at"), str)
            and isinstance(payload.get("id"), str)
        ):
            updated_at = datetime.fromisoformat(payload["updated_at"])
            if updated_at.tzinfo is None:
                raise ValueError("cursor timestamp must include a timezone")
            return 0, updated_at, UUID(payload["id"])
        if (
            not isinstance(payload, dict)
            or payload.get("version") != 2
            or payload.get("kind") != "sessions"
            or payload.get("filter_key") != expected_filter_key
            or not isinstance(payload.get("relevance"), int)
            or not isinstance(payload.get("updated_at"), str)
            or not isinstance(payload.get("id"), str)
        ):
            raise ValueError("unsupported cursor")
        relevance = payload["relevance"]
        allowed_relevance = {300, 400, 500} if has_query else {0}
        if relevance not in allowed_relevance:
            raise ValueError("invalid relevance")
        updated_at = datetime.fromisoformat(payload["updated_at"])
        if updated_at.tzinfo is None:
            raise ValueError("cursor timestamp must include a timezone")
        return relevance, updated_at, UUID(payload["id"])
    except (UnicodeDecodeError, ValueError, TypeError, json.JSONDecodeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Invalid cursor",
        ) from exc


def _normalize_search_text(value: str | None, label: str) -> str | None:
    if value is None:
        return None
    normalized = " ".join(value.split()).casefold()
    if not normalized:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Invalid {label}",
        )
    return normalized


def _session_filter_key(
    *,
    query: str | None,
    knowledge_mode: str | None,
    entity: str | None,
    archived: bool,
    pinned: bool | None,
) -> str:
    canonical = json.dumps(
        {
            "archived": archived,
            "entity": entity,
            "knowledge_mode": knowledge_mode,
            "pinned": pinned,
            "query": query,
        },
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _encode_message_cursor(turn: ChatTurn) -> str:
    payload = json.dumps(
        {
            "created_at": turn.anchor_created_at.isoformat(),
            "id": turn.anchor_id,
            "kind": "messages",
            "version": 1,
        },
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")


def _decode_message_cursor(cursor: str | None) -> tuple[datetime | None, int | None]:
    if cursor is None:
        return None, None
    try:
        padding = "=" * (-len(cursor) % 4)
        payload = json.loads(
            base64.b64decode(
                cursor + padding,
                altchars=b"-_",
                validate=True,
            )
        )
        if (
            not isinstance(payload, dict)
            or payload.get("version") != 1
            or payload.get("kind") != "messages"
            or not isinstance(payload.get("created_at"), str)
            or not isinstance(payload.get("id"), int)
            or payload["id"] < 1
        ):
            raise ValueError("unsupported cursor")
        created_at = datetime.fromisoformat(payload["created_at"])
        if created_at.tzinfo is None:
            raise ValueError("cursor timestamp must include a timezone")
        return created_at, payload["id"]
    except (UnicodeDecodeError, ValueError, TypeError, json.JSONDecodeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Invalid cursor",
        ) from exc
