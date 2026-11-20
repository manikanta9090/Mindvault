"""Knowledge item ingestion endpoint (plain-text notes and web URLs)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.knowledge_item import IngestResponse, KnowledgeItemCreate, KnowledgeItemResponse
from app.services.ingest_workflow import ingest_and_index

router = APIRouter(tags=["ingestion"])


@router.post(
    "/ingest",
    response_model=IngestResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Ingest a note or web page and index it automatically",
    description=(
        "NOTE items are stored verbatim. URL items are fetched server-side and "
        "their readable text is extracted. The saved item and the automatic "
        "search-indexing outcome are reported separately."
    ),
)
def create_note(
    payload: KnowledgeItemCreate,
    request: Request,
    session: Annotated[Session, Depends(get_db)],
) -> IngestResponse:
    result = ingest_and_index(
        session,
        payload,
        settings=request.app.state.settings,
        embedder=request.app.state.embedder,
        vector_store=request.app.state.vector_store,
    )
    item = KnowledgeItemResponse.model_validate(result.item)
    return IngestResponse(
        **item.model_dump(),
        indexing_status=result.indexing.status,
        indexed_chunk_count=result.indexing.chunk_count,
        indexing_error_code=result.indexing.error_code,
    )
