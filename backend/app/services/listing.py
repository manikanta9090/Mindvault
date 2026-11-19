"""Read-side service for paginated knowledge item listings.

Filtering, counting, and pagination all happen in SQL. The service returns a
ready-to-serialize response model so the route stays free of query logic.
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import ItemStatus, KnowledgeItem, SourceType
from app.schemas.knowledge_item import KnowledgeItemListResponse, KnowledgeItemResponse


def list_items(
    session: Session,
    *,
    limit: int = 20,
    offset: int = 0,
    source_type: SourceType | None = None,
    status: ItemStatus | None = None,
) -> KnowledgeItemListResponse:
    """Return one page of matching items plus the total number of matches.

    The count is computed from the filtered statement before ``limit`` and
    ``offset`` are applied, so ``total`` describes the whole result set rather
    than the current page. Exactly two queries are issued regardless of page
    size.
    """

    conditions = []
    if source_type is not None:
        conditions.append(KnowledgeItem.source_type == source_type)
    if status is not None:
        conditions.append(KnowledgeItem.status == status)

    count_statement = select(func.count()).select_from(KnowledgeItem)
    if conditions:
        count_statement = count_statement.where(*conditions)
    total = int(session.scalar(count_statement) or 0)

    page_statement = select(KnowledgeItem)
    if conditions:
        page_statement = page_statement.where(*conditions)
    page_statement = (
        page_statement.order_by(KnowledgeItem.created_at.desc(), KnowledgeItem.id.desc())
        .limit(limit)
        .offset(offset)
    )
    items = [
        KnowledgeItemResponse.model_validate(item)
        for item in session.scalars(page_statement).all()
    ]

    return KnowledgeItemListResponse(
        items=items,
        total=total,
        limit=limit,
        offset=offset,
    )
