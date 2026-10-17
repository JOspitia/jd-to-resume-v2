"""
backend.routes.assets_router
============================

Serves the generated PDF and clears the cache. Both endpoints are
trivial enough to be wired directly to the ``ResumeStorage`` adapter —
no use case layer needed (they're pure I/O).
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse

from ports.resume_storage import ResumeStorage

# Rate-limit helper lives in the composition root to keep this router free of
# any cross-cutting concerns besides storage DI. The function is imported
# lazily inside ``clear_cache`` so this router stays testable in isolation
# (the legacy main.py shim registered a duplicate of this endpoint that was
# never actually hit — the router version always won the route table).


def build_assets_router(storage: ResumeStorage) -> APIRouter:
    """Build the assets router. Takes the storage adapter by DI."""
    router = APIRouter(prefix="/api", tags=["assets"])

    @router.get("/download/{filename}")
    async def download_resume(filename: str, inline: int = 0):
        """Serve a generated PDF. Path-traversal hardened in the adapter.

        Uses the storage's resolved filesystem path so ``FileResponse``
        can serve via Starlette's streaming layer (which calls ``stat``
        on the path and rejects BytesIO).

        ``?inline=1`` switches the response header from
        ``attachment`` to ``inline`` so the browser's PDF viewer
        (target="_blank") renders the file in-tab instead of treating
        the navigation as a download. Default (``inline=0``) keeps the
        legacy ``attachment; filename=...`` behaviour for direct curl /
        wget / bot fetches.
        """
        # Use the storage's own validation (regex + is_relative_to).
        try:
            fs_path = storage.resolve_pdf_path(filename)
        except ValueError as err:
            raise HTTPException(status_code=400, detail=str(err)) from err
        except FileNotFoundError as err:
            raise HTTPException(status_code=404, detail="File not found") from err

        disposition = "inline" if inline else "attachment"
        return FileResponse(
            str(fs_path),
            filename=filename if not inline else None,
            media_type="application/pdf",
            headers={"content-disposition": f'{disposition}; filename="{filename}"'},
        )

    @router.post("/clear-cache")
    async def clear_cache(request: Request):
        """Delete every PDF and photo. Returns the counts.

        Rate-limited (``scope="clear-cache"``) via the helper exported by
        the composition root (``main.enforce_rate_limit``). Same per-IP
        budget as the other LLM-adjacent endpoints: configurable with
        ``RATE_LIMIT_DEFAULT`` (defaults to ``"5/minute"``).
        """
        from main import enforce_rate_limit  # composition-root helper

        await enforce_rate_limit(request, scope="clear-cache")
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