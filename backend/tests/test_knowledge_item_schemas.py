"""Tests for the knowledge item Pydantic schemas."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

import pytest
from pydantic import ValidationError

from app.models import ItemStatus, KnowledgeItem, SourceType
from app.models.knowledge_item import SOURCE_URL_MAX_LENGTH, TITLE_MAX_LENGTH
from app.schemas.knowledge_item import (
    KnowledgeItemCreate,
    KnowledgeItemListResponse,
    KnowledgeItemResponse,
)

NOW = datetime(2026, 11, 20, 12, 0, tzinfo=timezone.utc)

NOTE_PAYLOAD: dict[str, Any] = {
    "content": "A short note.",
    "source_type": "NOTE",
}
URL_PAYLOAD: dict[str, Any] = {
    "content": "<article>Raw markup is preserved.</article>",
    "source_type": "URL",
    "source_url": "https://example.com/articles/2026/11",
}

RESPONSE_FIELDS = {
    "id",
    "title",
    "content",
    "source_type",
    "source_url",
    "status",
    "created_at",
    "updated_at",
}


def _orm_item(**overrides: Any) -> KnowledgeItem:
    """Build an in-memory ORM instance without touching a database."""

    values: dict[str, Any] = {
        "id": 1,
        "title": "A title",
        "content": "Raw content with  spaces \nand Unicode: café 日本語 🚀",
        "source_type": SourceType.NOTE,
        "source_url": None,
        "status": ItemStatus.PROCESSING,
        "created_at": NOW,
        "updated_at": NOW,
    }
    values.update(overrides)
    return KnowledgeItem(**values)


def _response_payload(item_id: int = 1) -> dict[str, Any]:
    return {
        "id": item_id,
        "title": None,
        "content": "plain content",
        "source_type": "NOTE",
        "source_url": None,
        "status": "PROCESSING",
        "created_at": NOW,
        "updated_at": NOW,
    }


def test_valid_note_input() -> None:
    schema = KnowledgeItemCreate(**NOTE_PAYLOAD)

    assert schema.content == "A short note."
    assert schema.title is None
    assert schema.source_type is SourceType.NOTE
    assert schema.source_url is None


def test_valid_note_input_with_enum_member() -> None:
    schema = KnowledgeItemCreate(content="note", source_type=SourceType.NOTE, title="Title")

    assert schema.source_type is SourceType.NOTE
    assert schema.title == "Title"


@pytest.mark.parametrize("url", ["https://example.com/path?q=1", "http://localhost:8000/docs"])
def test_valid_url_input(url: str) -> None:
    schema = KnowledgeItemCreate(content="page body", source_type="URL", source_url=url)

    assert schema.source_type is SourceType.URL
    assert schema.source_url == url


def test_missing_required_content_is_rejected() -> None:
    with pytest.raises(ValidationError) as exc_info:
        KnowledgeItemCreate(source_type="NOTE")  # type: ignore[call-arg]

    assert "content" in str(exc_info.value)


@pytest.mark.parametrize("content", ["", "   ", "\n\t\r ", " \n \t "])
def test_empty_and_whitespace_only_content_is_rejected(content: str) -> None:
    with pytest.raises(ValidationError) as exc_info:
        KnowledgeItemCreate(content=content, source_type="NOTE")

    assert "content" in str(exc_info.value)


def test_raw_content_is_not_modified() -> None:
    raw = "  leading and trailing  \n\ttabbed line\t\nUnicode: 日本語 🚀  "
    schema = KnowledgeItemCreate(content=raw, source_type="NOTE")

    assert schema.content == raw


@pytest.mark.parametrize("source_type", ["TWEET", "note", "", None, 1])
def test_invalid_source_type_is_rejected(source_type: object) -> None:
    with pytest.raises(ValidationError) as exc_info:
        KnowledgeItemCreate(content="x", source_type=source_type)

    assert "source_type" in str(exc_info.value)


@pytest.mark.parametrize(
    "source_url",
    [
        "not-a-url",
        "ftp://example.com/file",
        "https://",
        "://example.com",
        "https://exa mple.com",
        "",
    ],
)
def test_invalid_source_url_is_rejected(source_url: str) -> None:
    with pytest.raises(ValidationError) as exc_info:
        KnowledgeItemCreate(content="x", source_type="NOTE", source_url=source_url)

    assert "source_url" in str(exc_info.value)


@pytest.mark.parametrize("payload", [{"content": "x", "source_type": "URL"}, {**URL_PAYLOAD, "source_url": None}])
def test_url_item_without_source_url_is_rejected(payload: dict[str, Any]) -> None:
    with pytest.raises(ValidationError) as exc_info:
        KnowledgeItemCreate(**payload)

    assert "source_url" in str(exc_info.value)


def test_note_item_may_include_or_omit_source_url() -> None:
    without = KnowledgeItemCreate(content="x", source_type="NOTE")
    with_url = KnowledgeItemCreate(content="x", source_type="NOTE", source_url="https://example.com")

    assert without.source_url is None
    assert with_url.source_url == "https://example.com"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("title", "a" * (TITLE_MAX_LENGTH + 1)),
        ("source_url", "https://example.com/" + "a" * SOURCE_URL_MAX_LENGTH),
    ],
)
def test_orm_length_limits_are_enforced(field: str, value: str) -> None:
    payload: dict[str, Any] = {"content": "x", "source_type": "NOTE", field: value}
    if field == "source_url":
        payload["source_type"] = "URL"

    with pytest.raises(ValidationError) as exc_info:
        KnowledgeItemCreate(**payload)

    assert field in str(exc_info.value)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("title", "a" * TITLE_MAX_LENGTH),
        ("source_url", "https://example.com/" + "a" * (SOURCE_URL_MAX_LENGTH - 20)),
    ],
)
def test_values_at_orm_length_limits_are_accepted(field: str, value: str) -> None:
    payload: dict[str, Any] = {"content": "x", "source_type": "NOTE", field: value}
    if field == "source_url":
        payload["source_type"] = "URL"

    schema = KnowledgeItemCreate(**payload)

    assert getattr(schema, field) == value


def test_response_converts_from_orm_object() -> None:
    item = _orm_item(id=7, title="Notes", source_type=SourceType.URL, source_url="https://example.com")

    response = KnowledgeItemResponse.model_validate(item)
    dumped = response.model_dump(mode="json")

    assert response.id == 7
    assert response.title == "Notes"
    assert response.content == item.content
    assert response.created_at == NOW
    assert response.updated_at == NOW
    assert set(dumped) == RESPONSE_FIELDS
    assert "_sa_instance_state" not in dumped


def test_response_also_accepts_plain_dicts() -> None:
    response = KnowledgeItemResponse.model_validate(_response_payload())

    assert response.source_type is SourceType.NOTE
    assert response.status is ItemStatus.PROCESSING


@pytest.mark.parametrize(
    ("source_type", "status", "expected_source", "expected_status"),
    [
        (SourceType.NOTE, ItemStatus.PROCESSING, "NOTE", "PROCESSING"),
        (SourceType.URL, ItemStatus.COMPLETED, "URL", "COMPLETED"),
        (SourceType.NOTE, ItemStatus.FAILED, "NOTE", "FAILED"),
    ],
)
def test_enum_serialization_uses_string_values(
    source_type: SourceType,
    status: ItemStatus,
    expected_source: str,
    expected_status: str,
) -> None:
    response = KnowledgeItemResponse.model_validate(_orm_item(source_type=source_type, status=status))

    python_dump = response.model_dump()
    json_dump = response.model_dump(mode="json")
    json_payload = json.loads(response.model_dump_json())

    for payload in (python_dump, json_dump, json_payload):
        assert payload["source_type"] == expected_source
        assert payload["status"] == expected_status
        assert isinstance(payload["source_type"], str)
        assert isinstance(payload["status"], str)


@pytest.mark.parametrize(
    ("overrides", "expected_title", "expected_url"),
    [
        ({}, "A title", None),
        ({"title": None}, None, None),
        ({"source_url": "https://example.com"}, "A title", "https://example.com"),
        ({"title": None, "source_url": None}, None, None),
    ],
)
def test_optional_fields_in_response(
    overrides: dict[str, Any],
    expected_title: str | None,
    expected_url: str | None,
) -> None:
    response = KnowledgeItemResponse.model_validate(_orm_item(**overrides))

    assert response.title == expected_title
    assert response.source_url == expected_url


def test_response_collection_validation() -> None:
    items = [KnowledgeItemResponse.model_validate(_orm_item(id=item_id)) for item_id in (1, 2)]
    collection = KnowledgeItemListResponse(items=items, total=2)
    payload = collection.model_dump(mode="json")

    assert collection.total == 2
    assert len(collection.items) == 2
    assert [item.id for item in collection.items] == [1, 2]
    assert payload["total"] == 2
    assert [item["id"] for item in payload["items"]] == [1, 2]


def test_collection_accepts_dict_items_and_derives_total() -> None:
    collection = KnowledgeItemListResponse.model_validate(
        {"items": [_response_payload(1), _response_payload(2)]}
    )

    assert collection.total == 2
    assert all(isinstance(item, KnowledgeItemResponse) for item in collection.items)


def test_empty_collection_is_valid() -> None:
    collection = KnowledgeItemListResponse(items=[])

    assert collection.items == []
    assert collection.total == 0


def test_collection_rejects_invalid_item() -> None:
    with pytest.raises(ValidationError) as exc_info:
        KnowledgeItemListResponse(items=[{"id": 1}], total=1)

    assert "items" in str(exc_info.value)


def test_collection_rejects_negative_total() -> None:
    with pytest.raises(ValidationError) as exc_info:
        KnowledgeItemListResponse(items=[], total=-1)

    assert "total" in str(exc_info.value)
