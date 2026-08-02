from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from backend.api.deps import UserDep
from backend.api.routes.chat_sessions import require_ask_v2_api
from backend.ask.federated_search import (
    FederatedSearchCursorError,
    FederatedSearchRequest,
    FederatedSearchResponse,
    FederatedSearchService,
    FederatedSearchUnavailable,
)


def get_federated_search_service() -> FederatedSearchService:
    return FederatedSearchService()


FederatedSearchServiceDep = Annotated[
    FederatedSearchService,
    Depends(get_federated_search_service),
]

router = APIRouter(
    prefix="/chat/search",
    tags=["chat-search"],
    dependencies=[Depends(require_ask_v2_api)],
)


@router.post("", response_model=FederatedSearchResponse)
def search(
    request: FederatedSearchRequest,
    user: UserDep,
    service: FederatedSearchServiceDep,
) -> FederatedSearchResponse:
    try:
        return service.search(user_id=UUID(user.id), request=request)
    except FederatedSearchCursorError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid research search cursor",
        ) from None
    except FederatedSearchUnavailable:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Research search is temporarily unavailable",
        ) from None
