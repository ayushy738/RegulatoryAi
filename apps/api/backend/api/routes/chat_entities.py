from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from backend.api.deps import UserDep
from backend.api.routes.chat_sessions import require_ask_v2_api
from backend.ask.entity_lookup import (
    EntityLookupRequest,
    EntityLookupResponse,
    EntityLookupService,
    EntityLookupUnavailable,
)


def get_entity_lookup_service() -> EntityLookupService:
    return EntityLookupService()


EntityLookupServiceDep = Annotated[
    EntityLookupService,
    Depends(get_entity_lookup_service),
]

router = APIRouter(
    prefix="/chat/entities",
    tags=["chat-entities"],
    dependencies=[Depends(require_ask_v2_api)],
)


@router.post(
    "/resolve",
    response_model=EntityLookupResponse,
)
def resolve_entity(
    request: EntityLookupRequest,
    _user: UserDep,
    service: EntityLookupServiceDep,
) -> EntityLookupResponse:
    try:
        return service.resolve(request)
    except EntityLookupUnavailable:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Entity lookup is temporarily unavailable",
        ) from None
