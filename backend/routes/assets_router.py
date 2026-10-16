"""
backend.routes.assets_router
============================

Serves the generated PDF and clears the cache. Both endpoints are
trivial enough to be wired directly to the ``ResumeStorage`` adapter —
no use case layer needed (they're pure I/O).
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from ports.resume_storage import ResumeStorage


def build_assets_router(storage: ResumeStorage) -> APIRouter:
    """Build the assets router. Takes the storage adapter by DI."""
    router = APIRouter(prefix="/api", tags=["assets"])

    @router.get("/download/{filename}")
    async def download_resume(filename: str):
        """Serve a generated PDF. Path-traversal hardened in the adapter.

        Uses the storage's resolved filesystem path so ``FileResponse``
        can serve via Starlette's streaming layer (which calls ``stat``
        on the path and rejects BytesIO).
        """
        # Use the storage's own validation (regex + is_relative_to).
        try:
            fs_path = storage.resolve_pdf_path(filename)
        except ValueError as err:
            raise HTTPException(status_code=400, detail=str(err)) from err
        except FileNotFoundError as err:
            raise HTTPException(status_code=404, detail="File not found") from err

        return FileResponse(
            str(fs_path),
            filename=filename,
            media_type="application/pdf",
        )

    @router.post("/clear-cache")
    async def clear_cache():
        """Delete every PDF and photo. Returns the counts."""
        try:
            pdfs, photos = storage.clear_all()
        except Exception as err:
            return {"status": "error", "error": str(err)}
        return {
            "status": "ok",
            "deleted_files": pdfs,
            "deleted_photos": photos,
            "message": "Cache, CVs generados y fotos eliminados correctamente.",
        }

    return router


__all__ = ["build_assets_router"]