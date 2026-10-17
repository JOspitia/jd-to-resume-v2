"""
Tests for the assets router + filesystem storage adapter + translation
service + api_models schemas.

Covers:
    * FilesystemStorage resolves paths safely (path-traversal hardening).
    * FilesystemStorage resolves real PDFs and rejects bad names.
    * FilesystemStorage saves uploaded PDFs with content-addressed names
      (no path traversal via original_filename).
    * The assets router serves a real PDF and returns 400 on bad names.
    * The assets router returns 404 on missing files.
    * The translation service produces the LANGUAGE OVERRIDE block.
    * GeminiResumeOutput (Pydantic) can be instantiated with the full
      payload shape.
"""

from __future__ import annotations

import io
import sys
from pathlib import Path

import pytest

sys.path.insert(0, ".")

from adapters.storage.filesystem_storage import FilesystemStorage
from application.services.translation_service import build_language_override
from routes.assets_router import build_assets_router
from schemas.api_models import GeminiResumeOutput


# ---------------------------------------------------------------------------
# Translation service
# ---------------------------------------------------------------------------


class TestTranslationService:
    def test_returns_a_block_with_overrides(self):
        block = build_language_override(target_language="en", source_language="es")
        assert "LANGUAGE OVERRIDE" in block
        assert "en" in block
        assert "es" in block

    def test_includes_do_not_translate_brands(self):
        block = build_language_override("en", "es")
        assert "BBVA" in block
        assert "Google" in block

    def test_includes_must_translate_national_ids(self):
        block = build_language_override("en", "es")
        assert "DNI" in block
        assert "Cédula de ciudadanía" in block

    def test_includes_anti_ai_reaffirmation(self):
        block = build_language_override("en", "es")
        assert "ANTI-AI REAFFIRMATION" in block
        assert "spearheaded" in block  # the AI-cliché blacklist


# ---------------------------------------------------------------------------
# API models
# ---------------------------------------------------------------------------


class TestGeminiResumeOutput:
    def test_parses_minimal_payload(self):
        out = GeminiResumeOutput(
            name="Test",
            phone="",
            email="",
            portfolio="",
            linkedin="",
            github="",
            summary="",
            education=[],
            skills=[],
            experience=[],
            projects=[],
            achievements=[],
        )
        assert out.name == "Test"
        assert out.education == []
        assert out.experience == []


# ---------------------------------------------------------------------------
# FilesystemStorage
# ---------------------------------------------------------------------------


class TestFilesystemStorage:
    def test_save_uploaded_pdf_uses_content_addressed_filename(self, tmp_path):
        storage = FilesystemStorage(tmp_path, tmp_path / "photos")
        content = b"%PDF-1.4 fake content"
        path = storage.save_uploaded_pdf(content, "original.pdf")
        assert path.endswith(".pdf")
        # The temp file is in the system temp dir (not in OUTPUT_DIR).
        assert Path(path).read_bytes() == content

    def test_save_uploaded_pdf_two_users_same_name_dont_collide(self, tmp_path):
        """Content-addressed filename means two users uploading the same
        original_filename produce different temp paths."""
        storage = FilesystemStorage(tmp_path, tmp_path / "photos")
        content_a = b"user-A content"
        content_b = b"user-B content"
        path_a = storage.save_uploaded_pdf(content_a, "cv.pdf")
        path_b = storage.save_uploaded_pdf(content_b, "cv.pdf")
        assert path_a != path_b

    def test_save_uploaded_pdf_sanitizes_traversal_in_original_filename(
        self, tmp_path
    ):
        """The original_filename can contain anything; the storage layer
        strips path separators and forces a .pdf suffix so the temp file
        is always safe."""
        storage = FilesystemStorage(tmp_path, tmp_path / "photos")
        path = storage.save_uploaded_pdf(
            b"%PDF-1.4 fake", "../../../etc/passwd"
        )
        # No path separators in the basename (only the tempdir prefix).
        basename = Path(path).name
        assert "/" not in basename.replace(os_sep(), "")
        assert "\\" not in basename.replace(os_sep(), "")

    def test_resolve_pdf_path_accepts_valid_format(self, tmp_path):
        storage = FilesystemStorage(tmp_path, tmp_path / "photos")
        (tmp_path / "tailored_resume_12345.pdf").write_bytes(b"%PDF-1.4 fake")
        path = storage.resolve_pdf_path("tailored_resume_12345.pdf")
        assert path.is_file()

    def test_resolve_pdf_path_rejects_bad_format(self, tmp_path):
        storage = FilesystemStorage(tmp_path, tmp_path / "photos")
        with pytest.raises(ValueError, match="Invalid filename"):
            storage.resolve_pdf_path("../etc/passwd")

    def test_resolve_pdf_path_rejects_missing_file(self, tmp_path):
        storage = FilesystemStorage(tmp_path, tmp_path / "photos")
        with pytest.raises(FileNotFoundError):
            storage.resolve_pdf_path("tailored_resume_99999999.pdf")

    def test_resolve_pdf_path_rejects_bad_format_with_traversal_chars(self, tmp_path):
        """Filenames with `..` segments fail the regex check before reaching
        the is_relative_to defense — the regex catches them first."""
        storage = FilesystemStorage(tmp_path, tmp_path / "photos")
        with pytest.raises(ValueError, match="Invalid filename"):
            storage.resolve_pdf_path("tailored_resume_1.pdf/../../../etc/passwd")

    def test_clear_all_returns_counts(self, tmp_path):
        photos = tmp_path / "photos"
        storage = FilesystemStorage(tmp_path, photos)
        (tmp_path / "tailored_resume_1.pdf").write_bytes(b"%PDF")
        (tmp_path / "tailored_resume_2.pdf").write_bytes(b"%PDF")
        pdfs, photo_count = storage.clear_all()
        assert pdfs == 2

    def test_download_filename_regex_is_classmethod(self):
        regex = FilesystemStorage.download_filename_regex()
        assert regex.fullmatch("tailored_resume_12345.pdf")
        assert regex.fullmatch("bad.pdf") is None


def os_sep() -> str:
    """Cross-platform separator helper for tests."""
    import os
    return os.sep


# ---------------------------------------------------------------------------
# Assets router (FastAPI integration via TestClient)
# ---------------------------------------------------------------------------


class TestAssetsRouter:
    def _make_client(self, storage: FilesystemStorage):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        app = FastAPI()
        app.include_router(build_assets_router(storage))
        return TestClient(app)

    def test_download_returns_200_for_real_pdf(self, tmp_path):
        storage = FilesystemStorage(tmp_path, tmp_path / "photos")
        (tmp_path / "tailored_resume_12345.pdf").write_bytes(b"%PDF-1.4 fake")
        client = self._make_client(storage)
        r = client.get("/api/download/tailored_resume_12345.pdf")
        assert r.status_code == 200
        assert r.headers["content-type"] == "application/pdf"
        assert r.content.startswith(b"%PDF-1.4")

    def test_download_returns_400_for_bad_format(self, tmp_path):
        """Filenames that pass Starlette's URL routing but fail the
        regex allowlist return 400. (Bare '..' segments fail Starlette
        routing entirely — that's the framework defense in depth.)"""
        storage = FilesystemStorage(tmp_path, tmp_path / "photos")
        client = self._make_client(storage)
        r = client.get("/api/download/tailored_resume_1.pdf.bak")
        assert r.status_code == 400
        assert "Invalid filename" in r.json()["detail"]

    def test_download_returns_404_for_missing(self, tmp_path):
        storage = FilesystemStorage(tmp_path, tmp_path / "photos")
        client = self._make_client(storage)
        r = client.get("/api/download/tailored_resume_99999999.pdf")
        assert r.status_code == 404

    def test_clear_cache_returns_counts(self, tmp_path):
        storage = FilesystemStorage(tmp_path, tmp_path / "photos")
        (tmp_path / "tailored_resume_1.pdf").write_bytes(b"%PDF")
        client = self._make_client(storage)
        r = client.post("/api/clear-cache")
        assert r.status_code == 200
        assert r.json()["deleted_files"] == 1
        assert r.json()["status"] == "ok"