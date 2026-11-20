"""ORM model for a chunk of a saved knowledge item.

This module defines persistence only. Chunking, embeddings, and vector storage
belong to later phases; this table records the state each chunk is in.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum

from sqlalchemy import (
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.knowledge_item import KnowledgeItem

CONTENT_HASH_MAX_LENGTH = 64
EMBEDDING_MODEL_MAX_LENGTH = 128
CHROMA_ID_MAX_LENGTH = 512
STATUS_MAX_LENGTH = 16


class ChunkStatus(StrEnum):
    """Processing lifecycle of a knowledge chunk."""

    PENDING = "PENDING"
    INDEXED = "INDEXED"
    FAILED = "FAILED"


def _utc_now() -> datetime:
    """Return the current time as a timezone-aware UTC datetime."""

    return datetime.now(timezone.utc)


class KnowledgeChunk(Base):
    """A single chunk belonging to a knowledge item."""

    __tablename__ = "knowledge_chunks"

    id: Mapped[int] = mapped_column(primary_key=True)
    knowledge_item_id: Mapped[int] = mapped_column(
        ForeignKey("knowledge_items.id", ondelete="CASCADE"),
        nullable=False,
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(CONTENT_HASH_MAX_LENGTH), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    token_count: Mapped[int] = mapped_column(Integer, nullable=False)
    embedding_model: Mapped[str | None] = mapped_column(
        String(EMBEDDING_MODEL_MAX_LENGTH),
        nullable=True,
    )
    dimension: Mapped[int | None] = mapped_column(Integer, nullable=True)
    chroma_id: Mapped[str | None] = mapped_column(String(CHROMA_ID_MAX_LENGTH), nullable=True)
    status: Mapped[ChunkStatus] = mapped_column(
        Enum(
            ChunkStatus,
            native_enum=False,
            create_constraint=True,
            length=STATUS_MAX_LENGTH,
        ),
        nullable=False,
        default=ChunkStatus.PENDING,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utc_now,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utc_now,
        onupdate=_utc_now,
    )

    knowledge_item: Mapped[KnowledgeItem] = relationship()

    __table_args__ = (
        Index("ix_knowledge_chunks_knowledge_item_id", "knowledge_item_id"),
        Index("ix_knowledge_chunks_status", "status"),
        UniqueConstraint(
            "knowledge_item_id",
            "chunk_index",
            "content_hash",
            name="uq_knowledge_chunks_item_index_hash",
        ),
    )
