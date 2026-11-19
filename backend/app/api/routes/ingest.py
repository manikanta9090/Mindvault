"""Plain-text note ingestion endpoint."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.knowledge_item import KnowledgeItemCreate, KnowledgeItemResponse
from app.services.ingestion import ingest_note

router = APIRouter(tags=["ingestion"])


@router.post(
    "/ingest",
    response_model=KnowledgeItemResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Ingest a plain-text note",
    description="Saves a plain-text note synchronously; URL ingestion is not supported yet.",
)
def create_note(
    payload: KnowledgeItemCreate,
    session: Annotated[Session, Depends(get_db)],
) -> KnowledgeItem:
    return ingest_note(session, payload)
