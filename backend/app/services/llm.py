"""Provider abstraction for language-model completions.

The RAG service depends only on :class:`LLMProvider`. Groq is implemented as
one adapter over its OpenAI-compatible chat completions endpoint using the
project's existing ``httpx2`` dependency. Provider construction is lazy so a
missing API key never affects application startup, ingestion, or listing.
"""

from __future__ import annotations

import time
from typing import Any, Protocol, runtime_checkable

import httpx2
from pydantic import SecretStr

from app.core.config import (
    LLM_PROVIDER_GROQ,
    Settings,
    get_settings,
)
from app.core.errors import AppError
from app.core.logging import logger

GROQ_OPENAI_BASE_URL = "https://api.groq.com/openai/v1"
_GROQ_CHAT_COMPLETIONS_PATH = "chat/completions"


class LLMError(AppError):
    """Base class for expected language-model failures."""


class LLMConfigurationError(LLMError):
    """Question answering is not usable with the current configuration."""

    status_code = 503
    code = "service_unavailable"
    default_message = "Question answering is not available with the current configuration."


class MissingLLMConfigurationError(LLMConfigurationError):
    """The configured provider has no usable credentials."""

    default_message = "Question answering is not configured. Please try again later."


class UnsupportedLLMProviderError(LLMConfigurationError):
    """The configured provider is not implemented."""

    default_message = "The configured language model provider is not supported."


class LLMUpstreamError(LLMError):
    """The language-model provider could not complete the request."""

    status_code = 502
    code = "upstream_error"
    default_message = "The language model service could not complete the request."


@runtime_checkable
class LLMProvider(Protocol):
    """Minimal completion interface consumed by the RAG service."""

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        """Return the provider's text answer for one system/user message pair."""
        ...


class GroqChatProvider:
    """Groq adapter using the OpenAI-compatible chat completions API."""

    def __init__(
        self,
        api_key: str | SecretStr,
        model: str,
        timeout_seconds: float,
        *,
        transport: httpx2.BaseTransport | None = None,
    ) -> None:
        secret = api_key.get_secret_value() if isinstance(api_key, SecretStr) else api_key
        if not secret or not secret.strip():
            raise MissingLLMConfigurationError()
        if not model.strip():
            raise MissingLLMConfigurationError("A language model must be configured.")

        self._api_key = secret.strip()
        self.model = model.strip()
        self.timeout_seconds = float(timeout_seconds)
        self._transport = transport

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        """Send one chat completion request and return its message content."""

        # Only widely supported OpenAI-compatible fields are sent. Groq does
        # not support logprobs/logit_bias/top_logprobs/names or n != 1.
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0,
        }

        started_at = time.perf_counter()
        try:
            with httpx2.Client(
                base_url=GROQ_OPENAI_BASE_URL,
                timeout=self.timeout_seconds,
                transport=self._transport,
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
            ) as client:
                response = client.post(_GROQ_CHAT_COMPLETIONS_PATH, json=payload)
                response.raise_for_status()
                data = response.json()
                answer = _extract_message_content(data)
        except (httpx2.TimeoutException, httpx2.RequestError, httpx2.HTTPStatusError) as exc:
            logger.warning(
                "llm_request_failed",
                extra={
                    "provider": LLM_PROVIDER_GROQ,
                    "model": self.model,
                    "duration_ms": round((time.perf_counter() - started_at) * 1000, 2),
                    "error_category": type(exc).__name__,
                },
            )
            raise LLMUpstreamError() from exc
        except (TypeError, ValueError, KeyError, IndexError) as exc:
            logger.warning(
                "llm_response_invalid",
                extra={
                    "provider": LLM_PROVIDER_GROQ,
                    "model": self.model,
                    "duration_ms": round((time.perf_counter() - started_at) * 1000, 2),
                    "error_category": type(exc).__name__,
                },
            )
            raise LLMUpstreamError() from exc

        logger.info(
            "llm_request_completed",
            extra={
                "provider": LLM_PROVIDER_GROQ,
                "model": self.model,
                "duration_ms": round((time.perf_counter() - started_at) * 1000, 2),
            },
        )
        return answer


def _extract_message_content(data: Any) -> str:
    """Read the first assistant message without trusting provider internals."""

    if not isinstance(data, dict):
        raise ValueError("unexpected response payload")
    choices = data.get("choices")
    if not isinstance(choices, list) or not choices:
        raise ValueError("missing choices")
    first = choices[0]
    if not isinstance(first, dict):
        raise ValueError("invalid choice")
    message = first.get("message")
    if not isinstance(message, dict):
        raise ValueError("missing message")
    content = message.get("content")
    if not isinstance(content, str) or not content.strip():
        raise ValueError("missing content")
    return content.strip()


def build_llm_provider(settings: Settings | None = None) -> LLMProvider:
    """Build the configured provider, validating credentials only on demand."""

    active_settings = settings or get_settings()
    provider_id = active_settings.llm_provider.strip().lower()
    if provider_id != LLM_PROVIDER_GROQ:
        raise UnsupportedLLMProviderError()

    if (
        active_settings.groq_api_key is None
        or not active_settings.groq_api_key.get_secret_value().strip()
    ):
        raise MissingLLMConfigurationError()

    provider = GroqChatProvider(
        active_settings.groq_api_key,
        active_settings.llm_model,
        active_settings.llm_timeout_seconds,
    )
    logger.info(
        "llm_provider_selected",
        extra={"provider": provider_id, "model": active_settings.llm_model},
    )
    return provider


__all__ = [
    "GROQ_OPENAI_BASE_URL",
    "GroqChatProvider",
    "LLMConfigurationError",
    "LLMError",
    "LLMProvider",
    "LLMUpstreamError",
    "MissingLLMConfigurationError",
    "UnsupportedLLMProviderError",
    "build_llm_provider",
]
