from fastapi import APIRouter

from backend.api.deps import UserDep
from backend.core.repository import list_enabled_source_catalog

router = APIRouter(prefix="/sources", tags=["sources"])


@router.get("/catalog")
async def source_catalog(user: UserDep) -> list[dict]:
    """Enabled regulatory sources for subscription preferences."""

    del user
    return list_enabled_source_catalog()
