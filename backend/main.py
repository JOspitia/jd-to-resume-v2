import os
import sys
import io

# Force UTF-8 stdout/stderr on Windows so print() with non-ASCII chars
# (emojis, accented chars, etc.) does not raise UnicodeEncodeError against
# the default cp1252 codec. Skipped under pytest so re-importing this module
# in tests does not leak wrapped streams past the test's captured buffers.
if sys.platform == "win32" and os.getenv("DISABLE_STDIO_REWRAP") != "1" and "pytest" not in sys.modules:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True)
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace", line_buffering=True)

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware

# Hexagonal split: section delegates to dedicated modules.
from adapters.storage.filesystem_storage import FilesystemStorage
from routes.assets_router import build_assets_router


# Backward-compatible wrapper for the photo-upload helper. The real
# implementation lives in ``photo_helpers.save_photo``; the storage
# adapter (``FilesystemStorage.save_photo``) also wraps the same helper.
# Kept here so the existing ``generate_resume`` endpoint signature
# (`_persist_uploaded_photo(photo)`) still resolves without a sweeping
# refactor of every endpoint.
#
# Defined further down (after ``_save_photo`` is imported and
# ``_PHOTOS_DIR`` is set) so the closure captures names that already
# exist when the function is called. Defining the function above its
# dependencies relies on Python's late binding to work — fine at
# runtime, but fragile if a test exercises a partial module load.
from slowapi import Limiter
from slowapi.util import get_remote_address


# Manual rate-limit helper. We don't use slowapi's middleware or its
# @limiter.limit decorators because:
#
#   * The ASGI middleware tries to inject rate-limit headers AFTER the
#     handler has already started the response — with SSE endpoints
#     (``/api/generate``) this corrupts the stream and the browser sees
#     ``net::ERR_FAILED``.
#   * The decorator-only approach loses its closure when FastAPI
#     re-registers the route, so the auto-check never runs.
#
# Instead: every LLM-expensive endpoint calls ``await enforce_rate_limit``
# explicitly with a unique ``scope`` label. The counter resets after
# the configured window expires.
_RL_HITS: dict[str, list[float]] = {}  # key -> list of monotonic timestamps


async def enforce_rate_limit(request: Request, scope: str) -> None:
    """Raise ``HTTPException(429)`` if the remote IP has exceeded the limit
    in the configured window for ``scope``.

    The limit comes from the env var ``RATE_LIMIT_DEFAULT`` (e.g.
    ``"5/minute"``).

    We previously raised ``slowapi.errors.RateLimitExceeded`` here, but the
    upstream exception constructor expects a ``Limit`` object (with an
    ``error_message`` attribute) rather than the raw string we parsed — that
    raised ``AttributeError`` instead of 429, which the SSE-handling
    frontend translated into a generic "Process Failed / network error".
    ``HTTPException(429, ...)`` is what FastAPI's existing CORS and SSE
    handlers already consume without surprises.
    """
    if not limiter.enabled:
        return
    from time import monotonic

    raw = os.getenv("RATE_LIMIT_DEFAULT", "5/minute")
    try:
        count_str, _, window_str = raw.partition("/")
        limit = int(count_str)
        if window_str.startswith("minute"):
            window = 60.0
        elif window_str.startswith("second"):
            window = 1.0
        elif window_str.startswith("hour"):
            window = 3600.0
        else:
            window = 60.0
    except ValueError:
        limit, window = 5, 60.0

    ip = get_remote_address(request)
    key = f"{scope}:{ip}"
    now = monotonic()
    hits = _RL_HITS.get(key, [])
    # Drop hits outside the window.
    hits = [t for t in hits if (now - t) < window]
    if len(hits) >= limit:
        # Persist the at-limit snapshot so concurrent requests see the
        # same window. Drop the key entirely if the filter emptied the
        # list, so the dict doesn't accumulate dead ``scope:ip`` entries
        # on a long-running server with many distinct callers.
        if hits:
            _RL_HITS[key] = hits
        else:
            _RL_HITS.pop(key, None)
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit exceeded for {scope!r}: {limit} requests per {window:.0f}s",
        )
    hits.append(now)
    _RL_HITS[key] = hits

from dotenv import load_dotenv
from photo_helpers import save_photo as _save_photo

load_dotenv()

app = FastAPI()

# CORS: defaults to local Vite dev origins; override with a comma-separated
# CORS_ALLOWED_ORIGINS env var when deploying behind a tunnel or production
# frontend. We deliberately do NOT use a wildcard: combined with the previous
# path-traversal bug in /api/download it would expose any file the server
# process can read to any origin on the public internet.
_cors_origins_raw = os.getenv(
    "CORS_ALLOWED_ORIGINS",
    "http://localhost:5173,http://localhost:5174,http://127.0.0.1:5173,"
    "http://localhost:4173,http://127.0.0.1:4173",
)
_cors_origins = [o.strip() for o in _cors_origins_raw.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
    allow_credentials=False,
)

# Rate limiting: protect LLM-expensive endpoints from runaway scripts that
# could drain the user's API quota.
#
# IMPORTANT: we intentionally do NOT use ``SlowAPIASGIMiddleware`` here.
# That middleware tries to inject rate-limit response headers AFTER the
# handler starts producing the response. With SSE endpoints
# (``/api/generate``, ``/api/analyze-ats``, ``/api/render-from-yaml``)
# the response has already started streaming by the time the middleware
# tries to mutate headers — the browser sees a corrupt response
# (``net::ERR_FAILED`` in DevTools) and the SSE connection drops. This is
# a documented limitation of slowapi + Starlette SSE.
#
# We also do NOT use ``@limiter.limit(...)`` decorators on the handlers
# themselves, because FastAPI re-registers the route after our composition
# root wires the routers — the decorator loses its closure and the check
# never runs.
#
# Instead, every LLM-expensive endpoint (and the ``/api/clear-cache`` shim
# inside ``routes.assets_router``) calls ``await enforce_rate_limit``
# explicitly with a unique ``scope`` label. The helper uses slowapi's
# ``Limiter`` only as a config object (for the ``enabled`` flag and key
# function); the real limit check is a tiny in-process dict kept in
# ``_RL_HITS`` — no middleware, no decorator, full control of the
# exception type (``HTTPException(429)``).
_rl_default = os.getenv("RATE_LIMIT_DEFAULT", "5/minute")
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[_rl_default],
    enabled=os.getenv("RATELIMIT_ENABLED", "1") != "0",
)
app.state.limiter = limiter  # kept for backward-compat introspection in tests

# --- Module-level paths (kept for backward compat with tests + scripts) ---
# The values are owned by FilesystemStorage in the composition root below.
# Tests that need to drop fake PDFs into the output dir use these.
_OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")
_PHOTOS_DIR = os.path.join(_OUTPUT_DIR, "photos")


async def _persist_uploaded_photo(photo):
    """Persist the optional candidate photo. Returns absolute path or None.

    Defined here (after ``_save_photo`` and ``_PHOTOS_DIR``) so the
    closure cannot fail at call time with ``NameError`` — this path
    is exercised by ``tests/test_persist_uploaded_photo.py``.
    """
    if photo is None:
        return None
    content = await photo.read()
    return _save_photo(content, _PHOTOS_DIR)

# --- Composition root: wire adapters into routes ---
# This is where the hexagonal architecture becomes concrete: every use case
# receives its adapters via the router factory, never via global imports.
_storage = FilesystemStorage(_OUTPUT_DIR, _PHOTOS_DIR)
app.include_router(build_assets_router(_storage))

# Single LLM orchestrator shared across all LLM-backed services. Building it
# is expensive (loads openai / google.generativeai SDKs) so we do it once at
# module-init and pass the instance to every service that needs LLM.
from application.services.llm_orchestrator import LLMOrchestrator
from adapters.llm.factory import build_llm_providers
_llm_orchestrator = LLMOrchestrator(build_llm_providers())

# Audit service: shared by /api/analyze-ats, /api/analyze-yaml, and the
# generation pipeline's auto re-audit (REQ-4). Wires a PyMuPDF parser so
# the ``audit_pdf`` path can extract text from a freshly uploaded resume.
from application.services.audit_service import AuditService
from adapters.parser.pymupdf_adapter import PyMuPDFParser
_audit_service = AuditService(_llm_orchestrator, PyMuPDFParser())

# /api/analyze-ats: the frontend-driven audit endpoint.
from routes.audit_router import build_audit_router
app.include_router(build_audit_router(_audit_service))

# YAML editor (render-from-yaml, analyze-yaml, repair-yaml): DI of the
# LLM-backed repair service + the storage for output path resolution.
# The audit_service is also injected so analyze-yaml can delegate.
from application.services.yaml_editor_service import YamlEditorService
from routes.yaml_editor_router import build_yaml_editor_router
_yaml_editor_service = YamlEditorService(_llm_orchestrator)
app.include_router(
    build_yaml_editor_router(
        _yaml_editor_service, _storage, audit_service=_audit_service
    )
)

# /api/generate: the SSE streaming CV generation pipeline. DI of the
# service (orchestrates the full LLM cascade + render) + storage (output
# path resolution) + audit_service (for the auto re-audit on translation).
from application.services.generation_service import GenerationService
from routes.generate_router import build_generate_router
_generation_service = GenerationService(_storage, _llm_orchestrator, _audit_service)
app.include_router(build_generate_router(_generation_service, _storage))


@app.get("/")
def read_root():
    return {"status": "AI Resume Backend is running OK!"}


def extract_text(file_path: str) -> str:
    """Backward-compatible wrapper around the PyMuPDFParser adapter."""
    return _get_resume_parser().extract_text(file_path)


def _extract_header_from_pdf_text(resume_text: str) -> dict:
    """Backward-compatible wrapper around the PyMuPDFParser adapter."""
    return _get_resume_parser().extract_header(resume_text)


_RESUME_PARSER = None


def _get_resume_parser():
    """Lazy accessor for the parser adapter. Lazy so module import doesn't
    pull ``adapters.parser.pymupdf_adapter`` (and its ``fitz`` dependency)
    into the test-suite import graph before tests have a chance to
    monkeypatch env vars. The first call instantiates; subsequent calls
    reuse the same instance."""
    global _RESUME_PARSER
    if _RESUME_PARSER is None:
        from adapters.parser.pymupdf_adapter import PyMuPDFParser

        _RESUME_PARSER = PyMuPDFParser()
    return _RESUME_PARSER


async def call_llm_api(prompt_text: str) -> str:
    """Backward-compatible wrapper that delegates to the LLM orchestrator.

    The cascade logic that used to live here (try OpenAI-Compatible,
    fall back to Gemini, fall back to DeepSeek direct) now lives in
    ``application.services.llm_orchestrator.LLMOrchestrator``. Each
    provider is its own adapter under ``adapters/llm/``; the
    orchestrator owns the fallback policy and timeouts.

    We delegate to the module-level ``_llm_orchestrator`` singleton
    (built once at app startup, lines 173-178) so we don't re-construct
    the provider cascade on every call. Each provider adapter loads
    its SDK / reads env vars / opens an HTTP client at init — that work
    is expensive and was previously duplicated on every LLM call.
    """
    return await _llm_orchestrator.complete(prompt_text)


# In-memory cache to avoid re-extracting LinkedIn on every refinement pass.
# key: linkedin_url, value: extracted text. Now owned by LinkedInService;
# the module-level dict is kept here so the public function signature
# and cache-key semantics are preserved across the refactor.
_linkedin_cache: dict = {}


async def extract_linkedin_profile_data(linkedin_url: str) -> str:
    """Backward-compatible wrapper that delegates to ``LinkedInService``.

    The three strategies (ProxyCurl -> Playwright auth -> Public urllib)
    live under ``adapters/linkedin/``; the orchestration + LLM pass-through
    + cache live in ``application.services.linkedin_service.LinkedInService``.

    Credentials are read once at startup via ``load_dotenv()`` above. To
    rotate a LinkedIn provider key (ProxyCurl, etc.), restart the server —
    the same reload contract as the LLM providers. We previously called
    ``load_dotenv(override=True)`` per request so devs could rotate keys
    without a restart, but that re-reads ``.env`` from disk on every
    LinkedIn extraction and contradicts the LLM-key reload semantics.
    """
    from adapters.linkedin.factory import build_linkedin_strategies
    from application.services.linkedin_service import LinkedInService

    print(f"[LINKEDIN EXTRACTOR] Iniciando extraccion para: {linkedin_url}")
    strategies = build_linkedin_strategies()
    service = LinkedInService(strategies, llm_call=call_llm_api, cache=_linkedin_cache)
    return await service.extract(linkedin_url)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)


