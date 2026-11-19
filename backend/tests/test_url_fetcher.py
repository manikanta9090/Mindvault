"""Tests for bounded, SSRF-checked HTML fetching using mocked HTTP only."""

from __future__ import annotations

from typing import Callable

import httpx2
import pytest

from app.core.config import Settings
from app.services.url_fetcher import (
    FetchContentTypeError,
    FetchHttpError,
    FetchNetworkError,
    FetchRedirectError,
    FetchSizeLimitError,
    FetchTimeoutError,
    FetchedPage,
    UrlFetcher,
    decode_html,
)
from app.services.url_safety import UnsafeUrlError

# Public literal IP avoids DNS entirely; MockTransport prevents any socket use.
_URL = "http://93.184.216.34/page"
_HTML = b"<html><head><title>Hi</title></head><body><p>Body text.</p></body></html>"
_CONTENT_TYPE = "text/html; charset=utf-8"


def _settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "database_url": "sqlite://",
        "fetch_max_bytes": 1_000,
        "fetch_max_redirects": 3,
        "fetch_timeout_seconds": 2.0,
    }
    values.update(overrides)
    return Settings(**values)  # type: ignore[arg-type]


def _fetcher(
    handler: Callable[[httpx2.Request], httpx2.Response],
    **settings_overrides: object,
) -> UrlFetcher:
    transport = httpx2.MockTransport(handler)
    return UrlFetcher(_settings(**settings_overrides), transport=transport)


def test_successful_html_fetch() -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        assert request.url.path == "/page"
        assert request.headers["user-agent"].startswith("MindVault/")
        return httpx2.Response(200, content=_HTML, headers={"content-type": _CONTENT_TYPE})

    fetched = _fetcher(handler).fetch(_URL)

    assert isinstance(fetched, FetchedPage)
    assert "<title>Hi</title>" in fetched.html
    assert fetched.content_type == "text/html"
    assert fetched.final_url == _URL


def test_non_success_status_raises_fetch_http_error() -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(404, content=b"missing", headers={"content-type": _CONTENT_TYPE})

    with pytest.raises(FetchHttpError, match="404"):
        _fetcher(handler).fetch(_URL)


def test_server_error_status_raises_fetch_http_error() -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(500, content=b"oops", headers={"content-type": _CONTENT_TYPE})

    with pytest.raises(FetchHttpError, match="500"):
        _fetcher(handler).fetch(_URL)


def test_timeout_is_mapped_to_typed_error() -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        raise httpx2.TimeoutException("timed out")

    with pytest.raises(FetchTimeoutError):
        _fetcher(handler).fetch(_URL)


def test_network_error_is_mapped_to_typed_error() -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        raise httpx2.ConnectError("connection refused")

    with pytest.raises(FetchNetworkError):
        _fetcher(handler).fetch(_URL)


@pytest.mark.parametrize(
    "content_type",
    ["application/json", "application/pdf", "image/png", "text/plain", ""],
)
def test_non_html_content_type_is_rejected(content_type: str) -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        headers = {"content-type": content_type} if content_type else {}
        return httpx2.Response(200, content=b"payload", headers=headers)

    with pytest.raises(FetchContentTypeError):
        _fetcher(handler).fetch(_URL)


def test_xhtml_is_accepted() -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(
            200,
            content=b"<html><body><p>x</p></body></html>",
            headers={"content-type": "application/xhtml+xml"},
        )

    assert _fetcher(handler).fetch(_URL).content_type == "application/xhtml+xml"


def test_response_exceeding_size_limit_is_rejected() -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(
            200,
            content=b"x" * 200,
            headers={"content-type": _CONTENT_TYPE},
        )

    with pytest.raises(FetchSizeLimitError):
        _fetcher(handler, fetch_max_bytes=50).fetch(_URL)


def test_oversized_content_length_header_is_rejected_early() -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(
            200,
            content=b"x" * 10,
            headers={"content-type": _CONTENT_TYPE, "content-length": "5000"},
        )

    with pytest.raises(FetchSizeLimitError):
        _fetcher(handler, fetch_max_bytes=50).fetch(_URL)


def test_body_within_limit_is_accepted() -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(
            200,
            content=b"x" * 40,
            headers={"content-type": _CONTENT_TYPE},
        )

    assert _fetcher(handler, fetch_max_bytes=50).fetch(_URL).html == "x" * 40


def test_redirect_limit_is_enforced() -> None:
    requests: list[str] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        requests.append(str(request.url))
        return httpx2.Response(
            302,
            content=b"",
            headers={"location": "http://93.184.216.34/loop"},
        )

    with pytest.raises(FetchRedirectError, match="Too many redirects"):
        _fetcher(handler, fetch_max_redirects=2).fetch(_URL)

    # Initial request + 2 followed hops, then the next redirect is rejected.
    assert len(requests) == 3


def test_redirect_without_location_is_rejected() -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(302, content=b"", headers={"content-type": _CONTENT_TYPE})

    with pytest.raises(FetchRedirectError, match="no Location"):
        _fetcher(handler).fetch(_URL)


def test_redirect_to_internal_ip_is_rejected() -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        if request.url.path == "/page":
            return httpx2.Response(
                302,
                content=b"",
                headers={"location": "http://127.0.0.1/admin"},
            )
        return httpx2.Response(
            200, content=b"secret", headers={"content-type": _CONTENT_TYPE}
        )

    with pytest.raises(UnsafeUrlError):
        _fetcher(handler).fetch(_URL)


def test_valid_redirect_is_followed() -> None:
    visited: list[str] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        visited.append(request.url.path)
        if request.url.path == "/page":
            return httpx2.Response(
                301,
                content=b"",
                headers={"location": "/final?x=1"},
            )
        return httpx2.Response(
            200,
            content=b"<html><body><p>Final</p></body></html>",
            headers={"content-type": _CONTENT_TYPE},
        )

    fetched = _fetcher(handler).fetch(_URL)

    assert visited == ["/page", "/final"]
    assert "Final" in fetched.html
    assert fetched.final_url.endswith("/final?x=1")


def test_relative_redirect_stays_on_same_host() -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        if request.url.path == "/page":
            return httpx2.Response(307, content=b"", headers={"location": "next.html"})
        return httpx2.Response(
            200, content=b"<p>ok</p>", headers={"content-type": _CONTENT_TYPE}
        )

    fetched = _fetcher(handler).fetch(_URL)

    assert fetched.final_url == "http://93.184.216.34/next.html"


def test_unsafe_initial_url_is_rejected_before_any_request() -> None:
    called = False

    def handler(request: httpx2.Request) -> httpx2.Response:
        nonlocal called
        called = True
        return httpx2.Response(200, content=_HTML, headers={"content-type": _CONTENT_TYPE})

    with pytest.raises(UnsafeUrlError):
        _fetcher(handler).fetch("http://127.0.0.1/internal")

    assert called is False


def test_declared_charset_is_used_for_decoding() -> None:
    body = "<html><body><p>Café ☕ 日本語</p></body></html>".encode("cp1252", errors="replace")

    def handler(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(
            200,
            content=body,
            headers={"content-type": "text/html; charset=cp1252"},
        )

    fetched = _fetcher(handler).fetch(_URL)

    assert "Café" in fetched.html


def test_decode_html_replaces_undecodable_bytes() -> None:
    decoded = decode_html(b"\xff\xfe<h1>ok</h1>", "text/html; charset=ascii")

    assert "<h1>ok</h1>" in decoded
