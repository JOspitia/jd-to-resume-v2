"""
backend.tests.test_cover_letter
================================

Tests for the cover-letter deliverable (``POST /api/cover-letter``).

Two levels:

* **Unit** — the prompt builder and the service's response normalisation.
  The service is the piece with the interesting failure modes: the model
  answers in markdown fences, in a list, under a ``{"letter": ...}``
  envelope, or with the body collapsed into a single string. All of those
  shapes must land on the same contract.

* **Endpoint** — the FastAPI route with a stubbed LLM provider, following
  the same pattern as ``tests/test_analyze_ats_endpoint_e2e.py``: a real
  PDF built with PyMuPDF, the LLM factory patched so no network call
  happens, and the route contract (422 on bad input, 200 with the
  documented body) asserted from the outside.

Run with:
    cd backend && pytest tests/test_cover_letter.py -v
"""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path
from typing import Any

import pymupdf
import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from application.services.cover_letter_service import CoverLetterService  # noqa: E402
from domain.cover_letter_prompts import build_cover_letter_prompt  # noqa: E402
from domain_games import get_game  # noqa: E402


RESUME_TEXT = "Jane Doe. Backend Engineer. 5 years. Python, FastAPI, Docker."
JD_TEXT = "Buscamos un ingeniero backend con experiencia en APIs y Docker."


# ---------------------------------------------------------------------------
# Fixtures / stubs
# ---------------------------------------------------------------------------


def _letter_payload() -> dict[str, Any]:
    return {
        "salutation": "Estimado equipo de Talento Humano:",
        "opening": "Vi la vacante de backend y el stack encaja con lo que vengo haciendo.",
        "body": [
            "En los últimos cinco años construí APIs en FastAPI que atienden el tráfico de producción.",
            "Automaticé el despliegue con Docker y reduje el tiempo de puesta en marcha del equipo.",
        ],
        "closing": "Puedo iniciar de inmediato y quedo atento para ampliar en una entrevista.",
        "signature": "Jane Doe\n+57 300 000 0000\njane@example.com",
    }


class _StubProvider:
    """Minimal LLM provider stub (the orchestrator calls it in a thread)."""

    name = "stub"

    def __init__(self, response: str | None = None) -> None:
        self.response = response if response is not None else json.dumps(_letter_payload())
        self.calls: list[str] = []

    def complete(self, prompt: str, *, model: str | None = None) -> str:
        self.calls.append(prompt)
        return self.response


class _StubLLM:
    """Stub for the orchestrator itself (used by the unit tests)."""

    def __init__(self, response: str | None = None) -> None:
        self.provider = _StubProvider(response)
        self.prompts: list[str] = []

    async def complete(self, prompt: str, *, model: str | None = None) -> str:
        self.prompts.append(prompt)
        return self.provider.complete(prompt, model=model)


@pytest.fixture
def valid_pdf(tmp_path: Path) -> bytes:
    pdf_path = tmp_path / "input.pdf"
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((50, 50), "Jane Doe")
    page.insert_text((50, 80), "Backend Engineer with 5 years of experience.")
    page.insert_text((50, 110), "Skills: Python, FastAPI")
    doc.save(str(pdf_path))
    doc.close()
    return pdf_path.read_bytes()


@pytest.fixture
def stubbed_llm(monkeypatch):
    from adapters.llm.factory import build_llm_providers

    stub = _StubProvider()
    monkeypatch.setattr("adapters.llm.factory.build_llm_providers", lambda: [stub])
    return stub


@pytest.fixture
def client(monkeypatch, stubbed_llm):
    saved_out, saved_err = sys.stdout, sys.stderr
    monkeypatch.setenv("RATE_LIMIT_DEFAULT", "1000/minute")
    sys.modules.pop("main", None)
    mod = importlib.import_module("main")
    sys.stdout, sys.stderr = saved_out, saved_err
    return TestClient(mod.app), mod


# ---------------------------------------------------------------------------
# Prompt builder
# ---------------------------------------------------------------------------


class TestCoverLetterPrompt:
    def test_prompt_carries_the_inputs(self):
        prompt = build_cover_letter_prompt(
            RESUME_TEXT,
            JD_TEXT,
            get_game("tech"),
            target_role="Backend Engineer",
            company_name="Acme",
        )
        assert RESUME_TEXT in prompt
        assert JD_TEXT in prompt
        assert "Backend Engineer" in prompt
        assert "Acme" in prompt

    def test_prompt_carries_the_domain_taxonomy_and_angle(self):
        prompt = build_cover_letter_prompt(
            RESUME_TEXT, JD_TEXT, get_game("general")
        )
        # The vocabulary comes from the game file, so it stays in sync.
        assert "Atención al Cliente & Ventas" in prompt
        # The angle is the per-domain paragraph.
        assert "service and commercial letter" in prompt

    def test_each_domain_has_its_own_angle(self):
        tech = build_cover_letter_prompt(RESUME_TEXT, JD_TEXT, get_game("tech"))
        psych = build_cover_letter_prompt(RESUME_TEXT, JD_TEXT, get_game("psychology"))
        hr = build_cover_letter_prompt(RESUME_TEXT, JD_TEXT, get_game("hr_recruiting"))
        assert "technical letter" in tech
        assert "clinical and ethical letter" in psych
        assert "people-process letter" in hr

    def test_tone_and_length_reach_the_prompt(self):
        prompt = build_cover_letter_prompt(
            RESUME_TEXT,
            JD_TEXT,
            get_game("tech"),
            tone="concise",
            length="short",
        )
        assert "120-180 words" in prompt
        assert "shortest acceptable" in prompt.lower()

    def test_unknown_tone_and_length_fall_back_to_the_defaults(self):
        prompt = build_cover_letter_prompt(
            RESUME_TEXT, JD_TEXT, get_game("tech"), tone="shouty", length="epic"
        )
        assert "220-320 words" in prompt
        assert "Corporate but human" in prompt

    def test_language_override_wins_over_the_jd_language(self):
        prompt = build_cover_letter_prompt(
            RESUME_TEXT, JD_TEXT, get_game("tech"), language="en"
        )
        assert "LANGUAGE OVERRIDE (ABSOLUTE PRIORITY)" in prompt
        assert "English" in prompt

    def test_auto_language_follows_the_job_description(self):
        prompt = build_cover_letter_prompt(
            RESUME_TEXT, JD_TEXT, get_game("tech"), language="auto"
        )
        assert "Detect the dominant language of the job description" in prompt

    def test_prompt_forbids_inventing_and_empty_adjectives(self):
        prompt = build_cover_letter_prompt(RESUME_TEXT, JD_TEXT, get_game("tech"))
        assert "ZERO HALLUCINATION" in prompt
        assert "persona dinámica y proactiva" in prompt
        assert "no meta-commentary" in prompt.lower()

    def test_custom_instructions_are_included(self):
        prompt = build_cover_letter_prompt(
            RESUME_TEXT,
            JD_TEXT,
            get_game("tech"),
            custom_instructions="Menciona que vivo en Bogotá.",
        )
        assert "Menciona que vivo en Bogotá." in prompt
        assert "ADDITIONAL REQUIREMENTS FROM THE USER" in prompt


# ---------------------------------------------------------------------------
# Service — response normalisation
# ---------------------------------------------------------------------------


class TestCoverLetterService:
    @pytest.mark.asyncio
    async def test_returns_the_documented_contract(self):
        svc = CoverLetterService(_StubLLM())
        out = await svc.generate_text(RESUME_TEXT, JD_TEXT, get_game("tech"))

        for key in (
            "salutation",
            "opening",
            "body",
            "closing",
            "signature",
            "plain_text",
            "contact",
            "meta",
        ):
            assert key in out, key

        assert isinstance(out["body"], list)
        assert len(out["body"]) == 2
        assert out["meta"]["domain_game"] == "tech"
        assert out["meta"]["word_count"] > 0

    @pytest.mark.asyncio
    async def test_plain_text_joins_the_blocks_in_reading_order(self):
        svc = CoverLetterService(_StubLLM())
        out = await svc.generate_text(RESUME_TEXT, JD_TEXT, get_game("tech"))
        text = out["plain_text"]
        assert text.index(out["salutation"]) < text.index(out["opening"])
        assert text.index(out["opening"]) < text.index(out["body"][0])
        assert text.index(out["body"][0]) < text.index(out["body"][1])
        assert text.index(out["body"][1]) < text.index(out["closing"])
        assert text.index(out["closing"]) < text.index(out["signature"])

    @pytest.mark.asyncio
    async def test_tolerates_markdown_fences(self):
        raw = "```json\n" + json.dumps(_letter_payload()) + "\n```"
        out = await CoverLetterService(_StubLLM(raw)).generate_text(
            RESUME_TEXT, JD_TEXT, get_game("tech")
        )
        assert len(out["body"]) == 2

    @pytest.mark.asyncio
    async def test_tolerates_a_list_wrapper(self):
        raw = json.dumps([_letter_payload()])
        out = await CoverLetterService(_StubLLM(raw)).generate_text(
            RESUME_TEXT, JD_TEXT, get_game("tech")
        )
        assert len(out["body"]) == 2

    @pytest.mark.asyncio
    async def test_tolerates_a_letter_envelope(self):
        raw = json.dumps({"letter": _letter_payload()})
        out = await CoverLetterService(_StubLLM(raw)).generate_text(
            RESUME_TEXT, JD_TEXT, get_game("tech")
        )
        assert len(out["body"]) == 2

    @pytest.mark.asyncio
    async def test_body_as_a_single_string_becomes_paragraphs(self):
        payload = _letter_payload()
        payload["body"] = "Primer parrafo.\n\nSegundo parrafo."
        out = await CoverLetterService(_StubLLM(json.dumps(payload))).generate_text(
            RESUME_TEXT, JD_TEXT, get_game("tech")
        )
        assert len(out["body"]) == 2

    @pytest.mark.asyncio
    async def test_missing_field_raises(self):
        payload = _letter_payload()
        del payload["closing"]
        with pytest.raises(ValueError, match="incompleta"):
            await CoverLetterService(_StubLLM(json.dumps(payload))).generate_text(
                RESUME_TEXT, JD_TEXT, get_game("tech")
            )

    @pytest.mark.asyncio
    async def test_empty_body_raises(self):
        payload = _letter_payload()
        payload["body"] = []
        with pytest.raises(ValueError):
            await CoverLetterService(_StubLLM(json.dumps(payload))).generate_text(
                RESUME_TEXT, JD_TEXT, get_game("tech")
            )

    @pytest.mark.asyncio
    async def test_non_json_answer_raises(self):
        with pytest.raises(ValueError):
            await CoverLetterService(_StubLLM("lo siento, no puedo")).generate_text(
                RESUME_TEXT, JD_TEXT, get_game("tech")
            )


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------


class TestCoverLetterEndpoint:
    def test_missing_file_returns_422(self, client):
        c, _ = client
        r = c.post("/api/cover-letter", data={"jd": JD_TEXT})
        assert r.status_code == 422

    def test_valid_pdf_returns_the_letter(self, client, valid_pdf):
        c, _ = client
        r = c.post(
            "/api/cover-letter",
            files={"file": ("input.pdf", valid_pdf, "application/pdf")},
            data={
                "jd": JD_TEXT,
                "domain_game": "tech",
                "target_role": "Backend Engineer",
                "company_name": "Acme",
                "tone": "professional",
                "length": "medium",
                "language": "auto",
            },
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["salutation"]
        assert isinstance(body["body"], list) and body["body"]
        assert body["plain_text"]
        assert body["meta"]["domain_game"] == "tech"

    def test_the_llm_prompt_carries_the_job_description_and_the_domain(
        self, client, valid_pdf, stubbed_llm
    ):
        c, _ = client
        c.post(
            "/api/cover-letter",
            files={"file": ("input.pdf", valid_pdf, "application/pdf")},
            data={"jd": "Vacante de atención al cliente en tienda", "domain_game": "general"},
        )
        assert stubbed_llm.calls, "the LLM was never called"
        prompt = stubbed_llm.calls[0]
        assert "Vacante de atención al cliente en tienda" in prompt
        assert "Atención al Cliente & Ventas" in prompt

    def test_invalid_domain_game_returns_422(self, client, valid_pdf):
        c, _ = client
        r = c.post(
            "/api/cover-letter",
            files={"file": ("input.pdf", valid_pdf, "application/pdf")},
            data={"domain_game": "made_up_game"},
        )
        assert r.status_code == 422
        assert "domain_game" in r.json()["detail"]

    @pytest.mark.parametrize(
        "field,bad_value",
        [
            ("tone", "shouty"),
            ("length", "epic"),
            ("language", "fr"),
        ],
    )
    def test_invalid_options_return_422(self, client, valid_pdf, field, bad_value):
        c, _ = client
        r = c.post(
            "/api/cover-letter",
            files={"file": ("input.pdf", valid_pdf, "application/pdf")},
            data={field: bad_value},
        )
        assert r.status_code == 422
        assert field in r.json()["detail"]

    def test_unreadable_model_answer_returns_502(self, client, valid_pdf, stubbed_llm):
        # The orchestrator was already built with the stub provider when the
        # `client` fixture imported main, so the only way to change what the
        # model "says" is to swap the stub's response.
        stubbed_llm.response = "lo siento, no puedo"
        c, _ = client
        r = c.post(
            "/api/cover-letter",
            files={"file": ("input.pdf", valid_pdf, "application/pdf")},
        )
        assert r.status_code == 502

    def test_rate_limit_scope_is_cover_letter(self, client, valid_pdf):
        from main import _RL_HITS

        c, _ = client
        c.post(
            "/api/cover-letter",
            files={"file": ("input.pdf", valid_pdf, "application/pdf")},
        )
        keys = [k for k in _RL_HITS if k.startswith("cover-letter:")]
        assert keys, "the cover-letter scope was never registered"


# ---------------------------------------------------------------------------
# Contact block — the signature is built from real data, never from the model
# ---------------------------------------------------------------------------


class _StubParser:
    """Parser stub whose header carries a known contact block."""

    def extract_text(self, path):  # pragma: no cover — not used in these tests
        return RESUME_TEXT

    def extract_header(self, text):
        return {
            "email": "cv@example.com",
            "phone": "+57 300 0000000",
            "linkedin": "linkedin.com/in/from-cv",
            "github": "",
            "portfolio": "",
        }


class TestContactBlock:
    @pytest.mark.asyncio
    async def test_signature_uses_the_real_contacts_not_the_model(self):
        """The model only supplies the name. The contacts come from the CV."""
        svc = CoverLetterService(_StubLLM(), _StubParser())
        out = await svc.generate_text(
            RESUME_TEXT,
            JD_TEXT,
            get_game("tech"),
            header=_StubParser().extract_header(RESUME_TEXT),
        )
        assert out["contact"]["email"] == "cv@example.com"
        assert out["contact"]["phone"] == "+57 300 0000000"
        assert out["contact"]["linkedin"] == "linkedin.com/in/from-cv"
        # The signature carries them, and the model's invented ones are gone.
        assert "cv@example.com" in out["signature"]
        assert "linkedin.com/in/from-cv" in out["signature"]
        assert "name@example.com" not in out["signature"]

    @pytest.mark.asyncio
    async def test_the_form_wins_over_the_cv(self):
        """A link typed in the form overrides what the PDF extraction found."""
        svc = CoverLetterService(_StubLLM(), _StubParser())
        out = await svc.generate_text(
            RESUME_TEXT,
            JD_TEXT,
            get_game("tech"),
            header=_StubParser().extract_header(RESUME_TEXT),
            contact_overrides={"linkedin": "linkedin.com/in/from-form"},
        )
        assert out["contact"]["linkedin"] == "linkedin.com/in/from-form"
        assert "linkedin.com/in/from-form" in out["signature"]
        assert "linkedin.com/in/from-cv" not in out["signature"]

    @pytest.mark.asyncio
    async def test_plain_text_carries_the_contact_block(self):
        svc = CoverLetterService(_StubLLM(), _StubParser())
        out = await svc.generate_text(
            RESUME_TEXT,
            JD_TEXT,
            get_game("tech"),
            header=_StubParser().extract_header(RESUME_TEXT),
        )
        assert "linkedin.com/in/from-cv" in out["plain_text"]


# ---------------------------------------------------------------------------
# The PDF
# ---------------------------------------------------------------------------


class TestCoverLetterPdf:
    def test_endpoint_returns_a_downloadable_pdf(self, client, valid_pdf):
        c, _ = client
        r = c.post(
            "/api/cover-letter",
            files={"file": ("input.pdf", valid_pdf, "application/pdf")},
            data={
                "jd": JD_TEXT,
                "domain_game": "tech",
                "letter_style": "classic",
                "accent": "navy",
            },
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("pdf_filename"), body
        assert body["pdf_filename"].startswith("cover_letter_")
        assert body["pdf_url"] == f"/api/download/{body['pdf_filename']}"
        assert body["meta"]["letter_style"] == "classic"
        assert body["meta"]["accent"] == "navy"

        pdf = c.get(body["pdf_url"])
        assert pdf.status_code == 200
        assert pdf.content.startswith(b"%PDF")

    def test_the_pdf_keeps_the_profile_url_intact(self, client, valid_pdf):
        """ATS crawlers read the text layer: a URL split at a hyphen reads as
        a broken URL."""
        c, _ = client
        r = c.post(
            "/api/cover-letter",
            files={"file": ("input.pdf", valid_pdf, "application/pdf")},
            data={
                "jd": JD_TEXT,
                "domain_game": "tech",
                "linkedin_url": "https://www.linkedin.com/in/jane-doe/",
                "letter_style": "classic",
            },
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["contact"]["linkedin"] == "https://www.linkedin.com/in/jane-doe/"

        pdf = c.get(body["pdf_url"])
        import pymupdf

        doc = pymupdf.open(stream=pdf.content, filetype="pdf")
        text = "\n".join(page.get_text() for page in doc)
        doc.close()
        assert "linkedin.com/in/jane-doe" in text

    def test_an_unknown_style_or_accent_falls_back(self, client, valid_pdf):
        c, _ = client
        r = c.post(
            "/api/cover-letter",
            files={"file": ("input.pdf", valid_pdf, "application/pdf")},
            data={
                "jd": JD_TEXT,
                "letter_style": "not-a-style",
                "accent": "not-a-palette",
            },
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["meta"]["letter_style"] == "classic"
        assert body["meta"]["accent"] == "none"


# ---------------------------------------------------------------------------
# Renderer helpers
# ---------------------------------------------------------------------------


class TestLetterRenderer:
    def test_unknown_styles_fall_back_to_the_default(self):
        from adapters.renderer.cover_letter_adapter import normalize_letter_style

        assert normalize_letter_style("modern") == "modern"
        assert normalize_letter_style("sidebar") == "sidebar"
        assert normalize_letter_style("bogus") == "classic"
        assert normalize_letter_style(None) == "classic"
        assert normalize_letter_style("") == "classic"

    def test_signature_links_use_the_ats_readable_label(self):
        from adapters.renderer.cover_letter_adapter import build_signature_links

        links = build_signature_links(
            {
                "linkedin": "https://www.linkedin.com/in/jane-doe/",
                "github": "https://github.com/jane",
                "portfolio": "",
            }
        )
        labels = [link["label"] for link in links]
        assert "linkedin.com/in/jane-doe" in labels
        assert "github.com/jane" in labels
        assert len(labels) == 2

    def test_the_storage_allows_the_cover_letter_filename(self):
        from adapters.storage.filesystem_storage import FilesystemStorage

        rgx = FilesystemStorage.download_filename_regex()
        assert rgx.fullmatch("cover_letter_1712345678.pdf")
        assert rgx.fullmatch("tailored_resume_1712345678.pdf")
        assert not rgx.fullmatch("cover_letter_abc.pdf")
        assert not rgx.fullmatch("../cover_letter_1.pdf")
        assert not rgx.fullmatch("cover_letter_1.PDF")
