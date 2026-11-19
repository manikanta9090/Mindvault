"""Ingestion services orchestrating validation, fetching, and persistence."""

from __future__ import annotations

from urllib.parse import urlsplit

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AppError
from app.core.logging import logger
from app.models import ItemStatus, KnowledgeItem, SourceType
from app.schemas.knowledge_item import KnowledgeItemCreate
from app.services.html_extractor import extract_page
from app.services.url_fetcher import FetchedPage, UrlFetchError, UrlFetcher
from app.services.url_safety import UnsafeUrlError


class UnsupportedSourceTypeError(AppError):
    """The requested source type cannot be ingested by this endpoint."""

    status_code = 400
    code = "unsupported_source_type"
    default_message = "Only NOTE and URL items can be ingested by this endpoint."


class UnsafeUrlAppError(AppError):
    """The submitted URL is not an allowed fetch target."""

    status_code = 400
    code = "unsafe_url"
    default_message = "The supplied URL cannot be fetched."


class UrlFetchAppError(AppError):
    """The remote page could not be fetched or extracted."""

    status_code = 502
    code = "upstream_error"
    default_message = "The URL could not be fetched. Please try again later."


def _persist(session: Session, item: KnowledgeItem) -> KnowledgeItem:
    """Commit and refresh one item, rolling back if persistence fails."""

    try:
        session.add(item)
        session.commit()
        session.refresh(item)
    except Exception:
        session.rollback()
        raise
    return item


def ingest_note(session: Session, payload: KnowledgeItemCreate) -> KnowledgeItem:
    """Persist a validated note verbatim and return the refreshed ORM object."""

    if payload.source_type is not SourceType.NOTE:
        raise UnsupportedSourceTypeError()

    return _persist(
        session,
        KnowledgeItem(
            title=payload.title,
            content=payload.content,
            source_type=SourceType.NOTE,
            source_url=payload.source_url,
            status=ItemStatus.COMPLETED,
        ),
    )


def ingest_url(
    session: Session,
    payload: KnowledgeItemCreate,
    fetcher: UrlFetcher | None = None,
) -> KnowledgeItem:
    """Fetch, extract, and persist a URL item.

    Client-provided content is deliberately ignored; the submitted URL is
    stored exactly as supplied, even if fetching followed redirects.
    """

    if payload.source_type is not SourceType.URL or payload.source_url is None:
        raise UnsupportedSourceTypeError()

    submitted_url = payload.source_url
    active_fetcher = fetcher or UrlFetcher(get_settings())

    try:
        fetched: FetchedPage = active_fetcher.fetch(submitted_url)
    except UnsafeUrlError as exc:
        raise UnsafeUrlAppError() from exc
    except UrlFetchError as exc:
        logger.warning("url_fetch_failed", extra={"error_type": type(exc).__name__})
        raise UrlFetchAppError() from exc

    extracted = extract_page(fetched.html)
    title = payload.title or extracted.title or urlsplit(submitted_url).hostname

    return _persist(
        session,
        KnowledgeItem(
            title=title,
            content=extracted.text,
            source_type=SourceType.URL,
            source_url=submitted_url,
            status=ItemStatus.COMPLETED,
        ),
    )
