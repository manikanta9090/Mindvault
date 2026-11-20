"""Offline tokenizer fakes for tokenizer-aware chunking tests.

These model the parts of a Hugging Face fast tokenizer that the chunker uses:
``add_special_tokens``, ``return_offsets_mapping``, and
``num_special_tokens_to_add``. No model download or torch import is needed.
"""

from __future__ import annotations

import re
from typing import Any

_WORD_OR_PUNCTUATION = re.compile(r"\w+|[^\w\s]")
_NON_WHITESPACE = re.compile(r"\S+")


class WordTokenizer:
    """Fast-tokenizer-like fake whose tokens are words and punctuation."""

    def __init__(self, special_tokens: int = 2) -> None:
        if special_tokens < 0:
            raise ValueError("special_tokens must be non-negative")
        self.special_tokens = special_tokens
        self._ids: dict[str, int] = {}

    def _id(self, token: str) -> int:
        if token not in self._ids:
            self._ids[token] = len(self._ids) + 10
        return self._ids[token]

    def _pairs(self, text: str) -> list[tuple[str, int, int]]:
        return [(match.group(), match.start(), match.end()) for match in _WORD_OR_PUNCTUATION.finditer(text)]

    def __call__(
        self,
        text: str,
        *,
        add_special_tokens: bool = False,
        return_offsets_mapping: bool = False,
    ) -> dict[str, Any]:
        pairs = self._pairs(text)
        ids = [self._id(token) for token, _, _ in pairs]
        offsets = [(start, end) for _, start, end in pairs]

        if add_special_tokens:
            left = self.special_tokens // 2
            right = self.special_tokens - left
            ids = [0] * left + ids + [3] * right
            offsets = [(0, 0)] * left + offsets + [(0, 0)] * right

        result: dict[str, Any] = {"input_ids": ids}
        if return_offsets_mapping:
            result["offset_mapping"] = offsets
        return result

    def encode(self, text: str, *, add_special_tokens: bool = False, **_: Any) -> list[int]:
        return list(self(text, add_special_tokens=add_special_tokens)["input_ids"])

    def num_special_tokens_to_add(self, pair: bool = False) -> int:  # noqa: ARG002
        return self.special_tokens


class BurstTokenizer:
    """Pathological fake: one token id per character but whole-word offsets.

    This forces the chunker's "single span exceeds the token budget" branch.
    """

    def __init__(self, special_tokens: int = 2) -> None:
        self.special_tokens = special_tokens

    def __call__(
        self,
        text: str,
        *,
        add_special_tokens: bool = False,
        return_offsets_mapping: bool = False,
    ) -> dict[str, Any]:
        ids: list[int] = []
        offsets: list[tuple[int, int]] = []
        for match in _NON_WHITESPACE.finditer(text):
            offsets.append((match.start(), match.end()))
            ids.extend(ord(character) for character in match.group())

        if add_special_tokens:
            ids = [0] + ids + [3]
            offsets = [(0, 0)] + offsets + [(0, 0)]

        result: dict[str, Any] = {"input_ids": ids}
        if return_offsets_mapping:
            result["offset_mapping"] = offsets
        return result

    def encode(self, text: str, *, add_special_tokens: bool = False, **_: Any) -> list[int]:
        return list(self(text, add_special_tokens=add_special_tokens)["input_ids"])

    def num_special_tokens_to_add(self, pair: bool = False) -> int:  # noqa: ARG002
        return self.special_tokens
