"""YAML editor router.

Three HTTP endpoints:

* ``POST /api/render-from-yaml`` — render a PDF from user-edited YAML.
* ``POST /api/analyze-yaml``    — audit a user-edited YAML.
* ``POST /POST /api/repair-yaml`` — LLM-driven structural repair.

Pulled out of ``main.py`` during the hexagonal split. The render
endpoint uses the same ``PdfRenderer`` factory that
``generate_router`` will use; the analyse / repair endpoints use the
``YamlEditorService`` for parsing / validating / repairing.

DI takes the form of a factory ``build_yaml_editor_router(service, ...)``
called from the composition root in ``main.py``.
"""

from __future__ import annotations

import asyncio
import os
import time
from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from playwright.sync_api import sync_playwright

from application.services.yaml_editor_service import YamlEditorService
from application.rate_limit import enforce_rate_limit
from ports.resume_storage import ResumeStorage
from domain_games import get_game
from render_service import render_cv_with_rendercv

# Rate-limit + photo-helpers live in the composition root for the same
# reason as ``routes/assets_router.py``: cross-cutting concerns don't
# belong in a thin router. Imported lazily inside each endpoint so this
# module stays importable in tests that don't preload ``main``.


def build_yaml_editor_router(
    service: YamlEditorService,
    storage: ResumeStorage,
    audit_service=None,
) -> APIRouter:
    """Build the YAML-editor router. DI of the service + renderer + storage."""

    router = APIRouter(prefix="/api", tags=["yaml-editor"])

    ALLOWED_GAMES = {"tech", "hr_recruiting", "psychology"}

    def _validate_domain_game(domain_game: Optional[str]) -> None:
        if domain_game is not None and domain_game not in ALLOWED_GAMES:
            raise HTTPException(
                status_code=422,
                detail=(
                    "domain_game must be one of "
                    f"{sorted(ALLOWED_GAMES)} or omitted, got {domain_game!r}"
                ),
            )

    # -----------------------------------------------------------------------
    # POST /api/render-from-yaml
    # -----------------------------------------------------------------------
    @router.post("/render-from-yaml")
    async def render_from_yaml(
        request: Request,
        yaml_content: str = Form(...),
        theme: Optional[str] = Form("sb2nov"),
        fit_single_page: Optional[bool] = Form(False),
        page_break_section: Optional[str] = Form(None),
        jd: Optional[str] = Form(None),
        custom_instructions: Optional[str] = Form(None),
        domain_game: Optional[str] = Form(None),
        photo: Optional[UploadFile] = File(None),
    ):
        """Render-only endpoint: parse the user-edited YAML, render PDF.

        No LLM call. Reuses the same RenderCV / Playwright path as
        ``/api/generate``. The body of the work is identical to
        ``generate_router``'s render step; only the parsed_data
        source differs (LLM-produced dict vs user-edited YAML dict).
        """
        from main import _persist_uploaded_photo  # removed in next refactor (commit B of MP-02)

        await enforce_rate_limit(request, scope="render-from-yaml")
        _validate_domain_game(domain_game)

        # Parse the YAML (reuses the service's pure helper).
        from application.services.yaml_editor_service import parse_yaml_safe

        parsed, err = parse_yaml_safe(yaml_content)
        if err or parsed is None:
            raise HTTPException(
                status_code=400,
                detail=err or "Invalid YAML",
            )

        photo_path = await _persist_uploaded_photo(photo)

        # Compose labels using the same fallback chain as /api/generate
        # so the rendered PDF is consistent regardless of source.
        game = get_game(domain_game)
        default_labels = {
            **game.section_labels_es,
            **game.section_labels_en,
            "summary": "Professional Summary",
            "education": "Education",
            "skills": "Skills",
            "experience": "Work Experience",
            "projects": "Projects",
            "achievements": "Achievements",
        }
        labels = {**default_labels, **parsed.get("section_labels", {})}

        # Render PDF. Same path as /api/generate's render step, just with
        # the YAML-sourced ``parsed`` dict.
        output_filename = f"tailored_resume_{int(time.time())}.pdf"
        output_path = os.path.join(storage.output_dir, output_filename)

        use_rendercv = theme and theme != "classic_html"
        rendered = False
        if use_rendercv:
            try:
                print(
                    f"[INFO] Render-from-YAML: RenderCV theme '{theme}' "
                    f"(fit_single_page={fit_single_page}, "
                    f"page_break_section={page_break_section}, "
                    f"photo={bool(photo_path)})..."
                )
                await asyncio.to_thread(
                    render_cv_with_rendercv,
                    parsed,
                    output_path,
                    theme,
                    fit_single_page or False,
                    page_break_section,
                    photo_path,
                )
                rendered = True
            except Exception as r_err:  # noqa: BLE001
                print(
                    f"[WARN] RenderCV theme '{theme}' failed: {r_err}. "
                    "Falling back to Playwright HTML renderer."
                )

        if not rendered:
            from adapters.renderer.playwright_html_adapter import (
                _render_html_template,
                _check_profile_urls_not_fragmented,
            )

            print(
                f"[INFO] Render-from-YAML: Playwright HTML engine "
                f"(page_break_section={page_break_section})..."
            )
            html_content = _render_html_template(
                parsed,
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
            _check_profile_urls_not_fragmented(output_path, parsed)

        return {
            "download_url": f"/api/download/{output_filename}",
            "filename": output_filename,
        }

    # -----------------------------------------------------------------------
    # POST /api/analyze-yaml
    # -----------------------------------------------------------------------
    @router.post("/analyze-yaml")
    async def analyze_yaml(
        request: Request,
        yaml_content: str = Form(...),
        jd: Optional[str] = Form(None),
        domain_game: Optional[str] = Form(None),
    ):
        """Audit-only endpoint for a user-edited YAML. No PDF render."""
        await enforce_rate_limit(request, scope="analyze-yaml")
        _validate_domain_game(domain_game)

        from application.services.yaml_editor_service import parse_yaml_safe
        from yaml_helpers import serialize_resume_data_as_text

        parsed, err = parse_yaml_safe(yaml_content)
        if err or parsed is None:
            raise HTTPException(status_code=400, detail=err or "Invalid YAML")
        if not isinstance(parsed, dict):
            raise HTTPException(
                status_code=400,
                detail=(
                    "Expected a YAML mapping at the top level, got "
                    f"{type(parsed).__name__}"
                ),
            )

        # Serialize the parsed dict to a plain-text narrative that mirrors
        # what ``extract_text`` would yield from a rendered PDF. The audit
        # LLM sees the same shape regardless of source.
        narrative = serialize_resume_data_as_text(parsed)

        effective_jd = (jd or "").strip() or (
            "Optimización general y mejoramiento de calidad del CV"
        )

        audit_game = get_game(domain_game)
        try:
            if audit_service is None:
                raise RuntimeError(
                    "audit_service not wired into yaml_editor_router. "
                    "Pass audit_service=... to build_yaml_editor_router()."
                )
            return await audit_service.audit_text(
                resume_text=narrative,
                jd_text=effective_jd,
                audit_game=audit_game,
            )
        except Exception as exc:  # noqa: BLE001 — match legacy contract
            import traceback
            traceback.print_exc()
            return {"error": str(exc)}

    # -----------------------------------------------------------------------
    # POST /api/repair-yaml
    # -----------------------------------------------------------------------
    @router.post("/repair-yaml")
    async def repair_yaml(
        request: Request,
        yaml_content: str = Form(...),
        domain_game: Optional[str] = Form(None),
    ):
        """Repair a damaged YAML via two-pass LLM fix.

        Pure delegation to :class:`YamlEditorService.repair`. The
        service handles drift guards, schema validation, and the
        two-pass fail-safe return envelope.
        """
        await enforce_rate_limit(request, scope="repair-yaml")
        _validate_domain_game(domain_game)
        return await service.repair(yaml_content, domain_game)

    return router


__all__ = ["build_yaml_editor_router"]
