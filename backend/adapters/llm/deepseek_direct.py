"""
backend.adapters.llm.deepseek_direct
===================================

Direct call to ``api.deepseek.com`` via the OpenAI client. Kept as a
separate adapter for callers that want DeepSeek regardless of the
``LLM_PROVIDER`` selection (mostly legacy refactor-compat).
"""

from __future__ import annotations

import os

from openai import OpenAI


class DeepSeekDirectAdapter:
    """Direct call to DeepSeek's API. Used as the last-resort fallback
    when neither OpenAI-Compatible nor Gemini are usable."""

    name = "deepseek"

    def __init__(self) -> None:
        api_key = (
            os.getenv("DEEPSEEK_API_KEY")
            or os.getenv("LLM_API_KEY")
            or os.getenv("OPENAI_API_KEY", "")
        ).strip()
        if not api_key:
            raise ValueError(
                "DEEPSEEK_API_KEY no configurada (ni LLM_API_KEY como fallback)."
            )
        self._client = OpenAI(
            api_key=api_key,
            base_url="https://api.deepseek.com/v1",
            timeout=60.0,
        )

    def complete(self, prompt: str, *, model: str | None = None) -> str:
        """Call DeepSeek with ``deepseek-chat`` (the only public model)."""
        response = self._client.chat.completions.create(
            model="deepseek-chat",
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
            response_format={"type": "json_object"},
        )
        return response.choices[0].message.content


__all__ = ["DeepSeekDirectAdapter"]