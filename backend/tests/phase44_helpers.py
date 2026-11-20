"""Offline, deterministic helpers for Phase 4.4 integration evaluation."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import FastAPI

from app.core.config import Settings
from app.services.embeddings import EMBEDDING_DIMENSION
from app.services.indexing import index_knowledge_item
from app.services.url_fetcher import FetchedPage

_KEYWORD_DIMENSIONS: tuple[tuple[str, int], ...] = (
    ("node", 0),
    ("chroma", 1),
    ("postgres", 2),
    ("runtime", 3),
)
_UNKNOWN_DIMENSION = EMBEDDING_DIMENSION - 1


class KeywordEmbedder:
    """Map known keywords to fixed orthogonal vectors; no model is loaded."""

    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def encode(self, texts: Any) -> list[list[float]]:
        values = list(texts)
        self.calls.append(values)
        vectors: list[list[float]] = []
        for value in values:
            vector = [0.0] * EMBEDDING_DIMENSION
            lowered = value.lower()
            matched = False
            for keyword, dimension in _KEYWORD_DIMENSIONS:
                if keyword in lowered:
                    vector[dimension] = 1.0
                    matched = True
            if not matched:
                vector[_UNKNOWN_DIMENSION] = 1.0
            vectors.append(vector)
        return vectors


class FailingEmbedder:
    """Fail every encode call to exercise rollback/recovery behavior."""

    def encode(self, _texts: Any) -> list[list[float]]:
        raise RuntimeError("simulated embedding failure")


class FakeUrlFetcher:
    """Stand-in for UrlFetcher that returns a fixed offline HTML document."""

    html = (
        "<html><head><title>Chroma persistence</title></head>"
        "<body><article>ChromaDB stores embeddings persistently. "
        "Chroma uses cosine distance.</article></body></html>"
    )

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def fetch(self, url: str) -> FetchedPage:
        return FetchedPage(html=self.html, final_url=url, content_type="text/html")


def settings_for(tmp_path: Path, **overrides: Any) -> Settings:
    """Build an isolated settings object for one deterministic test app."""

    values: dict[str, Any] = {
        "database_url": f"sqlite:///{tmp_path.joinpath('phase44.db').as_posix()}",
        "chroma_path": tmp_path / "phase44-chroma",
        "chunk_size_tokens": 64,
        "chunk_overlap_tokens": 8,
        "retrieval_top_k": 3,
    }
    values.update(overrides)
    return Settings(**values)


def index_item(app: FastAPI, item_id: int, embedder: Any | None = None) -> Any:
    """Run the real chunk/index pipeline against the app's lifespan-owned store."""

    active_embedder = embedder or KeywordEmbedder()
    with app.state.database.session_factory() as session:
        return index_knowledge_item(
            session,
            item_id,
            settings=app.state.settings,
            embedder=active_embedder,
            vector_store=app.state.vector_store,
        )
