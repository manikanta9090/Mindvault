from __future__ import annotations

from collections.abc import Generator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fastapi import Request
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import get_settings


@dataclass(frozen=True)
class Database:
    """Engine and session factory belonging to one database configuration."""

    engine: Engine
    session_factory: sessionmaker[Session]

    def dispose(self) -> None:
        """Release the engine's connection pool."""

        self.engine.dispose()


def create_database(database_url: str) -> Database:
    """Build an engine and session factory for ``database_url``."""

    options: dict[str, Any] = {"pool_pre_ping": True}
    is_sqlite = database_url.startswith("sqlite")
    if is_sqlite:
        # SQLite checks the connection's creating thread by default; FastAPI
        # routes run across threads, so allow sharing within the pool.
        options["connect_args"] = {"check_same_thread": False}
        if ":memory:" in database_url:
            options["poolclass"] = StaticPool

    engine = create_engine(database_url, **options)

    if is_sqlite:

        @event.listens_for(engine, "connect")
        def _enable_sqlite_foreign_keys(dbapi_connection: Any, _: Any) -> None:
            cursor = dbapi_connection.cursor()
            try:
                cursor.execute("PRAGMA foreign_keys=ON")
            finally:
                cursor.close()

    return Database(
        engine=engine,
        session_factory=sessionmaker(bind=engine, autoflush=False, expire_on_commit=False),
    )


class Base(DeclarativeBase):
    """Declarative base that future ORM models will inherit from."""


# One engine/factory for the configured application database.
database = create_database(get_settings().database_url)
engine = database.engine
SessionLocal = database.session_factory


def _ensure_sqlite_parent(target_engine: Engine) -> None:
    """Create the parent directory so SQLite can create its database file."""

    if target_engine.url.get_backend_name() != "sqlite":
        return

    database_path = target_engine.url.database
    if not database_path or database_path == ":memory:" or database_path.startswith("file:"):
        return

    Path(database_path).parent.mkdir(parents=True, exist_ok=True)


def init_db(target: Database | None = None) -> None:
    """Explicitly create the database file and any registered model tables.

    Called from the application lifespan, not at import time. There are no
    models in this phase, so no tables are created yet.
    """

    active = target if target is not None else database
    _ensure_sqlite_parent(active.engine)

    # Importing the package registers future model modules with Base.metadata.
    import app.models  # noqa: F401

    with active.engine.begin() as connection:
        Base.metadata.create_all(bind=connection)


def get_db(request: Request) -> Generator[Session, None, None]:
    """FastAPI dependency yielding a session that is closed after the request."""

    session = request.app.state.database.session_factory()
    try:
        yield session
    finally:
        session.close()
