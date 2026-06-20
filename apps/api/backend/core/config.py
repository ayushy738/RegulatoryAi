from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Regulatory AI"
    environment: Literal["development", "test", "production"] = "development"

    supabase_url: str | None = None
    supabase_anon_key: str | None = None
    supabase_service_role_key: str | None = None
    database_url: str | None = None
    supabase_storage_bucket: str = "regulatory-docs"

    app_base_url: str = "http://localhost:3000"
    api_base_url: str = "http://localhost:8000"
    auth_required: bool = False
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"

    llm_provider: Literal["anthropic", "openai", "offline"] = "offline"
    anthropic_api_key: str | None = None
    openai_api_key: str | None = None
    llm_model_agent: str | None = None
    llm_model_summary: str | None = None
    llm_model_chat: str | None = None

    email_provider: Literal["resend", "postmark", "ses", "offline"] = "offline"
    email_api_key: str | None = None
    email_from: str = "Regulatory AI <updates@example.com>"

    sentry_dsn: str | None = None
    crawl_user_agent: str = Field(
        default="RegulatoryAI-bot/0.1 (+https://example.com/bot)",
        min_length=10,
    )

    model_config = SettingsConfigDict(
        env_file=(".env", "../../.env", "../../../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    def require_database(self) -> None:
        if not self.database_url:
            raise RuntimeError("DATABASE_URL is required for database-backed runtime work.")

    def require_supabase_storage(self) -> None:
        missing = [
            name
            for name, value in {
                "SUPABASE_URL": self.supabase_url,
                "SUPABASE_SERVICE_ROLE_KEY": self.supabase_service_role_key,
                "SUPABASE_STORAGE_BUCKET": self.supabase_storage_bucket,
            }.items()
            if not value
        ]
        if missing:
            raise RuntimeError(f"Missing storage settings: {', '.join(missing)}")

    def require_llm(self) -> None:
        if self.llm_provider == "anthropic" and not self.anthropic_api_key:
            raise RuntimeError("ANTHROPIC_API_KEY is required when LLM_PROVIDER=anthropic.")
        if self.llm_provider == "openai" and not self.openai_api_key:
            raise RuntimeError("OPENAI_API_KEY is required when LLM_PROVIDER=openai.")


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
