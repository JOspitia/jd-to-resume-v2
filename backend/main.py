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



async def generation_pipeline(
    file_path: str,
    jd: Optional[str] = None,
    target_role: Optional[str] = None,
    github_url: Optional[str] = None,
    linkedin_url: Optional[str] = None,
    portfolio_url: Optional[str] = None,
    custom_instructions: Optional[str] = None,
    base_resume_filename: Optional[str] = None,
    theme: Optional[str] = "sb2nov",
    fit_single_page: bool = False,
    page_break_section: Optional[str] = None,
    extract_linkedin_info: bool = False,
    strict_edits_only: bool = False,
    force_language: Optional[str] = None,
    domain_game: Optional[str] = None,
    edit_before_generate: bool = False,
    photo_path: Optional[str] = None,
):
    """
    The end-to-end generation pipeline. Returns an SSE stream of progress events and
    ends with a `Finished` event containing the download URL.

    When `force_language='en'`, prepends AND appends a LANGUAGE OVERRIDE block to the
    system prompt so the output CV is generated in English regardless of the source
    JD language. See _build_language_override for the exact wording.

    When `domain_game` is set, the prompt body is composed from the corresponding
    game in `backend/domain_games/` instead of the legacy tech-only prompt. The
    available games today are: "tech" (default), "hr_recruiting", "psychology".
    Passing None or an unknown value falls back to "tech" (preserves v2.5 behaviour
    exactly because the tech game mirrors the legacy prompt body byte-for-byte).

    When `edit_before_generate=True`, the pipeline stops right after the LLM
    call has been parsed. It serialises `parsed_data` as YAML and emits a
    single SSE event with the form `{"step": "YAML Ready for Review",
    "progress": 100, "yaml": "...", "yaml_ready": true}` before returning
    without rendering a PDF. The frontend is expected to either POST the
    (possibly edited) YAML to `/api/render-from-yaml` (S6) or
    `/api/analyze-yaml` (S8). When False (default, or omitted) the
    existing PDF render path runs unchanged (S7).
    """
    if force_language:
        print(f"[TRANSLATE] force_language='{force_language}' — LANGUAGE OVERRIDE will be applied to system prompt (both preamble and tail).")
    print(f"[INPUT] github_url='{github_url}', linkedin_url='{linkedin_url}', portfolio_url='{portfolio_url}' (received from frontend form)")
    try:
        # Reload .env dynamically so any new API Key is immediately picked up
        load_dotenv(override=True)

        yield f"data: {json.dumps({'step': 'Validating Input', 'progress': 10})}\n\n"
        await asyncio.sleep(0.5)

        # If a previously generated resume filename is provided, use it as the base
        # This enables iterative refinement instead of regenerating from scratch
        effective_file_path = file_path
        if base_resume_filename:
            candidate_path = os.path.join(_OUTPUT_DIR, base_resume_filename)
            if os.path.exists(candidate_path):
                effective_file_path = candidate_path
                print(f"[INFO] ✅ Using previously generated resume as base: {candidate_path}")
            else:
                print(f"[WARN] ⚠️ base_resume_filename '{base_resume_filename}' not found in {_OUTPUT_DIR}, falling back to original upload.")
                print(f"[WARN]    Expected path: {candidate_path}")

        # Language-detection guardrail (REQ-3): if the user asked for English but the
        # source CV is already English, short-circuit before any LLM call so the
        # expensive translation round-trip is never executed.
        source_language = "unknown"
        if force_language == "en":
            detection_path = effective_file_path
            try:
                source_language = detect_language(extract_text(detection_path))
            except Exception as detect_err:
                print(f"[WARN] Language detection failed for '{detection_path}': {detect_err}. Falling back to 'unknown'.")
                source_language = "unknown"
            print(f"[INFO] force_language='{force_language}', detected source_language='{source_language}', detection_path='{detection_path}'")
            if source_language == "en":
                raise ValueError("E_CV_ALREADY_ENGLISH::CV already in English")

        yield f"data: {json.dumps({'step': 'Extracting Text from Resume', 'progress': 20})}\n\n"
        resume_text = extract_text(effective_file_path)

        # Extract contact header from the Base Resume so it survives regeneration
        # even when the user does not retype it in the form.
        extracted_header = _extract_header_from_pdf_text(resume_text)
        effective_github = (github_url.strip() if github_url and github_url.strip() else extracted_header["github"])
        effective_linkedin = (linkedin_url.strip() if linkedin_url and linkedin_url.strip() else extracted_header["linkedin"])
        effective_portfolio = (portfolio_url.strip() if portfolio_url and portfolio_url.strip() else extracted_header["portfolio"])
        print(f"[HEADER] github='{effective_github or '(empty)'}', linkedin='{effective_linkedin or '(empty)'}', portfolio='{effective_portfolio or '(empty)'}', email='{extracted_header['email'] or '(empty)'}', phone='{extracted_header['phone'] or '(empty)'}'")
        # Warn if the PDF had placeholder tokens (e.g. "LinkedIn") but no URL was found
        # and the user did not provide one in the form. CV will be missing that link.
        missing_placeholders = []
        if extracted_header["has_placeholder_github"] and not effective_github:
            missing_placeholders.append("github")
        if extracted_header["has_placeholder_linkedin"] and not effective_linkedin:
            missing_placeholders.append("linkedin")
        if extracted_header["has_placeholder_portfolio"] and not effective_portfolio:
            missing_placeholders.append("portfolio")
        if missing_placeholders:
            print(f"[HEADER] WARN: PDF had placeholder tokens but no URLs found for: {', '.join(missing_placeholders)}. User should fill the form with real URLs.")

        linkedin_extracted_text = ""
        if extract_linkedin_info and linkedin_url and linkedin_url.strip():
            yield f"data: {json.dumps({'step': 'Extrayendo datos del perfil de LinkedIn...', 'progress': 35})}\n\n"
            linkedin_extracted_text = await extract_linkedin_profile_data(linkedin_url.strip())
        
        yield f"data: {json.dumps({'step': 'Analyzing with AI Model', 'progress': 50})}\n\n"
        
        if strict_edits_only:
            user_requested_changes = custom_instructions.strip() if (custom_instructions and custom_instructions.strip()) else (jd.strip() if (jd and jd.strip()) else "No explicit changes specified.")
            language_override_block = ""
            if force_language == "en":
                language_override_block = _build_language_override(
                    target_language="en",
                    source_language=source_language,
                )
            prompt = f"""
{language_override_block}
You are an expert resume editor operating strictly in CONSERVATIVE SURGICAL EDIT MODE.
Your task is to take the provided Base Resume and perform ONLY the explicit change(s) requested by the user below.

USER REQUESTED MODIFICATIONS (CRITICAL — APPLY ONLY THESE):
{user_requested_changes}

STRICT SURGICAL EDIT RULES (ABSOLUTE HIGHEST PRIORITY — OVERRIDES ALL OTHER DEFAULTS):
1. DO NOT REWRITE, REPHRASE, OR ALTER THE PROFESSIONAL SUMMARY UNLESS THE USER'S REQUEST EXPLICITLY ASKS TO MODIFY THE SUMMARY. If the summary is not mentioned in the requested modifications, keep the 'summary' field 100% IDENTICAL to the Base Resume text.
2. DO NOT REWRITE OR REPHRASE ANY EXPERIENCE BULLET POINTS, DATES, ROLES, EDUCATION, OR SKILLS THAT WERE NOT EXPLICITLY TARGETED BY THE USER's REQUEST.
3. Keep ALL untouched text, experience entries, dates, education, skills, and section contents 100% EXACTLY IDENTICAL to the provided Base Resume.
4. ZERO HALLUCINATION: Do NOT invent or import any fake data, third-party companies, or fake projects.
5. DATE CONSISTENCY: Format ongoing roles/studies strictly as "YYYY-MM - Actualidad" (Spanish) or "YYYY-MM - Present" (English).
{language_override_block}
"""
        else:
            language_override_block = ""
            if force_language == "en":
                language_override_block = _build_language_override(
                    target_language="en",
                    source_language=source_language,
                )
            game = get_game(domain_game)
            prompt = f"""
{language_override_block}
{game.system_intro}

{game.strict_rules_block}
"""
        if custom_instructions and custom_instructions.strip() and not strict_edits_only:
            prompt += f"12. USER REFINEMENT FEEDBACK & SELECTED TIPS (HIGHEST PRIORITY): You MUST explicitly apply the following user-selected improvements, tone humanization tips, and custom instructions above all other defaults: {custom_instructions.strip()}\n"

        prompt += f"""
{language_override_block}
Target Role: {target_role if target_role else 'Not specified'}
GitHub: {effective_github}
LinkedIn: {effective_linkedin}
Portfolio: {effective_portfolio}

CONTACT HEADER PROTECTED FIELDS (DO NOT MODIFY, REMOVE, OR INVENT):
- email: {extracted_header["email"]}
- phone: {extracted_header["phone"]}
- github: {effective_github}
- linkedin: {effective_linkedin}
- portfolio: {effective_portfolio}
These values were extracted from the Base Resume and MUST be preserved verbatim
in the output JSON. If the Base Resume text does not contain one of them, leave
that field empty (do not invent placeholder URLs like 'github.com/janedoe').

Base Resume:
{resume_text}
"""
        # When force_language='en', strip contradictory language rules from the prompt
        # so the LLM cannot fall back to "use JD language" or "use Spanish verbs".
        # We remove rule 8 (LANGUAGE MATCHING) entirely and the Spanish-verb examples
        # in rule 5/15/17/18/20 — the LANGUAGE OVERRIDE block (preamble + tail) carries
        # the full English-only instruction set.
        if force_language == "en":
            prompt = prompt.replace(
                "8. LANGUAGE MATCHING (CRITICAL): Detect the dominant language of the Job Description. Generate ALL text content (summary, bullet points, skill categories, achievements) in THAT SAME language. If the JD is in English → output everything in English. If the JD is in Spanish → output everything in Spanish. Default to the JD language; never mix languages in the same document. Also output the correct localized 'section_labels' accordingly. [OVERRIDDEN when force_language is set — see LANGUAGE OVERRIDE block at the end of this prompt.]",
                "8. LANGUAGE: ABSOLUTE OVERRIDE APPLIES — see LANGUAGE OVERRIDE block. Do not detect or follow the JD language."
            )
            # Spanish verb examples in rule 5: force English-only examples
            prompt = prompt.replace(
                "Spanish: Diseñé, Implementé, Refactoricé, Despliegué, Migré, Optimicé, Automaticé, Incrementé, Reduje, Agilicé, Maximicé, Consolidé, Lideré, Construí.",
                "English (only): Engineered, Architected, Implemented, Spearheaded, Optimized, Automated, Streamlined, Reduced, Scaled, Deployed, Refactored, Designed, Built, Led, Migrated."
            )
            # Replace Spanish anti-AI examples in rules 15, 17, 18, 20 with English equivalents
            prompt = prompt.replace(
                'e.g., "Desarrollé [X] mediante [Y] logrando [Z]")',
                'e.g., "Engineered [X] through [Y] achieving [Z]")'
            )
            prompt = prompt.replace(
                'e.g., "Incrementé la velocidad de respuesta en 40% al refactorizar los endpoints..."',
                'e.g., "Reduced response latency by 40% through endpoint refactoring..."'
            )
            prompt = prompt.replace(
                'e.g., "Ante cuellos de botella en el procesamiento masivo de datos, diseñé una arquitectura de colas..."',
                'e.g., "Facing throughput bottlenecks in data pipelines, designed a queue-based architecture..."'
            )
            prompt = prompt.replace(
                'e.g., "Lideré el despliegue del sistema distribuido sobre AWS, reduciendo la latencia a menos de 100ms..."',
                'e.g., "Led the deployment of the distributed system on AWS, cutting latency below 100ms..."'
            )
            prompt = prompt.replace(
                'e.g., "Mediante FastAPI y PostgreSQL, automaticé los flujos de facturación eliminando 15 horas semanales de trabajo manual..."',
                'e.g., "Through FastAPI and PostgreSQL, automated billing flows eliminating 15 hours of manual work per week..."'
            )
            prompt = prompt.replace(
                'e.g., "Los equipos de bodega carecían de visibilidad en tiempo real; construí una plataforma con Laravel y React que..."',
                'e.g., "Warehouse teams lacked real-time visibility; built a Laravel + React platform that..."'
            )
            prompt = prompt.replace(
                'e.g., "Reduje en 40% los costos..."',
                'e.g., "Cut costs by 40%..."'
            )
            prompt = prompt.replace(
                'e.g., "Implementé el stack con X, logrando Y en Z%"',
                'e.g., "Built the stack with X, achieving Y in Z%"'
            )
            prompt = prompt.replace(
                'e.g., "Implementé el stack con" or starting 4 consecutive bullets with "Desarrollé"',
                'e.g., "Built the stack with" or starting 4 consecutive bullets with "Engineered"'
            )
            prompt = prompt.replace(
                '"Construí", "Diseñé e implementé", "Lideré el desarrollo de", "Refactoricé", "Desplegué", "Migré"',
                '"Built", "Designed and implemented", "Led the development of", "Refactored", "Deployed", "Migrated"'
            )
            prompt = prompt.replace(
                '"Implementé el stack con...", "Desarrollé una...", or "Construí una..."',
                '"Built the stack with...", "Developed a...", or "Engineered a..."'
            )
            prompt = prompt.replace(
                '* Project 1 (Architectural/Innovation Opening): "Arquitecturé una plataforma de optimización de CVs basada en la orquestación de LLMs y renderizado Typst..."',
                '* Project 1 (Architectural/Innovation Opening): "Architected a CV optimization platform based on LLM orchestration and Typst rendering..."'
            )
            prompt = prompt.replace(
                '* Project 2 (Problem/Business Opening): "Para resolver la falta de visibilidad del inventario en tiempo real, diseñé un sistema de monitoreo..."',
                '* Project 2 (Problem/Business Opening): "To solve the lack of real-time inventory visibility, designed a monitoring system..."'
            )
            prompt = prompt.replace(
                '* Project 3 (Technical Integration Opening): "Mediante la integración de Playwright, FastAPI y SSE, automaticé las pruebas E2E..."',
                '* Project 3 (Technical Integration Opening): "Through Playwright, FastAPI, and SSE integration, automated E2E tests..."'
            )
            prompt = prompt.replace(
                '* Project 4 (Metric/Performance Opening): "Reduje los tiempos de respuesta en 45% al implementar mecanismos de caché con Redis..."',
                '* Project 4 (Metric/Performance Opening): "Reduced response times by 45% through Redis caching mechanisms..."'
            )
            print(f"[TRANSLATE] ✂️ Stripped contradictory language rules from prompt (rule 8 + Spanish verb examples).")
        if linkedin_extracted_text:
            prompt += f"""
Extracted LinkedIn Profile Data (Use to enrich and complement the Base Resume):
{linkedin_extracted_text}
"""

        effective_jd = jd.strip() if (jd and jd.strip()) else "No Job Description provided. Perform a comprehensive ATS resume enhancement focused on impact, Google XYZ achievement formula (Action + Context + Measurable Result), strong action verbs, clean structure, and domain-relevant technical skills."

        prompt += f"""
Job Description / Target Requirements:
{effective_jd}
"""
        
        generation_config = {"response_mime_type": "application/json"}
        prompt += """
Respond ONLY with a JSON object in this exact structure. The 'section_labels' field MUST contain the localized section headings in the SAME language as the Job Description:
{
  "name": "Jane Doe",
  "location": "Medellín, Colombia",
  "phone": "555-1234",
  "email": "jane@example.com",
  "portfolio": "",
  "linkedin": "",
  "github": "",
  "summary": "Concise 2-line summary tailored to JD...",
  "education": [{"school": "Universidad Ejemplo", "degree": "Pregrado en Psicología", "dates": "2018 - 2022", "gpa": ""}],
  "skills": [{"category": "Pruebas Psicotécnicas", "items": ["16PF", "DISC", "Wartegg", "Valanti"]}],
  "experience": [{"company": "Empresa Ejemplo", "role": "Analista de Selección", "dates": "2023-01 - Actualidad", "points": ["Lideré procesos de selección...", "Evalué candidatos mediante..."]}],
  "projects": [{"name": "Project Name", "dates": "2025-01", "url": "", "github_url": "https://github.com/user/repo", "points": ["Built X using Y..."]}],
  "achievements": [],
  "section_labels": {
    "summary": "Professional Summary",
    "education": "Education",
    "skills": "Skills",
    "experience": "Work Experience",
    "projects": "Projects",
    "achievements": "Achievements",
    "portfolio": "Portfolio"
  }
}
IMPORTANT:
1. DATE FORMATTING & LOCALIZATION (CRITICAL FOR ATS PARSING):
   - Active / Ongoing Studies & Jobs: If a job or degree started in the past or current date (e.g. "2026-08" when current date is September 2026) and is ongoing, format it as "2026-08 - Actualidad" (Spanish) or "2026-08 - Present" (English).
   - Future Studies & Jobs ONLY: ONLY use "Inicio: YYYY-MM" if the start date is strictly in a future month that has not arrived yet. Do NOT use "Presente" or "Hoy".
2. If the JD is in Spanish, the section_labels values must be in Spanish (e.g. 'Resumen Profesional', 'Educación', 'Habilidades', 'Experiencia Laboral', 'Proyectos', 'Logros', 'Portafolio'). If the JD is in English, they must be in English ('Professional Summary', 'Education', 'Skills', 'Work Experience', 'Projects', 'Achievements', 'Portfolio').
"""

        
        yield f"data: {json.dumps({'step': 'Generating Tailored Resume Content', 'progress': 75})}\n\n"
        try:
            content = await asyncio.wait_for(call_llm_api(prompt), timeout=60.0)
        except asyncio.TimeoutError:
            raise TimeoutError("La generación del CV excedió el límite de 60 segundos. Intenta con un CV más simple o una descripción de trabajo más corta.")
        
        clean_content = content.strip()
        if "```" in clean_content:
            # Extract content inside markdown block if present
            import re
            match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", clean_content)
            if match:
                clean_content = match.group(1)

        try:
            parsed_data = json.loads(clean_content)
        except Exception:
            parsed_data = json.loads(content)
            
        if isinstance(parsed_data, list) and len(parsed_data) > 0:
            parsed_data = parsed_data[0]
            
        if not isinstance(parsed_data, dict):
            raise ValueError("El formato de respuesta de la IA no fue un diccionario válido.")

        # Ensure all expected keys exist to prevent template render errors
        defaults = {
            "name": "", "location": "", "phone": "", "email": "", "portfolio": "", "linkedin": "", "github": "",
            "summary": "", "education": [], "skills": [], "experience": [], "projects": [], "achievements": [],
            "section_labels": {}
        }
        for k, v in defaults.items():
            if k not in parsed_data or parsed_data[k] is None:
                parsed_data[k] = v


        # If user explicitly left GitHub / LinkedIn / Portfolio empty or they contain dummy placeholders, remove them
        # User input overrides if provided; if not provided, fall back to values extracted from the Base Resume
        # so the contact header survives regeneration even when the user does not retype it.
        gh_val = str(parsed_data.get("github", "")).strip()
        is_dummy_gh = any(dummy in gh_val.lower() for dummy in ["github.com/janedoe", "github.com/...", "example", "none"]) if gh_val else True
        if effective_github:
            parsed_data["github"] = effective_github
        elif is_dummy_gh or not gh_val:
            parsed_data["github"] = ""

        li_val = str(parsed_data.get("linkedin", "")).strip()
        is_dummy_li = any(dummy in li_val.lower() for dummy in ["linkedin.com/in/janedoe", "linkedin.com/in/...", "example", "none"]) if li_val else True
        if effective_linkedin:
            parsed_data["linkedin"] = effective_linkedin
        elif is_dummy_li or not li_val:
            parsed_data["linkedin"] = ""

        port_val = str(parsed_data.get("portfolio", "")).strip()
        is_dummy_port = any(dummy in port_val.lower() for dummy in ["janedoe.com", "example.com", "none"]) if port_val else True
        if effective_portfolio:
            parsed_data["portfolio"] = effective_portfolio
        elif is_dummy_port or not port_val:
            parsed_data["portfolio"] = ""

        # Same fallback for email and phone if the LLM dropped them
        em_val = str(parsed_data.get("email", "")).strip()
        if not em_val or any(d in em_val.lower() for d in ["example.com", "your.email", "placeholder"]):
            if extracted_header.get("email"):
                parsed_data["email"] = extracted_header["email"]

        ph_val = str(parsed_data.get("phone", "")).strip()
        if not ph_val or all(c in "0-" for c in ph_val):
            if extracted_header.get("phone"):
                parsed_data["phone"] = extracted_header["phone"]


        # Extract localized section headings from LLM output. The fallback
        # chain is: LLM output (if any) → game's localized labels (ES, then EN)
        # → hardcoded English defaults. Using the game's labels as the fallback
        # ensures the printed headers reflect the domain (e.g. psy 'Formación
        # Académica' instead of generic 'Education').
        default_labels = {
            **game.section_labels_en,   # always available; non-empty for every game
            **(game.section_labels_es if force_language != "en" else {}),
            "summary": "Professional Summary",
            "education": "Education",
            "skills": "Skills",
            "experience": "Work Experience",
            "projects": "Projects",
            "achievements": "Achievements"
        }
        labels = {**default_labels, **parsed_data.get("section_labels", {})}

        # Edit-before-generate path (S2 of yaml-editor feature): stop here,
        # serialise the parsed data as YAML, and stream it back to the
        # frontend so the user can review/edit it before the (separate,
        # LLM-free) render step. No PDF is produced; the frontend can then
        # POST the (possibly edited) YAML to /api/render-from-yaml or
        # /api/analyze-yaml.
        if edit_before_generate:
            try:
                yaml_payload = _yaml_safe_dump_unicode(parsed_data)
            except Exception as yaml_err:
                yield f"data: {json.dumps({'error': f'YAML serialization failed: {yaml_err}'})}\n\n"
                return
            yield f"data: {json.dumps({'step': 'YAML Ready for Review', 'progress': 100, 'yaml': yaml_payload, 'yaml_ready': True})}\n\n"
            return

        yield f"data: {json.dumps({'step': 'Formatting Professional PDF', 'progress': 90})}\n\n"
        
        output_filename = f"tailored_resume_{int(time.time())}.pdf"
        output_path = os.path.join(_OUTPUT_DIR, output_filename)

        use_rendercv = theme and theme != "classic_html"
        rendered = False
        if use_rendercv:
            try:
                print(f"[INFO] 🎨 Rendering PDF with RenderCV theme '{theme}' (fit_single_page={fit_single_page}, page_break_section={page_break_section}, photo={bool(photo_path)})...")
                await asyncio.to_thread(
                    render_cv_with_rendercv, 
                    parsed_data, 
                    output_path, 
                    theme, 
                    fit_single_page, 
                    page_break_section,
                    photo_path
                )
                rendered = True
            except Exception as r_err:
                print(f"[WARN] ⚠️ RenderCV theme '{theme}' failed: {r_err}. Falling back to Playwright HTML renderer.")

        if not rendered:
            print(f"[INFO] 📄 Rendering PDF with Playwright HTML engine (page_break_section={page_break_section})...")
            html_content = _render_html_template(
                parsed_data,
                labels,
                page_break_section=page_break_section,
                photo_path=photo_path,
            )

            def render_pdf_sync():
                with sync_playwright() as p:
                    browser = p.chromium.launch(headless=True)
                    page = browser.new_page()
                    page.set_content(html_content)
                    page.pdf(path=output_path, prefer_css_page_size=True, print_background=True)
                    browser.close()

            await asyncio.to_thread(render_pdf_sync)

        _check_profile_urls_not_fragmented(output_path, parsed_data)

        # Auto re-audit (REQ-4): when force_language='en' triggered the translation
        # path, internally invoke the ATS audit against the freshly rendered PDF so
        # the user sees new ats_score / ai_detection_score in the same response.
        # Graceful degradation: audit failure leaves audit_scores=None (additive
        # payload keeps back-compat for old clients that only read download_url).
        audit_scores = None
        translation_meta = None
        if force_language == "en":
            yield f"data: {json.dumps({'step': 'Auditing translated CV', 'progress': 95})}\n\n"
            try:
                audit_scores = await _run_internal_audit(output_path, jd=jd, custom_instructions=custom_instructions, domain_game=domain_game)
            except Exception as audit_err:
                print(f"[WARN] Auto re-audit failed: {audit_err}")
            translation_meta = {"source_language": source_language, "target_language": "en", "forced": True}

        # Emit the YAML alongside `download_url` so the frontend can capture it
        # as `lastGeneratedYaml` and the user can re-open the YAML editor
        # after a non-edit-before-generate flow. ~2-5KB on the wire.
        # In the edit_before_generate path we returned earlier with the YAML
        # on its own SSE event, so this branch only runs for the direct flow.
        yaml_payload = _yaml_safe_dump_unicode(parsed_data)
        yield f"data: {json.dumps({'step': 'Finished', 'progress': 100, 'download_url': f'/api/download/{output_filename}', 'audit_scores': audit_scores, 'translation': translation_meta, 'yaml': yaml_payload})}\n\n"
        
    except Exception as e:
        import traceback
        print(f"[ERROR IN PIPELINE]: {e}")
        traceback.print_exc()
        yield f"data: {json.dumps({'error': str(e)})}\n\n"


async def _run_internal_audit(
    pdf_path: str,
    jd: Optional[str],
    custom_instructions: Optional[str],
    domain_game: Optional[str] = None,
) -> dict:
    """
    Re-invoke the ATS audit internally against the freshly rendered PDF.
    Reuses the same prompt body as POST /api/analyze-ats (the audit prompt
    in /api/analyze-ats above), but additionally accepts a `domain_game`
    so the audit vocabulary lines up with the CV domain (the audit_scores
    auto-fired after a Translate-to-English flow otherwise carry tech-only
    keywords into actionable_tips for HR / Psychology CVs).
    Returns the parsed dict (already with defensive defaults).
    """
    resume_text = extract_text(pdf_path)
    effective_jd = jd.strip() if (jd and jd.strip()) else (
        custom_instructions.strip() if (custom_instructions and custom_instructions.strip()) else
        "Optimización general y mejoramiento de calidad del CV"
    )
    audit_game = get_game(domain_game)
    return await _run_audit_against_text(
        resume_text=resume_text,
        jd_text=effective_jd,
        audit_game=audit_game,
    )

    return parsed


@app.post("/api/generate")
async def generate_resume(
    request: Request,
    file: UploadFile,
    jd: Optional[str] = Form(None),
    target_role: Optional[str] = Form(None),
    github_url: Optional[str] = Form(None),
    linkedin_url: Optional[str] = Form(None),
    portfolio_url: Optional[str] = Form(None),
    custom_instructions: Optional[str] = Form(None),
    base_resume_filename: Optional[str] = Form(None),
    theme: Optional[str] = Form("sb2nov"),
    fit_single_page: Optional[bool] = Form(False),
    page_break_section: Optional[str] = Form(None),
    extract_linkedin_info: Optional[bool] = Form(False),
    strict_edits_only: Optional[bool] = Form(False),
    force_language: Optional[str] = Form(None),
    domain_game: Optional[str] = Form(None),
    edit_before_generate: Optional[bool] = Form(False),
    photo: Optional[UploadFile] = File(None),
):
    # Rate limit per remote IP (5/minute by default). See enforce_rate_limit
    # comment for why we don't use slowapi's middleware/decorators.
    await enforce_rate_limit(request, scope="generate")
    # Validate force_language early so unsupported values are rejected with HTTP 422
    # before any upload work or LLM call happens.
    if force_language is not None and force_language not in {"en"}:
        raise HTTPException(
            status_code=422,
            detail=f"force_language must be 'en' or omitted, got {force_language!r}"
        )

    # Validate domain_game early. The frontend selector offers:
    #   "tech" (default, preserves v2.5 behaviour),
    #   "hr_recruiting", "psychology".
    # Unknown values fall back to "tech" inside get_game(), but we reject them at
    # the edge so misconfigured clients surface the typo explicitly.
    ALLOWED_GAMES = {"tech", "hr_recruiting", "psychology"}
    if domain_game is not None and domain_game not in ALLOWED_GAMES:
        raise HTTPException(
            status_code=422,
            detail=f"domain_game must be one of {sorted(ALLOWED_GAMES)} or omitted, got {domain_game!r}"
        )

    # Save the original uploaded file temporarily (used as fallback if no base_resume_filename)
    temp_dir = tempfile.gettempdir()
    file_path = os.path.join(temp_dir, file.filename)
    with open(file_path, "wb") as f:
         f.write(await file.read())

    photo_path = await _persist_uploaded_photo(photo)

    return StreamingResponse(
        generation_pipeline(
            file_path,
            jd,
            target_role,
            github_url,
            linkedin_url,
            portfolio_url,
            custom_instructions,
            base_resume_filename,
            theme,
            fit_single_page or False,
            page_break_section,
            extract_linkedin_info or False,
            strict_edits_only or False,
            force_language,
            domain_game,
            edit_before_generate or False,
            photo_path,
        ),
        media_type="text/event-stream"
    )


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


