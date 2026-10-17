"""
Tests for ``application.services.llm_orchestrator.LLMOrchestrator``.

Uses mock LLMProvider implementations to verify:
    * First successful provider wins.
    * On failure the orchestrator falls back to the next provider.
    * Empty provider list raises immediately.
    * Timeout per provider is respected.
    * All-fail raises a single RuntimeError aggregating the errors.
"""

from __future__ import annotations

import asyncio

import pytest

from application.services.llm_orchestrator import LLMOrchestrator
from ports.llm_provider import LLMProvider


class _StubProvider:
    """Minimal mock implementing the LLMProvider protocol."""

    def __init__(
        self,
        name: str,
        *,
        response: str | None = None,
        raises: Exception | None = None,
        delay_seconds: float = 0.0,
        returns_empty: bool = False,
    ) -> None:
        self.name = name
        self._response = response
        self._raises = raises
        self._delay = delay_seconds
        self._returns_empty = returns_empty
        self.calls: int = 0

    @property
    def name(self) -> str:
        return self._name

    @name.setter
    def name(self, value: str) -> None:
        self._name = value

    def complete(self, prompt: str, *, model: str | None = None) -> str:
        self.calls += 1
        if self._delay > 0:
            import time as _t
            _t.sleep(self._delay)
        if self._raises is not None:
            raise self._raises
        if self._returns_empty:
            return ""
        return self._response or f"{self._name} echo: {prompt[:10]}"


class TestLLMOrchestrator:
    def test_empty_provider_list_raises_on_construction(self):
        with pytest.raises(ValueError, match="at least one provider"):
            LLMOrchestrator([])

    def test_first_provider_wins(self):
        a = _StubProvider("a", response="hello from a")
        b = _StubProvider("b", response="hello from b")
        orch = LLMOrchestrator([a, b])
        result = asyncio.run(orch.complete("hi"))
        assert result == "hello from a"
        assert a.calls == 1
        assert b.calls == 0  # never tried

    def test_falls_back_on_first_failure(self):
        a = _StubProvider("a", raises=RuntimeError("a is down"))
        b = _StubProvider("b", response="hello from b")
        orch = LLMOrchestrator([a, b])
        result = asyncio.run(orch.complete("hi"))
        assert result == "hello from b"
        assert a.calls == 1
        assert b.calls == 1

    def test_falls_back_on_empty_response(self):
        a = _StubProvider("a", returns_empty=True)
        b = _StubProvider("b", response="hello from b")
        orch = LLMOrchestrator([a, b])
        result = asyncio.run(orch.complete("hi"))
        assert result == "hello from b"
        assert a.calls == 1
        assert b.calls == 1

    def test_all_fail_raises_runtime_error_with_aggregated_message(self):
        a = _StubProvider("a", raises=RuntimeError("a down"))
        b = _StubProvider("b", raises=ValueError("b bad prompt"))
        c = _StubProvider("c", raises=TimeoutError("c slow"))
        orch = LLMOrchestrator([a, b, c])
        with pytest.raises(RuntimeError, match=r"Todos los proveedores LLM fallaron"):
            asyncio.run(orch.complete("hi"))
        # All three providers were tried.
        assert a.calls == 1 and b.calls == 1 and c.calls == 1

    def test_timeout_cancels_a_slow_provider(self):
        # Provider A sleeps 2s; orchestrator timeout is 0.1s. Should fall back to B.
        a = _StubProvider("a", delay_seconds=2.0)
        b = _StubProvider("b", response="fast b")
        orch = LLMOrchestrator([a, b], timeout_seconds=0.1)
        result = asyncio.run(orch.complete("hi"))
        assert result == "fast b"

    def test_providers_property_returns_tuple(self):
        a = _StubProvider("a", response="hi")
        b = _StubProvider("b", response="hi")
        orch = LLMOrchestrator([a, b])
        # tuple, not the internal list — callers can't mutate it.
        providers = orch.providers
        assert isinstance(providers, tuple)
        assert len(providers) == 2

    def test_all_providers_must_satisfy_protocol(self):
        # A class with the right shape passes isinstance; one missing methods doesn't.
        class NotAProvider:
            name = "nope"
            # missing complete()
            pass

        # The orchestrator catches the AttributeError and wraps it in a
        # RuntimeError that aggregates all per-provider failures.
        orch = LLMOrchestrator([NotAProvider()])  # type: ignore[list-item]
        with pytest.raises(RuntimeError, match=r"complete"):
            asyncio.run(orch.complete("hi"))


class TestLLMProviderProtocol:
    def test_stub_satisfies_protocol(self):
        a = _StubProvider("a", response="hi")
        assert isinstance(a, LLMProvider)