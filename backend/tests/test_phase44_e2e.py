"""Deterministic mocked end-to-end RAG evaluation for Phase 4.4.

These tests exercise real SQLite, chunking, indexing, ChromaDB, retrieval, and
HTTP routes. The embedder and LLM provider are offline fakes, so they verify
pipeline wiring and citation integrity, not live semantic quality.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.config import Settings
from app.main import create_app
from app.models import KnowledgeChunk, SourceType
from app.services.retrieval import retrieve_chunks
from app.services.rag import NO_RELEVANT_INFORMATION_ANSWER
from tests.phase44_helpers import (
    FakeUrlFetcher,
    KeywordEmbedder,
    index_item,
    settings_for,
)
from tests.rag_helpers import FakeLLMProvider


def test_note_pipeline_ingest_index_retrieve_answer_and_reindex(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    embedder = KeywordEmbedder()
    provider = FakeLLMProvider("Node.js facts [1] and [9].")
    app = create_app(settings_for(tmp_path))  # no Groq key by design
    app.state.embedder = embedder
    app.state.llm_provider = provider

    with TestClient(app) as client:
        created = client.post(
            "/ingest",
            json={
                "title": "Node.js runtime",
                "content": "Node.js is a JavaScript runtime. Node.js uses an event loop.",
                "source_type": "NOTE",
            },
        )
        assert created.status_code == 201
        item_id = created.json()["id"]

        first = index_item(app, item_id, embedder)
        original_chunk_ids = [chunk.id for chunk in first]
        original_chroma_ids = [chunk.chroma_id for chunk in first]
        assert app.state.vector_store.count() == len(first)

        # Repeated indexing must not create duplicate SQL rows or vectors.
        second = index_item(app, item_id, embedder)
        assert [chunk.id for chunk in second] == original_chunk_ids
        assert [chunk.chroma_id for chunk in second] == original_chroma_ids
        assert app.state.vector_store.count() == len(first)
        with app.state.database.session_factory() as session:
            rows = session.scalars(select(KnowledgeChunk)).all()
        assert len(rows) == len(first)

        response = client.post("/query", json={"question": "What did I save about Node.js?"})
        assert response.status_code == 200
        payload = response.json()
        assert payload["answer"] == "Node.js facts [1] and."
        assert "[9]" not in payload["answer"]
        assert len(payload["sources"]) == 1
        source = payload["sources"][0]
        assert source["item_id"] == item_id
        assert source["title"] == "Node.js runtime"
        assert source["source_type"] == "NOTE"
        assert source["source_url"] is None
        assert source["citation_id"] == "[1]"
        assert "Node.js" in source["snippet"]

        system_prompt, user_prompt = provider.last_call
        assert "Saved knowledge excerpts" in system_prompt
        assert "[1]" in user_prompt
        assert "Node.js is a JavaScript runtime." in user_prompt


def test_url_pipeline_preserves_original_metadata_and_citation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("app.services.ingestion.UrlFetcher", FakeUrlFetcher)
    embedder = KeywordEmbedder()
    app = create_app(settings_for(tmp_path))
    app.state.embedder = embedder
    app.state.llm_provider = FakeLLMProvider("ChromaDB stores embeddings [1].")
    url = "https://example.com/chroma"

    with TestClient(app) as client:
        created = client.post(
            "/ingest",
            json={
                "title": "Client title should not win",
                "content": "ignored client content",
                "source_type": "URL",
                "source_url": url,
            },
        )
        assert created.status_code == 201
        item_id = created.json()["id"]
        assert created.json()["title"] == "Client title should not win"
        assert created.json()["content"] == FakeUrlFetcher.html or "ChromaDB" in created.json()["content"]

        chunks = index_item(app, item_id, embedder)
        assert len(chunks) >= 1

        response = client.post("/query", json={"question": "What did I save about Chroma?"})
        assert response.status_code == 200
        payload = response.json()
        assert payload["answer"] == "ChromaDB stores embeddings [1]."
        assert len(payload["sources"]) == 1
        source = payload["sources"][0]
        assert source["item_id"] == item_id
        assert source["source_type"] == "URL"
        assert source["source_url"] == url
        assert source["citation_id"] == "[1]"
        assert "ChromaDB" in source["snippet"]


def test_quality_evaluation_distinguishes_relevant_unrelated_and_insufficient(
    tmp_path: Path,
) -> None:
    settings = settings_for(tmp_path, retrieval_top_k=3)
    embedder = KeywordEmbedder()
    app = create_app(settings)
    app.state.embedder = embedder
    provider = FakeLLMProvider("A grounded answer [1].")
    app.state.llm_provider = provider

    with TestClient(app) as client:
        items = {
            "note": client.post(
                "/ingest",
                json={
                    "title": "Node.js runtime",
                    "content": "Node.js is a JavaScript runtime.",
                    "source_type": "NOTE",
                },
            ).json()["id"],
            "postgres": client.post(
                "/ingest",
                json={
                    "title": "PostgreSQL notes",
                    "content": "PostgreSQL is a relational database.",
                    "source_type": "NOTE",
                },
            ).json()["id"],
        }
        for item_id in items.values():
            index_item(app, item_id, embedder)

        with app.state.database.session_factory() as session:
            node_hits = retrieve_chunks(
                session,
                "What did I save about Node.js?",
                vector_store=app.state.vector_store,
                embedder=embedder,
                settings=settings,
            )
            unrelated_hits = retrieve_chunks(
                session,
                "What did I save about quantum physics?",
                vector_store=app.state.vector_store,
                embedder=embedder,
                settings=settings,
            )

        assert node_hits
        assert node_hits[0].knowledge_item.id == items["note"]
        # Retrieval has no relevance threshold: unrelated vectors are still the
        # nearest neighbours, so distances are reported rather than "correct".
        assert unrelated_hits
        assert all(hit.distance == pytest.approx(1.0) for hit in unrelated_hits)

        relevant = client.post("/query", json={"question": "What did I save about Node.js?"})
        assert relevant.status_code == 200
        assert relevant.json()["sources"][0]["citation_id"] == "[1]"
        assert relevant.json()["sources"][0]["item_id"] in items.values()

        # Insufficient-context behavior is scripted here; it does not prove the
        # live model would make the same judgement.
        provider.answer = NO_RELEVANT_INFORMATION_ANSWER
        insufficient = client.post(
            "/query", json={"question": "What did I save about quantum physics?"}
        )
        assert insufficient.status_code == 200
        assert insufficient.json()["answer"] == NO_RELEVANT_INFORMATION_ANSWER
        assert insufficient.json()["sources"] != []
