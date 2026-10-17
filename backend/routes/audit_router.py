"""Audit router: ``POST /api/analyze-ats``.

Pulled out of ``main.py`` during the hexagonal split. The handler is
the last LLM-expensive route still in main.py; moving it here
finishes the hexagonal split started in commit ``c34c24c``.

The handler:
    1. Validates the domain_game.
    2. Enforces the rate limit.
    3. Persists the uploaded PDF to a temp file.
    4. Calls :class:`AuditService.audit_pdf` (which extracts text
       internally and runs the LLM audit).
    5. Returns the audit JSON or an error envelope.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile

from application.services.audit_service import AuditService


def build_audit_router(service: AuditService) -> APIRouter:
    """Build the audit router. DI of the audit service."""

    router = APIRouter(prefix="/api", tags=["audit"])

    ALLOWED_GAMES = {"tech", "hr_recruiting", "psychology"}

    @router.post("/analyze-ats")
    async def analyze_ats(
        request: Request,
        file: UploadFile,
        jd: Optional[str] = Form(None),
        domain_game: Optional[str] = Form(None),
    ):
        from main import enforce_rate_limit

        # Validate request contract
        await enforce_rate_limit(request, scope="analyze-ats")
        if domain_game is not None and domain_game not in ALLOWED_GAMES:
            raise HTTPException(
                status_code=422,
                detail=(
                    "domain_game must be one of "
                    f"{sorted(ALLOWED_GAMES)} or omitted, got {domain_game!r}"
                ),
            )

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

            effective_jd = (
                (jd or "").strip()
                or "Optimización general y mejoramiento de calidad del CV"
            )

            from domain_games import get_game
            audit_game = get_game(domain_game)
            return await service.audit_pdf(file_path, effective_jd, audit_game)
        except HTTPException:
            raise
        except Exception as exc:  # noqa: BLE001 — match legacy contract
            import traceback
            traceback.print_exc()
            return {"error": str(exc)}
        finally:
            try:
                os.unlink(file_path)
            except OSError:
                pass

    return router


__all__ = ["build_audit_router"]
