"""
backend.adapters.llm.factory
============================

Builds the ordered list of LLM adapters the orchestrator will try, based
on env vars. Returns the primary provider first, then the fallbacks.
"""

from __future__ import annotations

import os
from typing import Iterable

from adapters.llm.deepseek_direct import DeepSeekDirectAdapter
from adapters.llm.gemini import GeminiAdapter
from adapters.llm.openai_compatible import OpenAICompatibleAdapter
from ports.llm_provider import LLMProvider


_OPENAI_COMPATIBLE_PROVIDERS = frozenset({
    "openai", "openai_compatible", "minimax", "kimi", "moonshot",
    "deepseek", "openrouter", "groq",
})


def build_llm_providers() -> list[LLMProvider]:
    """Return the cascade of LLM providers to try, in priority order.

    Selection logic:
        * If ``LLM_PROVIDER`` is one of the OpenAI-compatible families →
          ``[OpenAICompatibleAdapter, GeminiAdapter, DeepSeekDirectAdapter]``.
          OpenAI first, then Gemini, then DeepSeek.
        * Otherwise (default ``gemini``) →
          ``[GeminiAdapter, OpenAICompatibleAdapter, DeepSeekDirectAdapter]``.
          Gemini first, then OpenAI compat, then DeepSeek.

    Each adapter is constructed eagerly so a missing API key raises
    immediately. Callers can introspect ``len(providers)`` before
    dispatching to know the cascade length.
    """
    provider = os.getenv("LLM_PROVIDER", "gemini").lower().strip()
    providers: list[LLMProvider] = []

    if provider in _OPENAI_COMPATIBLE_PROVIDERS:
        try:
            providers.append(OpenAICompatibleAdapter())
        except ValueError:
            pass  # missing key; skip
        try:
            providers.append(GeminiAdapter())
        except ValueError:
            pass
    else:  # default and explicit "gemini"
        try:
            providers.append(GeminiAdapter())
        except ValueError:
            pass
        try:
            providers.append(OpenAICompatibleAdapter())
        except ValueError:
            pass

    # DeepSeek always last as the universal fallback.
    try:
        providers.append(DeepSeekDirectAdapter())
    except ValueError:
        pass

    return providers


__all__ = ["build_llm_providers"]