"""End-to-end verification of application and database integration.

Every test in this module uses a temporary SQLite database created from
``Settings`` and passed through ``create_app``. The development database is
never opened here.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Annotated, Any
from unittest.mock import patch

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import inspect, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.database import Base, Database, get_db
from app.main import create_app
from app.models import ItemStatus, KnowledgeItem, SourceType
from app.schemas.knowledge_item import KnowledgeItemResponse

EXPECTED_COLUMNS = {
    "id",
    "title",
    "content",
    "source_type",
    "source_url",
    "status",
    "created_at",
    "updated_at",
}
EXPECTED_INDEXES = {
    "ix_knowledge_items_status",
    "ix_knowledge_items_source_type",
    "ix_knowledge_items_created_at",
    "ix_knowledge_items_status_created_at",
}


def _settings(tmp_path: Path, name: str = "integration.db") -> Settings:
    """Point an application at a throwaway SQLite file under ``tmp_path``."""

    return Settings(database_url=f"sqlite:///{tmp_path.joinpath(name).as_posix()}")


# ---------------------------------------------------------------------------
# Database integration through the application
# ---------------------------------------------------------------------------


def test_startup_initializes_database_and_creates_table(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    app = create_app(settings)

    with TestClient(app) as client:
        assert client.get("/health").status_code == 200

        engine = app.state.database.engine
        assert engine.url.get_backend_name() == "sqlite"
        assert Path(str(engine.url.database)).is_file()
        assert "knowledge_items" in inspect(engine).get_table_names()

    assert (tmp_path / "integration.db").is_file()


def test_insert_retrieve_and_serialize_through_app_database(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path))
    raw_content = "First line\n\nSecond line — naïve café ☕"

    with TestClient(app) as client:
        assert client.get("/health").status_code == 200
        database: Database = app.state.database

        with database.session_factory() as write_session:
            created = KnowledgeItem(
                title="Integration note",
                content=raw_content,
                source_type=SourceType.NOTE,
            )
            write_session.add(created)
            write_session.commit()
            item_id = created.id

        # A different session must observe the committed row.
        with database.session_factory() as read_session:
            stored = read_session.scalars(
                select(KnowledgeItem).where(KnowledgeItem.id == item_id)
            ).one()

        response = KnowledgeItemResponse.model_validate(stored)

    assert response.id == item_id
    assert response.title == "Integration note"
    assert response.content == raw_content
    assert response.source_type is SourceType.NOTE
    assert response.source_url is None
    assert response.status is ItemStatus.PROCESSING

    payload = response.model_dump(mode="json")
    assert payload["source_type"] == "NOTE"
    assert payload["status"] == "PROCESSING"
    assert "_sa_instance_state" not in payload


def test_url_item_round_trip_through_app_database(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path, "url-item.db"))
    url = "https://example.com/articles/2026/11/integration"

    with TestClient(app) as client:
        assert client.get("/health").status_code == 200
        database: Database = app.state.database

        with database.session_factory() as session:
            session.add(
                KnowledgeItem(
                    content="<p>raw markup</p>",
                    source_type=SourceType.URL,
                    source_url=url,
                    status=ItemStatus.COMPLETED,
                )
            )
            session.commit()

        with database.session_factory() as session:
            stored = session.scalars(select(KnowledgeItem)).one()
            response = KnowledgeItemResponse.model_validate(stored)

    assert response.source_type is SourceType.URL
    assert response.source_url == url
    assert response.status is ItemStatus.COMPLETED
    assert response.content == "<p>raw markup</p>"


# ---------------------------------------------------------------------------
# Application lifecycle
# ---------------------------------------------------------------------------


def test_models_are_registered_before_table_creation(tmp_path: Path) -> None:
    tables_at_creation: list[set[str]] = []
    original_create_all = Base.metadata.create_all

    def recording_create_all(bind: Engine, **kwargs: Any) -> None:
        tables_at_creation.append(set(Base.metadata.tables))
        original_create_all(bind=bind, **kwargs)

    app = create_app(_settings(tmp_path))

    with patch.object(Base.metadata, "create_all", side_effect=recording_create_all):
        with TestClient(app) as client:
            assert client.get("/health").status_code == 200

    assert tables_at_creation == [{"knowledge_items"}]

    engine = app.state.database.engine
    inspector = inspect(engine)
    assert {column["name"] for column in inspector.get_columns("knowledge_items")} == EXPECTED_COLUMNS
    assert EXPECTED_INDEXES <= {index["name"] for index in inspector.get_indexes("knowledge_items")}


def test_shutdown_disposes_engine(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path, "shutdown.db"))
    database: Database = app.state.database

    with patch.object(database.engine, "dispose", wraps=database.engine.dispose) as dispose_spy:
        with TestClient(app) as client:
            assert client.get("/health").status_code == 200
            dispose_spy.assert_not_called()

        dispose_spy.assert_called_once_with()


def test_shutdown_disposes_engine_on_abnormal_exit(tmp_path: Path) -> None:
    """A failing shutdown must not leak the engine's connection pool."""

    app = create_app(_settings(tmp_path, "abnormal-shutdown.db"))
    database: Database = app.state.database

    async def run_abnormal_lifespan() -> None:
        async with app.router.lifespan_context(app):
            raise RuntimeError("simulated shutdown failure")

    with patch.object(database.engine, "dispose", wraps=database.engine.dispose) as dispose_spy:
        with pytest.raises(RuntimeError, match="simulated shutdown failure"):
            asyncio.run(run_abnormal_lifespan())

    dispose_spy.assert_called_once_with()


def test_health_and_docs_remain_available(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path, "docs.db"))

    with TestClient(app) as client:
        assert client.get("/health").status_code == 200
        assert client.get("/docs").status_code == 200
        assert client.get("/openapi.json").status_code == 200


# ---------------------------------------------------------------------------
# get_db dependency isolation
# ---------------------------------------------------------------------------


def test_get_db_uses_each_apps_database_and_closes_sessions(tmp_path: Path) -> None:
    first_app = create_app(_settings(tmp_path, "first.db"))
    second_app = create_app(_settings(tmp_path, "second.db"))
    captured: dict[str, list[Session]] = {}
    observed_engines: dict[str, Engine] = {}

    def record_engine(label: str, session: Session) -> None:
        observed_engines[label] = session.get_bind()  # type: ignore[assignment]

    def first_probe(session: Annotated[Session, Depends(get_db)]) -> dict[str, str]:
        captured.setdefault("first", []).append(session)
        record_engine("first", session)
        session.execute(text("SELECT 1")).scalar_one()
        return {"label": "first"}

    def second_probe(session: Annotated[Session, Depends(get_db)]) -> dict[str, str]:
        captured.setdefault("second", []).append(session)
        record_engine("second", session)
        session.execute(text("SELECT 1")).scalar_one()
        return {"label": "second"}

    first_app.add_api_route("/probe-first", first_probe, methods=["GET"])
    second_app.add_api_route("/probe-second", second_probe, methods=["GET"])

    closed: list[Session] = []
    original_close = Session.close

    def tracking_close(self: Session) -> None:
        closed.append(self)
        original_close(self)

    with patch.object(Session, "close", tracking_close):
        with TestClient(first_app) as first_client, TestClient(second_app) as second_client:
            assert first_client.get("/probe-first").json() == {"label": "first"}
            assert second_client.get("/probe-second").json() == {"label": "second"}
            assert first_client.get("/probe-first").json() == {"label": "first"}
            assert second_client.get("/probe-second").json() == {"label": "second"}

    first_database: Database = first_app.state.database
    second_database: Database = second_app.state.database

    assert observed_engines["first"] is first_database.engine
    assert observed_engines["second"] is second_database.engine
    assert observed_engines["first"] is not observed_engines["second"]

    first_sessions, second_sessions = captured["first"], captured["second"]
    assert len(first_sessions) == len(second_sessions) == 2
    assert first_sessions[0] is not first_sessions[1]
    assert second_sessions[0] is not second_sessions[1]
    assert not set(first_sessions) & set(second_sessions)
    assert all(session in closed for session in [*first_sessions, *second_sessions])


def test_get_db_sessions_do_not_share_data_between_apps(tmp_path: Path) -> None:
    first_app = create_app(_settings(tmp_path, "isolated-first.db"))
    second_app = create_app(_settings(tmp_path, "isolated-second.db"))

    def add_item(session: Annotated[Session, Depends(get_db)]) -> dict[str, int]:
        item = KnowledgeItem(content="isolated", source_type=SourceType.NOTE)
        session.add(item)
        session.commit()
        return {"id": item.id}

    def count_items(session: Annotated[Session, Depends(get_db)]) -> dict[str, int]:
        return {"count": len(session.scalars(select(KnowledgeItem)).all())}

    first_app.add_api_route("/add-item", add_item, methods=["POST"])
    second_app.add_api_route("/count-items", count_items, methods=["GET"])

    with TestClient(first_app) as first_client, TestClient(second_app) as second_client:
        assert first_client.post("/add-item").status_code == 200
        assert second_client.get("/count-items").json() == {"count": 0}
        assert first_client.get("/health").status_code == 200


def test_get_db_is_used_by_a_request_scoped_dependency(tmp_path: Path) -> None:
    """The dependency yields a fresh, working session for each request."""

    app = create_app(_settings(tmp_path, "per-request.db"))
    captured: dict[int, Session] = {}

    def probe(session: Annotated[Session, Depends(get_db)]) -> dict[str, bool]:
        captured[len(captured)] = session
        return {"usable": session.execute(text("SELECT 1")).scalar_one() == 1}

    app.add_api_route("/session-probe", probe, methods=["GET"])

    with TestClient(app) as client:
        assert client.get("/session-probe").json() == {"usable": True}
        assert client.get("/session-probe").json() == {"usable": True}

    assert len(captured) == 2
    assert captured[0] is not captured[1]
    assert all(session.get_transaction() is None for session in captured.values())
