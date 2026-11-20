"""Indexing service that turns one completed item into persisted chunks.

The SQL database stores the chunk text, its SHA-256 hash, token count, and the
embedding model/dimension used for it. The vector itself is validated by the
embedding service and handed to the future vector-store phase; there is
deliberately no vector column or ChromaDB access in this phase.

Re-indexing is idempotent: when the computed chunk set matches what is already
stored, existing rows (and their statuses) are returned untouched. If the
source content or settings change, obsolete rows are replaced inside one
transaction, so a failure rolls the item back to its previous state. Chunk
boundaries come from the embedding model's own tokenizer when available, so
each chunk respects the model's sequence limit including special tokens.
"""

from __future__ import annotations

from collections.abc import Callable
from hashlib import sha256
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.errors import AppError
from app.core.logging import logger
from app.models import ChunkStatus, KnowledgeChunk, KnowledgeItem, ItemStatus
from app.services.chunking import TextChunk, chunk_text
from app.services.embeddings import (
    EMBEDDING_DIMENSION,
    EMBEDDING_MODEL_NAME,
    MINILM_MAX_SEQUENCE_LENGTH,
    Embedder,
    embed_texts,
    get_embedder,
)


class IndexingError(AppError):
    """Indexing could not be completed; the item was left unchanged."""

    status_code = 500
    code = "indexing_failed"
    default_message = "The knowledge item could not be indexed."


class ItemNotFoundError(IndexingError):
    """No knowledge item exists for the requested identifier."""

    status_code = 404
    code = "item_not_found"
    default_message = "The requested knowledge item does not exist."


class ItemNotCompletedError(IndexingError):
    """Only completed items may be indexed."""

    status_code = 409
    code = "invalid_item_status"
    default_message = "Only COMPLETED knowledge items can be indexed."


def _content_hash(text: str) -> str:
    """Return the SHA-256 hex digest of a chunk's UTF-8 text."""

    return sha256(text.encode("utf-8")).hexdigest()


def _resolve_item(session: Session, item: KnowledgeItem | int) -> KnowledgeItem:
    """Load a knowledge item from an ORM instance or an integer identifier."""

    if isinstance(item, KnowledgeItem):
        item_id = item.id
    elif isinstance(item, int):
        item_id = item
    else:
        raise TypeError("item must be a KnowledgeItem or an integer id")

    if item_id is None:
        raise ItemNotFoundError(details={"item_id": None})

    stored = session.get(KnowledgeItem, item_id)
    if stored is None:
        raise ItemNotFoundError(details={"item_id": item_id})
    return stored


def _state(records: list[KnowledgeChunk]) -> list[tuple[object, ...]]:
    """Content-based projection used to detect an unchanged chunk set.

    ``status`` is deliberately excluded: a later phase may mark chunks INDEXED,
    and re-indexing identical content must not downgrade them to PENDING.
    """

    return [
        (
            record.chunk_index,
            record.content_hash,
            record.text,
            record.token_count,
            record.embedding_model,
            record.dimension,
        )
        for record in records
    ]


def _stored_chunks(session: Session, item_id: int) -> list[KnowledgeChunk]:
    """Return an item's chunks in chunk order."""

    statement = (
        select(KnowledgeChunk)
        .where(KnowledgeChunk.knowledge_item_id == item_id)
        .order_by(KnowledgeChunk.chunk_index)
    )
    return list(session.scalars(statement).all())


def index_knowledge_item(
    session: Session,
    item: KnowledgeItem | int,
    *,
    settings: Settings | None = None,
    embedder: Embedder | None = None,
    chunker: Callable[..., list[TextChunk]] | None = None,
) -> list[KnowledgeChunk]:
    """Chunk, embed, and persist one completed knowledge item.

    ``embedder`` may be injected for offline tests; ``chunker`` is the
    :func:`~app.services.chunking.chunk_text` function by default. When the
    embedder exposes a tokenizer and a sequence limit, those are passed to the
    chunker so chunk boundaries respect the model's real tokenization. The
    returned chunks are the rows actually stored for the item, ordered by chunk
    index.
    """

    active_settings = settings or get_settings()
    active_chunker = chunker or chunk_text
    active_embedder = embedder if embedder is not None else get_embedder()
    knowledge_item = _resolve_item(session, item)

    if knowledge_item.status is not ItemStatus.COMPLETED:
        status_value = getattr(knowledge_item.status, "value", knowledge_item.status)
        raise ItemNotCompletedError(
            details={"item_id": knowledge_item.id, "status": status_value}
        )

    try:
        chunk_options: dict[str, Any] = {
            "chunk_size": active_settings.chunk_size_tokens,
            "overlap": active_settings.chunk_overlap_tokens,
        }
        if knowledge_item.content and knowledge_item.content.strip():
            # Accessing these properties loads the shared model at most once.
            tokenizer = getattr(active_embedder, "tokenizer", None)
            if tokenizer is not None:
                chunk_options["tokenizer"] = tokenizer
                max_seq_length = getattr(active_embedder, "max_seq_length", None)
                chunk_options["max_seq_length"] = (
                    max_seq_length or MINILM_MAX_SEQUENCE_LENGTH
                )

        chunks: list[TextChunk] = active_chunker(knowledge_item.content, **chunk_options)
        vectors = embed_texts([chunk.text for chunk in chunks], embedder=active_embedder)

        desired = [
            KnowledgeChunk(
                knowledge_item_id=knowledge_item.id,
                chunk_index=index,
                content_hash=_content_hash(chunk.text),
                text=chunk.text,
                token_count=chunk.token_count,
                embedding_model=EMBEDDING_MODEL_NAME,
                dimension=EMBEDDING_DIMENSION,
                status=ChunkStatus.PENDING,
            )
            for index, (chunk, _vector) in enumerate(zip(chunks, vectors))
        ]

        existing = _stored_chunks(session, knowledge_item.id)
        if _state(existing) == _state(desired):
            # Idempotent path: no writes, no new rows, no changed timestamps,
            # and existing statuses (including INDEXED) are preserved.
            return existing

        session.execute(
            delete(KnowledgeChunk).where(KnowledgeChunk.knowledge_item_id == knowledge_item.id)
        )
        if desired:
            session.add_all(desired)
        session.commit()

        return _stored_chunks(session, knowledge_item.id)
    except AppError:
        session.rollback()
        raise
    except Exception as exc:
        session.rollback()
        logger.warning(
            "knowledge_item_indexing_failed",
            extra={"item_id": knowledge_item.id, "exception_type": type(exc).__name__},
        )
        raise IndexingError(details={"item_id": knowledge_item.id}) from exc


__all__ = [
    "IndexingError",
    "ItemNotCompletedError",
    "ItemNotFoundError",
    "index_knowledge_item",
]
