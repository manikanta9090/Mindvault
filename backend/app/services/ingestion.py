"""Ingestion service for plain-text notes.

The service owns the persistence workflow; HTTP concerns stay in the route.
URL fetching and asynchronous processing belong to later milestones.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.models import ItemStatus, KnowledgeItem, SourceType
from app.schemas.knowledge_item import KnowledgeItemCreate


class UnsupportedSourceTypeError(AppError):
    """The requested source type cannot be ingested by this endpoint."""

    status_code = 400
    code = "unsupported_source_type"
    default_message = "Only NOTE items can be ingested by this endpoint."


def ingest_note(session: Session, payload: KnowledgeItemCreate) -> KnowledgeItem:
    """Persist a validated note and return the refreshed ORM object."""

    if payload.source_type is not SourceType.NOTE:
        raise UnsupportedSourceTypeError()

    item = KnowledgeItem(
        title=payload.title,
        content=payload.content,
        source_type=SourceType.NOTE,
        source_url=payload.source_url,
        status=ItemStatus.COMPLETED,
    )

    try:
        session.add(item)
        session.commit()
        session.refresh(item)
    except Exception:
        session.rollback()
        raise

    return item
