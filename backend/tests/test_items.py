"""Tests for the GET /items knowledge listing endpoint."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlalchemy.engine import Engine

from app.core.database import Database
from app.models import ItemStatus, KnowledgeItem, SourceType

RESPONSE_FIELDS = {"items", "total", "limit", "offset"}
ITEM_FIELDS = {
    "id",
    "title",
    "content",
    "source_type",
    "source_url",
    "status",
    "created_at",
    "updated_at",
}
_BASE_TIME = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _row(
    *,
    content: str = "content",
    source_type: SourceType = SourceType.NOTE,
    status: ItemStatus = ItemStatus.COMPLETED,
    created_at: datetime | None = None,
    title: str | None = None,
    source_url: str | None = None,
) -> dict[str, Any]:
    return {
        "title": title,
        "content": content,
        "source_type": source_type,
        "source_url": source_url,
        "status": status,
        "created_at": created_at if created_at is not None else _BASE_TIME,
    }


def _seed(client: TestClient, *rows: dict[str, Any]) -> list[int]:
    database: Database = client.app.state.database
    ids: list[int] = []
    with database.session_factory() as session:
        for row in rows:
            item = KnowledgeItem(**row)
            session.add(item)
            session.flush()
            ids.append(item.id)
        session.commit()
    return ids


def _at(minutes: int) -> datetime:
    from datetime import timedelta

    return _BASE_TIME + timedelta(minutes=minutes)


def _ids(payload: dict[str, Any]) -> list[int]:
    return [item["id"] for item in payload["items"]]


def test_list_empty_database(client: TestClient) -> None:
    response = client.get("/items")

    assert response.status_code == 200
    assert response.json() == {"items": [], "total": 0, "limit": 20, "offset": 0}


def test_list_single_saved_note(client: TestClient) -> None:
    item_id = _seed(client, _row(title="A note", content="note body"))[0]

    response = client.get("/items")

    assert response.status_code == 200
    payload = response.json()
    assert set(payload) == RESPONSE_FIELDS
    assert payload["total"] == 1
    assert len(payload["items"]) == 1
    item = payload["items"][0]
    assert set(item) == ITEM_FIELDS
    assert item["id"] == item_id
    assert item["title"] == "A note"
    assert item["content"] == "note body"
    assert item["source_type"] == "NOTE"
    assert item["source_url"] is None
    assert item["status"] == "COMPLETED"
    assert isinstance(item["created_at"], str)
    assert isinstance(item["updated_at"], str)


def test_list_multiple_notes_and_urls(client: TestClient) -> None:
    _seed(
        client,
        _row(content="note one", source_type=SourceType.NOTE),
        _row(content="url one", source_type=SourceType.URL, source_url="https://example.com/1"),
        _row(content="note two", source_type=SourceType.NOTE),
        _row(content="url two", source_type=SourceType.URL, source_url="https://example.com/2"),
    )

    payload = client.get("/items").json()

    assert payload["total"] == 4
    assert len(payload["items"]) == 4
    assert [item["source_type"] for item in payload["items"]].count("NOTE") == 2
    assert [item["source_type"] for item in payload["items"]].count("URL") == 2


def test_default_pagination(client: TestClient) -> None:
    _seed(client, *[_row(content=f"note {n}") for n in range(25)])

    payload = client.get("/items").json()

    assert payload["limit"] == 20
    assert payload["offset"] == 0
    assert len(payload["items"]) == 20
    assert payload["total"] == 25


def test_custom_limit(client: TestClient) -> None:
    _seed(client, *[_row(content=f"note {n}") for n in range(5)])

    payload = client.get("/items", params={"limit": 2}).json()

    assert payload["limit"] == 2
    assert len(payload["items"]) == 2
    assert payload["total"] == 5


def test_offset_behavior(client: TestClient) -> None:
    ids = _seed(
        client,
        *[_row(content=f"note {n}", created_at=_at(n)) for n in range(5)],
    )

    payload = client.get("/items", params={"limit": 2, "offset": 2}).json()

    assert payload["offset"] == 2
    # Seed order is oldest-first; the API returns newest-first.
    assert _ids(payload) == list(reversed(ids))[2:4]


def test_total_count_across_multiple_pages(client: TestClient) -> None:
    ids = _seed(client, *[_row(content=f"note {n}") for n in range(5)])

    pages = [
        client.get("/items", params={"limit": 2, "offset": offset}).json()
        for offset in (0, 2, 4)
    ]

    newest_first = list(reversed(ids))

    assert [page["total"] for page in pages] == [5, 5, 5]
    assert [len(page["items"]) for page in pages] == [2, 2, 1]
    assert _ids(pages[0]) == newest_first[0:2]
    assert _ids(pages[1]) == newest_first[2:4]
    assert _ids(pages[2]) == newest_first[4:5]
    assert len(set(_ids(pages[0]) + _ids(pages[1]) + _ids(pages[2]))) == 5


def test_offset_beyond_available_records(client: TestClient) -> None:
    _seed(client, _row(content="one"), _row(content="two"))

    payload = client.get("/items", params={"offset": 999}).json()

    assert payload["items"] == []
    assert payload["total"] == 2
    assert payload["offset"] == 999


def test_source_type_filter_note(client: TestClient) -> None:
    ids = _seed(
        client,
        _row(content="note a", source_type=SourceType.NOTE),
        _row(
            content="url a",
            source_type=SourceType.URL,
            source_url="https://example.com/a",
        ),
        _row(content="note b", source_type=SourceType.NOTE),
    )

    payload = client.get("/items", params={"source_type": "NOTE"}).json()

    assert payload["total"] == 2
    assert set(_ids(payload)) == {ids[0], ids[2]}
    assert all(item["source_type"] == "NOTE" for item in payload["items"])


def test_source_type_filter_url(client: TestClient) -> None:
    _seed(
        client,
        _row(content="note a", source_type=SourceType.NOTE),
        _row(
            content="url a",
            source_type=SourceType.URL,
            source_url="https://example.com/a",
        ),
        _row(
            content="url b",
            source_type=SourceType.URL,
            source_url="https://example.com/b",
        ),
    )

    payload = client.get("/items", params={"source_type": "URL"}).json()

    assert payload["total"] == 2
    assert all(item["source_type"] == "URL" for item in payload["items"])
    assert {item["source_url"] for item in payload["items"]} == {
        "https://example.com/a",
        "https://example.com/b",
    }


def test_status_filter(client: TestClient) -> None:
    ids = _seed(
        client,
        _row(content="done", status=ItemStatus.COMPLETED),
        _row(content="failed one", status=ItemStatus.FAILED),
        _row(content="processing", status=ItemStatus.PROCESSING),
        _row(content="failed two", status=ItemStatus.FAILED),
    )

    payload = client.get("/items", params={"status": "FAILED"}).json()

    assert payload["total"] == 2
    assert set(_ids(payload)) == {ids[1], ids[3]}
    assert all(item["status"] == "FAILED" for item in payload["items"])


def test_combined_filters_apply_before_total(client: TestClient) -> None:
    expected_ids = _seed(
        client,
        _row(content="note completed", source_type=SourceType.NOTE, status=ItemStatus.COMPLETED),
        _row(content="url completed a", source_type=SourceType.URL, status=ItemStatus.COMPLETED,
             source_url="https://example.com/a"),
        _row(content="url failed", source_type=SourceType.URL, status=ItemStatus.FAILED,
             source_url="https://example.com/f"),
        _row(content="note failed", source_type=SourceType.NOTE, status=ItemStatus.FAILED),
        _row(content="url completed b", source_type=SourceType.URL, status=ItemStatus.COMPLETED,
             source_url="https://example.com/b"),
        _row(content="url processing", source_type=SourceType.URL, status=ItemStatus.PROCESSING,
             source_url="https://example.com/p"),
    )

    payload = client.get(
        "/items",
        params={"source_type": "URL", "status": "COMPLETED"},
    ).json()

    assert payload["total"] == 2
    assert set(_ids(payload)) == {expected_ids[1], expected_ids[4]}
    assert all(
        item["source_type"] == "URL" and item["status"] == "COMPLETED"
        for item in payload["items"]
    )


@pytest.mark.parametrize("limit", [0, -1, 101, 1000, "abc"])
def test_invalid_limit_returns_422(client: TestClient, limit: object) -> None:
    response = client.get("/items", params={"limit": limit})

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


@pytest.mark.parametrize("offset", [-1, -100])
def test_negative_offset_returns_422(client: TestClient, offset: int) -> None:
    response = client.get("/items", params={"offset": offset})

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


@pytest.mark.parametrize("source_type", ["TWEET", "note", ""])
def test_invalid_source_type_returns_422(client: TestClient, source_type: str) -> None:
    response = client.get("/items", params={"source_type": source_type})

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


@pytest.mark.parametrize("status", ["PENDING", "completed", ""])
def test_invalid_status_returns_422(client: TestClient, status: str) -> None:
    response = client.get("/items", params={"status": status})

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_maximum_allowed_limit_is_accepted(client: TestClient) -> None:
    _seed(client, _row(content="one"))

    response = client.get("/items", params={"limit": 100})

    assert response.status_code == 200
    assert response.json()["limit"] == 100


def test_newest_first_with_stable_id_tiebreaker(client: TestClient) -> None:
    ids = _seed(
        client,
        _row(content="oldest", created_at=_at(0)),
        _row(content="middle", created_at=_at(5)),
        _row(content="newest", created_at=_at(10)),
    )

    payload = client.get("/items").json()

    assert _ids(payload) == [ids[2], ids[1], ids[0]]


def test_stable_ordering_when_timestamps_match(client: TestClient) -> None:
    ids = _seed(
        client,
        *[_row(content=f"same time {n}", created_at=_BASE_TIME) for n in range(4)],
    )

    payload = client.get("/items").json()

    assert _ids(payload) == list(reversed(ids))


def test_listing_issues_exactly_two_paginated_queries(client: TestClient) -> None:
    _seed(client, *[_row(content=f"note {n}") for n in range(6)])
    database: Database = client.app.state.database
    engine: Engine = database.engine
    statements: list[str] = []

    def record(
        _connection: object,
        _cursor: object,
        statement: str,
        _parameters: object,
        _context: object,
        _many: object,
    ) -> None:
        statements.append(statement)

    event.listen(engine, "before_cursor_execute", record)
    try:
        response = client.get("/items", params={"limit": 2})
    finally:
        event.remove(engine, "before_cursor_execute", record)

    selects = [
        statement
        for statement in statements
        if statement.lstrip().lower().startswith("select")
        and "knowledge_items" in statement.lower()
    ]

    assert response.status_code == 200
    assert len(selects) == 2
    assert any("count" in statement.lower() for statement in selects)
    assert any("limit" in statement.lower() or "offset" in statement.lower()
               for statement in selects)


def test_ingested_note_appears_in_listing(client: TestClient) -> None:
    created = client.post(
        "/ingest",
        json={"title": "From ingest", "content": "raw note", "source_type": "NOTE"},
    )

    payload = client.get("/items").json()

    assert created.status_code == 201
    assert payload["total"] == 1
    assert payload["items"][0]["id"] == created.json()["id"]
    assert payload["items"][0]["content"] == "raw note"
    assert payload["items"][0]["status"] == "COMPLETED"


def test_list_is_present_in_openapi_schema(client: TestClient) -> None:
    schema = client.get("/openapi.json").json()

    assert "/items" in schema["paths"]
    parameters = {
        parameter["name"]
        for parameter in schema["paths"]["/items"]["get"]["parameters"]
    }
    assert parameters == {"limit", "offset", "source_type", "status"}
