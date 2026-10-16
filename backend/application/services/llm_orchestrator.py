"""
backend.application.services.llm_orchestrator
============================================

Tries each ``LLMProvider`` in order and returns the first successful
response. Replaces the cascade that used to live inside
``main.call_llm_api``.

Each adapter knows only how to call its own provider; this orchestrator
owns the fallback policy and the timeout per provider.
"""

from __future__ import annotations

import asyncio
from typing import Iterable, Sequence

from ports.llm_provider import LLMProvider


_DEFAULT_TIMEOUT_SECONDS = 50.0


class LLMOrchestrator:
    """Cascade over multiple ``LLMProvider`` adapters.

    The orchestrator owns:
        * the order of providers (priority order — primary first)
        * per-provider timeout
        * the fallback policy (try the next provider on any exception)

    Each adapter stays focused on talking to its own provider. Adding a
    new provider means adding one adapter + listing it in the cascade —
    no changes to existing adapters.
    """

    def __init__(
        self,
        providers: Sequence[LLMProvider],
        *,
        timeout_seconds: float = _DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        if not providers:
            raise ValueError(
                "LLMOrchestrator requires at least one provider. "
                "Check that at least one of LLM_API_KEY, GEMINI_API_KEY, "
                "or DEEPSEEK_API_KEY is configured."
            )
        self._providers: list[LLMProvider] = list(providers)
        self._timeout = timeout_seconds

    @property
    def providers(self) -> Iterable[LLMProvider]:
        return tuple(self._providers)

    async def complete(self, prompt: str, *, model: str | None = None) -> str:
        """Run the cascade. Returns the first provider's response.

        Logs each failure so the user can see which providers were tried
        and why each one failed. The exception after the last provider
        includes all the errors so debugging is straightforward.
        """
        if not self._providers:
            raise ValueError(
                "No LLM providers are configured. Set LLM_API_KEY, "
                "GEMINI_API_KEY, or DEEPSEEK_API_KEY."
            )

        errors: list[str] = []
        for provider in self._providers:
            try:
                response = await asyncio.wait_for(
                    asyncio.to_thread(provider.complete, prompt, model=model),
                    timeout=self._timeout,
                )
                if response:
                    return response
                errors.append(f"{provider.name}: returned empty response")
            except Exception as exc:  # noqa: BLE001 — we want to log everything
                errors.append(f"{provider.name}: {exc}")
                continue

        joined = "; ".join(errors) or "no providers attempted"
        raise RuntimeError(
            f"Todos los proveedores LLM fallaron ({len(errors)}). Detalle: {joined}"
        )


__all__ = ["LLMOrchestrator"]