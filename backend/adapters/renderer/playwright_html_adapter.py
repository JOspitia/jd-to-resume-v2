"""
backend.adapters.renderer.playwright_html_adapter
=================================================

Adapter that renders the HTML template via headless Chromium.

Loads the Jinja2 template from ``backend/templates/classic.html.j2``
(relative to the package), renders it with the parsed Resume dict plus
the ats_link helper, then drives Playwright to print the HTML to a PDF.

The HTML→PDF step uses Chromium's ``page.pdf()`` with Letter page size
and 0.4 inch margins (matching what the original inline template set).
"""

from __future__ import annotations

import base64
import mimetypes
import os
import re
from html import escape
from pathlib import Path
from typing import Optional

from jinja2 import Environment, FileSystemLoader, select_autoescape

from ports.pdf_renderer import PDFRenderer


_TEMPLATE_DIR = Path(__file__).resolve().parent.parent.parent / "templates"


def _ats_link_label(url: str, network: str) -> str:
    """Render a profile URL as machine-readable visible text.

    ATS crawlers read the PDF's extracted text layer, not its link
    annotations. An anchor whose visible text is just "LinkedIn" therefore
    hides the URL from them: the crawler sees the word and has nothing to
    follow. This produces the same label RenderCV already emits —
    ``linkedin.com/in/<slug>`` — so both renderers agree and the URL
    survives text extraction while remaining a clickable link.

    HTML-escaped: the result is injected into the template as raw markup.
    """
    cleaned = (url or "").strip()
    if not cleaned:
        return ""
    no_scheme = re.sub(r"^https?://", "", cleaned, flags=re.IGNORECASE)
    no_scheme = re.sub(r"^www\.", "", no_scheme, flags=re.IGNORECASE)
    no_scheme = no_scheme.rstrip("/")

    if network == "linkedin" and "linkedin.com/" in no_scheme:
        slug = no_scheme.split("linkedin.com/", 1)[1].strip("/")
        return escape(f"linkedin.com/{slug or 'in'}")
    if network == "github" and "github.com/" in no_scheme:
        slug = no_scheme.split("github.com/", 1)[1].strip("/")
        return escape(f"github.com/{slug}" if slug else "github.com")
    return escape(no_scheme)


def _photo_to_data_uri(photo_path: Optional[str]) -> str:
    """Read the candidate photo from disk and return a ``data:`` URI.

    Empty string when no photo is supplied (the template's
    ``{% if photo_uri %}`` skips the ``<img>``).
    """
    if not photo_path or not os.path.exists(photo_path):
        return ""
    mime, _ = mimetypes.guess_type(photo_path)
    if not mime:
        mime = "image/png"
    with open(photo_path, "rb") as f:
        encoded = base64.b64encode(f.read()).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def _check_profile_urls_not_fragmented(pdf_path: str, parsed_data: dict) -> None:
    """Open the rendered PDF with PyMuPDF and assert the LinkedIn / GitHub
    URLs land on a single text run.

    Defense against a regression that wrapped URLs at hyphens in the
    rendered PDF, producing an extracted text layer like
    ``linkedin.com/in/foo-`` / ``bar`` that ATS parsers read as two
    broken URLs instead of one. Prints a warning (does NOT raise) when
    the URL is missing from the text layer — the check is informational.
    Silently no-ops on missing/invalid PDFs (the file may not yet exist
    when this is called from a test, or be corrupted mid-write).
    """
    import pymupdf  # PyMuPDF (formerly imported as `fitz`)

    try:
        doc = pymupdf.open(pdf_path)
    except Exception:
        # File missing or not a PDF — nothing to check.
        return
    try:
        full_text = "\n".join(page.get_text() for page in doc)
    except Exception:
        return

    for url_kind, url_value in (
        ("linkedin", parsed_data.get("linkedin") or ""),
        ("github", parsed_data.get("github") or ""),
        ("portfolio", parsed_data.get("portfolio") or ""),
    ):
        if not url_value:
            continue
        # Strip scheme + www for matching (the template strips them).
        no_scheme = re.sub(r"^https?://", "", url_value, flags=re.IGNORECASE)
        no_scheme = re.sub(r"^www\.", "", no_scheme, flags=re.IGNORECASE).rstrip("/")
        # The rendercv-style label we'd expect to see intact.
        if url_kind == "linkedin" and "linkedin.com/" in no_scheme:
            slug = no_scheme.split("linkedin.com/", 1)[1].strip("/")
            label = f"linkedin.com/{slug or 'in'}"
        elif url_kind == "github" and "github.com/" in no_scheme:
            slug = no_scheme.split("github.com/", 1)[1].strip("/")
            label = f"github.com/{slug}" if slug else "github.com"
        else:
            label = no_scheme
        if label and label not in full_text:
            # Not a hard error (the template can choose to omit the URL
            # when empty), but flag it loudly.
            print(
                f"[ATS HTML WARN] {url_kind} URL '{label}' not found intact "
                f"in the rendered PDF text layer. The link annotation may "
                f"have fragmented the URL at a hyphen."
            )


def _render_html_template(
    parsed_data: dict,
    labels: dict,
    *,
    page_break_section: Optional[str] = None,
    photo_path: Optional[str] = None,
) -> str:
    """Render the Jinja2 template with the parsed Resume dict + helpers."""
    env = Environment(
        loader=FileSystemLoader(str(_TEMPLATE_DIR)),
        autoescape=select_autoescape(["html"]),
    )
    env.filters["ats_link"] = lambda url, network: _ats_link_label(url, network)
    env.globals["ats_link"] = _ats_link_label
    template = env.get_template("classic.html.j2")
    return template.render(
        **parsed_data,
        labels=labels,
        page_break_section=page_break_section,
        photo_uri=_photo_to_data_uri(photo_path),
    )


class PlaywrightHTMLAdapter:
    """Adapter that renders the Jinja2 template + drives headless Chromium."""

    name = "playwright:classic_html"

    def render(
        self,
        parsed_data: dict,
        output_path: str,
        *,
        theme: str = "classic_html",
        fit_single_page: bool = False,
        page_break_section: Optional[str] = None,
        photo_path: Optional[str] = None,
        labels: Optional[dict] = None,
    ) -> None:
        """Render the template and print the HTML to ``output_path`` as PDF.

        ``labels`` is a dict with at least ``summary``, ``education``,
        ``skills``, ``experience``, ``projects``, ``achievements``.
        ``fit_single_page`` is currently a hint (the CSS already targets
        a single page; tightening margins is a future enhancement).
        """
        if labels is None:
            labels = {
                "summary": "Resumen",
                "education": "Educación",
                "skills": "Habilidades",
                "experience": "Experiencia Laboral",
                "projects": "Proyectos",
                "achievements": "Logros",
            }
        html = _render_html_template(
            parsed_data,
            labels,
            page_break_section=page_break_section,
            photo_path=photo_path,
        )

        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            try:
                page = browser.new_page()
                page.set_content(html, wait_until="networkidle")
                page.pdf(
                    path=output_path,
                    format="Letter",
                    margin={
                        "top": "0.4in",
                        "bottom": "0.4in",
                        "left": "0.4in",
                        "right": "0.4in",
                    },
                    print_background=True,
                )
            finally:
                browser.close()

        # ATS integrity check (URL fragmentation regression net).
        _check_profile_urls_not_fragmented(output_path, parsed_data)


__all__ = [
    "PlaywrightHTMLAdapter",
    "_ats_link_label",
    "_photo_to_data_uri",
    "_check_profile_urls_not_fragmented",
    "_render_html_template",
]