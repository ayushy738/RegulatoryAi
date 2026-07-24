import json
from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr
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
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"
    cors_origin_regex: str | None = None

    identity_jwt_signing_key: SecretStr | None = None
    identity_token_pepper: SecretStr | None = None
    identity_jwt_key_id: str = "identity-v1"
    identity_jwt_verification_keys: SecretStr = SecretStr("{}")
    identity_jwt_issuer: str = "resolven-identity"
    identity_jwt_audience: str = "resolven-api"
    identity_access_token_ttl_seconds: int = Field(default=900, ge=60, le=3600)
    identity_session_ttl_seconds: int = Field(
        default=2_592_000,
        ge=3600,
        le=7_776_000,
    )
    identity_cookie_secure: bool = False
    identity_cookie_samesite: Literal["lax", "strict", "none"] = "lax"
    identity_cookie_domain: str | None = None
    identity_trust_forwarded_for: bool = False
    identity_password_min_length: int = Field(default=12, ge=8, le=128)
    identity_password_max_length: int = Field(default=128, ge=64, le=1024)
    identity_failed_login_limit: int = Field(default=5, ge=3, le=20)
    identity_account_lock_seconds: int = Field(default=900, ge=60, le=86_400)
    identity_login_account_rate_limit: int = Field(default=10, ge=3, le=100)
    identity_login_ip_rate_limit: int = Field(default=30, ge=5, le=500)
    identity_login_rate_window_seconds: int = Field(default=900, ge=60, le=3600)
    identity_refresh_rate_limit: int = Field(default=60, ge=5, le=500)
    identity_refresh_rate_window_seconds: int = Field(default=60, ge=10, le=3600)
    identity_password_rate_limit: int = Field(default=10, ge=3, le=100)
    identity_password_rate_window_seconds: int = Field(default=900, ge=60, le=3600)
    identity_exchange_rate_limit: int = Field(default=3, ge=1, le=20)
    identity_exchange_rate_window_seconds: int = Field(default=3600, ge=60, le=86_400)

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

    @property
    def effective_identity_cookie_secure(self) -> bool:
        return self.environment == "production" or self.identity_cookie_secure

    def require_identity_token_secrets(self) -> tuple[str, str]:
        if self.identity_jwt_signing_key is None or self.identity_token_pepper is None:
            raise RuntimeError(
                "IDENTITY_JWT_SIGNING_KEY and IDENTITY_TOKEN_PEPPER are required "
                "for first-party token operations."
            )
        signing_key = self.identity_jwt_signing_key.get_secret_value()
        token_pepper = self.identity_token_pepper.get_secret_value()
        if len(signing_key.encode("utf-8")) < 32:
            raise RuntimeError("IDENTITY_JWT_SIGNING_KEY must contain at least 32 bytes.")
        if len(token_pepper.encode("utf-8")) < 32:
            raise RuntimeError("IDENTITY_TOKEN_PEPPER must contain at least 32 bytes.")
        if signing_key == token_pepper:
            raise RuntimeError(
                "IDENTITY_JWT_SIGNING_KEY and IDENTITY_TOKEN_PEPPER must be distinct."
            )
        if self.identity_cookie_samesite == "none" and not self.effective_identity_cookie_secure:
            raise RuntimeError("SameSite=None identity cookies must be Secure.")
        return signing_key, token_pepper

    def identity_jwt_key_ring(self, signing_key: str) -> dict[str, str]:
        try:
            parsed = json.loads(self.identity_jwt_verification_keys.get_secret_value())
        except json.JSONDecodeError as exc:
            raise RuntimeError("IDENTITY_JWT_VERIFICATION_KEYS must be valid JSON.") from exc
        if not isinstance(parsed, dict) or not all(
            isinstance(key_id, str) and isinstance(key, str)
            for key_id, key in parsed.items()
        ):
            raise RuntimeError(
                "IDENTITY_JWT_VERIFICATION_KEYS must be a JSON object of string keys."
            )
        key_ring = dict(parsed)
        configured_active_key = key_ring.get(self.identity_jwt_key_id)
        if configured_active_key is not None and configured_active_key != signing_key:
            raise RuntimeError(
                "The active JWT key ID has conflicting signing and verification keys."
            )
        key_ring[self.identity_jwt_key_id] = signing_key
        if any(len(key.encode("utf-8")) < 32 for key in key_ring.values()):
            raise RuntimeError("Every identity JWT verification key must contain 32 bytes.")
        return key_ring

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
