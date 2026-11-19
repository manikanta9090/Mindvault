"""Extract readable text and metadata from downloaded HTML.

BeautifulSoup with the standard-library ``html.parser`` is used deliberately:
it is small, maintained, and tolerant of malformed markup without pulling in a
native parser or a full readability engine.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Final

from bs4 import BeautifulSoup
from bs4.element import Tag

_NOISE_TAG_NAMES: Final = frozenset(
    {
        "script",
        "style",
        "noscript",
        "template",
        "nav",
        "footer",
        "header",
        "aside",
        "form",
        "iframe",
        "svg",
        "canvas",
        "button",
        "select",
        "option",
    }
)
_TEXT_TAG_NAMES: Final = (
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "p",
    "li",
    "blockquote",
    "pre",
)
# Token-bounded so innocuous names such as "headline" or "padding" survive,
# while "ad-banner", "cookie-banner" and "sidebar" are removed. BeautifulSoup
# applies this pattern to each individual class token and to the whole id.
_NOISE_NAME_PATTERN: Final = re.compile(
    r"(?:^|[-_])(?:ads?|advert(?:isement)?|banner|cookie|promo|sponsor(?:ed)?|"
    r"sidebar|nav(?:igation)?|footer|header|menu|social|share|related|popup|modal)"
    r"(?:[-_]|$)",
    re.IGNORECASE,
)
_WHITESPACE_PATTERN: Final = re.compile(r"\s+")


@dataclass(frozen=True)
class ExtractedPage:
    """Title and readable text recovered from an HTML document."""

    title: str | None
    text: str


def _clean(value: str) -> str:
    return _WHITESPACE_PATTERN.sub(" ", value).strip()


def _extract_title(soup: BeautifulSoup) -> str | None:
    candidates: list[str | None] = []

    title_tag = soup.find("title")
    candidates.append(title_tag.get_text(" ", strip=True) if title_tag else None)

    for attributes in (
        {"property": "og:title"},
        {"name": "twitter:title"},
    ):
        meta = soup.find("meta", attrs=attributes)
        content = meta.get("content") if isinstance(meta, Tag) else None
        candidates.append(content if isinstance(content, str) else None)

    heading = soup.find("h1")
    candidates.append(heading.get_text(" ", strip=True) if heading else None)

    for candidate in candidates:
        cleaned = _clean(candidate) if candidate else ""
        if cleaned:
            return cleaned
    return None


def _remove_boilerplate(soup: BeautifulSoup) -> None:
    for tag in list(soup.find_all(list(_NOISE_TAG_NAMES))):
        tag.decompose()

    noise_candidates = [
        *soup.find_all(attrs={"class": _NOISE_NAME_PATTERN}),
        *soup.find_all(attrs={"id": _NOISE_NAME_PATTERN}),
    ]
    for tag in noise_candidates:
        if tag.parent is not None:
            tag.decompose()

    for tag in list(soup.find_all(attrs={"aria-hidden": "true"})):
        if tag.parent is not None:
            tag.decompose()


def _content_root(soup: BeautifulSoup) -> Tag:
    for selector in ("article", "main"):
        found = soup.find(selector)
        if isinstance(found, Tag):
            return found
    role_main = soup.find(attrs={"role": "main"})
    if isinstance(role_main, Tag):
        return role_main
    body = soup.body
    return body if isinstance(body, Tag) else soup


def extract_page(html: str) -> ExtractedPage:
    """Extract a title and de-duplicated readable text from ``html``."""

    soup = BeautifulSoup(html or "", "html.parser")
    title = _extract_title(soup)
    _remove_boilerplate(soup)
    root = _content_root(soup)

    blocks: list[str] = []
    seen: set[str] = set()
    for tag in root.find_all(_TEXT_TAG_NAMES):
        text = _clean(tag.get_text(" ", strip=True))
        if not text or text in seen:
            continue
        seen.add(text)
        blocks.append(text)

    if not blocks:
        fallback = _clean(root.get_text(" ", strip=True))
        if fallback:
            blocks.append(fallback)

    return ExtractedPage(title=title, text="\n\n".join(blocks))
