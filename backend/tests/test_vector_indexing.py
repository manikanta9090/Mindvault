"""Tests for SQLite-backed vector indexing into persistent ChromaDB storage."""

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
from app.services.embeddings import EMBEDDING_DIMENSION
from app.services.indexing import index_knowledge_item
from app.services.vector_store import (
    VectorStore,
    VectorStoreError,
    stable_chroma_id,
)


@pytest.fixture
def database(tmp_path: Path) -> Iterator[Database]:
    db_path = tmp_path / "vector-indexing.db"
    database = create_database(f"sqlite:///{db_path.as_posix()}")
    init_db(database)
    try:
        yield database
    finally:
        database.dispose()


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        database_url=f"sqlite:///{tmp_path.joinpath('vector-indexing.db').as_posix()}",
        chroma_path=tmp_path / "chroma-vector-indexing",
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


class IndexedEmbedder:
    """Offline embedder returning distinct, valid vectors per batch position."""

    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def encode(self, texts: Any) -> list[list[float]]:
        values = list(texts)
        self.calls.append(values)
        return [
            [float(index + 1)] + [0.0] * (EMBEDDING_DIMENSION - 1)
            for index in range(len(values))
        ]


class FailingUpsertStore:
    """Delegate to a real store but fail the first vector write."""

    def __init__(self, inner: VectorStore) -> None:
        self.inner = inner
        self.upsert_calls = 0

    def upsert(self, **kwargs: Any) -> None:
        self.upsert_calls += 1
        if self.upsert_calls == 1:
            raise VectorStoreError("simulated partial failure")
        self.inner.upsert(**kwargs)

    def __getattr__(self, name: str) -> Any:
        return getattr(self.inner, name)


def _add_item(
    session: Session,
    content: str = "one two three four five six",
    *,
    title: str | None = "Indexed note",
    source_type: SourceType = SourceType.NOTE,
    source_url: str | None = None,
    status: ItemStatus = ItemStatus.COMPLETED,
) -> KnowledgeItem:
    item = KnowledgeItem(
        content=content,
        title=title,
        source_type=source_type,
        source_url=source_url,
        status=status,
    )
    session.add(item)
    session.flush()
    return item


def _stored(database: Database, item_id: int) -> list[KnowledgeChunk]:
    with database.session_factory() as session:
        return list(
            session.scalars(
                select(KnowledgeChunk)
                .where(KnowledgeChunk.knowledge_item_id == item_id)
                .order_by(KnowledgeChunk.chunk_index)
            ).all()
        )


def test_indexing_stores_vectors_and_marks_chunks_indexed(
    database: Database, settings: Settings, store: VectorStore
) -> None:
    embedder = IndexedEmbedder()
    with database.session_factory() as session:
        item = _add_item(session)
        chunks = index_knowledge_item(
            session, item.id, settings=settings, embedder=embedder, vector_store=store
        )
        item_id = item.id

    assert [chunk.text for chunk in chunks] == ["one two three four", "four five six"]
    assert all(chunk.status is ChunkStatus.INDEXED for chunk in chunks)
    assert [chunk.chroma_id for chunk in chunks] == [
        stable_chroma_id(item_id, index, chunk.content_hash)
        for index, chunk in enumerate(chunks)
    ]
    assert embedder.calls == [["one two three four", "four five six"]]
    assert store.count() == 2

    records = store.collection.get(
        ids=[chunk.chroma_id for chunk in chunks],
        include=["documents", "metadatas"],
    )
    assert records["documents"] == ["one two three four", "four five six"]
    assert records["metadatas"][0]["knowledge_item_id"] == item_id
    assert records["metadatas"][0]["knowledge_chunk_id"] == chunks[0].id
    assert records["metadatas"][0]["chunk_index"] == 0
    assert records["metadatas"][0]["content_hash"] == chunks[0].content_hash
    assert records["metadatas"][0]["title"] == "Indexed note"
    assert records["metadatas"][0]["source_type"] == "NOTE"
    assert records["metadatas"][0]["item_status"] == "COMPLETED"
    assert records["metadatas"][0]["dimension"] == EMBEDDING_DIMENSION

    stored = _stored(database, item_id)
    assert all(row.status is ChunkStatus.INDEXED for row in stored)
    assert [row.chroma_id for row in stored] == [chunk.chroma_id for chunk in chunks]


def test_repeated_vector_indexing_is_idempotent(
    database: Database, settings: Settings, store: VectorStore
) -> None:
    embedder = IndexedEmbedder()
    with database.session_factory() as session:
        item = _add_item(session)
        first = index_knowledge_item(
            session, item.id, settings=settings, embedder=embedder, vector_store=store
        )
        original_ids = [chunk.id for chunk in first]
        original_chroma_ids = [chunk.chroma_id for chunk in first]
        original_updated = [chunk.updated_at for chunk in first]
        item_id = item.id

        second = index_knowledge_item(
            session, item_id, settings=settings, embedder=embedder, vector_store=store
        )

    assert [chunk.id for chunk in second] == original_ids
    assert [chunk.chroma_id for chunk in second] == original_chroma_ids
    assert [chunk.updated_at for chunk in second] == original_updated
    assert all(chunk.status is ChunkStatus.INDEXED for chunk in second)
    assert store.count() == 2
    # Unchanged content is neither re-embedded nor re-upserted into Chroma.
    assert embedder.calls == [["one two three four", "four five six"]]


def test_changed_content_replaces_vectors_and_removes_stale_ids(
    database: Database, settings: Settings, store: VectorStore
) -> None:
    with database.session_factory() as session:
        item = _add_item(session)
        first = index_knowledge_item(
            session, item.id, settings=settings, embedder=IndexedEmbedder(), vector_store=store
        )
        old_ids = [chunk.chroma_id for chunk in first]
        item.content = "brand new content"
        session.flush()

        second = index_knowledge_item(
            session, item.id, settings=settings, embedder=IndexedEmbedder(), vector_store=store
        )
        item_id = item.id

    assert [chunk.text for chunk in second] == ["brand new content"]
    assert all(chunk.status is ChunkStatus.INDEXED for chunk in second)
    assert store.count() == 1
    assert set(store.collection.get(include=[])["ids"]) != set(old_ids)
    assert store.collection.get(include=[])["ids"] == [second[0].chroma_id]
    assert [row.text for row in _stored(database, item_id)] == ["brand new content"]


def test_failed_vector_write_keeps_chunks_pending_and_retry_has_no_duplicates(
    database: Database, settings: Settings, store: VectorStore
) -> None:
    failing = FailingUpsertStore(store)
    with database.session_factory() as session:
        item = _add_item(session)
        with pytest.raises(VectorStoreError):
            index_knowledge_item(
                session, item.id, settings=settings, embedder=IndexedEmbedder(), vector_store=failing
            )
        item_id = item.id

    pending = _stored(database, item_id)
    assert len(pending) == 2
    assert all(chunk.status is ChunkStatus.PENDING for chunk in pending)
    assert all(chunk.chroma_id is None for chunk in pending)
    assert store.count() == 0

    with database.session_factory() as session:
        retried = index_knowledge_item(
            session, item_id, settings=settings, embedder=IndexedEmbedder(), vector_store=store
        )

    assert failing.upsert_calls == 1
    assert all(chunk.status is ChunkStatus.INDEXED for chunk in retried)
    assert [chunk.id for chunk in retried] == [chunk.id for chunk in pending]
    assert store.count() == 2
    assert set(store.collection.get(include=[])["ids"]) == {
        chunk.chroma_id for chunk in retried
    }


def test_pending_chunks_are_completed_without_rewriting_sql(
    database: Database, settings: Settings, store: VectorStore
) -> None:
    with database.session_factory() as session:
        item = _add_item(session)
        chunks = index_knowledge_item(
            session, item.id, settings=settings, embedder=IndexedEmbedder()
        )
        original_ids = [chunk.id for chunk in chunks]
        item_id = item.id

    with database.session_factory() as session:
        completed = index_knowledge_item(
            session, item_id, settings=settings, embedder=IndexedEmbedder(), vector_store=store
        )

    assert [chunk.id for chunk in completed] == original_ids
    assert all(chunk.status is ChunkStatus.INDEXED for chunk in completed)
    assert store.count() == 2
