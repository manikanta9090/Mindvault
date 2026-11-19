"""Focused ORM tests for the knowledge item model."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import inspect, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.database import Database, create_database, init_db
from app.models import ItemStatus, KnowledgeItem, SourceType
from app.models.knowledge_item import SOURCE_URL_MAX_LENGTH, TITLE_MAX_LENGTH

PAST = datetime(2000, 1, 1, tzinfo=timezone.utc)


@pytest.fixture
def database(tmp_path: Path) -> Iterator[Database]:
    db_path = tmp_path / "knowledge-items.db"
    database = create_database(f"sqlite:///{db_path.as_posix()}")
    init_db(database)
    try:
        yield database
    finally:
        database.dispose()


def _as_utc(value: datetime) -> datetime:
    """Normalize SQLite's timezone-naive values to UTC for comparisons."""

    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def test_init_db_creates_knowledge_items_table(database: Database) -> None:
    inspector = inspect(database.engine)

    assert "knowledge_items" in inspector.get_table_names()
    assert {column["name"] for column in inspector.get_columns("knowledge_items")} == {
        "id",
        "title",
        "content",
        "source_type",
        "source_url",
        "status",
        "created_at",
        "updated_at",
    }
    assert {index["name"] for index in inspector.get_indexes("knowledge_items")} >= {
        "ix_knowledge_items_status",
        "ix_knowledge_items_source_type",
        "ix_knowledge_items_created_at",
        "ix_knowledge_items_status_created_at",
    }
    assert KnowledgeItem.__table__.c.title.type.length == TITLE_MAX_LENGTH
    assert KnowledgeItem.__table__.c.source_url.type.length == SOURCE_URL_MAX_LENGTH


def test_insert_note_item(database: Database) -> None:
    raw_content = "First line\n\nSecond line — naïve café ☕"
    with database.session_factory() as session:
        item = KnowledgeItem(
            title="Meeting notes",
            content=raw_content,
            source_type=SourceType.NOTE,
        )
        session.add(item)
        session.commit()
        item_id = item.id

    with database.session_factory() as session:
        stored = session.get(KnowledgeItem, item_id)

        assert stored is not None
        assert stored.title == "Meeting notes"
        assert stored.content == raw_content
        assert stored.source_type is SourceType.NOTE
        assert stored.source_url is None
        assert stored.status is ItemStatus.PROCESSING


def test_insert_url_item(database: Database) -> None:
    url = "https://example.com/articles/2026/11/a-very-long-path-segment?query=value"
    with database.session_factory() as session:
        item = KnowledgeItem(
            title="Article",
            content="<article>Raw markup is preserved.</article>",
            source_type=SourceType.URL,
            source_url=url,
        )
        session.add(item)
        session.commit()
        item_id = item.id

    with database.session_factory() as session:
        stored = session.get(KnowledgeItem, item_id)

        assert stored is not None
        assert stored.source_type is SourceType.URL
        assert stored.source_url == url
        assert stored.content == "<article>Raw markup is preserved.</article>"


def test_content_is_stored_unchanged(database: Database) -> None:
    raw_content = "  leading and trailing  \n\ttabbed line\t\nUnicode: 日本語 🚀"
    with database.session_factory() as session:
        session.add(KnowledgeItem(content=raw_content, source_type=SourceType.NOTE))
        session.commit()

    with database.session_factory() as session:
        stored = session.scalars(select(KnowledgeItem)).one()

        assert stored.content == raw_content


def test_timestamps_default_to_utc_now(database: Database) -> None:
    before = datetime.now(timezone.utc) - timedelta(seconds=1)
    with database.session_factory() as session:
        item = KnowledgeItem(content="timestamps", source_type=SourceType.NOTE)
        session.add(item)
        session.commit()
        after = datetime.now(timezone.utc) + timedelta(seconds=1)

        created, updated = item.created_at, item.updated_at

        # Python-side defaults are timezone-aware UTC before SQLite strips tzinfo.
        assert created.tzinfo is timezone.utc
        assert updated.tzinfo is timezone.utc

    assert before <= _as_utc(created) <= after
    assert before <= _as_utc(updated) <= after
    assert _as_utc(created) <= _as_utc(updated)

    with database.session_factory() as session:
        stored = session.get(KnowledgeItem, item.id)
        assert stored is not None
        assert _as_utc(stored.created_at) == _as_utc(created)
        assert _as_utc(stored.updated_at) == _as_utc(updated)


def test_status_and_source_type_persist(database: Database) -> None:
    values = [
        (SourceType.NOTE, ItemStatus.PROCESSING),
        (SourceType.NOTE, ItemStatus.COMPLETED),
        (SourceType.URL, ItemStatus.FAILED),
    ]
    with database.session_factory() as session:
        for source_type, status in values:
            session.add(
                KnowledgeItem(
                    content=f"{source_type.value}/{status.value}",
                    source_type=source_type,
                    status=status,
                    source_url="https://example.com" if source_type is SourceType.URL else None,
                )
            )
        session.commit()

    with database.session_factory() as session:
        stored = session.scalars(select(KnowledgeItem).order_by(KnowledgeItem.id)).all()

        assert [(item.source_type, item.status) for item in stored] == values
        assert [item.source_url for item in stored] == [None, None, "https://example.com"]


def test_optional_fields_are_nullable(database: Database) -> None:
    with database.session_factory() as session:
        session.add(
            KnowledgeItem(
                content="no title and no url",
                source_type=SourceType.NOTE,
                title=None,
                source_url=None,
            )
        )
        session.commit()

    with database.session_factory() as session:
        stored = session.scalars(select(KnowledgeItem)).one()

        assert stored.title is None
        assert stored.source_url is None


def test_required_fields_reject_null(database: Database) -> None:
    with database.session_factory() as session:
        session.add(KnowledgeItem(content=None, source_type=SourceType.NOTE))  # type: ignore[arg-type]
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()

    with database.session_factory() as session:
        assert session.scalars(select(KnowledgeItem)).all() == []


def test_enum_check_constraints_reject_unknown_values(database: Database) -> None:
    with pytest.raises(IntegrityError), database.engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO knowledge_items "
                "(content, source_type, status, created_at, updated_at) "
                "VALUES ('raw', 'TWEET', 'PROCESSING', '2026-01-01', '2026-01-01')"
            )
        )


def test_updated_at_changes_when_record_is_modified(database: Database) -> None:
    with database.session_factory() as session:
        item = KnowledgeItem(content="original", source_type=SourceType.NOTE)
        session.add(item)
        session.commit()
        original_created_at = _as_utc(item.created_at)

        # Backdate explicitly so the onupdate change is unambiguous.
        item.updated_at = PAST
        session.commit()
        assert _as_utc(item.updated_at) == PAST

        before_change = datetime.now(timezone.utc) - timedelta(seconds=1)
        item.title = "changed"
        session.commit()
        changed_updated_at = _as_utc(item.updated_at)

    assert changed_updated_at > PAST
    assert changed_updated_at >= before_change
    assert _as_utc(item.created_at) == original_created_at

    with database.session_factory() as session:
        stored = session.get(KnowledgeItem, item.id)
        assert stored is not None
        assert stored.title == "changed"
        assert _as_utc(stored.updated_at) == changed_updated_at
