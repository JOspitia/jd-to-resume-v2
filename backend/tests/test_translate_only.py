"""Tests for the faithful translation mode (``translate_only``).

The mode promises one thing: **the same CV, in another language**. No
tailoring, no rewriting, no invented content. The prompt is the main
defence (it carries the "change nothing else" contract) and this file
pins that contract down so it cannot be weakened by accident.

Two layers are covered:

* **The prompt** (``domain.translate_prompts``) — what the model is
  told. Fast, no HTTP.
* **The endpoint** (``POST /api/generate`` with ``translate_only=true``)
  — what actually reaches the model and what comes out. The LLM is
  stubbed so the test never touches a real provider.

What is NOT covered (intentional):
    * The quality of the English produced by a real model. That is a
      judgement call, not an assertion.
    * The rendering (covered by ``test_renderers.py``).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pymupdf
import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


# ---------------------------------------------------------------------------
# Stubs
# ---------------------------------------------------------------------------


class _RecordingProvider:
    """LLM provider that records every prompt it is handed."""

    name = "recording"

    def __init__(self, response: str) -> None:
        self.response = response
        self.prompts: list[str] = []

    def complete(self, prompt: str, *, model: str | None = None) -> str:
        self.prompts.append(prompt)
        return self.response


def _translated_resume_json() -> dict[str, Any]:
    """The JSON a translation model is expected to return."""
    return {
        "name": "Jane Doe",
        "location": "Bogota, CO",
        "phone": "+57 300 000 0000",
        "email": "jane@example.com",
        "portfolio": "",
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
        "skills": [{"category": "Backend", "items": ["Python", "FastAPI"]}],
        "experience": [
            {
                "company": "Acme",
                "role": "Senior Engineer",
                "dates": "2023 - Present",
                "points": ["Built a streaming CV pipeline in 30 days"],
            }
        ],
        "projects": [],
        "achievements": [],
        "section_labels": {
            "summary": "Professional Summary",
            "education": "Education",
            "skills": "Skills",
            "experience": "Work Experience",
            "projects": "Projects",
            "achievements": "Achievements",
            "portfolio": "Portfolio",
        },
    }


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _pdf_bytes(text: str) -> bytes:
    """Build a real one-page PDF whose text layer is ``text``."""
    doc = pymupdf.open()
    page = doc.new_page()
    y = 50
    for line in text.splitlines():
        page.insert_text((50, y), line)
        y += 18
    path = Path(__file__).parent / "_tmp_translate_fixture.pdf"
    doc.save(str(path))
    doc.close()
    data = path.read_bytes()
    path.unlink(missing_ok=True)
    return data


SPANISH_RESUME = """Jane Doe
Analista de soporte de TI con 5 anos de experiencia
Mantenimiento de 200 impresoras en todo el campus
Desarrollo de una API REST con FastAPI y PostgreSQL
Soporte a estudiantes, profesores y personal administrativo
Habilidades: Python, FastAPI, PostgreSQL, Docker, React
Universidad Nacional, Ingenieria de Sistemas, 2018 - 2022
Universidad de Bogota, Analisis y Desarrollo de Sistemas, 2023 - Actualidad
Desarrollo de una aplicacion web con Flask y React
Publicacion de un plugin con 2K+ descargas y 4,5 de calificacion
Experiencia profesional en soporte de usuario y mantenimiento de equipos
Trabajo con estudiantes y personal administrativo para resolver problemas
Sistema degestion de inventario para una empresa de retail
Coordinacion con los gerentes para priorizar las tareas del equipo
Metodologico del sistema y documentacion de procesos
Estudiante de ultimo ano con interes en la tecnologia
Experiencia/projects en Python, Docker y React
Uso de GitHub para el trabajo en equipo y las revisiones de codigo
Comunicacion efectiva con clientes internos y externos
Resolucion de problemas en entornos de produccion
Presentacion de resultados al equipo de forma clara y ordenada
Trabajo bajo presion y con plazos strictos
Nivel de ingles avanzado para la comunicacion internacional
Certificacion en Scrum fundamentals
Participacion en el programa de mentoring del centro decarrier"""


ENGLISH_RESUME = """Jane Doe
IT support analyst with 5 years of experience
Maintenance of 200 printers across the entire campus
Development of a REST API with FastAPI and PostgreSQL
Support for students, professors and administrative staff
Skills: Python, FastAPI, PostgreSQL, Docker, React
National University, Systems Engineering, 2018 - 2022
University of Bogota, Systems Analysis and Development, 2023 - Present
Development of a web application with Flask and React
Publication of a plugin with 2K+ downloads and a 4.5 rating
Professional experience in user support and equipment maintenance
Working with students and administrative staff to solve problems
Inventory management system for a retail company
Coordination with managers to prioritise the team tasks
I designed the system and documented the processes
Final year student with an interest in technology
Experience with Python, Docker and React
Using GitHub for teamwork and code reviews
Effective communication with internal and external clients
Problem solving in production environments
Presenting results to the team in a clear and orderly way
Working under pressure and with strict deadlines
Advanced English level for international communication
Scrum fundamentals certification
Participation in the mentoring programme of the career centre"""


@pytest.fixture
def spanish_pdf() -> bytes:
    return _pdf_bytes(SPANISH_RESUME)


@pytest.fixture
def english_pdf() -> bytes:
    return _pdf_bytes(ENGLISH_RESUME)


@pytest.fixture
def provider() -> _RecordingProvider:
    return _RecordingProvider(json.dumps(_translated_resume_json()))


@pytest.fixture
def client(monkeypatch, tmp_path, provider):
    """TestClient whose generation pipeline talks to the recording stub.

    The pipeline reaches the model through the shared orchestrator, so the
    orchestrator is swapped for one holding a single recording provider.
    """
    import importlib
    import sys

    for k, v in {"RATE_LIMIT_DEFAULT": "1000/minute"}.items():
        monkeypatch.setenv(k, v)

    saved_out, saved_err = sys.stdout, sys.stderr
    sys.modules.pop("main", None)
    mod = importlib.import_module("main")
    sys.stdout, sys.stderr = saved_out, saved_err

    from application.services.llm_orchestrator import LLMOrchestrator

    monkeypatch.setattr(
        mod._generation_service, "_llm", LLMOrchestrator([provider])
    )

    # Keep generated PDFs out of the real output folder.
    new_output = tmp_path / "output"
    new_output.mkdir(parents=True, exist_ok=True)
    new_photos = tmp_path / "photos"
    new_photos.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(mod._storage, "_output_dir", new_output)
    monkeypatch.setattr(mod._storage, "_photos_dir", new_photos)
    mod._OUTPUT_DIR = str(new_output)
    mod._PHOTOS_DIR = str(new_photos)

    return TestClient(mod.app), mod


# ---------------------------------------------------------------------------
# The prompt
# ---------------------------------------------------------------------------


class TestTranslationPrompt:
    """The contract the model receives."""

    def _prompt(self, **kwargs) -> str:
        from domain.translate_prompts import build_translation_prompt

        return build_translation_prompt("CV HERE", **kwargs)

    def test_it_asks_for_a_translation_and_not_a_rewrite(self):
        prompt = self._prompt()
        assert "professional translator" in prompt
        assert "TRANSLATE, DO NOT REWRITE" in prompt
        assert "do not improve, rewrite, shorten, expand or optimise" in prompt

    def test_it_forbids_tailoring(self):
        prompt = self._prompt()
        assert "NO TAILORING" in prompt
        assert "There is no job description" in prompt

    def test_it_forbids_additions_and_inventions(self):
        prompt = self._prompt()
        assert "NO ADDITIONS AND NO INVENTIONS" in prompt
        assert "Do not add achievements" in prompt

    def test_it_protects_the_contact_fields(self):
        prompt = self._prompt(
            contact_header={
                "email": "jane@example.com",
                "phone": "555-1234",
                "linkedin": "https://linkedin.com/in/jane",
                "github": "https://github.com/jane",
                "portfolio": "",
            }
        )
        assert "jane@example.com" in prompt
        assert "555-1234" in prompt
        assert "linkedin.com/in/jane" in prompt
        assert "Never translate or reformat a URL" in prompt

    def test_it_carries_the_source_resume(self):
        prompt = self._prompt()
        assert "CV HERE" in prompt

    def test_it_never_mentions_a_job_description(self):
        """The tailoring prompt has a "Job Description / Target
        Requirements" block. The translation prompt must not have one:
        that absence is the whole point of the mode."""
        prompt = self._prompt()
        assert "Job Description / Target Requirements" not in prompt

    def test_the_output_schema_matches_the_cv_schema(self):
        """Both prompts must produce the same JSON shape, otherwise the
        renderers cannot paint a translated CV."""
        from domain.translate_prompts import build_translation_prompt

        prompt = build_translation_prompt("CV HERE")
        for key in (
            '"name"',
            '"location"',
            '"phone"',
            '"email"',
            '"portfolio"',
            '"linkedin"',
            '"github"',
            '"summary"',
            '"education"',
            '"skills"',
            '"experience"',
            '"projects"',
            '"achievements"',
            '"section_labels"',
        ):
            assert key in prompt, f"missing key in the translation schema: {key}"

    def test_it_uses_the_english_section_labels(self):
        prompt = self._prompt()
        assert "Professional Summary" in prompt
        assert "Work Experience" in prompt

    def test_it_translates_the_date_markers(self):
        prompt = self._prompt()
        assert '"Actualidad" -> "Present"' in prompt

    def test_it_carries_the_certifications_over(self):
        """A certification is content. The schema has an ``achievements``
        array for it, and the prompt has to say so — otherwise the model
        drops the section and the translation loses information."""
        prompt = self._prompt()
        assert '"achievements" array' in prompt
        assert "Certificaciones" in prompt
        assert "Dropping a" in prompt and "content loss" in prompt


# ---------------------------------------------------------------------------
# The endpoint
# ---------------------------------------------------------------------------


class TestTranslateOnlyEndpoint:
    """``POST /api/generate`` with ``translate_only=true``."""

    def test_the_model_receives_the_translation_prompt(
        self, client, spanish_pdf, provider
    ):
        c, _ = client
        r = c.post(
            "/api/generate",
            files={"file": ("cv.pdf", spanish_pdf, "application/pdf")},
            data={
                "translate_only": "true",
                "jd": "Buscamos un desarrollador backend con Docker y Kubernetes",
                "theme": "classic_html",
            },
        )
        assert r.status_code == 200, r.text
        assert provider.prompts, "the LLM was never called"
        prompt = provider.prompts[0]
        assert "professional translator" in prompt
        # The job description must not reach the model at all.
        assert "Kubernetes" not in prompt
        assert "Job Description / Target Requirements" not in prompt

    def test_the_result_is_a_downloadable_pdf(self, client, spanish_pdf, provider):
        c, mod = client
        r = c.post(
            "/api/generate",
            files={"file": ("cv.pdf", spanish_pdf, "application/pdf")},
            data={"translate_only": "true", "theme": "classic_html"},
        )
        assert r.status_code == 200, r.text
        events = [
            json.loads(line.removeprefix("data: "))
            for line in r.text.splitlines()
            if line.startswith("data: ")
        ]
        finish = events[-1]
        assert finish.get("download_url"), finish
        assert finish["download_url"].startswith("/api/download/")

        filename = finish["download_url"].rsplit("/", 1)[-1]
        assert (Path(mod._OUTPUT_DIR) / filename).exists()

    def test_the_finish_event_reports_the_translation(
        self, client, spanish_pdf, provider
    ):
        c, _ = client
        r = c.post(
            "/api/generate",
            files={"file": ("cv.pdf", spanish_pdf, "application/pdf")},
            data={"translate_only": "true", "theme": "classic_html"},
        )
        events = [
            json.loads(line.removeprefix("data: "))
            for line in r.text.splitlines()
            if line.startswith("data: ")
        ]
        translation = events[-1].get("translation") or {}
        assert translation.get("target_language") == "en"
        assert translation.get("source_language") == "es"
        assert translation.get("translation_only") is True

    def test_a_cv_that_is_already_in_english_is_refused(
        self, client, english_pdf, provider
    ):
        """Translating English into English is a no-op, and the user is
        told so instead of getting a pointless re-render."""
        c, _ = client
        r = c.post(
            "/api/generate",
            files={"file": ("cv.pdf", english_pdf, "application/pdf")},
            data={"translate_only": "true", "theme": "classic_html"},
        )
        assert r.status_code == 200, r.text
        assert "E_CV_ALREADY_ENGLISH" in r.text
        assert not provider.prompts, "the model must not be called"

    def test_the_normal_flow_is_untouched(self, client, spanish_pdf, provider):
        """Without the flag, the pipeline keeps the tailoring prompt."""
        c, _ = client
        r = c.post(
            "/api/generate",
            files={"file": ("cv.pdf", spanish_pdf, "application/pdf")},
            data={
                "jd": "Buscamos un desarrollador backend con Docker y Kubernetes",
                "theme": "classic_html",
            },
        )
        assert r.status_code == 200, r.text
        prompt = provider.prompts[0]
        assert "professional translator" not in prompt
        assert "Job Description / Target Requirements" in prompt
