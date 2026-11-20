"""Environment-based application configuration.

Secrets are intentionally not represented here. Settings contains only values
that are safe to hold in application state; no endpoint returns this object.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlsplit

from dotenv import load_dotenv
from pydantic import BaseModel, Field, field_validator, model_validator

load_dotenv()

_ENV_PREFIX = "MINDVAULT_"
_DEFAULT_CORS_ORIGINS = ("http://localhost:5173", "http://127.0.0.1:5173")
_VALID_LOG_LEVELS = frozenset({"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"})
_TRUE_VALUES = frozenset({"1", "true", "yes", "on"})

# backend/app/core/config.py -> backend/app/core -> app -> backend -> repository root.
PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_DATABASE_URL = "sqlite:///./storage/mindvault.db"


def _resolve_sqlite_url(value: str) -> str:
    """Anchor relative SQLite paths to the repository root.

    Uvicorn may be launched from ``backend/`` or the repository root. Without
    this, ``sqlite:///./storage/mindvault.db`` would point at two different
    files. Absolute paths and special in-memory URLs are left untouched.
    """

    parts = urlsplit(value)
    if not parts.scheme.startswith("sqlite") or parts.netloc or not parts.path.startswith("/"):
        return value

    candidate = parts.path[1:]
    if candidate in {":memory:", ""} or candidate.startswith("file:"):
        return value

    path = Path(candidate)
    if path.is_absolute():
        return value

    resolved = (PROJECT_ROOT / path).resolve()
    url = f"{parts.scheme}:///{resolved.as_posix()}"
    if parts.query:
        url += f"?{parts.query}"
    if parts.fragment:
        url += f"#{parts.fragment}"
    return url


class Settings(BaseModel):
    """Validated, environment-driven settings for the application."""

    application: str = "MindVault"
    version: str = "1.0.0"
    environment: str = "development"
    log_level: str = Field(default="INFO")
    cors_origins: tuple[str, ...] = Field(default=_DEFAULT_CORS_ORIGINS)
    docs_enabled: bool = True
    api_title: str = "MindVault API"
    api_description: str = "Foundation API for the MindVault knowledge application."
    database_url: str = Field(default=DEFAULT_DATABASE_URL, validate_default=True)
    fetch_timeout_seconds: float = Field(default=10.0, gt=0)
    fetch_max_bytes: int = Field(default=2_000_000, gt=0)
    fetch_max_redirects: int = Field(default=3, ge=0)
    # Total encoded-token budget, special tokens included. 256 matches the
    # installed MiniLM-L6-v2 model's max_seq_length.
    chunk_size_tokens: int = Field(default=256, gt=0)
    chunk_overlap_tokens: int = Field(default=60, ge=0)

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return tuple(origin.strip() for origin in value.split(",") if origin.strip())
        return value

    @field_validator("log_level", mode="before")
    @classmethod
    def _normalize_log_level(cls, value: object) -> object:
        if isinstance(value, str):
            normalized = value.strip().upper()
            if normalized not in _VALID_LOG_LEVELS:
                raise ValueError(f"log_level must be one of {sorted(_VALID_LOG_LEVELS)}")
            return normalized
        return value

    @field_validator("database_url", mode="before")
    @classmethod
    def _normalize_database_url(cls, value: object) -> object:
        if isinstance(value, str):
            return _resolve_sqlite_url(value)
        return value

    @model_validator(mode="after")
    def _validate_chunk_settings(self) -> Settings:
        # An overlap equal to (or larger than) the chunk size would never
        # advance the chunking window, so reject it at the config boundary.
        if self.chunk_overlap_tokens >= self.chunk_size_tokens:
            raise ValueError("chunk_overlap_tokens must be smaller than chunk_size_tokens")
        return self

    @classmethod
    def from_env(cls) -> Settings:
        """Build settings from ``MINDVAULT_*`` environment variables."""

        def env(name: str, default: str) -> str:
            return os.getenv(f"{_ENV_PREFIX}{name}", default)

        return cls(
            application=env("APPLICATION", "MindVault"),
            version=env("VERSION", "1.0.0"),
            environment=env("ENVIRONMENT", "development"),
            log_level=env("LOG_LEVEL", "INFO"),
            cors_origins=env("CORS_ORIGINS", ",".join(_DEFAULT_CORS_ORIGINS)),
            docs_enabled=env("DOCS_ENABLED", "true").strip().lower() in _TRUE_VALUES,
            database_url=env("DATABASE_URL", DEFAULT_DATABASE_URL),
            fetch_timeout_seconds=float(env("FETCH_TIMEOUT_SECONDS", "10.0")),
            fetch_max_bytes=int(env("FETCH_MAX_BYTES", "2000000")),
            fetch_max_redirects=int(env("FETCH_MAX_REDIRECTS", "3")),
            chunk_size_tokens=int(env("CHUNK_SIZE_TOKENS", "256")),
            chunk_overlap_tokens=int(env("CHUNK_OVERLAP_TOKENS", "60")),
        )


@lru_cache
def get_settings() -> Settings:
    """Return the cached settings instance."""

    return Settings.from_env()
