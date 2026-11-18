"""Environment-based application configuration.

Secrets are intentionally not represented here. Settings contains only values
that are safe to hold in application state; no endpoint returns this object.
"""

from __future__ import annotations

import os
from functools import lru_cache

from dotenv import load_dotenv
from pydantic import BaseModel, Field, field_validator

load_dotenv()

_ENV_PREFIX = "MINDVAULT_"
_DEFAULT_CORS_ORIGINS = ("http://localhost:5173", "http://127.0.0.1:5173")
_VALID_LOG_LEVELS = frozenset({"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"})
_TRUE_VALUES = frozenset({"1", "true", "yes", "on"})


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
        )


@lru_cache
def get_settings() -> Settings:
    """Return the cached settings instance."""

    return Settings.from_env()
