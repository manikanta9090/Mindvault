"""Semantic retrieval over stored chunk vectors.

This service is intentionally independent of HTTP routes. Callers pass a
lifetime-owned :class:`~app.services.vector_store.VectorStore` and a SQL
session; results are validated against SQLite before being returned, so the
database remains the source of truth even if ChromaDB still holds an obsolete
or orphaned vector.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.errors import AppError
from app.models import ChunkStatus, KnowledgeChunk, KnowledgeItem, ItemStatus, SourceType
from app.services.embeddings import (
    EMBEDDING_DIMENSION,
    EMBEDDING_MODEL_NAME,
    Embedder,
    embed_texts,
)
from app.services.vector_store import VectorHit

if TYPE_CHECKING:  # pragma: no cover - imported only for static typing
    from app.services.vector_store import VectorStore


class RetrievalError(AppError):
    """Semantic retrieval could not be completed."""

    status_code = 500
    code = "retrieval_failed"
    default_message = "Semantic retrieval could not be completed."


@dataclass(frozen=True)
class KnowledgeItemMetadata:
    """Metadata copied from the SQL item that owns a retrieved chunk."""

    id: int
    title: str | None
    source_type: SourceType
    source_url: str | None
    status: ItemStatus
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class RetrievalResult:
    """One validated semantic hit."""

    chunk_id: int
    chunk_index: int
    content_hash: str
    chroma_id: str
    text: str
    distance: float
    knowledge_item: KnowledgeItemMetadata


def _as_int(value: Any) -> int | None:
    """Convert Chroma metadata to an integer when possible."""

    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _validate_hits(session: Session, hits: list[VectorHit]) -> list[RetrievalResult]:
    """Keep only vectors backed by an INDEXED chunk of a COMPLETED item."""

    results: list[RetrievalResult] = []
    seen: set[int] = set()

    for hit in hits:
        chunk = session.scalars(
            select(KnowledgeChunk).where(KnowledgeChunk.chroma_id == hit.id)
        ).first()
        if chunk is None or chunk.id in seen:
            continue
        if chunk.status is not ChunkStatus.INDEXED or chunk.chroma_id != hit.id:
            continue
        if chunk.embedding_model != EMBEDDING_MODEL_NAME:
            continue
        if chunk.dimension != EMBEDDING_DIMENSION:
            continue

        metadata = hit.metadata
        if _as_int(metadata.get("knowledge_item_id")) != chunk.knowledge_item_id:
            continue
        metadata_chunk_id = _as_int(metadata.get("knowledge_chunk_id"))
        if metadata_chunk_id is not None and metadata_chunk_id != chunk.id:
            continue
        if metadata.get("content_hash") != chunk.content_hash:
            continue
        if _as_int(metadata.get("dimension")) != EMBEDDING_DIMENSION:
            continue

        item = session.get(KnowledgeItem, chunk.knowledge_item_id)
        if item is None or item.status is not ItemStatus.COMPLETED:
            continue

        seen.add(chunk.id)
        results.append(
            RetrievalResult(
                chunk_id=int(chunk.id),
                chunk_index=int(chunk.chunk_index),
                content_hash=chunk.content_hash,
                chroma_id=hit.id,
                text=chunk.text,
                distance=hit.distance,
                knowledge_item=KnowledgeItemMetadata(
                    id=int(item.id),
                    title=item.title,
                    source_type=item.source_type,
                    source_url=item.source_url,
                    status=item.status,
                    created_at=item.created_at,
                    updated_at=item.updated_at,
                ),
            )
        )
    return results


def retrieve_chunks(
    session: Session,
    question: str,
    *,
    vector_store: VectorStore,
    embedder: Embedder | None = None,
    top_k: int | None = None,
    settings: Settings | None = None,
) -> list[RetrievalResult]:
    """Return up to ``top_k`` validated chunks ranked by Chroma distance.

    The question is embedded with the same MiniLM embedding service used for
    indexing. Empty questions return no results, and invalid ``top_k`` values
    raise :class:`RetrievalError` rather than querying the vector store.
    """

    if not question or not question.strip():
        return []

    active_settings = settings or get_settings()
    active_top_k = active_settings.retrieval_top_k if top_k is None else top_k
    if active_top_k <= 0:
        raise RetrievalError(
            "top_k must be greater than zero.", details={"top_k": active_top_k}
        )

    query_vector = embed_texts([question], embedder=embedder)[0]
    total = vector_store.count()
    if total == 0:
        return []

    # Over-fetch so stale vectors do not silently reduce a full result set.
    limit = min(max(active_top_k, 10), total)
    while True:
        validated = _validate_hits(session, vector_store.query(query_vector, n_results=limit))
        if len(validated) >= active_top_k or limit >= total:
            return validated[:active_top_k]
        next_limit = min(limit * 2, total)
        if next_limit <= limit:  # pragma: no cover - defensive progress guard
            return validated[:active_top_k]
        limit = next_limit


__all__ = [
    "KnowledgeItemMetadata",
    "RetrievalError",
    "RetrievalResult",
    "retrieve_chunks",
]
