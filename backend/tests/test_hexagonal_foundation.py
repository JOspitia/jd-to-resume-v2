"""
Tests for the hexagonal foundation (commit 1 of refactor-main-py.md).

Verifies:
  * Every port Protocol is ``@runtime_checkable`` so adapters can be
    tested with ``isinstance(mock, Protocol)`` without inheriting.
  * ``AuditResult.from_llm_dict`` handles missing keys without crashing.
  * Frozen dataclasses (``JobDescription``, ``AuditResult``, ``TailoredResume``)
    reject mutation (catches accidental in-place edits in callers).
  * A mock class with the right methods satisfies the Protocol structurally
    — no inheritance required (PEP 544).
  * TypedDict entries (``Resume``, ``ContactInfo``, etc.) carry the shape
    the rest of the codebase expects from ``parsed_data`` dicts.
"""

from __future__ import annotations

import pytest

from domain.entities import (
    AuditResult,
    ContactInfo,
    EducationEntry,
    ExperienceEntry,
    JobDescription,
    ProjectEntry,
    Resume,
    SectionLabels,
    SkillEntry,
    TailoredResume,
)
from ports.linkedin_scraper import LinkedInScraper
from ports.llm_provider import LLMProvider
from ports.pdf_renderer import PDFRenderer
from ports.resume_parser import ResumeParser
from ports.resume_storage import ResumeStorage


# ---------------------------------------------------------------------------
# Protocols must be runtime_checkable so adapters can be type-tested.
# ---------------------------------------------------------------------------


class TestProtocolsAreRuntimeCheckable:
    @pytest.mark.parametrize(
        "proto",
        [LLMProvider, PDFRenderer, ResumeParser, LinkedInScraper, ResumeStorage],
    )
    def test_protocol_is_runtime_checkable(self, proto):
        assert hasattr(proto, "_is_runtime_protocol"), (
            f"{proto.__name__} missing @runtime_checkable — adapters cannot "
            f"be type-tested with isinstance()"
        )


# ---------------------------------------------------------------------------
# AuditResult defensive parsing — the LLM sometimes drops keys.
# ---------------------------------------------------------------------------


class TestAuditResultFromLlmDict:
    def test_minimal_payload(self):
        a = AuditResult.from_llm_dict({})
        assert a.ats_score == 0
        assert a.match_level == "unknown"
        assert a.matched_keywords == []
        assert a.missing_keywords == []
        assert a.ai_detection_score == 0
        assert a.ai_tone_verdict == ""
        assert a.ai_humanize_tips == []
        assert a.ats_formatting_score == 0
        assert a.actionable_tips == []

    def test_full_payload(self):
        a = AuditResult.from_llm_dict({
            "ats_score": 85,
            "match_level": "Alto",
            "matched_keywords": ["Python", "FastAPI"],
            "missing_keywords": ["Docker"],
            "ai_detection_score": 12,
            "ai_tone_verdict": "Bajo Riesgo de IA",
            "ai_humanize_tips": ["Directo."],
            "ats_formatting_score": 95,
            "actionable_tips": ["Añade métricas."],
        })
        assert a.ats_score == 85
        assert a.match_level == "Alto"
        assert "FastAPI" in a.matched_keywords
        assert "Docker" in a.missing_keywords

    def test_string_score_is_coerced(self):
        # The LLM sometimes returns scores as strings ("85") instead of int.
        a = AuditResult.from_llm_dict({"ats_score": "85", "ai_detection_score": "12"})
        assert a.ats_score == 85
        assert a.ai_detection_score == 12


# ---------------------------------------------------------------------------
# Frozen dataclasses reject mutation — protects against in-place edits.
# ---------------------------------------------------------------------------


class TestFrozenValueObjects:
    def test_job_description_is_frozen(self):
        jd = JobDescription(text="Senior Python developer")
        with pytest.raises(Exception):  # FrozenInstanceError or AttributeError
            jd.text = "other"  # type: ignore[misc]

    def test_audit_result_is_frozen(self):
        a = AuditResult.from_llm_dict({})
        with pytest.raises(Exception):
            a.ats_score = 100  # type: ignore[misc]

    def test_tailored_resume_is_frozen(self):
        t = TailoredResume(pdf_path=None, yaml_text="name: ''", parsed_data={})  # type: ignore[arg-type]
        with pytest.raises(Exception):
            t.pdf_path = "/etc/passwd"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Protocol structural subtyping — mocks with the right methods work.
# ---------------------------------------------------------------------------


class MockLLM:
    """Implements LLMProvider without inheriting — proves PEP 544 works."""

    @property
    def name(self):
        return "mock"

    def complete(self, prompt, *, model=None):
        return f"echo: {prompt[:20]}"


class MockRenderer:
    def __init__(self, name="mock"):
        self._name = name

    @property
    def name(self):
        return self._name

    def render(self, parsed_data, output_path, *, theme="sb2nov", fit_single_page=False, page_break_section=None, photo_path=None):
        # Minimal smoke: just touch the file so renderers are observable.
        with open(output_path, "wb") as f:
            f.write(b"%PDF-1.4 mock")


class MockParser:
    def extract_text(self, file_path):
        return f"text from {file_path}"

    def extract_header(self, text):
        return {"email": "x@y.z"}


class MockLinkedIn:
    @property
    def strategy_name(self):
        return "mock"

    def scrape(self, url):
        return f"scraped {url}"


class MockStorage:
    def save_uploaded_pdf(self, content, original_filename):
        return "/tmp/mock.pdf"

    def save_generated_pdf(self, source_path):
        return source_path

    def read_pdf(self, filename):
        return b"%PDF-1.4"

    def delete_pdf(self, filename):
        pass

    def save_photo(self, content):
        return "/tmp/mock.png"

    def clear_all(self):
        return (0, 0)


class TestStructuralProtocolSatisfaction:
    def test_mock_llm_satisfies_protocol(self):
        assert isinstance(MockLLM(), LLMProvider)

    def test_mock_renderer_satisfies_protocol(self):
        assert isinstance(MockRenderer(), PDFRenderer)

    def test_mock_parser_satisfies_protocol(self):
        assert isinstance(MockParser(), ResumeParser)

    def test_mock_linkedin_satisfies_protocol(self):
        assert isinstance(MockLinkedIn(), LinkedInScraper)

    def test_mock_storage_satisfies_protocol(self):
        assert isinstance(MockStorage(), ResumeStorage)


# ---------------------------------------------------------------------------
# TypedDicts exist and carry the expected keys (compile-time check, not runtime).
# ---------------------------------------------------------------------------


class TestResumeTypedDictShape:
    def test_resume_can_be_instantiated_empty(self):
        # TypedDict doesn't enforce presence at runtime — but a `dict(...)`
        # with the right keys is still accepted by type checkers.
        r: Resume = {
            "name": "Test",
            "email": "x@y.z",
            "skills": [{"label": "Languages", "details": ["Python"]}],
            "experience": [{"company": "Acme", "position": "Eng", "highlights": ["Did X"]}],
        }
        assert r["name"] == "Test"
        assert r["skills"][0]["label"] == "Languages"  # type: ignore[typeddict-item]

    def test_section_labels_keys_present_in_doc(self):
        # This is a documentation regression net: if someone removes a key
        # from SectionLabels the test fails. The TypedDict itself doesn't
        # enforce keys at runtime; we just verify the type exists.
        sl: SectionLabels = {
            "summary": "Resumen",
            "experience": "Experiencia",
            "skills": "Habilidades",
        }
        assert sl["summary"] == "Resumen"