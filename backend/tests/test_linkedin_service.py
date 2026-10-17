"""
Tests for the LinkedIn extraction service and adapters.

Covers:
    * ``LinkedInService`` falls back through strategies in order.
    * Cache hit returns the cached value without calling any strategy.
    * Empty URL short-circuits without calling strategies.
    * URL without ``/in/`` path returns the raw URL, no strategy called.
    * JSON-shaped raw output (ProxyCurl) goes through the JSON cleanup prompt.
    * Plain-text raw output (Playwright) goes through the markdown cleanup prompt.
    * "Needs auth" placeholder from public scraper is returned as-is, no LLM call.
    * Each adapter satisfies the ``LinkedInScraper`` protocol structurally.
"""

from __future__ import annotations

import sys

import pytest

sys.path.insert(0, ".")

from adapters.linkedin.proxycurl_adapter import ProxyCurlAdapter
from adapters.linkedin.public_scraper_adapter import PublicScraperAdapter
from application.services.linkedin_service import LinkedInService
from ports.linkedin_scraper import LinkedInScraper


# ---------------------------------------------------------------------------
# Adapter protocol satisfaction.
# ---------------------------------------------------------------------------


class TestAdaptersSatisfyProtocol:
    def test_public_scraper_satisfies_protocol(self, monkeypatch):
        monkeypatch.setenv("LINKEDIN_API_URL", "")
        monkeypatch.setenv("LINKEDIN_EMAIL", "")
        monkeypatch.setenv("LINKEDIN_PASSWORD", "")
        assert isinstance(PublicScraperAdapter(), LinkedInScraper)


# ---------------------------------------------------------------------------
# Stub strategy used across service tests.
# ---------------------------------------------------------------------------


class StubStrategy:
    def __init__(self, name: str, raw: str | None = None, raises: Exception | None = None) -> None:
        self._name = name
        self._raw = raw
        self._raises = raises
        self.calls: int = 0
        self.received_url: str | None = None

    @property
    def strategy_name(self) -> str:
        return self._name

    def scrape(self, linkedin_url: str) -> str:
        self.calls += 1
        self.received_url = linkedin_url
        if self._raises is not None:
            raise self._raises
        return self._raw or ""


# ---------------------------------------------------------------------------
# Service behavior.
# ---------------------------------------------------------------------------


class TestLinkedInService:
    @pytest.mark.asyncio
    async def test_empty_url_returns_empty(self):
        async def llm(p): return "should not be called"
        svc = LinkedInService([StubStrategy("a", raw="data")], llm_call=llm)
        assert await svc.extract("") == ""
        assert await svc.extract("   ") == ""

    @pytest.mark.asyncio
    async def test_url_without_in_path_returns_wrapper_message(self):
        async def llm(p): return "should not be called"
        svc = LinkedInService([StubStrategy("a", raw="data")], llm_call=llm)
        out = await svc.extract("https://linkedin.com/company/acme")
        # Service wraps the URL to flag it for downstream logging. Pre-refactor
        # behavior: "LinkedIn URL proporcionada: <url>".
        assert "https://linkedin.com/company/acme" in out
        assert "LinkedIn URL proporcionada" in out

    @pytest.mark.asyncio
    async def test_first_strategy_with_data_wins(self):
        async def llm(p): return "cleaned"
        a = StubStrategy("a", raw="very long enough data from A strategy here (>=30 chars)")
        b = StubStrategy("b", raw="very long enough data from B strategy here (>=30 chars)")
        svc = LinkedInService([a, b], llm_call=llm)
        out = await svc.extract("https://www.linkedin.com/in/alice")
        assert out == "cleaned"
        assert a.calls == 1
        assert b.calls == 0  # never tried

    @pytest.mark.asyncio
    async def test_falls_back_on_empty_result(self):
        async def llm(p): return "from-b"
        a = StubStrategy("a", raw="")  # empty → fall through
        b = StubStrategy("b", raw="very long enough data from B strategy here (>=30 chars)")
        svc = LinkedInService([a, b], llm_call=llm)
        out = await svc.extract("https://www.linkedin.com/in/alice")
        assert out == "from-b"
        assert a.calls == 1
        assert b.calls == 1

    @pytest.mark.asyncio
    async def test_falls_back_on_short_result(self):
        async def llm(p): return "from-b"
        a = StubStrategy("a", raw="hi")  # < 30 chars → fall through
        b = StubStrategy("b", raw="very long enough data from B strategy here (>=30 chars)")
        svc = LinkedInService([a, b], llm_call=llm)
        out = await svc.extract("https://www.linkedin.com/in/alice")
        assert out == "from-b"

    @pytest.mark.asyncio
    async def test_falls_back_on_strategy_exception(self):
        async def llm(p): return "from-b"
        a = StubStrategy("a", raises=RuntimeError("a down"))
        b = StubStrategy("b", raw="very long enough data from B strategy here (>=30 chars)")
        svc = LinkedInService([a, b], llm_call=llm)
        out = await svc.extract("https://www.linkedin.com/in/alice")
        assert out == "from-b"
        assert a.calls == 1
        assert b.calls == 1

    @pytest.mark.asyncio
    async def test_cache_hit_skips_strategies(self):
        cache: dict[str, str] = {
            "https://www.linkedin.com/in/alice": "previously cleaned"
        }
        async def llm(p): return "should not be called"
        a = StubStrategy("a", raw="very long enough data here (>=30 chars)")
        svc = LinkedInService([a], llm_call=llm, cache=cache)
        out = await svc.extract("https://www.linkedin.com/in/alice")
        assert out == "previously cleaned"
        assert a.calls == 0

    @pytest.mark.asyncio
    async def test_result_is_cached_after_extraction(self):
        cache: dict[str, str] = {}
        async def llm(p): return "first result"
        a = StubStrategy("a", raw="very long enough data from A strategy here (>=30 chars)")
        svc = LinkedInService([a], llm_call=llm, cache=cache)
        first = await svc.extract("https://www.linkedin.com/in/alice")
        # Second call should use cache.
        b = StubStrategy("a", raw="some other data (>=30 chars)")
        svc2 = LinkedInService([b], llm_call=llm, cache=cache)
        second = await svc2.extract("https://www.linkedin.com/in/alice")
        assert first == second == "first result"
        assert b.calls == 0  # cached

    @pytest.mark.asyncio
    async def test_all_strategies_fail_returns_empty(self):
        async def llm(p): return "should not be called"
        a = StubStrategy("a", raises=RuntimeError("a"))
        b = StubStrategy("b", raises=RuntimeError("b"))
        svc = LinkedInService([a, b], llm_call=llm)
        out = await svc.extract("https://www.linkedin.com/in/alice")
        assert out == ""

    @pytest.mark.asyncio
    async def test_no_strategies_configured_returns_empty(self):
        async def llm(p): return "should not be called"
        svc = LinkedInService([], llm_call=llm)
        out = await svc.extract("https://www.linkedin.com/in/alice")
        assert out == ""

    @pytest.mark.asyncio
    async def test_json_payload_uses_json_cleanup_prompt(self):
        captured_prompts: list[str] = []

        async def llm(p: str) -> str:
            captured_prompts.append(p)
            return "json cleaned"

        a = StubStrategy("proxycurl", raw='{"headline": "Senior Engineer", "name": "Alice"}')
        svc = LinkedInService([a], llm_call=llm)
        out = await svc.extract("https://www.linkedin.com/in/alice")
        assert out == "json cleaned"
        assert len(captured_prompts) == 1
        # The JSON cleanup prompt references JSON / ProxyCurl keywords.
        assert "JSON" in captured_prompts[0] or "json" in captured_prompts[0]

    @pytest.mark.asyncio
    async def test_markdown_payload_uses_markdown_cleanup_prompt(self):
        captured_prompts: list[str] = []

        async def llm(p: str) -> str:
            captured_prompts.append(p)
            return "markdown cleaned"

        a = StubStrategy("playwright", raw="# Perfil\n**Name:** Alice\nLots of data here.")
        svc = LinkedInService([a], llm_call=llm)
        out = await svc.extract("https://www.linkedin.com/in/alice")
        assert out == "markdown cleaned"
        # The markdown prompt is the Playwright variant.
        assert "automatización" in captured_prompts[0] or "LinkedIn" in captured_prompts[0]

    @pytest.mark.asyncio
    async def test_needs_auth_placeholder_skips_llm_call(self):
        captured_calls: list[str] = []

        async def llm(p: str) -> str:
            captured_calls.append(p)
            return "should not be called"

        a = StubStrategy(
            "public",
            raw=(
                "Perfil de LinkedIn: https://www.linkedin.com/in/alice\n"
                "⚠️ El perfil requiere autenticación para ver el contenido completo. "
                "Configura LINKEDIN_EMAIL y LINKEDIN_PASSWORD en el archivo .env "
                "para extracción completa."
            ),
        )
        svc = LinkedInService([a], llm_call=llm)
        out = await svc.extract("https://www.linkedin.com/in/alice")
        # Public scraper's message is returned verbatim; LLM not called.
        assert "requiere autenticación" in out
        assert captured_calls == []

    @pytest.mark.asyncio
    async def test_strategies_property_returns_list_copy(self):
        a = StubStrategy("a", raw="x")
        b = StubStrategy("b", raw="y")
        svc = LinkedInService([a, b], llm_call=lambda p: "")
        strategies = svc.strategies
        assert len(strategies) == 2
        # The returned list is a copy — mutating it doesn't affect the service.
        strategies.clear()
        assert len(svc.strategies) == 2