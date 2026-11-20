"""Integration tests for URL ingestion (HTTP always mocked, never real)."""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.database import Database
from app.models import ItemStatus, KnowledgeItem, SourceType
from app.services import ingestion
from app.services.url_fetcher import (
    FetchedPage,
    FetchHttpError,
    FetchRedirectError,
    FetchTimeoutError,
)
from app.services.url_safety import UnsafeUrlError

PAGE_HTML = """
<html><head><title>Extracted Page Title</title>
<script>var secret = 'ignore me';</script>
<style>.x { color: red; }</style></head>
<body><nav>Navigation noise</nav>
<article>
  <h1>Real Heading</h1>
  <p>The first meaningful paragraph.</p>
  <p>The second meaningful paragraph.</p>
</article>
<footer>Footer noise</footer></body></html>
"""

URL_PAYLOAD: dict[str, Any] = {
    "title": "Example Article",
    "content": "CLIENT CONTENT MUST BE IGNORED",
    "source_type": "URL",
    "source_url": "https://example.com/article?utm=1",
}


class _FakeFetcher:
    def __init__(
        self,
        *,
        page: FetchedPage | None = None,
        error: Exception | None = None,
    ) -> None:
        self.page = page
        self.error = error
        self.calls: list[str] = []

    def fetch(self, url: str) -> FetchedPage:
        self.calls.append(url)
        if self.error is not None:
            raise self.error
        assert self.page is not None
        return self.page


def _page(**overrides: object) -> FetchedPage:
    values: dict[str, object] = {
        "html": PAGE_HTML,
        "final_url": "https://example.com/redirected-final",
        "content_type": "text/html",
    }
    values.update(overrides)
    return FetchedPage(**values)  # type: ignore[arg-type]


def _stored_items(database: Database) -> list[KnowledgeItem]:
    with database.session_factory() as session:
        return list(session.scalars(select(KnowledgeItem).order_by(KnowledgeItem.id)).all())


def _patch_fetcher(monkeypatch: pytest.MonkeyPatch, fetcher: _FakeFetcher) -> None:
    monkeypatch.setattr(ingestion, "UrlFetcher", lambda settings: fetcher)


def test_url_ingestion_returns_201_with_expected_response(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    fetcher = _FakeFetcher(page=_page())
    _patch_fetcher(monkeypatch, fetcher)

    response = client.post("/ingest", json=URL_PAYLOAD)

    assert response.status_code == 201
    payload = response.json()
    assert set(payload) == {
        "id",
        "title",
        "content",
        "source_type",
        "source_url",
        "status",
        "created_at",
        "updated_at",
        "indexing_status",
        "indexed_chunk_count",
        "indexing_error_code",
    }
    assert payload["id"] > 0
    assert payload["source_type"] == "URL"
    assert payload["status"] == "COMPLETED"
    assert payload["indexing_status"] == "indexed"
    assert payload["indexed_chunk_count"] == 1
    assert payload["indexing_error_code"] is None
    assert payload["source_url"] == URL_PAYLOAD["source_url"]
    assert fetcher.calls == [URL_PAYLOAD["source_url"]]


def test_extracted_content_is_persisted_and_client_content_ignored(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    fetcher = _FakeFetcher(page=_page())
    _patch_fetcher(monkeypatch, fetcher)

    response = client.post("/ingest", json=URL_PAYLOAD)
    database: Database = client.app.state.database

    stored = _stored_items(database)
    content = response.json()["content"]

    assert len(stored) == 1
    assert content == stored[0].content
    assert "Real Heading" in content
    assert "The first meaningful paragraph." in content
    assert "The second meaningful paragraph." in content
    for noise in ("secret", "color: red", "Navigation noise", "Footer noise"):
        assert noise not in content
    assert "CLIENT CONTENT MUST BE IGNORED" not in content


def test_original_submitted_url_is_persisted_not_final_url(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    fetcher = _FakeFetcher(page=_page(final_url="https://example.com/redirected-final"))
    _patch_fetcher(monkeypatch, fetcher)

    response = client.post("/ingest", json=URL_PAYLOAD)
    stored = _stored_items(client.app.state.database)

    assert response.json()["source_url"] == "https://example.com/article?utm=1"
    assert stored[0].source_url == "https://example.com/article?utm=1"
    assert stored[0].source_url != "https://example.com/redirected-final"
    assert stored[0].source_type is SourceType.URL
    assert stored[0].status is ItemStatus.COMPLETED


def test_supplied_title_takes_precedence(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_fetcher(monkeypatch, _FakeFetcher(page=_page()))

    response = client.post("/ingest", json=URL_PAYLOAD)

    assert response.json()["title"] == "Example Article"


def test_falls_back_to_page_title_when_title_omitted(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_fetcher(monkeypatch, _FakeFetcher(page=_page()))

    payload = dict(URL_PAYLOAD)
    payload.pop("title")
    response = client.post("/ingest", json=payload)

    assert response.json()["title"] == "Extracted Page Title"


def test_falls_back_to_hostname_when_no_title_available(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_fetcher(
        monkeypatch,
        _FakeFetcher(page=_page(html="<html><body><article><p>Body only.</p></article></body></html>")),
    )

    payload = dict(URL_PAYLOAD)
    payload.pop("title")
    response = client.post("/ingest", json=payload)

    assert response.json()["title"] == "example.com"


def test_url_item_with_blank_content_is_accepted(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_fetcher(monkeypatch, _FakeFetcher(page=_page()))

    response = client.post("/ingest", json={**URL_PAYLOAD, "content": ""})

    assert response.status_code == 201
    assert response.json()["content"] != ""


@pytest.mark.parametrize(
    "error",
    [
        FetchHttpError("HTTP 404"),
        FetchTimeoutError("timed out"),
        FetchRedirectError("Too many redirects"),
    ],
)
def test_fetch_failure_returns_502_and_creates_no_item(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    error: Exception,
) -> None:
    _patch_fetcher(monkeypatch, _FakeFetcher(error=error))

    response = client.post("/ingest", json=URL_PAYLOAD)
    stored = _stored_items(client.app.state.database)

    assert response.status_code == 502
    assert response.json()["error"]["code"] == "upstream_error"
    assert "stack" not in str(response.json()).lower()
    assert stored == []


def test_unsafe_url_mapped_to_400_and_no_item(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_fetcher(monkeypatch, _FakeFetcher(error=UnsafeUrlError("private target")))

    response = client.post("/ingest", json=URL_PAYLOAD)
    stored = _stored_items(client.app.state.database)

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "unsafe_url"
    assert stored == []


def test_real_unsafe_url_is_rejected_without_network_access(client: TestClient) -> None:
    # No fetcher mock here: a private IP literal is rejected by SSRF validation
    # before any socket is opened, so no internal service is contacted.
    response = client.post(
        "/ingest",
        json={
            "content": "",
            "source_type": "URL",
            "source_url": "http://127.0.0.1:8080/admin",
        },
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "unsafe_url"
    assert _stored_items(client.app.state.database) == []


def test_note_ingestion_remains_unchanged_alongside_url_support(client: TestClient) -> None:
    note_response = client.post(
        "/ingest",
        json={
            "title": "A note",
            "content": "  verbatim note content  ",
            "source_type": "NOTE",
        },
    )
    stored = _stored_items(client.app.state.database)

    assert note_response.status_code == 201
    assert note_response.json()["content"] == "  verbatim note content  "
    assert note_response.json()["source_type"] == "NOTE"
    assert note_response.json()["source_url"] is None
    assert len(stored) == 1
    assert stored[0].content == "  verbatim note content  "
