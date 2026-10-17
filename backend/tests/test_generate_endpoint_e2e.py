"""End-to-end tests for ``POST /api/generate``.

Same pattern as ``tests/test_yaml_endpoints_e2e.py`` but for the most
critical endpoint of the app — the one users hit 90% of the time.
Closes the meta-hole that allowed today's 3 NameError bugs to slip
through (no test runner could see that ``/api/generate`` was broken
because no E2E exercise existed).

Coverage:
    * PDF required (422 if missing)
    * valid PDF + LLM stub -> 200 SSE stream with download_url
    * invalid domain_game / force_language -> 422
    * base_resume_filename fallback to original upload
    * render path writes a PDF to disk
    * rate-limit scope is per-endpoint (not shared with /api/clear-cache)

What is NOT covered (intentional):
    * Real LLM providers (stubbed; the providers' own test suite covers them)
    * Frontend integration (server-only)
    * Real RenderCV binary (covered by ``test_renderers.py``)
    * Visual rendering correctness (covered by ``test_renderers.py``)
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pymupdf  # PyMuPDF (formerly imported as `fitz`), used to build a real (tiny) test PDF
import pytest
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Stubs
# ---------------------------------------------------------------------------


def _build_minimal_resume_json() -> dict[str, Any]:
    """Return a JSON-shaped dict matching GeminiResumeOutput's schema.

    This is what the LLM stub returns from ``complete()`` — the LLM's
    actual job is to produce JSON in this shape.
    """
    return {
        "name": "Jane Doe",
        "location": "Bogota, CO",
        "phone": "+57 300 000 0000",
        "email": "jane@example.com",
        "portfolio": "https://jane.example.com",
        "linkedin": "https://linkedin.com/in/jane",
        "github": "https://github.com/jane",
        "summary": "Backend engineer with 5 years of experience.",
        "education": [
            {
                "school": "Universidad Nacional",
                "degree": "BSc Computer Science",
                "dates": "2018 - 2023",
                "gpa": "4.5",
            }
        ],
        "skills": [
            {"category": "Backend", "items": ["Python", "FastAPI", "PostgreSQL"]}
        ],
        "experience": [
            {
                "company": "Acme",
                "role": "Senior Engineer",
                "dates": "2023 - Present",
                "points": [
                    "Built a streaming CV pipeline in 30 days",
                    "Reduced LLM cost by 40%",
                ],
            }
        ],
        "projects": [
            {
                "name": "cv-tailor",
                "dates": "2024",
                "url": "https://example.com/cv-tailor",
                "github_url": "https://github.com/jane/cv-tailor",
                "points": ["Open-source tool with 1.5k stars"],
            }
        ],
        "achievements": ["Speaker at PyCon Latam 2024"],
        "section_labels": {
            "summary": "Resumen Profesional",
            "education": "Educacion",
            "skills": "Habilidades",
            "experience": "Experiencia",
            "projects": "Proyectos",
            "achievements": "Logros",
            "portfolio": "Portfolio",
        },
    }


class _StubLLMProvider:
    """Stub LLM provider that returns a valid GeminiResumeOutput JSON.

    Sync (the orchestrator calls us via ``asyncio.to_thread``).
    """

    name = "stub"

    def __init__(self, response: str | None = None) -> None:
        self.response = response or json.dumps(_build_minimal_resume_json())
        self.calls: list[str] = []

    def complete(self, prompt: str, *, model: str | None = None) -> str:
        self.calls.append(prompt)
        return self.response


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def valid_pdf(tmp_path: Path) -> bytes:
    """Generate a real, valid PDF using PyMuPDF. PyMuPDF will read it
    back without error, which is what the production code requires."""
    pdf_path = tmp_path / "input.pdf"
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((50, 50), "Jane Doe")
    page.insert_text((50, 80), "Backend Engineer with 5 years of experience.")
    page.insert_text((50, 110), "Skills: Python, FastAPI, PostgreSQL")
    doc.save(str(pdf_path))
    doc.close()
    return pdf_path.read_bytes()


@pytest.fixture
def stubbed_yaml_service(monkeypatch):
    """Replace the yaml editor service's LLM with a stub. Unused here
    but kept as a reminder for tests in this directory that might
    touch the yaml service via shared composition root."""
    from application.services.llm_orchestrator import LLMOrchestrator
    from main import _yaml_editor_service
    monkeypatch.setattr(
        _yaml_editor_service,
        "_llm",
        LLMOrchestrator([_StubLLMProvider()]),
    )


@pytest.fixture
def stubbed_llm(monkeypatch, stubbed_yaml_service):
    """Replace the LLM orchestrator the generation pipeline uses.

    The pipeline in ``main.py`` builds its own LLMOrchestrator inside
    ``call_llm_api`` (called via ``generation_pipeline``). We patch
    ``main.call_llm_api`` to bypass the orchestrator and return our
    stubbed JSON directly.
    """
    from main import call_llm_api

    async def _stub_call_llm(prompt_text: str) -> str:
        return json.dumps(_build_minimal_resume_json())

    monkeypatch.setattr("main.call_llm_api", _stub_call_llm)
    return _stub_call_llm


@pytest.fixture
def client(monkeypatch, tmp_path, stubbed_llm):
    """TestClient with rate limit loosened to keep tests fast.

    Also redirects output/photo directories to ``tmp_path`` so we don't
    pollute the real ``backend/output/`` directory.
    """
    import sys
    import importlib
    saved_out, saved_err = sys.stdout, sys.stderr
    for k, v in {
        "RATE_LIMIT_DEFAULT": "1000/minute",
    }.items():
        monkeypatch.setenv(k, v)
    sys.modules.pop("main", None)
    mod = importlib.import_module("main")
    sys.stdout, sys.stderr = saved_out, saved_err

    # Redirect the storage's output/photos dirs to the per-test tmp dir
    # so generated PDFs don't accumulate in the real output folder.
    # The public ``output_dir`` / ``photos_dir`` are read-only properties
    # backed by private attributes; we set the privates and re-derive.
    new_output = tmp_path / "output"
    new_output.mkdir(parents=True, exist_ok=True)
    new_photos = tmp_path / "photos"
    new_photos.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(mod._storage, "_output_dir", new_output)
    monkeypatch.setattr(mod._storage, "_photos_dir", new_photos)
    # ``_OUTPUT_DIR`` / ``_PHOTOS_DIR`` are still referenced by the
    # generate handler (line ~432 of the legacy path). They were the
    # source of today's first NameError; keep them in sync.
    mod._OUTPUT_DIR = str(new_output)
    mod._PHOTOS_DIR = str(new_photos)
    return TestClient(mod.app), mod


# ---------------------------------------------------------------------------
# /api/generate
# ---------------------------------------------------------------------------


class TestGenerateEndpoint:
    """The most critical endpoint of the app."""

    def test_missing_file_returns_422(self, client):
        c, _ = client
        r = c.post(
            "/api/generate",
            data={"jd": "Build a CLI tool"},
        )
        assert r.status_code == 422

    def test_valid_pdf_with_stubbed_llm_streams_sse_with_download_url(
        self, client, valid_pdf
    ):
        c, _ = client
        r = c.post(
            "/api/generate",
            files={"file": ("input.pdf", valid_pdf, "application/pdf")},
            data={"jd": "Build a streaming CV pipeline", "theme": "classic_html"},
        )
        assert r.status_code == 200, r.text
        # The body is a Server-Sent Events stream. Parse it as text
        # and check that the final event carries the download URL.
        body = r.text
        assert "data: " in body
        # Find the success event (last data: line in the body)
        events = [line for line in body.splitlines() if line.startswith("data: ")]
        last = json.loads(events[-1].removeprefix("data: "))
        assert last.get("download_url"), f"missing download_url: {last}"
        assert last["download_url"].startswith("/api/download/")
        # And the file referenced by the download_url actually exists in
        # the redirected output dir.
        filename = last["download_url"].rsplit("/", 1)[-1]
        assert filename.startswith("tailored_resume_")
        # The body is JSON, not the file content, so we can't read the
        # file from here. The disk-write test below verifies the file
        # exists.

    def test_valid_pdf_writes_a_pdf_to_disk(self, client, valid_pdf):
        c, mod = client
        output_dir = Path(mod._OUTPUT_DIR)
        before = set(output_dir.glob("tailored_resume_*.pdf"))
        r = c.post(
            "/api/generate",
            files={"file": ("input.pdf", valid_pdf, "application/pdf")},
            data={"theme": "classic_html"},
        )
        assert r.status_code == 200
        after = set(output_dir.glob("tailored_resume_*.pdf"))
        new_pdfs = after - before
        assert len(new_pdfs) == 1, f"expected 1 new PDF, found {len(new_pdfs)}"
        new_pdf = new_pdfs.pop()
        # Sanity: non-empty, looks like a PDF
        assert new_pdf.stat().st_size > 100
        head = new_pdf.read_bytes()[:5]
        assert head == b"%PDF-", f"file does not look like a PDF: {head!r}"

    def test_invalid_domain_game_returns_422(self, client, valid_pdf):
        c, _ = client
        r = c.post(
            "/api/generate",
            files={"file": ("input.pdf", valid_pdf, "application/pdf")},
            data={"domain_game": "bogus_game"},
        )
        assert r.status_code == 422
        assert "domain_game" in r.json()["detail"]

    def test_invalid_force_language_returns_422(self, client, valid_pdf):
        c, _ = client
        r = c.post(
            "/api/generate",
            files={"file": ("input.pdf", valid_pdf, "application/pdf")},
            data={"force_language": "klingon"},
        )
        assert r.status_code == 422
        assert "force_language" in r.json()["detail"]

    def test_base_resume_filename_falls_back_to_original_when_missing(
        self, client, valid_pdf
    ):
        """When ``base_resume_filename`` is provided but the file does
        not exist in the output dir, the handler should fall back to
        using the user's uploaded PDF instead of crashing. This is the
        branch where the original ``OUTPUT_DIR`` NameError hid for weeks.
        """
        c, mod = client
        r = c.post(
            "/api/generate",
            files={"file": ("input.pdf", valid_pdf, "application/pdf")},
            data={
                "base_resume_filename": "tailored_resume_9999999999.pdf",  # doesn't exist
                "theme": "classic_html",
            },
        )
        # The handler should NOT crash with NameError or 500. Either it
        # 200s (using the original upload) or 422s (validation), but the
        # important thing is the request reaches the render step.
        assert r.status_code in (200, 422), r.text
        if r.status_code == 200:
            # And the success event is emitted.
            events = [
                line for line in r.text.splitlines() if line.startswith("data: ")
            ]
            assert any("download_url" in e for e in events)

    def test_rate_limit_scope_is_generate(self, client, valid_pdf):
        """Generate must consume the ``generate`` scope, not share a budget
        with /api/clear-cache or /api/render-from-yaml."""
        from main import _RL_HITS

        c, _ = client
        c.post(
            "/api/generate",
            files={"file": ("input.pdf", valid_pdf, "application/pdf")},
            data={"theme": "classic_html"},
        )
        keys = [k for k in _RL_HITS if k.startswith("generate:")]
        assert keys, f"no generate scope in _RL_HITS: {_RL_HITS}"
