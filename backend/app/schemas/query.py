"""Pydantic schemas for grounding-aware question answering."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_serializer, field_validator

from app.models import SourceType

QUESTION_MAX_LENGTH = 2_000


class QueryRequest(BaseModel):
    """Validated question submitted to ``POST /query``."""

    question: str = Field(min_length=1, max_length=QUESTION_MAX_LENGTH)

    @field_validator("question")
    @classmethod
    def _question_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("question must not be empty or whitespace-only")
        return value


class QuerySource(BaseModel):
    """One retrieved item that the answer may cite."""

    model_config = ConfigDict(from_attributes=True)

    item_id: int = Field(gt=0)
    title: str | None
    source_type: SourceType
    source_url: str | None = None
    snippet: str
    citation_id: str = Field(pattern=r"^\[\d+\]$")

    @field_serializer("source_type", mode="plain")
    def _serialize_source_type(self, value: SourceType) -> str:
        """Emit enum values (e.g. ``"NOTE"``) consistently with item schemas."""

        return value.value


class QueryResponse(BaseModel):
    """Grounded answer plus the complete citation-to-item mapping."""

    answer: str
    sources: list[QuerySource]


__all__ = ["QueryRequest", "QueryResponse", "QuerySource", "QUESTION_MAX_LENGTH"]
