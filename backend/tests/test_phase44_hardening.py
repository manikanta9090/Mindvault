"""API/configuration/logging hardening checks for Phase 4.4."""

from __future__ import annotations

import logging
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.config import (
    DEFAULT_LLM_MODEL,
    DEFAULT_LLM_TIMEOUT_SECONDS,
    Settings,
)
from app.main import create_app
from app.services.llm import LLMUpstreamError, MissingLLMConfigurationError
from tests.phase44_helpers import KeywordEmbedder, index_item, settings_for
from tests.rag_helpers import FakeLLMProvider


def test_logs_do_not_expose_key_question_answer_or_saved_content(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    secret = "groq-secret-do-not-log"
    question = "What did I save about Node.js?"
    saved_text = "Node.js is a uniquely identifiable runtime detail."
    answer = "Grounded answer [1]."

    settings = settings_for(tmp_path, groq_api_key=secret)
    app = create_app(settings)
    app.state.embedder = KeywordEmbedder()
    app.state.llm_provider = FakeLLMProvider(answer)

    with caplog.at_level(logging.INFO, logger="mindvault"):
        with TestClient(app) as client:
            created = client.post(
                "/ingest",
                json={
                    "title": "Node.js runtime",
                    "content": saved_text,
                    "source_type": "NOTE",
                },
            )
            assert created.status_code == 201
            index_item(app, created.json()["id"])
            response = client.post("/query", json={"question": question})

    assert response.status_code == 200
    logged = caplog.text
    for sensitive in (secret, question, saved_text, answer, "Bearer"):
        assert sensitive not in logged


def test_configuration_defaults_and_error_messages_are_safe() -> None:
    settings = Settings()

    assert settings.llm_provider == "groq"
    assert settings.llm_model == DEFAULT_LLM_MODEL
    assert settings.llm_timeout_seconds == DEFAULT_LLM_TIMEOUT_SECONDS
    assert settings.llm_context_max_chars == 12_000
    assert settings.chunk_size_tokens == 256
    assert settings.chunk_overlap_tokens == 60
    assert settings.retrieval_top_k == 8
    assert settings.fetch_timeout_seconds == 10.0
    assert settings.fetch_max_bytes == 2_000_000
    assert settings.fetch_max_redirects == 3
    assert settings.groq_api_key is None

    missing = MissingLLMConfigurationError().message.lower()
    upstream = LLMUpstreamError().message.lower()
    assert "key" not in missing
    assert "groq" not in missing
    assert "bearer" not in upstream
    assert "timeout" not in upstream


def test_invalid_query_payload_uses_standard_error_schema(client: TestClient) -> None:
    response = client.post("/query", json={"question": "   "})

    assert response.status_code == 422
    error = response.json()["error"]
    assert set(error) == {"code", "message", "details"}
    assert error["code"] == "validation_error"
    assert error["message"] == "Request validation failed."
    assert all(set(item) == {"location", "message"} for item in error["details"])


def test_dns_rebinding_limitation_is_documented() -> None:
    readme = (Path(__file__).resolve().parents[2] / "README.md").read_text(encoding="utf-8")
    lowered = readme.lower()

    assert "dns-rebinding" in lowered
    assert "not provide complete ssrf protection" in lowered
