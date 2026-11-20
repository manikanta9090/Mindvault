"""Persistent ChromaDB lifecycle, configuration, and storage tests."""

from __future__ import annotations

from pathlib import Path
from typing import Iterator

import pytest
from fastapi.testclient import TestClient

from app.core.config import (
    DEFAULT_CHROMA_COLLECTION,
    DEFAULT_CHROMA_PATH,
    DEFAULT_RETRIEVAL_TOP_K,
    PROJECT_ROOT,
    Settings,
)
from app.main import create_app
from app.services.embeddings import EMBEDDING_DIMENSION
from app.services.vector_store import VectorStore

ALPHA = [1.0] + [0.0] * (EMBEDDING_DIMENSION - 1)
BETA = [0.0, 1.0] + [0.0] * (EMBEDDING_DIMENSION - 2)


def _settings(tmp_path: Path, name: str = "chroma.db") -> Settings:
    return Settings(
        database_url=f"sqlite:///{tmp_path.joinpath(name).as_posix()}",
        chroma_path=tmp_path / f"chroma-{name}",
    )


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return _settings(tmp_path, "store.db")


@pytest.fixture
def store(settings: Settings) -> Iterator[VectorStore]:
    vector_store = VectorStore(settings)
    vector_store.connect()
    try:
        yield vector_store
    finally:
        vector_store.close()


def test_chroma_settings_are_anchored_like_sqlite() -> None:
    defaults = Settings()

    assert DEFAULT_CHROMA_PATH == "./storage/chroma"
    assert DEFAULT_CHROMA_COLLECTION == "mindvault_chunks"
    assert DEFAULT_RETRIEVAL_TOP_K == 8
    assert defaults.chroma_path == PROJECT_ROOT / "storage" / "chroma"
    assert defaults.chroma_collection_name == "mindvault_chunks"
    assert defaults.retrieval_top_k == 8

    custom = Settings(chroma_path="./custom/chroma", retrieval_top_k=3)
    assert custom.chroma_path == PROJECT_ROOT / "custom" / "chroma"
    assert custom.retrieval_top_k == 3


def test_vector_store_is_initialized_by_lifespan_and_closed_on_shutdown(
    tmp_path: Path,
) -> None:
    app = create_app(_settings(tmp_path, "lifespan.db"))

    assert app.state.vector_store is None
    assert app.state.chroma_client is None
    assert app.state.chroma_collection is None

    with TestClient(app) as client:
        assert client.get("/health").status_code == 200
        active: VectorStore = app.state.vector_store
        assert active.connected
        assert active.path == _settings(tmp_path, "lifespan.db").chroma_path
        assert app.state.chroma_client is active.client
        assert app.state.chroma_collection is active.collection

        metadata = active.collection.metadata
        assert metadata["hnsw:space"] == "cosine"
        assert metadata["embedding_model"] == "sentence-transformers/all-MiniLM-L6-v2"
        assert metadata["dimension"] == EMBEDDING_DIMENSION
        assert active.path.is_dir()

    assert app.state.vector_store is None
    assert app.state.chroma_client is None
    assert app.state.chroma_collection is None
    assert not active.connected


def test_vectors_persist_across_client_restart(settings: Settings) -> None:
    first = VectorStore(settings)
    first.connect()
    first.upsert(
        ids=["persistent"],
        embeddings=[ALPHA],
        documents=["survives restart"],
        metadatas=[{"knowledge_item_id": 1}],
    )
    first.close()

    second = VectorStore(settings)
    try:
        second.connect()
        assert second.count() == 1
        hits = second.query(ALPHA, n_results=1)
        assert [hit.id for hit in hits] == ["persistent"]
        assert hits[0].text == "survives restart"
        assert hits[0].metadata["knowledge_item_id"] == 1
    finally:
        second.close()


def test_upsert_replaces_existing_id_without_duplicates(store: VectorStore) -> None:
    store.upsert(
        ids=["same-id"],
        embeddings=[ALPHA],
        documents=["old text"],
        metadatas=[{"version": 1}],
    )
    store.upsert(
        ids=["same-id"],
        embeddings=[BETA],
        documents=["new text"],
        metadatas=[{"version": 2}],
    )

    assert store.count() == 1
    hits = store.query(BETA, n_results=1)
    assert hits[0].id == "same-id"
    assert hits[0].text == "new text"
    assert hits[0].metadata["version"] == 2


def test_cleanup_only_deletes_stale_ids_for_one_item(store: VectorStore) -> None:
    store.upsert(
        ids=["keep", "stale", "other-item"],
        embeddings=[ALPHA, BETA, ALPHA],
        documents=["keep", "stale", "other"],
        metadatas=[
            {"knowledge_item_id": 1},
            {"knowledge_item_id": 1},
            {"knowledge_item_id": 2},
        ],
    )

    store.delete_stale(1, {"keep"})

    assert set(store.item_vector_ids(1)) == {"keep"}
    assert set(store.item_vector_ids(2)) == {"other-item"}
    assert store.count() == 2
