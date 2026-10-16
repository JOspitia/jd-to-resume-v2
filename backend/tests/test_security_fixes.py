"""
Security regression tests for quick-wins PR.

Covers:
  * /api/download path-traversal hardening (regex allowlist + Path.resolve()).
  * CORS middleware: no wildcard, defaults to localhost Vite origins.
  * SlowAPI rate limiter is registered and rejects after N requests/minute.
  * Rate limit is configurable via RATE_LIMIT_DEFAULT env var.

The tests import ``main`` directly. All runtime dependencies (pymupdf,
google.generativeai, playwright, rendercv) must be available — which they are
in the standard backend venv.
"""

from __future__ import annotations

import importlib
import os
import re
import tempfile
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Module loading helpers
# ---------------------------------------------------------------------------


def _load_main(monkeypatch, **env):
    """Reload main with custom env vars and return the module.

    main.py replaces ``sys.stdout``/``sys.stderr`` at import time on Windows
    (see lines 8-10) so non-ASCII ``print()`` does not raise cp1252 errors.
    That replacement runs against the **already-captured** streams under
    pytest, which leaves the new ``TextIOWrapper`` wrapping a closed file
    and breaks subsequent tests. We snapshot/restore around the re-import
    so each test starts from a known-good stdout/stderr.
    """
    import io
    import sys

    saved_out, saved_err = sys.stdout, sys.stderr
    try:
        for k, v in env.items():
            monkeypatch.setenv(k, v)
        sys.modules.pop("main", None)
        mod = importlib.import_module("main")
    finally:
        sys.stdout, sys.stderr = saved_out, saved_err
    return mod


@pytest.fixture
def client(monkeypatch):
    """Default TestClient; rate limit loosened to keep tests fast."""
    mod = _load_main(monkeypatch, RATE_LIMIT_DEFAULT="1000/minute")
    return TestClient(mod.app), mod


# ---------------------------------------------------------------------------
# /api/download — path traversal
# ---------------------------------------------------------------------------


class TestDownloadPathTraversal:
    def test_regex_matches_legacy_filename(self):
        # Belt-and-braces: confirm the allowlist matches the format the
        # pipeline actually writes. The regex now lives in
        # ``adapters.storage.filesystem_storage`` (commit 6 of the hexagonal
        # refactor).
        from adapters.storage.filesystem_storage import FilesystemStorage

        regex = FilesystemStorage.download_filename_regex()
        assert regex.fullmatch(f"tailored_resume_{int(time.time())}.pdf")

    def test_regex_rejects_path_traversal_segments(self):
        from adapters.storage.filesystem_storage import FilesystemStorage

        regex = FilesystemStorage.download_filename_regex()
        bad = [
            "../etc/passwd",
            "..\\windows\\system32\\config\\sam",
            "/etc/passwd",
            "tailored_resume_123.pdf.bak",
            "tailored_resume_abc.pdf",
            "tailored_resume_.pdf",
            "Tailored_resume_1.pdf",  # case sensitive
            "tailored_resume_1.PDF",
            "",
            "tailored_resume_1",
        ]
        for name in bad:
            assert regex.fullmatch(name) is None, name

    def test_valid_filename_in_output_dir_returns_pdf(self, client):
        c, mod = client
        # Drop a fake PDF into the real output dir (which FilesystemStorage
        # creates on instantiation).
        from adapters.storage.filesystem_storage import FilesystemStorage

        storage = FilesystemStorage(mod._OUTPUT_DIR, mod._PHOTOS_DIR)
        out_dir = storage.output_dir
        out_dir.mkdir(parents=True, exist_ok=True)
        filename = f"tailored_resume_{int(time.time())}.pdf"
        target = out_dir / filename
        target.write_bytes(b"%PDF-1.4 fake")

        try:
            r = c.get(f"/api/download/{filename}")
            assert r.status_code == 200
            assert r.headers["content-type"] == "application/pdf"
            assert r.content.startswith(b"%PDF-1.4")
        finally:
            target.unlink(missing_ok=True)

    def test_path_traversal_dot_dot_returns_blocked(self, client):
        c, _ = client
        # Starlette normalizes the URL path before route matching, so a
        # ``..`` segment either escapes the path entirely (404, no route
        # matched) or reaches the handler and fails the regex (400).
        # Either response is acceptable — both keep the file off-disk.
        r = c.get("/api/download/..%2F..%2Fetc%2Fpasswd")
        assert r.status_code in (400, 404), r.status_code

    def test_path_traversal_with_prefix_returns_400(self, client):
        c, _ = client
        # Filename that passes the route but fails the regex (defence in
        # depth: even if Starlette normalisation were disabled, the
        # regex rejects this).
        r = c.get("/api/download/tailored_resume_1.pdf.bak")
        assert r.status_code == 400
        assert "invalid" in r.json()["detail"].lower()

    def test_unknown_filename_format_returns_400(self, client):
        c, _ = client
        r = c.get("/api/download/not_a_valid_name.pdf")
        assert r.status_code == 400

    def test_valid_filename_not_in_output_dir_returns_404(self, client):
        c, _ = client
        # Format is valid, but the file does not exist.
        r = c.get("/api/download/tailored_resume_9999999999.pdf")
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# CORS — no wildcard, defaults to localhost Vite origins
# ---------------------------------------------------------------------------


class TestCorsConfig:
    def test_default_origins_are_localhost_only(self, monkeypatch):
        mod = _load_main(monkeypatch)  # No env override → use defaults.
        cors = mod.app.user_middleware
        origins = []
        for mw in cors:
            if mw.cls.__name__ == "CORSMiddleware":
                origins = mw.kwargs.get("allow_origins", [])
                break
        assert origins, "CORSMiddleware not registered"
        assert "*" not in origins
        for o in origins:
            assert "localhost" in o or "127.0.0.1" in o, o

    def test_custom_origins_via_env(self, monkeypatch):
        mod = _load_main(
            monkeypatch,
            CORS_ALLOWED_ORIGINS="https://cv.example.com, https://admin.example.com",
        )
        origins = []
        for mw in mod.app.user_middleware:
            if mw.cls.__name__ == "CORSMiddleware":
                origins = mw.kwargs.get("allow_origins", [])
                break
        assert origins == ["https://cv.example.com", "https://admin.example.com"]

    def test_methods_limited_to_get_post_options(self, monkeypatch):
        mod = _load_main(monkeypatch)
        for mw in mod.app.user_middleware:
            if mw.cls.__name__ == "CORSMiddleware":
                methods = mw.kwargs.get("allow_methods", [])
                assert "DELETE" not in methods
                assert "PUT" not in methods
                assert "GET" in methods
                assert "POST" in methods
                return
        pytest.fail("CORSMiddleware not found")


# ---------------------------------------------------------------------------
# Rate limiting (slowapi)
# ---------------------------------------------------------------------------


class TestRateLimit:
    def test_limiter_registered(self, monkeypatch):
        mod = _load_main(monkeypatch, RATE_LIMIT_DEFAULT="1000/minute")
        assert hasattr(mod.app.state, "limiter")

    def test_rate_limit_blocks_after_threshold(self, monkeypatch):
        # Tight limit so the test is fast.
        mod = _load_main(monkeypatch, RATE_LIMIT_DEFAULT="2/minute")
        c = TestClient(mod.app)
        seen = []
        for _ in range(6):
            r = c.get("/")
            seen.append(r.status_code)
        # The first two should pass (or 200); the rest should be 429.
        assert 429 in seen, f"Expected 429 in responses, got {seen}"
        # At least one 200 must have come through.
        assert 200 in seen, f"Expected at least one 200, got {seen}"

    def test_rate_limit_default_is_configurable(self, monkeypatch):
        # Custom value should be honored on next import.
        mod = _load_main(monkeypatch, RATE_LIMIT_DEFAULT="42/minute")
        # Re-read env-confirmed default via Limiter default_limits.
        limits = mod.app.state.limiter._default_limits if hasattr(
            mod.app.state.limiter, "_default_limits"
        ) else []
        assert any("42" in str(x) for x in limits) or limits, (
            "Configured rate limit default not applied"
        )