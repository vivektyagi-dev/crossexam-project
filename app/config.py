"""Central configuration. Every setting can be overridden with an environment variable
of the same name (case-insensitive), e.g. DATABASE_URL, LLM_PROVIDER."""

from __future__ import annotations

import json
from decimal import Decimal
from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # --- environment -------------------------------------------------------
    env: Literal["local", "test", "gcp"] = "local"
    service_name: str = "crossexam"
    log_level: str = "INFO"

    # --- infrastructure ------------------------------------------------------
    database_url: str = "postgresql+psycopg://crossexam:crossexam@localhost:5432/crossexam"
    redis_url: str = "redis://localhost:6379/0"
    enable_pgvector: bool = True
    embedding_dim: int = 768

    storage_backend: Literal["local", "gcs"] = "local"
    local_storage_dir: str = "./data/storage"
    gcs_bucket: str = ""

    api_url: str = "http://localhost:8000"  # where the web screen forwards /api

    # --- LLM -----------------------------------------------------------------
    llm_provider: Literal["gemini", "vertex", "openai", "fake"] = "gemini"
    google_api_key: str = ""
    openai_api_key: str = ""
    gcp_project: str = ""
    gcp_location: str = "us-central1"

    # Model tiers. Check https://ai.google.dev/models for current IDs before you rely on them.
    model_small: str = "gemini-3.5-flash-lite"
    model_mid: str = "gemini-3.8-flash"
    model_strong: str = "gemini-3.8-flash"
    model_fallback: str = "gemini-3.1-flash-lite"
    model_vision: str = "gemini-3.8-flash"
    embedding_model: str = "gemini-embedding-001"

    # USD per 1M tokens: {"model": [input, output]}. Placeholder values - set from current pricing.
    model_prices_json: str = Field(
        default='{"default": [0.10, 0.40]}',
        description="JSON map of model -> [input_usd_per_mtok, output_usd_per_mtok]",
    )
    llm_requests_per_minute: int = 60  # shared across ALL workers (Redis token bucket)
    llm_temperature: float | None = None  # None = the model's own default (newer Gemini models fix it)

    # Agent guard rails
    max_model_calls_per_run: int = 12
    max_tool_calls_per_run: int = 20
    confidence_threshold: float = 0.80
    supervisor_for_clean_packs: bool = False  # clean packs take the free deterministic path

    # --- business rules ------------------------------------------------------
    default_price_tolerance_pct: Decimal = Decimal("2.0")
    default_qty_tolerance_pct: Decimal = Decimal("0.0")
    eway_value_tolerance_pct: Decimal = Decimal("1.0")
    min_shelf_life_days: int = 180
    duplicate_date_window_days: int = 7
    manager_approval_threshold_inr: Decimal = Decimal("500000")

    # --- pipeline ------------------------------------------------------------
    prompt_version: str = "v3"
    schema_version: str = "v2"
    claim_lease_seconds: int = 900
    max_pages_per_document: int = 60

    # --- observability ------------------------------------------------------
    otel_exporter: Literal["none", "console", "otlp", "gcp"] = "none"
    metrics_exporter: Literal["none", "prometheus", "gcp"] = "prometheus"
    metrics_port: int = 9100

    # On Cloud Run the password arrives from Secret Manager as its own variable, so the URL
    # is assembled here instead of storing a password inside DATABASE_URL.
    db_host: str = ""
    db_name: str = "crossexam"
    db_user: str = "crossexam"
    db_password: str = ""

    def model_post_init(self, __context) -> None:
        if self.db_host:
            from urllib.parse import quote

            self.database_url = (f"postgresql+psycopg://{quote(self.db_user)}:{quote(self.db_password)}"
                                 f"@{self.db_host}:5432/{self.db_name}?sslmode=require")

    @property
    def model_prices(self) -> dict[str, tuple[float, float]]:
        raw = json.loads(self.model_prices_json)
        return {k: (float(v[0]), float(v[1])) for k, v in raw.items()}

    @property
    def sync_database_url(self) -> str:
        return self.database_url

    @property
    def psycopg_dsn(self) -> str:
        """Plain libpq DSN for the LangGraph Postgres checkpointer."""
        return self.database_url.replace("postgresql+psycopg://", "postgresql://")


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
