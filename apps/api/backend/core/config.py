from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Resolven Regulatory AI"
    environment: Literal["development", "test", "production"] = "development"

    supabase_url: str | None = None
    supabase_anon_key: str | None = None
    supabase_service_role_key: str | None = None
    database_url: str | None = None
    supabase_storage_bucket: str = "regulatory-docs"

    app_base_url: str = "http://localhost:3000"
    api_base_url: str = "http://localhost:8001"
    auth_required: bool = True
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"
    cors_origin_regex: str | None = None

    llm_provider: Literal["anthropic", "openai", "parallel", "offline"] = "offline"
    anthropic_api_key: str | None = None
    openai_api_key: str | None = None
    parallel_api_key: str | None = None
    parallel_base_url: str = "https://api.parallel.ai"
    llm_model_agent: str | None = None
    llm_model_summary: str | None = None
    llm_model_chat: str | None = None

    embedding_provider: Literal["parallel", "openai", "offline"] = "offline"
    vector_provider: Literal["supabase", "memory"] = "supabase"
    retrieval_provider: Literal["supabase"] = "supabase"
    embedding_model: str = "text-embedding-3-small"
    embedding_dimension: int = 1536
    openai_compatible_embedding_base_url: str = "https://api.openai.com/v1"
    openai_compatible_embedding_api_key: str | None = None
    rag_chunk_min_tokens: int = 600
    rag_chunk_max_tokens: int = 800
    rag_chunk_overlap_tokens: int = 120
    rag_context_token_limit: int = 6500
    rag_top_k: int = 15

    email_provider: Literal["resend", "postmark", "ses", "offline"] = "offline"
    email_api_key: str | None = None
    email_from: str = "Resolven Regulatory AI <updates@example.com>"

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

    @property
    def cors_origin_regex_value(self) -> str | None:
        if not self.cors_origin_regex:
            return None
        return self.cors_origin_regex.strip() or None

    @property
    def supabase_project_url(self) -> str | None:
        if not self.supabase_url:
            return None
        return self.supabase_url.rstrip("/").removesuffix("/rest/v1")

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
        if self.llm_provider == "parallel" and not self.parallel_api_key:
            raise RuntimeError("PARALLEL_API_KEY is required when LLM_PROVIDER=parallel.")

    def require_embedding_provider(self) -> None:
        if self.embedding_provider == "parallel" and not self.parallel_api_key:
            raise RuntimeError(
                "PARALLEL_API_KEY is required when EMBEDDING_PROVIDER=parallel."
            )
        if self.embedding_provider == "openai" and not (
            self.openai_compatible_embedding_api_key or self.openai_api_key
        ):
            raise RuntimeError(
                "OPENAI_COMPATIBLE_EMBEDDING_API_KEY or OPENAI_API_KEY is required "
                "when EMBEDDING_PROVIDER=openai."
            )


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
