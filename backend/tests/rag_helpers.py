"""Shared offline helpers for Phase 4.3 tests (no real provider calls)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.models import ItemStatus, SourceType
from app.services.retrieval import KnowledgeItemMetadata, RetrievalResult


def make_result(
    *,
    item_id: int = 1,
    chunk_id: int | None = None,
    title: str | None = "Saved note",
    text: str = "Node.js is a JavaScript runtime.",
    source_type: SourceType = SourceType.NOTE,
    source_url: str | None = None,
) -> RetrievalResult:
    """Build one SQL-backed retrieval hit without touching ChromaDB."""

    now = datetime.now(timezone.utc)
    return RetrievalResult(
        chunk_id=chunk_id if chunk_id is not None else item_id,
        chunk_index=0,
        content_hash="test-hash",
        chroma_id=f"knowledge_chunk_{item_id}_0_test-hash",
        text=text,
        distance=0.0,
        knowledge_item=KnowledgeItemMetadata(
            id=item_id,
            title=title,
            source_type=source_type,
            source_url=source_url,
            status=ItemStatus.COMPLETED,
            created_at=now,
            updated_at=now,
        ),
    )


class FakeLLMProvider:
    """Record prompts and return a scripted answer or raise a scripted error."""

    def __init__(self, answer: str = "A grounded answer [1].", error: Exception | None = None) -> None:
        self.answer = answer
        self.error = error
        self.calls: list[tuple[str, str]] = []

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        self.calls.append((system_prompt, user_prompt))
        if self.error is not None:
            raise self.error
        return self.answer

    @property
    def last_call(self) -> tuple[str, str]:
        return self.calls[-1]


def retrieval_stub(results: list[RetrievalResult]) -> Any:
    """Return a compatible replacement for ``retrieve_chunks`` in tests."""

    def _stub(*_args: Any, **_kwargs: Any) -> list[RetrievalResult]:
        return results

    return _stub
