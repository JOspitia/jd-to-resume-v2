"""
backend.ports.resume_parser
==========================

Port for parsing a resume PDF into plain text + structured header fields.

One adapter today:
    * PyMuPDFAdapter  (pymupdf.open + page.get_text() + /Link annotations)

Future adapter (out of scope): pdfplumber, Tika, an OCR pipeline for
scanned PDFs.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class ResumeParser(Protocol):
    """Extracts the text + header fields from a PDF resume."""

    def extract_text(self, file_path: str) -> str:
        """Return the PDF's plain text with all /Link URIs concatenated.

        The result feeds the LLM prompt (so the LLM sees both the rendered
        text and the actual URLs the PDF hyperlinks to — Workday / Greenhouse
        / Taleo parsers care about both).
        """
        ...

    def extract_header(self, text: str) -> dict[str, str]:
        """Pull structured contact fields out of the raw text.

        Returns a dict with keys ``email``, ``phone``, ``location``,
        ``github``, ``linkedin``, ``portfolio`` (all optional — only
        fields the regex matched are present). Used by the generation
        pipeline to preserve contact info across refinements even when the
        user does not retype it in the form.
        """
        ...


__all__ = ["ResumeParser"]