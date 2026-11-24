"""
backend.adapters.renderer.cover_letter_adapter
==============================================

Renders a cover letter to PDF.

Why a dedicated adapter instead of reusing the CV renderers
------------------------------------------------------------
The CV renderers are built around a *sectioned document*: RenderCV's
Typst themes (``sb2nov`` / ``classic`` / ``moderncv``) expect a resume
schema (education, skills, experience, projects...), and the HTML
fallback renders the same section tree. A cover letter has none of that
— it is a salutation, an opening, a few paragraphs, a closing and a
signature — so there is nothing to feed those renderers.

This adapter therefore renders the letter from its own Jinja template
(``backend/templates/letter.html.j2``) through the same headless
Chromium the HTML fallback uses. It deliberately reuses the pieces that
make the CV output good:

* ``design_palettes.accent_css_variables`` → the exact same accent
  palettes the CV offers, so the letter matches the CV the user chose.
* ``_ats_link_label`` → profile URLs are printed as
  ``linkedin.com/in/<slug>`` instead of the word "LinkedIn", because
  ATS crawlers read the extracted text layer and not the link
  annotations. A wrapped URL would parse as a broken one.
* The same ATS-safety rules: body copy is never tinted, nothing gets a
  background fill behind the text, and the accent is a tint rather than
  a redesign.

Three letter styles mirror the three CV designs:

* ``classic`` → centred letterhead, serif body.
* ``modern``  → left-aligned letterhead, sans body, accent rule.
* ``sidebar`` → contact column on the left, letter on the right.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from jinja2 import Environment, FileSystemLoader, select_autoescape

from design_palettes import accent_css_variables
from adapters.renderer.playwright_html_adapter import _ats_link_label


_TEMPLATE_DIR = Path(__file__).resolve().parent.parent.parent / "templates"

#: The letter styles this adapter can render. Mirrored by the backend
#: catalogue (``routes/design_router.py``) so the UI never offers a
#: style the renderer does not know.
LETTER_STYLES = ("classic", "modern", "sidebar")

#: Default style when the request does not specify one.
DEFAULT_LETTER_STYLE = "classic"


def normalize_letter_style(value: Optional[str]) -> str:
    """Normalise a user-supplied style id.

    Unknown or empty values fall back to the default instead of raising:
    a stale bookmark or a hand-made curl should still produce a valid
    letter, just with the default design.
    """
    candidate = (value or "").strip().lower()
    if candidate in LETTER_STYLES:
        return candidate
    return DEFAULT_LETTER_STYLE


def build_signature_links(
    contact: dict,
) -> list[dict[str, str]]:
    """Turn the candidate's profile URLs into link descriptors.

    Each entry is ``{"url": ..., "label": ...}`` where the label is the
    ATS-readable form of the URL (the same one the CV prints).
    """
    links: list[dict[str, str]] = []
    for network in ("linkedin", "github", "portfolio"):
        url = (contact.get(network) or "").strip()
        if not url:
            continue
        label = _ats_link_label(url, network)
        if not label:
            continue
        links.append({"url": url, "label": label})
    return links


def _render_letter_html(
    letter_data: dict,
    *,
    style: str,
    accent: Optional[str],
) -> str:
    """Render the letter template to an HTML string."""
    env = Environment(
        loader=FileSystemLoader(str(_TEMPLATE_DIR)),
        autoescape=select_autoescape(["html"]),
    )
    env.filters["ats_link"] = lambda url, network: _ats_link_label(url, network)
    env.globals["ats_link"] = _ats_link_label
    template = env.get_template("letter.html.j2")
    return template.render(
        **letter_data,
        style=style,
        accent=accent_css_variables(accent),
    )


class CoverLetterAdapter:
    """Renders a cover letter dict to a PDF file on disk."""

    name = "playwright:cover_letter"

    def render(
        self,
        letter_data: dict,
        output_path: str,
        *,
        style: str = DEFAULT_LETTER_STYLE,
        accent: Optional[str] = None,
    ) -> None:
        """Render the letter and print it to ``output_path`` as a PDF.

        ``letter_data`` carries the contact block and the letter itself:
        ``name``, ``location``, ``phone``, ``email``, ``linkedin``,
        ``github``, ``portfolio``, ``salutation``, ``opening``, ``body``,
        ``closing``, ``signature_name``, ``signature_lines`` and
        ``signature_links``.

        ``style`` is one of ``classic`` / ``modern`` / ``sidebar``.
        ``accent`` names a palette from ``design_palettes``.
        """
        normalized_style = normalize_letter_style(style)
        html = _render_letter_html(
            letter_data,
            style=normalized_style,
            accent=accent,
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
                        "top": "0.6in",
                        "bottom": "0.6in",
                        "left": "0.6in",
                        "right": "0.6in",
                    },
                    print_background=True,
                )
            finally:
                browser.close()


__all__ = [
    "CoverLetterAdapter",
    "DEFAULT_LETTER_STYLE",
    "LETTER_STYLES",
    "build_signature_links",
    "normalize_letter_style",
]
