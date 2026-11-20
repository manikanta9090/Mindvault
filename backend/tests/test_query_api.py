"""Tests for POST /query, its schemas, and API error mapping."""

from __future__ import annotations

import logging

import httpx2
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.models import SourceType
from app.schemas.query import QueryRequest, QueryResponse, QuerySource
from app.services.rag import NO_RELEVANT_INFORMATION_ANSWER
from tests.rag_helpers import FakeLLMProvider, make_result, retrieval_stub


def test_query_returns_grounded_answer_and_source_metadata(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    question = "What did I save about Node.js?"
    saved_text = "Node.js is a JavaScript runtime."
    monkeypatch.setattr(
        "app.services.rag.retrieve_chunks",
        retrieval_stub(
            [
                make_result(
                    item_id=23,
                    title="Node.js overview",
                    text=saved_text,
                    source_type=SourceType.URL,
                    source_url="https://example.com/node",
                )
            ]
        ),
    )
    provider = FakeLLMProvider("Node.js is a JavaScript runtime [1].")
    client.app.state.llm_provider = provider

    with caplog.at_level(logging.INFO, logger="mindvault"):
        response = client.post("/query", json={"question": question})

    assert response.status_code == 200
    payload = response.json()
    assert set(payload) == {"answer", "sources"}
    assert payload["answer"] == "Node.js is a JavaScript runtime [1]."
    assert len(payload["sources"]) == 1

    source = payload["sources"][0]
    assert set(source) == {
        "item_id",
        "title",
        "source_type",
        "source_url",
        "snippet",
        "citation_id",
    }
    assert source["item_id"] == 23
    assert source["title"] == "Node.js overview"
    assert source["source_type"] == "URL"
    assert source["source_url"] == "https://example.com/node"
    assert source["snippet"] == saved_text
    assert source["citation_id"] == "[1]"
    assert len(provider.calls) == 1
    assert question not in caplog.text
    assert saved_text not in caplog.text


def test_query_with_empty_retrieval_does_not_need_a_provider(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("app.services.rag.retrieve_chunks", retrieval_stub([]))
    provider = FakeLLMProvider("Should never be called.")
    client.app.state.llm_provider = provider

    response = client.post("/query", json={"question": "Anything saved?"})

    assert response.status_code == 200
    assert response.json() == {
        "answer": NO_RELEVANT_INFORMATION_ANSWER,
        "sources": [],
    }
    assert provider.calls == []


def test_missing_api_key_affects_query_but_not_startup_or_health(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "app.services.rag.retrieve_chunks",
        retrieval_stub([make_result(item_id=1, text="Backed by a saved item.")]),
    )
    client.app.state.llm_provider = None

    assert client.get("/health").status_code == 200
    response = client.post("/query", json={"question": "A question?"})
    payload = response.json()

    assert response.status_code == 503
    assert payload["error"]["code"] == "service_unavailable"
    assert "api key" not in payload["error"]["message"].lower()
    assert "groq" not in payload["error"]["message"].lower()


def test_provider_timeout_maps_to_upstream_error(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "app.services.rag.retrieve_chunks",
        retrieval_stub([make_result(item_id=1, text="Backed by a saved item.")]),
    )
    client.app.state.llm_provider = FakeLLMProvider(
        error=httpx2.ConnectTimeout("simulated timeout")
    )

    response = client.post("/query", json={"question": "A question?"})

    assert response.status_code == 502
    assert response.json()["error"]["code"] == "upstream_error"
    assert "timeout" not in response.text.lower()


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"question": ""},
        {"question": "   "},
        {"question": 42},
    ],
)
def test_invalid_question_returns_standard_validation_error(
    client: TestClient, payload: dict[object, object]
) -> None:
    response = client.post("/query", json=payload)

    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "validation_error"
    assert error["message"] == "Request validation failed."


def test_query_schemas_validate_request_and_response_boundaries() -> None:
    assert QueryRequest.model_validate({"question": "Valid question"}).question == "Valid question"
    with pytest.raises(ValidationError):
        QueryRequest.model_validate({"question": "   "})

    response = QueryResponse.model_validate(
        {
            "answer": "An answer [1].",
            "sources": [
                {
                    "item_id": 5,
                    "title": "A note",
                    "source_type": "NOTE",
                    "source_url": None,
                    "snippet": "A snippet.",
                    "citation_id": "[1]",
                }
            ],
        }
    )
    assert response.sources[0].source_type is SourceType.NOTE
    assert response.model_dump(mode="json")["sources"][0]["citation_id"] == "[1]"

    with pytest.raises(ValidationError):
        QuerySource.model_validate(
            {
                "item_id": 0,
                "title": None,
                "source_type": "NOTE",
                "snippet": "A snippet.",
                "citation_id": "1",
            }
        )


def test_existing_ingestion_and_listing_still_work(client: TestClient) -> None:
    created = client.post(
        "/ingest",
        json={
            "title": "Still working",
            "content": "Ingestion is unaffected by query integration.",
            "source_type": "NOTE",
        },
    )
    listed = client.get("/items")

    assert created.status_code == 201
    assert listed.status_code == 200
    payload = listed.json()
    assert payload["total"] == 1
    assert payload["items"][0]["id"] == created.json()["id"]


def test_query_endpoint_is_present_in_openapi_schema(client: TestClient) -> None:
    schema = client.get("/openapi.json").json()

    assert "post" in schema["paths"]["/query"]
    assert "QueryRequest" in schema["components"]["schemas"]
    assert "QueryResponse" in schema["components"]["schemas"]
