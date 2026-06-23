from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from backend.api.auth import CurrentUser, admin_user
from backend.core.models import (
    CrawlTriggerResponse,
    SourceAnalyticsResponse,
    SourcePagePayload,
    SourcePageUpdatePayload,
    SourcePayload,
    SourceUpdatePayload,
)
from backend.core.repository import (
    create_source,
    create_source_page,
    delete_source,
    delete_source_page,
    get_admin_analytics,
    get_crawl_run,
    get_source_analytics,
    list_admin_documents,
    list_admin_events,
    list_admin_families,
    list_all_source_pages,
    list_crawl_runs,
    list_source_page_checkpoints,
    list_source_pages,
    list_sources,
    update_source,
    update_source_page,
)
from backend.pipeline.run_once import run_crawl

router = APIRouter(prefix="/admin", tags=["admin"])
AdminUserDep = Annotated[CurrentUser, Depends(admin_user)]


@router.get("/sources")
async def sources(user: AdminUserDep) -> list[dict]:
    del user
    return list_sources()


@router.post("/sources")
async def add_source(payload: SourcePayload, user: AdminUserDep) -> dict:
    del user
    return create_source(payload)


@router.put("/sources/{source_id}")
async def edit_source(
    source_id: int,
    payload: SourceUpdatePayload,
    user: AdminUserDep,
) -> dict:
    del user
    source = update_source(source_id, payload)
    if source:
        return source
    raise HTTPException(status_code=404, detail="Source not found")


@router.delete("/sources/{source_id}")
async def remove_source(source_id: int, user: AdminUserDep) -> dict:
    del user
    result = delete_source(source_id)
    if result["deleted"]:
        return result
    raise HTTPException(status_code=404, detail="Source not found")


@router.get("/sources/{source_id}/pages")
async def source_pages(source_id: int, user: AdminUserDep) -> list[dict]:
    del user
    return list_source_pages(source_id)


@router.post("/sources/{source_id}/pages")
async def add_source_page(
    source_id: int,
    payload: SourcePagePayload,
    user: AdminUserDep,
) -> dict:
    del user
    return create_source_page(source_id, payload)


@router.put("/pages/{page_id}")
async def edit_source_page(
    page_id: int,
    payload: SourcePageUpdatePayload,
    user: AdminUserDep,
) -> dict:
    del user
    page = update_source_page(page_id, payload)
    if page:
        return page
    raise HTTPException(status_code=404, detail="Source page not found")


@router.delete("/pages/{page_id}")
async def remove_source_page(page_id: int, user: AdminUserDep) -> dict:
    del user
    result = delete_source_page(page_id)
    if result["deleted"]:
        return result
    raise HTTPException(status_code=404, detail="Source page not found")


@router.post("/pages/{page_id}/crawl", response_model=CrawlTriggerResponse)
async def crawl_source_page(page_id: int, user: AdminUserDep) -> dict:
    del user
    return await run_crawl(page_id=page_id)


@router.post("/sources/{source_id}/crawl", response_model=CrawlTriggerResponse)
async def crawl_source(source_id: int, user: AdminUserDep) -> dict:
    del user
    return await run_crawl(source_id=source_id)


@router.get("/runs")
async def crawl_runs(user: AdminUserDep) -> list[dict]:
    del user
    return list_crawl_runs()


@router.get("/runs/{run_id}")
async def crawl_run(run_id: int, user: AdminUserDep) -> dict:
    del user
    run = get_crawl_run(run_id)
    if run:
        return run
    raise HTTPException(status_code=404, detail="Crawl run not found")


@router.get("/pages")
async def all_source_pages(user: AdminUserDep) -> list[dict]:
    del user
    return list_all_source_pages()


@router.get("/checkpoints")
async def source_page_checkpoints(user: AdminUserDep) -> list[dict]:
    del user
    return list_source_page_checkpoints()


@router.get("/documents")
async def admin_documents(user: AdminUserDep, limit: int = 100) -> list[dict]:
    del user
    return list_admin_documents(limit=limit)


@router.get("/events")
async def admin_events(user: AdminUserDep, limit: int = 100) -> list[dict]:
    del user
    return list_admin_events(limit=limit)


@router.get("/families")
async def admin_families(user: AdminUserDep, limit: int = 100) -> list[dict]:
    del user
    return list_admin_families(limit=limit)


@router.get("/analytics")
async def admin_analytics(user: AdminUserDep) -> dict:
    del user
    return get_admin_analytics()


@router.get("/sources/{source_id}/analytics", response_model=SourceAnalyticsResponse)
async def source_analytics(source_id: int, user: AdminUserDep) -> dict:
    del user
    analytics = get_source_analytics(source_id)
    if analytics:
        return analytics
    raise HTTPException(status_code=404, detail="Source not found")
