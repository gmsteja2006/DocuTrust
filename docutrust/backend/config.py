"""
DocuTrust Configuration — Environment-driven settings for the platform.
Uses pydantic for type-safe configuration with .env support.
"""

from typing import Optional

try:
    from pydantic_settings import BaseSettings, SettingsConfigDict
    from pydantic import field_validator
except ImportError:  # pragma: no cover - fallback for pydantic v1
    from pydantic import BaseSettings, validator

    SettingsConfigDict = None
    field_validator = validator


def _parse_bool(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes", "on"}:
            return True
        if normalized in {"false", "0", "no", "off"}:
            return False
        # Unknown strings can appear from debug tooling or environment.
        # Avoid startup failure by treating them as False.
        return False
    return bool(value)


class Settings(BaseSettings):
    """Application settings loaded from environment variables or .env file."""

    if SettingsConfigDict is not None:
        model_config = SettingsConfigDict(
            env_file=".env",
            env_file_encoding="utf-8",
            case_sensitive=True,
        )

    # ── Application ──
    APP_NAME: str = "DocuTrust"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = True
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    CORS_ORIGINS: list[str] = ["*"]

    @field_validator("DEBUG", mode="before")
    @classmethod
    def validate_debug(cls, value):
        return _parse_bool(value)

    # ── MongoDB ──
    MONGODB_URI: str = "mongodb://localhost:27017"
    MONGODB_DB_NAME: str = "docutrust"

    # ── LLM Configuration ──
    LLM_PROVIDER: str = "google"  # "google" or "openai"
    GOOGLE_API_KEY: Optional[str] = None
    OPENAI_API_KEY: Optional[str] = None
    LLM_MODEL: str = "gemini-1.5-flash"
    LLM_TEMPERATURE: float = 0.1
    LLM_MAX_TOKENS: int = 4096

    # ── Embedding Model ──
    EMBEDDING_MODEL: str = "all-MiniLM-L6-v2"
    EMBEDDING_DIMENSION: int = 384

    # ── Reranker / Grader ──
    RERANKER_MODEL: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"
    RELEVANCE_THRESHOLD: float = 0.5

    # ── Retrieval ──
    RETRIEVAL_TOP_K: int = 10
    RERANK_TOP_K: int = 5

    # ── Document Ingestion ──
    CHUNK_SIZE: int = 512
    CHUNK_OVERLAP: int = 64
    MAX_UPLOAD_SIZE_MB: int = 50

    # ── Web Search Fallback ──
    TAVILY_API_KEY: Optional[str] = None
    WEB_SEARCH_MAX_RESULTS: int = 3

    if SettingsConfigDict is None:
        class Config:
            env_file = ".env"
            env_file_encoding = "utf-8"
            case_sensitive = True


settings = Settings()
