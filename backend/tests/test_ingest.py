"""Tests for plain-text note ingestion."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.database import Database, create_database, get_db, init_db
from app.main import create_app
from app.models import ItemStatus, KnowledgeItem, SourceType
from app.schemas.knowledge_item import KnowledgeItemCreate
from app.services.ingestion import UnsupportedSourceTypeError, ingest_note

RESPONSE_FIELDS = {
    "id",
    "title",
    "content",
    "source_type",
    "source_url",
    "status",
    "created_at",
    "updated_at",
    "indexing_status",
    "indexed_chunk_count",
    "indexing_error_code",
}
NOTE_PAYLOAD: dict[str, Any] = {
    "title": "Understanding Node.js",
    "content": "Node.js is a JavaScript runtime.",
    "source_type": "NOTE",
}


def _stored_items(database: Database) -> list[KnowledgeItem]:
    with database.session_factory() as session:
        return list(session.scalars(select(KnowledgeItem).order_by(KnowledgeItem.id)).all())


# ---------------------------------------------------------------------------
# Successful ingestion
# ---------------------------------------------------------------------------


def test_ingest_note_returns_201_with_expected_response(client: TestClient) -> None:
    response = client.post("/ingest", json=NOTE_PAYLOAD)

    assert response.status_code == 201
    payload = response.json()
    assert set(payload) == RESPONSE_FIELDS
    assert payload["id"] > 0
    assert payload["title"] == "Understanding Node.js"
    assert payload["content"] == "Node.js is a JavaScript runtime."
    assert payload["source_type"] == "NOTE"
    assert payload["source_url"] is None
    assert payload["status"] == "COMPLETED"
    assert payload["indexing_status"] == "indexed"
    assert payload["indexed_chunk_count"] == 1
    assert payload["indexing_error_code"] is None
    assert isinstance(payload["created_at"], str)
    assert isinstance(payload["updated_at"], str)


def test_ingest_note_persists_to_database(client: TestClient) -> None:
    response = client.post("/ingest", json=NOTE_PAYLOAD)
    database: Database = client.app.state.database

    stored = _stored_items(database)

    assert len(stored) == 1
    assert stored[0].id == response.json()["id"]
    assert stored[0].title == NOTE_PAYLOAD["title"]
    assert stored[0].content == NOTE_PAYLOAD["content"]
    assert stored[0].source_type is SourceType.NOTE
    assert stored[0].source_url is None
    assert stored[0].status is ItemStatus.COMPLETED
    assert stored[0].created_at is not None
    assert stored[0].updated_at is not None


def test_ingest_preserves_raw_content(client: TestClient) -> None:
    raw_content = "  First line  \n\n\tSecond line — naïve café 日本語 🚀  "
    response = client.post("/ingest", json={"content": raw_content, "source_type": "NOTE"})
    database: Database = client.app.state.database

    assert response.status_code == 201
    assert response.json()["content"] == raw_content
    assert _stored_items(database)[0].content == raw_content


def test_ingest_with_optional_title_omitted(client: TestClient) -> None:
    response = client.post("/ingest", json={"content": "no title", "source_type": "NOTE"})
    database: Database = client.app.state.database

    assert response.status_code == 201
    assert response.json()["title"] is None
    assert _stored_items(database)[0].title is None


def test_independent_requests_create_independent_records(client: TestClient) -> None:
    first = client.post(
        "/ingest",
        json={"title": "First", "content": "first note", "source_type": "NOTE"},
    )
    second = client.post(
        "/ingest",
        json={"title": "Second", "content": "second note", "source_type": "NOTE"},
    )
    database: Database = client.app.state.database

    assert first.status_code == second.status_code == 201
    first_id, second_id = first.json()["id"], second.json()["id"]
    assert first_id != second_id

    stored = _stored_items(database)
    assert [item.id for item in stored] == [first_id, second_id]
    assert [item.content for item in stored] == ["first note", "second note"]


def test_ingest_is_present_in_openapi_schema(client: TestClient) -> None:
    schema = client.get("/openapi.json").json()

    assert "/ingest" in schema["paths"]
    assert "post" in schema["paths"]["/ingest"]


# ---------------------------------------------------------------------------
# Validation and rejection
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("content", ["", "   ", "\n\t\r "])
def test_ingest_rejects_empty_or_whitespace_content(client: TestClient, content: str) -> None:
    response = client.post("/ingest", json={"content": content, "source_type": "NOTE"})
    database: Database = client.app.state.database

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"
    assert _stored_items(database) == []


@pytest.mark.parametrize("source_type", ["TWEET", "note", None])
def test_ingest_rejects_invalid_source_type(client: TestClient, source_type: object) -> None:
    response = client.post("/ingest", json={"content": "x", "source_type": source_type})
    database: Database = client.app.state.database

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"
    assert _stored_items(database) == []


def test_ingest_url_requires_source_url(client: TestClient) -> None:
    # URL ingestion is now supported (see test_ingest_url.py), but a URL item
    # without a source_url is still rejected at the validation boundary.
    response = client.post(
        "/ingest",
        json={"content": "", "source_type": "URL"},
    )
    database: Database = client.app.state.database

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"
    assert _stored_items(database) == []


def test_ingest_rejects_request_without_source_type(client: TestClient) -> None:
    response = client.post("/ingest", json={"content": "x"})

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


# ---------------------------------------------------------------------------
# Service behaviour and rollback
# ---------------------------------------------------------------------------


def test_service_persists_completed_note_and_refreshes(tmp_path: Path) -> None:
    database = create_database(f"sqlite:///{tmp_path.joinpath('service.db').as_posix()}")
    init_db(database)
    try:
        payload = KnowledgeItemCreate(content="service note", source_type=SourceType.NOTE)

        with database.session_factory() as session:
            saved = ingest_note(session, payload)

        assert saved.id is not None
        assert saved.content == "service note"
        assert saved.source_type is SourceType.NOTE
        assert saved.status is ItemStatus.COMPLETED
        assert saved.created_at is not None
        assert saved.updated_at is not None
    finally:
        database.dispose()


def test_service_rejects_non_note_payload(tmp_path: Path) -> None:
    database = create_database(f"sqlite:///{tmp_path.joinpath('service-url.db').as_posix()}")
    init_db(database)
    try:
        payload = KnowledgeItemCreate(
            content="page",
            source_type=SourceType.URL,
            source_url="https://example.com",
        )

        with database.session_factory() as session:
            with pytest.raises(UnsupportedSourceTypeError):
                ingest_note(session, payload)

        assert _stored_items(database) == []
    finally:
        database.dispose()


def test_ingest_rolls_back_on_persistence_failure(tmp_path: Path) -> None:
    settings = Settings(
        database_url=f"sqlite:///{tmp_path.joinpath('rollback.db').as_posix()}",
        chroma_path=tmp_path / "chroma-rollback",
    )
    app = create_app(settings)
    database: Database = app.state.database
    commits: list[MagicMock] = []
    rollbacks: list[MagicMock] = []

    def failing_db() -> Iterator[Session]:
        session = database.session_factory()
        commit = MagicMock(side_effect=SQLAlchemyError("simulated commit failure"))
        rollback = MagicMock(wraps=session.rollback)
        session.commit = commit  # type: ignore[method-assign]
        session.rollback = rollback  # type: ignore[method-assign]
        commits.append(commit)
        rollbacks.append(rollback)
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = failing_db
    try:
        # The app's generic error handler returns a 500 response; TestClient
        # re-raises unhandled exceptions by default, so opt out here.
        with TestClient(app, raise_server_exceptions=False) as failing_client:
            response = failing_client.post("/ingest", json=NOTE_PAYLOAD)
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 500
    assert response.json() == {
        "error": {"code": "internal_error", "message": "An unexpected error occurred."}
    }
    assert len(commits) == len(rollbacks) == 1
    commits[0].assert_called_once_with()
    rollbacks[0].assert_called_once_with()
    assert _stored_items(database) == []
