"""Generation service: the end-to-end resume generation pipeline.

Pulled out of ``main.py`` during the hexagonal split. The HTTP endpoint
in ``routes/generate_router.py`` is a thin FastAPI wrapper that calls
:py:meth:`GenerationService.run` and streams its output to the client
as Server-Sent Events.

The pipeline:
    1. Validates input (loads env, handles ``base_resume_filename`` fallback).
    2. Detects source language when ``force_language='en'`` (REQ-3 short-circuit).
    3. Optionally extracts LinkedIn profile data.
    4. Builds the prompt (game-driven, with English-only-mode replacements).
    5. Calls the LLM via the orchestrator.
    6. Sanitises the response (defaults, dummy URL detection).
    7. ``edit_before_generate`` short-circuits to a YAML SSE event.
    8. Renders the PDF (RenderCV, falling back to Playwright HTML).
    9. Optionally re-audits the rendered PDF when ``force_language='en'``
       (REQ-4 auto re-audit).
    10. Emits the final SSE event with the download URL + audit scores.

The service holds the LLM via :class:`application.services.llm_orchestrator.LLMOrchestrator`
and writes output PDFs via :class:`ports.resume_storage.ResumeStorage`.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import time
from typing import AsyncIterator, Optional

from application.services.llm_orchestrator import LLMOrchestrator
from application.services.translation_service import build_language_override
from domain_games import get_game
from language import detect_language
from photo_helpers import prune_orphaned_photos as _prune_photos
from ports.resume_parser import ResumeParser
from ports.resume_storage import ResumeStorage
from render_service import render_cv_with_rendercv
from yaml_helpers import yaml_safe_dump_unicode as _yaml_safe_dump_unicode


# Local imports for the legacy render path; the route does not need to
# know about these because the renderer is chosen inside the pipeline.
from playwright.sync_api import sync_playwright
from adapters.renderer.playwright_html_adapter import (
    _render_html_template,
    _check_profile_urls_not_fragmented,
)
from adapters.parser.pymupdf_adapter import PyMuPDFParser


# Internal helper: lazy builder for the PDF parser so we don't pull PyMuPDF
# at import time of the module (keeps test imports cheap).
_RESUME_PARSER: Optional[ResumeParser] = None


def _get_resume_parser() -> ResumeParser:
    global _RESUME_PARSER
    if _RESUME_PARSER is None:
        _RESUME_PARSER = PyMuPDFParser()
    return _RESUME_PARSER


class GenerationService:
    """The end-to-end CV generation pipeline. Streams SSE events as it runs."""

    def __init__(
        self,
        storage: ResumeStorage,
        llm_orchestrator: LLMOrchestrator,
        audit_service: Optional["AuditService"] = None,
    ) -> None:
        self._storage = storage
        self._llm = llm_orchestrator
        # Audit service is optional: if not injected, the auto re-audit
        # on force_language='en' is silently skipped.
        self._audit_service = audit_service

    # ------------------------------------------------------------------ #
    # Public streaming entry point
    # ------------------------------------------------------------------ #
    async def run(
        self,
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
    ) -> AsyncIterator[str]:
        """Yield SSE-formatted strings. See module docstring for the flow."""
        async for event in self._pipeline(
            file_path=file_path,
            jd=jd,
            target_role=target_role,
            github_url=github_url,
            linkedin_url=linkedin_url,
            portfolio_url=portfolio_url,
            custom_instructions=custom_instructions,
            base_resume_filename=base_resume_filename,
            theme=theme,
            fit_single_page=fit_single_page,
            page_break_section=page_break_section,
            extract_linkedin_info=extract_linkedin_info,
            strict_edits_only=strict_edits_only,
            force_language=force_language,
            domain_game=domain_game,
            edit_before_generate=edit_before_generate,
            photo_path=photo_path,
        ):
            yield event

    # ------------------------------------------------------------------ #
    # Internal pipeline (verbatim port from main.py)
    # ------------------------------------------------------------------ #
    async def _pipeline(
        self,
        file_path: str,
        jd: Optional[str],
        target_role: Optional[str],
        github_url: Optional[str],
        linkedin_url: Optional[str],
        portfolio_url: Optional[str],
        custom_instructions: Optional[str],
        base_resume_filename: Optional[str],
        theme: Optional[str],
        fit_single_page: bool,
        page_break_section: Optional[str],
        extract_linkedin_info: bool,
        strict_edits_only: bool,
        force_language: Optional[str],
        domain_game: Optional[str],
        edit_before_generate: bool,
        photo_path: Optional[str],
    ) -> AsyncIterator[str]:
        """The full pipeline. Yields SSE-formatted strings.

        When `force_language='en'`, prepends AND appends a LANGUAGE OVERRIDE block
        to the system prompt so the output CV is generated in English regardless
        of the source JD language. See ``build_language_override`` for the exact
        wording.

        When `domain_game` is set, the prompt body is composed from the
        corresponding game in ``backend/domain_games/`` instead of the legacy
        tech-only prompt. The available games today are: "tech" (default),
        "hr_recruiting", "psychology". Passing None or an unknown value falls
        back to "tech" (preserves v2.5 behaviour exactly because the tech
        game mirrors the legacy prompt body byte-for-byte).

        When `edit_before_generate=True`, the pipeline stops right after the
        LLM call has been parsed. It serialises `parsed_data` as YAML and
        emits a single SSE event with the form
        ``{"step": "YAML Ready for Review", "progress": 100, "yaml": "...",
        "yaml_ready": true}`` before returning without rendering a PDF. The
        frontend is expected to either POST the (possibly edited) YAML to
        ``/api/render-from-yaml`` (S6) or ``/api/analyze-yaml`` (S8). When
        False (default) the existing PDF render path runs unchanged (S7).
        """
        output_dir = str(self._storage.output_dir)

        if force_language:
            print(
                f"[TRANSLATE] force_language='{force_language}' — LANGUAGE "
                "OVERRIDE will be applied to system prompt (both preamble and tail)."
            )
        print(
            f"[INPUT] github_url='{github_url}', linkedin_url='{linkedin_url}', "
            f"portfolio_url='{portfolio_url}' (received from frontend form)"
        )
        try:
            yield f"data: {json.dumps({'step': 'Validating Input', 'progress': 10})}\n\n"
            await asyncio.sleep(0.5)

            # base_resume_filename fallback
            effective_file_path = file_path
            if base_resume_filename:
                candidate_path = os.path.join(output_dir, base_resume_filename)
                if os.path.exists(candidate_path):
                    effective_file_path = candidate_path
                    print(
                        f"[INFO] ✅ Using previously generated resume as base: {candidate_path}"
                    )
                else:
                    print(
                        f"[WARN] ⚠️ base_resume_filename '{base_resume_filename}' "
                        f"not found in {output_dir}, falling back to original upload."
                    )
                    print(f"[WARN]    Expected path: {candidate_path}")

            # Language detection short-circuit
            source_language = "unknown"
            if force_language == "en":
                detection_path = effective_file_path
                try:
                    source_language = detect_language(
                        _get_resume_parser().extract_text(detection_path)
                    )
                except Exception as detect_err:
                    print(
                        f"[WARN] Language detection failed for '{detection_path}': "
                        f"{detect_err}. Falling back to 'unknown'."
                    )
                    source_language = "unknown"
                print(
                    f"[INFO] force_language='{force_language}', detected "
                    f"source_language='{source_language}', detection_path='{detection_path}'"
                )
                if source_language == "en":
                    raise ValueError("E_CV_ALREADY_ENGLISH::CV already in English")

            yield f"data: {json.dumps({'step': 'Extracting Text from Resume', 'progress': 20})}\n\n"
            resume_text = _get_resume_parser().extract_text(effective_file_path)

            extracted_header = _get_resume_parser().extract_header(resume_text)
            effective_github = (
                github_url.strip()
                if github_url and github_url.strip()
                else extracted_header["github"]
            )
            effective_linkedin = (
                linkedin_url.strip()
                if linkedin_url and linkedin_url.strip()
                else extracted_header["linkedin"]
            )
            effective_portfolio = (
                portfolio_url.strip()
                if portfolio_url and portfolio_url.strip()
                else extracted_header["portfolio"]
            )
            print(
                f"[HEADER] github='{effective_github or '(empty)'}', "
                f"linkedin='{effective_linkedin or '(empty)'}', "
                f"portfolio='{effective_portfolio or '(empty)'}', "
                f"email='{extracted_header['email'] or '(empty)'}', "
                f"phone='{extracted_header['phone'] or '(empty)'}'"
            )
            missing_placeholders = []
            if extracted_header["has_placeholder_github"] and not effective_github:
                missing_placeholders.append("github")
            if extracted_header["has_placeholder_linkedin"] and not effective_linkedin:
                missing_placeholders.append("linkedin")
            if extracted_header["has_placeholder_portfolio"] and not effective_portfolio:
                missing_placeholders.append("portfolio")
            if missing_placeholders:
                print(
                    f"[HEADER] WARN: PDF had placeholder tokens but no URLs found for: "
                    f"{', '.join(missing_placeholders)}. User should fill the form with real URLs."
                )

            linkedin_extracted_text = ""
            if extract_linkedin_info and linkedin_url and linkedin_url.strip():
                yield f"data: {json.dumps({'step': 'Extrayendo datos del perfil de LinkedIn...', 'progress': 35})}\n\n"
                from main import extract_linkedin_profile_data
                linkedin_extracted_text = await extract_linkedin_profile_data(
                    linkedin_url.strip()
                )

            yield f"data: {json.dumps({'step': 'Analyzing with AI Model', 'progress': 50})}\n\n"

            if strict_edits_only:
                user_requested_changes = (
                    custom_instructions.strip()
                    if (custom_instructions and custom_instructions.strip())
                    else (jd.strip() if (jd and jd.strip()) else "No explicit changes specified.")
                )
                language_override_block = ""
                if force_language == "en":
                    language_override_block = build_language_override(
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
                    language_override_block = build_language_override(
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
                prompt += (
                    "12. USER REFINEMENT FEEDBACK & SELECTED TIPS (HIGHEST PRIORITY): "
                    "You MUST explicitly apply the following user-selected improvements, "
                    "tone humanization tips, and custom instructions above all other "
                    f"defaults: {custom_instructions.strip()}\n"
                )

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
            if force_language == "en":
                prompt = prompt.replace(
                    "8. LANGUAGE MATCHING (CRITICAL): Detect the dominant language of the Job Description. Generate ALL text content (summary, bullet points, skill categories, achievements) in THAT SAME language. If the JD is in English → output everything in English. If the JD is in Spanish → output everything in Spanish. Default to the JD language; never mix languages in the same document. Also output the correct localized 'section_labels' accordingly. [OVERRIDDEN when force_language is set — see LANGUAGE OVERRIDE block at the end of this prompt.]",
                    "8. LANGUAGE: ABSOLUTE OVERRIDE APPLIES — see LANGUAGE OVERRIDE block. Do not detect or follow the JD language.",
                )
                prompt = prompt.replace(
                    "Spanish: Diseñé, Implementé, Refactoricé, Despliegué, Migré, Optimicé, Automaticé, Incrementé, Reduje, Agilicé, Maximicé, Consolidé, Lideré, Construí.",
                    "English (only): Engineered, Architected, Implemented, Spearheaded, Optimized, Automated, Streamlined, Reduced, Scaled, Deployed, Refactored, Designed, Built, Led, Migrated.",
                )
                prompt = prompt.replace(
                    'e.g., "Desarrollé [X] mediante [Y] logrando [Z]")',
                    'e.g., "Engineered [X] through [Y] achieving [Z]")',
                )
                prompt = prompt.replace(
                    'e.g., "Incrementé la velocidad de respuesta en 40% al refactorizar los endpoints..."',
                    'e.g., "Reduced response latency by 40% through endpoint refactoring..."',
                )
                prompt = prompt.replace(
                    'e.g., "Ante cuellos de botella en el procesamiento masivo de datos, diseñé una arquitectura de colas..."',
                    'e.g., "Facing throughput bottlenecks in data pipelines, designed a queue-based architecture..."',
                )
                prompt = prompt.replace(
                    'e.g., "Lideré el despliegue del sistema distribuido sobre AWS, reduciendo la latencia a menos de 100ms..."',
                    'e.g., "Led the deployment of the distributed system on AWS, cutting latency below 100ms..."',
                )
                prompt = prompt.replace(
                    'e.g., "Mediante FastAPI y PostgreSQL, automaticé los flujos de facturación eliminando 15 horas semanales de trabajo manual..."',
                    'e.g., "Through FastAPI and PostgreSQL, automated billing flows eliminating 15 hours of manual work per week..."',
                )
                prompt = prompt.replace(
                    'e.g., "Los equipos de bodega carecían de visibilidad en tiempo real; construí una plataforma con Laravel y React que..."',
                    'e.g., "Warehouse teams lacked real-time visibility; built a Laravel + React platform that..."',
                )
                prompt = prompt.replace(
                    'e.g., "Reduje en 40% los costos..."',
                    'e.g., "Cut costs by 40%..."',
                )
                prompt = prompt.replace(
                    'e.g., "Implementé el stack con X, logrando Y en Z%"',
                    'e.g., "Built the stack with X, achieving Y in Z%"',
                )
                prompt = prompt.replace(
                    'e.g., "Implementé el stack con" or starting 4 consecutive bullets with "Desarrollé"',
                    'e.g., "Built the stack with" or starting 4 consecutive bullets with "Engineered"',
                )
                prompt = prompt.replace(
                    '"Construí", "Diseñé e implementé", "Lideré el desarrollo de", "Refactoricé", "Desplegué", "Migré"',
                    '"Built", "Designed and implemented", "Led the development of", "Refactored", "Deployed", "Migrated"',
                )
                prompt = prompt.replace(
                    '"Implementé el stack con...", "Desarrollé una...", or "Construí una..."',
                    '"Built the stack with...", "Developed a...", or "Engineered a..."',
                )
                prompt = prompt.replace(
                    '* Project 1 (Architectural/Innovation Opening): "Arquitecturé una plataforma de optimización de CVs basada en la orquestación de LLMs y renderizado Typst..."',
                    '* Project 1 (Architectural/Innovation Opening): "Architected a CV optimization platform based on LLM orchestration and Typst rendering..."',
                )
                prompt = prompt.replace(
                    '* Project 2 (Problem/Business Opening): "Para resolver la falta de visibilidad del inventario en tiempo real, diseñé un sistema de monitoreo..."',
                    '* Project 2 (Problem/Business Opening): "To solve the lack of real-time inventory visibility, designed a monitoring system..."',
                )
                prompt = prompt.replace(
                    '* Project 3 (Technical Integration Opening): "Mediante la integración de Playwright, FastAPI y SSE, automaticé las pruebas E2E..."',
                    '* Project 3 (Technical Integration Opening): "Through Playwright, FastAPI, and SSE integration, automated E2E tests..."',
                )
                prompt = prompt.replace(
                    '* Project 4 (Metric/Performance Opening): "Reduje los tiempos de respuesta en 45% al implementar mecanismos de caché con Redis..."',
                    '* Project 4 (Metric/Performance Opening): "Reduced response times by 45% through Redis caching mechanisms..."',
                )
                print("[TRANSLATE] ✂️ Stripped contradictory language rules from prompt (rule 8 + Spanish verb examples).")
            if linkedin_extracted_text:
                prompt += f"""
Extracted LinkedIn Profile Data (Use to enrich and complement the Base Resume):
{linkedin_extracted_text}
"""

            effective_jd = (
                jd.strip()
                if (jd and jd.strip())
                else "No Job Description provided. Perform a comprehensive ATS resume enhancement focused on impact, Google XYZ achievement formula (Action + Context + Measurable Result), strong action verbs, clean structure, and domain-relevant technical skills."
            )

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
                content = await asyncio.wait_for(self._call_llm(prompt), timeout=60.0)
            except asyncio.TimeoutError:
                raise TimeoutError(
                    "La generación del CV excedió el límite de 60 segundos. "
                    "Intenta con un CV más simple o una descripción de trabajo más corta."
                )

            clean_content = content.strip()
            if "```" in clean_content:
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

            defaults = {
                "name": "", "location": "", "phone": "", "email": "", "portfolio": "", "linkedin": "", "github": "",
                "summary": "", "education": [], "skills": [], "experience": [], "projects": [], "achievements": [],
                "section_labels": {}
            }
            for k, v in defaults.items():
                if k not in parsed_data or parsed_data[k] is None:
                    parsed_data[k] = v

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

            em_val = str(parsed_data.get("email", "")).strip()
            if not em_val or any(d in em_val.lower() for d in ["example.com", "your.email", "placeholder"]):
                if extracted_header.get("email"):
                    parsed_data["email"] = extracted_header["email"]

            ph_val = str(parsed_data.get("phone", "")).strip()
            if not ph_val or all(c in "0-" for c in ph_val):
                if extracted_header.get("phone"):
                    parsed_data["phone"] = extracted_header["phone"]

            default_labels = {
                **game.section_labels_en,
                **(game.section_labels_es if force_language != "en" else {}),
                "summary": "Professional Summary",
                "education": "Education",
                "skills": "Skills",
                "experience": "Work Experience",
                "projects": "Projects",
                "achievements": "Achievements"
            }
            labels = {**default_labels, **parsed_data.get("section_labels", {})}

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
            output_path = os.path.join(output_dir, output_filename)

            use_rendercv = theme and theme != "classic_html"
            rendered = False
            if use_rendercv:
                try:
                    print(
                        f"[INFO] 🎨 Rendering PDF with RenderCV theme '{theme}' "
                        f"(fit_single_page={fit_single_page}, page_break_section={page_break_section}, "
                        f"photo={bool(photo_path)})..."
                    )
                    await asyncio.to_thread(
                        render_cv_with_rendercv,
                        parsed_data,
                        output_path,
                        theme,
                        fit_single_page,
                        page_break_section,
                        photo_path,
                    )
                    rendered = True
                except Exception as r_err:
                    print(
                        f"[WARN] ⚠️ RenderCV theme '{theme}' failed: {r_err}. "
                        "Falling back to Playwright HTML renderer."
                    )

            if not rendered:
                print(
                    f"[INFO] 📄 Rendering PDF with Playwright HTML engine "
                    f"(page_break_section={page_break_section})..."
                )
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
                        page.pdf(
                            path=output_path,
                            prefer_css_page_size=True,
                            print_background=True,
                        )
                        browser.close()

                await asyncio.to_thread(render_pdf_sync)
                _check_profile_urls_not_fragmented(output_path, parsed_data)

            audit_scores = None
            translation_meta = None
            if force_language == "en":
                yield f"data: {json.dumps({'step': 'Auditing translated CV', 'progress': 95})}\n\n"
                try:
                    audit_scores = await self.run_internal_audit(
                        output_path, jd=jd,
                        custom_instructions=custom_instructions,
                        domain_game=domain_game,
                    )
                except Exception as audit_err:
                    print(f"[WARN] Auto re-audit failed: {audit_err}")
                translation_meta = {"source_language": source_language, "target_language": "en", "forced": True}

            yaml_payload = _yaml_safe_dump_unicode(parsed_data)
            download_url = f"/api/download/{output_filename}"
            finish_event = {
                "step": "Finished",
                "progress": 100,
                "download_url": download_url,
                "audit_scores": audit_scores,
                "translation": translation_meta,
                "yaml": yaml_payload,
            }
            yield f"data: {json.dumps(finish_event)}\n\n"

        except Exception as e:
            import traceback
            print(f"[ERROR IN PIPELINE]: {e}")
            traceback.print_exc()
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    # ------------------------------------------------------------------ #
    # LLM helper
    # ------------------------------------------------------------------ #
    async def _call_llm(self, prompt: str) -> str:
        """Wrap the LLM orchestrator's call. The orchestrator builds the
        cascade and applies timeouts / fallback policy."""
        return await self._llm.complete(prompt)

    # ------------------------------------------------------------------ #
    # Internal audit (used by force_language='en' re-audit path)
    # ------------------------------------------------------------------ #
    async def run_internal_audit(
        self,
        pdf_path: str,
        jd: Optional[str],
        custom_instructions: Optional[str],
        domain_game: Optional[str] = None,
    ) -> dict:
        """Re-invoke the ATS audit internally against the freshly rendered PDF.

        Used by the generation pipeline's auto re-audit step (REQ-4) when
        ``force_language='en'`` triggers the translation path.

        Delegates to the injected ``AuditService``. ``custom_instructions``
        is part of the legacy signature but the audit pipeline today only
        uses ``jd``; it stays for backward compat.
        """
        if self._audit_service is None:
            raise RuntimeError(
                "GenerationService.run_internal_audit called without an "
                "AuditService wired in. Pass audit_service=... to the "
                "constructor."
            )
        effective_jd = (
            (jd or "").strip()
            or "Optimización general y mejoramiento de calidad del CV"
        )
        audit_game = get_game(domain_game)
        return await self._audit_service.audit_pdf(
            pdf_path=pdf_path,
            jd_text=effective_jd,
            audit_game=audit_game,
        )


__all__ = ["GenerationService"]
