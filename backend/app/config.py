"""Application settings loaded from environment / .env file."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central configuration sourced from env vars / .env."""

    model_config = SettingsConfigDict(
        env_file="../.env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Data stores ---
    pg_url: str
    opensearch_url: str

    # --- Kafka ---
    kafka_broker: str
    kafka_ca: str = "certs/ca.pem"
    kafka_user: str
    kafka_password: str

    # --- ML / AI ---
    embedding_model: str = (
        "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    )
    llm_fallback_enabled: bool = False

    # --- App ---
    app_env: str = "development"
    log_level: str = "INFO"

    @property
    def async_pg_url(self) -> str:
        """Return the PG URL rewritten for the asyncpg driver."""
        url = self.pg_url
        if url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql+asyncpg://", 1)
        elif url.startswith("postgresql://"):
            url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
        # asyncpg does not accept ?sslmode=require, it expects ?ssl=require
        url = url.replace("sslmode=", "ssl=")
        return url


settings = Settings()
