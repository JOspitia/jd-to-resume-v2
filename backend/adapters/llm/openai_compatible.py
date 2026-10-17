"""
backend.adapters.llm.openai_compatible
=====================================

Adapter for any provider that speaks the OpenAI Chat Completions API
(OpenAI itself, DeepSeek, Groq, OpenRouter, MiniMax, Kimi, Moonshot,
local llama.cpp, etc.). Selection is driven by ``LLM_PROVIDER`` env var
plus ``OPENAI_BASE_URL`` / ``LLM_BASE_URL`` and ``OPENAI_MODEL`` /
``LLM_MODEL``.
"""

from __future__ import annotations

import asyncio
import os

from openai import OpenAI


class OpenAICompatibleAdapter:
    """Adapter for any OpenAI-API-compatible endpoint.

    Recognized values for ``LLM_PROVIDER`` (case-insensitive):
        * ``openai``
        * ``openai_compatible``
        * ``deepseek``
        * ``openrouter``
        * ``groq``
        * ``minimax``
        * ``kimi``
        * ``moonshot``

    The actual URL and model come from ``OPENAI_BASE_URL`` / ``LLM_BASE_URL``
    and ``OPENAI_MODEL`` / ``LLM_MODEL``. If unset, defaults to OpenAI's
    public API at ``https://api.openai.com/v1`` with ``gpt-4o-mini``.
    """

    name = "openai_compatible"

    # Providers that don't accept the ``response_format=json_object`` flag
    # (some hosts reject it because their templates don't expose JSON mode).
    _JSON_FORMAT_DISABLED_HOSTS = ("minimax", "moonshot", "kimi")

    def __init__(self) -> None:
        api_key = os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY")
        base_url = (
            os.getenv("OPENAI_BASE_URL")
            or os.getenv("LLM_BASE_URL")
            or "https://api.openai.com/v1"
        )
        model_name = (
            os.getenv("OPENAI_MODEL")
            or os.getenv("LLM_MODEL")
            or "gpt-4o-mini"
        )
        if not api_key:
            raise ValueError("Falta la clave API para openai_compatible provider.")
        self._client = OpenAI(api_key=api_key, base_url=base_url, timeout=45.0)
        self._model_name = model_name
        self._base_url = base_url

    def complete(self, prompt: str, *, model: str | None = None) -> str:
        """Call the OpenAI-compatible endpoint and return the assistant text.

        Synchronous. The orchestrator wraps it in ``asyncio.to_thread``
        because the OpenAI client is blocking.
        """
        extra_args: dict = {}
        if not any(host in self._base_url for host in self._JSON_FORMAT_DISABLED_HOSTS):
            extra_args["response_format"] = {"type": "json_object"}
        response = self._client.chat.completions.create(
            model=model or self._model_name,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a professional technical recruiter and "
                        "resume writer. Always respond strictly in valid JSON format."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.3,
            **extra_args,
        )
        return response.choices[0].message.content


__all__ = ["OpenAICompatibleAdapter"]