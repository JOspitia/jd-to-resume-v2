"""
Tests for ``adapters.parser.pymupdf_adapter.PyMuPDFParser``.

Covers:
    * Lazy accessor in main.py instantiates the adapter on first call.
    * The adapter satisfies the ``ResumeParser`` port structurally.
    * Header extraction handles common inputs (real email/phone/github/
      linkedin/portfolio, placeholders, edge cases).
"""

from __future__ import annotations

import sys

import pytest

sys.path.insert(0, ".")

from adapters.parser.pymupdf_adapter import PyMuPDFParser
from ports.resume_parser import ResumeParser


# ---------------------------------------------------------------------------
# Protocol satisfaction + module-level wiring.
# ---------------------------------------------------------------------------


class TestPyMuPDFParserContract:
    def test_adapter_satisfies_resume_parser_port(self):
        assert isinstance(PyMuPDFParser(), ResumeParser)

    def test_main_lazy_accessor_returns_adapter(self):
        from main import _get_resume_parser

        p1 = _get_resume_parser()
        p2 = _get_resume_parser()
        # Lazy: same instance on repeated calls.
        assert p1 is p2

    def test_main_backward_compat_functions(self):
        from main import _extract_header_from_pdf_text, extract_text

        # Both module-level functions exist and delegate to the adapter.
        assert callable(extract_text)
        assert callable(_extract_header_from_pdf_text)


# ---------------------------------------------------------------------------
# Header extraction behavior — the bulk of the port's value is in regex
# correctness against typical Spanish/English resume text.
# ---------------------------------------------------------------------------


@pytest.fixture
def parser() -> PyMuPDFParser:
    return PyMuPDFParser()


class TestExtractHeader:
    def test_empty_text_returns_empty_dict_with_placeholder_flags_false(
        self, parser
    ):
        out = parser.extract_header("")
        assert out["email"] == ""
        assert out["phone"] == ""
        assert out["github"] == ""
        assert out["linkedin"] == ""
        assert out["portfolio"] == ""
        assert out["has_placeholder_github"] is False
        assert out["has_placeholder_linkedin"] is False
        assert out["has_placeholder_portfolio"] is False

    def test_real_email_is_extracted(self, parser):
        text = "John Doe\nSoftware Engineer\njohn.doe@company.com\n+57 300 1234567"
        out = parser.extract_header(text)
        assert out["email"] == "john.doe@company.com"
        assert "+57" in out["phone"]

    def test_example_email_is_skipped(self, parser):
        text = "Contact: jane@example.com\nReal: real.person@gmail.com"
        out = parser.extract_header(text)
        # First match was "example.com" — skipped. Real email is picked.
        assert out["email"] == "real.person@gmail.com"

    def test_noreply_email_is_skipped(self, parser):
        text = "noreply@service.com\nreal@business.com"
        out = parser.extract_header(text)
        assert out["email"] == "real@business.com"

    def test_github_url_is_extracted(self, parser):
        text = "GitHub: github.com/johndoe\nEmail: a@b.com"
        out = parser.extract_header(text)
        assert "github.com/johndoe" in out["github"]

    def test_linkedin_url_is_extracted(self, parser):
        text = "LinkedIn: linkedin.com/in/johndoe"
        out = parser.extract_header(text)
        assert "linkedin.com/in/johndoe" in out["linkedin"]

    def test_portfolio_url_extracted_and_normalized(self, parser):
        text = "Portfolio: jd.dev\nEmail: x@gmail.com"
        out = parser.extract_header(text)
        # gmail.com is excluded; jd.dev should match and get https:// prefix.
        assert "jd.dev" in out["portfolio"]
        assert out["portfolio"].startswith("https://")

    def test_email_domain_excluded_from_portfolio(self, parser):
        text = "Email: someone@gmail.com\nMore: gmail.com is my host"
        out = parser.extract_header(text)
        # gmail.com appears as a domain but is in the exclude set; no portfolio match.
        assert out["portfolio"] == ""

    def test_github_bare_word_flags_placeholder(self, parser):
        # "GitHub" appears as a token but no actual github.com URL.
        text = "John Doe\nGitHub | LinkedIn | Portafolio\nEmail: j@d.com"
        out = parser.extract_header(text)
        assert out["github"] == ""
        assert out["has_placeholder_github"] is True
        assert out["has_placeholder_linkedin"] is True
        assert out["has_placeholder_portfolio"] is True

    def test_phone_with_short_digits_is_skipped(self, parser):
        text = "Phone: 12-34\nReal: +57 300 1234567"
        out = parser.extract_header(text)
        # First candidate had only 4 digits; skipped. Real phone picked.
        assert "+57" in out["phone"]

    def test_phone_with_dashes_and_parens(self, parser):
        text = "Phone: (300) 123-4567"
        out = parser.extract_header(text)
        assert out["phone"] != ""
        digits = "".join(c for c in out["phone"] if c.isdigit())
        assert len(digits) >= 10

    def test_skip_words_in_portfolio_are_filtered(self, parser):
        text = "Portfolio: example.com\nReal: mysite.dev"
        out = parser.extract_header(text)
        # example.com is a skip word; mysite.dev should match.
        assert "mysite.dev" in out["portfolio"]