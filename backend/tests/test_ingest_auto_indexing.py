"""Phase 4.5A tests for automatic indexing during note and URL ingestion."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.main import create_app
from app.models import ChunkStatus, KnowledgeChunk, KnowledgeItem
from app.services.indexing import index_knowledge_item
from app.services.vector_store import VectorStoreError
from tests.phase44_helpers import (
    FakeUrlFetcher,
    KeywordEmbedder,
    settings_for,
)
from tests.rag_helpers import FakeLLMProvider


class FailingEmbedder:
    """Embedder that fails encoding to exercise safe ingestion recovery."""

    def encode(self, _texts: Any) -> list[list[float]]:
        raise RuntimeError("simulated embedding failure")


class FailingUpsertStore:
    """Delegate to the real store but fail its first vector write."""

    def __init__(self, inner: Any) -> None:
        self.inner = inner
        self.upsert_calls = 0

    def upsert(self, **kwargs: Any) -> None:
        self.upsert_calls += 1
        if self.upsert_calls == 1:
            raise VectorStoreError("simulated ChromaDB write failure")
        self.inner.upsert(**kwargs)

    def __getattr__(self, name: str) -> Any:
        return getattr(self.inner, name)


def _stored_items(app: Any) -> list[KnowledgeItem]:
    with app.state.database.session_factory() as session:
        return list(session.scalars(select(KnowledgeItem)).all())


def _stored_chunks(app: Any) -> list[KnowledgeChunk]:
    with app.state.database.session_factory() as session:
        return list(session.scalars(select(KnowledgeChunk)).all())


def test_note_ingestion_automatically_indexes_and_enables_query(tmp_path: Path) -> None:
    embedder = KeywordEmbedder()
    provider = FakeLLMProvider("Node.js is a runtime [1].")
    app = create_app(settings_for(tmp_path))
    app.state.embedder = embedder
    app.state.llm_provider = provider

    with TestClient(app) as client:
        response = client.post(
            "/ingest",
            json={
                "title": "Node.js runtime",
                "content": "Node.js is a JavaScript runtime.",
                "source_type": "NOTE",
            },
        )

        assert response.status_code == 201
        payload = response.json()
        assert payload["status"] == "COMPLETED"
        assert payload["indexing_status"] == "indexed"
        assert payload["indexed_chunk_count"] == 1
        assert payload["indexing_error_code"] is None

        chunks = _stored_chunks(app)
        assert len(chunks) == 1
        assert chunks[0].status is ChunkStatus.INDEXED
        assert chunks[0].chroma_id
        assert app.state.vector_store.count() == 1

        query = client.post("/query", json={"question": "What did I save about Node.js?"})
        assert query.status_code == 200
        answer = query.json()
        assert answer["answer"] == "Node.js is a runtime [1]."
        assert len(answer["sources"]) == 1
        assert answer["sources"][0]["item_id"] == payload["id"]
        assert answer["sources"][0]["citation_id"] == "[1]"


def test_url_ingestion_automatically_indexes_with_original_metadata(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("app.services.ingestion.UrlFetcher", FakeUrlFetcher)
    embedder = KeywordEmbedder()
    app = create_app(settings_for(tmp_path))
    app.state.embedder = embedder
    app.state.llm_provider = FakeLLMProvider("ChromaDB is persistent [1].")
    source_url = "https://example.com/chroma"

    with TestClient(app) as client:
        response = client.post(
            "/ingest",
            json={
                "title": "Client title is ignored for URL extraction",
                "content": "ignored",
                "source_type": "URL",
                "source_url": source_url,
            },
        )

        assert response.status_code == 201
        payload = response.json()
        assert payload["source_type"] == "URL"
        assert payload["source_url"] == source_url
        assert payload["indexing_status"] == "indexed"
        assert payload["indexed_chunk_count"] == 1
        assert app.state.vector_store.count() == 1

        query = client.post("/query", json={"question": "What did I save about ChromaDB?"})
        assert query.status_code == 200
        source = query.json()["sources"][0]
        assert source["item_id"] == payload["id"]
        assert source["source_type"] == "URL"
        assert source["source_url"] == source_url
        assert source["citation_id"] == "[1]"


def test_embedding_failure_preserves_item_and_reports_indexing_failure(tmp_path: Path) -> None:
    app = create_app(settings_for(tmp_path))
    app.state.embedder = FailingEmbedder()

    with TestClient(app) as client:
        response = client.post(
            "/ingest",
            json={
                "title": "Node.js runtime",
                "content": "Node.js is a JavaScript runtime.",
                "source_type": "NOTE",
            },
        )
        vector_count = app.state.vector_store.count()

    assert response.status_code == 201
    payload = response.json()
    assert payload["status"] == "COMPLETED"
    assert payload["indexing_status"] == "failed"
    assert payload["indexing_error_code"] == "embedding_failed"
    assert payload["indexed_chunk_count"] is None

    items = _stored_items(app)
    assert len(items) == 1
    assert items[0].id == payload["id"]
    assert items[0].content == "Node.js is a JavaScript runtime."
    assert _stored_chunks(app) == []
    assert vector_count == 0


def test_chromadb_failure_preserves_item_and_pending_chunks(tmp_path: Path) -> None:
    app = create_app(settings_for(tmp_path))
    app.state.embedder = KeywordEmbedder()

    with TestClient(app) as client:
        failing_store = FailingUpsertStore(app.state.vector_store)
        app.state.vector_store = failing_store
        response = client.post(
            "/ingest",
            json={
                "title": "Chroma notes",
                "content": "ChromaDB stores vectors.",
                "source_type": "NOTE",
            },
        )

        assert response.status_code == 201
        payload = response.json()
        assert payload["indexing_status"] == "failed"
        assert payload["indexing_error_code"] == "vector_store_failed"
        assert response.json()["status"] == "COMPLETED"

        items = _stored_items(app)
        assert len(items) == 1
        assert items[0].id == payload["id"]

        chunks = _stored_chunks(app)
        assert len(chunks) == 1
        assert chunks[0].status is ChunkStatus.PENDING
        assert chunks[0].chroma_id is None
        assert failing_store.upsert_calls == 1
        assert failing_store.inner.count() == 0

        query = client.post("/query", json={"question": "ChromaDB"})
        assert query.status_code == 200
        assert query.json()["sources"] == []


def test_chromadb_failure_retry_is_idempotent(tmp_path: Path) -> None:
    app = create_app(settings_for(tmp_path))
    embedder = KeywordEmbedder()
    app.state.embedder = embedder

    with TestClient(app) as client:
        real_store = app.state.vector_store
        app.state.vector_store = FailingUpsertStore(real_store)
        first = client.post(
            "/ingest",
            json={
                "title": "Chroma notes",
                "content": "ChromaDB stores vectors.",
                "source_type": "NOTE",
            },
        )
        assert first.json()["indexing_status"] == "failed"
        item_id = first.json()["id"]

        # Retry the existing idempotent indexing service against the recovered
        # store. This is the same path automatic ingestion used.
        app.state.vector_store = real_store
        with app.state.database.session_factory() as session:
            chunks = index_knowledge_item(
                session,
                item_id,
                settings=app.state.settings,
                embedder=embedder,
                vector_store=real_store,
            )

        assert len(chunks) == 1
        assert all(chunk.status is ChunkStatus.INDEXED for chunk in chunks)
        assert _stored_chunks(app)[0].id == chunks[0].id
        assert real_store.count() == 1

        with app.state.database.session_factory() as session:
            repeated = index_knowledge_item(
                session,
                item_id,
                settings=app.state.settings,
                embedder=embedder,
                vector_store=real_store,
            )

        assert [chunk.id for chunk in repeated] == [chunk.id for chunk in chunks]
        assert all(chunk.chroma_id for chunk in repeated)
        assert len(_stored_chunks(app)) == 1
        assert real_store.count() == 1


def test_missing_vector_store_preserves_item_without_crashing(tmp_path: Path) -> None:
    app = create_app(settings_for(tmp_path))
    app.state.embedder = KeywordEmbedder()

    with TestClient(app) as client:
        app.state.vector_store = None
        response = client.post(
            "/ingest",
            json={
                "title": "No vector store",
                "content": "Node.js is a runtime.",
                "source_type": "NOTE",
            },
        )

        assert response.status_code == 201
        payload = response.json()
        assert payload["status"] == "COMPLETED"
        assert payload["indexing_status"] == "unavailable"
        assert payload["indexing_error_code"] == "vector_store_unavailable"
        assert payload["indexed_chunk_count"] is None
        assert len(_stored_items(app)) == 1
        assert _stored_chunks(app) == []
