"""Cover letter router: ``POST /api/cover-letter``.

The handler:
    1. Enforces the rate limit (its own scope, so the letter budget is
       independent from the CV generation budget).
    2. Validates the request contract: domain_game, tone and length.
    3. Persists the uploaded PDF to a temp file.
    4. Calls :meth:`CoverLetterService.generate_from_pdf`.
    5. Returns the structured letter or an error envelope.

The response shape is the contract consumed by
``frontend/src/components/CoverLetterPanel.tsx`` — see
``application/services/cover_letter_service.py`` for the field list.
"""

from __future__ import annotations

import logging
import os
import tempfile
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile

from application.services.cover_letter_service import CoverLetterService


def build_cover_letter_router(service: CoverLetterService) -> APIRouter:
    """Build the cover-letter router. DI of the cover-letter service."""

    router = APIRouter(prefix="/api", tags=["cover-letter"])

    ALLOWED_GAMES = {"tech", "hr_recruiting", "psychology", "general"}
    ALLOWED_TONES = {"professional", "persuasive", "warm", "concise"}
    ALLOWED_LENGTHS = {"short", "medium", "long"}
    ALLOWED_LANGUAGES = {"auto", "es", "en"}

    @router.post("/cover-letter")
    async def create_cover_letter(
        request: Request,
        file: UploadFile,
        jd: Optional[str] = Form(None),
        domain_game: Optional[str] = Form(None),
        target_role: Optional[str] = Form(None),
        company_name: Optional[str] = Form(None),
        tone: Optional[str] = Form(None),
        length: Optional[str] = Form(None),
        language: Optional[str] = Form(None),
        custom_instructions: Optional[str] = Form(None),
        letter_style: Optional[str] = Form(None),
        accent: Optional[str] = Form(None),
        linkedin_url: Optional[str] = Form(None),
        github_url: Optional[str] = Form(None),
        portfolio_url: Optional[str] = Form(None),
    ):
        from application.rate_limit import enforce_rate_limit

        await enforce_rate_limit(request, scope="cover-letter")

        if domain_game is not None and domain_game not in ALLOWED_GAMES:
            raise HTTPException(
                status_code=422,
                detail=(
                    "domain_game must be one of "
                    f"{sorted(ALLOWED_GAMES)} or omitted, got {domain_game!r}"
                ),
            )

        effective_tone = (tone or "professional").strip().lower()
        if effective_tone not in ALLOWED_TONES:
            raise HTTPException(
                status_code=422,
                detail=(
                    "tone must be one of "
                    f"{sorted(ALLOWED_TONES)} or omitted, got {tone!r}"
                ),
            )

        effective_length = (length or "medium").strip().lower()
        if effective_length not in ALLOWED_LENGTHS:
            raise HTTPException(
                status_code=422,
                detail=(
                    "length must be one of "
                    f"{sorted(ALLOWED_LENGTHS)} or omitted, got {length!r}"
                ),
            )

        effective_language = (language or "auto").strip().lower()
        if effective_language not in ALLOWED_LANGUAGES:
            raise HTTPException(
                status_code=422,
                detail=(
                    "language must be one of "
                    f"{sorted(ALLOWED_LANGUAGES)} or omitted, got {language!r}"
                ),
            )

        # The letter style and the accent palette are normalised, not
        # rejected: an unknown value falls back to the default design
        # instead of failing the whole request (same policy as the
        # palette ids in /api/design-options).
        from adapters.renderer.cover_letter_adapter import normalize_letter_style
        from design_palettes import normalize_palette_id

        effective_style = normalize_letter_style(letter_style)
        effective_accent = normalize_palette_id(accent)

        # Persist the upload to a temp file (the parser expects a path).
        suffix = Path(file.filename or "upload.pdf").suffix or ".pdf"
        fd, file_path = tempfile.mkstemp(suffix=suffix, dir=tempfile.gettempdir())
        try:
            with os.fdopen(fd, "wb") as f:
                while True:
                    chunk = await file.read(64 * 1024)
                    if not chunk:
                        break
                    f.write(chunk)

            from domain_games import get_game

            game = get_game(domain_game)
            letter = await service.generate_from_pdf(
                file_path,
                (jd or "").strip(),
                game,
                target_role=(target_role or "").strip(),
                company_name=(company_name or "").strip(),
                tone=effective_tone,
                length=effective_length,
                language=effective_language,
                custom_instructions=(custom_instructions or "").strip(),
                letter_style=effective_style,
                accent=effective_accent,
                linkedin_url=(linkedin_url or "").strip(),
                github_url=(github_url or "").strip(),
                portfolio_url=(portfolio_url or "").strip(),
            )

            # The PDF is served by the same hardened /api/download route
            # the generated CVs use.
            pdf_filename = letter.get("pdf_filename")
            if pdf_filename:
                letter["pdf_url"] = f"/api/download/{pdf_filename}"
            return letter
        except HTTPException:
            raise
        except ValueError as exc:
            # The model answered with something that is not a readable
            # letter. This is a user-facing message, not a server fault.
            raise HTTPException(status_code=502, detail={"error": str(exc)}) from exc
        except Exception as exc:  # noqa: BLE001 — match legacy contract
            logging.exception("cover_letter pipeline failed")
            raise HTTPException(
                status_code=500,
                detail={
                    "error": str(exc),
                    "type": exc.__class__.__name__,
                },
            ) from exc
        finally:
            try:
                os.unlink(file_path)
            except OSError:
                pass

    return router


__all__ = ["build_cover_letter_router"]
