"""Knowledge item ingestion endpoint (plain-text notes and web URLs)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models import KnowledgeItem, SourceType
from app.schemas.knowledge_item import KnowledgeItemCreate, KnowledgeItemResponse
from app.services.ingestion import ingest_note, ingest_url

router = APIRouter(tags=["ingestion"])


@router.post(
    "/ingest",
    response_model=KnowledgeItemResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Ingest a note or web page",
    description=(
        "NOTE items are stored verbatim. URL items are fetched server-side and "
        "their readable text is extracted."
    ),
)
def create_note(
    payload: KnowledgeItemCreate,
    session: Annotated[Session, Depends(get_db)],
) -> KnowledgeItem:
    if payload.source_type is SourceType.URL:
        return ingest_url(session, payload)
    return ingest_note(session, payload)
