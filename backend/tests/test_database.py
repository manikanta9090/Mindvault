"""Tests for the SQLite/SQLAlchemy database foundation."""

from __future__ import annotations

from pathlib import Path

from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

from app.core.config import DEFAULT_DATABASE_URL, PROJECT_ROOT, Settings
from app.core.database import create_database, get_db, init_db


def _url(tmp_path: Path, name: str) -> str:
    db_path = tmp_path / name
    return f"sqlite:///{db_path.as_posix()}"


def test_engine_connects_to_sqlite(tmp_path: Path) -> None:
    database = create_database(_url(tmp_path, "engine.db"))
    try:
        assert database.engine.url.get_backend_name() == "sqlite"
        with database.engine.connect() as connection:
            assert connection.execute(text("SELECT 1")).scalar_one() == 1
    finally:
        database.dispose()


def test_session_can_be_created_and_closed(tmp_path: Path) -> None:
    database = create_database(_url(tmp_path, "session.db"))
    try:
        with database.session_factory() as session:
            assert session.execute(text("SELECT 1")).scalar_one() == 1
        assert session.get_transaction() is None
    finally:
        database.dispose()


def test_init_db_creates_database_file_and_registered_tables(tmp_path: Path) -> None:
    db_path = tmp_path / "nested" / "mindvault.db"
    database = create_database(f"sqlite:///{db_path.as_posix()}")
    try:
        assert not db_path.exists()
        init_db(database)
        assert db_path.is_file()
        assert "knowledge_items" in inspect(database.engine).get_table_names()

        # Initialization is safe to repeat.
        init_db(database)
        assert "knowledge_items" in inspect(database.engine).get_table_names()
    finally:
        database.dispose()


def test_get_db_dependency_closes_session_after_request(tmp_path: Path) -> None:
    database = create_database(_url(tmp_path, "dependency.db"))
    init_db(database)
    captured: list[Session] = []

    app = FastAPI()
    app.state.database = database

    @app.get("/session-probe")
    def session_probe(session: Session = Depends(get_db)) -> dict[str, int]:
        captured.append(session)
        return {"result": session.execute(text("SELECT 1")).scalar_one()}

    try:
        with TestClient(app) as test_client:
            response = test_client.get("/session-probe")

        assert response.status_code == 200
        assert response.json() == {"result": 1}
        assert len(captured) == 1
        assert captured[0].get_transaction() is None
    finally:
        database.dispose()


def test_relative_sqlite_url_is_anchored_to_project_root() -> None:
    settings = Settings()
    expected = f"sqlite:///{(PROJECT_ROOT / 'storage' / 'mindvault.db').as_posix()}"

    assert DEFAULT_DATABASE_URL == "sqlite:///./storage/mindvault.db"
    assert settings.database_url == expected
