"""Pydantic schemas for knowledge items.

This module defines the validation boundary for knowledge items. Persistence
stays in :mod:`app.models.knowledge_item`; no database access belongs here.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import (
    AnyHttpUrl,
    BaseModel,
    ConfigDict,
    Field,
    TypeAdapter,
    field_serializer,
    field_validator,
    model_validator,
)

from app.models import ItemStatus, SourceType
from app.models.knowledge_item import SOURCE_URL_MAX_LENGTH, TITLE_MAX_LENGTH

# Validate URLs with Pydantic's HTTP URL rules but keep the field as ``str``:
# callers' strings are stored verbatim rather than being normalized (e.g. by
# adding a trailing slash or percent-encoding) by the URL type.
_HTTP_URL_ADAPTER: TypeAdapter[AnyHttpUrl] = TypeAdapter(AnyHttpUrl)


class KnowledgeItemCreate(BaseModel):
    """Validated payload for capturing a raw knowledge item."""

    title: str | None = Field(default=None, max_length=TITLE_MAX_LENGTH)
    content: str = Field(min_length=1)
    source_type: SourceType
    source_url: str | None = Field(default=None, max_length=SOURCE_URL_MAX_LENGTH)

    @field_validator("content")
    @classmethod
    def _content_must_not_be_blank(cls, value: str) -> str:
        """Reject blank content without altering the caller's raw text."""

        if not value.strip():
            raise ValueError("content must not be empty or whitespace-only")
        return value

    @field_validator("source_url")
    @classmethod
    def _source_url_must_be_http_url(cls, value: str | None) -> str | None:
        """Require a valid http/https URL when one is supplied."""

        if value is None:
            return value
        _HTTP_URL_ADAPTER.validate_python(value)
        return value

    @model_validator(mode="after")
    def _url_items_require_a_source_url(self) -> KnowledgeItemCreate:
        """A URL item is meaningless without the URL it was captured from."""

        if self.source_type is SourceType.URL and self.source_url is None:
            raise ValueError("source_url is required when source_type is URL")
        return self


class KnowledgeItemResponse(BaseModel):
    """Serializable view of a stored knowledge item.

    Only public fields are declared, so ORM internals (such as
    ``_sa_instance_state``) are never serialized.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str | None
    content: str
    source_type: SourceType
    source_url: str | None
    status: ItemStatus
    created_at: datetime
    updated_at: datetime

    @field_serializer("source_type", "status", mode="plain")
    def _serialize_enum_value(self, value: SourceType | ItemStatus) -> str:
        """Emit enum values (e.g. ``"NOTE"``) in both Python and JSON output."""

        return value.value


class KnowledgeItemListResponse(BaseModel):
    """A collection of knowledge items with its overall count."""

    items: list[KnowledgeItemResponse]
    total: int = Field(ge=0)

    @model_validator(mode="before")
    @classmethod
    def _default_total_to_item_count(cls, data: Any) -> Any:
        """Derive ``total`` from ``items`` when the caller omits it.

        Paginated callers can still pass an explicit total representing the
        full result set rather than just the current page.
        """

        if isinstance(data, dict) and "total" not in data:
            items = data.get("items")
            if isinstance(items, (list, tuple)):
                return {**data, "total": len(items)}
        return data
