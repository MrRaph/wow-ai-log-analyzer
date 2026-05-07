"""Centralised settings, loaded from environment variables / .env."""
from __future__ import annotations

from functools import lru_cache
from typing import Annotated, Literal

from pydantic import AnyUrl, EmailStr, Field, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- General ---
    app_name: str = "WoW AI Log Analyzer"
    app_env: Literal["production", "development", "test"] = "production"
    log_level: str = "INFO"
    public_base_url: str = "http://localhost:3000"

    # --- Backend ---
    backend_host: str = "0.0.0.0"  # noqa: S104  (intentional in container)
    backend_port: int = 8000
    secret_key: str = Field(default="insecure-dev-key", min_length=16)
    jwt_algorithm: str = "HS256"
    jwt_access_ttl_minutes: int = 60
    jwt_refresh_ttl_days: int = 30
    cors_allow_origins: str = "http://localhost:3000"

    # --- Database ---
    postgres_host: str = "db"
    postgres_port: int = 5432
    postgres_db: str = "wowanalyzer"
    postgres_user: str = "wowanalyzer"
    postgres_password: str = "change-me"

    # --- Redis ---
    redis_host: str = "redis"
    redis_port: int = 6379
    redis_db: int = 0

    # --- WCL ---
    wcl_client_id: str = ""
    wcl_client_secret: str = ""
    wcl_api_url: str = "https://www.warcraftlogs.com/api/v2/client"
    wcl_oauth_token_url: str = "https://www.warcraftlogs.com/oauth/token"

    # --- AI ---
    ai_provider: Literal["anthropic", "openai", "ollama"] = "anthropic"
    anthropic_api_key: str = ""
    ai_model: str = "claude-sonnet-4-6"
    ai_max_tokens: int = 8000

    # --- SMTP ---
    smtp_host: str = "smtp.local"
    smtp_port: int = 25
    smtp_use_tls: bool = False
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from_email: EmailStr = "wowanalyzer@example.com"
    smtp_from_name: str = "WoW AI Log Analyzer"

    # --- Top-Logs daily fetcher ---
    top_logs_cron: str = "0 4 * * *"
    top_logs_limit: int = 25

    # --- Initial admin ---
    initial_admin_email: EmailStr = "admin@example.com"
    initial_admin_password: str = "changeme-at-first-login"

    # --- Feature flags ---
    allow_registration: bool = True

    # ---- derived ----
    @computed_field  # type: ignore[misc]
    @property
    def database_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @computed_field  # type: ignore[misc]
    @property
    def redis_url(self) -> str:
        return f"redis://{self.redis_host}:{self.redis_port}/{self.redis_db}"

    @computed_field  # type: ignore[misc]
    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.cors_allow_origins.split(",") if o.strip()]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
