from typing import Annotated

from fastapi import APIRouter, Depends

from backend.api.auth import CurrentUser, admin_user
from backend.core.sample_data import SOURCES

router = APIRouter(prefix="/admin", tags=["admin"])
AdminUserDep = Annotated[CurrentUser, Depends(admin_user)]


@router.get("/sources")
async def sources(user: AdminUserDep) -> list[dict]:
    return SOURCES


@router.post("/sources/{source_id}/toggle")
async def toggle_source(
    source_id: int,
    user: AdminUserDep,
) -> dict[str, int | bool]:
    return {"source_id": source_id, "enabled": True}


@router.get("/runs")
async def crawl_runs(user: AdminUserDep) -> list[dict]:
    return [
        {
            "id": 1,
            "status": "partial",
            "sources_attempted": 3,
            "sources_succeeded": 3,
            "docs_found": 3,
            "new_events": 2,
        }
    ]
