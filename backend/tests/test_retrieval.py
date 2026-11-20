"""Tests for validated semantic retrieval over persistent ChromaDB vectors."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.database import Database, create_database, init_db
from app.models import ChunkStatus, KnowledgeChunk, KnowledgeItem, ItemStatus, SourceType
from app.services.embeddings import (
    EMBEDDING_DIMENSION,
    EMBEDDING_MODEL_NAME,
)
from app.services.indexing import index_knowledge_item
from app.services.retrieval import RetrievalError, retrieve_chunks
from app.services.vector_store import VectorStore

ALPHA = [1.0] + [0.0] * (EMBEDDING_DIMENSION - 1)
BETA = [0.0, 1.0] + [0.0] * (EMBEDDING_DIMENSION - 2)
GAMMA = [0.0, 0.0, 1.0] + [0.0] * (EMBEDDING_DIMENSION - 3)
BY_TEXT = {"alpha": ALPHA, "beta": BETA, "gamma": GAMMA}


@pytest.fixture
def database(tmp_path: Path) -> Iterator[Database]:
    db_path = tmp_path / "retrieval.db"
    database = create_database(f"sqlite:///{db_path.as_posix()}")
    init_db(database)
    try:
        yield database
    finally:
        database.dispose()


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        database_url=f"sqlite:///{tmp_path.joinpath('retrieval.db').as_posix()}",
        chroma_path=tmp_path / "chroma-retrieval",
        chunk_size_tokens=4,
        chunk_overlap_tokens=1,
    )


@pytest.fixture
def store(settings: Settings) -> Iterator[VectorStore]:
    vector_store = VectorStore(settings)
    vector_store.connect()
    try:
        yield vector_store
    finally:
        vector_store.close()


class MappingEmbedder:
    """Offline embedder mapping known text to fixed, distinct vectors."""

    def __init__(self, vectors: dict[str, list[float]] | None = None) -> None:
        self.vectors = vectors or BY_TEXT
        self.calls: list[list[str]] = []

    def encode(self, texts: Any) -> list[list[float]]:
        values = list(texts)
        self.calls.append(values)
        return [self.vectors[value] for value in values]


def _add_item(
    session: Session,
    content: str,
    *,
    title: str | None,
    source_type: SourceType = SourceType.NOTE,
    source_url: str | None = None,
) -> KnowledgeItem:
    item = KnowledgeItem(
        content=content,
        title=title,
        source_type=source_type,
        source_url=source_url,
        status=ItemStatus.COMPLETED,
    )
    session.add(item)
    session.flush()
    return item


def _index_all(session: Session, settings: Settings, store: VectorStore) -> dict[str, int]:
    items = [
        _add_item(
            session,
            "alpha",
            title="Primary note",
            source_type=SourceType.URL,
            source_url="https://example.com/alpha",
        ),
        _add_item(session, "beta", title="Secondary note"),
        _add_item(session, "gamma", title="Tertiary note"),
    ]
    ids: dict[str, int] = {}
    for item in items:
        chunks = index_knowledge_item(
            session,
            item.id,
            settings=settings,
            embedder=MappingEmbedder(),
            vector_store=store,
        )
        ids[item.content] = chunks[0].id
    return ids


def test_retrieval_ranks_results_and_returns_sql_metadata(
    database: Database, settings: Settings, store: VectorStore
) -> None:
    embedder = MappingEmbedder()
    with database.session_factory() as session:
        ids = _index_all(session, settings, store)
        results = retrieve_chunks(
            session, "alpha", vector_store=store, embedder=embedder, top_k=2
        )

    assert [result.chunk_id for result in results] == [ids["alpha"], ids["beta"]]
    assert [result.text for result in results] == ["alpha", "beta"]
    assert results[0].distance == pytest.approx(0.0)
    assert results[1].distance == pytest.approx(1.0)
    assert results[0].chunk_index == 0
    assert len(results[0].content_hash) == 64
    assert results[0].chroma_id
    assert embedder.calls == [["alpha"]]

    primary = results[0].knowledge_item
    assert primary.id in ids.values()
    assert primary.title == "Primary note"
    assert primary.source_type is SourceType.URL
    assert primary.source_url == "https://example.com/alpha"
    assert primary.status is ItemStatus.COMPLETED
    assert primary.created_at <= primary.updated_at


def test_retrieval_excludes_failed_missing_and_stale_vectors(
    database: Database, settings: Settings, store: VectorStore
) -> None:
    with database.session_factory() as session:
        ids = _index_all(session, settings, store)

        failed_item = session.scalars(
            select(KnowledgeItem).where(KnowledgeItem.content == "beta")
        ).one()
        failed_item.status = ItemStatus.FAILED

        failed_chunk = session.get(KnowledgeChunk, ids["gamma"])
        assert failed_chunk is not None
        failed_chunk.status = ChunkStatus.FAILED
        session.commit()

    # An orphan vector with a perfect match must also be excluded.
    store.upsert(
        ids=["orphan-vector"],
        embeddings=[ALPHA],
        documents=["orphan text"],
        metadatas=[
            {
                "knowledge_item_id": 9999,
                "knowledge_chunk_id": 9999,
                "content_hash": "missing",
                "embedding_model": EMBEDDING_MODEL_NAME,
                "dimension": EMBEDDING_DIMENSION,
            }
        ],
    )

    with database.session_factory() as session:
        results = retrieve_chunks(
            session,
            "alpha",
            vector_store=store,
            embedder=MappingEmbedder(),
            top_k=8,
        )

    assert [result.chunk_id for result in results] == [ids["alpha"]]
    assert [result.text for result in results] == ["alpha"]


def test_retrieval_honors_default_top_k_and_rejects_empty_questions(
    database: Database, settings: Settings, store: VectorStore
) -> None:
    settings.retrieval_top_k = 1
    with database.session_factory() as session:
        _index_all(session, settings, store)
        results = retrieve_chunks(
            session, "alpha", vector_store=store, embedder=MappingEmbedder(), settings=settings
        )

        assert len(results) == 1
        assert retrieve_chunks(
            session, "   ", vector_store=store, embedder=MappingEmbedder(), settings=settings
        ) == []

        with pytest.raises(RetrievalError) as raised:
            retrieve_chunks(
                session,
                "alpha",
                vector_store=store,
                embedder=MappingEmbedder(),
                top_k=0,
                settings=settings,
            )

    assert raised.value.details == {"top_k": 0}


def test_retrieval_on_an_empty_collection_returns_no_results(
    database: Database, settings: Settings, store: VectorStore
) -> None:
    with database.session_factory() as session:
        assert retrieve_chunks(
            session, "alpha", vector_store=store, embedder=MappingEmbedder()
        ) == []
