"""Tests for indexing one completed knowledge item into persisted chunks."""

from __future__ import annotations

from collections.abc import Iterator
from hashlib import sha256
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.database import Database, create_database, init_db
from app.models import ChunkStatus, KnowledgeChunk, KnowledgeItem, ItemStatus, SourceType
from app.services.embeddings import (
    EMBEDDING_DIMENSION,
    EMBEDDING_MODEL_NAME,
    EmbeddingError,
)
from app.services.indexing import (
    ItemNotCompletedError,
    ItemNotFoundError,
    index_knowledge_item,
)
from tests.fake_tokenizers import WordTokenizer


@pytest.fixture
def database(tmp_path: Path) -> Iterator[Database]:
    db_path = tmp_path / "indexing.db"
    database = create_database(f"sqlite:///{db_path.as_posix()}")
    init_db(database)
    try:
        yield database
    finally:
        database.dispose()


@pytest.fixture
def settings() -> Settings:
    return Settings(chunk_size_tokens=4, chunk_overlap_tokens=1)


class FakeEmbedder:
    """Offline embedder that records batches and returns valid vectors."""

    def __init__(
        self,
        error: Exception | None = None,
        tokenizer: Any | None = None,
        max_seq_length: int | None = None,
    ) -> None:
        self.calls: list[list[str]] = []
        self.error = error
        self.tokenizer = tokenizer
        self.max_seq_length = max_seq_length

    def encode(self, texts: Any) -> list[list[float]]:
        values = list(texts)
        self.calls.append(values)
        if self.error is not None:
            raise self.error
        return [[float(index)] + [0.0] * (EMBEDDING_DIMENSION - 1) for index in range(len(values))]


def _add_item(
    session: Session,
    content: str = "one two three four five six",
    status: ItemStatus = ItemStatus.COMPLETED,
) -> KnowledgeItem:
    item = KnowledgeItem(content=content, source_type=SourceType.NOTE, status=status)
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


# ---------------------------------------------------------------------------
# Successful persistence
# ---------------------------------------------------------------------------


def test_index_persists_chunks_with_metadata(database: Database, settings: Settings) -> None:
    embedder = FakeEmbedder()
    with database.session_factory() as session:
        item = _add_item(session)
        chunks = index_knowledge_item(session, item.id, settings=settings, embedder=embedder)
        item_id = item.id

    assert [chunk.chunk_index for chunk in chunks] == [0, 1]
    assert [chunk.text for chunk in chunks] == ["one two three four", "four five six"]
    assert [chunk.token_count for chunk in chunks] == [4, 3]
    assert all(
        chunk.content_hash == sha256(chunk.text.encode("utf-8")).hexdigest() for chunk in chunks
    )
    assert all(chunk.embedding_model == EMBEDDING_MODEL_NAME for chunk in chunks)
    assert all(chunk.dimension == EMBEDDING_DIMENSION for chunk in chunks)
    assert all(chunk.status is ChunkStatus.PENDING for chunk in chunks)
    assert all(chunk.chroma_id is None for chunk in chunks)
    assert embedder.calls == [["one two three four", "four five six"]]

    stored = _stored(database, item_id)
    assert [(row.chunk_index, row.text) for row in stored] == [
        (0, "one two three four"),
        (1, "four five six"),
    ]


def test_index_accepts_an_item_instance(database: Database, settings: Settings) -> None:
    with database.session_factory() as session:
        item = _add_item(session, "short content")
        chunks = index_knowledge_item(session, item, settings=settings, embedder=FakeEmbedder())

    assert [chunk.text for chunk in chunks] == ["short content"]


# ---------------------------------------------------------------------------
# Idempotency and replacement
# ---------------------------------------------------------------------------


def test_repeated_indexing_does_not_create_duplicates(
    database: Database, settings: Settings
) -> None:
    embedder = FakeEmbedder()
    with database.session_factory() as session:
        item = _add_item(session)
        first = index_knowledge_item(session, item.id, settings=settings, embedder=embedder)
        first_ids = [chunk.id for chunk in first]
        first_updated = [chunk.updated_at for chunk in first]

        second = index_knowledge_item(session, item.id, settings=settings, embedder=embedder)
        item_id = item.id

    assert [chunk.id for chunk in second] == first_ids
    assert [chunk.updated_at for chunk in second] == first_updated
    assert len(_stored(database, item_id)) == 2
    # An unchanged chunk set is detected before embedding, so the second pass
    # writes nothing and does not re-run the model.
    assert len(embedder.calls) == 1


def test_reindex_replaces_obsolete_chunks(database: Database, settings: Settings) -> None:
    with database.session_factory() as session:
        item = _add_item(session)
        first = index_knowledge_item(session, item.id, settings=settings, embedder=FakeEmbedder())
        old_hashes = {chunk.content_hash for chunk in first}
        item.content = "brand new content"
        session.flush()

        second = index_knowledge_item(session, item.id, settings=settings, embedder=FakeEmbedder())
        item_id = item.id

    assert [chunk.text for chunk in second] == ["brand new content"]
    assert all(chunk.content_hash not in old_hashes for chunk in second)
    stored = _stored(database, item_id)
    assert [chunk.text for chunk in stored] == ["brand new content"]
    assert len({(chunk.chunk_index, chunk.content_hash) for chunk in stored}) == len(stored)


def test_empty_content_removes_obsolete_chunks(database: Database, settings: Settings) -> None:
    with database.session_factory() as session:
        item = _add_item(session, "some words here")
        index_knowledge_item(session, item.id, settings=settings, embedder=FakeEmbedder())
        item.content = ""
        session.flush()

        assert index_knowledge_item(
            session, item.id, settings=settings, embedder=FakeEmbedder()
        ) == []
        item_id = item.id

    assert _stored(database, item_id) == []


# ---------------------------------------------------------------------------
# Validation and failure handling
# ---------------------------------------------------------------------------


def test_rejects_non_completed_item(database: Database, settings: Settings) -> None:
    with database.session_factory() as session:
        item = _add_item(session, status=ItemStatus.PROCESSING)
        with pytest.raises(ItemNotCompletedError) as raised:
            index_knowledge_item(session, item.id, settings=settings, embedder=FakeEmbedder())
        item_id = item.id

    assert raised.value.code == "invalid_item_status"
    assert raised.value.details == {"item_id": item_id, "status": "PROCESSING"}
    assert _stored(database, item_id) == []


def test_rejects_missing_item(database: Database, settings: Settings) -> None:
    with database.session_factory() as session:
        with pytest.raises(ItemNotFoundError) as raised:
            index_knowledge_item(session, 999, settings=settings, embedder=FakeEmbedder())

    assert raised.value.code == "item_not_found"


def test_commit_failure_rolls_back(database: Database, settings: Settings) -> None:
    with database.session_factory() as session:
        item = _add_item(session)
        item_id = item.id
        commit = MagicMock(side_effect=SQLAlchemyError("simulated commit failure"))
        rollback = MagicMock(wraps=session.rollback)
        session.commit = commit  # type: ignore[method-assign]
        session.rollback = rollback  # type: ignore[method-assign]

        with pytest.raises(Exception) as raised:
            index_knowledge_item(session, item_id, settings=settings, embedder=FakeEmbedder())

    assert raised.value.code == "indexing_failed"
    assert isinstance(raised.value.__cause__, SQLAlchemyError)
    commit.assert_called_once_with()
    rollback.assert_called_once_with()
    assert _stored(database, item_id) == []


def test_embedding_failure_rolls_back_without_persisting(
    database: Database, settings: Settings
) -> None:
    with database.session_factory() as session:
        item = _add_item(session)
        item_id = item.id
        rollback = MagicMock(wraps=session.rollback)
        session.rollback = rollback  # type: ignore[method-assign]

        with pytest.raises(EmbeddingError):
            index_knowledge_item(
                session,
                item_id,
                settings=settings,
                embedder=FakeEmbedder(error=RuntimeError("offline model failed")),
            )

    rollback.assert_called_once_with()
    assert _stored(database, item_id) == []


# ---------------------------------------------------------------------------
# Tokenizer integration and status preservation
# ---------------------------------------------------------------------------


def test_indexing_uses_embedder_tokenizer_and_sequence_limit(database: Database) -> None:
    tokenizer = WordTokenizer()
    settings = Settings(chunk_size_tokens=8, chunk_overlap_tokens=2)
    embedder = FakeEmbedder(tokenizer=tokenizer, max_seq_length=8)
    text = "one two three four five six seven eight"

    with database.session_factory() as session:
        item = _add_item(session, text)
        chunks = index_knowledge_item(session, item.id, settings=settings, embedder=embedder)
        item_id = item.id

    assert len(chunks) > 1
    assert all(len(tokenizer.encode(chunk.text, add_special_tokens=True)) <= 8 for chunk in chunks)
    assert [chunk.text for chunk in chunks] == [
        "one two three four five six",
        "five six seven eight",
    ]
    assert _stored(database, item_id)


def test_reindexing_unchanged_content_keeps_indexed_status(
    database: Database, settings: Settings
) -> None:
    with database.session_factory() as session:
        item = _add_item(session)
        first = index_knowledge_item(session, item.id, settings=settings, embedder=FakeEmbedder())
        item_id = item.id
        for chunk in first:
            chunk.status = ChunkStatus.INDEXED
        session.commit()
        original_ids = [chunk.id for chunk in first]

    with database.session_factory() as session:
        second = index_knowledge_item(
            session, item_id, settings=settings, embedder=FakeEmbedder()
        )

    assert [chunk.id for chunk in second] == original_ids
    assert all(chunk.status is ChunkStatus.INDEXED for chunk in second)
    stored = _stored(database, item_id)
    assert len(stored) == len(original_ids)
    assert all(chunk.status is ChunkStatus.INDEXED for chunk in stored)
