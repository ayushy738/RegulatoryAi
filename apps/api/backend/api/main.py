import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api.ask_errors import AskCorrelationMiddleware
from backend.api.routes import (
    admin,
    chat,
    chat_documents,
    chat_entities,
    chat_evidence,
    chat_runs,
    chat_search,
    chat_sessions,
    digests,
    events,
    exports,
    identity_auth,
    intelligence,
    meta,
    sources,
    subscriptions,
)
from backend.core.config import settings
from backend.core.db import database_healthcheck
from backend.core.logging import configure_logging, log_event
from backend.core.repository import seed_system_documents
from backend.pipeline.crawl_recovery import reclaim_stale_crawl_runs


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # Age-gated reclaim of crawl_runs left RUNNING after process death.
    # Safe for multi-instance: only rows older than crawl_running_stale_seconds.
    try:
        result = await asyncio.to_thread(reclaim_stale_crawl_runs)
        log_event(
            "crawl_recovery_startup",
            reclaimed=result.get("reclaimed", 0),
            stale_seconds=result.get("stale_seconds"),
        )
    except Exception as exc:
        log_event(
            "crawl_recovery_startup_failed",
            error=f"{type(exc).__name__}: {exc}",
        )
    yield


configure_logging()
seed_system_documents()

app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)

app.add_middleware(AskCorrelationMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_origin_regex=settings.cors_origin_regex_value,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(digests.router)
app.include_router(events.router)
app.include_router(chat.router)
app.include_router(chat_documents.router)
app.include_router(chat_entities.router)
app.include_router(chat_search.router)
app.include_router(chat_sessions.router)
app.include_router(chat_runs.router)
app.include_router(chat_evidence.router)
app.include_router(chat_evidence.saved_items_router)
app.include_router(subscriptions.router)
app.include_router(sources.router)
app.include_router(admin.router)
app.include_router(exports.router)
app.include_router(meta.router)
app.include_router(intelligence.router)
app.include_router(identity_auth.router)


@app.get("/health")
async def health() -> dict[str, str | bool]:
    database_connected = False
    if settings.database_url:
        try:
            database_connected = await asyncio.wait_for(
                asyncio.to_thread(database_healthcheck),
                timeout=5,
            )
        except Exception:
            database_connected = False
    effective_llm_provider = (
        "parallel"
        if settings.llm_provider == "offline" and settings.parallel_api_key
        else settings.llm_provider
    )
    return {
        "status": "ok" if database_connected else "degraded",
        "database_configured": bool(settings.database_url),
        "database_connected": database_connected,
        "storage_configured": bool(settings.supabase_service_role_key),
        "llm_provider": settings.llm_provider,
        "effective_llm_provider": effective_llm_provider,
    }
