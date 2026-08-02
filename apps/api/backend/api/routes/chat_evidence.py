from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status

from backend.api.deps import UserDep
from backend.api.routes.chat_sessions import require_ask_v2_api
from backend.ask.persistence import AskPersistenceService
from backend.ask.regeneration import (
    RefreshResponseRequest,
    RegenerateResponseRequest,
    ResponseRegenerationConflict,
    ResponseRegenerationNotEligible,
    ResponseRegenerationNotFound,
    ResponseRegenerationResponse,
    ResponseRegenerationService,
)
from backend.ask.schemas import (
    AskCitationDetailResponse,
    AskFeedbackRequest,
    AskFeedbackResponse,
    AskMessageEvidenceResponse,
    AskMessageSourcesResponse,
    AskSavedItemCreateRequest,
    AskSavedItemListResponse,
    AskSavedItemResponse,
)


def get_ask_evidence_service() -> AskPersistenceService:
    return AskPersistenceService()


AskEvidenceServiceDep = Annotated[
    AskPersistenceService,
    Depends(get_ask_evidence_service),
]


def get_ask_regeneration_service() -> ResponseRegenerationService:
    return ResponseRegenerationService()


AskRegenerationServiceDep = Annotated[
    ResponseRegenerationService,
    Depends(get_ask_regeneration_service),
]

router = APIRouter(
    prefix="/chat/messages",
    tags=["chat-evidence"],
    dependencies=[Depends(require_ask_v2_api)],
)

saved_items_router = APIRouter(
    prefix="/chat/sessions",
    tags=["chat-saved-items"],
    dependencies=[Depends(require_ask_v2_api)],
)


def _get_owned_version(
    *,
    message_id: UUID,
    user_id: UUID,
    service: AskPersistenceService,
) -> AskMessageEvidenceResponse:
    version = service.get_response_version(
        assistant_message_public_id=message_id,
        user_id=user_id,
    )
    if version is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Message not found",
        )
    return AskMessageEvidenceResponse.from_domain(version)


@router.get("/{message_id}", response_model=AskMessageEvidenceResponse)
def get_message_evidence(
    message_id: UUID,
    user: UserDep,
    service: AskEvidenceServiceDep,
) -> AskMessageEvidenceResponse:
    return _get_owned_version(
        message_id=message_id,
        user_id=UUID(user.id),
        service=service,
    )


@router.get("/{message_id}/sources", response_model=AskMessageSourcesResponse)
def get_message_sources(
    message_id: UUID,
    user: UserDep,
    service: AskEvidenceServiceDep,
) -> AskMessageSourcesResponse:
    version = service.get_response_version(
        assistant_message_public_id=message_id,
        user_id=UUID(user.id),
    )
    if version is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Message not found",
        )
    return AskMessageSourcesResponse.from_domain(version)


@router.get(
    "/{message_id}/citations/{citation_id}",
    response_model=AskCitationDetailResponse,
)
def get_message_citation_detail(
    message_id: UUID,
    citation_id: UUID,
    user: UserDep,
    service: AskEvidenceServiceDep,
) -> AskCitationDetailResponse:
    detail = service.get_citation_detail(
        assistant_message_public_id=message_id,
        citation_id=citation_id,
        user_id=UUID(user.id),
    )
    if detail is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Citation not found",
        )
    return AskCitationDetailResponse.from_domain(detail)


@router.post("/{message_id}/feedback", response_model=AskFeedbackResponse)
def record_message_feedback(
    message_id: UUID,
    request: AskFeedbackRequest,
    user: UserDep,
    service: AskEvidenceServiceDep,
) -> AskFeedbackResponse:
    feedback = service.record_message_feedback(
        assistant_message_public_id=message_id,
        user_id=UUID(user.id),
        value=request.value,
        reason_code=request.reason_code,
        comment=request.comment,
    )
    if feedback is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Message not found",
        )
    return AskFeedbackResponse.from_domain(feedback, message_id=message_id)


def _regeneration_error(exc: Exception) -> HTTPException:
    if isinstance(exc, ResponseRegenerationNotFound):
        return HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Message not found",
        )
    if isinstance(exc, ResponseRegenerationNotEligible):
        return HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Message cannot create another response version",
        )
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail="Response version conflict",
    )


@router.post(
    "/{message_id}/regenerate",
    response_model=ResponseRegenerationResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def regenerate_message(
    message_id: UUID,
    request: RegenerateResponseRequest,
    user: UserDep,
    service: AskRegenerationServiceDep,
) -> ResponseRegenerationResponse:
    try:
        record = service.regenerate(
            source_message_id=message_id,
            user_id=UUID(user.id),
            request=request,
        )
    except (
        ResponseRegenerationNotFound,
        ResponseRegenerationNotEligible,
        ResponseRegenerationConflict,
    ) as exc:
        raise _regeneration_error(exc) from None
    return ResponseRegenerationResponse.from_record(record)


@router.post(
    "/{message_id}/refresh",
    response_model=ResponseRegenerationResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def refresh_message(
    message_id: UUID,
    request: RefreshResponseRequest,
    user: UserDep,
    service: AskRegenerationServiceDep,
) -> ResponseRegenerationResponse:
    try:
        record = service.refresh(
            source_message_id=message_id,
            user_id=UUID(user.id),
            request=request,
        )
    except (
        ResponseRegenerationNotFound,
        ResponseRegenerationNotEligible,
        ResponseRegenerationConflict,
    ) as exc:
        raise _regeneration_error(exc) from None
    return ResponseRegenerationResponse.from_record(record)


@saved_items_router.get(
    "/{session_id}/saved-items",
    response_model=AskSavedItemListResponse,
)
def list_saved_items(
    session_id: UUID,
    user: UserDep,
    service: AskEvidenceServiceDep,
) -> AskSavedItemListResponse:
    items = service.list_saved_items(
        session_id=session_id,
        user_id=UUID(user.id),
    )
    if items is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found",
        )
    return AskSavedItemListResponse(
        items=[AskSavedItemResponse.from_domain(item) for item in items],
    )


@saved_items_router.post(
    "/{session_id}/saved-items",
    response_model=AskSavedItemResponse,
    status_code=status.HTTP_201_CREATED,
)
def save_item(
    session_id: UUID,
    request: AskSavedItemCreateRequest,
    user: UserDep,
    service: AskEvidenceServiceDep,
) -> AskSavedItemResponse:
    item = service.save_item(
        session_id=session_id,
        user_id=UUID(user.id),
        item_type=request.item_type,
        target_key=request.target_id,
    )
    if item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Saved item target not found",
        )
    return AskSavedItemResponse.from_domain(item)


@saved_items_router.delete(
    "/{session_id}/saved-items/{saved_item_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_saved_item(
    session_id: UUID,
    saved_item_id: UUID,
    user: UserDep,
    service: AskEvidenceServiceDep,
) -> Response:
    deleted = service.delete_saved_item(
        saved_item_id=saved_item_id,
        session_id=session_id,
        user_id=UUID(user.id),
    )
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Saved item not found",
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
