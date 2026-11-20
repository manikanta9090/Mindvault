"""Unit tests for tokenizer-aware chunking, limits, and source preservation."""

from __future__ import annotations

import re

import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.services.chunking import (
    DEFAULT_CHUNK_OVERLAP_TOKENS,
    DEFAULT_CHUNK_SIZE_TOKENS,
    ChunkingService,
    TextChunk,
    chunk_text,
)
from tests.fake_tokenizers import BurstTokenizer, WordTokenizer


def _encoded_length(tokenizer: WordTokenizer | BurstTokenizer, chunk: TextChunk) -> int:
    return len(tokenizer.encode(chunk.text, add_special_tokens=True))


def _assert_source_preserved(chunks: list[TextChunk], source: str) -> None:
    """Chunks are exact, ordered slices reaching both ends of the source."""

    assert chunks
    assert chunks[0].start_char == 0
    assert chunks[-1].end_char == len(source)
    assert all(source[chunk.start_char : chunk.end_char] == chunk.text for chunk in chunks)
    assert all(chunks[i].start_char < chunks[i + 1].start_char for i in range(len(chunks) - 1))
    assert all(chunks[i].end_char <= chunks[i + 1].end_char for i in range(len(chunks) - 1))
    for match in re.finditer(r"\S+", source):
        assert any(
            chunk.start_char <= match.start() and match.end() <= chunk.end_char
            for chunk in chunks
        ), f"source word {match.group()!r} was dropped"


def test_defaults_match_minilm_sequence_limit() -> None:
    assert DEFAULT_CHUNK_SIZE_TOKENS == 256
    assert DEFAULT_CHUNK_OVERLAP_TOKENS == 60

    settings = Settings()
    assert settings.chunk_size_tokens == 256
    assert settings.chunk_overlap_tokens == 60


def test_settings_validate_chunk_window() -> None:
    with pytest.raises(ValidationError):
        Settings(chunk_size_tokens=10, chunk_overlap_tokens=10)
    with pytest.raises(ValidationError):
        Settings(chunk_size_tokens=0, chunk_overlap_tokens=0)


@pytest.mark.parametrize(
    ("chunk_size", "overlap"),
    [(0, 0), (-1, 0), (5, 5), (5, 6), (5, -1)],
)
def test_chunk_text_rejects_invalid_windows(chunk_size: int, overlap: int) -> None:
    with pytest.raises(ValueError):
        chunk_text("some text", chunk_size=chunk_size, overlap=overlap)


def test_special_tokens_must_leave_room_for_content() -> None:
    tokenizer = WordTokenizer(special_tokens=10)

    with pytest.raises(ValueError, match="special tokens"):
        chunk_text("hello world", chunk_size=10, tokenizer=tokenizer)


@pytest.mark.parametrize("text", ["", "   ", "\n\t\r  "])
def test_empty_or_whitespace_input_produces_no_chunks(text: str) -> None:
    assert chunk_text(text) == []
    assert chunk_text(text, tokenizer=WordTokenizer(), max_seq_length=10) == []


def test_chunks_never_exceed_model_sequence_limit() -> None:
    tokenizer = WordTokenizer()
    text = " ".join(f"word{index}" for index in range(20))

    chunks = chunk_text(text, chunk_size=256, overlap=2, tokenizer=tokenizer, max_seq_length=10)

    assert len(chunks) > 1
    assert all(_encoded_length(tokenizer, chunk) <= 10 for chunk in chunks)
    assert all(chunk.token_count <= 8 for chunk in chunks)  # 10 - 2 special tokens
    assert all(chunk.token_count > 0 for chunk in chunks)
    _assert_source_preserved(chunks, text)


def test_exact_boundary_fits_one_chunk() -> None:
    tokenizer = WordTokenizer()
    text = " ".join(f"w{index}" for index in range(8))

    chunks = chunk_text(text, chunk_size=256, overlap=2, tokenizer=tokenizer, max_seq_length=10)

    assert len(chunks) == 1
    assert _encoded_length(tokenizer, chunks[0]) == 10
    assert chunks[0].token_count == 8


def test_one_token_over_the_boundary_creates_a_second_chunk() -> None:
    tokenizer = WordTokenizer()
    text = " ".join(f"w{index}" for index in range(9))

    chunks = chunk_text(text, chunk_size=256, overlap=2, tokenizer=tokenizer, max_seq_length=10)

    assert len(chunks) == 2
    assert all(_encoded_length(tokenizer, chunk) <= 10 for chunk in chunks)
    _assert_source_preserved(chunks, text)


def test_max_seq_length_caps_a_larger_configured_chunk_size() -> None:
    tokenizer = WordTokenizer()
    text = " ".join(f"token{index}" for index in range(40))

    chunks = chunk_text(text, chunk_size=100, overlap=3, tokenizer=tokenizer, max_seq_length=12)

    assert all(_encoded_length(tokenizer, chunk) <= 12 for chunk in chunks)
    _assert_source_preserved(chunks, text)


def test_special_token_count_is_read_from_the_tokenizer() -> None:
    tokenizer = WordTokenizer(special_tokens=4)
    text = " ".join(f"x{index}" for index in range(30))

    chunks = chunk_text(text, chunk_size=10, overlap=1, tokenizer=tokenizer)

    assert all(_encoded_length(tokenizer, chunk) <= 10 for chunk in chunks)
    assert all(chunk.token_count <= 6 for chunk in chunks)  # 10 - 4 special tokens


def test_overlap_is_preserved_in_content_tokens() -> None:
    tokenizer = WordTokenizer()
    text = " ".join(f"w{index}" for index in range(10))

    chunks = chunk_text(text, chunk_size=8, overlap=2, tokenizer=tokenizer)

    first_words = chunks[0].text.split()
    second_words = chunks[1].text.split()
    assert first_words == [f"w{index}" for index in range(6)]
    assert second_words == [f"w{index}" for index in range(4, 10)]
    assert first_words[-2:] == second_words[:2]


def test_long_text_is_ordered_bounded_and_not_truncated() -> None:
    tokenizer = WordTokenizer()
    words = [f"token{index}" for index in range(1000)]
    text = " ".join(words)

    chunks = chunk_text(text, chunk_size=256, overlap=4, tokenizer=tokenizer, max_seq_length=32)

    assert len(chunks) > 10
    assert all(_encoded_length(tokenizer, chunk) <= 32 for chunk in chunks)
    assert chunks[0].text.startswith("token0 ")
    assert chunks[-1].text.endswith("token999")
    _assert_source_preserved(chunks, text)


def test_code_like_text_preserves_layout_and_stays_within_limit() -> None:
    tokenizer = WordTokenizer()
    snippet = "def calculate(value):\n    result = value ** 2 + 1\n    return result\n"
    text = snippet * 5

    chunks = chunk_text(text, chunk_size=256, overlap=4, tokenizer=tokenizer, max_seq_length=24)

    assert all(_encoded_length(tokenizer, chunk) <= 24 for chunk in chunks)
    assert any("def calculate(value):" in chunk.text for chunk in chunks)
    assert any("return result" in chunk.text for chunk in chunks)
    assert chunks[-1].text.endswith("return result\n")
    _assert_source_preserved(chunks, text)


def test_punctuation_heavy_text_preserves_punctuation_and_stays_within_limit() -> None:
    tokenizer = WordTokenizer()
    text = "Hi, there!!! (really: 1,2,3); why? ... " * 5

    chunks = chunk_text(text, chunk_size=256, overlap=3, tokenizer=tokenizer, max_seq_length=20)

    assert all(_encoded_length(tokenizer, chunk) <= 20 for chunk in chunks)
    assert "1,2,3" in "".join(chunk.text for chunk in chunks)
    assert chunks[0].text.startswith("Hi, there!!!")
    _assert_source_preserved(chunks, text)


def test_single_long_word_with_burst_tokenizer_is_subdivided() -> None:
    tokenizer = BurstTokenizer()
    text = "x" * 100

    chunks = chunk_text(text, chunk_size=10, overlap=0, tokenizer=tokenizer)

    assert len(chunks) > 1
    assert all(_encoded_length(tokenizer, chunk) <= 10 for chunk in chunks)
    assert chunks[0].start_char == 0
    assert chunks[-1].end_char == len(text)
    assert all(
        chunks[index].start_char == chunks[index - 1].end_char
        for index in range(1, len(chunks))
    )
    assert "".join(chunk.text for chunk in chunks) == text


def test_word_based_fallback_still_produces_overlapping_chunks() -> None:
    chunks = chunk_text("a b c d e", chunk_size=3, overlap=1)

    assert [chunk.text for chunk in chunks] == ["a b c", "c d e"]
    assert [chunk.token_count for chunk in chunks] == [3, 3]
    _assert_source_preserved(chunks, "a b c d e")


def test_chunking_service_passes_tokenizer_and_limit() -> None:
    tokenizer = WordTokenizer()
    service = ChunkingService(chunk_size=256, overlap=2, tokenizer=tokenizer, max_seq_length=12)
    text = " ".join(f"part{index}" for index in range(30))

    chunks = service.chunk(text)

    assert all(_encoded_length(tokenizer, chunk) <= 12 for chunk in chunks)
    _assert_source_preserved(chunks, text)
