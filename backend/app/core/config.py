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
from pydantic import BaseModel, Field, field_validator

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
        )


@lru_cache
def get_settings() -> Settings:
    """Return the cached settings instance."""

    return Settings.from_env()
