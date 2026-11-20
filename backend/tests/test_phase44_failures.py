"""Failure and recovery verification for the Phase 4.4 RAG pipeline."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx2
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.config import Settings
from app.main import create_app
from app.models import ChunkStatus, KnowledgeChunk
from app.services.rag import NO_RELEVANT_INFORMATION_ANSWER
from app.services.retrieval import retrieve_chunks
from app.services.vector_store import VectorStoreError
from tests.phase44_helpers import KeywordEmbedder, index_item, settings_for
from tests.rag_helpers import FakeLLMProvider


class FailingUpsertStore:
    """Delegate to a real store but fail the first Chroma write."""

    def __init__(self, inner: Any) -> None:
        self.inner = inner
        self.upsert_calls = 0

    def upsert(self, **kwargs: Any) -> None:
        self.upsert_calls += 1
        if self.upsert_calls == 1:
            raise VectorStoreError("simulated Chroma write failure")
        self.inner.upsert(**kwargs)

    def __getattr__(self, name: str) -> Any:
        return getattr(self.inner, name)


class _FailingEmbedder:
    def encode(self, _texts: Any) -> Any:
        raise RuntimeError("simulated embedding failure")


def _seeded_app(tmp_path: Path, *, settings: Settings | None = None) -> tuple[Any, KeywordEmbedder, int]:
    embedder = KeywordEmbedder()
    app = create_app(settings or settings_for(tmp_path))
    app.state.embedder = embedder
    return app, embedder, 0


def test_embedding_failure_rolls_back_and_recovers(tmp_path: Path) -> None:
    app, embedder, _ = _seeded_app(tmp_path)

    with TestClient(app) as client:
        app.state.embedder = _FailingEmbedder()
        created = client.post(
            "/ingest",
            json={
                "title": "Node.js runtime",
                "content": "Node.js is a JavaScript runtime.",
                "source_type": "NOTE",
            },
        )
        item_id = created.json()["id"]
        assert created.json()["indexing_status"] == "failed"
        assert created.json()["indexing_error_code"] == "embedding_failed"

        with app.state.database.session_factory() as session:
            assert session.scalars(select(KnowledgeChunk)).all() == []
        assert app.state.vector_store.count() == 0

        app.state.embedder = embedder
        recovered = index_item(app, item_id, embedder)
        assert all(chunk.status is ChunkStatus.INDEXED for chunk in recovered)
        assert app.state.vector_store.count() == 1


def test_chroma_write_failure_and_retry_keep_sqlite_and_chroma_consistent(tmp_path: Path) -> None:
    app, embedder, _ = _seeded_app(tmp_path)

    with TestClient(app) as client:
        failing_store = FailingUpsertStore(app.state.vector_store)
        app.state.vector_store = failing_store
        created = client.post(
            "/ingest",
            json={
                "title": "Chroma notes",
                "content": "ChromaDB stores vectors.",
                "source_type": "NOTE",
            },
        )
        item_id = created.json()["id"]
        assert created.json()["indexing_status"] == "failed"
        assert created.json()["indexing_error_code"] == "vector_store_failed"

        with app.state.database.session_factory() as session:
            pending = session.scalars(select(KnowledgeChunk)).all()
        assert pending
        assert all(chunk.status is ChunkStatus.PENDING for chunk in pending)
        assert all(chunk.chroma_id is None for chunk in pending)
        assert failing_store.inner.count() == 0

        app.state.vector_store = failing_store.inner
        retried = index_item(app, item_id, embedder)
        assert [chunk.id for chunk in retried] == [chunk.id for chunk in pending]
        assert all(chunk.status is ChunkStatus.INDEXED for chunk in retried)
        assert app.state.vector_store.count() == 1

        with app.state.database.session_factory() as session:
            hits = retrieve_chunks(
                session,
                "Chroma",
                vector_store=app.state.vector_store,
                embedder=embedder,
                settings=app.state.settings,
            )
        assert [hit.chunk_id for hit in hits] == [chunk.id for chunk in retried]
        assert failing_store.upsert_calls == 1


def test_failed_chunks_are_never_valid_sources(tmp_path: Path) -> None:
    app, embedder, _ = _seeded_app(tmp_path)
    provider = FakeLLMProvider("Grounded answer [1].")
    app.state.llm_provider = provider

    with TestClient(app) as client:
        created = client.post(
            "/ingest",
            json={
                "title": "Node.js runtime",
                "content": "Node.js is a JavaScript runtime.",
                "source_type": "NOTE",
            },
        )
        item_id = created.json()["id"]
        index_item(app, item_id, embedder)

        assert client.post("/query", json={"question": "Node.js"}).status_code == 200
        assert len(provider.calls) == 1

        with app.state.database.session_factory() as session:
            chunk = session.scalars(select(KnowledgeChunk)).one()
            chunk.status = ChunkStatus.FAILED
            session.commit()

        blocked = client.post("/query", json={"question": "Node.js"})
        assert blocked.status_code == 200
        assert blocked.json()["answer"] == NO_RELEVANT_INFORMATION_ANSWER
        assert blocked.json()["sources"] == []
        assert len(provider.calls) == 1

        with app.state.database.session_factory() as session:
            chunk = session.scalars(select(KnowledgeChunk)).one()
            chunk.status = ChunkStatus.INDEXED
            session.commit()

        recovered = client.post("/query", json={"question": "Node.js"})
        assert recovered.status_code == 200
        assert recovered.json()["sources"][0]["item_id"] == item_id
        assert len(provider.calls) == 2


def test_missing_groq_key_fails_query_only(tmp_path: Path) -> None:
    app, embedder, _ = _seeded_app(tmp_path)
    app.state.llm_provider = None

    with TestClient(app) as client:
        assert client.get("/health").status_code == 200
        created = client.post(
            "/ingest",
            json={"title": "Node.js", "content": "Node.js is a runtime.", "source_type": "NOTE"},
        )
        assert created.status_code == 201
        assert client.get("/items").status_code == 200
        index_item(app, created.json()["id"], embedder)

        response = client.post("/query", json={"question": "Node.js?"})
        assert response.status_code == 503
        assert response.json()["error"]["code"] == "service_unavailable"
        assert "key" not in response.text.lower()


def test_provider_timeout_and_failure_map_to_upstream_error(tmp_path: Path) -> None:
    app, embedder, _ = _seeded_app(tmp_path)
    provider = FakeLLMProvider("Grounded answer [1].")
    app.state.llm_provider = provider

    with TestClient(app) as client:
        created = client.post(
            "/ingest",
            json={"title": "Node.js", "content": "Node.js is a runtime.", "source_type": "NOTE"},
        )
        index_item(app, created.json()["id"], embedder)

        provider.error = httpx2.ConnectTimeout("simulated timeout")
        timeout = client.post("/query", json={"question": "Node.js?"})
        assert timeout.status_code == 502
        assert timeout.json()["error"]["code"] == "upstream_error"
        assert "timeout" not in timeout.text.lower()

        provider.error = RuntimeError("provider exploded")
        failure = client.post("/query", json={"question": "Node.js?"})
        assert failure.status_code == 502
        assert "exploded" not in failure.text.lower()


def test_startup_and_shutdown_succeed_without_groq_credentials(tmp_path: Path) -> None:
    app = create_app(settings_for(tmp_path))

    with TestClient(app) as client:
        assert client.get("/health").status_code == 200
        assert client.get("/items").json()["total"] == 0
        assert client.post(
            "/ingest",
            json={"title": "No key", "content": "Still works.", "source_type": "NOTE"},
        ).status_code == 201

    assert app.state.vector_store is None
