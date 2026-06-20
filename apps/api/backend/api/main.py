from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api.routes import admin, chat, digests, events, subscriptions
from backend.core.config import settings
from backend.core.logging import configure_logging

configure_logging()

app = FastAPI(title=settings.app_name, version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(digests.router)
app.include_router(events.router)
app.include_router(chat.router)
app.include_router(subscriptions.router)
app.include_router(admin.router)


@app.get("/health")
async def health() -> dict[str, str | bool]:
    return {
        "status": "ok",
        "database_configured": bool(settings.database_url),
        "storage_configured": bool(settings.supabase_service_role_key),
        "llm_provider": settings.llm_provider,
    }
