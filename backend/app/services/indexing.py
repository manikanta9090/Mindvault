"""Indexing service that turns one completed item into persisted chunks.

The SQL database remains the source of truth: it stores each chunk's text,
SHA-256 hash, token count, and embedding metadata. When a vector store is
supplied, the same chunks are upserted into ChromaDB by stable ID, and only
then are their SQL rows moved to ``INDEXED`` with their ``chroma_id`` recorded.
Without a vector store, chunk rows remain ``PENDING`` as in Phase 4.1.

Re-indexing is idempotent. Unchanged content does not rewrite SQL rows,
regenerate embeddings, or downgrade existing ``INDEXED`` statuses; it only
completes vector storage for rows that are still pending. Changed content is
replaced in one SQL transaction, and stale vectors are cleaned up after the
new vectors are stored safely.
"""

from __future__ import annotations

from collections.abc import Callable
from hashlib import sha256
from typing import TYPE_CHECKING, Any

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
from app.services.vector_store import VectorStoreError, stable_chroma_id

if TYPE_CHECKING:  # pragma: no cover - imported only for static typing
    from app.services.vector_store import VectorStore


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

    ``status`` and ``chroma_id`` are deliberately excluded: vector storage is a
    later step, and re-indexing identical content must not downgrade or renumber
    chunks that were already indexed.
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


def _metadata(item: KnowledgeItem, chunk: KnowledgeChunk) -> dict[str, Any]:
    """Build Chroma metadata, omitting no-value fields Chroma cannot store."""

    source_type = getattr(item.source_type, "value", item.source_type)
    item_status = getattr(item.status, "value", item.status)
    return {
        "knowledge_item_id": int(item.id),
        "knowledge_chunk_id": int(chunk.id),
        "chunk_index": int(chunk.chunk_index),
        "content_hash": chunk.content_hash,
        "embedding_model": chunk.embedding_model or EMBEDDING_MODEL_NAME,
        "dimension": int(chunk.dimension or EMBEDDING_DIMENSION),
        "title": item.title or "",
        "source_type": str(source_type),
        "source_url": item.source_url or "",
        "item_status": str(item_status),
    }


def _pending_records(
    records: list[KnowledgeChunk],
) -> list[tuple[int, KnowledgeChunk]]:
    """Return indexed positions of rows that still need vector storage."""

    return [
        (index, record)
        for index, record in enumerate(records)
        if record.status is not ChunkStatus.INDEXED or not record.chroma_id
    ]


def _cleanup_stale(
    vector_store: VectorStore,
    item: KnowledgeItem,
    keep_ids: set[str],
) -> None:
    """Best-effort removal of superseded vectors; retrieval also guards them."""

    try:
        vector_store.delete_stale(int(item.id), keep_ids)
    except VectorStoreError as exc:
        logger.warning(
            "stale_vector_cleanup_failed",
            extra={"item_id": item.id, "exception_type": type(exc).__name__},
        )


def _persist_vectors(
    session: Session,
    item: KnowledgeItem,
    records: list[KnowledgeChunk],
    vector_store: VectorStore,
    embedder: Embedder | None,
    vectors: list[list[float]] | None,
) -> list[KnowledgeChunk]:
    """Upsert pending chunks, then mark them INDEXED in SQLite."""

    pending = _pending_records(records)
    keep_ids = {
        record.chroma_id
        for record in records
        if record.status is ChunkStatus.INDEXED and record.chroma_id
    }

    if not pending:
        _cleanup_stale(vector_store, item, keep_ids)
        return records

    if vectors is not None:
        if len(vectors) != len(records):
            raise IndexingError(details={"item_id": item.id})
        selected_vectors = [vectors[index] for index, _ in pending]
    else:
        selected_vectors = embed_texts(
            [record.text for _, record in pending], embedder=embedder
        )

    pending_records = [record for _, record in pending]
    ids = [
        stable_chroma_id(int(item.id), record.chunk_index, record.content_hash)
        for record in pending_records
    ]
    vector_store.upsert(
        ids=ids,
        embeddings=selected_vectors,
        documents=[record.text for record in pending_records],
        metadatas=[_metadata(item, record) for record in pending_records],
    )

    # SQL is updated only after Chroma accepted every vector. A later SQL
    # failure leaves rows PENDING; a retry upserts the same stable IDs.
    for record, vector_id in zip(pending_records, ids):
        record.chroma_id = vector_id
        record.status = ChunkStatus.INDEXED
    session.commit()

    keep_ids.update(ids)
    _cleanup_stale(vector_store, item, keep_ids)
    return records


def index_knowledge_item(
    session: Session,
    item: KnowledgeItem | int,
    *,
    settings: Settings | None = None,
    embedder: Embedder | None = None,
    chunker: Callable[..., list[TextChunk]] | None = None,
    vector_store: VectorStore | None = None,
) -> list[KnowledgeChunk]:
    """Chunk, embed, and persist one completed knowledge item.

    ``embedder`` may be injected for offline tests; ``chunker`` is the
    :func:`~app.services.chunking.chunk_text` function by default. When the
    embedder exposes a tokenizer and a sequence limit, those are passed to the
    chunker so chunk boundaries respect the model's real tokenization.

    Passing ``vector_store`` enables Phase 4.2 persistence: vectors are stored
    in ChromaDB and the corresponding SQL rows are marked ``INDEXED``. Without
    it, this retains the Phase 4.1 behavior of only persisting chunk rows.
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

    vectors: list[list[float]] | None = None
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
            for index, chunk in enumerate(chunks)
        ]

        existing = _stored_chunks(session, knowledge_item.id)
        if _state(existing) == _state(desired):
            # No SQL writes and no new embeddings for unchanged content.
            records = existing
        else:
            vectors = embed_texts([chunk.text for chunk in chunks], embedder=active_embedder)
            session.execute(
                delete(KnowledgeChunk).where(
                    KnowledgeChunk.knowledge_item_id == knowledge_item.id
                )
            )
            if desired:
                session.add_all(desired)
            session.commit()
            records = _stored_chunks(session, knowledge_item.id)

        if vector_store is not None:
            records = _persist_vectors(
                session,
                knowledge_item,
                records,
                vector_store,
                active_embedder,
                vectors,
            )
        return records
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
