"""Tests for the language guard of the translation mode.

The guard is the answer to a bug the prompt could not fix: the model
translated the section headings (the prompt spells those out literally)
and left **every bullet, job title, skill category, degree and
achievement** in Spanish. The prompt was rebalanced, but a prompt is a
request, not a guarantee — so the output language is verified here.

Two layers are covered:

* **The detector** (``domain.translation_facts``) — which strings still
  carry Spanish, and which English strings must NOT be flagged. The
  second half matters as much as the first: a false positive costs a
  wasted model call on every single CV.
* **The guard** (the generation pipeline) — the corrective retry, the
  targeted pass, and the guarantee that the returned CV is English.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from domain.translation_facts import (  # noqa: E402
    build_targeted_prompt,
    find_untranslated_fields,
    is_untranslated,
    set_path,
    spanish_markers_in,
    strip_degree_markers,
)


# ---------------------------------------------------------------------------
# The detector
# ---------------------------------------------------------------------------


class TestSpanishDetection:
    """Which strings are still in Spanish."""

    def test_a_spanish_bullet_is_detected(self):
        text = (
            "Incrementé la cobertura de pruebas automatizadas al 90% en "
            "módulos críticos del sistema."
        )
        assert is_untranslated(text)
        assert spanish_markers_in(text), "the markers list must not be empty"

    def test_a_spanish_job_title_is_detected(self):
        assert is_untranslated("Ingeniero TICs - QA")
        assert is_untranslated("Analista y Desarrollador de TIC")

    def test_a_spanish_skill_category_is_detected(self):
        assert is_untranslated("Lenguajes & Frameworks")
        assert is_untranslated("Bases de Datos & Cloud")
        assert is_untranslated("Inteligencia Artificial & LLMs")

    def test_a_spanish_degree_is_detected(self):
        assert is_untranslated(
            "Máster Universitario en Dirección y Gestión de Tecnologías de la Información"
        )

    def test_english_bullets_are_not_flagged(self):
        """A false positive costs a wasted model call on every CV."""
        assert not is_untranslated(
            "Built the backend with Python (FastAPI) for orchestration, "
            "while the interface was programmed in TypeScript with React."
        )
        assert not is_untranslated(
            "Validated medical flows for admissions, hospitalization, "
            "pharmacy and billing, ensuring regulatory compliance."
        )

    def test_english_tech_words_are_not_spanish_markers(self):
        """"backend" and "sector" are English words; treating them as
        Spanish markers was the first version's bug."""
        for text in (
            "Built the backend with Python",
            "Worked in the healthcare sector for years",
            "Experience with cloud services and containers",
        ):
            assert not is_untranslated(text), text

    def test_technology_names_are_not_flagged(self):
        for text in ("Docker", "Power BI", "Scrum", "PostgreSQL"):
            assert not is_untranslated(text)

    def test_a_single_word_is_not_judged(self):
        """Below two words there is no sentence to judge."""
        assert not is_untranslated("Java")


# ---------------------------------------------------------------------------
# The parsed-CV walk
# ---------------------------------------------------------------------------


class TestFindUntranslatedFields:
    """The paths the detector reports."""

    @pytest.fixture
    def parsed(self) -> dict[str, Any]:
        return {
            "name": "Jane Doe",
            "summary": "IT support analyst with 5 years of experience",
            "education": [
                {
                    "school": "Universidad de Bogota",
                    "degree": "Analisis y Desarrollo de Sistemas",
                    "dates": "2018 - 2022",
                }
            ],
            "skills": [
                {
                    "category": "Lenguajes & Frameworks",
                    "items": ["Python", "Automatización de pruebas"],
                }
            ],
            "experience": [
                {
                    "company": "Acme",
                    "role": "Analista y Desarrollador de TIC",
                    "dates": "2023 - Present",
                    "points": [
                        "Desarrollo de aplicaciones backend en PHP y Java.",
                        "Built a REST API with FastAPI and PostgreSQL.",
                    ],
                }
            ],
            "projects": [],
            "achievements": ["Diplomado en Big Data y Business Intelligence."],
        }

    def test_it_reports_the_prose_fields(self, parsed):
        offenders = find_untranslated_fields(parsed)
        assert "education[0].degree" in offenders
        assert "skills[0].category" in offenders
        assert "skills[0].items[1]" in offenders
        assert "experience[0].role" in offenders
        assert "experience[0].points[0]" in offenders
        assert "achievements[0]" in offenders

    def test_it_leaves_the_english_fields_alone(self, parsed):
        offenders = find_untranslated_fields(parsed)
        assert "experience[0].points[1]" not in offenders
        assert "summary" not in offenders

    def test_it_skips_proper_nouns(self, parsed):
        """A company or a university is a name: translating it would be
        wrong, and flagging it would be a false positive."""
        offenders = find_untranslated_fields(parsed)
        assert "experience[0].company" not in offenders
        assert "education[0].school" not in offenders
        assert "name" not in offenders

    def test_a_fully_english_cv_has_no_offenders(self):
        parsed = {
            "name": "Jane Doe",
            "summary": "IT support analyst with 5 years of experience.",
            "education": [
                {
                    "school": "Universidad de Bogota",
                    "degree": "Systems Analysis and Development",
                    "dates": "2018 - 2022",
                }
            ],
            "skills": [{"category": "Languages & Frameworks", "items": ["Python"]}],
            "experience": [
                {
                    "company": "Acme",
                    "role": "ICT Analyst and Developer",
                    "dates": "2023 - Present",
                    "points": ["Developed backend applications in PHP and Java."],
                }
            ],
            "projects": [],
            "achievements": ["Diploma in Big Data and Business Intelligence."],
        }
        assert find_untranslated_fields(parsed) == {}


# ---------------------------------------------------------------------------
# Writing the fixes back
# ---------------------------------------------------------------------------


class TestSetPath:
    """Writing the translation back into the document."""

    def test_it_writes_a_top_level_field(self):
        data = {"summary": "Desarrollo de software"}
        assert set_path(data, "summary", "Software development")
        assert data["summary"] == "Software development"

    def test_it_writes_a_nested_list_field(self):
        data = {"experience": [{"role": "Ingeniero TICs - QA"}]}
        assert set_path(data, "experience[0].role", "ICT Engineer - QA")
        assert data["experience"][0]["role"] == "ICT Engineer - QA"

    def test_it_writes_a_nested_dict_field(self):
        data = {"skills": [{"items": ["Python", "Automatización de pruebas"]}]}
        assert set_path(data, "skills[0].items[1]", "Test automation")
        assert data["skills"][0]["items"][1] == "Test automation"

    def test_it_refuses_a_path_that_does_not_exist(self):
        data = {"experience": []}
        assert not set_path(data, "experience[3].role", "ICT Engineer")
        assert not set_path(data, "nope[0]", "x")


# ---------------------------------------------------------------------------
# The targeted prompt
# ---------------------------------------------------------------------------


class TestTargetedPrompt:
    """The prompt for the second, focused pass."""

    def test_it_quotes_the_offending_strings(self):
        offenders = {
            "experience[0].role": "Analista y Desarrollador de TIC",
            "skills[0].category": "Lenguajes & Frameworks",
        }
        prompt = build_targeted_prompt(offenders)
        assert "Analista y Desarrollador de TIC" in prompt
        assert "Lenguajes & Frameworks" in prompt
        assert "experience[0].role" in prompt
        assert "English" in prompt

    def test_it_keeps_the_same_keys(self):
        prompt = build_targeted_prompt({"summary": "Desarrollo de software"})
        assert "summary" in prompt
        assert "Do not add, drop or merge" in prompt


# ---------------------------------------------------------------------------
# The RenderCV marker leak
# ---------------------------------------------------------------------------


class TestDegreeMarkers:
    """RenderCV prints "in" before a degree; a faithful copy doubles it."""

    def test_it_strips_the_leaked_marker(self):
        data = {
            "education": [
                {"degree": "in in Master's Degree in Computer Science"},
                {"degree": "in Bachelor's Degree"},
            ]
        }
        strip_degree_markers(data)
        assert data["education"][0]["degree"] == "Master's Degree in Computer Science"
        assert data["education"][1]["degree"] == "Bachelor's Degree"

    def test_it_leaves_a_clean_degree_alone(self):
        data = {"education": [{"degree": "Systems Engineering"}]}
        strip_degree_markers(data)
        assert data["education"][0]["degree"] == "Systems Engineering"

    def test_it_does_not_touch_a_degree_that_starts_with_a_word(self):
        """Only the bare marker "in" is stripped — "Ingeniería" is a word."""
        data = {"education": [{"degree": "Ingeniería de Sistemas"}]}
        strip_degree_markers(data)
        assert data["education"][0]["degree"] == "Ingeniería de Sistemas"
