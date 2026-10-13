from functools import lru_cache
from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    environment: Literal["development", "production", "test"] = "development"
    database_url: str = "postgresql+psycopg://supportdesk:supportdesk@localhost:5432/supportdesk"
    redis_url: str = "redis://localhost:6379/0"
    dashboard_origin: str = "http://localhost:3000"
    api_origin: str = "http://localhost:8000"
    model_mode: Literal["mock", "openai"] = "mock"
    model_base_url: str = "https://api.openai.com/v1"
    model_api_key: str = ""
    chat_model: str = "gpt-4o-mini"
    embedding_model: str = "text-embedding-3-small"
    embedding_dimensions: int = 1536
    provider_timeout: float = 30
    input_cost_per_million: float = 0
    output_cost_per_million: float = 0
    chunk_size: int = 1000
    chunk_overlap: int = 150
    retrieval_count: int = 4
    retrieval_max_distance: float = 0.55
    max_upload_bytes: int = 10 * 1024 * 1024
    max_document_chars: int = 500_000
    session_hours: int = 24
    visitor_hours: int = 24
    retention_days: int = 90
    daily_chat_quota: int = 1000
    storage_mode: Literal["s3", "local"] = "s3"
    s3_endpoint: str = "http://localhost:9000"
    s3_access_key: str = "supportdesk"
    s3_secret_key: str = "local-development-only"
    s3_bucket: str = "supportdesk"
    local_storage_path: str = ".local-storage"
    test_inline_jobs: bool = False
    test_memory_rate_limit: bool = False
    demo_password: str = ""

    @model_validator(mode="after")
    def validate_config(self):
        if not 0 <= self.chunk_overlap < self.chunk_size:
            raise ValueError("chunk_overlap must be smaller than chunk_size")
        if self.environment != "test" and (self.test_inline_jobs or self.test_memory_rate_limit):
            raise ValueError("Test adapters require ENVIRONMENT=test")
        if self.environment == "production":
            if not self.database_url.startswith("postgresql"):
                raise ValueError("Production requires PostgreSQL for concurrency-safe locking")
            if not self.dashboard_origin.startswith("https://") or not self.api_origin.startswith(
                "https://"
            ):
                raise ValueError("Production requires HTTPS origins")
            if self.storage_mode != "s3" or "local-development" in self.s3_secret_key:
                raise ValueError("Production requires configured object storage credentials")
        if self.model_mode == "openai" and not self.model_api_key:
            raise ValueError("MODEL_API_KEY is required in openai mode")
        return self

    @property
    def embedding_identity(self):
        return f"{self.model_mode}:{self.embedding_model}:{self.embedding_dimensions}"


@lru_cache
def settings():
    return Settings()
