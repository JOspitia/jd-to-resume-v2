"""
backend.ports.resume_storage
===========================

Port for the persistence layer that owns generated PDFs and candidate photos.

One adapter today:
    * FilesystemStorage  (writes to ``backend/output/`` + ``backend/output/photos/``)

The PDF path-traversal hardening (regex allowlist + ``is_relative_to``)
lives inside this adapter — not in the routes. The route's only job is
to call ``storage.read_pdf(filename)`` and let the adapter validate.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class ResumeStorage(Protocol):
    """Persists generated PDFs and candidate photos."""

    def save_uploaded_pdf(self, content: bytes, original_filename: str) -> str:
        """Persist the bytes the user just uploaded as a temp file. Returns
        the absolute path the rest of the pipeline reads from.

        ``original_filename`` is for diagnostics only — the storage layer
        must NOT use it as-is on the filesystem (path-traversal risk);
        the adapter is responsible for sanitizing or hashing the name.
        """
        ...

    def save_generated_pdf(self, source_path: str) -> str:
        """Promote a generated PDF (typically in /tmp) to the persistent
        ``OUTPUT_DIR`` with the canonical ``tailored_resume_<ts>.pdf`` name.
        Returns the absolute path of the final file."""
        ...

    def read_pdf(self, filename: str) -> bytes:
        """Read a persisted PDF by name. Raises if the name doesn't match
        the canonical pattern or the file does not exist."""
        ...

    def delete_pdf(self, filename: str) -> None:
        """Delete one PDF. No-op if the file does not exist."""
        ...

    def save_photo(self, content: bytes) -> str:
        """Persist an optional candidate photo. Returns the absolute path
        to renderers (RenderCV wants a filesystem path; Playwright HTML
        gets a data URI built from the same file)."""
        ...

    def clear_all(self) -> tuple[int, int]:
        """Delete every generated PDF and photo. Returns
        ``(pdfs_deleted, photos_deleted)``."""
        ...


__all__ = ["ResumeStorage"]