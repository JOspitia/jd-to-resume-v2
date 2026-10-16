"""
backend.adapters.storage.filesystem_storage
===========================================

Adapter that persists generated PDFs and candidate photos to the local
disk. Implements the ``ResumeStorage`` port.

Path-traversal hardening lives here (regex allowlist + ``is_relative_to``),
NOT in the route — the route's only job is to call ``storage.read_pdf``.
"""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import tempfile
import time
from pathlib import Path
from typing import Optional, Union

from photo_helpers import prune_orphaned_photos as _prune_photos
from photo_helpers import save_photo as _save_photo
from ports.resume_storage import ResumeStorage


# Filename pattern: tailored_resume_<unix_seconds>.pdf. The downstream route
# uses the SAME regex to validate read requests.
_DOWNLOAD_FILENAME_RE = re.compile(r"^tailored_resume_\d+\.pdf$")


class FilesystemStorage:
    """Adapter that persists PDFs and photos to the local filesystem."""

    def __init__(
        self,
        output_dir: Union[str, Path],
        photos_dir: Union[str, Path],
    ) -> None:
        self._output_dir = Path(output_dir)
        self._photos_dir = Path(photos_dir)
        self._output_dir.mkdir(parents=True, exist_ok=True)
        self._photos_dir.mkdir(parents=True, exist_ok=True)

    @property
    def output_dir(self) -> Path:
        return self._output_dir

    @property
    def photos_dir(self) -> Path:
        return self._photos_dir

    @staticmethod
    def download_filename_regex() -> re.Pattern:
        """Return the regex the download route uses to validate filenames."""
        return _DOWNLOAD_FILENAME_RE

    def save_uploaded_pdf(
        self,
        content: bytes,
        original_filename: str,
    ) -> str:
        """Persist an uploaded PDF to a temp file. Returns the absolute path.

        Uses a content-addressed filename (sha256[:16]) so two concurrent
        uploads with the same ``original_filename`` don't collide and
        the file is safe to write (no path traversal).
        """
        digest = hashlib.sha256(content).hexdigest()[:16]
        safe_name = re.sub(r"[^A-Za-z0-9._-]", "_", original_filename or "upload.pdf")
        if not safe_name.lower().endswith(".pdf"):
            safe_name = safe_name + ".pdf"
        fd, tmp_path = tempfile.mkstemp(
            prefix=f"upload_{digest}_", suffix=f"_{safe_name}", dir=tempfile.gettempdir()
        )
        with os.fdopen(fd, "wb") as f:
            f.write(content)
        return tmp_path

    def save_generated_pdf(self, source_path: str) -> str:
        """Promote a generated PDF to the persistent output dir with the
        canonical ``tailored_resume_<ts>.pdf`` name.

        Returns the absolute path of the final file.
        """
        filename = f"tailored_resume_{int(time.time())}.pdf"
        dest = self._output_dir / filename
        shutil.copy(source_path, dest)
        return str(dest)

    def read_pdf(self, filename: str) -> bytes:
        """Read a persisted PDF. Raises if the name doesn't match the
        canonical pattern or the file does not exist."""
        path = self.resolve_pdf_path(filename)
        return path.read_bytes()

    def resolve_pdf_path(self, filename: str) -> Path:
        """Resolve the absolute filesystem path of a stored PDF after
        validating the filename against the regex allowlist + ensuring
        the path is within the output dir. Raises ``ValueError`` on a
        bad name or path-traversal attempt, ``FileNotFoundError`` if the
        file doesn't exist.

        Used by routes that need a real path (e.g. ``FileResponse``).
        """
        if not _DOWNLOAD_FILENAME_RE.fullmatch(filename):
            raise ValueError(
                f"Invalid filename format: {filename!r}. "
                f"Expected {_DOWNLOAD_FILENAME_RE.pattern}"
            )
        resolved = (self._output_dir / filename).resolve()
        if not resolved.is_relative_to(self._output_dir.resolve()):
            raise ValueError(f"Path traversal attempt: {filename!r}")
        if not resolved.is_file():
            raise FileNotFoundError(filename)
        return resolved

    def delete_pdf(self, filename: str) -> None:
        """Delete one PDF. No-op if the file does not exist."""
        if not _DOWNLOAD_FILENAME_RE.fullmatch(filename):
            return
        path = self._output_dir / filename
        try:
            path.unlink(missing_ok=True)
        except Exception:
            pass

    def save_photo(self, content: bytes) -> str:
        """Persist a candidate photo. Returns the absolute path."""
        return _save_photo(content, str(self._photos_dir))

    def clear_all(self) -> tuple[int, int]:
        """Delete every PDF and photo. Returns (pdfs_deleted, photos_deleted)."""
        pdfs_deleted = 0
        if self._output_dir.exists():
            for entry in self._output_dir.iterdir():
                if entry.is_file():
                    try:
                        entry.unlink()
                        pdfs_deleted += 1
                    except Exception as err:
                        print(f"Could not remove {entry}: {err}")
        photos_deleted = _prune_photos(self._photos_dir, keep=set())
        return pdfs_deleted, photos_deleted


__all__ = ["FilesystemStorage"]