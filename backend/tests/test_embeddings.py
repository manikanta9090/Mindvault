"""Embedding tests using injected fakes only; the real model is never loaded."""

from __future__ import annotations

from typing import Any

import pytest

from app.services import embeddings
from app.services.embeddings import (
    EMBEDDING_DIMENSION,
    EMBEDDING_MODEL_NAME,
    MINILM_MAX_SEQUENCE_LENGTH,
    MINILM_SPECIAL_TOKENS,
    EmbeddingError,
    SentenceTransformerEmbedder,
    embed_texts,
    get_embedder,
    reset_embedder_cache,
    validate_embedding,
)


class FakeEmbedder:
    """Records calls and returns predictable, valid 384-dimensional vectors."""

    def __init__(self, vectors: list[list[float]] | None = None, error: Exception | None = None):
        self.calls: list[list[str]] = []
        self.vectors = vectors
        self.error = error

    def encode(self, texts: Any) -> list[list[float]]:
        values = list(texts)
        self.calls.append(values)
        if self.error is not None:
            raise self.error
        if self.vectors is not None:
            return self.vectors
        return [[float(index)] + [0.0] * (EMBEDDING_DIMENSION - 1) for index in range(len(values))]


def _forbid_shared_model(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fail loudly if a test accidentally reaches for the shared real model."""

    def forbidden() -> Any:
        raise AssertionError("the real embedding model must not be loaded in tests")

    monkeypatch.setattr(embeddings, "get_embedder", forbidden)


def test_model_identity_dimension_and_sequence_limit() -> None:
    assert EMBEDDING_MODEL_NAME == "sentence-transformers/all-MiniLM-L6-v2"
    assert EMBEDDING_DIMENSION == 384
    assert MINILM_MAX_SEQUENCE_LENGTH == 256
    assert MINILM_SPECIAL_TOKENS == 2


def test_injected_model_is_used_once_and_vectors_keep_input_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _forbid_shared_model(monkeypatch)
    fake = FakeEmbedder()

    vectors = embed_texts(["first", "second"], embedder=fake)

    assert fake.calls == [["first", "second"]]
    assert [vector[0] for vector in vectors] == [0.0, 1.0]
    assert all(len(vector) == EMBEDDING_DIMENSION for vector in vectors)


def test_empty_batch_does_not_call_the_model(monkeypatch: pytest.MonkeyPatch) -> None:
    _forbid_shared_model(monkeypatch)
    fake = FakeEmbedder()

    assert embed_texts([], embedder=fake) == []
    assert fake.calls == []


def test_wrong_dimension_is_rejected() -> None:
    fake = FakeEmbedder(vectors=[[0.0] * (EMBEDDING_DIMENSION - 1)])

    with pytest.raises(EmbeddingError, match="384-dimensional"):
        embed_texts(["text"], embedder=fake)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_non_finite_values_are_rejected(value: float) -> None:
    vector = [0.0] * EMBEDDING_DIMENSION
    vector[7] = value

    with pytest.raises(EmbeddingError, match="non-finite"):
        validate_embedding(vector)


def test_non_numeric_values_are_rejected() -> None:
    vector: list[Any] = [0.0] * EMBEDDING_DIMENSION
    vector[3] = "not-a-number"

    with pytest.raises(EmbeddingError, match="non-numeric"):
        validate_embedding(vector)


def test_vector_count_must_match_input_count() -> None:
    fake = FakeEmbedder(vectors=[[0.0] * EMBEDDING_DIMENSION])

    with pytest.raises(EmbeddingError, match="wrong number"):
        embed_texts(["one", "two"], embedder=fake)


def test_model_exceptions_become_structured_errors() -> None:
    fake = FakeEmbedder(error=RuntimeError("model exploded"))

    with pytest.raises(EmbeddingError, match="failed to encode") as raised:
        embed_texts(["text"], embedder=fake)

    assert isinstance(raised.value.__cause__, RuntimeError)


def test_model_is_loaded_lazily_and_reused() -> None:
    loader_calls: list[tuple[str, str]] = []

    class FakeModel:
        tokenizer = object()
        max_seq_length = MINILM_MAX_SEQUENCE_LENGTH

        def encode(self, texts: Any, **options: Any) -> list[list[float]]:
            assert options["device"] == "cpu"
            assert options["convert_to_numpy"] is True
            assert options["show_progress_bar"] is False
            return [[0.0] * EMBEDDING_DIMENSION for _ in texts]

    def loader(model_name: str, device: str) -> FakeModel:
        loader_calls.append((model_name, device))
        return FakeModel()

    embedder = SentenceTransformerEmbedder(model_name="fake/local-model", model_loader=loader)

    assert loader_calls == []
    assert embedder.tokenizer is embedder.model.tokenizer
    assert embedder.max_seq_length == 256
    assert loader_calls == [("fake/local-model", "cpu")]
    embedder.encode(["first"])
    embedder.encode(["second", "third"])
    assert loader_calls == [("fake/local-model", "cpu")]


def test_shared_embedder_wrapper_is_cached() -> None:
    # Creating the wrapper is lazy; no model is loaded until encode() is called.
    reset_embedder_cache()
    try:
        first = get_embedder()
        second = get_embedder()

        assert first is second
        assert first.model_name == EMBEDDING_MODEL_NAME
    finally:
        reset_embedder_cache()
