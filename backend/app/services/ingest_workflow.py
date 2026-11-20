"""Orchestration for ingest-then-index without nested database transactions.

The item is committed by the existing ingestion services first. Indexing then
runs in its own SQLAlchemy session and transaction, reusing the existing
:func:`~app.services.indexing.index_knowledge_item` service unchanged. A failed
index never rolls back the successfully saved item.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import AppError
from app.core.logging import logger
from app.models import KnowledgeItem, SourceType
from app.schemas.knowledge_item import KnowledgeItemCreate
from app.services.embeddings import Embedder
from app.services.ingestion import ingest_note, ingest_url
from app.services.indexing import index_knowledge_item
from app.services.url_fetcher import UrlFetcher
from app.services.vector_store import VectorStore

INDEXING_STATUS_INDEXED = "indexed"
INDEXING_STATUS_FAILED = "failed"
INDEXING_STATUS_UNAVAILABLE = "unavailable"
VECTOR_STORE_UNAVAILABLE_CODE = "vector_store_unavailable"
GENERIC_INDEXING_ERROR_CODE = "indexing_failed"


@dataclass(frozen=True)
class IndexingOutcome:
    """Search-index result reported alongside a successfully saved item."""

    status: str
    chunk_count: int | None = None
    error_code: str | None = None


@dataclass(frozen=True)
class IngestResult:
    """Persisted item plus the independent outcome of automatic indexing."""

    item: KnowledgeItem
    indexing: IndexingOutcome


def _index_item(
    *,
    item_id: int,
    bind: Any,
    settings: Settings | None,
    embedder: Embedder | None,
    vector_store: VectorStore | None,
) -> IndexingOutcome:
    """Index one already-committed item in an independent transaction."""

    if vector_store is None:
        logger.warning(
            "automatic_indexing_unavailable",
            extra={"item_id": item_id, "error_code": VECTOR_STORE_UNAVAILABLE_CODE},
        )
        return IndexingOutcome(
            status=INDEXING_STATUS_UNAVAILABLE,
            error_code=VECTOR_STORE_UNAVAILABLE_CODE,
        )

    try:
        # A new session is essential: ingestion has already committed the item,
        # and indexing owns its own PENDING -> INDEXED transaction.
        with Session(bind) as indexing_session:
            chunks = index_knowledge_item(
                indexing_session,
                item_id,
                settings=settings,
                embedder=embedder,
                vector_store=vector_store,
            )
            chunk_count = len(chunks)
        return IndexingOutcome(status=INDEXING_STATUS_INDEXED, chunk_count=chunk_count)
    except AppError as exc:
        logger.warning(
            "automatic_indexing_failed",
            extra={"item_id": item_id, "error_code": exc.code},
        )
        return IndexingOutcome(status=INDEXING_STATUS_FAILED, error_code=exc.code)
    except Exception as exc:  # pragma: no cover - defensive boundary
        logger.warning(
            "automatic_indexing_failed",
            extra={
                "item_id": item_id,
                "error_code": GENERIC_INDEXING_ERROR_CODE,
                "exception_type": type(exc).__name__,
            },
        )
        return IndexingOutcome(
            status=INDEXING_STATUS_FAILED,
            error_code=GENERIC_INDEXING_ERROR_CODE,
        )


def ingest_and_index(
    session: Session,
    payload: KnowledgeItemCreate,
    *,
    settings: Settings | None = None,
    embedder: Embedder | None = None,
    vector_store: VectorStore | None = None,
    fetcher: UrlFetcher | None = None,
) -> IngestResult:
    """Persist a note or URL, then attempt idempotent semantic indexing.

    Ingestion validation/fetch/persistence failures still propagate as before.
    Only indexing failures are converted into a response-status outcome because
    the item has already been durably saved at that point.
    """

    item = (
        ingest_url(session, payload, fetcher=fetcher)
        if payload.source_type is SourceType.URL
        else ingest_note(session, payload)
    )
    indexing = _index_item(
        item_id=item.id,
        bind=session.get_bind(),
        settings=settings,
        embedder=embedder,
        vector_store=vector_store,
    )
    return IngestResult(item=item, indexing=indexing)


__all__ = ["IndexingOutcome", "IngestResult", "ingest_and_index"]
