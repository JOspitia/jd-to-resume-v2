"""
backend.adapters.llm.gemini
==========================

Adapter for Google Gemini. Internally tries ``gemini-2.0-flash`` →
``gemini-1.5-flash`` → ``gemini-1.5-pro`` within a single ``complete()``
call because each model has different availability per user (the 2.0
and 1.5 free-tier rate limits differ).

Migration note (commit history)
------------------------------
Previously imported ``google.generativeai`` as ``genai``. That package is
end-of-life and emits a ``FutureWarning`` on every import. This module now
uses the new official SDK (``google-genai`` on PyPI), which exposes the
``genai.Client`` async/sync façade. The ``complete()`` contract returned
to ``LLMProvider`` is unchanged; only the SDK surface beneath it moved.
"""

from __future__ import annotations

import os

from google import genai
from google.genai import types


_CASCADE = ("gemini-2.0-flash", "gemini-1.5-flash", "gemini-1.5-pro")
_GENERATION_CONFIG = types.GenerateContentConfig(response_mime_type="application/json")


class GeminiAdapter:
    """Adapter for the Gemini family. Internally cascades across models."""

    name = "gemini"

    def __init__(self) -> None:
        api_key = os.getenv("GEMINI_API_KEY", "").strip()
        if not api_key or api_key.startswith("AQ."):
            raise ValueError(
                "GEMINI_API_KEY no configurada o no válida. "
                "Configura la env var con tu clave real."
            )
        self._client = genai.Client(api_key=api_key)

    def complete(self, prompt: str, *, model: str | None = None) -> str:
        """Call Gemini and return the response text. Cascades across the
        three free-tier-friendly models; the first one to respond wins.

        The ``model`` parameter is accepted to satisfy the ``LLMProvider``
        protocol but currently ignored — the cascade is hardcoded. A
        future revision could route ``model`` to a single targeted call.

        Raises ``RuntimeError`` if every model fails.
        """
        last_error: Exception | None = None
        for model_name in _CASCADE:
            try:
                res = self._client.models.generate_content(
                    model=model_name,
                    contents=prompt,
                    config=_GENERATION_CONFIG,
                )
                if res and getattr(res, "text", None):
                    return res.text
            except Exception as exc:  # pragma: no cover - network errors
                last_error = exc
                continue
        raise RuntimeError(
            f"Todos los modelos Gemini fallaron. Último error: {last_error}"
        )


__all__ = ["GeminiAdapter"]
