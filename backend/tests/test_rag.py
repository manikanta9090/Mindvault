"""Tests for grounded RAG answering and citation validation."""

from __future__ import annotations

import httpx2
import pytest

from app.core.config import Settings
from app.services.llm import LLMUpstreamError, MissingLLMConfigurationError
from app.services.rag import (
    NO_RELEVANT_INFORMATION_ANSWER,
    answer_question,
    remove_invalid_citations,
)
from tests.rag_helpers import FakeLLMProvider, make_result, retrieval_stub


def test_answer_question_uses_grounding_prompt_and_returns_source_map(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    results = [
        make_result(
            item_id=7,
            title="Node.js",
            text="Node.js is a JavaScript runtime.",
        )
    ]
    monkeypatch.setattr("app.services.rag.retrieve_chunks", retrieval_stub(results))
    provider = FakeLLMProvider("Node.js is a JavaScript runtime [1].")

    response = answer_question(
        None,  # type: ignore[arg-type] - retrieval is stubbed
        "What did I save about Node.js?",
        vector_store=None,  # type: ignore[arg-type] - retrieval is stubbed
        provider=provider,
        settings=Settings(),
    )

    assert response.answer == "Node.js is a JavaScript runtime [1]."
    assert [source.citation_id for source in response.sources] == ["[1]"]
    assert response.sources[0].item_id == 7
    assert response.sources[0].title == "Node.js"
    assert response.sources[0].snippet == "Node.js is a JavaScript runtime."

    system_prompt, user_prompt = provider.last_call
    assert "only" in system_prompt.lower()
    assert "untrusted" in system_prompt.lower()
    assert "ignore" in system_prompt.lower()
    assert "outside knowledge" in system_prompt.lower()
    assert "What did I save about Node.js?" in user_prompt
    assert "[1]" in user_prompt
    assert "Node.js is a JavaScript runtime." in user_prompt


def test_answer_question_removes_invalid_citations_but_keeps_mapping(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    results = [
        make_result(item_id=1, title="First", text="First fact."),
        make_result(item_id=2, title="Second", text="Second fact."),
    ]
    monkeypatch.setattr("app.services.rag.retrieve_chunks", retrieval_stub(results))
    provider = FakeLLMProvider("Valid [1] and invalid [9].")

    response = answer_question(
        None,  # type: ignore[arg-type]
        "Facts?",
        vector_store=None,  # type: ignore[arg-type]
        provider=provider,
        settings=Settings(),
    )

    assert response.answer == "Valid [1] and invalid."
    assert "[9]" not in response.answer
    assert [source.citation_id for source in response.sources] == ["[1]", "[2]"]


def test_remove_invalid_citations_accepts_only_known_ids() -> None:
    answer = "[1] yes, [2] yes, [3] no, [99] no"

    cleaned = remove_invalid_citations(answer, {"[1]", "[2]"})

    assert cleaned == "[1] yes, [2] yes, no, no"


def test_empty_retrieval_returns_no_information_without_provider_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.services.rag.retrieve_chunks", retrieval_stub([]))
    provider = FakeLLMProvider("This must never be returned.")

    response = answer_question(
        None,  # type: ignore[arg-type]
        "Anything?",
        vector_store=None,  # type: ignore[arg-type]
        provider=provider,
        settings=Settings(),
    )

    assert response.answer == NO_RELEVANT_INFORMATION_ANSWER
    assert response.sources == []
    assert provider.calls == []


def test_missing_key_is_reported_only_after_retrieval(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.services.rag.retrieve_chunks",
        retrieval_stub([make_result(item_id=1, text="Backed by a saved item.")]),
    )

    with pytest.raises(MissingLLMConfigurationError):
        answer_question(
            None,  # type: ignore[arg-type]
            "Question?",
            vector_store=None,  # type: ignore[arg-type]
            settings=Settings(),
        )


def test_provider_timeout_is_mapped_to_upstream_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.services.rag.retrieve_chunks",
        retrieval_stub([make_result(item_id=1, text="Backed by a saved item.")]),
    )
    provider = FakeLLMProvider(error=httpx2.ConnectTimeout("simulated timeout"))

    with pytest.raises(LLMUpstreamError):
        answer_question(
            None,  # type: ignore[arg-type]
            "Question?",
            vector_store=None,  # type: ignore[arg-type]
            provider=provider,
            settings=Settings(),
        )
