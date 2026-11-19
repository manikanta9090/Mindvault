"""ORM model for a saved knowledge item.

This module defines persistence only. The raw content is stored verbatim;
chunking, embeddings, and any downstream processing belong to later phases.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum

from sqlalchemy import DateTime, Enum, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

TITLE_MAX_LENGTH = 512
SOURCE_URL_MAX_LENGTH = 2048
SOURCE_TYPE_MAX_LENGTH = 16
STATUS_MAX_LENGTH = 16


class SourceType(StrEnum):
    """How a knowledge item was captured."""

    NOTE = "NOTE"
    URL = "URL"


class ItemStatus(StrEnum):
    """Processing lifecycle of a knowledge item."""

    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


def _utc_now() -> datetime:
    """Return the current time as a timezone-aware UTC datetime."""

    return datetime.now(timezone.utc)


class KnowledgeItem(Base):
    """A single raw knowledge item saved by a user."""

    __tablename__ = "knowledge_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str | None] = mapped_column(String(TITLE_MAX_LENGTH), nullable=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    source_type: Mapped[SourceType] = mapped_column(
        Enum(
            SourceType,
            native_enum=False,
            create_constraint=True,
            length=SOURCE_TYPE_MAX_LENGTH,
        ),
        nullable=False,
    )
    source_url: Mapped[str | None] = mapped_column(String(SOURCE_URL_MAX_LENGTH), nullable=True)
    status: Mapped[ItemStatus] = mapped_column(
        Enum(
            ItemStatus,
            native_enum=False,
            create_constraint=True,
            length=STATUS_MAX_LENGTH,
        ),
        nullable=False,
        default=ItemStatus.PROCESSING,
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

    __table_args__ = (
        Index("ix_knowledge_items_status", "status"),
        Index("ix_knowledge_items_source_type", "source_type"),
        Index("ix_knowledge_items_created_at", "created_at"),
        Index("ix_knowledge_items_status_created_at", "status", "created_at"),
    )
