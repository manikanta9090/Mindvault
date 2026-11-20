"""Question-answering endpoint backed by the retrieval and RAG services."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.database import get_db
from app.schemas.query import QueryRequest, QueryResponse
from app.services.rag import answer_question
from app.services.vector_store import VectorStore, get_vector_store

router = APIRouter(tags=["query"])


@router.post(
    "/query",
    response_model=QueryResponse,
    summary="Ask a question about saved knowledge",
    description=(
        "Retrieves relevant saved chunks, builds a bounded cited context, and "
        "returns a grounded answer with the source items used for inspection."
    ),
)
def ask_question(
    payload: QueryRequest,
    request: Request,
    session: Annotated[Session, Depends(get_db)],
    vector_store: Annotated[VectorStore, Depends(get_vector_store)],
) -> QueryResponse:
    settings: Settings = getattr(request.app.state, "settings", None) or get_settings()
    provider = getattr(request.app.state, "llm_provider", None)
    embedder = getattr(request.app.state, "embedder", None)
    return answer_question(
        session,
        payload.question,
        vector_store=vector_store,
        provider=provider,
        embedder=embedder,
        settings=settings,
    )
