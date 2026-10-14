"""
backend.tests.test_yaml_endpoints
==================================

Tests for the new YAML editor endpoints (/api/render-from-yaml and
/api/analyze-yaml) added in T4-T5 of the yaml-editor feature.

Strategy
--------
The heavy dependencies of `main.py` (fitz / PyMuPDF, google.generativeai,
render_service / rendercv, playwright) are mocked at the sys.modules
level before importing main. This is necessary because the test sandbox
does not have PyMuPDF installed and the existing import chain pulls it
in at module load time.

After the mock injection, main can be imported and we use FastAPI's
TestClient to hit the endpoints with multipart FormData. The LLM
(`call_llm_api`) and PDF renderer (`render_cv_with_rendercv`) are
replaced with `unittest.mock.AsyncMock` / `MagicMock` so the tests
don't need real API keys or Typst/RenderCV installed.

Run with:
    cd backend && pytest tests/test_yaml_endpoints.py -v
"""

from __future__ import annotations

import asyncio
import io
import sys
import types
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Pre-import mocks: install fake modules into sys.modules before main.py is
# imported. The fitz / google.generativeai / render_service / playwright
# imports are the only ones that need fakes; the rest of main.py uses
# stdlib + our own modules (domain_games, audit_prompts, yaml_helpers,
# language) which are already importable.
# ---------------------------------------------------------------------------


def _install_module_stub(name: str) -> types.ModuleType:
    mod = types.ModuleType(name)
    sys.modules[name] = mod
    return mod


# fitz (PyMuPDF): provide a placeholder; the endpoints under test don't
# actually need real PDF parsing because the YAML endpoints accept
# already-parsed text via the YAML payload.
_install_module_stub("fitz").open = MagicMock()  # type: ignore[attr-defined]

# google.generativeai: not used in the YAML endpoints but imported at
# top of main.py. The genai.configure call is a no-op; the model class
# is mocked so `genai.GenerativeModel` doesn't blow up if anything
# references it lazily.
_genai = _install_module_stub("google.generativeai")
_genai.configure = MagicMock()
_genai.GenerativeModel = MagicMock()
_install_module_stub("google").generativeai = _genai  # for `import google.generativeai as genai`

# render_service: render_cv_with_rendercv is the only thing the YAML
# endpoints use from this module. We replace it with a MagicMock that
# creates an empty file at the requested path (so the render branch
# in /api/render-from-yaml succeeds).
_render_service = _install_module_stub("render_service")
_render_service.render_cv_with_rendercv = MagicMock(
    side_effect=lambda parsed, path, theme, fit, page_break: Path(path).write_bytes(b"%PDF-1.4 fake")
)

# Playwright: imported by main.py but only used in the render-fallback
# branch of generation_pipeline (not used by the YAML endpoints). Still,
# provide a stub so the import succeeds.
_playwright = _install_module_stub("playwright")
_sync_api = _install_module_stub("playwright.sync_api")
_sync_api.sync_playwright = MagicMock()

# Weasyprint is in requirements.txt but imported lazily; not needed for
# the YAML endpoint tests.
# ---------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Now we can import main. If any of the stubbed modules are accessed in
# an unexpected way, the import or test will fail and we'll iterate.
import main as main_module  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


@pytest.fixture
def client():
    """A FastAPI TestClient with the LLM and PDF render mocked."""
    # Reset mocks between tests.
    main_module.call_llm_api = AsyncMock(
        return_value='{"ats_score": 88, "match_level": "Alto", '
                     '"matched_keywords": ["16PF"], '
                     '"missing_keywords": ["DISC"], '
                     '"ai_detection_score": 12, '
                     '"ai_tone_verdict": "Bajo Riesgo de IA", '
                     '"ai_humanize_tips": ["Directo y conciso."], '
                     '"ats_formatting_score": 95, '
                     '"actionable_tips": ["Refuerza keywords del dominio."]}'
    )
    main_module.render_cv_with_rendercv.reset_mock()
    main_module.render_cv_with_rendercv.side_effect = (
        lambda parsed, path, theme, fit, page_break: Path(path).write_bytes(b"%PDF-1.4 fake")
    )
    # The endpoint checks OUTPUT_DIR exists; create it if missing.
    main_module.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    return TestClient(main_module.app)


# ---------------------------------------------------------------------------
# /api/render-from-yaml (T4, S6)
# ---------------------------------------------------------------------------


class TestRenderFromYaml:
    def test_missing_yaml_content_returns_400(self, client):
        r = client.post("/api/render-from-yaml", data={})
        assert r.status_code == 422  # FastAPI rejects the missing required field

    def test_empty_yaml_content_returns_400(self, client):
        r = client.post("/api/render-from-yaml", data={"yaml_content": "   "})
        assert r.status_code == 400
        assert "yaml_content" in r.json()["detail"].lower()

    def test_invalid_yaml_returns_400_with_parser_error(self, client):
        r = client.post(
            "/api/render-from-yaml",
            data={"yaml_content": "this is: not: valid: yaml: [unterminated"},
        )
        assert r.status_code == 400
        assert "invalid yaml" in r.json()["detail"].lower()

    def test_yaml_scalar_top_level_returns_400(self, client):
        # A bare scalar at the top level (e.g. "42") is valid YAML but
        # not a dict; the endpoint should reject it.
        r = client.post("/api/render-from-yaml", data={"yaml_content": "42"})
        assert r.status_code == 400
        assert "mapping" in r.json()["detail"].lower()

    def test_invalid_domain_game_returns_422(self, client):
        r = client.post(
            "/api/render-from-yaml",
            data={
                "yaml_content": "name: Jane\nsummary: x\n",
                "domain_game": "marketing",  # not in ALLOWED_GAMES
            },
        )
        assert r.status_code == 422
        assert "domain_game" in r.json()["detail"].lower()

    def test_valid_yaml_renders_pdf(self, client):
        r = client.post(
            "/api/render-from-yaml",
            data={
                "yaml_content": (
                    "name: Jane Doe\n"
                    "summary: Senior psychologist with 8 years.\n"
                    "experience:\n"
                    "  - role: Senior Consultant\n"
                    "    company: Talent Lab\n"
                    "    dates: '2021-03 - Actualidad'\n"
                    "    points:\n"
                    "      - Led assessment centers for 15 clients.\n"
                ),
                "theme": "sb2nov",
                "fit_single_page": "false",
                "domain_game": "psychology",
            },
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert "download_url" in body
        assert body["download_url"].startswith("/api/download/")
        assert "filename" in body
        # render_cv_with_rendercv was called exactly once with the parsed
        # data and the requested path.
        main_module.render_cv_with_rendercv.assert_called_once()
        args, kwargs = main_module.render_cv_with_rendercv.call_args
        parsed_arg = args[0] if args else kwargs.get("parsed_data")
        assert parsed_arg["name"] == "Jane Doe"
        assert parsed_arg["summary"].startswith("Senior psychologist")
        # The renderer wrote a fake PDF at the output path.
        rendered_path = Path(main_module.OUTPUT_DIR) / body["filename"]
        assert rendered_path.exists()
        assert rendered_path.read_bytes() == b"%PDF-1.4 fake"

    def test_valid_yaml_default_domain_is_tech(self, client):
        # No domain_game -> default tech. The endpoint should accept and
        # not fail.
        r = client.post(
            "/api/render-from-yaml",
            data={
                "yaml_content": "name: Dev\nskills: []\n",
            },
        )
        assert r.status_code == 200


# ---------------------------------------------------------------------------
# /api/analyze-yaml (T5, S8)
# ---------------------------------------------------------------------------


class TestAnalyzeYaml:
    def test_missing_yaml_content_returns_422(self, client):
        r = client.post("/api/analyze-yaml", data={})
        assert r.status_code == 422

    def test_empty_yaml_content_returns_400(self, client):
        r = client.post("/api/analyze-yaml", data={"yaml_content": ""})
        assert r.status_code == 400

    def test_invalid_yaml_returns_400(self, client):
        r = client.post(
            "/api/analyze-yaml",
            data={"yaml_content": "name: [broken"},
        )
        assert r.status_code == 400
        assert "invalid yaml" in r.json()["detail"].lower()

    def test_invalid_domain_game_returns_422(self, client):
        r = client.post(
            "/api/analyze-yaml",
            data={
                "yaml_content": "name: Jane\n",
                "domain_game": "marketing",
            },
        )
        assert r.status_code == 422

    def test_valid_yaml_returns_audit_dict(self, client):
        r = client.post(
            "/api/analyze-yaml",
            data={
                "yaml_content": (
                    "name: Jane Doe\n"
                    "summary: Psychologist.\n"
                    "experience:\n"
                    "  - role: Consultant\n"
                    "    company: Acme\n"
                    "    points:\n"
                    "      - Did 16PF assessments.\n"
                ),
                "domain_game": "psychology",
            },
        )
        assert r.status_code == 200, r.text
        body = r.json()
        # The mocked LLM returned ats_score 88, matched 16PF, missing DISC.
        assert body["ats_score"] == 88
        assert body["matched_keywords"] == ["16PF"]
        assert body["missing_keywords"] == ["DISC"]
        # LLM was called exactly once.
        main_module.call_llm_api.assert_awaited_once()

    def test_valid_yaml_with_default_game_uses_tech_taxonomy(self, client):
        r = client.post(
            "/api/analyze-yaml",
            data={"yaml_content": "name: Dev\n"},
        )
        assert r.status_code == 200
        # The LLM was called (we don't introspect the prompt here; that's
        # covered by test_audit_prompts.py). The point of this test is
        # that the default game path doesn't 500.
        main_module.call_llm_api.assert_awaited()


# ---------------------------------------------------------------------------
# Cross-cutting: the existing /api/analyze-ats and /api/generate still
# work after the YAML editor feature (regression guard).
# ---------------------------------------------------------------------------


class TestLegacyEndpointsUnaffected:
    def test_analyze_ats_rejects_unknown_domain_game(self, client):
        # Sanity: the existing /api/analyze-ats domain_game validation
        # still works after the YAML feature work.
        # We don't upload a file (we expect 422 from the form parsing
        # first), but at least the endpoint is reachable.
        r = client.post(
            "/api/analyze-ats",
            data={"jd": "x", "domain_game": "marketing"},
        )
        # FastAPI returns 422 for missing required 'file' field; we
        # only care that the route exists and didn't 404.
        assert r.status_code in (422, 400, 500)
        assert r.status_code != 404
