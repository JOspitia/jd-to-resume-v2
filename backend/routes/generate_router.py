"""Generate router: the HTTP entry point for ``POST /api/generate``.

Pulled out of ``main.py`` during the hexagonal split. The handler is a
thin FastAPI wrapper that:
    1. Validates input (domain_game + force_language).
    2. Persists the optional photo upload.
    3. Enforces the rate limit.
    4. Streams the SSE events from :class:`GenerationService` to the
       client as the pipeline runs.

DI takes the form of a factory ``build_generate_router(service)`` called
from the composition root in ``main.py``.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.responses import StreamingResponse

from application.services.generation_service import GenerationService
from ports.resume_storage import ResumeStorage


def build_generate_router(
    service: GenerationService,
    storage: ResumeStorage,
) -> APIRouter:
    """Build the generate router. DI of the service + storage."""

    router = APIRouter(prefix="/api", tags=["generate"])

    ALLOWED_GAMES = {"tech", "hr_recruiting", "psychology"}

    def _validate_domain_game(domain_game: Optional[str]) -> None:
        from fastapi import HTTPException
        if domain_game is not None and domain_game not in ALLOWED_GAMES:
            raise HTTPException(
                status_code=422,
                detail=(
                    "domain_game must be one of "
                    f"{sorted(ALLOWED_GAMES)} or omitted, got {domain_game!r}"
                ),
            )

    @router.post("/generate")
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
        from main import enforce_rate_limit, _persist_uploaded_photo
        from fastapi import HTTPException

        # Validate request contract
        await enforce_rate_limit(request, scope="generate")
        _validate_domain_game(domain_game)
        if force_language is not None and force_language not in {"en"}:
            raise HTTPException(
                status_code=422,
                detail=f"force_language must be 'en' or omitted, got {force_language!r}",
            )

        # Persist the optional photo first; downstream code wants the path.
        photo_path = await _persist_uploaded_photo(photo)

        # Stream the pipeline output as SSE.
        return StreamingResponse(
            service.run(
                file_path=await _save_upload_to_disk(file),
                jd=jd,
                target_role=target_role,
                github_url=github_url,
                linkedin_url=linkedin_url,
                portfolio_url=portfolio_url,
                custom_instructions=custom_instructions,
                base_resume_filename=base_resume_filename,
                theme=theme,
                fit_single_page=fit_single_page or False,
                page_break_section=page_break_section,
                extract_linkedin_info=extract_linkedin_info or False,
                strict_edits_only=strict_edits_only or False,
                force_language=force_language,
                domain_game=domain_game,
                edit_before_generate=edit_before_generate or False,
                photo_path=photo_path,
            ),
            media_type="text/event-stream",
        )

    return router


async def _save_upload_to_disk(file: UploadFile) -> str:
    """Save the uploaded PDF to a temp file and return its path.

    The original handler in ``main.py`` received a path from
    ``file.filename``-based temp file logic upstream; we replicate the
    minimal contract here (write bytes, return path) so the pipeline's
    first step (extract_text) gets a filesystem path.
    """
    import os
    import tempfile
    from pathlib import Path

    suffix = Path(file.filename or "upload.pdf").suffix or ".pdf"
    fd, path = tempfile.mkstemp(suffix=suffix, dir=tempfile.gettempdir())
    try:
        with os.fdopen(fd, "wb") as f:
            # Read in chunks to handle large PDFs without loading them
            # all into memory at once.
            while True:
                chunk = await file.read(64 * 1024)
                if not chunk:
                    break
                f.write(chunk)
    except Exception:
        try:
            os.unlink(path)
        except OSError:
            pass
        raise
    return path


__all__ = ["build_generate_router"]
