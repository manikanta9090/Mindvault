"""Local MiniLM embedding generation with lazy, reusable model loading.

The heavyweight ``sentence-transformers`` and ``torch`` imports happen only
when an embedding is actually requested. One :class:`SentenceTransformerEmbedder`
instance is shared for the process, so the model is loaded at most once per
worker. Inference is explicitly pinned to CPU.
"""

from __future__ import annotations

import math
import threading
from collections.abc import Callable, Sequence
from typing import Any, Protocol

from app.core.errors import AppError

EMBEDDING_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
EMBEDDING_DIMENSION = 384
DEFAULT_BATCH_SIZE = 32

# Verified from the installed model: all-MiniLM-L6-v2 accepts 256 tokens per
# sequence and its tokenizer adds [CLS] and [SEP] (2 special tokens).
MINILM_MAX_SEQUENCE_LENGTH = 256
MINILM_SPECIAL_TOKENS = 2


class EmbeddingError(AppError):
    """An embedding could not be generated or failed validation."""

    status_code = 500
    code = "embedding_failed"
    default_message = "Text embeddings could not be generated."


class Embedder(Protocol):
    """Minimal interface used by callers; easy to fake in tests."""

    def encode(self, texts: Sequence[str]) -> Sequence[Sequence[float]]:
        """Return one vector per input text, in the same order."""
        ...


ModelLoader = Callable[[str, str], Any]


def _load_sentence_transformer(model_name: str, device: str) -> Any:
    """Import and construct the real model only when it is first needed."""

    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(model_name, device=device)


class SentenceTransformerEmbedder:
    """Thread-safe, lazily initialized wrapper around a sentence transformer."""

    def __init__(
        self,
        model_name: str = EMBEDDING_MODEL_NAME,
        *,
        device: str = "cpu",
        batch_size: int = DEFAULT_BATCH_SIZE,
        model_loader: ModelLoader | None = None,
    ) -> None:
        self.model_name = model_name
        self.device = device
        self.batch_size = batch_size
        self._model_loader: ModelLoader = model_loader or _load_sentence_transformer
        # Only the real loader needs the explicit torch inference_mode guard;
        # injected fakes stay lightweight and never import torch.
        self._use_inference_mode = model_loader is None
        self._model: Any | None = None
        self._lock = threading.Lock()

    @property
    def model(self) -> Any:
        """Load the model on first access, then reuse it."""

        if self._model is None:
            with self._lock:
                if self._model is None:
                    self._model = self._model_loader(self.model_name, self.device)
        return self._model

    @property
    def tokenizer(self) -> Any:
        """The tokenizer belonging to the already-loaded model (lazy)."""

        return self.model.tokenizer

    @property
    def max_seq_length(self) -> int:
        """The model's real sequence limit, including special tokens."""

        value = getattr(self.model, "max_seq_length", None)
        if value is None:
            value = getattr(self.tokenizer, "model_max_length", MINILM_MAX_SEQUENCE_LENGTH)
        return int(value)

    def encode(self, texts: Sequence[str]) -> Sequence[Sequence[float]]:
        """Encode a batch of texts on the configured device (CPU by default)."""

        model = self.model
        options: dict[str, Any] = {
            "batch_size": self.batch_size,
            "convert_to_numpy": True,
            "show_progress_bar": False,
            "device": self.device,
        }
        if self._use_inference_mode:
            import torch

            with torch.inference_mode():
                return model.encode(list(texts), **options)
        return model.encode(list(texts), **options)


_shared_embedder: SentenceTransformerEmbedder | None = None
_shared_embedder_lock = threading.Lock()


def get_embedder() -> SentenceTransformerEmbedder:
    """Return the process-wide embedder, creating the wrapper lazily."""

    global _shared_embedder
    if _shared_embedder is None:
        with _shared_embedder_lock:
            if _shared_embedder is None:
                _shared_embedder = SentenceTransformerEmbedder()
    return _shared_embedder


def reset_embedder_cache() -> None:
    """Drop the shared wrapper (test helper; does not unload torch tensors)."""

    global _shared_embedder
    with _shared_embedder_lock:
        _shared_embedder = None


def validate_embedding(vector: Sequence[float]) -> list[float]:
    """Convert one vector to floats and enforce dimension/finiteness rules."""

    try:
        values = [float(value) for value in vector]
    except (TypeError, ValueError) as exc:
        raise EmbeddingError("Embedding contains a non-numeric value.") from exc

    if len(values) != EMBEDDING_DIMENSION:
        raise EmbeddingError(
            f"Expected a {EMBEDDING_DIMENSION}-dimensional embedding, got {len(values)}."
        )
    if not all(math.isfinite(value) for value in values):
        raise EmbeddingError("Embedding contains a non-finite value.")

    return values


def embed_texts(
    texts: Sequence[str],
    *,
    embedder: Embedder | None = None,
) -> list[list[float]]:
    """Embed texts in order, validating every vector before returning it.

    An empty batch returns immediately without loading the model. Callers can
    inject any object implementing :class:`Embedder`, which keeps tests fully
    offline and independent of the real model.
    """

    texts_list = list(texts)
    if not texts_list:
        return []

    active = embedder if embedder is not None else get_embedder()

    try:
        raw_vectors = active.encode(texts_list)
    except EmbeddingError:
        raise
    except Exception as exc:
        raise EmbeddingError("The embedding model failed to encode the input.") from exc

    try:
        rows = list(raw_vectors)
    except TypeError as exc:
        raise EmbeddingError("Embedding model did not return a sequence of vectors.") from exc
    if len(rows) != len(texts_list):
        raise EmbeddingError("Embedding model returned the wrong number of vectors.")
    return [validate_embedding(row) for row in rows]


__all__ = [
    "DEFAULT_BATCH_SIZE",
    "EMBEDDING_DIMENSION",
    "EMBEDDING_MODEL_NAME",
    "MINILM_MAX_SEQUENCE_LENGTH",
    "MINILM_SPECIAL_TOKENS",
    "Embedder",
    "EmbeddingError",
    "SentenceTransformerEmbedder",
    "embed_texts",
    "get_embedder",
    "reset_embedder_cache",
    "validate_embedding",
]
