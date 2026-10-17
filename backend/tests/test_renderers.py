"""
Tests for the renderer adapters and helpers.

Covers:
    * ``_ats_link_label`` produces the same labels as the original inline
      implementation (LinkedIn slug, GitHub slug, generic URL fallback).
    * ``_photo_to_data_uri`` returns empty for missing/None paths; encodes
      a real file as ``data:<mime>;base64,...``.
    * The Jinja2 template renders without error for a minimal Resume dict.
    * ``PlaywrightHTMLAdapter`` satisfies the ``PDFRenderer`` port.
    * ``RenderCVAdapter`` satisfies the ``PDFRenderer`` port.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, ".")

from adapters.renderer.playwright_html_adapter import (
    PlaywrightHTMLAdapter,
    _ats_link_label,
    _check_profile_urls_not_fragmented,
    _photo_to_data_uri,
    _render_html_template,
)
from adapters.renderer.rendercv_adapter import RenderCVAdapter
from ports.pdf_renderer import PDFRenderer


# ---------------------------------------------------------------------------
# Adapter protocol satisfaction.
# ---------------------------------------------------------------------------


class TestAdapterProtocol:
    def test_playwright_satisfies_protocol(self):
        assert isinstance(PlaywrightHTMLAdapter(), PDFRenderer)

    def test_rendercv_satisfies_protocol(self):
        assert isinstance(RenderCVAdapter("sb2nov"), PDFRenderer)


# ---------------------------------------------------------------------------
# _ats_link_label — the URL→visible-text transformation that keeps ATS
# parsers happy (extracted text layer must contain the full URL).
# ---------------------------------------------------------------------------


class TestAtsLinkLabel:
    def test_linkedin_url_strips_scheme_and_prefixes_slug(self):
        out = _ats_link_label("https://www.linkedin.com/in/john-doe", "linkedin")
        assert out == "linkedin.com/in/john-doe"

    def test_linkedin_url_with_trailing_slash(self):
        out = _ats_link_label("https://linkedin.com/in/jane/", "linkedin")
        assert out == "linkedin.com/in/jane"

    def test_linkedin_url_with_www(self):
        out = _ats_link_label("https://www.linkedin.com/in/john", "linkedin")
        assert out == "linkedin.com/in/john"

    def test_github_url_strips_scheme_and_prefixes_slug(self):
        out = _ats_link_label("https://github.com/johndoe", "github")
        assert out == "github.com/johndoe"

    def test_github_url_with_www(self):
        out = _ats_link_label("https://www.github.com/johndoe", "github")
        assert out == "github.com/johndoe"

    def test_generic_url_strips_scheme_only(self):
        out = _ats_link_label("https://example.com/path", "portfolio")
        assert out == "example.com/path"

    def test_empty_url_returns_empty(self):
        assert _ats_link_label("", "linkedin") == ""
        assert _ats_link_label("   ", "linkedin") == ""

    def test_url_with_no_scheme_keeps_bare(self):
        out = _ats_link_label("linkedin.com/in/john", "linkedin")
        assert out == "linkedin.com/in/john"

    def test_linkedin_url_with_subpath(self):
        out = _ats_link_label("https://linkedin.com/in/john-doe/details", "linkedin")
        assert out == "linkedin.com/in/john-doe/details"

    def test_label_is_html_escaped(self):
        # If a URL contains HTML special chars, the label must be escaped
        # so it doesn't break the rendered HTML.
        out = _ats_link_label('https://example.com/<script>alert(1)</script>', "portfolio")
        assert "<script>" not in out
        assert "&lt;script&gt;" in out


# ---------------------------------------------------------------------------
# _photo_to_data_uri — encodes a photo file as a ``data:`` URI.
# ---------------------------------------------------------------------------


class TestPhotoToDataUri:
    def test_returns_empty_for_none(self):
        assert _photo_to_data_uri(None) == ""

    def test_returns_empty_for_empty_string(self):
        assert _photo_to_data_uri("") == ""

    def test_returns_empty_for_missing_file(self):
        assert _photo_to_data_uri("/nonexistent/path.png") == ""

    def test_encodes_real_png_file(self, tmp_path):
        # A 1x1 transparent PNG.
        png_bytes = (
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
            b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\rIDATx\x9cc\x00\x01"
            b"\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
        )
        png_path = tmp_path / "photo.png"
        png_path.write_bytes(png_bytes)
        out = _photo_to_data_uri(str(png_path))
        assert out.startswith("data:image/png;base64,")
        # The encoded bytes should round-trip.
        import base64
        encoded = out.split(",", 1)[1]
        assert base64.b64decode(encoded) == png_bytes


# ---------------------------------------------------------------------------
# Template rendering — smoke test that the Jinja2 template compiles and
# renders without error against a minimal Resume dict.
# ---------------------------------------------------------------------------


_MINIMAL_LABELS = {
    "summary": "Resumen",
    "education": "Educación",
    "skills": "Habilidades",
    "experience": "Experiencia",
    "projects": "Proyectos",
    "achievements": "Logros",
}


class TestRenderHtmlTemplate:
    def test_renders_minimal_dict_without_error(self):
        parsed = {
            "name": "Jane Doe",
            "email": "jane@example.com",
            "phone": "+57 300 1234567",
            "location": "Bogotá, Colombia",
            "summary": "Senior backend engineer with 10y of experience.",
            "education": [],
            "skills": [],
            "experience": [],
            "projects": [],
            "achievements": [],
        }
        html = _render_html_template(parsed, _MINIMAL_LABELS)
        assert "Jane Doe" in html
        assert "jane@example.com" in html
        assert "+57 300 1234567" in html
        assert "Bogotá, Colombia" in html
        assert "Senior backend engineer" in html

    def test_renders_with_photo_data_uri(self):
        parsed = {
            "name": "With Photo",
            "email": "",
            "phone": "",
            "location": "",
            "summary": "",
            "education": [],
            "skills": [],
            "experience": [],
            "projects": [],
            "achievements": [],
        }
        html = _render_html_template(
            parsed,
            _MINIMAL_LABELS,
            photo_path="/nonexistent.png",  # missing → empty data URI
        )
        assert "With Photo" in html

    def test_renders_with_profile_links(self):
        parsed = {
            "name": "LinkedIn User",
            "linkedin": "https://linkedin.com/in/test",
            "github": "https://github.com/test",
            "portfolio": "https://myportfolio.dev",
            "email": "",
            "phone": "",
            "location": "",
            "summary": "",
            "education": [],
            "skills": [],
            "experience": [],
            "projects": [],
            "achievements": [],
        }
        html = _render_html_template(parsed, _MINIMAL_LABELS)
        assert "linkedin.com/in/test" in html
        assert "github.com/test" in html
        assert "myportfolio.dev" in html

    def test_renders_experience_section(self):
        parsed = {
            "name": "Exp User",
            "email": "",
            "phone": "",
            "location": "",
            "summary": "",
            "education": [],
            "skills": [],
            "experience": [
                {
                    "role": "Senior Engineer",
                    "company": "Acme Corp",
                    "dates": "2020 - Present",
                    "points": ["Did X", "Did Y"],
                }
            ],
            "projects": [],
            "achievements": [],
        }
        html = _render_html_template(parsed, _MINIMAL_LABELS)
        assert "Senior Engineer" in html
        assert "Acme Corp" in html
        assert "Did X" in html

    def test_renders_page_break_section(self):
        parsed = {
            "name": "Page Break User",
            "email": "",
            "phone": "",
            "location": "",
            "summary": "summary text",
            "education": [],
            "skills": [],
            "experience": [],
            "projects": [],
            "achievements": [],
        }
        html = _render_html_template(
            parsed, _MINIMAL_LABELS, page_break_section="summary"
        )
        assert "manual-page-break" in html


# ---------------------------------------------------------------------------
# _check_profile_urls_not_fragmented — regression net for the URL wrap bug.
# ---------------------------------------------------------------------------


class TestCheckProfileUrlsNotFragmented:
    def test_does_not_raise_for_missing_file(self, tmp_path):
        # The check is non-fatal (only prints a warning), so this just
        # confirms the function doesn't crash on missing input.
        _check_profile_urls_not_fragmented(str(tmp_path / "missing.pdf"), {})

    def test_does_not_raise_for_empty_dict(self, tmp_path):
        # Write a minimal PDF (we don't care if it's valid; the check
        # only looks at URLs in the text layer).
        fake_pdf = tmp_path / "fake.pdf"
        fake_pdf.write_bytes(b"%PDF-1.4 fake")
        # Without real fitz parsing this might silently no-op; that's OK.
        _check_profile_urls_not_fragmented(str(fake_pdf), {"linkedin": ""})


# ---------------------------------------------------------------------------
# Adapter render() method invocation (smoke tests; full PDF output not checked).
# ---------------------------------------------------------------------------


class TestRenderCVAdapter:
    def test_name_reflects_theme(self):
        a = RenderCVAdapter("classic")
        assert a.name == "rendercv:classic"
        b = RenderCVAdapter("sb2nov")
        assert b.name == "rendercv:sb2nov"


class TestPlaywrightHTMLAdapter:
    def test_name_is_classic_html(self):
        assert PlaywrightHTMLAdapter().name == "playwright:classic_html"