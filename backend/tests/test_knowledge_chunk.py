"""Focused ORM tests for the knowledge chunk model."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import inspect, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.database import Database, create_database, init_db
from app.models import ChunkStatus, KnowledgeChunk, KnowledgeItem, SourceType
from app.models.knowledge_chunk import (
    CHROMA_ID_MAX_LENGTH,
    CONTENT_HASH_MAX_LENGTH,
    EMBEDDING_MODEL_MAX_LENGTH,
)

PAST = datetime(2000, 1, 1, tzinfo=timezone.utc)


@pytest.fixture
def database(tmp_path: Path) -> Iterator[Database]:
    db_path = tmp_path / "knowledge-chunks.db"
    database = create_database(f"sqlite:///{db_path.as_posix()}")
    init_db(database)
    try:
        yield database
    finally:
        database.dispose()


def _as_utc(value: datetime) -> datetime:
    """Normalize SQLite's timezone-naive values to UTC for comparisons."""

    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def _item(session: Session, content: str = "parent item") -> KnowledgeItem:
    item = KnowledgeItem(content=content, source_type=SourceType.NOTE)
    session.add(item)
    session.flush()
    return item


def _chunk(
    item_id: int,
    index: int = 0,
    content: str = "chunk text",
    tokens: int = 3,
) -> KnowledgeChunk:
    return KnowledgeChunk(
        knowledge_item_id=item_id,
        chunk_index=index,
        content_hash=f"hash-{index}",
        text=content,
        token_count=tokens,
    )


def test_init_db_creates_knowledge_chunks_table(database: Database) -> None:
    inspector = inspect(database.engine)

    assert "knowledge_chunks" in inspector.get_table_names()
    assert {column["name"] for column in inspector.get_columns("knowledge_chunks")} == {
        "id",
        "knowledge_item_id",
        "chunk_index",
        "content_hash",
        "text",
        "token_count",
        "embedding_model",
        "dimension",
        "chroma_id",
        "status",
        "created_at",
        "updated_at",
    }
    columns = {column["name"]: column for column in inspector.get_columns("knowledge_chunks")}
    assert columns["id"]["primary_key"] == 1
    assert columns["knowledge_item_id"]["nullable"] is False
    assert columns["chunk_index"]["nullable"] is False
    assert columns["content_hash"]["nullable"] is False
    assert columns["text"]["nullable"] is False
    assert columns["token_count"]["nullable"] is False
    assert columns["status"]["nullable"] is False
    assert columns["created_at"]["nullable"] is False
    assert columns["updated_at"]["nullable"] is False

    assert KnowledgeChunk.__table__.c.content_hash.type.length == CONTENT_HASH_MAX_LENGTH
    assert KnowledgeChunk.__table__.c.embedding_model.type.length == EMBEDDING_MODEL_MAX_LENGTH
    assert KnowledgeChunk.__table__.c.chroma_id.type.length == CHROMA_ID_MAX_LENGTH


def test_chunk_table_does_not_duplicate_knowledge_item_fields() -> None:
    columns = set(KnowledgeChunk.__table__.c.keys())

    assert {"title", "source_type", "source_url"}.isdisjoint(columns)


@pytest.mark.parametrize(
    "field",
    ["knowledge_item_id", "chunk_index", "content_hash", "text", "token_count"],
)
def test_required_fields_reject_null(database: Database, field: str) -> None:
    with database.session_factory() as session:
        item = _item(session)
        values: dict[str, object] = {
            "knowledge_item_id": item.id,
            "chunk_index": 0,
            "content_hash": "hash",
            "text": "text",
            "token_count": 1,
        }
        values[field] = None
        session.add(KnowledgeChunk(**values))  # type: ignore[arg-type]

        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()


def test_foreign_key_targets_knowledge_items_with_cascade(database: Database) -> None:
    foreign_keys = inspect(database.engine).get_foreign_keys("knowledge_chunks")

    assert len(foreign_keys) == 1
    assert foreign_keys[0]["constrained_columns"] == ["knowledge_item_id"]
    assert foreign_keys[0]["referred_table"] == "knowledge_items"
    assert foreign_keys[0]["referred_columns"] == ["id"]
    assert foreign_keys[0]["options"]["ondelete"] == "CASCADE"


def test_chunk_exposes_relationship_to_its_knowledge_item(database: Database) -> None:
    with database.session_factory() as session:
        item = _item(session)
        chunk = _chunk(item.id)
        session.add(chunk)
        session.commit()

        assert chunk.knowledge_item is item
        assert chunk.knowledge_item.id == item.id
        assert chunk.knowledge_item.content == "parent item"


def test_deleting_item_cascades_to_chunks_via_orm(database: Database) -> None:
    with database.session_factory() as session:
        item = _item(session)
        session.add_all([_chunk(item.id, 0), _chunk(item.id, 1)])
        session.commit()
        item_id = item.id

    with database.session_factory() as session:
        session.delete(session.get(KnowledgeItem, item_id))
        session.commit()

    with database.session_factory() as session:
        assert session.get(KnowledgeItem, item_id) is None
        assert session.scalars(select(KnowledgeChunk)).all() == []


def test_deleting_item_cascades_to_chunks_via_database(database: Database) -> None:
    with database.session_factory() as session:
        item = _item(session)
        session.add_all([_chunk(item.id, 0), _chunk(item.id, 1)])
        session.commit()
        item_id = item.id

    with database.engine.begin() as connection:
        connection.execute(text("DELETE FROM knowledge_items WHERE id = :id"), {"id": item_id})

    with database.session_factory() as session:
        assert session.scalars(select(KnowledgeChunk)).all() == []


def test_chunk_status_enum_values() -> None:
    assert [status.value for status in ChunkStatus] == ["PENDING", "INDEXED", "FAILED"]
    assert all(isinstance(status, str) for status in ChunkStatus)


def test_status_defaults_to_pending(database: Database) -> None:
    with database.session_factory() as session:
        item = _item(session)
        chunk = _chunk(item.id)
        session.add(chunk)
        session.commit()
        chunk_id = chunk.id

    with database.session_factory() as session:
        assert session.get(KnowledgeChunk, chunk_id).status is ChunkStatus.PENDING


def test_explicit_statuses_round_trip(database: Database) -> None:
    with database.session_factory() as session:
        item = _item(session)
        chunks = [_chunk(item.id, 0), _chunk(item.id, 1), _chunk(item.id, 2)]
        chunks[1].status = ChunkStatus.INDEXED
        chunks[2].status = ChunkStatus.FAILED
        session.add_all(chunks)
        session.commit()

    with database.session_factory() as session:
        stored = session.scalars(select(KnowledgeChunk).order_by(KnowledgeChunk.chunk_index)).all()
        assert [chunk.status for chunk in stored] == [
            ChunkStatus.PENDING,
            ChunkStatus.INDEXED,
            ChunkStatus.FAILED,
        ]


def test_status_check_constraint_rejects_unknown_value(database: Database) -> None:
    with database.session_factory() as session:
        item = _item(session)
        item_id = item.id
        session.commit()

    with pytest.raises(IntegrityError), database.engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO knowledge_chunks "
                "(knowledge_item_id, chunk_index, content_hash, text, token_count, status, "
                "created_at, updated_at) "
                "VALUES (:item_id, 0, 'hash', 'text', 1, 'QUEUED', '2026-01-01', '2026-01-01')"
            ),
            {"item_id": item_id},
        )


def test_embedding_and_vector_fields_are_nullable(database: Database) -> None:
    with database.session_factory() as session:
        item = _item(session)
        chunk = _chunk(item.id)
        session.add(chunk)
        session.commit()
        chunk_id = chunk.id

    with database.session_factory() as session:
        stored = session.get(KnowledgeChunk, chunk_id)
        assert stored is not None
        assert stored.embedding_model is None
        assert stored.dimension is None
        assert stored.chroma_id is None


def test_embedding_and_vector_fields_can_be_populated(database: Database) -> None:
    with database.session_factory() as session:
        item = _item(session)
        chunk = _chunk(item.id)
        chunk.embedding_model = "sentence-transformers/all-MiniLM-L6-v2"
        chunk.dimension = 384
        chunk.chroma_id = "chroma-uuid-1"
        chunk.status = ChunkStatus.INDEXED
        session.add(chunk)
        session.commit()
        chunk_id = chunk.id

    with database.session_factory() as session:
        stored = session.get(KnowledgeChunk, chunk_id)
        assert stored is not None
        assert stored.embedding_model == "sentence-transformers/all-MiniLM-L6-v2"
        assert stored.dimension == 384
        assert stored.chroma_id == "chroma-uuid-1"
        assert stored.status is ChunkStatus.INDEXED


def test_indexes_and_unique_constraint_are_created(database: Database) -> None:
    inspector = inspect(database.engine)
    index_names = {index["name"] for index in inspector.get_indexes("knowledge_chunks")}

    assert {
        "ix_knowledge_chunks_knowledge_item_id",
        "ix_knowledge_chunks_status",
    } <= index_names

    unique_constraints = inspector.get_unique_constraints("knowledge_chunks")
    assert any(
        set(constraint["column_names"])
        == {"knowledge_item_id", "chunk_index", "content_hash"}
        for constraint in unique_constraints
    )


def test_duplicate_item_index_hash_is_rejected(database: Database) -> None:
    with database.session_factory() as session:
        item = _item(session)
        session.add_all([_chunk(item.id, 0), _chunk(item.id, 0)])

        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()


def test_same_index_with_different_hash_is_allowed(database: Database) -> None:
    with database.session_factory() as session:
        item = _item(session)
        first = _chunk(item.id, 0, content="original")
        second = _chunk(item.id, 0, content="revised")
        second.content_hash = "hash-revised"
        session.add_all([first, second])
        session.commit()

    with database.session_factory() as session:
        assert len(session.scalars(select(KnowledgeChunk)).all()) == 2


def test_timestamps_default_to_utc_now(database: Database) -> None:
    before = datetime.now(timezone.utc) - timedelta(seconds=1)
    with database.session_factory() as session:
        item = _item(session)
        chunk = _chunk(item.id)
        session.add(chunk)
        session.commit()
        after = datetime.now(timezone.utc) + timedelta(seconds=1)

        created, updated = chunk.created_at, chunk.updated_at
        assert created.tzinfo is timezone.utc
        assert updated.tzinfo is timezone.utc

    assert before <= _as_utc(created) <= after
    assert before <= _as_utc(updated) <= after
    assert _as_utc(created) <= _as_utc(updated)

    with database.session_factory() as session:
        stored = session.get(KnowledgeChunk, chunk.id)
        assert stored is not None
        assert _as_utc(stored.created_at) == _as_utc(created)
        assert _as_utc(stored.updated_at) == _as_utc(updated)


def test_updated_at_changes_when_chunk_is_modified(database: Database) -> None:
    with database.session_factory() as session:
        item = _item(session)
        chunk = _chunk(item.id)
        session.add(chunk)
        session.commit()
        original_created_at = _as_utc(chunk.created_at)

        chunk.updated_at = PAST
        session.commit()
        assert _as_utc(chunk.updated_at) == PAST

        before_change = datetime.now(timezone.utc) - timedelta(seconds=1)
        chunk.status = ChunkStatus.INDEXED
        session.commit()
        changed_updated_at = _as_utc(chunk.updated_at)

    assert changed_updated_at > PAST
    assert changed_updated_at >= before_change
    assert _as_utc(chunk.created_at) == original_created_at


def test_multiple_chunks_belong_to_one_knowledge_item(database: Database) -> None:
    with database.session_factory() as session:
        item = _item(session, "multi-chunk item")
        session.add_all(
            [
                _chunk(item.id, 2, "third chunk", 5),
                _chunk(item.id, 0, "first chunk", 3),
                _chunk(item.id, 1, "second chunk", 4),
            ]
        )
        session.commit()
        item_id = item.id

    with database.session_factory() as session:
        stored = session.scalars(
            select(KnowledgeChunk)
            .where(KnowledgeChunk.knowledge_item_id == item_id)
            .order_by(KnowledgeChunk.chunk_index)
        ).all()

        assert [chunk.chunk_index for chunk in stored] == [0, 1, 2]
        assert [chunk.text for chunk in stored] == ["first chunk", "second chunk", "third chunk"]
        assert [chunk.token_count for chunk in stored] == [3, 4, 5]
        assert {chunk.knowledge_item_id for chunk in stored} == {item_id}
        assert all(chunk.knowledge_item.id == item_id for chunk in stored)
