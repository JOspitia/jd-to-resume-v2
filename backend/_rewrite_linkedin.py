"""One-shot rewrite of main.py: collapse the LinkedIn extraction function."""
import re
src = open("main.py", encoding="utf-8").read()
start_pat = re.compile(r"# In-memory cache to avoid re-extracting LinkedIn.*?async def extract_linkedin_profile_data", re.DOTALL)
end_pat = re.compile(r"def _build_language_override")
m_start = start_pat.search(src)
m_end = end_pat.search(src)
assert m_start, "start marker not found"
assert m_end, "end marker not found"
print(f"removing {m_end.start() - m_start.start()} chars (lines ~{src[:m_start.start()].count(chr(10))+1} to {src[:m_end.start()].count(chr(10))+1})")

NEW = '''# In-memory cache to avoid re-extracting LinkedIn on every refinement pass.
# key: linkedin_url, value: extracted text. Now owned by LinkedInService;
# the module-level dict is kept here so the public function signature
# and cache-key semantics are preserved across the refactor.
_linkedin_cache: dict = {}


async def extract_linkedin_profile_data(linkedin_url: str) -> str:
    """Backward-compatible wrapper that delegates to ``LinkedInService``.

    The three strategies (ProxyCurl -> Playwright auth -> Public urllib)
    live under ``adapters/linkedin/``; the orchestration + LLM pass-through
    + cache live in ``application.services.linkedin_service.LinkedInService``.
    """
    from adapters.linkedin.factory import build_linkedin_strategies
    from application.services.linkedin_service import LinkedInService

    # Re-read .env on each call so credentials added after server start are picked up.
    load_dotenv(override=True)
    print(f"[LINKEDIN EXTRACTOR] Iniciando extraccion para: {linkedin_url}")
    strategies = build_linkedin_strategies()
    service = LinkedInService(strategies, llm_call=call_llm_api, cache=_linkedin_cache)
    return await service.extract(linkedin_url)


'''

new_src = src[:m_start.start()] + NEW + src[m_end.start():]
open("main.py", "w", encoding="utf-8").write(new_src)
print(f"wrote {len(new_src)} chars (was {len(src)})")