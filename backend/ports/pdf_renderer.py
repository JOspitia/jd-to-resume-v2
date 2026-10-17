"""
backend.ports.pdf_renderer
=========================

Port for any PDF renderer that takes a parsed Resume dict and writes a PDF.

Two adapters today:
    * RenderCVAdapter     (Typst + sb2nov | classic | moderncv themes)
    * PlaywrightHTMLAdapter (Jinja2 + headless Chromium; used for ``classic_html``
                             theme and as the universal fallback when RenderCV
                             fails)
"""

from __future__ import annotations

from typing import Optional, Protocol, runtime_checkable

from domain.entities import Resume


@runtime_checkable
class PDFRenderer(Protocol):
    """Renders a parsed Resume to a PDF file on disk."""

    @property
    def name(self) -> str:
        """Stable identifier for logs (e.g. ``"rendercv:sb2nov"``,
        ``"playwright:classic_html"``)."""
        ...

    def render(
        self,
        parsed_data: Resume,
        output_path: str,
        *,
        theme: str = "sb2nov",
        fit_single_page: bool = False,
        page_break_section: Optional[str] = None,
        photo_path: Optional[str] = None,
    ) -> None:
        """Render ``parsed_data`` to the file at ``output_path``.

        ``theme`` is advisory — adapters may ignore it when their renderer
        doesn't support multiple themes (e.g. PlaywrightHTMLAdapter only
        ships one template).

        ``fit_single_page`` tightens margins and line spacing so the CV
        fits on a single page.

        ``page_break_section`` inserts a hard page break before that
        section (``"experience"``, ``"projects"``, ...). ``None`` means
        no forced break.

        ``photo_path`` is the absolute filesystem path to an optional
        candidate photo; ``None`` skips the photo entirely.

        Raises on render failure. Callers should catch and fall back to a
        different adapter (the fallback policy lives in the application
        layer, not in the adapter).
        """
        ...


__all__ = ["PDFRenderer"]