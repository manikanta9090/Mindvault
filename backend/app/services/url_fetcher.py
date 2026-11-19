"""Bounded, SSRF-checked fetching of remote HTML pages.

Redirects are followed manually so every destination is revalidated before the
next request. Response bodies are read in bounded chunks, never as one
unbounded buffer.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Final
from urllib.parse import urljoin

import httpx2

from app.core.config import Settings
from app.services.url_safety import UnsafeUrlError, validate_url_target

_REDIRECT_STATUSES: Final[frozenset[int]] = frozenset({301, 302, 303, 307, 308})
_HTML_CONTENT_TYPES: Final[frozenset[str]] = frozenset({"text/html", "application/xhtml+xml"})
_CHARSET_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"charset\s*=\s*[\"']?([^;\"'\s]+)", re.IGNORECASE
)
_USER_AGENT: Final[str] = "MindVault/1.0 (URL ingestion)"


class UrlFetchError(Exception):
    """Base class for expected URL fetching failures."""


class FetchHttpError(UrlFetchError):
    """The remote server returned an unsuccessful status code."""


class FetchTimeoutError(UrlFetchError):
    """The request timed out."""


class FetchNetworkError(UrlFetchError):
    """A transport-level failure occurred."""


class FetchContentTypeError(UrlFetchError):
    """The response was not an HTML document."""


class FetchSizeLimitError(UrlFetchError):
    """The response exceeded the configured size limit."""


class FetchRedirectError(UrlFetchError):
    """The redirect chain was invalid or too long."""


@dataclass(frozen=True)
class FetchedPage:
    """The decoded HTML body of a successfully fetched page."""

    html: str
    final_url: str
    content_type: str


def decode_html(body: bytes, content_type: str) -> str:
    """Decode a response body using the declared charset with safe fallbacks."""

    match = _CHARSET_PATTERN.search(content_type)
    candidates = [match.group(1)] if match else []
    candidates.extend(("utf-8", "cp1252"))

    for codec in candidates:
        try:
            return body.decode(codec)
        except (LookupError, UnicodeDecodeError):
            continue
    return body.decode("utf-8", errors="replace")


class UrlFetcher:
    """Fetch HTML with validation, bounded reads, and safe redirects."""

    def __init__(
        self,
        settings: Settings,
        transport: httpx2.BaseTransport | None = None,
    ) -> None:
        self._settings = settings
        self._transport = transport

    def fetch(self, url: str) -> FetchedPage:
        """Fetch ``url`` and return its decoded HTML, or raise a typed error."""

        current_url = url
        max_redirects = self._settings.fetch_max_redirects

        for redirect_count in range(max_redirects + 1):
            # DNS/IP validation is repeated for every hop, including the first.
            validate_url_target(current_url)

            with httpx2.Client(
                follow_redirects=False,
                timeout=self._settings.fetch_timeout_seconds,
                headers={"User-Agent": _USER_AGENT},
                transport=self._transport,
            ) as client:
                try:
                    with client.stream("GET", current_url) as response:
                        if response.status_code in _REDIRECT_STATUSES:
                            location = response.headers.get("location")
                            if not location:
                                raise FetchRedirectError("A redirect response had no Location.")
                            if redirect_count == max_redirects:
                                raise FetchRedirectError("Too many redirects.")
                            current_url = urljoin(str(response.url), location)
                            continue

                        if not 200 <= response.status_code < 300:
                            raise FetchHttpError(
                                f"The remote server returned HTTP {response.status_code}."
                            )

                        declared_type = response.headers.get("content-type", "")
                        content_type = declared_type.split(";", 1)[0].strip().lower()
                        if content_type not in _HTML_CONTENT_TYPES:
                            raise FetchContentTypeError("The URL did not return HTML content.")

                        declared_length = response.headers.get("content-length", "")
                        if declared_length.isdigit() and int(declared_length) > self._settings.fetch_max_bytes:
                            raise FetchSizeLimitError("The response is too large.")

                        body = self._read_bounded(response)
                        return FetchedPage(
                            html=decode_html(body, declared_type),
                            final_url=str(response.url),
                            content_type=content_type,
                        )
                except UnsafeUrlError:
                    raise
                except UrlFetchError:
                    raise
                except httpx2.TimeoutException as exc:
                    raise FetchTimeoutError("The request timed out.") from exc
                except httpx2.RequestError as exc:
                    raise FetchNetworkError("The URL could not be reached.") from exc

        raise FetchRedirectError("Too many redirects.")

    def _read_bounded(self, response: httpx2.Response) -> bytes:
        """Accumulate body chunks, aborting as soon as the limit is exceeded."""

        chunks: list[bytes] = []
        total = 0
        for chunk in response.iter_bytes():
            total += len(chunk)
            if total > self._settings.fetch_max_bytes:
                raise FetchSizeLimitError("The response is too large.")
            chunks.append(chunk)
        return b"".join(chunks)
