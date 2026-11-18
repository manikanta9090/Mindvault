"""MindVault FastAPI application entry point."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.core.config import Settings, get_settings
from app.core.database import create_database, init_db
from app.core.errors import register_error_handlers
from app.core.logging import configure_logging, logger
from app.core.middleware import request_logging_middleware


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build a configured application instance (also used by tests)."""

    settings = settings or get_settings()
    configure_logging(settings.log_level)
    database = create_database(settings.database_url)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        init_db(database)
        logger.info(
            "database_initialized",
            extra={"backend": database.engine.url.get_backend_name()},
        )
        logger.info(
            "application_started",
            extra={"environment": settings.environment, "version": settings.version},
        )
        yield
        logger.info("application_stopped")
        database.dispose()

    docs_url = "/docs" if settings.docs_enabled else None
    app = FastAPI(
        title=settings.api_title,
        description=settings.api_description,
        version=settings.version,
        lifespan=lifespan,
        docs_url=docs_url,
        redoc_url="/redoc" if settings.docs_enabled else None,
        openapi_url="/openapi.json" if settings.docs_enabled else None,
    )

    app.state.settings = settings
    app.state.database = database
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["*"],
    )
    app.middleware("http")(request_logging_middleware)

    register_error_handlers(app)
    app.include_router(api_router)
    return app


app = create_app()
