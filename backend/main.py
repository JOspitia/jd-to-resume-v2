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

import json
import asyncio
import base64
from html import escape
from pathlib import Path
from typing import Optional
from fastapi import FastAPI, UploadFile, Form, File, BackgroundTasks, HTTPException, Request
from fastapi.responses import StreamingResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import fitz  # PyMuPDF
import google.generativeai as genai
from playwright.sync_api import sync_playwright
import tempfile
import time
import re

# Hexagonal split: section delegates to dedicated modules.
from schemas.api_models import GeminiResumeOutput  # noqa: F401 — re-exported for backward compat
from application.services.translation_service import build_language_override as _build_language_override
from adapters.storage.filesystem_storage import FilesystemStorage  # noqa: F401 — exposed for tests
from routes.assets_router import build_assets_router  # noqa: F401 — composition root uses it


# Backward-compatible wrapper for the photo-upload helper. The real
# implementation lives in ``photo_helpers.save_photo``; the storage
# adapter (``FilesystemStorage.save_photo``) also wraps the same helper.
# Kept here so the existing ``generate_resume`` endpoint signature
# (`_persist_uploaded_photo(photo)`) still resolves without a sweeping
# refactor of every endpoint.
async def _persist_uploaded_photo(photo):
    """Persist the optional candidate photo. Returns absolute path or None."""
    if photo is None:
        return None
    content = await photo.read()
    return _save_photo(content, _PHOTOS_DIR)
from slowapi import Limiter  # noqa: F401 — re-exported for backward compat (Limiter config)
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
        _RL_HITS[key] = hits
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit exceeded for {scope!r}: {limit} requests per {window:.0f}s",
        )
    hits.append(now)
    _RL_HITS[key] = hits

from dotenv import load_dotenv
from render_service import render_cv_with_rendercv
from language import detect_language
from photo_helpers import save_photo as _save_photo, prune_orphaned_photos as _prune_photos
from domain_games import get_game
from audit_prompts import build_audit_prompt as _build_audit_prompt_lib
from yaml_helpers import (
    serialize_resume_data_as_text as _serialize_resume_data_as_text,
    yaml_safe_dump_unicode as _yaml_safe_dump_unicode,
)
import yaml as _pyyaml

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

# --- Composition root: wire adapters into routes ---
# This is where the hexagonal architecture becomes concrete: every use case
# receives its adapters via the router factory, never via global imports.
_storage = FilesystemStorage(_OUTPUT_DIR, _PHOTOS_DIR)
app.include_router(build_assets_router(_storage))

# YAML editor (render-from-yaml, analyze-yaml, repair-yaml): DI of the
# LLM-backed repair service + the storage for output path resolution.
# The PdfRenderer is built per-request inside the render handler because
# the choice depends on the user-selected theme.
from application.services.yaml_editor_service import YamlEditorService
from application.services.llm_orchestrator import LLMOrchestrator
from routes.yaml_editor_router import build_yaml_editor_router


def _build_yaml_editor_service() -> YamlEditorService:
    """Late-bind the LLM orchestrator so importing ``main`` is cheap."""
    from adapters.llm.factory import build_llm_providers

    orchestrator = LLMOrchestrator(build_llm_providers())
    return YamlEditorService(orchestrator)


_yaml_editor_service = _build_yaml_editor_service()
app.include_router(
    build_yaml_editor_router(_yaml_editor_service, _storage)
)

# /api/generate: the SSE streaming CV generation pipeline. DI of the
# service (orchestrates the full LLM cascade + render) + storage (output
# path resolution). The LLM orchestrator is built lazily inside the
# service so the heavy SDKs are only loaded on first request.
from application.services.generation_service import GenerationService
from routes.generate_router import build_generate_router


def _build_generation_service() -> GenerationService:
    """Late-bind the LLM orchestrator so importing ``main`` is cheap."""
    from adapters.llm.factory import build_llm_providers

    orchestrator = LLMOrchestrator(build_llm_providers())
    return GenerationService(_storage, orchestrator)


_generation_service = _build_generation_service()
app.include_router(build_generate_router(_generation_service, _storage))


# --- Module-level paths (kept for backward compat with tests + scripts) ---
# The values are owned by FilesystemStorage in the composition root below.
# Tests that need to drop fake PDFs into the output dir use these.
_OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")
_PHOTOS_DIR = os.path.join(_OUTPUT_DIR, "photos")



@app.get("/")
def read_root():
    return {"status": "AI Resume Backend is running OK!"}

# Define schemas for Gemini response
from pydantic import BaseModel, Field

# Backward-compatible wrappers for the HTML-template helpers. The
# implementations (template, ATS helpers, photo data URI, render function,
# URL-fragmentation check) live in
# ``adapters/renderer/playwright_html_adapter.py``. The render function
# keeps the same name here so existing call sites keep working; the local
# ``_render_html_template`` alias is the adapter's implementation.

from adapters.renderer.playwright_html_adapter import (
    _ats_link_label,
    _photo_to_data_uri,
    _check_profile_urls_not_fragmented,
    _render_html_template,
)


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
    """
    from adapters.llm.factory import build_llm_providers
    from application.services.llm_orchestrator import LLMOrchestrator

    providers = build_llm_providers()
    print(f"[LLM] Iniciando cascada con {len(providers)} proveedor(es): "
          f"{[p.name for p in providers]}")
    orchestrator = LLMOrchestrator(providers)
    return await orchestrator.complete(prompt_text)


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
    """
    from adapters.linkedin.factory import build_linkedin_strategies
    from application.services.linkedin_service import LinkedInService

    # Re-read .env on each call so credentials added after server start are picked up.
    load_dotenv(override=True)
    print(f"[LINKEDIN EXTRACTOR] Iniciando extraccion para: {linkedin_url}")
    strategies = build_linkedin_strategies()
    service = LinkedInService(strategies, llm_call=call_llm_api, cache=_linkedin_cache)
    return await service.extract(linkedin_url)


def _build_audit_prompt(resume_text: str, jd_text: str, audit_game) -> str:
    """
    Thin wrapper around `audit_prompts.build_audit_prompt` so call sites
    in main.py keep the original name. The body of the audit prompt
    (per-game taxonomy + seed matched/missing keywords + actionable_tips
    templates) lives in `backend/audit_prompts.py` and is unit-tested
    there.
    """
    return _build_audit_prompt_lib(resume_text, jd_text, audit_game)


async def _run_audit_against_text(
    resume_text: str,
    jd_text: str,
    audit_game,
) -> dict:
    """
    Single source of truth for the ATS-audit LLM call.

    All three audit paths in this app delegate here:
      * `_run_internal_audit` (auto-fired after a forced translate-to-en flow).
      * `POST /api/analyze-ats` (frontend-driven audit on a freshly uploaded CV).
      * `POST /api/analyze-yaml` (audit on a YAML dict the user has edited
        before rendering — T5 of the yaml-editor feature).

    Composes the per-game prompt, calls the LLM, strips any ```json```
    markdown fence and returns the parsed dict. Raises ValueError if the
    response is not a JSON object (caller is responsible for HTTP mapping).
    """
    prompt = _build_audit_prompt(
        resume_text=resume_text,
        jd_text=jd_text,
        audit_game=audit_game,
    )
    content = await call_llm_api(prompt)

    clean_content = content.strip()
    if "```" in clean_content:
        match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", clean_content)
        if match:
            clean_content = match.group(1)

    try:
        parsed = json.loads(clean_content)
    except Exception:
        parsed = json.loads(content)

    # Some LLM clients wrap the payload in a list; take the first element.
    if isinstance(parsed, list) and len(parsed) > 0:
        parsed = parsed[0]

    if not isinstance(parsed, dict):
        raise ValueError(f"Audit response was not a dict (got {type(parsed).__name__})")
    return parsed


@app.post("/api/analyze-ats")
async def analyze_ats(
    request: Request,
    file: UploadFile,
    jd: Optional[str] = Form(None),
    domain_game: Optional[str] = Form(None)
):
    await enforce_rate_limit(request, scope="analyze-ats")
    # Validate domain_game (same contract as /api/generate).
    ALLOWED_GAMES = {"tech", "hr_recruiting", "psychology"}
    if domain_game is not None and domain_game not in ALLOWED_GAMES:
        raise HTTPException(
            status_code=422,
            detail=f"domain_game must be one of {sorted(ALLOWED_GAMES)} or omitted, got {domain_game!r}"
        )

    try:
        load_dotenv(override=True)
        temp_dir = tempfile.gettempdir()
        file_path = os.path.join(temp_dir, file.filename)
        with open(file_path, "wb") as f:
            f.write(await file.read())

        resume_text = extract_text(file_path)

        effective_jd = jd.strip() if (jd and jd.strip()) else "Optimización general y mejoramiento de calidad del CV"

        # Audit prompt is composed from the selected game's vocabulary so the
        # 'actionable_tips' stop suggesting tech-only artifacts (e.g. 'Add Docker')
        # for HR or Psychology CVs. The single source of truth for the
        # LLM call lives in `_run_audit_against_text` (shared with
        # `_run_internal_audit` and the upcoming `/api/analyze-yaml`).
        audit_game = get_game(domain_game)
        return await _run_audit_against_text(
            resume_text=resume_text,
            jd_text=effective_jd,
            audit_game=audit_game,
        )
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"error": str(e)}


# --- YAML editor: handlers + helpers moved to ``routes/yaml_editor_router.py``
# and ``application/services/yaml_editor_service.py``. The legacy module-level
# helpers below are kept as backward-compat shims because existing tests
# (notably ``tests/test_content_drift.py``) still import them from ``main``.
from application.services.yaml_editor_service import (
    parse_yaml_safe as _parse_yaml_safe,
    validate_yaml_schema as _validate_yaml_schema,
    content_tokens as _content_tokens,
    content_drift as _content_drift,
    strip_yaml_fences as _strip_yaml_fences,
)



if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)


