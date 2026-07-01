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
    UserUpdatePayload,
)
from backend.core.repository import (
    create_source,
    create_source_page,
    delete_source,
    delete_source_page,
    get_admin_analytics,
    get_crawl_run,
    get_source_analytics,
    list_admin_users,
    list_admin_documents,
    list_admin_events,
    list_admin_families,
    list_all_source_pages,
    list_crawl_runs,
    list_source_page_checkpoints,
    list_source_pages,
    list_sources,
    update_admin_user,
    update_source,
    update_source_page,
)
from backend.pipeline.run_once import run_crawl
from backend.rag.admin import (
    chunk_count,
    chunk_inspector,
    context_preview,
    embedding_queue,
    prompt_preview,
    rag_status,
    retrieval_inspector,
    vector_search_tester,
)
from backend.rag.indexing import (
    enqueue_existing_documents,
    process_pending_rag_jobs,
    requeue_processing_jobs,
)

router = APIRouter(prefix="/admin", tags=["admin"])
AdminUserDep = Annotated[CurrentUser, Depends(admin_user)]


@router.get("/sources")
async def sources(user: AdminUserDep) -> list[dict]:
    del user
    return list_sources()


@router.get("/users")
async def users(user: AdminUserDep) -> list[dict]:
    del user
    return list_admin_users()


@router.put("/users/{user_id}")
async def edit_user(user_id: str, payload: UserUpdatePayload, user: AdminUserDep) -> dict:
    if user.id == user_id and payload.role != "admin":
        raise HTTPException(status_code=400, detail="Admins cannot remove their own admin access")
    updated = update_admin_user(user_id, payload)
    if updated:
        return updated
    raise HTTPException(status_code=404, detail="User not found")


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


@router.get("/rag/status")
async def rag_readiness(user: AdminUserDep) -> dict:
    del user
    return rag_status()


@router.get("/rag/queue")
async def rag_queue(user: AdminUserDep, limit: int = 100) -> list[dict]:
    del user
    return embedding_queue(limit=limit)


@router.post("/rag/process")
async def rag_process(
    user: AdminUserDep,
    limit: int = 25,
    include_processing: bool = False,
) -> dict:
    del user
    return process_pending_rag_jobs(
        limit=limit,
        include_processing=include_processing,
    )


@router.post("/rag/requeue-processing")
async def rag_requeue_processing(user: AdminUserDep, limit: int | None = None) -> dict:
    del user
    return requeue_processing_jobs(limit=limit)


@router.post("/rag/enqueue-existing")
async def rag_enqueue_existing(user: AdminUserDep, limit: int | None = None) -> dict:
    del user
    return enqueue_existing_documents(limit=limit)


@router.get("/rag/chunks")
async def rag_chunks(user: AdminUserDep) -> list[dict]:
    del user
    return chunk_count()


@router.get("/rag/chunks/{document_id}")
async def rag_chunk_detail(document_id: int, user: AdminUserDep) -> list[dict]:
    del user
    return chunk_inspector(document_id)


@router.get("/rag/retrieval")
async def rag_retrieval(query: str, user: AdminUserDep, limit: int = 15) -> dict:
    del user
    return retrieval_inspector(query, limit=limit)


@router.get("/rag/context")
async def rag_context(query: str, user: AdminUserDep, limit: int = 15) -> dict:
    del user
    return context_preview(query, limit=limit)


@router.get("/rag/prompt")
async def rag_prompt(query: str, user: AdminUserDep, limit: int = 15) -> dict:
    del user
    return prompt_preview(query, limit=limit)


@router.get("/rag/vector-search")
async def rag_vector_search(query: str, user: AdminUserDep, limit: int = 10) -> list[dict]:
    del user
    return vector_search_tester(query, limit=limit)
