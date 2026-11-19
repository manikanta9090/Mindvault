"""Knowledge item listing endpoint."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models import ItemStatus, SourceType
from app.schemas.knowledge_item import KnowledgeItemListResponse
from app.services.listing import list_items

router = APIRouter(tags=["items"])


@router.get(
    "/items",
    response_model=KnowledgeItemListResponse,
    summary="List saved knowledge items",
    description=(
        "Returns a filtered, newest-first page of saved notes and URLs. "
        "The total counts every matching record, not just the current page."
    ),
)
def get_items(
    session: Annotated[Session, Depends(get_db)],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
    source_type: Annotated[SourceType | None, Query()] = None,
    status: Annotated[ItemStatus | None, Query()] = None,
) -> KnowledgeItemListResponse:
    return list_items(
        session,
        limit=limit,
        offset=offset,
        source_type=source_type,
        status=status,
    )
