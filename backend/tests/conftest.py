"""Shared pytest fixtures."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from tests.phase44_helpers import KeywordEmbedder


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    # Every test app gets its own temporary database; the development database
    # is never touched by the test suite.
    db_path = tmp_path / "mindvault-test.db"
    settings = Settings(
        cors_origins=("http://localhost:5173",),
        database_url=f"sqlite:///{db_path.as_posix()}",
        chroma_path=tmp_path / "chroma",
    )
    app = create_app(settings)
    # Keep automatic indexing offline and deterministic for every API test.
    app.state.embedder = KeywordEmbedder()
    with TestClient(app) as test_client:
        yield test_client
