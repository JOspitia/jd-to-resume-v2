"""
backend.application.services.linkedin_service
==============================================

Orchestrates the three LinkedIn extraction strategies:

    1. ProxyCurl / external API   →  raw JSON, normalized to Markdown by LLM.
    2. Playwright auth            →  already Markdown (raw scrape).
    3. Public urllib fetch        →  small Markdown blob (og: + JSON-LD).

Caches results per URL so refinement passes don't re-scrape. Returns an
empty string when every strategy fails (caller treats that as "no
LinkedIn enrichment available").
"""

from __future__ import annotations

from typing import Iterable

from ports.linkedin_scraper import LinkedInScraper


_PROXYCURL_CLEANUP_PROMPT = """
Tienes el siguiente JSON crudo devuelto por una API externa de LinkedIn (ProxyCurl o similar):

JSON:
{raw_json}

Estructura y limpia esta información para enriquecer y complementar el CV del candidato.
Genera un resumen profesional estructurado en Markdown con las siguientes secciones (omite las vacías):
- Nombre y Titular profesional
- Ubicación
- Resumen / Acerca de
- Experiencia Laboral (con empresa, cargo, fechas y descripción de responsabilidades)
- Educación (institución, título, fechas)
- Habilidades (lista completa de skills mencionadas)
- Certificaciones y Licencias (nombre, institución, fecha)
- Idiomas

IMPORTANTE: Conserva TODA la información de experiencias, cargos y certificaciones que encuentres, sin omitir ninguna.
"""


_PLAYWRIGHT_CLEANUP_PROMPT = """
Tienes el siguiente contenido extraído del perfil de LinkedIn de un candidato usando automatización de navegador.
El contenido puede tener texto duplicado, artefactos HTML o texto crudo de la interfaz.

CONTENIDO EXTRAÍDO DE LINKEDIN:
{raw_text}

Estructura y limpia esta información para enriquecer y complementar el CV del candidato.
Genera un resumen profesional estructurado en Markdown con las siguientes secciones (omite las vacías):
- Nombre y Titular profesional
- Ubicación
- Resumen / Acerca de
- Experiencia Laboral (con empresa, cargo, fechas y descripción de responsabilidades)
- Educación (institución, título, fechas)
- Habilidades (lista completa de skills mencionadas)
- Certificaciones y Licencias (nombre, institución, fecha)
- Idiomas

IMPORTANTE: Conserva TODA la información de experiencias, cargos y certificaciones que encuentres, sin omitir ninguna.
"""


_PUBLIC_CLEANUP_PROMPT = """
Tienes datos públicos limitados del perfil de LinkedIn de un candidato.
Extrae toda la información profesional disponible para complementar su CV.

DATOS PÚBLICOS DE LINKEDIN:
{raw_text}

Genera un resumen en Markdown con la información disponible. Indica claramente si la información es limitada por ser pública.
"""


# Whether the raw output of a strategy looks like JSON (ProxyCurl) and
# therefore needs the JSON-specific cleanup prompt.
def _looks_like_json(raw: str) -> bool:
    s = raw.strip()
    return s.startswith("{") or s.startswith("[")


class LinkedInService:
    """Orchestrates the LinkedIn extraction strategies.

    Args:
        strategies: ordered list of adapters. The first one to return a
            non-empty string wins. Empty strategies means "no extraction".
        llm_call: async callable that takes a prompt string and returns
            the model's response text. The service uses it to clean and
            structure each adapter's raw output into Markdown.
        cache: dict used as the per-URL memo. Defaults to a fresh dict;
            callers may pass a shared dict to make the cache persistent
            across service instances.
    """

    def __init__(
        self,
        strategies: Iterable[LinkedInScraper],
        llm_call,
        cache: dict[str, str] | None = None,
    ) -> None:
        self._strategies: list[LinkedInScraper] = list(strategies)
        self._llm_call = llm_call
        # Store the cache *by reference*, not by copy — this is intentional.
        # ``backend/main.py`` passes a module-level dict into every fresh
        # ``LinkedInService`` instance so the cache survives across the
        # per-request service re-instantiation. If callers copy here instead
        # (e.g. ``dict(cache)`` or ``cache.copy()``), the cache never persists
        # between calls and every LinkedIn extraction re-pays the full cost.
        self._cache: dict[str, str] = cache if cache is not None else {}

    @property
    def strategies(self) -> list[LinkedInScraper]:
        return list(self._strategies)

    async def extract(self, linkedin_url: str) -> str:
        """Try each strategy in order, clean the result with the LLM, cache.

        Returns the cleaned Markdown, or an empty string if every
        strategy fails or no strategies are configured.
        """
        if not linkedin_url or not linkedin_url.strip():
            return ""

        url = linkedin_url.strip()
        if "linkedin.com/in/" not in url:
            print(f"[LINKEDIN EXTRACTOR WARN] URL no parece perfil válido: {url}")
            return f"LinkedIn URL proporcionada: {url}"

        if url in self._cache:
            print(f"[LINKEDIN EXTRACTOR] ✅ Usando datos en caché para: {url}")
            return self._cache[url]

        if not self._strategies:
            print("[LINKEDIN EXTRACTOR WARN] Sin strategies configuradas.")
            return ""

        last_strategy = ""
        for strategy in self._strategies:
            last_strategy = strategy.strategy_name
            try:
                raw = strategy.scrape(url)
            except Exception as scrape_err:
                print(
                    f"[LINKEDIN EXTRACTOR WARN] Estrategia '{strategy.strategy_name}' falló: {scrape_err}"
                )
                continue
            if not raw or len(raw.strip()) < 30:
                # Empty / suspiciously short → try the next strategy.
                continue
            try:
                cleaned = await self._clean(raw)
                if cleaned:
                    self._cache[url] = cleaned
                    return cleaned
            except Exception as clean_err:
                print(
                    f"[LINKEDIN EXTRACTOR WARN] Limpieza con LLM falló para "
                    f"'{strategy.strategy_name}': {clean_err}"
                )
                continue

        print(
            f"[LINKEDIN EXTRACTOR WARN] Ninguna estrategia produjo datos utilizables "
            f"(última intentada: {last_strategy or 'ninguna'})."
        )
        return ""

    async def _clean(self, raw: str) -> str:
        """Send ``raw`` through the LLM with the appropriate cleanup prompt.

        The JSON variant uses the ProxyCurl prompt; everything else uses
        the Playwright / Public prompt (they're nearly identical but
        preserved separately so future tweaks don't accidentally merge).

        Truncates the raw input to 6000 chars before formatting — keeps
        the prompt bounded (LLM context safety).
        """
        truncated = raw[:6000]
        if _looks_like_json(truncated):
            prompt = _PROXYCURL_CLEANUP_PROMPT.format(raw_json=truncated)
        elif truncated.startswith("Perfil de LinkedIn") and "autenticación" in truncated:
            # Public scraper returned the "needs auth" placeholder — don't waste
            # an LLM call on it; return as-is.
            return truncated
        else:
            prompt = _PLAYWRIGHT_CLEANUP_PROMPT.format(raw_text=truncated)
        return await self._llm_call(prompt)


async def extract_linkedin_profile_data(
    linkedin_url: str,
    *,
    llm_call,
    cache: dict[str, str] | None = None,
) -> str:
    """Module-level entry point so callers (like ``GenerationService``)
    can import a single async function instead of instantiating
    ``LinkedInService`` themselves.

    The composition root (``main.py``) keeps a thin wrapper that closes
    over the module-level ``_linkedin_cache`` and its ``call_llm_api`` so
    external scripts and the existing
    ``main.extract_linkedin_profile_data`` shim continue to work.

    Moved from ``main.py`` during the final pass of the MP-02 circular
    import cleanup — eliminates the last ``from main import`` inside a
    service hot path.
    """
    from adapters.linkedin.factory import build_linkedin_strategies

    strategies = build_linkedin_strategies()
    service = LinkedInService(strategies, llm_call=llm_call, cache=cache)
    return await service.extract(linkedin_url)


__all__ = ["LinkedInService", "extract_linkedin_profile_data"]