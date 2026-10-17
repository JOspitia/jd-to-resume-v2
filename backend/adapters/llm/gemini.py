"""
backend.adapters.llm.gemini
==========================

Adapter for Google Gemini. Internally tries ``gemini-2.0-flash`` →
``gemini-1.5-flash`` → ``gemini-1.5-pro`` within a single ``complete()``
call because each model has different availability per user (the 2.0
and 1.5 free-tier rate limits differ).
"""

from __future__ import annotations

import os

import google.generativeai as genai


_CASCADE = ("gemini-2.0-flash", "gemini-1.5-flash", "gemini-1.5-pro")
_GENERATION_CONFIG = {"response_mime_type": "application/json"}


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
        genai.configure(api_key=api_key)
        self._models = [
            genai.GenerativeModel(model_name, generation_config=_GENERATION_CONFIG)
            for model_name in _CASCADE
        ]

    def complete(self, prompt: str, *, model: str | None = None) -> str:
        """Call Gemini and return the response text. Cascades across the
        three free-tier-friendly models; the first one to respond wins.

        Raises ``RuntimeError`` if every model fails.
        """
        last_error: Exception | None = None
        for m in self._models:
            try:
                res = m.generate_content(prompt)
                if res and getattr(res, "text", None):
                    return res.text
            except Exception as exc:  # pragma: no cover - network errors
                last_error = exc
                continue
        raise RuntimeError(
            f"Todos los modelos Gemini fallaron. Último error: {last_error}"
        )


__all__ = ["GeminiAdapter"]