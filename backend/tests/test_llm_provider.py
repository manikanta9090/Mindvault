"""Tests for the Groq adapter and lazy provider configuration."""

from __future__ import annotations

import json
from typing import Any

import httpx2
import pytest

from app.core.config import (
    DEFAULT_LLM_MODEL,
    LLM_PROVIDER_GROQ,
    Settings,
)
from app.services.llm import (
    GROQ_OPENAI_BASE_URL,
    GroqChatProvider,
    LLMUpstreamError,
    MissingLLMConfigurationError,
    UnsupportedLLMProviderError,
    build_llm_provider,
)


def test_groq_provider_sends_compatible_payload_and_returns_message() -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx2.Request) -> httpx2.Response:
        captured["request"] = request
        return httpx2.Response(
            200,
            json={"choices": [{"message": {"role": "assistant", "content": "Node.js is runtime."}}]},
        )

    provider = GroqChatProvider(
        "unit-test-key",
        DEFAULT_LLM_MODEL,
        5.0,
        transport=httpx2.MockTransport(handler),
    )

    assert provider.complete("SYSTEM", "USER") == "Node.js is runtime."
    assert GROQ_OPENAI_BASE_URL == "https://api.groq.com/openai/v1"

    request: httpx2.Request = captured["request"]
    assert request.url.path.endswith("/chat/completions")
    assert request.headers["Authorization"] == "Bearer unit-test-key"
    payload = json.loads(request.content)
    assert set(payload) == {"model", "messages", "temperature"}
    assert payload["model"] == DEFAULT_LLM_MODEL
    assert payload["temperature"] == 0
    assert payload["messages"] == [
        {"role": "system", "content": "SYSTEM"},
        {"role": "user", "content": "USER"},
    ]


def test_groq_provider_maps_timeout_to_upstream_error() -> None:
    def handler(_: httpx2.Request) -> httpx2.Response:
        raise httpx2.ReadTimeout("simulated timeout")

    provider = GroqChatProvider(
        "unit-test-key",
        DEFAULT_LLM_MODEL,
        5.0,
        transport=httpx2.MockTransport(handler),
    )

    with pytest.raises(LLMUpstreamError):
        provider.complete("SYSTEM", "USER")


def test_groq_provider_maps_http_and_malformed_responses_to_upstream_error() -> None:
    http_failure = GroqChatProvider(
        "unit-test-key",
        DEFAULT_LLM_MODEL,
        5.0,
        transport=httpx2.MockTransport(lambda _: httpx2.Response(500, json={"error": "failed"})),
    )
    malformed = GroqChatProvider(
        "unit-test-key",
        DEFAULT_LLM_MODEL,
        5.0,
        transport=httpx2.MockTransport(lambda _: httpx2.Response(200, json={"choices": []})),
    )

    with pytest.raises(LLMUpstreamError):
        http_failure.complete("SYSTEM", "USER")
    with pytest.raises(LLMUpstreamError):
        malformed.complete("SYSTEM", "USER")


def test_provider_requires_credentials() -> None:
    with pytest.raises(MissingLLMConfigurationError):
        GroqChatProvider("", DEFAULT_LLM_MODEL, 5.0)


def test_build_provider_uses_groq_only_when_key_is_present() -> None:
    settings = Settings(
        llm_provider=LLM_PROVIDER_GROQ,
        llm_model=DEFAULT_LLM_MODEL,
        groq_api_key="configured-key",
    )

    provider = build_llm_provider(settings)

    assert isinstance(provider, GroqChatProvider)
    assert provider.model == DEFAULT_LLM_MODEL


def test_build_provider_rejects_missing_key_and_unknown_provider() -> None:
    with pytest.raises(MissingLLMConfigurationError):
        build_llm_provider(Settings())

    with pytest.raises(UnsupportedLLMProviderError):
        build_llm_provider(Settings(llm_provider="unknown", groq_api_key="configured-key"))


def test_settings_keep_api_key_out_of_repr_and_serialization() -> None:
    settings = Settings(groq_api_key="top-secret-key")

    assert "top-secret-key" not in repr(settings)
    assert "groq_api_key" not in settings.model_dump()
    assert settings.groq_api_key is not None
    assert settings.groq_api_key.get_secret_value() == "top-secret-key"


def test_llm_environment_variables_are_loaded(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MINDVAULT_LLM_PROVIDER", "GROQ")
    monkeypatch.setenv("MINDVAULT_GROQ_API_KEY", "env-secret-key")
    monkeypatch.setenv("MINDVAULT_LLM_MODEL", "chosen-model")
    monkeypatch.setenv("MINDVAULT_LLM_TIMEOUT", "12.5")
    monkeypatch.setenv("MINDVAULT_LLM_CONTEXT_MAX_CHARS", "8000")

    settings = Settings.from_env()

    assert settings.llm_provider == LLM_PROVIDER_GROQ
    assert settings.groq_api_key is not None
    assert settings.groq_api_key.get_secret_value() == "env-secret-key"
    assert settings.llm_model == "chosen-model"
    assert settings.llm_timeout_seconds == 12.5
    assert settings.llm_context_max_chars == 8_000
    assert "env-secret-key" not in repr(settings)
