"""
backend.ports.llm_provider
=========================

Port for any text-completion LLM.

Three adapters implement this today:
    * OpenAICompatibleAdapter  (DeepSeek, Groq, OpenRouter, Kimi, MiniMax, ...)
    * GeminiAdapter            (cascade 2.0-flash → 1.5-flash → 1.5-pro)
    * DeepSeekDirectAdapter    (legacy direct DeepSeek path)

The cascade / fallback between providers lives in the application layer
(``application.services.llm_orchestrator``), not in the adapters themselves.
Each adapter only knows how to call its own provider.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class LLMProvider(Protocol):
    """A text-completion LLM. The orchestrator owns fallback; the adapter
    only knows how to call its own provider once."""

    @property
    def name(self) -> str:
        """Stable identifier used in logs and the env-driven selection
        (e.g. ``"openai_compatible"``, ``"gemini"``, ``"deepseek"``)."""
        ...

    def complete(self, prompt: str, *, model: str | None = None) -> str:
        """Send the prompt to the provider and return the raw text response.

        ``model`` is optional; when ``None`` the adapter falls back to the
        provider's configured default (e.g. ``deepseek-chat``,
        ``gemini-2.0-flash``). Raises on transport, auth, or timeout errors.
        """
        ...


__all__ = ["LLMProvider"]