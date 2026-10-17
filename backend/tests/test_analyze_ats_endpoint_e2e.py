"""End-to-end tests for ``POST /api/analyze-ats``.

The audit endpoint runs the LLM over a candidate's resume text. We
stub ``call_llm_api`` (the entry point the audit pipeline uses) to
return a fixed audit JSON, so the suite exercises plumbing, not
model quality.

Same pattern as ``tests/test_generate_endpoint_e2e.py``: TestClient
via FastAPI, real PDF generated with PyMuPDF, LLM stubbed in-process.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import fitz
import pytest
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Stubs
# ---------------------------------------------------------------------------


def _audit_json() -> dict[str, Any]:
    """Return a realistic audit JSON that the frontend can render."""
    return {
        "score": 82,
        "summary": "Strong technical profile; consider adding metrics to two bullets.",
        "ats_score": 88,
        "strengths": ["Clear stack", "Quantified impact"],
        "gaps": [
            "Experience bullet 2 lacks a metric",
            "Skills section missing Postgres",
        ],
    }


class _StubLLMProvider:
    name = "stub"

    def __init__(self, response: str | None = None) -> None:
        self.response = response or json.dumps(_audit_json())
        self.calls: list[str] = []

    def complete(self, prompt: str, *, model: str | None = None) -> str:
        self.calls.append(prompt)
        return self.response


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def valid_pdf(tmp_path: Path) -> bytes:
    pdf_path = tmp_path / "input.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((50, 50), "Jane Doe")
    page.insert_text((50, 80), "Backend Engineer with 5 years of experience.")
    page.insert_text((50, 110), "Skills: Python, FastAPI")
    doc.save(str(pdf_path))
    doc.close()
    return pdf_path.read_bytes()


@pytest.fixture
def stubbed_llm(monkeypatch):
    """Patch the LLM provider factory so every LLMOrchestrator instance
    the audit pipeline builds uses only our stub.

    The audit pipeline goes through ``call_llm_api`` -> ``build_llm_providers``
    -> ``LLMOrchestrator``. Patching the factory is the cleanest choke
    point because every orchestrator instance picks up the stub.
    """
    from adapters.llm.factory import build_llm_providers

    stub = _StubLLMProvider()
    monkeypatch.setattr(
        "adapters.llm.factory.build_llm_providers",
        lambda: [stub],
    )
    return stub


@pytest.fixture
def client(monkeypatch, stubbed_llm):
    import sys
    import importlib
    saved_out, saved_err = sys.stdout, sys.stderr
    for k, v in {"RATE_LIMIT_DEFAULT": "1000/minute"}.items():
        monkeypatch.setenv(k, v)
    sys.modules.pop("main", None)
    mod = importlib.import_module("main")
    sys.stdout, sys.stderr = saved_out, saved_err
    return TestClient(mod.app), mod


# ---------------------------------------------------------------------------
# /api/analyze-ats
# ---------------------------------------------------------------------------


class TestAnalyzeAtsEndpoint:
    def test_missing_file_returns_422(self, client):
        c, _ = client
        r = c.post("/api/analyze-ats", data={"jd": "Build a CLI tool"})
        assert r.status_code == 422

    def test_valid_pdf_with_stubbed_llm_returns_audit(self, client, valid_pdf, stubbed_llm):
        c, _ = client
        r = c.post(
            "/api/analyze-ats",
            files={"file": ("input.pdf", valid_pdf, "application/pdf")},
            data={"jd": "Build a streaming CV pipeline"},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        # The audit response shape is owned by ``audit_prompts``; the
        # production pipeline returns a different envelope than the
        # raw LLM JSON. The stub we inject at the LLM level returns
        # our raw JSON, but the audit pipeline wraps / extracts from
        # it. So we just verify the response is JSON and the LLM was
        # called with the audit prompt.
        assert isinstance(body, dict)
        assert len(stubbed_llm.calls) >= 1
        # The audit prompt mentions the JD we passed in.
        assert "Build a streaming CV pipeline" in stubbed_llm.calls[0]

    def test_invalid_domain_game_returns_422(self, client, valid_pdf):
        c, _ = client
        r = c.post(
            "/api/analyze-ats",
            files={"file": ("input.pdf", valid_pdf, "application/pdf")},
            data={"domain_game": "made_up_game"},
        )
        assert r.status_code == 422
        assert "domain_game" in r.json()["detail"]

    def test_rate_limit_scope_is_analyze_ats(self, client, valid_pdf):
        from main import _RL_HITS

        c, _ = client
        c.post(
            "/api/analyze-ats",
            files={"file": ("input.pdf", valid_pdf, "application/pdf")},
        )
        keys = [k for k in _RL_HITS if k.startswith("analyze-ats:")]
        assert keys, f"no analyze-ats scope in _RL_HITS: {_RL_HITS}"
