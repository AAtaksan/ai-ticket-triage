"""Central application settings, loaded from environment / .env.

Uses pydantic-settings so every value is typed and validated at startup.
If a required value is missing or the wrong type, the app fails fast with a
clear error instead of blowing up deep inside a request.
"""
from functools import lru_cache
from typing import Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # App
    app_name: str = "AI Ticket Triage"
    environment: str = "development"
    log_level: str = "INFO"

    # Security
    jwt_secret: str = "change-me"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60

    # Postgres
    database_url: str = "postgresql+asyncpg://triage:triage@postgres:5432/triage"

    # Redis
    redis_url: str = "redis://redis:6379/0"

    # LLM
    llm_provider: Literal["anthropic", "openai", "groq", "mock"] = "mock"
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    anthropic_model: str = "claude-haiku-4-5-20251001"
    openai_model: str = "gpt-4o-mini"
    # Groq is OpenAI-compatible (fast + free tier). Uses the openai SDK.
    groq_api_key: str = ""
    groq_model: str = "llama-3.1-8b-instant"
    groq_base_url: str = "https://api.groq.com/openai/v1"
    llm_timeout_seconds: int = 15

    # Rate limiting
    rate_limit_tickets_per_minute: int = 10

    # Worker
    max_ai_retries: int = 3

    @field_validator("database_url", mode="before")
    @classmethod
    def normalize_db_url(cls, v: str) -> str:
        """Cloud providers (Neon, Render, Supabase, Heroku) hand out URLs like
        `postgres://...` or `postgresql://...`. Our async stack needs the
        asyncpg driver, so we normalize the scheme automatically. This lets you
        paste a provider's connection string straight into DATABASE_URL."""
        if not v:
            return v
        if v.startswith("postgres://"):
            v = "postgresql://" + v[len("postgres://"):]
        if v.startswith("postgresql://"):
            v = "postgresql+asyncpg://" + v[len("postgresql://"):]
        # Some providers append ?sslmode=require which asyncpg doesn't accept as
        # a query arg; asyncpg negotiates SSL automatically, so strip it.
        if "?sslmode=" in v:
            v = v.split("?sslmode=")[0]
        return v


@lru_cache
def get_settings() -> Settings:
    """Cached so we build Settings once per process."""
    return Settings()


settings = get_settings()
