"""Tokenizer-aware text chunking for knowledge items.

Splitting strategy
------------------
When a tokenizer is supplied (the indexing service passes the already-loaded
embedding model's tokenizer), chunk sizes are measured in *real model tokens*:

1. The total sequence budget is ``min(chunk_size, max_seq_length)``. The number
   of special tokens (``[CLS]``/``[SEP]`` for MiniLM) is obtained from the
   tokenizer and subtracted, so an encoded chunk including specials never
   exceeds the model's sequence limit.
2. The tokenizer is called with ``add_special_tokens=False`` and
   ``return_offsets_mapping=True``. Its character offsets give exact source
   spans, so each chunk is a verbatim ``str`` slice of the original content.
   Words are never re-joined or normalized.
3. Spans are packed into overlapping windows of content tokens. When tokenizer
   offsets fall inside a word (punctuation or WordPieces), window edges are
   nudged to whole-word boundaries without exceeding the token budget. Windows
   preserve source order and the configured overlap.
4. Every candidate chunk is re-encoded *with* special tokens and verified. A
   candidate that still exceeds the budget (for example, a single word that
   explodes into many WordPieces) is subdivided at token offsets; only if a
   single token span is itself too large is it split at a character boundary.
   Exhausting the safety limit raises an error rather than truncating text.

Without a tokenizer, a deterministic word-based fallback is used. It cannot
know the model's exact tokenization, so it is only an approximation; production
indexing always supplies the real tokenizer.

In all cases empty/whitespace input yields no chunks, invalid windows raise
``ValueError``, and the final chunk reaches the end of the source.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Protocol

# Total encoded sequence budget, *including* special tokens. MiniLM-L6-v2 has
# max_seq_length=256 and adds 2 special tokens (confirmed from the model).
DEFAULT_CHUNK_SIZE_TOKENS = 256
DEFAULT_CHUNK_OVERLAP_TOKENS = 60

# Fallback only: a word longer than this is cut into fragments so one
# pathological word cannot block the word-based window from advancing.
MAX_TOKEN_CHARS = 64

_MAX_SPLIT_DEPTH = 32
_WORD_PATTERN = re.compile(r"\S+")


class TokenizerLike(Protocol):
    """Duck-typed subset of a Hugging Face fast tokenizer used for chunking."""

    def __call__(
        self,
        text: str,
        *,
        add_special_tokens: bool = ...,
        return_offsets_mapping: bool = ...,
    ) -> Any: ...

    def encode(self, text: str, *, add_special_tokens: bool = ...) -> Any: ...

    def num_special_tokens_to_add(self, pair: bool = ...) -> int: ...


@dataclass(frozen=True)
class TextChunk:
    """One source slice, with counts and offsets into the original text."""

    text: str
    token_count: int
    start_char: int
    end_char: int


def _encode(
    tokenizer: TokenizerLike,
    text: str,
    *,
    add_special_tokens: bool,
    want_offsets: bool = False,
) -> Any | None:
    """Call the tokenizer, preferring the fast ``__call__`` API for offsets."""

    if hasattr(tokenizer, "__call__"):
        try:
            return tokenizer(
                text,
                add_special_tokens=add_special_tokens,
                return_offsets_mapping=want_offsets,
            )
        except TypeError:
            pass

    options: dict[str, Any] = {"add_special_tokens": add_special_tokens}
    if want_offsets:
        options["return_offsets_mapping"] = True
    try:
        return tokenizer.encode(text, **options)
    except TypeError:
        if want_offsets:
            return None
        raise


def _token_ids(encoding: Any) -> list[int]:
    """Normalize a tokenizer result to a list of integer ids."""

    if isinstance(encoding, dict):
        raw = encoding.get("input_ids")
    else:
        raw = getattr(encoding, "input_ids", None)
    if raw is None and isinstance(encoding, (list, tuple)):
        raw = encoding
    if raw is None:
        raise TypeError("Tokenizer result did not contain input_ids")
    return [int(value) for value in raw]


def _offsets(encoding: Any | None) -> list[tuple[int, int]] | None:
    """Return offset pairs from a tokenizer result, if it provides them."""

    if encoding is None:
        return None
    if isinstance(encoding, dict):
        raw = encoding.get("offset_mapping")
    else:
        raw = getattr(encoding, "offset_mapping", None)
    if raw is None:
        return None
    return [(int(start), int(end)) for start, end in raw]


def _special_overhead(tokenizer: TokenizerLike) -> int:
    """Count special tokens the tokenizer adds to a single sequence."""

    counter = getattr(tokenizer, "num_special_tokens_to_add", None)
    if counter is not None:
        try:
            return max(int(counter(pair=False)), 0)
        except TypeError:
            return max(int(counter(False)), 0)
    return max(len(_token_ids(_encode(tokenizer, "", add_special_tokens=True))), 0)


def _encoded_length(tokenizer: TokenizerLike, text: str, special_overhead: int) -> int:
    """Length of ``text`` as the model sees it, special tokens included.

    Encoding without specials first avoids transformers' sequence-length
    warning when the source itself is longer than the model can accept.
    """

    return len(_token_ids(_encode(tokenizer, text, add_special_tokens=False))) + special_overhead


def _tokenizer_spans(tokenizer: TokenizerLike, text: str) -> list[tuple[int, int]]:
    """Exact character spans of non-special tokens, deduplicated and ordered."""

    encoding = _encode(tokenizer, text, add_special_tokens=False, want_offsets=True)
    offsets = _offsets(encoding)
    if not offsets:
        return []

    spans: list[tuple[int, int]] = []
    seen: set[tuple[int, int]] = set()
    for start, end in offsets:
        candidate = (start, end)
        if 0 <= start < end <= len(text) and candidate not in seen:
            seen.add(candidate)
            spans.append(candidate)
    return spans


def _word_spans(text: str) -> list[tuple[int, int]]:
    """Fallback spans: whitespace words, with overlong words fragmented."""

    spans: list[tuple[int, int]] = []
    for match in _WORD_PATTERN.finditer(text):
        start, end = match.span()
        while end - start > MAX_TOKEN_CHARS:
            spans.append((start, start + MAX_TOKEN_CHARS))
            start += MAX_TOKEN_CHARS
        spans.append((start, end))
    return spans


def _word_boundaries(text: str) -> tuple[set[int], set[int]]:
    """Character offsets where whitespace-delimited words start and end."""

    matches = list(_WORD_PATTERN.finditer(text))
    return (
        {match.start() for match in matches},
        {match.end() for match in matches},
    )


def _align_window(
    spans: list[tuple[int, int]],
    start: int,
    end: int,
    word_starts: set[int],
    word_ends: set[int],
) -> tuple[int, int]:
    """Nudge a token window so it does not start or end inside a word.

    Tokenizer offsets may fall inside a word (punctuation and WordPieces). The
    end is moved back to a word end and the start forward to a word start,
    keeping the window within its original token budget.
    """

    while end > start + 1 and spans[end - 1][1] not in word_ends:
        end -= 1
    while start < end - 1 and spans[start][0] not in word_starts:
        start += 1
    return start, end


def _split_with_tokenizer(
    text: str,
    global_start: int,
    *,
    tokenizer: TokenizerLike,
    total_limit: int,
    content_limit: int,
    overlap: int,
    special_overhead: int,
    depth: int = 0,
) -> list[TextChunk]:
    """Recursively split one source segment until it fits the token budget."""

    encoded = _encoded_length(tokenizer, text, special_overhead)
    if encoded <= total_limit:
        return [
            TextChunk(
                text=text,
                token_count=max(encoded - special_overhead, 1),
                start_char=global_start,
                end_char=global_start + len(text),
            )
        ]

    if depth >= _MAX_SPLIT_DEPTH:
        raise ValueError("Unable to fit source text within the tokenizer limit")

    spans = _tokenizer_spans(tokenizer, text) or _word_spans(text)
    if not spans:
        raise ValueError("Non-empty text produced no token spans")

    if len(spans) > content_limit:
        pieces: list[TextChunk] = []
        word_starts, word_ends = _word_boundaries(text)
        window_start = 0
        while window_start < len(spans):
            desired_end = min(window_start + content_limit, len(spans))
            aligned_start, aligned_end = _align_window(
                spans, window_start, desired_end, word_starts, word_ends
            )
            if aligned_end <= aligned_start:
                aligned_start, aligned_end = window_start, desired_end
            is_last = aligned_end == len(spans)
            local_start = 0 if aligned_start == 0 else spans[aligned_start][0]
            local_end = len(text) if is_last else spans[aligned_end - 1][1]
            part = text[local_start:local_end]
            if not part.strip():
                break
            pieces.extend(
                _split_with_tokenizer(
                    part,
                    global_start + local_start,
                    tokenizer=tokenizer,
                    total_limit=total_limit,
                    content_limit=content_limit,
                    overlap=overlap,
                    special_overhead=special_overhead,
                    depth=depth + 1,
                )
            )
            if is_last:
                break
            window_start = max(aligned_start + 1, aligned_end - overlap)
        if pieces:
            return pieces
        raise ValueError("Unable to split source text into non-empty chunks")

    # The segment has few spans but too many model tokens (e.g. one very long
    # word). Bisect its widest span; this is the only case that can cut a word.
    widest = max(range(len(spans)), key=lambda index: spans[index][1] - spans[index][0])
    start, end = spans[widest]
    if end - start < 2:
        raise ValueError("A single tokenizer position exceeds the sequence limit")
    midpoint = (start + end) // 2
    return _split_with_tokenizer(
        text[:midpoint],
        global_start,
        tokenizer=tokenizer,
        total_limit=total_limit,
        content_limit=content_limit,
        overlap=overlap,
        special_overhead=special_overhead,
        depth=depth + 1,
    ) + _split_with_tokenizer(
        text[midpoint:],
        global_start + midpoint,
        tokenizer=tokenizer,
        total_limit=total_limit,
        content_limit=content_limit,
        overlap=overlap,
        special_overhead=special_overhead,
        depth=depth + 1,
    )


def chunk_text(
    text: str,
    *,
    chunk_size: int = DEFAULT_CHUNK_SIZE_TOKENS,
    overlap: int = DEFAULT_CHUNK_OVERLAP_TOKENS,
    tokenizer: TokenizerLike | None = None,
    max_seq_length: int | None = None,
) -> list[TextChunk]:
    """Split ``text`` into ordered, source-preserving overlapping chunks.

    ``chunk_size`` is the total encoded budget when a tokenizer is supplied;
    ``overlap`` is a number of *content* tokens shared between adjacent chunks.
    ``max_seq_length`` (normally the model's own limit) further caps the total.
    """

    if chunk_size <= 0:
        raise ValueError("chunk_size must be greater than zero")
    if overlap < 0:
        raise ValueError("overlap must be non-negative")
    if max_seq_length is not None and max_seq_length <= 0:
        raise ValueError("max_seq_length must be greater than zero")
    if not text or not text.strip():
        return []

    total_limit = chunk_size if max_seq_length is None else min(chunk_size, max_seq_length)
    special_overhead = _special_overhead(tokenizer) if tokenizer is not None else 0
    content_limit = total_limit - special_overhead
    if content_limit <= 0:
        raise ValueError("special tokens leave no room for content in a chunk")
    if overlap >= content_limit:
        raise ValueError("overlap must be smaller than the available content budget")

    if tokenizer is not None:
        return _split_with_tokenizer(
            text,
            0,
            tokenizer=tokenizer,
            total_limit=total_limit,
            content_limit=content_limit,
            overlap=overlap,
            special_overhead=special_overhead,
        )

    # Best-effort fallback when no tokenizer is available.
    spans = _word_spans(text)
    if not spans:
        return []
    step = content_limit - overlap
    chunks: list[TextChunk] = []
    window_start = 0
    while window_start < len(spans):
        window_end = min(window_start + content_limit, len(spans))
        is_last = window_end == len(spans)
        start_char = 0 if window_start == 0 else spans[window_start][0]
        end_char = len(text) if is_last else spans[window_end - 1][1]
        chunk_value = text[start_char:end_char]
        if not chunk_value.strip():
            break
        chunks.append(
            TextChunk(
                text=chunk_value,
                token_count=window_end - window_start,
                start_char=start_char,
                end_char=end_char,
            )
        )
        if is_last:
            break
        window_start += step
    return chunks


@dataclass(frozen=True)
class ChunkingService:
    """Configurable wrapper around :func:`chunk_text` for service callers."""

    chunk_size: int = DEFAULT_CHUNK_SIZE_TOKENS
    overlap: int = DEFAULT_CHUNK_OVERLAP_TOKENS
    tokenizer: TokenizerLike | None = None
    max_seq_length: int | None = None

    def chunk(self, text: str) -> list[TextChunk]:
        """Return the ordered chunks for one item's raw content."""

        return chunk_text(
            text,
            chunk_size=self.chunk_size,
            overlap=self.overlap,
            tokenizer=self.tokenizer,
            max_seq_length=self.max_seq_length,
        )


__all__ = [
    "DEFAULT_CHUNK_OVERLAP_TOKENS",
    "DEFAULT_CHUNK_SIZE_TOKENS",
    "MAX_TOKEN_CHARS",
    "ChunkingService",
    "TextChunk",
    "TokenizerLike",
    "chunk_text",
]
