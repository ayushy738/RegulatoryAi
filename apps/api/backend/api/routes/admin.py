from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query

from backend.api.auth import CurrentUser, admin_user, rag_process_user
from backend.core.admin_queries import (
    DEFAULT_PAGE_SIZE,
    MAX_PAGE_SIZE,
    get_crawl_run_pages,
    list_admin_users_page,
    list_crawl_run_sources,
    list_crawl_runs_page,
    list_sources_page,
)
from backend.core.logging import log_event
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
    list_admin_documents,
    list_admin_events,
    list_admin_families,
    list_admin_users,
    list_all_source_pages,
    list_crawl_runs,
    list_source_page_checkpoints,
    list_source_pages,
    list_sources,
    permanently_delete_source_page,
    restore_source_page,
    update_admin_user,
    update_source,
    update_source_page,
)
from backend.core.source_page_policy import (
    SourceDeleteBlockedError,
    SourcePageConflictError,
    SourcePagePermanentDeleteError,
    SourcePagePolicyError,
)


def _source_page_conflict_detail(exc: SourcePageConflictError) -> dict[str, object] | str:
    """Prefer structured 409 detail when a retired duplicate should be restored."""

    if exc.retired and exc.page_id is not None:
        return {
            "message": str(exc),
            "page_id": exc.page_id,
            "retired": True,
            "hint": "restore",
        }
    if exc.page_id is not None:
        return {
            "message": str(exc),
            "page_id": exc.page_id,
            "retired": False,
        }
    return str(exc)
from backend.pipeline.github_dispatch import CrawlDispatchError, dispatch_crawl_workflow
from backend.pipeline.run_once import queue_crawl_run
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
RagProcessUserDep = Annotated[CurrentUser, Depends(rag_process_user)]


PageParam = Annotated[int, Query(ge=1)]
PageSizeParam = Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)]


@router.get("/sources")
async def sources(
    user: AdminUserDep,
    q: str | None = None,
    jurisdiction: str | None = None,
    status: str = "all",
    last_run: str = "all",
    page: PageParam = 1,
    page_size: PageSizeParam = DEFAULT_PAGE_SIZE,
) -> dict:
    """Paginated source registry with search, jurisdiction/status/last-run filters."""

    del user
    return list_sources_page(
        q=q,
        jurisdiction=jurisdiction,
        status=status,
        last_run=last_run,
        page=page,
        page_size=page_size,
    )


@router.get("/sources/all")
async def all_sources(user: AdminUserDep) -> list[dict]:
    """Unpaginated registry, for pickers that need every source code."""

    del user
    return list_sources()


@router.get("/users")
async def users(
    user: AdminUserDep,
    q: str | None = None,
    role: str = "all",
    notifications: str = "all",
    page: PageParam = 1,
    page_size: PageSizeParam = DEFAULT_PAGE_SIZE,
) -> dict:
    """Paginated user directory with search plus role/notification filters."""

    del user
    return list_admin_users_page(
        q=q,
        role=role,
        notifications=notifications,
        page=page,
        page_size=page_size,
    )


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
    try:
        return create_source(payload)
    except SourcePagePolicyError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.put("/sources/{source_id}")
async def edit_source(
    source_id: int,
    payload: SourceUpdatePayload,
    user: AdminUserDep,
) -> dict:
    del user
    try:
        source = update_source(source_id, payload)
    except SourcePagePolicyError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if source:
        return source
    raise HTTPException(status_code=404, detail="Source not found")


@router.delete("/sources/{source_id}")
async def remove_source(source_id: int, user: AdminUserDep) -> dict:
    del user
    try:
        result = delete_source(source_id)
    except SourceDeleteBlockedError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if result["deleted"]:
        return result
    raise HTTPException(status_code=404, detail="Source not found")


@router.get("/sources/{source_id}/pages")
async def source_pages(
    source_id: int,
    user: AdminUserDep,
    include_retired: bool = False,
) -> list[dict]:
    del user
    return list_source_pages(source_id, include_retired=include_retired)


@router.post("/sources/{source_id}/pages")
async def add_source_page(
    source_id: int,
    payload: SourcePagePayload,
    user: AdminUserDep,
) -> dict:
    del user
    try:
        return create_source_page(source_id, payload)
    except SourcePageConflictError as exc:
        raise HTTPException(
            status_code=409,
            detail=_source_page_conflict_detail(exc),
        ) from exc
    except SourcePagePolicyError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.put("/pages/{page_id}")
async def edit_source_page(
    page_id: int,
    payload: SourcePageUpdatePayload,
    user: AdminUserDep,
) -> dict:
    del user
    try:
        page = update_source_page(page_id, payload)
    except SourcePageConflictError as exc:
        raise HTTPException(
            status_code=409,
            detail=_source_page_conflict_detail(exc),
        ) from exc
    except SourcePagePolicyError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if page:
        return page
    raise HTTPException(status_code=404, detail="Source page not found")


@router.delete("/pages/{page_id}")
async def remove_source_page(page_id: int, user: AdminUserDep) -> dict:
    """Soft-delete (retire) a monitored page. Never hard-deletes the row."""

    result = delete_source_page(page_id, deleted_by=user.id)
    if result["deleted"]:
        return result
    raise HTTPException(status_code=404, detail="Source page not found")


@router.post("/pages/{page_id}/retire")
async def retire_page(page_id: int, user: AdminUserDep) -> dict:
    """Explicit retire alias for soft-delete (same semantics as DELETE)."""

    result = delete_source_page(page_id, deleted_by=user.id)
    if result["deleted"]:
        return result
    raise HTTPException(status_code=404, detail="Source page not found")


@router.post("/pages/{page_id}/restore")
async def restore_page(page_id: int, user: AdminUserDep) -> dict:
    """Clear soft-delete markers; preserves page id and enabled state."""

    del user
    result = restore_source_page(page_id)
    if result.get("page") is None and not result.get("restored"):
        raise HTTPException(status_code=404, detail="Source page not found")
    return result


@router.delete("/pages/{page_id}/permanent")
async def permanently_delete_page(page_id: int, user: AdminUserDep) -> dict:
    """Hard-delete a retired page configuration only. Preserves regulatory data."""

    try:
        result = permanently_delete_source_page(page_id, actor_id=user.id)
    except SourcePagePermanentDeleteError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if not result.get("deleted"):
        raise HTTPException(status_code=404, detail="Source page not found")
    return result


@router.post("/pages/{page_id}/crawl", response_model=CrawlTriggerResponse)
async def crawl_source_page(
    page_id: int,
    user: AdminUserDep,
) -> dict:
    del user
    try:
        payload = queue_crawl_run(page_id=page_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    run_id = int(payload["run_id"])
    try:
        dispatch_crawl_workflow(run_id=run_id, source_id=None, page_id=page_id)
    except CrawlDispatchError as exc:
        log_event(
            "crawl_workflow_dispatch_failed",
            run_id=run_id,
            page_id=page_id,
            status="queued",
            error=str(exc),
        )
        raise HTTPException(
            status_code=503,
            detail=(
                f"Crawl run {run_id} is queued but GitHub Actions dispatch failed: {exc}. "
                "The run remains queued and was not executed in the API process."
            ),
        ) from exc
    log_event(
        "crawl_workflow_dispatched",
        run_id=run_id,
        page_id=page_id,
        status="queued",
    )
    return payload


@router.post("/sources/{source_id}/crawl", response_model=CrawlTriggerResponse)
async def crawl_source(
    source_id: int,
    user: AdminUserDep,
) -> dict:
    del user
    try:
        payload = queue_crawl_run(source_id=source_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    run_id = int(payload["run_id"])
    try:
        dispatch_crawl_workflow(run_id=run_id, source_id=source_id, page_id=None)
    except CrawlDispatchError as exc:
        log_event(
            "crawl_workflow_dispatch_failed",
            run_id=run_id,
            source_id=source_id,
            status="queued",
            error=str(exc),
        )
        raise HTTPException(
            status_code=503,
            detail=(
                f"Crawl run {run_id} is queued but GitHub Actions dispatch failed: {exc}. "
                "The run remains queued and was not executed in the API process."
            ),
        ) from exc
    log_event(
        "crawl_workflow_dispatched",
        run_id=run_id,
        source_id=source_id,
        status="queued",
    )
    return payload


@router.get("/runs")
async def crawl_runs(
    user: AdminUserDep,
    q: str | None = None,
    source_code: str | None = None,
    status: str = "all",
    date_range: str = "all",
    page: PageParam = 1,
    page_size: PageSizeParam = DEFAULT_PAGE_SIZE,
) -> dict:
    """Paginated crawl-run telemetry with search plus source/status/date filters."""

    del user
    return list_crawl_runs_page(
        q=q,
        source_code=source_code,
        status=status,
        date_range=date_range,
        page=page,
        page_size=page_size,
    )


@router.get("/runs/sources")
async def crawl_run_source_options(user: AdminUserDep) -> list[dict]:
    """Source codes that appear in crawl history, for the run source filter."""

    del user
    return list_crawl_run_sources()


@router.get("/runs/{run_id}")
async def crawl_run(run_id: int, user: AdminUserDep) -> dict:
    del user
    run = get_crawl_run(run_id)
    if run:
        return run
    raise HTTPException(status_code=404, detail="Crawl run not found")


@router.get("/runs/{run_id}/pages")
async def crawl_run_pages(run_id: int, user: AdminUserDep) -> list[dict]:
    """Per-page results for one run, derived from discovery audit and run errors."""

    del user
    if not get_crawl_run(run_id):
        raise HTTPException(status_code=404, detail="Crawl run not found")
    return get_crawl_run_pages(run_id)


@router.get("/pages")
async def all_source_pages(
    user: AdminUserDep,
    include_retired: bool = False,
) -> list[dict]:
    del user
    return list_all_source_pages(include_retired=include_retired)


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
    user: RagProcessUserDep,
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
