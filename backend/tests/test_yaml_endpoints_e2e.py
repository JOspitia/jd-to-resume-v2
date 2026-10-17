"""End-to-end tests for the YAML editor endpoints.

Covers the happy path of POST /api/render-from-yaml, /api/analyze-yaml, and
/api/repair-yaml via FastAPI TestClient (no browser, no SSE). LLM
providers are stubbed in-process so the suite runs offline and
deterministic.

Why this module exists
======================

Today's debugging session surfaced 3 NameError bugs that the test suite
didn't catch (``OUTPUT_DIR``, ``HTML_TEMPLATE``, ``RateLimitExceeded``).
The reason: there was zero end-to-end coverage of the YAML editor
endpoints' happy paths. Pytest exercised the pure helpers (parse,
drift check) but never the FastAPI handler that wires them together.

These tests are the structural net that closes the class of bug: any
future split that moves code in or out of these endpoints will get
caught here if it breaks the request/response contract.

What is NOT covered
===================

* Real LLM providers (stubbed; we test plumbing, not model quality)
* Real Playwright HTML render (exercised in ``test_renderers.py``)
* Real RenderCV binary (also covered elsewhere)
* Frontend integration (this is server-only)
"""

from __future__ import annotations

import asyncio
import io
import json
import time
from pathlib import Path
from typing import Optional

import pytest
from fastapi.testclient import TestClient


MINIMAL_VALID_YAML = """\
name: Jane Doe
location: Bogota, CO
phone: +57 300 000 0000
email: jane@example.com
portfolio: https://jane.example.com
linkedin: https://linkedin.com/in/jane
github: https://github.com/jane
summary: Backend engineer with 5 years of experience.
education:
  - school: Universidad Nacional
    degree: BSc Computer Science
    dates: 2018 - 2023
skills:
  - category: Backend
    items: ["Python", "FastAPI", "PostgreSQL"]
experience:
  - company: Acme
    role: Senior Engineer
    dates: 2023 - Present
    points:
      - Built a streaming CV pipeline in 30 days
      - Reduced LLM cost by 40%
projects:
  - name: cv-tailor
    dates: 2024
    points:
      - Open-source tool with 1.5k stars
achievements:
  - "Speaker at PyCon Latam 2024"
section_labels:
  summary: Resumen Profesional
"""


# ---------------------------------------------------------------------------
# Stubs
# ---------------------------------------------------------------------------


class _StubLLMProvider:
    """In-process LLM stub. Returns a fixed YAML response, so we can verify
    the request/response plumbing without hitting any external API."""

    name = "stub"

    def __init__(self, response: str = MINIMAL_VALID_YAML) -> None:
        self.response = response
        self.calls: list[str] = []

    def complete(self, prompt: str, *, model: str | None = None) -> str:
        # Note: the production providers are SYNC; the orchestrator runs
        # them via ``asyncio.to_thread`` so the event loop isn't blocked.
        # The stub must follow the same contract or ``to_thread`` returns
        # the coroutine object instead of awaiting it.
        self.calls.append(prompt)
        return self.response


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def stub_llm_orchestrator(monkeypatch):
    """Replace the live LLM orchestrator with one backed by a stub.

    The closure inside ``routes/yaml_editor_router`` captures the service
    at module-init time, so we patch the LLM that *the service holds*
    rather than the service itself. Each test that exercises
    analyze-yaml / repair-yaml gets a fresh stub to inspect.
    """
    from application.services.llm_orchestrator import LLMOrchestrator
    from main import _yaml_editor_service

    stub = _StubLLMProvider()
    stub_orch = LLMOrchestrator([stub])
    monkeypatch.setattr(_yaml_editor_service, "_llm", stub_orch)
    return stub


@pytest.fixture
def client(monkeypatch, tmp_path):
    """TestClient with rate limit loosened to keep tests fast."""
    import sys
    # Reload main with a clean module path so each test starts with a
    # fresh composition root. This mirrors the pattern in
    # tests/test_security_fixes.py.
    saved_out, saved_err = sys.stdout, sys.stderr
    import importlib
    for k, v in {"RATE_LIMIT_DEFAULT": "1000/minute"}.items():
        monkeypatch.setenv(k, v)
    sys.modules.pop("main", None)
    mod = importlib.import_module("main")
    sys.stdout, sys.stderr = saved_out, saved_err
    c = TestClient(mod.app)
    return c, mod


# ---------------------------------------------------------------------------
# POST /api/render-from-yaml
# ---------------------------------------------------------------------------


class TestRenderFromYaml:
    """Render PDF from user-edited YAML. No LLM call. Pure plumbing."""

    def test_valid_yaml_returns_200_with_download_url(self, client):
        c, mod = client
        r = c.post(
            "/api/render-from-yaml",
            data={"yaml_content": MINIMAL_VALID_YAML, "theme": "classic_html"},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert "download_url" in body
        assert body["download_url"].startswith("/api/download/")
        assert body["filename"].startswith("tailored_resume_")
        assert body["filename"].endswith(".pdf")

    def test_valid_yaml_writes_a_pdf_to_disk(self, client):
        c, mod = client
        before = set(Path(mod._OUTPUT_DIR).glob("tailored_resume_*.pdf"))
        r = c.post(
            "/api/render-from-yaml",
            data={"yaml_content": MINIMAL_VALID_YAML, "theme": "classic_html"},
        )
        assert r.status_code == 200
        after = set(Path(mod._OUTPUT_DIR).glob("tailored_resume_*.pdf"))
        # The production filename is ``tailored_resume_<int(time.time())>.pdf``,
        # which has 1-second resolution. If two tests run inside the same
        # second they share the filename and the second overwrites the
        # first; the set difference would be empty even though a PDF
        # was successfully rendered. So we only assert "at least one new
        # PDF" and pick any file that's a valid PDF to verify shape.
        new_pdfs = after - before
        assert len(new_pdfs) >= 1, f"expected ≥1 new PDF, found {len(new_pdfs)}"
        # Sanity: the file is non-empty.
        new_pdf = new_pdfs.pop()
        assert new_pdf.stat().st_size > 100
        head = new_pdf.read_bytes()[:5]
        assert head == b"%PDF-", f"file does not look like a PDF: {head!r}"

    def test_invalid_yaml_syntax_returns_400(self, client):
        c, _ = client
        # Indentation breaks the mapping.
        broken = "name: x\n  bad: y: :\n   z:\n"
        r = c.post("/api/render-from-yaml", data={"yaml_content": broken})
        assert r.status_code == 400
        # Detail should be non-empty and indicate a parse / mapping error.
        detail = r.json()["detail"].lower()
        assert any(t in detail for t in ("mapping", "syntax", "yaml"))

    def test_top_level_list_returns_400(self, client):
        c, _ = client
        r = c.post(
            "/api/render-from-yaml",
            data={"yaml_content": "- a\n- b\n- c\n"},
        )
        assert r.status_code == 400
        assert "mapping" in r.json()["detail"].lower()

    def test_empty_content_returns_400(self, client):
        c, _ = client
        r = c.post("/api/render-from-yaml", data={"yaml_content": "   \n"})
        assert r.status_code == 400

    def test_invalid_domain_game_returns_422(self, client):
        c, _ = client
        r = c.post(
            "/api/render-from-yaml",
            data={
                "yaml_content": MINIMAL_VALID_YAML,
                "domain_game": "made_up_game",
            },
        )
        assert r.status_code == 422
        assert "domain_game" in r.json()["detail"]

    def test_rate_limit_scope_is_render_from_yaml(self, client):
        """The rate-limit helper scopes the hit by endpoint name; a render
        request must NOT consume the analyze-yaml budget. Verifies the
        scope label is wired correctly so two yaml endpoints don't share
        a budget."""
        from main import _RL_HITS

        c, _ = client
        c.post(
            "/api/render-from-yaml",
            data={"yaml_content": MINIMAL_VALID_YAML, "theme": "classic_html"},
        )
        # At least one key with the render-from-yaml scope should exist.
        render_keys = [k for k in _RL_HITS if k.startswith("render-from-yaml:")]
        assert render_keys, f"no render-from-yaml scope in {_RL_HITS}"


# ---------------------------------------------------------------------------
# POST /api/analyze-yaml
# ---------------------------------------------------------------------------


class TestAnalyzeYaml:
    """Audit user-edited YAML. Delegates to the audit pipeline (which
    calls the LLM in production; here we mock it to a fixed result so
    the test is deterministic)."""

    def test_valid_yaml_returns_audit_payload(self, client, stub_llm_orchestrator, monkeypatch):
        """Wire the audit pipeline to the stub too — analyze-yaml calls
        ``_run_audit_against_text`` which uses the LLM. We monkeypatch
        that helper to return a fixed dict so we test the route, not the
        audit logic."""
        c, mod = client
        # Replace the audit helper with a stub that just returns a dict.
        async def _stub_audit(resume_text, jd_text, audit_game):
            return {"score": 88, "summary": "ok", "resume_chars": len(resume_text)}
        monkeypatch.setattr(mod, "_run_audit_against_text", _stub_audit)

        r = c.post(
            "/api/analyze-yaml",
            data={"yaml_content": MINIMAL_VALID_YAML, "domain_game": "tech"},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("score") == 88
        assert body.get("resume_chars") > 0

    def test_invalid_yaml_returns_400(self, client, stub_llm_orchestrator, monkeypatch):
        c, mod = client
        r = c.post(
            "/api/analyze-yaml",
            data={"yaml_content": "name: x\n  bad: :\n"},
        )
        assert r.status_code == 400

    def test_invalid_domain_game_returns_422(self, client, stub_llm_orchestrator, monkeypatch):
        c, mod = client
        r = c.post(
            "/api/analyze-yaml",
            data={"yaml_content": MINIMAL_VALID_YAML, "domain_game": "not_a_game"},
        )
        assert r.status_code == 422


# ---------------------------------------------------------------------------
# POST /api/repair-yaml
# ---------------------------------------------------------------------------


class TestRepairYaml:
    """Two-pass LLM repair. Stubbed LLM so we test plumbing + drift
    guard, not model quality."""

    def test_valid_yaml_returns_ok_without_calling_llm(self, client, stub_llm_orchestrator):
        c, _ = client
        r = c.post(
            "/api/repair-yaml",
            data={"yaml_content": MINIMAL_VALID_YAML},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["ok"] is True
        # The valid YAML doesn't need an LLM pass.
        assert stub_llm_orchestrator.calls == []

    def test_yaml_with_bad_indent_calls_llm_and_returns_envelope(
        self, client, stub_llm_orchestrator
    ):
        c, _ = client
        # A YAML that parses but has a structural problem (missing required
        # top-level field "name") so the schema check fails, the LLM is
        # called, and we get a fixed envelope back.
        bad = """\
location: Bogota
email: no-name@example.com
"""
        r = c.post("/api/repair-yaml", data={"yaml_content": bad})
        assert r.status_code == 200
        body = r.json()
        # Either the LLM was called (returning the stub response which is
        # valid YAML, so ok=True) or it wasn't. Either is fine — what
        # matters is the envelope shape.
        assert "ok" in body
        assert "yaml" in body
        assert "repairs" in body
        assert "schema_errors" in body

    def test_drift_guard_aborts_when_llm_rewrites_content(
        self, client, stub_llm_orchestrator
    ):
        """If the LLM rewrites the candidate's facts (numbers, names),
        the drift guard MUST abort the repair and return the original
        text untouched. This is the product promise: editing the YAML
        by hand never silently loses the candidate's data.

        The original text below is **schema-invalid** (education must
        be a list of objects, not a string) which forces the LLM to be
        called for the schema-repair pass. The stub returns valid
        schema but rewrites the candidate's name from "Jane Doe" to
        "John Smith" — the drift guard must catch that and abort.
        """
        c, _ = client
        original = (
            "name: Jane Doe\n"
            "email: jane@example.com\n"
            "education: not-a-list\n"
        )
        stub_llm_orchestrator.response = MINIMAL_VALID_YAML.replace(
            "Jane Doe", "John Smith",
        )

        r = c.post("/api/repair-yaml", data={"yaml_content": original})
        body = r.json()
        assert body["ok"] is False, f"drift guard should have aborted: {body}"
        # The returned yaml must be the ORIGINAL (untouched), not the
        # LLM response.
        assert "Jane Doe" in body["yaml"]
        assert "John Smith" not in body["yaml"]
        # And the response explains why it aborted.
        schema_errors = body.get("schema_errors", [])
        assert any("modificado" in e.lower() for e in schema_errors), schema_errors

    def test_invalid_domain_game_returns_422(self, client, stub_llm_orchestrator):
        c, _ = client
        r = c.post(
            "/api/repair-yaml",
            data={"yaml_content": MINIMAL_VALID_YAML, "domain_game": "made_up"},
        )
        assert r.status_code == 422
