"""Application settings loaded from environment / .env file."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central configuration sourced from env vars / .env."""

    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Data stores ---
    pg_url: str
    opensearch_url: str
    opensearch_ca: str | None = None
    opensearch_verify_certs: bool = True

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

    # --- Decart AI Try-On ---
    decart_api_key: str = (
        "dct_tryon-_VErErNIjtkljGhftkHyNAiJJnPHRoCLaCaDbdNXueFzaqHaOVGvmWXIsFxYuBECe"
    )
    decart_vton_model: str = "lucy-vton-3.5"
    ai_tryon_max_seconds: int = 120
    ai_tryon_allowed_origins: str = ""

    # --- App ---
    app_env: str = "development"
    log_level: str = "INFO"
    admin_api_key: str = "admin123"

    # --- Marketplace & GST Configuration ---
    category_gst_rates: dict[str, float] = {
        "fashion": 0.12,
        "electronics": 0.18,
        "mobiles": 0.18,
        "appliances": 0.18,
        "beauty": 0.18,
        "food & health": 0.05,
    }
    default_gst_rate: float = 0.18
    city_state_map: dict[str, str] = {
        "bengaluru": "Karnataka",
        "mumbai": "Maharashtra",
        "delhi": "Delhi",
        "hyderabad": "Telangana",
        "chennai": "Tamil Nadu",
    }

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
