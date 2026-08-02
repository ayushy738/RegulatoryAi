from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from backend.api.deps import UserDep
from backend.api.routes.chat_sessions import require_ask_v2_api
from backend.ask.manual_document_search import (
    ManualDocumentSearchCursorError,
    ManualDocumentSearchRequest,
    ManualDocumentSearchResponse,
    ManualDocumentSearchService,
    ManualDocumentSearchUnavailable,
)


def get_manual_document_search_service() -> ManualDocumentSearchService:
    return ManualDocumentSearchService()


ManualDocumentSearchServiceDep = Annotated[
    ManualDocumentSearchService,
    Depends(get_manual_document_search_service),
]

router = APIRouter(
    prefix="/chat/documents/search",
    tags=["chat-documents"],
    dependencies=[Depends(require_ask_v2_api)],
)


@router.post("", response_model=ManualDocumentSearchResponse)
def search_documents(
    request: ManualDocumentSearchRequest,
    _user: UserDep,
    service: ManualDocumentSearchServiceDep,
) -> ManualDocumentSearchResponse:
    try:
        return service.search(request)
    except ManualDocumentSearchCursorError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid manual document search cursor",
        ) from None
    except ManualDocumentSearchUnavailable:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Manual document search is temporarily unavailable",
        ) from None
