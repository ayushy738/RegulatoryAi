from typing import Annotated

from fastapi import APIRouter, Depends

from backend.api.auth import CurrentUser, admin_user
from backend.core.repository import (
    list_crawl_runs,
    list_sources,
)
from backend.core.repository import (
    toggle_source as update_source_toggle,
)

router = APIRouter(prefix="/admin", tags=["admin"])
AdminUserDep = Annotated[CurrentUser, Depends(admin_user)]


@router.get("/sources")
async def sources(user: AdminUserDep) -> list[dict]:
    return list_sources()


@router.post("/sources/{source_id}/toggle")
async def toggle_source(
    source_id: int,
    user: AdminUserDep,
) -> dict[str, int | bool]:
    return update_source_toggle(source_id)


@router.get("/runs")
async def crawl_runs(user: AdminUserDep) -> list[dict]:
    return list_crawl_runs()
