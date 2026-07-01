import asyncio

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api.routes import (
    admin,
    chat,
    digests,
    events,
    exports,
    intelligence,
    meta,
    subscriptions,
)
from backend.core.config import settings
from backend.core.db import database_healthcheck
from backend.core.logging import configure_logging
from backend.core.repository import seed_system_documents

configure_logging()
seed_system_documents()

app = FastAPI(title=settings.app_name, version="0.1.0")

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
app.include_router(subscriptions.router)
app.include_router(admin.router)
app.include_router(exports.router)
app.include_router(meta.router)
app.include_router(intelligence.router)


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
