"""Persistent ChromaDB lifecycle and collection access.

The Chroma client is deliberately constructed only from the application
lifespan, via :func:`connect_vector_store`. Importing this module never opens a
database, creates a directory, or imports ``chromadb`` itself. The small
wrapper exposes only the operations the indexing and retrieval services need,
which also keeps those services easy to test with in-memory fakes.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request

from app.core.config import Settings, get_settings
from app.core.errors import AppError
from app.core.logging import logger
from app.services.embeddings import EMBEDDING_DIMENSION, EMBEDDING_MODEL_NAME

CHROMA_DISTANCE = "cosine"


class VectorStoreError(AppError):
    """A ChromaDB operation could not be completed."""

    status_code = 500
    code = "vector_store_failed"
    default_message = "The vector store could not complete the operation."


class VectorStoreUnavailableError(VectorStoreError):
    """No initialized vector store is available for this application."""

    status_code = 503
    code = "vector_store_unavailable"
    default_message = "The vector store is not available."


@dataclass(frozen=True)
class VectorHit:
    """One normalized result from a Chroma similarity query."""

    id: str
    text: str
    distance: float
    metadata: dict[str, Any]


def stable_chroma_id(item_id: int, chunk_index: int, content_hash: str) -> str:
    """Return a deterministic vector ID for one immutable chunk revision."""

    return f"knowledge_chunk_{item_id}_{chunk_index}_{content_hash}"


def _first_result_list(value: Any) -> list[Any]:
    """Normalize Chroma's nested ``[ [ ... ] ]`` query payloads."""

    if isinstance(value, (list, tuple)) and value:
        first = value[0]
        if isinstance(first, (list, tuple)):
            return list(first)
    if isinstance(value, (list, tuple)):
        return list(value)
    return []


def _safe_close(client: Any) -> None:
    """Close a Chroma client without masking the original startup error."""

    close = getattr(client, "close", None)
    if close is None:
        return
    try:
        close()
    except Exception as exc:  # pragma: no cover - defensive shutdown cleanup
        logger.warning(
            "chroma_client_close_failed",
            extra={"exception_type": type(exc).__name__},
        )


class VectorStore:
    """Own a lazy Chroma client and one cosine-distance collection."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.path = Path(self.settings.chroma_path)
        self.collection_name = self.settings.chroma_collection_name
        self.client: Any | None = None
        self.collection: Any | None = None

    @property
    def connected(self) -> bool:
        return self.collection is not None

    def connect(self) -> None:
        """Open (or create) the persistent store; safe to call repeatedly."""

        if self.connected:
            return

        client: Any | None = None
        try:
            # Import here so module import never touches ChromaDB.
            from chromadb import PersistentClient

            self.path.mkdir(parents=True, exist_ok=True)
            client = PersistentClient(path=str(self.path))
            collection = client.get_or_create_collection(
                name=self.collection_name,
                metadata={
                    "hnsw:space": CHROMA_DISTANCE,
                    "embedding_model": EMBEDDING_MODEL_NAME,
                    "dimension": EMBEDDING_DIMENSION,
                },
            )
        except Exception as exc:
            _safe_close(client)
            raise VectorStoreError("The ChromaDB collection could not be opened.") from exc

        self.client = client
        self.collection = collection

    def close(self) -> None:
        """Release the Chroma client; errors here must not break shutdown."""

        client, self.client, self.collection = self.client, None, None
        if client is not None:
            _safe_close(client)

    def _require_collection(self) -> Any:
        if self.collection is None:
            raise VectorStoreUnavailableError()
        return self.collection

    def count(self) -> int:
        collection = self._require_collection()
        try:
            return int(collection.count())
        except Exception as exc:
            raise VectorStoreError("The ChromaDB collection could not be counted.") from exc

    def upsert(
        self,
        *,
        ids: Sequence[str],
        embeddings: Sequence[Sequence[float]],
        documents: Sequence[str],
        metadatas: Sequence[Mapping[str, Any]],
    ) -> None:
        """Insert or replace vectors by stable ID (never creates duplicates)."""

        collection = self._require_collection()
        if not ids:
            return
        if not (len(ids) == len(embeddings) == len(documents) == len(metadatas)):
            raise VectorStoreError("ChromaDB received mismatched vector batches.")

        try:
            collection.upsert(
                ids=list(ids),
                embeddings=[list(vector) for vector in embeddings],
                documents=list(documents),
                metadatas=[dict(metadata) for metadata in metadatas],
            )
        except Exception as exc:
            raise VectorStoreError("The ChromaDB vectors could not be stored.") from exc

    def query(self, embedding: Sequence[float], *, n_results: int) -> list[VectorHit]:
        """Return nearest vectors with their documents and metadata."""

        if n_results <= 0:
            return []
        collection = self._require_collection()
        try:
            if int(collection.count()) == 0:
                return []
        except Exception as exc:
            raise VectorStoreError("The ChromaDB collection could not be counted.") from exc

        try:
            result = collection.query(
                query_embeddings=[list(embedding)],
                n_results=n_results,
                include=["documents", "metadatas", "distances"],
            )
        except Exception as exc:
            raise VectorStoreError("The ChromaDB query could not be completed.") from exc

        ids = [str(value) for value in _first_result_list(result.get("ids"))]
        texts = _first_result_list(result.get("documents"))
        metadatas = _first_result_list(result.get("metadatas"))
        distances = _first_result_list(result.get("distances"))

        hits: list[VectorHit] = []
        for index, vector_id in enumerate(ids):
            if index >= len(distances):
                break
            try:
                distance = float(distances[index])
            except (TypeError, ValueError):
                continue
            text = texts[index] if index < len(texts) and isinstance(texts[index], str) else ""
            metadata = metadatas[index] if index < len(metadatas) else None
            hits.append(
                VectorHit(
                    id=vector_id,
                    text=text,
                    distance=distance,
                    metadata=dict(metadata) if isinstance(metadata, dict) else {},
                )
            )
        return hits

    def item_vector_ids(self, knowledge_item_id: int) -> list[str]:
        """Return all stored vector IDs tagged with one knowledge item."""

        collection = self._require_collection()
        try:
            result = collection.get(
                where={"knowledge_item_id": int(knowledge_item_id)},
                include=["metadatas"],
            )
        except Exception as exc:
            raise VectorStoreError("The ChromaDB lookup could not be completed.") from exc
        return [str(value) for value in result.get("ids", [])]

    def delete(self, ids: Sequence[str]) -> None:
        """Delete vector IDs, ignoring an empty request."""

        if not ids:
            return
        collection = self._require_collection()
        try:
            collection.delete(ids=list(ids))
        except Exception as exc:
            raise VectorStoreError("The ChromaDB vectors could not be deleted.") from exc

    def delete_stale(self, knowledge_item_id: int, keep_ids: set[str]) -> None:
        """Remove this item's vectors that no longer match a SQL chunk."""

        stored = self.item_vector_ids(knowledge_item_id)
        stale = [vector_id for vector_id in stored if vector_id not in keep_ids]
        self.delete(stale)


def connect_vector_store(app: FastAPI) -> VectorStore:
    """Initialize the configured store from the application lifespan."""

    settings: Settings = getattr(app.state, "settings", None) or get_settings()
    store = VectorStore(settings)
    store.connect()

    app.state.vector_store = store
    app.state.chroma_client = store.client
    app.state.chroma_collection = store.collection
    logger.info(
        "chroma_initialized",
        extra={
            "path": str(store.path),
            "collection": store.collection_name,
            "distance": CHROMA_DISTANCE,
        },
    )
    return store


def close_vector_store(app: FastAPI) -> None:
    """Close the lifespan-owned store and clear its application state."""

    store = getattr(app.state, "vector_store", None)
    if store is not None:
        store.close()
    app.state.vector_store = None
    app.state.chroma_client = None
    app.state.chroma_collection = None


def get_vector_store(request: Request) -> VectorStore:
    """FastAPI dependency exposing the lifespan-owned vector store."""

    store = getattr(request.app.state, "vector_store", None)
    if store is None or getattr(store, "connected", False) is not True:
        raise VectorStoreUnavailableError()
    return store


__all__ = [
    "CHROMA_DISTANCE",
    "VectorHit",
    "VectorStore",
    "VectorStoreError",
    "VectorStoreUnavailableError",
    "close_vector_store",
    "connect_vector_store",
    "get_vector_store",
    "stable_chroma_id",
]
